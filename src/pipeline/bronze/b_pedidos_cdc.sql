-- Bronze: CDC do banco transacional de pedidos (estilo Debezium: op, ts_ms, source, after). Nomes em inglês.
CREATE OR REFRESH STREAMING TABLE b_pedidos_cdc
COMMENT 'CDC do banco transacional de pedidos (estilo Debezium: op, ts_ms, source, after). Nomes em inglês. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/pedidos_cdc', format => 'json');
