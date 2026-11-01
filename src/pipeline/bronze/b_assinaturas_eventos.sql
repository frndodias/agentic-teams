-- Bronze: Eventos do billing de assinaturas: novo, upgrade, reajuste, cancelamento.
CREATE OR REFRESH STREAMING TABLE b_assinaturas_eventos
COMMENT 'Eventos do billing de assinaturas: novo, upgrade, reajuste, cancelamento. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/assinaturas_eventos', format => 'json');
