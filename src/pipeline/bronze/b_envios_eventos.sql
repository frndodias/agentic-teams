-- Bronze: Eventos de rastreio das transportadoras.
CREATE OR REFRESH STREAMING TABLE b_envios_eventos
COMMENT 'Eventos de rastreio das transportadoras. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/envios_eventos', format => 'json');
