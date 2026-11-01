-- Bronze: Catálogo de produtos das lojas.
CREATE OR REFRESH STREAMING TABLE b_produtos
COMMENT 'Catálogo de produtos das lojas. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/produtos', format => 'json');
