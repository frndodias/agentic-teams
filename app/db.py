"""Estado operacional do time agêntico no Lakebase (Postgres): execuções, etapas, handoffs, aprovações, testes."""
import json
import os
import threading
import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

import config as C
from dbx import w

_token = {"valor": None, "expira": 0.0}
_lock = threading.Lock()


def _endpoint() -> str:
    return os.environ["LAKEBASE_ENDPOINT"]


def token_lakebase() -> str:
    with _lock:
        if not _token["valor"] or time.time() > _token["expira"]:
            _token["valor"] = w.postgres.generate_database_credential(endpoint=_endpoint()).token
            _token["expira"] = time.time() + 40 * 60  # o token vale 1h; renova antes
        return _token["valor"]


class _ConexaoComToken(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo: str = "", **kwargs):
        kwargs["password"] = token_lakebase()
        return super().connect(conninfo, **kwargs)


def _params() -> dict:
    host = os.getenv("PGHOST") or w.postgres.get_endpoint(name=_endpoint()).status.hosts.host
    user = os.getenv("PGUSER") or w.current_user.me().user_name
    return {"host": host, "port": int(os.getenv("PGPORT", "5432")), "dbname": os.getenv("PGDATABASE", "databricks_postgres"),
            "user": user, "sslmode": "require", "options": f"-c search_path={C.PG_SCHEMA},public"}


pool: ConnectionPool | None = None


def iniciar():
    global pool
    print("lakebase env:", {k: (v if k != "PGPASSWORD" else "***") for k, v in os.environ.items() if k.startswith(("PG", "LAKEBASE"))})
    params = _params()
    # cria o schema antes do pool (o search_path aponta para ele)
    if not os.getenv("PREVIEW_LOCAL"):
        with _ConexaoComToken.connect(**{k: v for k, v in params.items() if k != "options"}, autocommit=True) as c:
            c.execute(f"CREATE SCHEMA IF NOT EXISTS {C.PG_SCHEMA}")
    # check: valida a conexão antes de entregar (o Lakebase pode reiniciar / escalar a zero)
    pool = ConnectionPool(conninfo="", connection_class=_ConexaoComToken, min_size=1, max_size=8, open=True,
                          kwargs={**params, "autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                          max_lifetime=45 * 60, check=ConnectionPool.check_connection)
    if os.getenv("PREVIEW_LOCAL"):  # visualização local com usuário humano: as tabelas são do SP do app
        return
    with pool.connection() as c:
        for stmt in (x.strip() for x in DDL.split(";")):
            if stmt:
                c.execute(stmt)


DDL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, criado_em TIMESTAMPTZ DEFAULT now(), atualizado_em TIMESTAMPTZ DEFAULT now(),
  solicitante TEXT, pergunta TEXT, status TEXT, etapa TEXT, produto TEXT, plano TEXT,
  resposta_genie_inicial TEXT, resposta_final TEXT, pr_url TEXT, pr_numero INT, branch TEXT,
  iteracoes INT DEFAULT 0, tokens_entrada BIGINT DEFAULT 0, tokens_saida BIGINT DEFAULT 0,
  finalizado_em TIMESTAMPTZ, erro TEXT, estado JSONB DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS steps (
  step_id BIGSERIAL PRIMARY KEY, run_id TEXT, agente TEXT, acao TEXT, titulo TEXT, detalhe JSONB,
  status TEXT, iniciado_em TIMESTAMPTZ DEFAULT now(), finalizado_em TIMESTAMPTZ,
  tokens_entrada INT DEFAULT 0, tokens_saida INT DEFAULT 0, modelo TEXT
);
CREATE INDEX IF NOT EXISTS steps_run ON steps(run_id, step_id);
CREATE TABLE IF NOT EXISTS handoffs (
  handoff_id BIGSERIAL PRIMARY KEY, run_id TEXT, de_agente TEXT, para_agente TEXT, motivo TEXT, ts TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id BIGSERIAL PRIMARY KEY, run_id TEXT, tipo TEXT, pergunta JSONB, resposta JSONB, decisao TEXT,
  comentario TEXT, usuario TEXT, login_github TEXT, status TEXT, criado_em TIMESTAMPTZ DEFAULT now(), respondido_em TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS dq_results (
  dq_id BIGSERIAL PRIMARY KEY, run_id TEXT, iteracao INT, teste TEXT, status TEXT, evidencia TEXT, ts TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id BIGSERIAL PRIMARY KEY, run_id TEXT, tipo TEXT, nome TEXT, conteudo TEXT, status TEXT, ts TIMESTAMPTZ DEFAULT now()
);
"""


def _exec(q: str, args=(), um=False, todos=False, tentativas=3):
    for i in range(tentativas):
        try:
            with pool.connection() as c:
                cur = c.execute(q, args)
                if um:
                    return cur.fetchone()
                if todos:
                    return cur.fetchall()
                return None
        except psycopg.OperationalError:
            if i == tentativas - 1:
                raise
            time.sleep(2 * (i + 1))


def _j(x):
    return json.dumps(x, ensure_ascii=False, default=str) if x is not None else None


# ---------------------------------------------------------------- runs

def criar_run(run_id, solicitante, pergunta, resposta_genie):
    _exec("INSERT INTO runs (run_id, solicitante, pergunta, status, etapa, resposta_genie_inicial) VALUES (%s,%s,%s,'em_andamento','supervisor',%s)",
          (run_id, solicitante, pergunta, resposta_genie))


def atualizar_run(run_id, **campos):
    if not campos:
        return
    sets, vals = [], []
    for k, v in campos.items():
        if v == "now()":
            sets.append(f"{k} = now()")
            continue
        sets.append(f"{k} = %s")
        vals.append(_j(v) if k == "estado" else v)
    sets.append("atualizado_em = now()")
    _exec(f"UPDATE runs SET {', '.join(sets)} WHERE run_id = %s", (*vals, run_id))


def somar_tokens(run_id, entrada, saida):
    _exec("UPDATE runs SET tokens_entrada = tokens_entrada + %s, tokens_saida = tokens_saida + %s WHERE run_id = %s",
          (entrada, saida, run_id))


def get_run(run_id):
    return _exec("SELECT * FROM runs WHERE run_id = %s", (run_id,), um=True)


def listar_runs(limite=30):
    return _exec("SELECT run_id, criado_em, solicitante, pergunta, status, etapa, produto, pr_url, iteracoes, "
                 "tokens_entrada, tokens_saida, finalizado_em FROM runs ORDER BY criado_em DESC LIMIT %s", (limite,), todos=True)


# ---------------------------------------------------------------- etapas e eventos

def abrir_step(run_id, agente, acao, titulo, detalhe=None, status="em_andamento", modelo=None) -> int:
    r = _exec("INSERT INTO steps (run_id, agente, acao, titulo, detalhe, status, modelo) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING step_id",
              (run_id, agente, acao, titulo, _j(detalhe), status, modelo), um=True)
    return r["step_id"]


def fechar_step(step_id, status="ok", detalhe=None, tokens_entrada=0, tokens_saida=0):
    _exec("UPDATE steps SET status=%s, detalhe=COALESCE(%s::jsonb, detalhe), finalizado_em=now(), "
          "tokens_entrada=tokens_entrada+%s, tokens_saida=tokens_saida+%s WHERE step_id=%s",
          (status, _j(detalhe), tokens_entrada, tokens_saida, step_id))


def evento(run_id, agente, acao, titulo, detalhe=None, status="ok", tokens_entrada=0, tokens_saida=0):
    sid = abrir_step(run_id, agente, acao, titulo, detalhe, status=status)
    _exec("UPDATE steps SET finalizado_em = now(), tokens_entrada = %s, tokens_saida = %s WHERE step_id = %s",
          (tokens_entrada, tokens_saida, sid))
    return sid


def handoff(run_id, de, para, motivo):
    _exec("INSERT INTO handoffs (run_id, de_agente, para_agente, motivo) VALUES (%s,%s,%s,%s)", (run_id, de, para, motivo))
    evento(run_id, de, "handoff", f"{de} → {para}", {"motivo": motivo})


def criar_aprovacao(run_id, tipo, pergunta) -> int:
    r = _exec("INSERT INTO approvals (run_id, tipo, pergunta, status) VALUES (%s,%s,%s,'pendente') RETURNING approval_id",
              (run_id, tipo, _j(pergunta)), um=True)
    return r["approval_id"]


def responder_aprovacao(approval_id, resposta, decisao, usuario, comentario=None, login_github=None):
    _exec("UPDATE approvals SET resposta=%s, decisao=%s, usuario=%s, comentario=%s, login_github=%s, status='respondida', "
          "respondido_em=now() WHERE approval_id=%s", (_j(resposta), decisao, usuario, comentario, login_github, approval_id))


def aprovacao_pendente(run_id, tipo=None):
    q = "SELECT * FROM approvals WHERE run_id=%s AND status='pendente'"
    args = [run_id]
    if tipo:
        q += " AND tipo=%s"
        args.append(tipo)
    return _exec(q + " ORDER BY approval_id DESC LIMIT 1", tuple(args), um=True)


def registrar_dq(run_id, iteracao, teste, status, evidencia):
    _exec("INSERT INTO dq_results (run_id, iteracao, teste, status, evidencia) VALUES (%s,%s,%s,%s,%s)",
          (run_id, iteracao, teste, status, evidencia))


def registrar_artefato(run_id, tipo, nome, conteudo, status="sandbox"):
    _exec("DELETE FROM artifacts WHERE run_id=%s AND nome=%s", (run_id, nome))
    _exec("INSERT INTO artifacts (run_id, tipo, nome, conteudo, status) VALUES (%s,%s,%s,%s,%s)", (run_id, tipo, nome, conteudo, status))


def status_artefatos(run_id, status):
    _exec("UPDATE artifacts SET status=%s WHERE run_id=%s", (status, run_id))


def detalhe_run(run_id):
    return {
        "run": get_run(run_id),
        "steps": _exec("SELECT * FROM steps WHERE run_id=%s ORDER BY step_id", (run_id,), todos=True),
        "aprovacoes": _exec("SELECT * FROM approvals WHERE run_id=%s ORDER BY approval_id", (run_id,), todos=True),
        "dq": _exec("SELECT * FROM dq_results WHERE run_id=%s ORDER BY dq_id", (run_id,), todos=True),
        "artefatos": _exec("SELECT * FROM artifacts WHERE run_id=%s ORDER BY artifact_id", (run_id,), todos=True),
    }


def operacao():
    """Indicadores da área Operação."""
    return {
        "resumo": _exec("""SELECT count(*) execucoes, count(*) FILTER (WHERE status='concluido') concluidas,
                             count(*) FILTER (WHERE pr_url IS NOT NULL) prs, round(avg(iteracoes)::numeric, 2) iteracoes_media,
                             round(avg(EXTRACT(EPOCH FROM (finalizado_em - criado_em))/60)::numeric, 1) minutos_medio,
                             sum(tokens_entrada) tokens_entrada, sum(tokens_saida) tokens_saida FROM runs""", um=True),
        "por_agente": _exec("""SELECT agente, count(*) FILTER (WHERE acao='llm') chamadas_llm, count(*) FILTER (WHERE acao='tool') tools,
                                 sum(tokens_entrada) tokens_entrada, sum(tokens_saida) tokens_saida,
                                 round(avg(EXTRACT(EPOCH FROM (finalizado_em - iniciado_em))) FILTER (WHERE acao='agente')::numeric, 1) seg_medio
                               FROM steps GROUP BY agente ORDER BY agente""", todos=True),
        "aprovacoes": _exec("SELECT tipo, decisao, count(*) n FROM approvals WHERE status='respondida' GROUP BY 1,2 ORDER BY 1,2", todos=True),
        "dq": _exec("SELECT status, count(*) n FROM dq_results GROUP BY 1", todos=True),
    }


def limpar_tudo():
    """Reset da demo: esvazia o estado operacional e apaga as tabelas do LangGraph (recriadas em seguida pelo setup)."""
    proprias = ["runs", "steps", "handoffs", "approvals", "dq_results", "artifacts"]
    langgraph = ["checkpoint_writes", "checkpoint_blobs", "checkpoints", "checkpoint_migrations"]
    with pool.connection() as c:
        c.execute("TRUNCATE " + ", ".join(f"{C.PG_SCHEMA}.{t}" for t in proprias) + " RESTART IDENTITY")
        for t in langgraph:
            c.execute(f"DROP TABLE IF EXISTS {C.PG_SCHEMA}.{t}")
    return proprias + langgraph
