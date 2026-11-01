-- Bronze: Export diário da Meta Ads (CSV). A coluna de investimento mudou de nome ao longo do tempo.
CREATE OR REFRESH STREAMING TABLE b_marketing_meta
COMMENT 'Export diário da Meta Ads (CSV). A coluna de investimento mudou de nome ao longo do tempo. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/marketing_meta', format => 'csv', header => true, inferColumnTypes => false,
  schemaHints => 'amount_spent STRING, spend STRING');
