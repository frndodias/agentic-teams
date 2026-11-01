CREATE OR REPLACE FUNCTION {catalog}.agentic_teams.descrever_tabela(nome STRING)
RETURNS TABLE (coluna STRING, tipo STRING, comentario STRING)
COMMENT 'Tool do Discovery Agent: colunas, tipos e comentários de uma tabela (nome completo catalogo.schema.tabela).'
RETURN
  SELECT column_name, full_data_type, comment
  FROM {catalog}.information_schema.columns
  WHERE concat_ws('.', table_catalog, table_schema, table_name) = nome
  ORDER BY ordinal_position
