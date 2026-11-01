-- Silver: catálogo de produtos (SKU por loja).
CREATE OR REFRESH MATERIALIZED VIEW s_produtos (
  CONSTRAINT preco_positivo EXPECT (preco > 0)
)
COMMENT 'Catálogo de produtos das lojas: um SKU por linha, com categoria, marca, preço e custo.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  produto_id,
  loja_id,
  sku,
  nome,
  categoria,
  subcategoria,
  marca,
  CAST(preco AS DECIMAL(12,2)) AS preco,
  CAST(custo AS DECIMAL(12,2)) AS custo,
  CAST(peso_g AS INT) AS peso_g,
  CAST(ativo AS BOOLEAN) AS ativo,
  to_date(data_criacao) AS data_criacao
FROM b_produtos;
