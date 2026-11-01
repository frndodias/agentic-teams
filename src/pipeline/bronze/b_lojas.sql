-- Bronze: Export do backoffice de lojas (CSV, tudo texto).
CREATE OR REFRESH STREAMING TABLE b_lojas
COMMENT 'Export do backoffice de lojas (CSV, tudo texto). Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/lojas', format => 'csv', header => true, inferColumnTypes => false);
