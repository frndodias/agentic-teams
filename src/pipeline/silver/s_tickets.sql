-- Silver: tickets de atendimento com datas tipadas.
CREATE OR REFRESH MATERIALIZED VIEW s_tickets
COMMENT 'Tickets de atendimento. origem: comprador_loja (cliente final falando com a loja) ou lojista_plataforma (lojista falando com a plataforma). texto = mensagem livre do cliente.'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  ticket_id,
  origem,
  loja_id,
  pedido_id,
  canal,
  assunto,
  texto,
  to_timestamp(aberto_em) AS aberto_em,
  to_timestamp(resolvido_em) AS resolvido_em,
  CAST(csat AS INT) AS csat
FROM b_tickets;
