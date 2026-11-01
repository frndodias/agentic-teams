-- Silver: investimento em mídia unificado (Meta e Google têm schemas diferentes).
-- Meta: a coluna de investimento era amount_spent e passou a se chamar spend.
CREATE OR REFRESH MATERIALIZED VIEW s_investimento_marketing (
  CONSTRAINT investimento_informado EXPECT (investimento IS NOT NULL)
)
COMMENT 'Investimento diário em mídia paga por loja e plataforma (meta, google): valor em R$, impressões e cliques.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  store_ref AS loja_id,
  to_date(date) AS data,
  'meta' AS canal_midia,
  campaign_name AS campanha,
  CAST(coalesce(spend, amount_spent) AS DECIMAL(12,2)) AS investimento,
  CAST(impressions AS BIGINT) AS impressoes,
  CAST(link_clicks AS BIGINT) AS cliques
FROM b_marketing_meta
UNION ALL
SELECT
  store_ref,
  to_date(day),
  'google',
  campaign,
  CAST(CAST(cost_micros AS BIGINT) / 1000000 AS DECIMAL(12,2)),
  CAST(impressions AS BIGINT),
  CAST(clicks AS BIGINT)
FROM b_marketing_google;
