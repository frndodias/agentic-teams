-- Bronze: Eventos de navegação da loja (últimos 90 dias).
CREATE OR REFRESH STREAMING TABLE b_eventos_web
COMMENT 'Eventos de navegação da loja (últimos 90 dias). Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/eventos_web', format => 'json');
