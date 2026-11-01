-- Silver: períodos de plano por loja, montados a partir dos eventos de billing.
CREATE OR REFRESH MATERIALIZED VIEW s_assinaturas
COMMENT 'Histórico de assinatura das lojas: um período por plano/preço vigente (inicio a fim). tipo_mudanca = novo, upgrade ou reajuste; fim preenchido quando houve nova mudança ou cancelamento.'
TBLPROPERTIES ('camada' = 'silver')
AS WITH ev AS (
  SELECT loja_id, tipo, plano, preco_mensal, to_timestamp(ocorrido_em) AS ts
  FROM b_assinaturas_eventos
),
seq AS (
  SELECT *, lead(ts) OVER (PARTITION BY loja_id ORDER BY ts) AS proximo_ts
  FROM ev
)
SELECT
  loja_id,
  plano,
  CAST(preco_mensal AS DECIMAL(10,2)) AS preco_mensal,
  ts AS inicio,
  proximo_ts AS fim,
  tipo AS tipo_mudanca
FROM seq
WHERE tipo <> 'cancelamento';
