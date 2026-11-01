-- Silver: uma disputa por linha (chargeback ou MED), consolidando os eventos do adquirente.
CREATE OR REFRESH MATERIALIZED VIEW s_disputas
COMMENT 'Disputas de pagamento: tipo (chargeback no cartão / MED no Pix), motivo, valor, status (aberta, em_analise, ganha, perdida) e datas.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  disputa_id,
  any_value(pedido_id) AS pedido_id,
  any_value(pagamento_id) AS pagamento_id,
  any_value(tipo) AS tipo,
  any_value(motivo) AS motivo,
  CAST(any_value(valor) AS DECIMAL(12,2)) AS valor,
  min(CASE WHEN evento = 'aberta' THEN to_timestamp(ocorrido_em) END) AS data_abertura,
  max_by(evento, to_timestamp(ocorrido_em)) AS status,
  max(CASE WHEN evento IN ('ganha', 'perdida') THEN to_timestamp(ocorrido_em) END) AS data_resolucao
FROM b_disputas_eventos
GROUP BY disputa_id;
