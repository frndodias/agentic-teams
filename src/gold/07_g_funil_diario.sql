CREATE OR REPLACE TABLE {cs}.g_funil_diario
COMMENT 'Funil diário de navegação (últimos 90 dias): sessões que chegaram a cada etapa, por loja, dia, dispositivo e origem.'
TBLPROPERTIES ('camada' = 'gold')
AS SELECT
  loja_id,
  DATE(ts) AS data,
  dispositivo,
  origem_trafego,
  COUNT(DISTINCT sessao_id) AS sessoes,
  COUNT(DISTINCT CASE WHEN tipo = 'view_item' THEN sessao_id END) AS sessoes_produto,
  COUNT(DISTINCT CASE WHEN tipo = 'add_to_cart' THEN sessao_id END) AS sessoes_carrinho,
  COUNT(DISTINCT CASE WHEN tipo = 'begin_checkout' THEN sessao_id END) AS sessoes_checkout,
  COUNT(DISTINCT CASE WHEN tipo = 'purchase' THEN sessao_id END) AS sessoes_compra
FROM {cs}.s_eventos_web
GROUP BY ALL
