"""Promove um produto de dados aprovado: sandbox -> ecommerce, e publica no Genie.

Lê os arquivos do produto na main do repositório de PR (fonte=github) ou no volume do time (fonte=volume),
troca o schema do sandbox pelo de produção, executa os .sql em ordem e adiciona as novas metric views (g_*) ao Genie.
"""
import argparse
import json
import os
import re

import requests
from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument("--produto", required=True)
p.add_argument("--run_id", required=True)
p.add_argument("--fonte", default="github")
p.add_argument("--repo", required=True)
p.add_argument("--catalog", required=True)
p.add_argument("--genie_space_id", default="")
p.add_argument("--leitores", default="", help="principais (vírgula) que recebem SELECT nos objetos promovidos")
a = p.parse_args()

SANDBOX, PROD = f"{a.catalog}.agentic_teams_sandbox", f"{a.catalog}.ecommerce"
spark = SparkSession.builder.getOrCreate()
w = WorkspaceClient()


def arquivos():
    if a.fonte == "github":
        base = f"https://api.github.com/repos/{a.repo}/contents/produtos_dados/{a.produto}"
        lst = requests.get(base, params={"ref": "main"}, timeout=30)
        lst.raise_for_status()
        return {f["name"]: requests.get(f["download_url"], timeout=30).text for f in lst.json() if f["type"] == "file"}
    pasta = f"/Volumes/{a.catalog}/agentic_teams/artefatos/{a.run_id}"
    return {n: open(f"{pasta}/{n}", encoding="utf-8").read() for n in os.listdir(pasta)}


fs = arquivos()
sqls = sorted(n for n in fs if n.endswith(".sql"))
print("arquivos:", list(fs), "| executando:", sqls)
# executa respeitando dependências: o que falhar por falta de tabela de origem volta para a fila
pendentes = []
for nome in sqls:
    conteudo = fs[nome].replace(SANDBOX + ".", PROD + ".").replace(f"`{a.catalog}`.`agentic_teams_sandbox`.", PROD + ".")
    for bloco in re.split(r"\n(?=-- objeto: )", conteudo):
        stmt = "\n".join(l for l in bloco.splitlines() if not l.startswith("-- objeto:")).strip().rstrip(";")
        if stmt:
            pendentes.append(stmt)
criados = []
for _ in range(len(pendentes) + 1):
    if not pendentes:
        break
    adiados = []
    for stmt in pendentes:
        m = re.search(rf"{re.escape(PROD)}\.([a-z0-9_]+)", stmt)
        try:
            spark.sql(stmt)
        except Exception as e:  # noqa: BLE001
            if "TABLE_OR_VIEW_NOT_FOUND" in str(e):
                print("   adiado (dependência):", m.group(1) if m else "?")
                adiados.append(stmt)
                continue
            raise
        print("->", m.group(1) if m else "?")
        if m:
            criados.append(m.group(1))
            tipo = "VIEW" if re.match(r"^\s*CREATE\s+OR\s+REPLACE\s+VIEW", stmt, re.I) else "TABLE"
            spark.sql(f"ALTER {tipo} {PROD}.{m.group(1)} SET TAGS ('produzido_por' = 'agentic_teams', 'run_id' = '{a.run_id}', "
                      f"'produto' = '{a.produto}')")
    if len(adiados) == len(pendentes):
        raise RuntimeError(f"dependências não resolvidas: {adiados[0][:300]}")
    pendentes = adiados
print("criados:", criados)
# o deploy aplica os grants: quem consome a gold (Genie/app; depois os grupos) precisa ler o que foi publicado
for principal in [x.strip() for x in a.leitores.split(",") if x.strip()]:
    for obj in criados:
        spark.sql(f"GRANT SELECT ON TABLE {PROD}.{obj} TO `{principal}`")
    print("SELECT concedido a", principal)

if a.genie_space_id:
    novas = [f"{PROD}.{c}" for c in criados if c.startswith("g_")]
    # REST direto: o SDK do ambiente serverless pode não ter os parâmetros novos da API do Genie
    sp = w.api_client.do("GET", f"/api/2.0/genie/spaces/{a.genie_space_id}", query={"include_serialized_space": "true"})
    ss = json.loads(sp["serialized_space"])
    mvs = ss.setdefault("data_sources", {}).setdefault("metric_views", [])
    existentes = {m["identifier"] for m in mvs}
    for n in novas:
        if n not in existentes:
            mvs.append({"identifier": n})
    mvs.sort(key=lambda m: m["identifier"])
    # a instrução da lacuna deixa de valer para o que acabou de ser publicado
    for ti in ss.get("instructions", {}).get("text_instructions", []):
        ti["content"] = [re.sub(r"\[LACUNA\].*?\[/LACUNA\]", "Métricas de compradores (recompra, recorrência, compradores ativos) "
                                "estão em " + ", ".join(novas) + ". Use-as para essas perguntas.", c, flags=re.S) for c in ti["content"]]
    w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{a.genie_space_id}", body={"serialized_space": json.dumps(ss)})
    print("genie atualizado com", novas)
print("promoção ok")
