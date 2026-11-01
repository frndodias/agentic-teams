CREATE OR REPLACE VIEW {cs}.g_suporte
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Atendimento: volume de tickets, tempo de resolução e CSAT por assunto, origem, loja e transportadora do pedido."
  source: {cs}.s_tickets
  joins:
    - name: dim_loja
      source: {cs}.s_lojas
      'on': source.loja_id = dim_loja.loja_id
    - name: dim_envio
      source: {cs}.s_envios
      'on': source.pedido_id = dim_envio.pedido_id
  dimensions:
    - name: Data
      expr: "DATE(source.aberto_em)"
    - name: Mês
      expr: "DATE_TRUNC('MONTH', source.aberto_em)"
    - name: Origem
      expr: source.origem
    - name: Assunto
      expr: source.assunto
    - name: Canal
      expr: source.canal
    - name: Loja
      expr: dim_loja.nome_loja
    - name: Segmento
      expr: dim_loja.segmento
    - name: Transportadora
      expr: dim_envio.transportadora
    - name: UF de Destino
      expr: dim_envio.uf_destino
  measures:
    - name: Tickets
      expr: COUNT(1)
    - name: Tempo Médio de Resolução (h)
      expr: AVG(TIMESTAMPDIFF(MINUTE, source.aberto_em, source.resolvido_em)) / 60.0
    - name: CSAT Médio
      expr: AVG(source.csat)
    - name: Taxa de Resolução
      expr: COUNT(source.resolvido_em) * 1.0 / COUNT(1)
$$
