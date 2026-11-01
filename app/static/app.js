// Agentic Data Team — front-end (sem build): Conversa, Time ao vivo, Revisão e Operação.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const md = (s) => (window.marked ? marked.parse(String(s ?? "")) : `<pre>${esc(s)}</pre>`);
const api = async (url, opts = {}) => {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
};
const svg = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICONE = {
  supervisor: svg('<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>'),
  discovery: svg('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>'),
  analyst: svg('<path d="M4 20h16M6 16l4-6 3 3 5-7"/>'),
  negocio: svg('<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/><path d="M17.5 4.5l1.5-1.5M19.5 7H21"/>'),
  engineer: svg('<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>'),
  quality: svg('<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6A2 2 0 0 0 19 18l-5-9V3"/><path d="M7.5 15h9"/>'),
  engenheiro: svg('<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M6 8.5v7M18 15.5V10a3 3 0 0 0-3-3h-4"/>'),
};
// ordem do fluxo (os humanos aparecem onde o time pausa); nomes sempre visíveis junto da cor
const FLUXO = [["supervisor", "Supervisor", "planeja e coordena"], ["discovery", "Discovery", "descobre fontes e regras"],
  ["analyst", "Analyst", "especifica"], ["negocio", "Negócio", "decide as definições"], ["engineer", "Engineer", "constrói no sandbox"],
  ["quality", "Quality", "testa de forma independente"], ["engenheiro", "Engenheiro", "revisa e aprova o PR"]];
const NOME_AGENTE = Object.fromEntries(FLUXO.map(([k, n]) => [k, n]));
NOME_AGENTE.humano = "Humano"; NOME_AGENTE.genie = "Genie";
const ETAPA_NO = { supervisor: "supervisor", discovery: "discovery", analyst: "analyst", engineer: "engineer", quality: "quality",
  pull_request: "engineer", aguardando_esclarecimento: "negocio", aguardando_revisao: "engenheiro", promover: "supervisor", genie: "supervisor" };
let CFG = {}, runAtual = null, conversaId = null;
const acompanhados = new Set();

// ---------------------------------------------------------------- menu lateral
if (localStorage.getItem("menu_recolhido") === "1") document.body.classList.add("recolhido");
$("#recolher").onclick = () => {
  document.body.classList.toggle("recolhido");
  localStorage.setItem("menu_recolhido", document.body.classList.contains("recolhido") ? "1" : "0");
};

// ---------------------------------------------------------------- abas
document.querySelectorAll("nav button").forEach((b) => b.onclick = () => abrirAba(b.dataset.aba));
const TITULOS = {
  conversa: ["Conversa", "Pergunte ao Genie; se o dado não existir, o time de dados constrói."],
  time: ["Time ao vivo", "Supervisor, Discovery, Analyst, Engineer e Quality trabalhando — com pausas para decisões humanas."],
  revisao: ["Revisão", "O engenheiro de dados revisa o PR, os testes e as decisões antes de publicar."],
  operacao: ["Operação", "Custo, tempo, retrabalho e decisões humanas do time agêntico."],
};
function abrirAba(nome) {
  $("#titulo-aba").textContent = TITULOS[nome][0];
  $("#subtitulo-aba").textContent = TITULOS[nome][1];
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("ativa", x.dataset.aba === nome));
  document.querySelectorAll(".aba").forEach((x) => x.classList.toggle("ativa", x.id === `aba-${nome}`));
  const carregar = { revisao: carregarRevisao, operacao: carregarOperacao, time: carregarRuns }[nome];
  if (carregar) comCarga(nome, carregar);
}

// mostra "carregando…" e, se falhar, uma mensagem de erro em vez de tela vazia
async function comCarga(nome, fn) {
  const sec = $(`#aba-${nome}`);
  sec.querySelectorAll(".erro-carga").forEach((e) => e.remove());
  let aviso = null;
  const t = setTimeout(() => { aviso = document.createElement("div"); aviso.className = "carregando"; aviso.textContent = "carregando…"; sec.prepend(aviso); }, 400);
  try { await fn(); }
  catch (e) {
    const d = document.createElement("div"); d.className = "erro-carga";
    d.textContent = `Não foi possível carregar: ${e.message}. Tente de novo em alguns segundos.`; sec.prepend(d);
  } finally { clearTimeout(t); aviso?.remove(); }
}

// ---------------------------------------------------------------- conversa
const SUGESTOES = [
  "Qual foi o GMV por segmento no último mês?",
  "Quais lojas de Eletrônicos têm a maior taxa de chargeback nos últimos 90 dias?",
  "Qual a taxa de recompra dos compradores nos últimos 90 dias, por categoria?",
];
$("#sugestoes").innerHTML = SUGESTOES.map((s) => `<button>${esc(s)}</button>`).join("");
$("#sugestoes").querySelectorAll("button").forEach((b) => b.onclick = () => { $("#pergunta").value = b.textContent; $("#form-pergunta").requestSubmit(); });

function msg(quem, html, classe = "bot") {
  const d = document.createElement("div");
  d.className = `msg ${classe}`;
  d.innerHTML = `<div class="quem">${esc(quem)}</div>${html}`;
  $("#chat").appendChild(d);
  $("#chat").scrollTop = 1e9;
  return d;
}
// números no padrão brasileiro: inteiros com milhar, decimais com 1 casa (percentuais/taxas com 1-2 casas)
function fmtCelula(v) {
  if (v === null || v === undefined || v === "" || !/^-?\d+(\.\d+)?$/.test(String(v))) return v ?? "";
  const n = Number(v);
  if (Number.isInteger(n)) return n.toLocaleString("pt-BR");
  const casas = Math.abs(n) < 1 ? 3 : Math.abs(n) < 100 ? 1 : 2;
  return n.toLocaleString("pt-BR", { minimumFractionDigits: casas === 3 ? 1 : casas, maximumFractionDigits: casas });
}
const NUM = (v) => v !== null && v !== "" && /^-?\d+(\.\d+)?$/.test(String(v));
function cabecalho(c) { const t = String(c).replace(/_/g, " ").replace(/\bpct\b/i, "(%)"); return t.charAt(0).toUpperCase() + t.slice(1); }
// coluna de barra: a última coluna toda numérica (normalmente a taxa / o valor que responde a pergunta)
function tabelaHtml(cols, linhas) {
  if (!cols?.length) return "";
  linhas = (linhas || []).slice(0, 50);
  let barra = -1;
  for (let j = cols.length - 1; j >= 0; j--) if (linhas.length && linhas.every((l) => NUM(l[j]))) { barra = j; break; }
  const max = barra >= 0 ? Math.max(...linhas.map((l) => Math.abs(Number(l[barra])))) || 1 : 1;
  return `<div class="tabela-wrap"><table class="tabela">
    <tr>${cols.map((c, j) => `<th class="${NUM(linhas[0]?.[j]) ? "num" : ""}">${esc(cabecalho(c))}</th>`).join("")}</tr>${
    linhas.map((l) => `<tr>${l.map((v, j) => j === barra
      ? `<td class="num" title="${esc(l[0])}: ${esc(fmtCelula(v))}"><div class="barra-dado"><span style="width:${(Math.abs(Number(v)) / max * 100).toFixed(1)}%"></span><b>${esc(fmtCelula(v))}</b></div></td>`
      : `<td class="${NUM(v) ? "num" : ""}">${esc(fmtCelula(v))}</td>`).join("")}</tr>`).join("")}</table></div>`;
}

$("#form-pergunta").onsubmit = async (e) => {
  e.preventDefault();
  const p = $("#pergunta").value.trim();
  if (!p) return;
  $("#pergunta").value = "";
  msg("você", esc(p), "user");
  const aguarde = msg("Genie", "<i>consultando o modelo semântico…</i>");
  try {
    const r = await api("/api/perguntar", { method: "POST", body: JSON.stringify({ pergunta: p, conversa_id: conversaId }) });
    conversaId = r.genie.conversa_id;
    aguarde.innerHTML = `<div class="quem">Genie</div>${md(r.genie.texto || "")}${tabelaHtml(r.genie.colunas, r.genie.linhas)}`;
    if (r.run_id) {
      msg("Supervisor", `O Genie não tem esse dado no modelo semântico. <b>Acionei o time de dados</b> para construir.
        <br><a href="#" onclick="verRun('${r.run_id}');return false;">acompanhar ao vivo →</a>`, "bot time");
      acompanhar(r.run_id);
    }
  } catch (err) { aguarde.innerHTML = `<div class="quem">erro</div>${esc(err.message)}`; }
};

function verRun(id) { runAtual = id; abrirAba("time"); }

async function acompanhar(runId) {
  if (acompanhados.has(runId)) return;
  acompanhados.add(runId);
  let mostrouPergunta = false, mostrouPR = false;
  const loop = async () => {
    try {
      const d = await api(`/api/runs/${runId}`);
      const st = d.run.status;
      if (st === "aguardando_esclarecimento" && !mostrouPergunta) { mostrouPergunta = true; cartaoEsclarecimento(runId, d); }
      if (st === "aguardando_revisao" && !mostrouPR) {
        mostrouPR = true;
        msg("Supervisor", `Produto de dados construído e validado. ${d.run.pr_url ? `<a href="${esc(d.run.pr_url)}" target="_blank">PR aberto</a>` : "PR pronto"} —
          aguardando revisão do time de engenharia de dados.`, "bot time");
        atualizarBadge();
      }
      if (st === "concluido") {
        const fin = d.steps.filter((s) => s.acao === "final").pop();
        const g = fin?.detalhe?.genie || {};
        msg("Genie + Supervisor", `${md(d.run.resposta_final || "")}${tabelaHtml(g.colunas, g.linhas)}`, "bot time");
        return;
      }
      if (st === "falhou") {
        const el = msg("Supervisor", `Execução falhou: ${esc(d.run.erro || "")} <br><button class="sec">↻ Tentar de novo</button>`, "bot time");
        el.querySelector("button").onclick = async (ev) => {
          ev.target.disabled = true;
          await api(`/api/runs/${runId}/tentar-novamente`, { method: "POST" });
          acompanhados.delete(runId); acompanhar(runId);
        };
        return;
      }
      if (st === "rejeitado") { msg("Supervisor", "PR rejeitado: os objetos do sandbox foram descartados.", "bot time"); return; }
      if (st === "descartado") return;  // execução arquivada por um reset da demo
    } catch (e) { /* tenta de novo */ }
    setTimeout(loop, 2500);
  };
  loop();
}

// o agente pode indicar a recomendada pelo texto, pelo começo do texto ou só pela letra ("A")
function recomendada(opcao, rec) {
  if (!rec) return false;
  const o = String(opcao).trim(), r = String(rec).trim();
  return o === r || o.startsWith(r) || r.startsWith(o.slice(0, 25)) || (/^[A-Z]\)?$/.test(r) && o.startsWith(r.replace(")", "") + ")"));
}

function formEsclarecimento(runId, perguntas) {
  return `<div class="perguntas-card"><b>O Analyst Agent precisa de uma decisão do negócio:</b>${perguntas.map((p) => `
      <div style="margin-top:10px">${esc(p.pergunta)}</div>
      <div class="opcoes">${p.opcoes.map((o) => { const r = recomendada(o, p.recomendada); return `<label><input type="radio" name="${esc(p.id)}" value="${esc(o)}" ${r ? "checked" : ""}>${esc(o)}${r ? '<span class="rec">recomendada</span>' : ""}</label>`; }).join("")}</div>`).join("")}
    <button class="primario">Responder</button></div>`;
}

function ligarEsclarecimento(el, runId, perguntas) {
  el.querySelector("button.primario").onclick = async (ev) => {
    ev.target.disabled = true;
    const respostas = {};
    perguntas.forEach((p) => { const sel = el.querySelector(`input[name="${p.id}"]:checked`); respostas[p.id] = sel ? sel.value : p.recomendada; });
    await api(`/api/runs/${runId}/esclarecimento`, { method: "POST", body: JSON.stringify({ respostas }) });
    document.querySelectorAll(".perguntas-card button.primario").forEach((b) => { b.disabled = true; b.textContent = "Respondido ✓"; });
  };
}

function cartaoEsclarecimento(runId, d) {
  const ap = d.aprovacoes.filter((a) => a.tipo === "esclarecimento" && a.status === "pendente").pop();
  const perguntas = ap?.pergunta?.perguntas || [];
  const el = msg("Analyst Agent", formEsclarecimento(runId, perguntas), "bot time");
  ligarEsclarecimento(el, runId, perguntas);
}

// cartão de decisão humana na aba Time ao vivo (renderiza uma vez por aprovação, para não perder a seleção)
let acaoRenderizada = null;
function desenharAcaoHumana(runId, d) {
  const box = $("#acao-humana");
  const ap = d.aprovacoes.filter((a) => a.status === "pendente").pop();
  if (!ap) { box.innerHTML = ""; acaoRenderizada = null; return; }
  if (acaoRenderizada === ap.approval_id) return;
  acaoRenderizada = ap.approval_id;
  if (ap.tipo === "esclarecimento") {
    const perguntas = ap.pergunta?.perguntas || [];
    box.innerHTML = `<div class="acao-humana"><h3>⏸ Aguardando decisão do negócio</h3>${formEsclarecimento(runId, perguntas)}</div>`;
    ligarEsclarecimento(box, runId, perguntas);
  } else {
    box.innerHTML = `<div class="acao-humana"><h3>⏸ Aguardando revisão do engenheiro de dados</h3>
      <div>O produto de dados foi construído e aprovado pelo Quality Agent. ${d.run.pr_url ? `<a href="${esc(d.run.pr_url)}" target="_blank">PR #${d.run.pr_numero}</a>` : "PR pronto"}.</div>
      <div class="acoes"><button class="primario">Abrir revisão →</button></div></div>`;
    box.querySelector("button").onclick = () => { revSel = runId; abrirAba("revisao"); detalheRevisao(); };
  }
}

// ---------------------------------------------------------------- time ao vivo
async function carregarRuns() {
  const runs = await api("/api/runs");
  if (!runAtual && runs.length) runAtual = runs[0].run_id;
  $("#sel-run").innerHTML = runs.map((r) => `<option value="${r.run_id}" ${r.run_id === runAtual ? "selected" : ""}>
    ${esc(r.pergunta.slice(0, 70))} · ${esc(r.status)}</option>`).join("");
  $("#sel-run").onchange = (e) => { runAtual = e.target.value; desenharRun(); };
  desenharRun();
}

function fmtHora(t) { return t ? new Date(t).toLocaleTimeString("pt-BR") : ""; }

function chip(agente) { return `<span class="chip ag-${esc(agente)}">${esc(NOME_AGENTE[agente] || agente)}</span>`; }

async function desenharRun() {
  if (!runAtual) { $("#timeline").innerHTML = '<div class="vazio">Nenhuma execução ainda. Faça uma pergunta na Conversa.</div>'; return; }
  const d = await api(`/api/runs/${runAtual}`);
  const r = d.run;
  const fim = ["concluido", "rejeitado", "descartado", "falhou"].includes(r.status);
  const ativo = fim ? null : ETAPA_NO[r.etapa] || "supervisor";
  const esperando = r.status.startsWith("aguardando");
  desenharAcaoHumana(runAtual, d);
  // estatísticas por nó
  const est = {};
  d.steps.forEach((s) => { const e = (est[s.agente] ||= { tools: 0, tokens: 0 }); if (s.acao === "tool") e.tools++; e.tokens += (s.tokens_entrada || 0) + (s.tokens_saida || 0); });
  const respondida = (tipo) => d.aprovacoes.some((a) => a.tipo === tipo && a.status === "respondida");
  const feito = (k) => k === "negocio" ? respondida("esclarecimento") : k === "engenheiro" ? respondida("pr") : !!est[k];
  const no = ([k, nome, papel]) => {
    const cls = k === ativo ? (esperando ? "espera" : "ativo") : feito(k) ? "feito" : "";
    const st = k === ativo ? (esperando ? "aguardando você" : "trabalhando…") : feito(k) ? "concluído" : "aguardando";
    const info = est[k] && (est[k].tools || est[k].tokens) ? `<div class="info">${est[k].tools} ferramentas · ${(est[k].tokens / 1000).toFixed(0)}k tokens</div>` : `<div class="info">${papel}</div>`;
    return `<div class="no ${cls} ${["negocio", "engenheiro"].includes(k) ? "humano" : ""}"><div class="ic ag-${k}">${ICONE[k]}</div>
      <div class="nm">${nome}</div><div class="st">${st}</div>${info}</div>`;
  };
  const seta = (loop) => `<div class="seta ${loop ? "loop" : ""}">${loop ? `<span>⇄ ${Math.max(1, r.iteracoes || 0)}x</span>` : ""}</div>`;
  $("#diagrama").innerHTML = FLUXO.map((n, i) => (i ? seta(FLUXO[i - 1][0] === "engineer") : "") + no(n)).join("");
  const dur = r.criado_em ? Math.round(((r.finalizado_em ? new Date(r.finalizado_em) : new Date()) - new Date(r.criado_em)) / 1000) : 0;
  const ROT_STATUS = { em_andamento: "em andamento", aguardando_esclarecimento: "aguardando o negócio", aguardando_revisao: "aguardando revisão",
    concluido: "concluído", falhou: "falhou", rejeitado: "rejeitado", descartado: "descartado" };
  $("#kpis-run").innerHTML = [
    ["Status", `<span class="pill st-${esc(r.status)}">${esc(ROT_STATUS[r.status] || r.status)}</span>`], ["Iterações", r.iteracoes || 0],
    ["Tokens", ((r.tokens_entrada || 0) + (r.tokens_saida || 0)).toLocaleString("pt-BR")],
    ["Tempo", `${Math.floor(dur / 60)}m${String(dur % 60).padStart(2, "0")}s`],
    ["Pull request", r.pr_url ? `<a href="${esc(r.pr_url)}" target="_blank">#${r.pr_numero} ↗</a>` : "—"],
  ].map(([k, v]) => `<div class="kpi">${k}<b>${String(v).startsWith("<") ? v : esc(v)}</b></div>`).join("");
  $("#plano").innerHTML = md(r.plano || "<i>…</i>");
  $("#tab-dq").innerHTML = d.dq.length ? `<tr><th>It.</th><th>Teste</th><th>Status</th><th>Evidência</th></tr>${d.dq.map((t) => `<tr><td>${t.iteracao}</td><td>${esc(t.teste)}</td>
      <td><span class="pill st-${t.status}">${t.status === "passou" ? "✓ passou" : "✕ falhou"}</span></td><td>${esc((t.evidencia || "").slice(0, 220))}</td></tr>`).join("")}`
    : "<tr><td class='vazio'>ainda sem testes</td></tr>";
  // linha do tempo: agrupa chamadas de ferramenta seguidas do mesmo agente
  const passos = d.steps.filter((s) => !(s.acao === "llm" && !(s.detalhe?.texto || "").trim()) && s.acao !== "agente");
  const grupos = [];
  passos.forEach((s) => { const g = grupos[grupos.length - 1];
    if (s.acao === "tool" && g?.tools && g.agente === s.agente) g.tools.push(s); else grupos.push(s.acao === "tool" ? { agente: s.agente, tools: [s], iniciado_em: s.iniciado_em } : s); });
  $("#timeline").innerHTML = grupos.slice(-80).reverse().map((s) => {
    if (s.tools) {
      const cont = {}; s.tools.forEach((t) => cont[t.titulo] = (cont[t.titulo] || 0) + 1);
      const resumo = Object.entries(cont).map(([n, c]) => `${n}${c > 1 ? ` ×${c}` : ""}`).join(" · ");
      const erros = s.tools.filter((t) => t.status === "erro").length;
      return `<li class="${esc(s.agente)}"><span class="t">${fmtHora(s.iniciado_em)}</span> ${chip(s.agente)}
        <details><summary>🔧 ${s.tools.length} ferramenta${s.tools.length > 1 ? "s" : ""}: ${esc(resumo)}${erros ? ` <span class="st-falhou">(${erros} com erro)</span>` : ""}</summary>
        ${s.tools.map((t) => `<div class="tool"><b>${esc(t.titulo)}</b>${t.status === "erro" ? " ❌" : ""}<pre>${esc(JSON.stringify(t.detalhe?.args || {}, null, 1)).slice(0, 700)}${t.detalhe?.saida ? "\n→ " + esc(String(t.detalhe.saida).slice(0, 600)) : ""}</pre></div>`).join("")}
        </details></li>`;
    }
    let corpo = "";
    if (s.acao === "llm") corpo = `<div class="md">${md(String(s.detalhe?.texto || "").slice(0, 1500))}</div>`;
    else if (s.acao === "handoff") corpo = `<div class="handoff">${esc(s.detalhe?.motivo || "")}</div>`;
    else if (s.acao === "erro") corpo = `<pre class="st-erro">${esc(s.detalhe?.erro || "")}</pre>`;
    else if (s.acao === "especificacao") corpo = `<details><summary>ver especificação</summary><pre>${esc(JSON.stringify(s.detalhe, null, 1)).slice(0, 3000)}</pre></details>`;
    else if (s.detalhe?.texto) corpo = `<div class="md">${md(s.detalhe.texto)}</div>`;
    return `<li class="${esc(s.agente)}"><span class="t">${fmtHora(s.iniciado_em)}</span> ${chip(s.agente)} <span class="titulo-passo">${esc(s.titulo)}</span>
      ${s.status === "em_andamento" ? " ⏳" : s.status === "erro" ? " ❌" : ""}${corpo}</li>`;
  }).join("");
}
setInterval(() => { if ($("#aba-time").classList.contains("ativa")) desenharRun().catch(() => {}); }, 2000);
setInterval(() => atualizarBadge().catch(() => {}), 10000);

// ---------------------------------------------------------------- revisão
let revSel = null;
async function atualizarBadge() {
  const runs = await api("/api/runs");
  $("#dot-time").classList.toggle("oculto", !runs.some((r) => r.status.startsWith("aguardando")));
  const n = runs.filter((r) => r.status === "aguardando_revisao").length;
  $("#badge-revisao").textContent = n;
  $("#badge-revisao").classList.toggle("oculto", !n);
}
async function carregarRevisao() {
  const runs = (await api("/api/runs")).filter((r) => r.pr_url || ["aguardando_revisao", "concluido", "rejeitado", "descartado"].includes(r.status));
  $("#lista-revisao").innerHTML = runs.map((r) => `<li data-id="${r.run_id}" class="${r.run_id === revSel ? "sel" : ""}">
    <div>${esc(r.produto || r.pergunta.slice(0, 50))}</div><div class="estado">${esc(r.status)} ${r.pr_url ? "· PR" : ""}</div></li>`).join("") || '<li class="vazio">nenhum PR</li>';
  $("#lista-revisao").querySelectorAll("li[data-id]").forEach((li) => li.onclick = () => { revSel = li.dataset.id; carregarRevisao(); detalheRevisao(); });
  atualizarBadge();
}
async function detalheRevisao() {
  const [d, pr] = await Promise.all([api(`/api/runs/${revSel}`), api(`/api/runs/${revSel}/pr`)]);
  const r = d.run;
  const espec = d.steps.filter((s) => s.acao === "especificacao").pop()?.detalhe || {};
  const decisoes = (espec.decisoes_do_negocio || []).length ? espec.decisoes_do_negocio
    : d.aprovacoes.filter((a) => a.tipo === "esclarecimento" && a.resposta).flatMap((a) => Object.values(a.resposta).map((v) => ({ pergunta: "", resposta: v })));
  const q = d.artefatos.find((a) => a.nome === "relatorio_quality.md")?.conteudo || "";
  const resultado = q.includes("## Resposta") ? q.slice(q.indexOf("## Resposta")).replace(/^##[^\n]*\n/, "") : "";
  const ultimaIt = Math.max(0, ...d.dq.map((t) => t.iteracao));
  const aprovadoQ = d.dq.length && d.dq.filter((t) => t.iteracao === ultimaIt).every((t) => t.status === "passou");
  const objetos = Object.keys(r.estado?.objetos || {});
  const arquivosPR = pr.arquivos || [];
  const sqls = d.artefatos.filter((a) => a.tipo === "sql");
  const codigo = arquivosPR.length
    ? arquivosPR.map((f) => `<h4>${esc(f.arquivo)} <span class="pill">${esc(f.status)}</span></h4><pre class="diff">${esc(f.patch).split("\n").map((l) =>
        l.startsWith("+") ? `<span class="add">${l}</span>` : l.startsWith("-") ? `<span class="del">${l}</span>` : l).join("\n")}</pre>`).join("")
    : sqls.map((a) => `<h4>${esc(a.nome)}</h4><pre><code class="language-sql">${esc(a.conteudo)}</code></pre>`).join("");
  const testes = [...new Set(d.dq.map((t) => t.iteracao))].map((it) => `<h4>Iteração ${it}</h4><table class="tabela">${d.dq.filter((t) => t.iteracao === it).map((t) =>
      `<tr><td style="width:34%">${esc(t.teste)}</td><td style="width:90px"><span class="pill st-${t.status}">${t.status === "passou" ? "✓ passou" : "✕ falhou"}</span></td><td>${esc(t.evidencia || "")}</td></tr>`).join("")}</table>`).join("");
  const lista = (xs) => `<ul>${(xs || []).map((x) => `<li>${esc(typeof x === "string" ? x : `${x.nome}: ${x.definicao}`)}</li>`).join("")}</ul>`;
  const pode = r.status === "aguardando_revisao";
  $("#rev-detalhe").innerHTML = `
    ${!CFG.github ? '<div class="aviso">GitHub não configurado: o PR é simulado e os artefatos ficam no volume do time.</div>' : ""}
    <div class="cartao rev-cab">
      <div class="rev-titulo">${esc(espec.titulo || r.produto || "Produto de dados")}</div>
      <div class="rev-pergunta">“${esc(r.pergunta)}”</div>
      <div class="rev-meta">
        <span class="pill ${aprovadoQ ? "st-passou" : "st-falhou"}">${aprovadoQ ? "✓ Quality aprovou" : "✕ Quality reprovou"}</span>
        <span class="pill">${r.iteracoes || 0} iteraç${(r.iteracoes || 0) > 1 ? "ões" : "ão"} Engineer ⇄ Quality</span>
        <span class="pill">${objetos.length} objeto${objetos.length === 1 ? "" : "s"}</span>
        ${r.pr_url ? `<a class="pill link" href="${esc(r.pr_url)}" target="_blank">PR #${r.pr_numero} no GitHub ↗</a>` : '<span class="pill">PR simulado</span>'}
        <span class="rev-autor">pedido por ${esc(r.solicitante)}${pr.pr ? ` · PR de ${esc(pr.pr.autor)}` : ""}</span>
      </div>
    </div>
    <div class="abas-int">${[["resumo", "Resumo"], ["testes", `Testes (${d.dq.length})`], ["codigo", `Código (${arquivosPR.length || sqls.length})`], ["espec", "Especificação"]]
      .map(([k, n], i) => `<button data-p="${k}" class="${i ? "" : "ativa"}">${n}</button>`).join("")}</div>
    <div class="painel ativa" data-p="resumo">
      <div class="cartao"><h3>Decisões do negócio</h3>${decisoes.length ? `<ul>${decisoes.map((x) => `<li>${x.pergunta ? `${esc(x.pergunta)} → ` : ""}<b>${esc(x.resposta)}</b></li>`).join("")}</ul>` : "<i>nenhuma</i>"}</div>
      <div class="cartao"><h3>Resultado no sandbox (pergunta original)</h3><div class="md">${resultado ? md(resultado) : "<i>—</i>"}</div></div>
      <div class="cartao"><h3>Objetos criados</h3>${objetos.length ? `<ul>${objetos.map((o) => `<li><code>${esc(o)}</code></li>`).join("")}</ul>` : "<i>—</i>"}</div>
    </div>
    <div class="painel" data-p="testes"><div class="cartao">${testes || "<i>sem testes</i>"}</div></div>
    <div class="painel" data-p="codigo"><div class="cartao">${codigo || "<i>sem arquivos</i>"}</div></div>
    <div class="painel" data-p="espec"><div class="cartao">
      <h3>Objetivo</h3><p>${esc(espec.objetivo || "")}</p><h3>Grão</h3><p>${esc(espec.grao || "")}</p>
      <h3>Regras</h3>${lista(espec.regras)}<h3>Medidas</h3>${lista(espec.medidas)}<h3>Dimensões</h3>${lista(espec.dimensoes)}</div></div>
    ${pode ? `<div class="decisao-fixa"><textarea id="rev-coment" placeholder="Comentário para o PR (obrigatório para solicitar mudanças)"></textarea>
      <div class="acoes"><button class="primario" data-d="aprovar">✓ Aprovar e fazer merge</button><button class="sec" data-d="mudancas">↻ Solicitar mudanças</button>
      <button class="perigo" data-d="rejeitar">✕ Rejeitar</button></div></div>` : `<div class="cartao"><h3>Decisão</h3><span class="pill st-${esc(r.status)}">${esc(r.status)}</span></div>`}`;
  $("#rev-detalhe").querySelectorAll(".abas-int button").forEach((b) => b.onclick = () => {
    $("#rev-detalhe").querySelectorAll(".abas-int button").forEach((x) => x.classList.toggle("ativa", x === b));
    $("#rev-detalhe").querySelectorAll(".painel").forEach((p) => p.classList.toggle("ativa", p.dataset.p === b.dataset.p));
  });
  if (window.hljs) $("#rev-detalhe").querySelectorAll("code.language-sql").forEach((c) => hljs.highlightElement(c));
  $("#rev-detalhe").querySelectorAll("button[data-d]").forEach((b) => b.onclick = async () => {
    const decisao = b.dataset.d, comentario = $("#rev-coment").value;
    if (decisao === "mudancas" && !comentario.trim()) { alert("Descreva as mudanças."); return; }
    $("#rev-detalhe").querySelectorAll("button[data-d]").forEach((x) => x.disabled = true);
    try { await api(`/api/runs/${revSel}/revisao`, { method: "POST", body: JSON.stringify({ decisao, comentario }) }); runAtual = revSel; abrirAba("time"); acompanhar(revSel); }
    catch (e) { alert(e.message); $("#rev-detalhe").querySelectorAll("button[data-d]").forEach((x) => x.disabled = false); }
  });
}

// ---------------------------------------------------------------- operação
async function carregarOperacao() {
  const [o, runs] = await Promise.all([api("/api/operacao"), api("/api/runs")]);
  const s = o.resumo || {};
  $("#op-kpis").innerHTML = [["execuções", s.execucoes], ["concluídas", s.concluidas], ["PRs", s.prs], ["iterações médias", fmtCelula(s.iteracoes_media)],
    ["minutos por execução", fmtCelula(s.minutos_medio)], ["tokens", ((+s.tokens_entrada || 0) + (+s.tokens_saida || 0)).toLocaleString("pt-BR")]]
    .map(([k, v]) => `<div class="kpi">${k.charAt(0).toUpperCase() + k.slice(1)}<b>${esc(v ?? 0)}</b></div>`).join("");
  const ROTULO = { agente: "Agente", chamadas_llm: "Chamadas ao LLM", tools: "Ferramentas", tokens_entrada: "Tokens de entrada",
    tokens_saida: "Tokens de saída", seg_medio: "Tempo médio (s)", tipo: "Tipo", decisao: "Decisão", n: "Quantidade",
    status: "Status", criado_em: "Início", pergunta: "Pergunta", iteracoes: "Iterações", produto: "Produto de dados" };
  const fmt = (c, v) => c === "criado_em" && v ? new Date(v).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
    : c === "agente" && v ? v.charAt(0).toUpperCase() + v.slice(1) : fmtCelula(v);
  const tab = (el, linhas, cols) => { $(el).innerHTML = `<tr>${cols.map((c) => `<th>${ROTULO[c] || c}</th>`).join("")}</tr>` +
    (linhas || []).map((l) => `<tr>${cols.map((c) => `<td>${esc(fmt(c, l[c] ?? ""))}</td>`).join("")}</tr>`).join(""); };
  const ags = (o.por_agente || []).filter((a) => !["genie", "humano"].includes(a.agente))
    .map((a) => ({ ...a, total: (+a.tokens_entrada || 0) + (+a.tokens_saida || 0) })).sort((x, y) => y.total - x.total);
  const maxT = Math.max(1, ...ags.map((a) => a.total));
  $("#op-barras").innerHTML = ags.map((a) => `<div class="hbar" title="${esc(NOME_AGENTE[a.agente] || a.agente)}: ${a.total.toLocaleString("pt-BR")} tokens · ${a.chamadas_llm} chamadas ao LLM · ${a.tools} ferramentas">
      <div class="hbar-rot">${chip(a.agente)}</div><div class="hbar-trilho"><span style="width:${(a.total / maxT * 100).toFixed(1)}%"></span></div>
      <div class="hbar-val">${(a.total / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 0 })}k</div></div>`).join("");
  tab("#op-agentes", ags, ["agente", "chamadas_llm", "tools", "tokens_entrada", "tokens_saida", "seg_medio"]);
  tab("#op-aprov", o.aprovacoes, ["tipo", "decisao", "n"]);
  const dq = Object.fromEntries((o.dq || []).map((x) => [x.status, +x.n]));
  $("#op-dq").innerHTML = `<div class="tiles"><div class="tile"><span class="pill st-passou">✓ passou</span><b>${dq.passou || 0}</b></div>
    <div class="tile"><span class="pill st-falhou">✕ falhou</span><b>${dq.falhou || 0}</b></div>
    <div class="tile"><span class="pill">testes aprovados</span><b>${(dq.passou || 0) + (dq.falhou || 0) ? Math.round((dq.passou || 0) / ((dq.passou || 0) + (dq.falhou || 0)) * 100) : 0}%</b></div></div>`;
  tab("#op-runs", runs, ["criado_em", "pergunta", "status", "iteracoes", "produto", "tokens_saida"]);
  $("#op-links").innerHTML = [CFG.experimento_url && `<a target="_blank" href="${CFG.experimento_url}">Traces no MLflow →</a>`,
    CFG.genie_url && `<a target="_blank" href="${CFG.genie_url}">Genie →</a>`].filter(Boolean).join("");
}

// ---------------------------------------------------------------- início
(async () => {
  CFG = await api("/api/config");
  const iniciais = (CFG.nome || CFG.usuario).split(" ").filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("");
  $("#usuario").innerHTML = `<div class="avatar">${esc(iniciais)}</div><div><div class="nome">${esc(CFG.nome || CFG.usuario)}</div>
    <div class="email">${esc(CFG.usuario)}${CFG.revisor ? " · revisor" : ""}</div></div>`;
  $("#usuario").title = `Modelo: ${CFG.modelo}`;
  msg("Genie", "Olá! Pergunte sobre vendas, lojistas, pagamentos, disputas, atendimento ou marketing. Se eu não tiver o dado, o time de dados constrói. 🚀");
  const runs = await api("/api/runs");
  runs.filter((r) => !["concluido", "falhou", "rejeitado", "descartado"].includes(r.status)).forEach((r) => acompanhar(r.run_id));
  atualizarBadge();
})();
