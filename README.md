# agentic-teams

**From Data Consumer to Data Creator** — base mock Nuvemshop-like + um **time agêntico de engenharia de dados** no Databricks.
A pessoa de negócio pergunta no Genie; quando o dado não existe, o time de agentes descobre as fontes, especifica, constrói,
testa e abre um PR; um engenheiro humano revisa e aprova; o produto de dados é promovido e o Genie passa a responder.

```
Genie ──(lacuna)──▶ Supervisor ─▶ Discovery ─▶ Analyst ─▶ ⏸ negócio esclarece ─▶ Engineer ⇄ Quality (até 3x)
                                                                                     │
        Genie responde ◀── promoção (job) ◀── ⏸ engenheiro aprova o PR ◀── Pull Request
```

## Componentes

| Peça | Onde | O quê |
|---|---|---|
| Gerador | `src/gerador/` · job `ecommerce_gerador` | "Sistemas de origem" em arquivos na landing (CDC de pedidos, webhooks, rastreio, CSVs). Escalas XS/S/M/L, data âncora móvel, seed fixa |
| Pipeline | `src/pipeline/` · `ecommerce_pipeline` | Lakeflow Declarative Pipeline (SQL): bronze `b_*` (Auto Loader) → silver `s_*` (AUTO CDC SCD1/SCD2, expectations) |
| Gold | `src/gold/` · job `ecommerce_gold` | 8 metric views `g_*` + `g_funil_diario`. **Sem nada de comprador** (lacuna intencional) |
| Orquestração da base | job `ecommerce_recriar_base` | gerador → pipeline (full refresh) → gold. Escala M: ~30 min |
| Documentos | `src/docs/` → volume `ecommerce.docs` | Contrato de dados, glossário, políticas (PDF) → `s_documentos` via `ai_parse_document` |
| Tools governadas | `src/setup/` · job `agentic_teams_setup` | UC Functions em `agentic_teams`: `buscar_tabelas`, `descrever_tabela`, `listar_documentos`, `ler_documento` |
| LLM | Unity Gateway `fc_catalog.agentic_teams.agentic_teams_llm` | Sonnet 5.5 + fallback Opus 5.5 → GPT-5.5, rate limit, inference table |
| Estado dos agentes | Lakebase `agentic-teams` (schema `agentic_teams`) | execuções, etapas, handoffs, aprovações, testes, artefatos + checkpoints do LangGraph. Consultável no UC pelo catálogo `agentic_teams_lakebase` |
| App | `app/` · app `agentic-teams` | FastAPI + LangGraph. Áreas: Conversa, Time ao vivo, Revisão, Operação |
| Promoção | `src/promover/` · job `agentic_teams_promover_produto` | Pós-merge: sandbox → `ecommerce`, grants para os leitores, publica a metric view no Genie |
| Genie | `genie/estado_limpo.json` | Space "Nuvemshop Commerce (demo)" — a instrução da lacuna fica entre `[LACUNA]...[/LACUNA]` |
| Reset | `scripts/reset_demo.py` | Volta a demo ao estado limpo (sandbox, ecommerce, GitHub, Genie, artefatos). **Arquiva** o histórico no Lakebase (pendentes viram "descartado"); `--apagar-historico` zera tudo |
| Restauração | `scripts/restaurar_historico.py` | Recupera execuções de um branch point-in-time do Lakebase |

Schemas: `ecommerce` (dados), `agentic_teams` (como o time trabalha), `agentic_teams_sandbox` (o que o time produz).

## Como rodar

```bash
databricks bundle deploy                                     # target fevm (profile fevm-fc)
databricks bundle run ecommerce_base --params escala=M        # recria a base inteira (~30 min)
databricks bundle run agentic_setup                           # documentos + UC Functions
databricks bundle run agentic_teams_app                       # sobe o app
uv run --with databricks-sdk --with requests python scripts/reset_demo.py --genie <space_id>   # estado limpo
```

## Roteiro da demo (≈ 12–15 min de agentes; use o "programa de culinária")

1. **Conversa:** "Qual foi o GMV por segmento no último mês?" → Genie responde (mostra que o modelo semântico funciona).
2. **Conversa:** "Qual a taxa de recompra dos compradores nos últimos 90 dias, por categoria?" → Genie diz que não tem → **o time é acionado**.
3. **Time ao vivo:** Supervisor planeja; Discovery lê o catálogo, a linhagem e o **contrato de dados**.
4. **Conversa:** o Analyst pergunta (recompra na categoria? por loja ou plataforma?) → o negócio responde.
5. **Time ao vivo:** Engineer cria no sandbox; **Quality reprova** a identidade (cadastros de convidado sem CPF separam a mesma pessoa:
   ~1,2 M pares loja+e-mail) → Engineer corrige → Quality aprova (22,3 M cadastros → 18,2 M compradores reais).
6. **Revisão:** engenheiro (de preferência alguém da plateia) lê SQL, testes e decisões → **Aprovar e fazer merge**.
7. **Conversa:** Genie responde: **Ração 58%, Petiscos 54%… demais categorias < 19%** — "seus clientes pet voltam 3x mais".
   Contraponto: a conta ingênua (comprador_id cru) diria Ração ~29%.
8. **Operação:** custo/tokens por agente, iterações, decisões humanas; traces no MLflow; inference table do gateway.

Dica: dispare o passo 2 cedo e volte nele; tenha um run concluído de backup (não resete depois do último ensaio).

## Pendências conhecidas

- **GitHub:** o secret `agentic-teams/github_token` nasce com valor provisório → PR **simulado** (artefatos no volume `agentic_teams.artefatos`).
  Para PR real: criar o GitHub App (ver `desenho.md` §9.6) ou, provisoriamente, gravar um token fine-grained só do repo de PR no secret.
  A integração (branch, commit, PR, comentário, merge, promoção lendo da `main`) foi validada com token local.
- **Permissões** (grupos `negocio`, `dados_pii`, `engenharia_dados`, column mask do CPF): adiadas. Hoje o SP do app tem o mínimo para
  funcionar (sem SELECT em `b_*`); o bloqueio de bronze também é aplicado nas tools.
- **Lakehouse Sync (Beta):** configurado e removido — não gerou tabelas e reiniciou o Lakebase. Plano B ativo: catálogo
  `agentic_teams_lakebase` (consulta federada do Lakebase no UC).
- Guardrail de CPF no Unity Gateway e dashboard AI/BI de operação: próximos passos.

Todos os nomes de lojas, marcas e transportadoras são fictícios.
