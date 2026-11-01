-- Silver: cadastros de clientes por loja. Só tipagem: a silver NÃO unifica identidade
-- (e-mail/CPF continuam como vieram). Unificar compradores é regra de negócio, fora desta camada.
CREATE OR REFRESH MATERIALIZED VIEW s_compradores (
  CONSTRAINT comprador_id_obrigatorio EXPECT (comprador_id IS NOT NULL)
)
COMMENT 'Cadastros de compradores por loja (cliente da loja: loja_id + comprador_id). A mesma pessoa pode ter mais de um cadastro (conta e convidado) e cadastros em várias lojas. CPF é dado pessoal.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  CAST(comprador_id AS BIGINT) AS comprador_id,
  loja_id,
  nome,
  email,
  cpf,
  telefone,
  cep,
  cidade,
  uf,
  to_date(data_cadastro) AS data_cadastro,
  tipo_cadastro,
  canal_aquisicao
FROM b_compradores;
