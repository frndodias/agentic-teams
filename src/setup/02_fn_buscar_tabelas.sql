CREATE OR REPLACE FUNCTION {catalog}.agentic_teams.buscar_tabelas(termo STRING)
RETURNS TABLE (tabela STRING, tipo STRING, comentario STRING)
COMMENT 'Tool do Discovery Agent: procura tabelas e metric views nos schemas de dados pelo nome ou pelo comentário. termo vazio lista tudo.'
RETURN
  SELECT concat_ws('.', table_catalog, table_schema, table_name), table_type, comment
  FROM {catalog}.information_schema.tables
  WHERE table_schema IN ('ecommerce', 'agentic_teams_sandbox')
    AND (coalesce(termo, '') = ''
         OR lower(table_name) LIKE concat('%', lower(termo), '%')
         OR lower(coalesce(comment, '')) LIKE concat('%', lower(termo), '%'))
  ORDER BY table_schema, table_name
