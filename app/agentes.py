"""Os agentes do time: Supervisor, Discovery, Analyst, Engineer e Quality (prompts + ferramentas)."""
import datetime as dt
import json
import re

import config as C
import db
import dbx
from llm import Tool, extrair_json, rodar_agente

HOJE = lambda: dt.date.today().isoformat()  # noqa: E731


def _lit(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


CONTEXTO = f"""Ambiente (Databricks, Unity Catalog):
- Catálogo {C.CATALOG}. Dados de negócio em {C.FQ_DADOS} com prefixos: b_* = bronze (dado bruto, SEM acesso para agentes),
  s_* = silver (tabelas limpas), g_* = gold (metric views consumidas pelo Genie).
- Sandbox do time: {C.FQ_SANDBOX} (único lugar onde o time pode criar objetos). Tools governadas em {C.FQ_AGENTES}.
- Dialeto: Databricks SQL. Metric views: CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$ e consulta com MEASURE().
- LGPD: CPF, e-mail, nome e telefone são dados pessoais. Nunca exponha esses campos em objetos de saída; use hash (sha2) quando precisar de chave.
- Data de hoje: {{hoje}}. Responda sempre em português."""


def _ctx():
    return CONTEXTO.replace("{hoje}", HOJE())


# ---------------------------------------------------------------- ferramentas

def _bloqueia_bronze(sql: str):
    if re.search(r"(^|[\s.`(])b_[a-z0-9_]+", sql, flags=re.I):
        raise PermissionError("acesso negado: agentes não leem tabelas b_* (bronze). Use as tabelas s_* da silver.")


def t_consultar_sql(sql: str) -> str:
    s = sql.strip().rstrip(";")
    if not re.match(r"^(select|with|describe|show)\b", s, flags=re.I):
        raise PermissionError("somente leitura: use SELECT/WITH/DESCRIBE/SHOW")
    _bloqueia_bronze(s)
    return dbx.sql_texto(s, max_linhas=40)


def t_buscar_tabelas(termo: str = "") -> str:
    return dbx.sql_texto(f"SELECT * FROM {C.FQ_AGENTES}.buscar_tabelas({_lit(termo)}) WHERE tabela NOT RLIKE '\\\\.b_'", 80)


def t_descrever_tabela(nome: str) -> str:
    if re.search(r"\.b_", nome):
        raise PermissionError("acesso negado: bronze (b_*)")
    return dbx.sql_texto(f"SELECT * FROM {C.FQ_AGENTES}.descrever_tabela({_lit(nome)})", 120)


def t_listar_documentos() -> str:
    return dbx.sql_texto(f"SELECT * FROM {C.FQ_AGENTES}.listar_documentos()")


def t_ler_documento(nome_arquivo: str) -> str:
    r = dbx.sql(f"SELECT {C.FQ_AGENTES}.ler_documento({_lit(nome_arquivo)}) AS t")
    return (r["linhas"][0][0] if r["linhas"] else None) or "documento não encontrado"


def t_linhagem(tabela: str) -> str:
    return dbx.linhagem(tabela)


TOOLS_DISCOVERY = [
    Tool("buscar_tabelas", "Procura tabelas e metric views (nome ou comentário). termo vazio lista tudo.",
         {"termo": {"type": "string"}}),
    Tool("descrever_tabela", "Colunas, tipos e comentários de uma tabela (nome completo).", {"nome": {"type": "string"}}),
    Tool("consultar_sql", "Executa SQL somente leitura (SELECT/WITH/DESCRIBE/SHOW) e devolve até 40 linhas.",
         {"sql": {"type": "string"}}),
    Tool("listar_documentos", "Lista os documentos de negócio (contrato de dados, glossário, políticas).", {}, obrigatorios=[]),
    Tool("ler_documento", "Texto completo de um documento de negócio.", {"nome_arquivo": {"type": "string"}}),
    Tool("consultar_linhagem", "Linhagem (upstream/downstream) de uma tabela no Unity Catalog.", {"tabela": {"type": "string"}}),
]
for _t, _f in zip(TOOLS_DISCOVERY, [t_buscar_tabelas, t_descrever_tabela, t_consultar_sql, t_listar_documentos,
                                     t_ler_documento, t_linhagem]):
    _t.fn = _f


def tools_engineer(run_id: str):
    padrao = re.compile(rf"^\s*CREATE\s+OR\s+REPLACE\s+(?:TABLE|VIEW|MATERIALIZED\s+VIEW)\s+`?{C.CATALOG}`?\.`?{C.SCHEMA_SANDBOX}`?\.`?([a-z0-9_]+)`?",
                        flags=re.I)

    def criar_no_sandbox(nome_arquivo: str, sql: str) -> str:
        m = padrao.match(sql)
        if not m:
            raise PermissionError(f"só é permitido CREATE OR REPLACE TABLE/VIEW em {C.FQ_SANDBOX}.<nome>")
        _bloqueia_bronze(sql)
        obj = m.group(1)
        dbx.sql(sql.strip().rstrip(";"), max_linhas=1)
        for tipo in ("TABLE", "VIEW"):
            try:
                dbx.sql(f"ALTER {tipo} {C.FQ_SANDBOX}.{obj} SET TAGS ('run_id' = {_lit(run_id)}, 'agente' = 'engineer', "
                        f"'criado_em' = {_lit(HOJE())})")
                break
            except Exception:  # noqa: BLE001
                continue
        estado = (db.get_run(run_id) or {}).get("estado") or {}
        objetos = dict(estado.get("objetos", {}))  # obj -> {arquivo, sql}; recriar mantém a posição original
        objetos[obj] = {"arquivo": nome_arquivo, "sql": sql.strip().rstrip(";")}
        arquivos = {}
        for nome, o in objetos.items():
            arquivos.setdefault(o["arquivo"], []).append(f"-- objeto: {nome}\n{o['sql']};\n")
        arquivos = {k: "\n".join(v) for k, v in sorted(arquivos.items())}
        db.atualizar_run(run_id, estado={**estado, "objetos": objetos, "arquivos": arquivos})
        for nome_arq, conteudo in arquivos.items():
            db.registrar_artefato(run_id, "sql", nome_arq, conteudo)
        return f"OK: {C.FQ_SANDBOX}.{obj} criado e registrado em {nome_arquivo}"

    return [
        Tool("descrever_tabela", "Colunas e tipos de uma tabela.", {"nome": {"type": "string"}}, fn=t_descrever_tabela),
        Tool("consultar_sql", "SQL somente leitura para explorar e validar (até 40 linhas).", {"sql": {"type": "string"}},
             fn=t_consultar_sql),
        Tool("criar_no_sandbox", "Cria/atualiza UM objeto no sandbox (CREATE OR REPLACE TABLE/VIEW). "
             "nome_arquivo: 01_silver.sql para tabelas s_*, 02_gold.sql para metric views g_*.",
             {"nome_arquivo": {"type": "string", "enum": ["01_silver.sql", "02_gold.sql"]}, "sql": {"type": "string"}},
             fn=criar_no_sandbox),
    ]


def tools_quality(run_id: str, iteracao: int):
    def registrar_teste(teste: str, status: str, evidencia: str) -> str:
        st = "passou" if status.lower().startswith("pass") else "falhou"
        db.registrar_dq(run_id, iteracao, teste, st, evidencia[:2000])
        return "registrado"

    ts = [
        Tool("consultar_sql", "SQL somente leitura para testar os objetos (até 40 linhas).", {"sql": {"type": "string"}}),
        Tool("descrever_tabela", "Colunas e tipos de uma tabela.", {"nome": {"type": "string"}}),
        Tool("registrar_teste", "Registra o resultado de UM teste de qualidade (aparece ao vivo para o time).",
             {"teste": {"type": "string"}, "status": {"type": "string", "enum": ["passou", "falhou"]},
              "evidencia": {"type": "string"}}),
    ]
    ts[0].fn, ts[1].fn, ts[2].fn = t_consultar_sql, t_descrever_tabela, registrar_teste
    return ts


# ---------------------------------------------------------------- prompts e execução

def supervisor_plano(run_id, pergunta, resposta_genie):
    from llm import chat
    msg, a, b = chat([
        {"role": "system", "content": _ctx() + "\n\nVocê é o Supervisor de um time agêntico de engenharia de dados "
         "(Discovery, Analyst, Engineer, Quality). Seja breve e concreto."},
        {"role": "user", "content": f"Pedido do negócio: {pergunta}\nO Genie respondeu: {resposta_genie}\n\n"
         "Escreva um plano de 3 a 5 linhas curtas (uma por agente) de como o time vai disponibilizar essa informação."}],
        max_tokens=2000)  # folga: parte dos tokens vai para o raciocínio do modelo
    db.somar_tokens(run_id, a, b)
    db.evento(run_id, "supervisor", "plano", "Plano do time", {"texto": msg.content}, tokens_entrada=a, tokens_saida=b)
    return msg.content


def discovery(run_id, pergunta):
    system = _ctx() + """

Você é o Discovery Agent de um time de engenharia de dados. Missão: dado um pedido de negócio, descobrir no Unity Catalog
se a informação já existe e, se não existir, quais fontes permitem construí-la e quais regras de negócio se aplicam.
Como trabalhar:
1. Procure métricas existentes primeiro na gold (g_*), depois nas fontes da silver (s_*).
2. Inspecione as fontes candidatas (descrever_tabela; consultar_sql só com amostras pequenas e contagens).
3. Leia os documentos de negócio relevantes: o contrato de dados tem as regras oficiais (pedido pago, pedido de teste, identidade).
4. Use a linhagem quando ajudar a entender a origem do dado.
Regras: só leitura; não use tabelas b_*; no máximo 12 chamadas de ferramenta; seja objetivo.
Termine com um parágrafo de resumo e um bloco ```json com:
{"metrica_existe": bool, "objetos_existentes": [str], "fontes": [{"tabela": str, "uso": str, "colunas_chave": [str]}],
 "regras_negocio": [str], "riscos_qualidade": [str], "resumo": str}"""
    txt = rodar_agente(run_id, "discovery", system, f"Pedido do negócio: {pergunta}", TOOLS_DISCOVERY)
    return extrair_json(txt) or {"resumo": txt}


def analyst(run_id, pergunta, descoberta):
    system = _ctx() + """

Você é o Analyst Agent. Transforme o pedido de negócio e os achados do Discovery numa especificação de produto de dados.
- Siga as regras do contrato de dados (não pergunte o que o contrato já define).
- Identifique ambiguidades que só o negócio pode decidir e faça no máximo 2 perguntas objetivas, cada uma com 2 ou 3 opções;
  indique a opção recomendada. SEMPRE confirme com o negócio pelo menos 1 definição que muda o número (ex.: visão por loja ou
  consolidada da plataforma, janela, como contar um comprador em várias categorias), mesmo que o contrato tenha um padrão —
  nesse caso, recomende o padrão do contrato.
- Sugira objetos seguindo a convenção (s_* tabela silver, g_* metric view gold) e um slug curto do produto (snake_case).
Seja conciso: frases curtas em cada campo. Responda só com um bloco ```json:
{"produto": str, "titulo": str, "objetivo": str, "grao": str, "regras": [str],
 "medidas": [{"nome": str, "definicao": str}], "dimensoes": [str],
 "objetos_sugeridos": [{"nome": str, "tipo": "tabela|metric view", "descricao": str}],
 "perguntas": [{"id": "p1", "pergunta": str, "opcoes": [str], "recomendada": str}]}
"recomendada" deve ser exatamente o texto de uma das opções."""
    txt = rodar_agente(run_id, "analyst", system,
                       f"Pedido: {pergunta}\n\nAchados do Discovery:\n{json.dumps(descoberta, ensure_ascii=False, indent=1)}",
                       tools=None, max_tokens=8000)
    return extrair_json(txt) or {"produto": "produto_dados", "titulo": pergunta, "perguntas": [], "texto": txt}


MV_GUIA = """Guia rápido de metric view (YAML 1.1):
CREATE OR REPLACE VIEW fc_catalog.agentic_teams_sandbox.g_exemplo
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: "descrição"
  source: |
    SELECT ... FROM fc_catalog.agentic_teams_sandbox.s_alguma_tabela ...   # pode ser uma query SQL
  joins:
    - name: dim_loja
      source: fc_catalog.ecommerce.s_lojas
      'on': source.loja_id = dim_loja.loja_id      # a chave 'on' SEMPRE entre aspas simples
  dimensions:
    - name: Segmento
      expr: dim_loja.segmento
  measures:
    - name: Compradores Ativos
      expr: COUNT(DISTINCT source.chave)
    - name: Compradores Recorrentes
      expr: COUNT(DISTINCT source.chave) FILTER (WHERE source.n >= 2)
    - name: Taxa
      expr: "MEASURE(`Compradores Recorrentes`) * 1.0 / MEASURE(`Compradores Ativos`)"   # aspas duplas + crases
$$
Consulta: SELECT `Segmento`, MEASURE(`Taxa`) FROM <view> GROUP BY ALL.
Cuidados: expr com ':' ou começando com crase vai entre aspas duplas; alias de join com prefixo dim_; joins só muitos-para-um;
métricas de recorrência exigem agregar em dois níveis (primeiro por comprador, depois contar) — materialize o primeiro nível
numa tabela s_* ou faça no source da metric view; janelas relativas a hoje usam current_date()."""


def engineer(run_id, pergunta, espec, feedback=None, iteracao=1, descoberta=None):
    system = _ctx() + f"""

Você é o Engineer Agent. Construa no sandbox ({C.FQ_SANDBOX}) o produto de dados especificado, pronto para virar PR.
- Você já recebe os achados do Discovery (fontes, colunas e regras): NÃO refaça a descoberta. Faça no máximo 6 consultas de
  exploração antes do primeiro criar_no_sandbox; crie cedo e itere em cima do que criou.
- Use criar_no_sandbox para cada objeto (um CREATE OR REPLACE por chamada). Tabelas s_* em 01_silver.sql; metric views g_* em 02_gold.sql.
  Um produto típico: 1 ou 2 tabelas s_* (ex.: resolução de identidade e fato no grão certo) + 1 metric view g_*.
- Só diga que um objeto foi criado se criar_no_sandbox respondeu OK. Se der erro, leia a mensagem, corrija e tente de novo.
- Leia apenas tabelas s_* de {C.FQ_DADOS} (e o que você mesmo criou no sandbox).
- Siga a especificação e o contrato de dados; não exponha dados pessoais (use sha2 do valor normalizado como chave).
- Antes de terminar, valide com consultar_sql (contagens, unicidade e a resposta da pergunta original via MEASURE()).
- Se receber feedback do Quality Agent ou do revisor humano, corrija exatamente o apontado.
{MV_GUIA}
Termine com um parágrafo curto e um bloco ```json:
{{"objetos": [{{"nome": str, "arquivo": str, "descricao": str}}], "decisoes": [str], "consulta_exemplo": str, "resumo": str}}"""
    tarefa = (f"Pergunta original do negócio: {pergunta}\n\nEspecificação aprovada:\n{json.dumps(espec, ensure_ascii=False, indent=1)}"
              f"\n\nAchados do Discovery:\n{json.dumps(descoberta or {}, ensure_ascii=False, indent=1)}")
    estado = (db.get_run(run_id) or {}).get("estado") or {}
    if estado.get("arquivos"):
        tarefa += "\n\nObjetos que você já criou no sandbox (SQL atual):\n" + "\n".join(estado["arquivos"].values())
    if feedback:
        tarefa += f"\n\nIteração {iteracao}. CORRIJA conforme o feedback abaixo:\n{feedback}"
    ts = tools_engineer(run_id)
    txt = rodar_agente(run_id, "engineer", system, tarefa, ts, max_turnos=30, max_tokens=8000)
    return extrair_json(txt) or {"resumo": txt}


def quality(run_id, pergunta, espec, entrega, arquivos, iteracao):
    system = _ctx() + """

Você é o Quality Agent: revisor INDEPENDENTE. Você não vê o raciocínio do Engineer — só a especificação, o SQL e os objetos.
Escreva e rode testes com consultar_sql e registre CADA teste com registrar_teste (aparece ao vivo para o time).
Testes mínimos:
1. Unicidade do grão das tabelas criadas.
2. Identidade: cadastros da MESMA pessoa na MESMA loja (mesmo CPF só com dígitos, ou mesmo e-mail com trim+lower)
   precisam cair no mesmo comprador unificado. Procure contraexemplos nos dados de s_compradores.
3. Pedidos de teste excluídos (regras do contrato de dados).
4. Só pedidos pagos (regras do contrato de dados: pagamento aprovado, status, chargeback perdido).
5. Nenhum dado pessoal (cpf, email, nome, telefone) exposto nas colunas da metric view ou tabelas de saída.
6. Sanidade: taxas entre 0 e 1, contagens > 0 e a metric view responde à pergunta original com MEASURE().
Seja rigoroso: reprove se um teste crítico falhar, com feedback acionável para o Engineer. No máximo 16 ferramentas.
Termine com um bloco ```json:
{"aprovado": bool, "testes": [{"teste": str, "status": "passou|falhou", "evidencia": str}], "feedback": str,
 "resultado_pergunta": str}
resultado_pergunta = tabela curta em markdown com a resposta da pergunta original (rode a consulta na metric view)."""
    sql_txt = "\n\n".join(f"-- arquivo {k}\n{v}" for k, v in arquivos.items())
    tarefa = (f"Pergunta original: {pergunta}\n\nEspecificação:\n{json.dumps(espec, ensure_ascii=False, indent=1)}\n\n"
              f"Objetos entregues: {json.dumps(entrega.get('objetos', []), ensure_ascii=False)}\n\nSQL entregue:\n{sql_txt}")
    txt = rodar_agente(run_id, "quality", system, tarefa, tools_quality(run_id, iteracao), max_turnos=20, max_tokens=5000)
    return extrair_json(txt) or {"aprovado": False, "feedback": txt, "testes": []}


def supervisor_final(run_id, pergunta, resposta_genie, construido=""):
    from llm import chat
    msg, a, b = chat([
        {"role": "system", "content": _ctx() + "\n\nVocê é o Supervisor. Escreva para a pessoa de negócio, em até 6 linhas."},
        {"role": "user", "content": f"Pergunta: {pergunta}\nO que o time construiu e publicou: {construido}\n"
         f"Resposta do Genie agora: {resposta_genie}\n\n"
         "Resuma a resposta (com os números do Genie) e o que o time construiu. Destaque o principal insight dos números. "
         "Se o Genie não trouxe números, diga isso claramente."}], max_tokens=3000)
    db.somar_tokens(run_id, a, b)
    db.evento(run_id, "supervisor", "resumo", "Resumo para o negócio", None, tokens_entrada=a, tokens_saida=b)
    return msg.content
