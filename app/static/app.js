// Agentic Data Team — front-end (sem build): Conversa, Time ao vivo, Revisão e Operação.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const md = (s) => (window.marked ? marked.parse(String(s ?? "")) : `<pre>${esc(s)}</pre>`);
const api = async (url, opts = {}) => {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
};
const AGENTES = [
  ["supervisor", "🧭", "Supervisor"], ["discovery", "🔎", "Discovery"], ["analyst", "📐", "Analyst"],
  ["engineer", "🛠️", "Engineer"], ["quality", "🧪", "Quality"], ["humano", "🧑‍💻", "Humano"],
];
const ETAPA_AGENTE = { supervisor: "supervisor", discovery: "discovery", analyst: "analyst", engineer: "engineer", quality: "quality",
  pull_request: "engineer", aguardando_esclarecimento: "humano", aguardando_revisao: "humano", promover: "supervisor", genie: "supervisor" };
const ORDEM = ["supervisor", "discovery", "analyst", "engineer", "quality", "humano"];
let CFG = {}, runAtual = null, conversaId = null;
const acompanhados = new Set();

// ---------------------------------------------------------------- abas
document.querySelectorAll("nav button").forEach((b) => b.onclick = () => abrirAba(b.dataset.aba));
function abrirAba(nome) {
  document.querySelectorAll("nav button").forEach((x) => x.classList.toggle("ativa", x.dataset.aba === nome));
  document.querySelectorAll(".aba").forEach((x) => x.classList.toggle("ativa", x.id === `aba-${nome}`));
  if (nome === "revisao") carregarRevisao();
  if (nome === "operacao") carregarOperacao();
  if (nome === "time") carregarRuns();
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
function tabelaHtml(cols, linhas) {
  if (!cols?.length) return "";
  return `<table class="tabela"><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>${
    (linhas || []).slice(0, 20).map((l) => `<tr>${l.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</table>`;
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

async function desenharRun() {
  if (!runAtual) { $("#timeline").innerHTML = '<div class="vazio">Nenhuma execução ainda. Faça uma pergunta na Conversa.</div>'; return; }
  const d = await api(`/api/runs/${runAtual}`);
  const r = d.run;
  const ativo = ETAPA_AGENTE[r.etapa] || (r.status === "concluido" ? null : "supervisor");
  const esperando = r.status.startsWith("aguardando");
  desenharAcaoHumana(runAtual, d);
  const vistos = new Set(d.steps.map((s) => s.agente));
  const estAtivo = (k) => k === ativo && r.status !== "concluido";
  $("#diagrama").innerHTML = AGENTES.map(([k, ic, nm]) => `<div class="agente ${estAtivo(k) ? (esperando ? "espera" : "ativo") : vistos.has(k) ? "feito" : ""}">
      <div class="ic">${ic}</div><div class="nm">${nm}</div><div class="st">${estAtivo(k) ? (esperando ? "aguardando você" : "trabalhando…") : vistos.has(k) ? "✓" : "—"}</div></div>`).join("");
  const dur = r.criado_em ? Math.round(((r.finalizado_em ? new Date(r.finalizado_em) : new Date()) - new Date(r.criado_em)) / 1000) : 0;
  $("#kpis-run").innerHTML = [
    ["status", r.status], ["iteração", r.iteracoes || 0], ["tokens", ((r.tokens_entrada || 0) + (r.tokens_saida || 0)).toLocaleString("pt-BR")],
    ["tempo", `${Math.floor(dur / 60)}m${String(dur % 60).padStart(2, "0")}s`], ["PR", r.pr_url ? `<a href="${esc(r.pr_url)}" target="_blank">#${r.pr_numero}</a>` : "—"],
  ].map(([k, v]) => `<div class="kpi">${k}<b>${typeof v === "string" && v.startsWith("<a") ? v : esc(v)}</b></div>`).join("");
  $("#plano").innerHTML = md(r.plano || "<i>…</i>");
  $("#tab-dq").innerHTML = d.dq.length ? `<tr><th>it.</th><th>teste</th><th>status</th><th>evidência</th></tr>${d.dq.map((t) => `<tr><td>${t.iteracao}</td><td>${esc(t.teste)}</td>
      <td class="st-${t.status}">${esc(t.status)}</td><td>${esc((t.evidencia || "").slice(0, 220))}</td></tr>`).join("")}` : "<tr><td class='vazio'>ainda sem testes</td></tr>";
  const itens = d.steps.filter((s) => !(s.acao === "llm" && !(s.detalhe?.texto || "").trim())).slice(-120).reverse();
  $("#timeline").innerHTML = itens.map((s) => {
    let corpo = "";
    if (s.acao === "tool") corpo = `<pre>${esc(JSON.stringify(s.detalhe?.args || {}, null, 1)).slice(0, 900)}${s.detalhe?.saida ? "\n→ " + esc(String(s.detalhe.saida).slice(0, 700)) : ""}</pre>`;
    else if (s.acao === "llm") corpo = `<div class="md">${md(String(s.detalhe?.texto || "").slice(0, 1500))}</div>`;
    else if (s.acao === "handoff") corpo = `<div>${esc(s.detalhe?.motivo || "")}</div>`;
    else if (s.acao === "erro") corpo = `<pre class="st-erro">${esc(s.detalhe?.erro || "")}</pre>`;
    else if (s.acao === "especificacao") corpo = `<pre>${esc(JSON.stringify(s.detalhe, null, 1)).slice(0, 1500)}</pre>`;
    else if (s.detalhe?.texto) corpo = `<div class="md">${md(s.detalhe.texto)}</div>`;
    const ag = s.agente === "humano" ? "humano" : s.agente;
    return `<li class="${esc(ag)}"><span class="t">${fmtHora(s.iniciado_em)}</span> · <span class="ag">${esc(s.agente)}</span> · ${esc(s.titulo)}
      ${s.status === "em_andamento" ? " ⏳" : s.status === "erro" ? " ❌" : ""}${corpo}</li>`;
  }).join("");
}
setInterval(() => { if ($("#aba-time").classList.contains("ativa")) desenharRun(); }, 2000);

// ---------------------------------------------------------------- revisão
let revSel = null;
async function atualizarBadge() {
  const runs = await api("/api/runs");
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
  const decisoes = d.aprovacoes.filter((a) => a.tipo === "esclarecimento" && a.resposta).map((a) => a.resposta);
  const q = d.artefatos.find((a) => a.nome === "relatorio_quality.md");
  const arquivos = pr.arquivos?.length ? pr.arquivos.map((f) => `<h4>${esc(f.arquivo)}</h4><pre class="diff">${esc(f.patch).split("\n").map((l) =>
      l.startsWith("+") ? `<span class="add">${l}</span>` : l.startsWith("-") ? `<span class="del">${l}</span>` : l).join("\n")}</pre>`).join("")
    : d.artefatos.filter((a) => a.tipo === "sql").map((a) => `<h4>${esc(a.nome)}</h4><pre>${esc(a.conteudo)}</pre>`).join("");
  const pode = r.status === "aguardando_revisao";
  $("#rev-detalhe").innerHTML = `
    ${!CFG.github ? '<div class="aviso">GitHub não configurado: o PR é simulado e os artefatos ficam no volume do time. Configure o secret <code>github_token</code> do app.</div>' : ""}
    ${CFG.modo_aprovacao === "app_token" && CFG.github ? '<div class="aviso">Modo de aprovação <b>app_token</b>: o merge é feito pelo token do app e a decisão fica registrada com a sua identidade. Com o GitHub App + OAuth, a aprovação sai com o seu usuário do GitHub.</div>' : ""}
    <div class="cartao"><h3>Pedido</h3><div><b>${esc(r.pergunta)}</b></div><div class="estado">por ${esc(r.solicitante)} · run ${esc(r.run_id)} ·
      ${r.pr_url ? `<a href="${esc(r.pr_url)}" target="_blank">abrir no GitHub</a>` : "PR simulado"} · ${pr.pr ? `autor ${esc(pr.pr.autor)}` : ""}</div></div>
    <div class="cartao"><h3>Especificação (Analyst) e decisões do negócio</h3><pre>${esc(JSON.stringify({ objetivo: espec.objetivo, grao: espec.grao, regras: espec.regras, medidas: espec.medidas }, null, 1))}</pre>
      ${decisoes.length ? `<div>Decisões: ${esc(JSON.stringify(decisoes))}</div>` : ""}</div>
    <div class="cartao"><h3>Quality Agent</h3><div class="md">${q ? md(q.conteudo) : "<i>sem relatório</i>"}</div></div>
    <div class="cartao"><h3>Mudanças (${pr.arquivos?.length ? "diff do PR" : "artefatos"})</h3>${arquivos || "<i>sem arquivos</i>"}</div>
    <div class="cartao"><h3>Decisão</h3>${pode ? `<div class="acoes"><textarea id="rev-coment" placeholder="Comentário (obrigatório para solicitar mudanças)"></textarea>
      <button class="primario" data-d="aprovar">✅ Aprovar e fazer merge</button><button class="sec" data-d="mudancas">🔁 Solicitar mudanças</button>
      <button class="perigo" data-d="rejeitar">⛔ Rejeitar</button></div>` : `<div>Status: <b>${esc(r.status)}</b></div>`}</div>`;
  $("#rev-detalhe").querySelectorAll("button[data-d]").forEach((b) => b.onclick = async () => {
    const decisao = b.dataset.d, comentario = $("#rev-coment").value;
    if (decisao === "mudancas" && !comentario.trim()) { alert("Descreva as mudanças."); return; }
    $("#rev-detalhe").querySelectorAll("button").forEach((x) => x.disabled = true);
    try { await api(`/api/runs/${revSel}/revisao`, { method: "POST", body: JSON.stringify({ decisao, comentario }) }); runAtual = revSel; abrirAba("time"); acompanhar(revSel); }
    catch (e) { alert(e.message); $("#rev-detalhe").querySelectorAll("button").forEach((x) => x.disabled = false); }
  });
}

// ---------------------------------------------------------------- operação
async function carregarOperacao() {
  const [o, runs] = await Promise.all([api("/api/operacao"), api("/api/runs")]);
  const s = o.resumo || {};
  $("#op-kpis").innerHTML = [["execuções", s.execucoes], ["concluídas", s.concluidas], ["PRs", s.prs], ["iterações médias", s.iteracoes_media],
    ["minutos por execução", s.minutos_medio], ["tokens", ((+s.tokens_entrada || 0) + (+s.tokens_saida || 0)).toLocaleString("pt-BR")]]
    .map(([k, v]) => `<div class="kpi">${k}<b>${esc(v ?? 0)}</b></div>`).join("");
  const tab = (el, linhas, cols) => { $(el).innerHTML = `<tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>` + (linhas || []).map((l) => `<tr>${cols.map((c) => `<td>${esc(l[c] ?? "")}</td>`).join("")}</tr>`).join(""); };
  tab("#op-agentes", o.por_agente, ["agente", "chamadas_llm", "tools", "tokens_entrada", "tokens_saida", "seg_medio"]);
  tab("#op-aprov", o.aprovacoes, ["tipo", "decisao", "n"]);
  tab("#op-dq", o.dq, ["status", "n"]);
  tab("#op-runs", runs, ["criado_em", "pergunta", "status", "iteracoes", "produto", "tokens_saida"]);
  $("#op-links").innerHTML = [CFG.experimento_url && `<a target="_blank" href="${CFG.experimento_url}">Traces no MLflow →</a>`,
    CFG.genie_url && `<a target="_blank" href="${CFG.genie_url}">Genie →</a>`].filter(Boolean).join("");
}

// ---------------------------------------------------------------- início
(async () => {
  CFG = await api("/api/config");
  $("#usuario").textContent = `${CFG.usuario} · ${CFG.modelo}`;
  msg("Genie", "Olá! Pergunte sobre vendas, lojistas, pagamentos, disputas, atendimento ou marketing. Se eu não tiver o dado, o time de dados constrói. 🚀");
  const runs = await api("/api/runs");
  runs.filter((r) => !["concluido", "falhou", "rejeitado", "descartado"].includes(r.status)).forEach((r) => acompanhar(r.run_id));
  atualizarBadge();
})();
