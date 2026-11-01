-- Silver: pedidos a partir do CDC do banco transacional (nomes em inglês -> português).
-- s_pedidos = estado atual (SCD1); s_pedidos_historico = cada mudança de status (SCD2).
CREATE TEMPORARY VIEW v_pedidos_cdc AS
SELECT
  after.id AS pedido_id,
  after.store_id AS loja_id,
  after.customer_id AS comprador_id,
  to_timestamp(after.created_at) AS data_hora_pedido,
  after.channel AS canal,
  after.traffic_source AS origem_trafego,
  after.device AS dispositivo,
  after.coupon_code AS cupom,
  CAST(after.subtotal AS DECIMAL(12,2)) AS valor_produtos,
  CAST(after.discount AS DECIMAL(12,2)) AS desconto,
  CAST(after.shipping_cost AS DECIMAL(12,2)) AS frete,
  CAST(after.total AS DECIMAL(12,2)) AS valor_total,
  CASE after.status
    WHEN 'pending' THEN 'pendente' WHEN 'paid' THEN 'pago' WHEN 'shipped' THEN 'enviado'
    WHEN 'delivered' THEN 'entregue' WHEN 'cancelled' THEN 'cancelado' WHEN 'returned' THEN 'devolvido'
  END AS status_pedido,
  to_timestamp(after.updated_at) AS status_atualizado_em,
  ts_ms
FROM STREAM(b_pedidos_cdc);

CREATE OR REFRESH STREAMING TABLE s_pedidos
COMMENT 'Pedidos no estado atual (um por pedido). status_pedido: pendente, pago, enviado, entregue, cancelado, devolvido. valor_total = valor_produtos - desconto + frete.'
TBLPROPERTIES ('camada' = 'silver');

CREATE FLOW f_s_pedidos AS AUTO CDC INTO s_pedidos
FROM STREAM(v_pedidos_cdc)
KEYS (pedido_id)
SEQUENCE BY ts_ms
COLUMNS * EXCEPT (ts_ms)
STORED AS SCD TYPE 1;

CREATE OR REFRESH STREAMING TABLE s_pedidos_historico
COMMENT 'Histórico de status dos pedidos (SCD tipo 2): uma linha por versão; __START_AT/__END_AT delimitam a vigência (versão atual: __END_AT IS NULL).'
TBLPROPERTIES ('camada' = 'silver');

CREATE FLOW f_s_pedidos_historico AS AUTO CDC INTO s_pedidos_historico
FROM STREAM(v_pedidos_cdc)
KEYS (pedido_id)
SEQUENCE BY ts_ms
COLUMNS * EXCEPT (ts_ms)
STORED AS SCD TYPE 2
TRACK HISTORY ON status_pedido;
