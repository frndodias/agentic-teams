"""Orquestração do time com LangGraph (checkpoints no Lakebase) + execução em background e retomada após decisões humanas.

Fluxo: supervisor -> discovery -> analyst -> [esclarecimento humano] -> engineer <-> quality (até MAX_ITERACOES)
       -> pull request -> [revisão humana: aprovar | mudanças | rejeitar] -> promover (job) -> Genie responde.
"""
import io
import json
import os
import threading
import traceback
from typing import Any, TypedDict

import mlflow
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import agentes as A
import config as C
import db
import dbx
import github_api as gh


class Estado(TypedDict, total=False):
    run_id: str
    pergunta: str
    resposta_genie: str
    descoberta: dict
    espec: dict
    respostas: dict
    entrega: dict
    qualidade: dict
    iteracao: int
    feedback: str
    pr: dict
    decisao: str
    comentario: str
    final: str


def _arquivos(run_id) -> dict:
    return ((db.get_run(run_id) or {}).get("estado") or {}).get("arquivos", {})


# ---------------------------------------------------------------- nós

def n_supervisor(s: Estado):
    db.atualizar_run(s["run_id"], etapa="supervisor")
    plano = A.supervisor_plano(s["run_id"], s["pergunta"], s.get("resposta_genie", ""))
    db.atualizar_run(s["run_id"], plano=plano)
    db.handoff(s["run_id"], "supervisor", "discovery", "Investigar se o dado existe e quais fontes/regras se aplicam")
    return {"iteracao": 0}


def n_discovery(s: Estado):
    db.atualizar_run(s["run_id"], etapa="discovery")
    d = A.discovery(s["run_id"], s["pergunta"])
    db.handoff(s["run_id"], "discovery", "analyst", d.get("resumo", "")[:300])
    return {"descoberta": d}


def n_analyst(s: Estado):
    db.atualizar_run(s["run_id"], etapa="analyst")
    e = A.analyst(s["run_id"], s["pergunta"], s["descoberta"])
    db.atualizar_run(s["run_id"], produto=e.get("produto"))
    db.evento(s["run_id"], "analyst", "especificacao", "Especificação do produto de dados", e)
    return {"espec": e}


def n_esclarecimento(s: Estado):
    perguntas = (s.get("espec") or {}).get("perguntas") or []
    if not perguntas:
        return {"respostas": {}}
    respostas = interrupt({"tipo": "esclarecimento", "perguntas": perguntas})
    espec = dict(s["espec"])
    espec["decisoes_do_negocio"] = [
        {"pergunta": p["pergunta"], "resposta": respostas.get(p["id"], p.get("recomendada"))} for p in perguntas]
    db.evento(s["run_id"], "supervisor", "esclarecimento", "Negócio respondeu", espec["decisoes_do_negocio"])
    db.handoff(s["run_id"], "analyst", "engineer", "Especificação aprovada pelo negócio")
    return {"respostas": respostas, "espec": espec}


def n_engineer(s: Estado):
    it = (s.get("iteracao") or 0) + 1
    db.atualizar_run(s["run_id"], etapa="engineer", iteracoes=it)
    entrega = A.engineer(s["run_id"], s["pergunta"], s["espec"], s.get("feedback"), it, s.get("descoberta"))
    db.handoff(s["run_id"], "engineer", "quality", "Objetos criados no sandbox; validar")
    return {"entrega": entrega, "iteracao": it, "feedback": None}


def n_quality(s: Estado):
    db.atualizar_run(s["run_id"], etapa="quality")
    q = A.quality(s["run_id"], s["pergunta"], s["espec"], s.get("entrega") or {}, _arquivos(s["run_id"]), s["iteracao"])
    if q.get("aprovado"):
        db.handoff(s["run_id"], "quality", "supervisor", "Testes aprovados")
        return {"qualidade": q}
    if s["iteracao"] < C.MAX_ITERACOES:
        db.handoff(s["run_id"], "quality", "engineer", q.get("feedback", "")[:400])
        return {"qualidade": q, "feedback": q.get("feedback")}
    db.handoff(s["run_id"], "quality", "supervisor", "Limite de iterações: decisão fica com o humano")
    return {"qualidade": q}


def depois_quality(s: Estado):
    if (s.get("qualidade") or {}).get("aprovado") or s["iteracao"] >= C.MAX_ITERACOES:
        return "pull_request"
    return "engineer"


def _md_especificacao(s: Estado) -> str:
    e = s["espec"]
    linhas = [f"# {e.get('titulo', e.get('produto'))}", "", f"**Pergunta do negócio:** {s['pergunta']}", "",
              f"**Objetivo:** {e.get('objetivo', '')}", "", f"**Grão:** {e.get('grao', '')}", "", "## Regras"]
    linhas += [f"- {r}" for r in e.get("regras", [])]
    linhas += ["", "## Decisões do negócio"] + [f"- {d['pergunta']} → **{d['resposta']}**" for d in e.get("decisoes_do_negocio", [])]
    linhas += ["", "## Medidas"] + [f"- **{m.get('nome')}**: {m.get('definicao')}" for m in e.get("medidas", [])]
    return "\n".join(linhas) + "\n"


def _md_quality(s: Estado) -> str:
    q = s.get("qualidade") or {}
    linhas = [f"# Relatório do Quality Agent (iteração {s.get('iteracao')})", "",
              f"**Resultado:** {'✅ aprovado' if q.get('aprovado') else '⚠️ reprovado — decisão do revisor humano'}", "",
              "| Teste | Status | Evidência |", "|---|---|---|"]
    for t in q.get("testes", []):
        linhas.append(f"| {t.get('teste')} | {t.get('status')} | {str(t.get('evidencia', '')).replace('|', '/')[:300]} |")
    if q.get("resultado_pergunta"):
        linhas += ["", "## Resposta da pergunta original (sandbox)", "", q["resultado_pergunta"]]
    return "\n".join(linhas) + "\n"


def n_pull_request(s: Estado):
    run_id = s["run_id"]
    db.atualizar_run(run_id, etapa="pull_request")
    produto = (s["espec"].get("produto") or "produto_dados").strip().replace(" ", "_").lower()
    arquivos = dict(_arquivos(run_id))
    arquivos["especificacao.md"] = _md_especificacao(s)
    arquivos["relatorio_quality.md"] = _md_quality(s)
    for nome, conteudo in arquivos.items():
        if nome.endswith(".md"):
            db.registrar_artefato(run_id, "md", nome, conteudo)
    # cópia dos artefatos no volume do time (fonte da promoção quando não há GitHub)
    for nome, conteudo in arquivos.items():
        dbx.w.files.upload(f"/Volumes/{C.CATALOG}/{C.SCHEMA_AGENTES}/artefatos/{run_id}/{nome}",
                           io.BytesIO(conteudo.encode()), overwrite=True)
    pr = dict(s.get("pr") or {})
    if gh.configurado():
        branch = pr.get("branch") or gh.criar_branch(f"agent/{produto}-{run_id[:6]}")
        for nome, conteudo in arquivos.items():
            gh.gravar_arquivo(branch, f"produtos_dados/{produto}/{nome}", conteudo,
                              f"[{produto}] {nome} (iteração {s.get('iteracao')})")
        if not pr.get("numero"):
            corpo = (f"Produto de dados criado pelo **time agêntico** a partir da pergunta:\n\n> {s['pergunta']}\n\n"
                     f"{_md_especificacao(s)}\n---\n{_md_quality(s)}\n---\n_Run `{run_id}` · revisão no app agentic-teams._")
            p = gh.abrir_pr(branch, f"[agentes] {s['espec'].get('titulo', produto)}", corpo)
            pr = {"numero": p["number"], "url": p["html_url"], "branch": branch}
        else:
            gh.comentar(pr["numero"], "🔄 Nova versão enviada pelo time agêntico.\n\n" + _md_quality(s))
        db.atualizar_run(run_id, pr_url=pr["url"], pr_numero=pr["numero"], branch=branch, produto=produto)
        db.evento(run_id, "engineer", "pull_request", f"PR #{pr['numero']} aberto", pr)
    else:
        pr = {"numero": None, "url": None, "branch": None}
        db.atualizar_run(run_id, produto=produto)
        db.evento(run_id, "engineer", "pull_request", "PR simulado (GitHub não configurado): artefatos no volume",
                  {"volume": f"/Volumes/{C.CATALOG}/{C.SCHEMA_AGENTES}/artefatos/{run_id}/"})
    db.handoff(run_id, "supervisor", "humano", "Aguardando revisão do engenheiro de dados")
    return {"pr": pr}


def n_revisao(s: Estado):
    d = interrupt({"tipo": "pr", "pr": s.get("pr"), "qualidade": s.get("qualidade")})
    return {"decisao": d.get("decisao"), "comentario": d.get("comentario", "")}


def depois_revisao(s: Estado):
    return {"aprovar": "promover", "mudancas": "engineer_mudancas", "rejeitar": "rejeitar"}.get(s.get("decisao"), "rejeitar")


def n_engineer_mudancas(s: Estado):
    db.handoff(s["run_id"], "humano", "engineer", f"Mudanças solicitadas: {s.get('comentario', '')[:300]}")
    return {"feedback": f"O revisor humano pediu: {s.get('comentario', '')}", "iteracao": min(s.get("iteracao") or 0, C.MAX_ITERACOES - 1)}


def n_promover(s: Estado):
    run_id = s["run_id"]
    db.atualizar_run(run_id, etapa="promover")
    sid = db.abrir_step(run_id, "supervisor", "deploy", "Promovendo para ecommerce (job de deploy)")
    fonte = "github" if (s.get("pr") or {}).get("numero") else "volume"
    r = dbx.rodar_job(int(C.PROMOVER_JOB_ID), {"produto": s["espec"].get("produto"), "run_id": run_id, "fonte": fonte})
    db.fechar_step(sid, "ok" if r["resultado"] == "SUCCESS" else "erro", r)
    if r["resultado"] != "SUCCESS":
        raise RuntimeError(f"job de promoção falhou: {r}")
    db.status_artefatos(run_id, "promovido")
    return {}


def n_final(s: Estado):
    run_id = s["run_id"]
    db.atualizar_run(run_id, etapa="genie")
    sid = db.abrir_step(run_id, "supervisor", "genie", "Perguntando de novo ao Genie")
    g = dbx.genie_perguntar(s["pergunta"])
    db.fechar_step(sid, "ok", g)
    objs = list(((db.get_run(run_id) or {}).get("estado") or {}).get("objetos", {}))
    construido = (f"objetos {', '.join(objs)} em {C.FQ_DADOS}, aprovados pelo Quality Agent e por revisão humana, "
                  f"publicados no Genie") if objs else "nada"
    final = A.supervisor_final(run_id, s["pergunta"], json.dumps({"texto": g["texto"], "colunas": g["colunas"],
                                                                   "linhas": g["linhas"][:60]}, ensure_ascii=False), construido)
    db.evento(run_id, "supervisor", "final", "Resposta final", {"texto": final, "genie": g})
    db.atualizar_run(run_id, status="concluido", etapa="concluido", resposta_final=final, finalizado_em="now()")
    return {"final": final}


def n_rejeitar(s: Estado):
    run_id = s["run_id"]
    for nome in ((db.get_run(run_id) or {}).get("estado") or {}).get("objetos", {}):
        for tipo in ("VIEW", "TABLE"):
            try:
                dbx.sql(f"DROP {tipo} IF EXISTS {C.FQ_SANDBOX}.{nome}")
            except Exception:  # noqa: BLE001
                pass
    db.status_artefatos(run_id, "descartado")
    db.evento(run_id, "supervisor", "rejeitado", "PR rejeitado: objetos do sandbox descartados", {"comentario": s.get("comentario")})
    db.atualizar_run(run_id, status="rejeitado", etapa="rejeitado", finalizado_em="now()")
    return {}


def construir(checkpointer):
    g = StateGraph(Estado)
    for nome, fn in [("supervisor", n_supervisor), ("discovery", n_discovery), ("analyst", n_analyst),
                     ("esclarecimento", n_esclarecimento), ("engineer", n_engineer), ("quality", n_quality),
                     ("pull_request", n_pull_request), ("revisao", n_revisao), ("engineer_mudancas", n_engineer_mudancas),
                     ("promover", n_promover), ("final", n_final), ("rejeitar", n_rejeitar)]:
        g.add_node(nome, fn)
    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "discovery")
    g.add_edge("discovery", "analyst")
    g.add_edge("analyst", "esclarecimento")
    g.add_edge("esclarecimento", "engineer")
    g.add_edge("engineer", "quality")
    g.add_conditional_edges("quality", depois_quality, ["engineer", "pull_request"])
    g.add_edge("pull_request", "revisao")
    g.add_conditional_edges("revisao", depois_revisao, ["promover", "engineer_mudancas", "rejeitar"])
    g.add_edge("engineer_mudancas", "engineer")
    g.add_edge("promover", "final")
    g.add_edge("final", END)
    g.add_edge("rejeitar", END)
    return g.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------- execução

GRAFO = None


def iniciar():
    global GRAFO
    saver = PostgresSaver(db.pool)
    if not os.getenv("PREVIEW_LOCAL"):
        saver.setup()
    GRAFO = construir(saver)


def _executar(run_id: str, entrada: Any):
    cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 60}
    try:
        with mlflow.start_span(name=f"time_agentico {run_id[:8]}", span_type="CHAIN") as sp:
            sp.set_attributes({"run_id": run_id})
            GRAFO.invoke(entrada, cfg)
        st = GRAFO.get_state(cfg)
        pend = [i for t in st.tasks for i in (t.interrupts or [])]
        if pend:
            payload = pend[0].value
            db.criar_aprovacao(run_id, payload["tipo"], payload)
            status = "aguardando_esclarecimento" if payload["tipo"] == "esclarecimento" else "aguardando_revisao"
            db.atualizar_run(run_id, status=status, etapa=status)
    except Exception as e:  # noqa: BLE001
        db.evento(run_id, "supervisor", "erro", "Falha na execução", {"erro": str(e), "trace": traceback.format_exc()[-3000:]}, status="erro")
        db.atualizar_run(run_id, status="falhou", erro=str(e)[:2000])


def disparar(run_id: str, pergunta: str, resposta_genie: str):
    threading.Thread(target=_executar, args=(run_id, {"run_id": run_id, "pergunta": pergunta,
                                                      "resposta_genie": resposta_genie}), daemon=True).start()


def tentar_novamente(run_id: str):
    """Retoma do último checkpoint (refaz o nó que falhou)."""
    db.atualizar_run(run_id, status="em_andamento", erro=None)
    db.evento(run_id, "humano", "retentativa", "Tentar de novo a partir do ponto de falha")
    threading.Thread(target=_executar, args=(run_id, None), daemon=True).start()


def retomar(run_id: str, valor: dict):
    db.atualizar_run(run_id, status="em_andamento")
    threading.Thread(target=_executar, args=(run_id, Command(resume=valor)), daemon=True).start()
