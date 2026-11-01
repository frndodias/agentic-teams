-- Bronze: Export diário do Google Ads (CSV, custo em micros).
CREATE OR REFRESH STREAMING TABLE b_marketing_google
COMMENT 'Export diário do Google Ads (CSV, custo em micros). Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/marketing_google', format => 'csv', header => true, inferColumnTypes => false);
