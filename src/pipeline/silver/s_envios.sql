-- Silver: um envio por linha, consolidando os eventos de rastreio.
CREATE OR REFRESH MATERIALIZED VIEW s_envios
COMMENT 'Envios dos pedidos: transportadora, destino, prazo prometido, datas de postagem/entrega e último status (postado, em_transito, saiu_para_entrega, entregue, extraviado).'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  envio_id,
  any_value(pedido_id) AS pedido_id,
  any_value(transportadora) AS transportadora,
  any_value(codigo_rastreio) AS codigo_rastreio,
  any_value(cep_destino) AS cep_destino,
  any_value(uf_destino) AS uf_destino,
  CAST(any_value(prazo_prometido_dias) AS INT) AS prazo_prometido_dias,
  to_timestamp(any_value(data_postagem)) AS data_postagem,
  to_date(any_value(data_entrega_prevista)) AS data_entrega_prevista,
  max(CASE WHEN evento = 'entregue' THEN to_timestamp(ocorrido_em) END) AS data_entrega,
  max_by(evento, to_timestamp(ocorrido_em)) AS status_envio,
  CAST(any_value(custo_frete) AS DECIMAL(12,2)) AS custo_frete
FROM b_envios_eventos
GROUP BY envio_id;
