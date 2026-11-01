CREATE OR REPLACE FUNCTION {catalog}.agentic_teams.listar_documentos()
RETURNS TABLE (arquivo STRING, caracteres INT)
COMMENT 'Tool do Discovery Agent: lista os documentos de negócio disponíveis (contrato de dados, glossário, políticas).'
RETURN SELECT arquivo, length(texto) FROM {catalog}.ecommerce.s_documentos ORDER BY arquivo
