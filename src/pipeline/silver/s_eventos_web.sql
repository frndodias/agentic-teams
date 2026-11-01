-- Silver: eventos de navegação com timestamp tipado.
CREATE OR REFRESH STREAMING TABLE s_eventos_web (
  CONSTRAINT ts_obrigatorio EXPECT (ts IS NOT NULL)
)
COMMENT 'Eventos de navegação nas lojas (últimos 90 dias): page_view, view_item, add_to_cart, begin_checkout, purchase. comprador_id nulo = visitante anônimo.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  evento_id,
  sessao_id,
  loja_id,
  comprador_id,
  to_timestamp(ts) AS ts,
  tipo,
  produto_id,
  pedido_id,
  dispositivo,
  origem_trafego,
  utm_campaign
FROM STREAM(b_eventos_web);
