"""LLM via Unity Gateway (API compatível com OpenAI) + loop de ferramentas dos agentes."""
import json
import re

import mlflow
from openai import OpenAI

import config as C
import db
from dbx import w

_BASE = f"{w.config.host.rstrip('/')}/ai-gateway/mlflow/v1"


def _cliente() -> OpenAI:
    # o token OAuth do app expira: pega um fresco a cada chamada (o SDK cuida do cache/refresh)
    auth = w.config.authenticate()
    token = auth["Authorization"].split(" ", 1)[1]
    return OpenAI(api_key=token, base_url=_BASE, timeout=180, max_retries=2)


def chat(messages, tools=None, max_tokens=4000):
    # sem temperature: os modelos Claude 5.x não aceitam o parâmetro
    kw = {"model": C.LLM_MODEL, "messages": messages, "max_tokens": max_tokens}
    if tools:
        kw["tools"] = tools
    r = _cliente().chat.completions.create(**kw)
    u = r.usage
    msg = r.choices[0].message
    msg.content = texto(msg.content)
    return msg, (getattr(u, "prompt_tokens", 0) or 0), (getattr(u, "completion_tokens", 0) or 0)


def texto(conteudo) -> str:
    """O gateway pode devolver o conteúdo como lista de blocos (texto/raciocínio): fica só o texto."""
    if conteudo is None or isinstance(conteudo, str):
        return conteudo or ""
    if isinstance(conteudo, list):
        partes = []
        for b in conteudo:
            if isinstance(b, dict):
                if b.get("type") in (None, "text", "output_text"):
                    partes.append(b.get("text") or b.get("content") or "")
            else:
                partes.append(getattr(b, "text", "") or "")
        return "\n".join(p for p in partes if p)
    return str(conteudo)


def _schema_tool(nome, descricao, params: dict, obrigatorios=None):
    return {"type": "function", "function": {
        "name": nome, "description": descricao,
        "parameters": {"type": "object", "properties": params, "required": obrigatorios or list(params)}}}


class Tool:
    def __init__(self, nome, descricao, params, fn=None, obrigatorios=None):
        self.nome, self.fn = nome, fn
        self.schema = _schema_tool(nome, descricao, params, obrigatorios)


def extrair_json(texto: str):
    """Último bloco ```json``` da resposta; se não houver, o maior trecho entre { e } que seja JSON válido."""
    texto = texto or ""
    candidatos = re.findall(r"```(?:json)?\s*\n(.*?)\n?```", texto, flags=re.S)[::-1]
    if "{" in texto:
        candidatos.append(texto[texto.find("{"): texto.rfind("}") + 1])
    for c in candidatos:
        c = c.strip()
        if not c.startswith("{"):
            continue
        try:
            return json.loads(c)
        except Exception:  # noqa: BLE001
            continue
    return None


def rodar_agente(run_id: str, agente: str, system: str, usuario: str, tools: list[Tool] | None = None,
                 max_turnos: int = 14, max_tokens: int = 4000) -> str:
    """Loop ReAct simples: o modelo chama ferramentas até responder sem tool_calls."""
    tools = tools or []
    por_nome = {t.nome: t for t in tools}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": usuario}]
    sid_agente = db.abrir_step(run_id, agente, "agente", f"{agente} trabalhando", modelo=C.LLM_MODEL)
    tin = tout = 0
    with mlflow.start_span(name=agente, span_type="AGENT") as span_ag:
        span_ag.set_inputs({"tarefa": usuario[:4000]})
        for turno in range(max_turnos):
            ultima = turno == max_turnos - 1
            with mlflow.start_span(name=f"{agente}.llm", span_type="CHAT_MODEL") as sp:
                msg, a, b = chat(messages, tools=None if ultima else [t.schema for t in tools] or None, max_tokens=max_tokens)
                sp.set_attributes({"tokens_entrada": a, "tokens_saida": b, "modelo": C.LLM_MODEL})
            tin, tout = tin + a, tout + b
            db.somar_tokens(run_id, a, b)
            db.evento(run_id, agente, "llm", "pensando" if msg.tool_calls else "resposta",
                      {"texto": (msg.content or "")[:3000], "tokens_entrada": a, "tokens_saida": b})
            if not msg.tool_calls:
                db.fechar_step(sid_agente, "ok", {"resposta": (msg.content or "")[:6000]}, tin, tout)
                span_ag.set_outputs({"resposta": (msg.content or "")[:4000]})
                return msg.content or ""
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                nome = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:  # noqa: BLE001
                    args = {}
                sid = db.abrir_step(run_id, agente, "tool", nome, {"args": args})
                with mlflow.start_span(name=f"{agente}.{nome}", span_type="TOOL") as sp:
                    sp.set_inputs(args)
                    try:
                        if nome not in por_nome:
                            raise ValueError(f"ferramenta desconhecida: {nome}")
                        saida = str(por_nome[nome].fn(**args))
                        ok = True
                    except Exception as e:  # noqa: BLE001
                        saida, ok = f"ERRO: {e}", False
                    sp.set_outputs({"saida": saida[:4000]})
                saida = saida if len(saida) <= 8000 else saida[:8000] + "\n...(truncado)"
                db.fechar_step(sid, "ok" if ok else "erro", {"args": args, "saida": saida[:4000]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": saida})
    db.fechar_step(sid_agente, "erro", {"resposta": "limite de turnos"}, tin, tout)
    return ""
