-- Bronze: Snapshot de estoque por SKU (CSV, tudo texto).
CREATE OR REFRESH STREAMING TABLE b_estoque
COMMENT 'Snapshot de estoque por SKU (CSV, tudo texto). Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/estoque', format => 'csv', header => true, inferColumnTypes => false);
