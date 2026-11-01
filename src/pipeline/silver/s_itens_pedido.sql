-- Silver: itens dos pedidos (nomes em inglês -> português).
CREATE OR REFRESH STREAMING TABLE s_itens_pedido (
  CONSTRAINT quantidade_positiva EXPECT (quantidade > 0)
)
COMMENT 'Itens dos pedidos: um produto por linha (pedido_id + item_seq).'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  order_id AS pedido_id,
  CAST(line AS INT) AS item_seq,
  product_id AS produto_id,
  sku,
  CAST(quantity AS INT) AS quantidade,
  CAST(unit_price AS DECIMAL(12,2)) AS preco_unitario,
  CAST(discount AS DECIMAL(12,2)) AS desconto_item,
  to_timestamp(created_at) AS criado_em
FROM STREAM(b_itens_pedido);
