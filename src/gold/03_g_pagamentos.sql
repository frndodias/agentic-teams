CREATE OR REPLACE VIEW {cs}.g_pagamentos
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Tentativas de pagamento: aprovação, recusas por motivo, mix de meios (Pix, cartão, boleto) e parcelamento."
  source: {cs}.s_pagamentos
  joins:
    - name: dim_pedido
      source: {cs}.s_pedidos
      'on': source.pedido_id = dim_pedido.pedido_id
      joins:
        - name: dim_loja
          source: {cs}.s_lojas
          'on': dim_pedido.loja_id = dim_loja.loja_id
  dimensions:
    - name: Data
      expr: "DATE(source.criado_em)"
    - name: Mês
      expr: "DATE_TRUNC('MONTH', source.criado_em)"
    - name: Hora do Dia
      expr: "HOUR(source.criado_em)"
    - name: Meio de Pagamento
      expr: "CASE source.meio WHEN 'pix' THEN 'Pix' WHEN 'cartao_credito' THEN 'Cartão de crédito' WHEN 'cartao_debito' THEN 'Cartão de débito' WHEN 'boleto' THEN 'Boleto' WHEN 'carteira_digital' THEN 'Carteira digital' ELSE source.meio END"
    - name: Status do Pagamento
      expr: "INITCAP(source.status)"
    - name: Motivo da Recusa
      expr: source.motivo_recusa
    - name: Parcelas
      expr: source.parcelas
    - name: Segmento
      expr: dim_pedido.dim_loja.segmento
    - name: Loja
      expr: dim_pedido.dim_loja.nome_loja
    - name: Canal
      expr: dim_pedido.canal
  measures:
    - name: Tentativas
      expr: COUNT(1)
    - name: Aprovadas
      expr: COUNT(1) FILTER (WHERE source.status IN ('aprovado', 'estornado'))
    - name: Recusadas
      expr: COUNT(1) FILTER (WHERE source.status = 'recusado')
    - name: Taxa de Aprovação
      expr: "MEASURE(`Aprovadas`) * 1.0 / MEASURE(`Tentativas`)"
    - name: Valor Aprovado
      expr: SUM(source.valor) FILTER (WHERE source.status IN ('aprovado', 'estornado'))
    - name: Parcelamento Médio
      expr: AVG(source.parcelas) FILTER (WHERE source.meio = 'cartao_credito')
$$
