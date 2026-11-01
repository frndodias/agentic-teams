CREATE OR REPLACE FUNCTION {catalog}.agentic_teams.ler_documento(nome_arquivo STRING)
RETURNS STRING
COMMENT 'Tool do Discovery Agent: texto completo de um documento de negócio.'
RETURN SELECT max(texto) FROM {catalog}.ecommerce.s_documentos WHERE arquivo = nome_arquivo
