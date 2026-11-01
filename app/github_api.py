"""GitHub REST: branch, commit de arquivos, PR, review, merge e status. Repositório configurável (PR_REPO)."""
import base64

import requests

import config as C

_API = "https://api.github.com"


def _h(token=None):
    t = token or C.GITHUB_TOKEN
    if not t:
        raise RuntimeError("GITHUB_TOKEN não configurado (secret do app). Ver README.")
    return {"Authorization": f"Bearer {t}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _req(metodo, caminho, token=None, **kw):
    r = requests.request(metodo, f"{_API}/repos/{C.PR_REPO}{caminho}", headers=_h(token), timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub {metodo} {caminho}: {r.status_code} {r.text[:300]}")
    return r.json() if r.text else {}


def configurado() -> bool:
    # o secret nasce com um valor provisório; token real do GitHub tem bem mais que 20 caracteres
    return bool(C.GITHUB_TOKEN) and len(C.GITHUB_TOKEN) > 20 and not C.GITHUB_TOKEN.startswith("nao_configurado")


def status() -> dict:
    """Diagnóstico: o token enxerga o repositório de PR e pode escrever?"""
    if not configurado():
        return {"configurado": False}
    r = requests.get(f"{_API}/repos/{C.PR_REPO}", headers=_h(), timeout=30)
    if r.status_code >= 400:
        return {"configurado": True, "ok": False, "erro": f"{r.status_code} {r.text[:200]}"}
    j = r.json()
    return {"configurado": True, "ok": True, "repo": j["full_name"], "branch_padrao": j["default_branch"],
            "pode_escrever": (j.get("permissions") or {}).get("push")}


def criar_branch(nome: str) -> str:
    base = _req("GET", f"/git/ref/heads/{C.PR_BRANCH_BASE}")["object"]["sha"]
    try:
        _req("POST", "/git/refs", json={"ref": f"refs/heads/{nome}", "sha": base})
    except RuntimeError as e:
        if "Reference already exists" not in str(e):
            raise
    return nome


def gravar_arquivo(branch: str, caminho: str, conteudo: str, mensagem: str):
    sha = None
    try:
        sha = _req("GET", f"/contents/{caminho}", params={"ref": branch}).get("sha")
    except RuntimeError:
        pass
    corpo = {"message": mensagem, "branch": branch, "content": base64.b64encode(conteudo.encode()).decode()}
    if sha:
        corpo["sha"] = sha
    _req("PUT", f"/contents/{caminho}", json=corpo)


def abrir_pr(branch: str, titulo: str, corpo: str) -> dict:
    existentes = _req("GET", "/pulls", params={"head": f"{C.PR_REPO.split('/')[0]}:{branch}", "state": "open"})
    if existentes:
        return existentes[0]
    return _req("POST", "/pulls", json={"title": titulo, "head": branch, "base": C.PR_BRANCH_BASE, "body": corpo})


def comentar(numero: int, texto: str, token=None):
    _req("POST", f"/issues/{numero}/comments", token=token, json={"body": texto})


def pr(numero: int) -> dict:
    return _req("GET", f"/pulls/{numero}")


def arquivos_pr(numero: int) -> list[dict]:
    return [{"arquivo": f["filename"], "status": f["status"], "patch": f.get("patch", "")}
            for f in _req("GET", f"/pulls/{numero}/files")]


def aprovar_e_mergear(numero: int, comentario: str, token=None) -> dict:
    # no modo app_token o autor do PR e o aprovador são a mesma identidade: o GitHub não aceita review APPROVE,
    # então registra um comentário de aprovação e faz o merge (sem proteção de branch). Com o GitHub App + OAuth,
    # o token é do engenheiro e o review APPROVE vale para a proteção de branch.
    if C.GITHUB_APPROVAL_MODE == "github_user" and token:
        _req("POST", f"/pulls/{numero}/reviews", token=token, json={"event": "APPROVE", "body": comentario})
    else:
        comentar(numero, f"✅ **Aprovado no app agentic-teams**\n\n{comentario}", token=token)
    return _req("PUT", f"/pulls/{numero}/merge", token=token, json={"merge_method": "squash"})


def pedir_mudancas(numero: int, comentario: str, token=None):
    comentar(numero, f"🔁 **Mudanças solicitadas no app agentic-teams**\n\n{comentario}", token=token)


def fechar(numero: int, comentario: str, token=None):
    comentar(numero, f"⛔ **Rejeitado no app agentic-teams**\n\n{comentario}", token=token)
    _req("PATCH", f"/pulls/{numero}", token=token, json={"state": "closed"})
