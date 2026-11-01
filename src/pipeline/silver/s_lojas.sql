-- Silver: lojas (sellers) com tipos corretos e região derivada da UF.
CREATE OR REFRESH MATERIALIZED VIEW s_lojas (
  CONSTRAINT loja_id_obrigatorio EXPECT (loja_id IS NOT NULL)
)
COMMENT 'Lojas (sellers) da plataforma: segmento, localização, tier e status (ativa/inativa). Uma linha por loja.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  loja_id,
  nome_loja,
  segmento,
  subsegmento,
  uf,
  cidade,
  CASE
    WHEN uf IN ('SP','RJ','MG','ES') THEN 'Sudeste'
    WHEN uf IN ('PR','SC','RS') THEN 'Sul'
    WHEN uf IN ('DF','GO','MT','MS') THEN 'Centro-Oeste'
    WHEN uf IN ('AM','PA','AC','RO','RR','AP','TO') THEN 'Norte'
    ELSE 'Nordeste'
  END AS regiao,
  tier,
  to_date(data_abertura) AS data_abertura,
  status,
  to_date(data_churn) AS data_churn
FROM b_lojas;
