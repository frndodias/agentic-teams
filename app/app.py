"""App agentic-teams: Conversa (negócio + Genie), Time ao vivo, Revisão (engenheiro) e Operação."""
import threading
import time
import uuid

import mlflow
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config as C
import db
import dbx
import github_api as gh
import grafo

app = FastAPI(title="agentic-teams")


@app.on_event("startup")
def _startup():
    mlflow.set_tracking_uri("databricks")
    if C.MLFLOW_EXPERIMENT:
        mlflow.set_experiment(experiment_id=C.MLFLOW_EXPERIMENT)
    db.iniciar()
    grafo.iniciar()
    threading.Thread(target=_vigiar_prs, daemon=True).start()


def _usuario(req: Request) -> str:
    return (req.headers.get("x-forwarded-email") or req.headers.get("x-forwarded-preferred-username") or "local").lower()


def _revisor(req: Request) -> str:
    u = _usuario(req)
    if C.REVISORES and u not in C.REVISORES:
        raise HTTPException(403, "Área de revisão restrita ao time de engenharia de dados")
    return u


# ---------------------------------------------------------------- conversa

class Pergunta(BaseModel):
    pergunta: str
    conversa_id: str | None = None
    acionar_time: bool = True


@app.post("/api/perguntar")
def perguntar(p: Pergunta, req: Request):
    g = dbx.genie_perguntar(p.pergunta, p.conversa_id)
    out = {"genie": g, "run_id": None}
    if not g["tem_dados"] and p.acionar_time:
        run_id = uuid.uuid4().hex[:12]
        db.criar_run(run_id, _usuario(req), p.pergunta, g["texto"])
        db.evento(run_id, "genie", "lacuna", "Genie não encontrou o dado", {"texto": g["texto"]})
        grafo.disparar(run_id, p.pergunta, g["texto"])
        out["run_id"] = run_id
    return out


# ---------------------------------------------------------------- runs

@app.get("/api/runs")
def runs():
    return db.listar_runs()


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    d = db.detalhe_run(run_id)
    if not d["run"]:
        raise HTTPException(404)
    return d


class Respostas(BaseModel):
    respostas: dict


@app.post("/api/runs/{run_id}/esclarecimento")
def esclarecimento(run_id: str, r: Respostas, req: Request):
    ap = db.aprovacao_pendente(run_id, "esclarecimento")
    if not ap:
        raise HTTPException(409, "não há esclarecimento pendente")
    db.responder_aprovacao(ap["approval_id"], r.respostas, "respondido", _usuario(req))
    grafo.retomar(run_id, r.respostas)
    return {"ok": True}


class Revisao(BaseModel):
    decisao: str  # aprovar | mudancas | rejeitar
    comentario: str = ""


@app.get("/api/runs/{run_id}/pr")
def pr_detalhe(run_id: str):
    r = db.get_run(run_id)
    if not r or not r.get("pr_numero") or not gh.configurado():
        return {"arquivos": [], "pr": None}
    p = gh.pr(r["pr_numero"])
    return {"pr": {"numero": p["number"], "url": p["html_url"], "estado": p["state"], "merged": p.get("merged"),
                   "autor": p["user"]["login"], "titulo": p["title"]}, "arquivos": gh.arquivos_pr(r["pr_numero"])}


@app.post("/api/runs/{run_id}/revisao")
def revisao(run_id: str, rv: Revisao, req: Request):
    usuario = _revisor(req)
    ap = db.aprovacao_pendente(run_id, "pr")
    if not ap:
        raise HTTPException(409, "não há revisão pendente")
    r = db.get_run(run_id)
    numero = r.get("pr_numero")
    comentario = (rv.comentario or "").strip() or {"aprovar": "Aprovado.", "rejeitar": "Rejeitado."}.get(rv.decisao, "")
    assinatura = f"\n\n— {usuario} (via app agentic-teams)"
    if numero and gh.configurado():
        if rv.decisao == "aprovar":
            gh.aprovar_e_mergear(numero, comentario + assinatura)
        elif rv.decisao == "mudancas":
            gh.pedir_mudancas(numero, comentario + assinatura)
        else:
            gh.fechar(numero, comentario + assinatura)
    db.responder_aprovacao(ap["approval_id"], {"decisao": rv.decisao}, rv.decisao, usuario, comentario)
    db.evento(run_id, "humano", "revisao", f"Revisão: {rv.decisao}", {"usuario": usuario, "comentario": comentario})
    grafo.retomar(run_id, {"decisao": rv.decisao, "comentario": comentario})
    return {"ok": True}


@app.post("/api/runs/{run_id}/tentar-novamente")
def tentar_novamente(run_id: str):
    r = db.get_run(run_id)
    if not r or r["status"] != "falhou":
        raise HTTPException(409, "só execuções com falha podem ser retomadas")
    grafo.tentar_novamente(run_id)
    return {"ok": True}


def _vigiar_prs():
    """Merge/fechamento feito direto no GitHub também retoma o fluxo."""
    while True:
        time.sleep(20)
        if not gh.configurado():
            continue
        try:
            for r in db.listar_runs(50):
                if r["status"] != "aguardando_revisao":
                    continue
                full = db.get_run(r["run_id"])
                if not full.get("pr_numero"):
                    continue
                p = gh.pr(full["pr_numero"])
                if p.get("merged") or p["state"] == "closed":
                    ap = db.aprovacao_pendente(r["run_id"], "pr")
                    if not ap:
                        continue
                    dec = "aprovar" if p.get("merged") else "rejeitar"
                    db.responder_aprovacao(ap["approval_id"], {"decisao": dec}, dec, p.get("merged_by", {}).get("login") or "github",
                                           "Decisão tomada direto no GitHub", (p.get("merged_by") or {}).get("login"))
                    db.evento(r["run_id"], "humano", "revisao", f"Revisão no GitHub: {dec}", {"pr": p["html_url"]})
                    grafo.retomar(r["run_id"], {"decisao": dec, "comentario": "Decisão tomada direto no GitHub"})
        except Exception as e:  # noqa: BLE001
            print("vigia de PRs:", e)


@app.post("/api/admin/reset")
def reset(req: Request):
    """Usado pelo scripts/reset_demo.py: limpa execuções, aprovações e checkpoints (estado limpo da demo)."""
    _revisor(req)
    tabelas = db.limpar_tudo()
    grafo.iniciar()  # recria as tabelas de checkpoint do LangGraph
    return {"tabelas_limpas": tabelas}


# ---------------------------------------------------------------- operação e config

@app.get("/api/github/status")
def github_status():
    return gh.status()


@app.get("/api/operacao")
def operacao():
    return db.operacao()


@app.get("/api/config")
def config(req: Request):
    host = dbx.w.config.host.rstrip("/")
    return {"usuario": _usuario(req), "github": gh.configurado(), "pr_repo": C.PR_REPO,
            "genie_url": f"{host}/genie/rooms/{C.GENIE_SPACE_ID}" if C.GENIE_SPACE_ID else None,
            "experimento_url": f"{host}/ml/experiments/{C.MLFLOW_EXPERIMENT}" if C.MLFLOW_EXPERIMENT else None,
            "modelo": C.LLM_MODEL, "revisor": (not C.REVISORES) or _usuario(req) in C.REVISORES,
            "modo_aprovacao": C.GITHUB_APPROVAL_MODE}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
