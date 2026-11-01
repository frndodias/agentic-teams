-- Silver: snapshot atual de estoque.
CREATE OR REFRESH MATERIALIZED VIEW s_estoque
COMMENT 'Estoque atual por SKU (snapshot). quantidade = 0 indica ruptura.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  produto_id,
  loja_id,
  CAST(quantidade AS INT) AS quantidade,
  to_timestamp(atualizado_em) AS atualizado_em
FROM b_estoque;
