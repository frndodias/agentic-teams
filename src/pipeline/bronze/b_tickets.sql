-- Bronze: Tickets da ferramenta de atendimento (comprador->loja e lojista->plataforma).
CREATE OR REFRESH STREAMING TABLE b_tickets
COMMENT 'Tickets da ferramenta de atendimento (comprador->loja e lojista->plataforma). Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/tickets', format => 'json');
