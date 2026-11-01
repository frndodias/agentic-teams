CREATE OR REPLACE VIEW {cs}.g_pedidos
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Pedidos (um por pedido): GMV total com frete e desconto, ticket médio, cancelamento, devolução e disputas por loja, canal e tempo."
  source: {cs}.s_pedidos
  joins:
    - name: dim_loja
      source: {cs}.s_lojas
      'on': source.loja_id = dim_loja.loja_id
    - name: dim_disputa
      source: {cs}.s_disputas
      'on': source.pedido_id = dim_disputa.pedido_id
  dimensions:
    - name: Data
      expr: "DATE(source.data_hora_pedido)"
    - name: Mês
      expr: "DATE_TRUNC('MONTH', source.data_hora_pedido)"
    - name: Ano
      expr: "YEAR(source.data_hora_pedido)"
    - name: Hora do Dia
      expr: "HOUR(source.data_hora_pedido)"
    - name: Loja
      expr: dim_loja.nome_loja
    - name: ID Loja
      expr: source.loja_id
    - name: Segmento
      expr: dim_loja.segmento
    - name: UF da Loja
      expr: dim_loja.uf
    - name: Região da Loja
      expr: dim_loja.regiao
    - name: Tier
      expr: dim_loja.tier
    - name: Canal
      expr: source.canal
    - name: Origem do Tráfego
      expr: source.origem_trafego
    - name: Dispositivo
      expr: source.dispositivo
    - name: Status do Pedido
      expr: source.status_pedido
    - name: Usou Cupom
      expr: "source.cupom IS NOT NULL"
  measures:
    - name: Pedidos Criados
      expr: COUNT(1)
    - name: Pedidos
      expr: COUNT(1) FILTER (WHERE source.status_pedido NOT IN ('cancelado', 'pendente'))
      comment: "Pedidos válidos (exclui cancelados e pendentes)"
    - name: GMV Total
      expr: SUM(source.valor_total) FILTER (WHERE source.status_pedido NOT IN ('cancelado', 'pendente'))
      comment: "valor_total = produtos - desconto + frete, só pedidos válidos"
    - name: Frete
      expr: SUM(source.frete) FILTER (WHERE source.status_pedido NOT IN ('cancelado', 'pendente'))
    - name: Descontos
      expr: SUM(source.desconto) FILTER (WHERE source.status_pedido NOT IN ('cancelado', 'pendente'))
    - name: Ticket Médio
      expr: "MEASURE(`GMV Total`) / MEASURE(`Pedidos`)"
    - name: Taxa de Cancelamento
      expr: COUNT(1) FILTER (WHERE source.status_pedido = 'cancelado') * 1.0 / COUNT(1)
    - name: Taxa de Devolução
      expr: COUNT(1) FILTER (WHERE source.status_pedido = 'devolvido') * 1.0 / NULLIF(COUNT(1) FILTER (WHERE source.status_pedido IN ('entregue', 'devolvido')), 0)
    - name: Pedidos com Chargeback
      expr: COUNT(1) FILTER (WHERE dim_disputa.tipo = 'chargeback')
    - name: Taxa de Chargeback
      expr: COUNT(1) FILTER (WHERE dim_disputa.tipo = 'chargeback') * 1.0 / NULLIF(MEASURE(`Pedidos`), 0)
      comment: "Pedidos com chargeback sobre pedidos válidos"
$$
