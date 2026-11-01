-- Bronze: Eventos de disputas: chargeback (cartão) e MED (Pix).
CREATE OR REFRESH STREAMING TABLE b_disputas_eventos
COMMENT 'Eventos de disputas: chargeback (cartão) e MED (Pix). Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/disputas_eventos', format => 'json');
