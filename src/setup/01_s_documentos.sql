CREATE OR REPLACE TABLE {catalog}.ecommerce.s_documentos
COMMENT 'Documentos de negócio (contrato de dados, glossário, políticas, manual) convertidos em texto com ai_parse_document. Um documento por linha.'
TBLPROPERTIES ('camada' = 'silver')
AS WITH p AS (
  SELECT path, ai_parse_document(content) AS doc
  FROM read_files('/Volumes/{catalog}/ecommerce/docs/', format => 'binaryFile')
)
SELECT
  regexp_extract(path, '([^/]+)$', 1) AS arquivo,
  concat_ws('\n', transform(CAST(doc:document:elements AS ARRAY<VARIANT>), e -> CAST(e:content AS STRING))) AS texto,
  current_timestamp() AS processado_em
FROM p
