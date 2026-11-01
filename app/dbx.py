"""Acesso à plataforma: SQL warehouse, Genie, jobs e linhagem (identidade do app)."""
import json
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementState

import config as C

w = WorkspaceClient()


def sql(statement: str, max_linhas: int = 200, timeout_s: int = 600) -> dict:
    """Executa SQL no warehouse do app. Retorna {colunas, linhas, total} ou levanta erro com a mensagem do SQL."""
    r = w.statement_execution.execute_statement(
        warehouse_id=C.WAREHOUSE_ID, statement=statement, wait_timeout="30s",
        disposition=Disposition.INLINE, format=Format.JSON_ARRAY, row_limit=max_linhas)
    inicio = time.time()
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() - inicio > timeout_s:
            w.statement_execution.cancel_execution(r.statement_id)
            raise RuntimeError(f"SQL excedeu {timeout_s}s")
        time.sleep(1.5)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        msg = r.status.error.message if r.status.error else str(r.status.state)
        raise RuntimeError(msg)
    cols = [c.name for c in (r.manifest.schema.columns or [])] if r.manifest and r.manifest.schema else []
    linhas = (r.result.data_array or []) if r.result else []
    total = r.manifest.total_row_count if r.manifest else len(linhas)
    return {"colunas": cols, "linhas": linhas, "total": total}


def sql_texto(statement: str, max_linhas: int = 50) -> str:
    """Resultado de SQL como texto compacto (para devolver a um agente)."""
    res = sql(statement, max_linhas=max_linhas)
    if not res["colunas"]:
        return "OK (sem resultado tabular)"
    cab = " | ".join(res["colunas"])
    corpo = "\n".join(" | ".join("" if v is None else str(v) for v in l) for l in res["linhas"])
    extra = f"\n... ({res['total']} linhas no total)" if (res["total"] or 0) > len(res["linhas"]) else ""
    return f"{cab}\n{corpo}{extra}"


# ---------------------------------------------------------------- Genie

def genie_perguntar(pergunta: str, conversa_id: str | None = None, timeout_s: int = 180) -> dict:
    """Pergunta ao Genie space. Retorna {texto, sql, colunas, linhas, conversa_id, tem_dados}."""
    if conversa_id:
        msg = w.genie.create_message(space_id=C.GENIE_SPACE_ID, conversation_id=conversa_id, content=pergunta)
        conversa_id, msg_id = conversa_id, msg.message_id
    else:
        msg = w.genie.start_conversation(space_id=C.GENIE_SPACE_ID, content=pergunta)
        conversa_id, msg_id = msg.conversation_id, msg.message_id
    inicio = time.time()
    while True:
        m = w.genie.get_message(space_id=C.GENIE_SPACE_ID, conversation_id=conversa_id, message_id=msg_id)
        st = str(m.status.value if hasattr(m.status, "value") else m.status)
        if st in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
            break
        if time.time() - inicio > timeout_s:
            break
        time.sleep(2)
    texto, sql_gerado, cols, linhas = "", None, [], []
    for a in (m.attachments or []):
        if a.text and a.text.content:
            texto += a.text.content + "\n"
        if a.query:
            sql_gerado = a.query.query
            if a.query.description:
                texto += a.query.description + "\n"
            try:
                qr = w.genie.get_message_attachment_query_result(
                    space_id=C.GENIE_SPACE_ID, conversation_id=conversa_id, message_id=msg_id,
                    attachment_id=a.attachment_id)
                sr = qr.statement_response
                cols = [c.name for c in sr.manifest.schema.columns]
                linhas = (sr.result.data_array or [])[:100]
            except Exception:  # noqa: BLE001
                pass
    return {"texto": texto.strip(), "sql": sql_gerado, "colunas": cols, "linhas": linhas,
            "conversa_id": conversa_id, "tem_dados": bool(sql_gerado and linhas), "status": st}


# ---------------------------------------------------------------- jobs e linhagem

def rodar_job(job_id: int, params: dict, timeout_s: int = 1800) -> dict:
    run = w.jobs.run_now(job_id=job_id, job_parameters=params)
    inicio = time.time()
    while True:
        r = w.jobs.get_run(run.run_id)
        lc = r.state.life_cycle_state.value if r.state.life_cycle_state else ""
        if lc in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            return {"run_id": run.run_id, "resultado": r.state.result_state.value if r.state.result_state else lc,
                    "mensagem": r.state.state_message, "url": r.run_page_url}
        if time.time() - inicio > timeout_s:
            return {"run_id": run.run_id, "resultado": "TIMEOUT", "url": r.run_page_url}
        time.sleep(5)


def linhagem(tabela: str) -> str:
    """Upstream/downstream de uma tabela pela API de linhagem do Unity Catalog."""
    try:
        r = w.api_client.do("GET", "/api/2.0/lineage-tracking/table-lineage",
                            query={"table_name": tabela, "include_entity_lineage": "false"})
    except Exception as e:  # noqa: BLE001
        return f"linhagem indisponível: {e}"
    def nomes(lst):
        out = []
        for x in lst or []:
            t = x.get("tableInfo") or {}
            if t.get("name"):
                out.append(f"{t.get('catalog_name')}.{t.get('schema_name')}.{t.get('name')}")
        return sorted(set(out))
    return json.dumps({"upstream": nomes(r.get("upstreams")), "downstream": nomes(r.get("downstreams"))}, ensure_ascii=False)
