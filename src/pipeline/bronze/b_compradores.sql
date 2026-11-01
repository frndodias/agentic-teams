-- Bronze: Export de clientes das lojas (CSV, tudo texto). Contém CPF: dado pessoal.
CREATE OR REFRESH STREAMING TABLE b_compradores
COMMENT 'Export de clientes das lojas (CSV, tudo texto). Contém CPF: dado pessoal. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/compradores', format => 'csv', header => true, inferColumnTypes => false);
