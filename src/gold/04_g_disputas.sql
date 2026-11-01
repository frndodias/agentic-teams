CREATE OR REPLACE VIEW {cs}.g_disputas
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Disputas de pagamento (chargeback no cartão e MED no Pix): volume, valor, motivo e resultado."
  source: {cs}.s_disputas
  joins:
    - name: dim_pedido
      source: {cs}.s_pedidos
      'on': source.pedido_id = dim_pedido.pedido_id
      joins:
        - name: dim_loja
          source: {cs}.s_lojas
          'on': dim_pedido.loja_id = dim_loja.loja_id
  dimensions:
    - name: Mês de Abertura
      expr: "DATE_TRUNC('MONTH', source.data_abertura)"
    - name: Data de Abertura
      expr: "DATE(source.data_abertura)"
    - name: Tipo
      expr: source.tipo
    - name: Motivo
      expr: source.motivo
    - name: Status
      expr: source.status
    - name: Loja
      expr: dim_pedido.dim_loja.nome_loja
    - name: ID Loja
      expr: dim_pedido.loja_id
    - name: Segmento
      expr: dim_pedido.dim_loja.segmento
    - name: UF da Loja
      expr: dim_pedido.dim_loja.uf
  measures:
    - name: Disputas
      expr: COUNT(1)
    - name: Valor Disputado
      expr: SUM(source.valor)
    - name: Disputas Perdidas
      expr: COUNT(1) FILTER (WHERE source.status = 'perdida')
    - name: Valor Perdido
      expr: SUM(source.valor) FILTER (WHERE source.status = 'perdida')
    - name: Win Rate
      expr: COUNT(1) FILTER (WHERE source.status = 'ganha') * 1.0 / NULLIF(COUNT(1) FILTER (WHERE source.status IN ('ganha', 'perdida')), 0)
$$
