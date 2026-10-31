# agentic-teams

Base mock Nuvemshop-like e demo de um **time agêntico de engenharia de dados** no Databricks.

## O que tem aqui

| Pasta | Conteúdo |
|---|---|
| `src/gerador/` | Gerador dos "sistemas de origem": escreve arquivos (JSON/CSV) na landing do Unity Catalog |
| `resources/` | Recursos do bundle: schema `ecommerce`, volumes `landing` e `docs`, job `ecommerce_gerador` |

Próximos: pipeline bronze → silver (`b_*`, `s_*`), gold (`g_*`, metric views), app e agentes.

## Como rodar

Pré-requisitos: Databricks CLI ≥ 0.294 e um profile em `~/.databrickscfg` (o target `fevm` usa o profile `fevm-fc`).

```bash
databricks bundle deploy
databricks bundle run gerador --params escala=M          # S | M | L  (XS só para testar código)
databricks bundle run gerador --params data_ancora=2026-11-11
```

O gerador é determinístico: mesma `seed` + mesma `data_ancora` = mesmos dados.

## Escalas

| Escala | Lojas | Pessoas | Pedidos | Eventos web (90 dias) |
|---|---|---|---|---|
| XS | 50 | ~15k | 30k | ~330k |
| S | 500 | ~510k | 1M | ~11M |
| M | 10k | ~15M | 30M | ~330M |
| L | 50k | ~76M | 150M | ~1,6B |

## Histórias plantadas

H1 sazonalidade (Black Friday, Natal, Dia das Mães) · H2 grupo de fraude em Eletrônicos · H3 churn após
reajuste do plano Inicial · H4 atraso da "Rota Express" no Nordeste · H5 recompra (Pet ~3x, WhatsApp ~2x Ads) ·
H6 Pix x cartão e recusa de madrugada · H7 checkout iOS quebrado · H8 mudança de schema no CSV da Meta.

A lacuna da demo (recompra de compradores) tem armadilhas de propósito: cadastros duplicados, CPF com e sem
máscara, pedidos de teste e a definição de "pedido pago". O gabarito é gravado fora do alcance dos agentes.

Todos os nomes de lojas, marcas e transportadoras são fictícios.
