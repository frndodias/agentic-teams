-- Bronze: Webhooks do gateway de pagamento (payment.created/approved/declined/refunded). Nomes em inglês.
CREATE OR REFRESH STREAMING TABLE b_pagamentos_eventos
COMMENT 'Webhooks do gateway de pagamento (payment.created/approved/declined/refunded). Nomes em inglês. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/pagamentos_eventos', format => 'json');
