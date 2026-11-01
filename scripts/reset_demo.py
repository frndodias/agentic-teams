"""Volta a demo para o estado limpo (rodar antes de cada ensaio e antes do evento).

uv run --with databricks-sdk --with requests python scripts/reset_demo.py --genie <space_id>

1. Apaga os objetos do sandbox (agentic_teams_sandbox).
2. Apaga de ecommerce os objetos promovidos pelo time (tag produzido_por = agentic_teams).
3. Lakebase: ARQUIVA por padrão — o histórico fica; execuções pendentes viram "descartado".
   --apagar-historico zera tudo (execuções, etapas, aprovações e checkpoints).
4. GitHub: fecha PRs abertos de branches agent/*, apaga as branches e remove produtos_dados/* da main.
5. Restaura o Genie space a partir de genie/estado_limpo.json.
6. Limpa o volume de artefatos.
"""
import argparse
import json
import subprocess
from pathlib import Path

import requests
from databricks.sdk import WorkspaceClient

p = argparse.ArgumentParser()
p.add_argument("--profile", default="fevm-fc")
p.add_argument("--catalog", default="fc_catalog")
p.add_argument("--warehouse", default="ed167610612860b6")
p.add_argument("--genie", required=True)
p.add_argument("--repo", default="frndodias/agentic-teams-pr")
p.add_argument("--app", default="agentic-teams")
p.add_argument("--apagar-historico", action="store_true", help="zera o histórico do time no Lakebase (padrão: arquivar)")
a = p.parse_args()
w = WorkspaceClient(profile=a.profile)


def sql(q):
    r = w.statement_execution.execute_statement(warehouse_id=a.warehouse, statement=q, wait_timeout="50s")
    if r.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"{q}\n{r.status.error.message if r.status.error else r.status.state}")
    return (r.result.data_array or []) if r.result else []


print("1) sandbox")
for (nome, tipo) in sql(f"SELECT table_name, table_type FROM {a.catalog}.information_schema.tables WHERE table_schema = 'agentic_teams_sandbox'"):
    sql(f"DROP {'VIEW' if 'VIEW' in tipo else 'TABLE'} IF EXISTS {a.catalog}.agentic_teams_sandbox.{nome}")
    print("   -", nome)

print("2) objetos promovidos em ecommerce")
for (nome,) in sql(f"SELECT DISTINCT table_name FROM {a.catalog}.information_schema.table_tags WHERE schema_name = 'ecommerce' "
                   "AND tag_name = 'produzido_por' AND tag_value = 'agentic_teams'"):
    tipo = sql(f"SELECT table_type FROM {a.catalog}.information_schema.tables WHERE table_schema='ecommerce' AND table_name='{nome}'")
    sql(f"DROP {'VIEW' if tipo and 'VIEW' in tipo[0][0] else 'TABLE'} IF EXISTS {a.catalog}.ecommerce.{nome}")
    print("   -", nome)

print("3) Lakebase (via app, que é dono das tabelas): " + ("apagando histórico" if a.apagar_historico else "arquivando"))
app_url = w.apps.get(a.app).url
tok = w.config.authenticate()["Authorization"]
r = requests.post(f"{app_url}/api/admin/reset", headers={"Authorization": tok}, timeout=120,
                  params={"apagar_historico": "true" if a.apagar_historico else "false"})
r.raise_for_status()
print("   -", r.json())

print("4) GitHub")
gh_token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
H = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
API = f"https://api.github.com/repos/{a.repo}"
for pr in requests.get(f"{API}/pulls", headers=H, params={"state": "open", "per_page": 100}).json():
    if pr["head"]["ref"].startswith("agent/"):
        requests.patch(f"{API}/pulls/{pr['number']}", headers=H, json={"state": "closed"})
        print("   - PR fechado", pr["number"])
for ref in requests.get(f"{API}/git/matching-refs/heads/agent/", headers=H).json():
    requests.delete(f"{API}/git/{ref['ref']}", headers=H)
    print("   - branch apagada", ref["ref"])
r = requests.get(f"{API}/contents/produtos_dados", headers=H, params={"ref": "main"})
for item in (r.json() if r.ok else []):
    if item["type"] != "dir":
        continue
    for f in requests.get(item["url"], headers=H).json():
        requests.delete(f"{API}/contents/{f['path']}", headers=H,
                        json={"message": f"reset da demo: remove {f['path']}", "sha": f["sha"], "branch": "main"})
        print("   - removido", f["path"])

print("5) Genie")
ss = json.loads(Path(__file__).resolve().parents[1].joinpath("genie/estado_limpo.json").read_text())
w.genie.update_space(a.genie, serialized_space=json.dumps(ss))
print("   - restaurado")

print("6) volume de artefatos")
for d in w.files.list_directory_contents(f"/Volumes/{a.catalog}/agentic_teams/artefatos"):
    for f in w.files.list_directory_contents(d.path):
        w.files.delete(f.path)
    w.files.delete_directory(d.path)
print("pronto: demo no estado limpo")
