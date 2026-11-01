-- Silver: estado final de cada tentativa de pagamento, consolidando os webhooks do gateway.
CREATE OR REFRESH MATERIALIZED VIEW s_pagamentos
COMMENT 'Tentativas de pagamento (uma por linha) no último estado: aprovado, recusado, estornado ou pendente. Um pedido pode ter 2 tentativas (recusa seguida de nova tentativa).'
TBLPROPERTIES ('camada' = 'silver')
AS SELECT
  payment_id AS pagamento_id,
  any_value(order_id) AS pedido_id,
  CASE any_value(method)
    WHEN 'credit_card' THEN 'cartao_credito' WHEN 'debit_card' THEN 'cartao_debito'
    WHEN 'wallet' THEN 'carteira_digital' ELSE any_value(method)
  END AS meio,
  CAST(any_value(installments) AS INT) AS parcelas,
  CAST(any_value(amount) AS DECIMAL(12,2)) AS valor,
  CASE max_by(type, to_timestamp(occurred_at))
    WHEN 'payment.approved' THEN 'aprovado' WHEN 'payment.declined' THEN 'recusado'
    WHEN 'payment.refunded' THEN 'estornado' ELSE 'pendente'
  END AS status,
  max(decline_reason) AS motivo_recusa,
  CAST(any_value(risk_score) AS INT) AS score_antifraude,
  min(to_timestamp(occurred_at)) AS criado_em,
  max(to_timestamp(occurred_at)) AS atualizado_em
FROM b_pagamentos_eventos
GROUP BY payment_id;
