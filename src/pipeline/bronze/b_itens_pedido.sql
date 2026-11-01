-- Bronze: Itens dos pedidos do banco transacional. Nomes em inglês.
CREATE OR REFRESH STREAMING TABLE b_itens_pedido
COMMENT 'Itens dos pedidos do banco transacional. Nomes em inglês. Ingestão como chegou da landing.'
TBLPROPERTIES ('camada' = 'bronze')
AS SELECT
  *,
  _metadata.file_path AS _arquivo_origem,
  current_timestamp() AS _ingerido_em
FROM STREAM read_files('${landing}/itens_pedido', format => 'json');
