CREATE OR REPLACE VIEW {cs}.g_marketing
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Mídia paga (Meta e Google): investimento, cliques, CPC e ROAS com receita atribuída por origem do pedido."
  source: |
    SELECT m.*, coalesce(r.receita, 0) AS receita_atribuida, coalesce(r.pedidos, 0) AS pedidos_atribuidos
    FROM {cs}.s_investimento_marketing m
    LEFT JOIN (
      SELECT loja_id, DATE(data_hora_pedido) AS data,
             CASE origem_trafego WHEN 'ads_meta' THEN 'meta' WHEN 'ads_google' THEN 'google' END AS canal_midia,
             SUM(valor_total) AS receita, COUNT(1) AS pedidos
      FROM {cs}.s_pedidos
      WHERE origem_trafego IN ('ads_meta', 'ads_google') AND status_pedido NOT IN ('cancelado', 'pendente')
      GROUP BY ALL
    ) r ON m.loja_id = r.loja_id AND m.data = r.data AND m.canal_midia = r.canal_midia
  joins:
    - name: dim_loja
      source: {cs}.s_lojas
      'on': source.loja_id = dim_loja.loja_id
  dimensions:
    - name: Data
      expr: source.data
    - name: Mês
      expr: "DATE_TRUNC('MONTH', source.data)"
    - name: Plataforma
      expr: "CASE source.canal_midia WHEN 'meta' THEN 'Meta' WHEN 'google' THEN 'Google' ELSE source.canal_midia END"
    - name: Campanha
      expr: source.campanha
    - name: Loja
      expr: dim_loja.nome_loja
    - name: Segmento
      expr: dim_loja.segmento
  measures:
    - name: Investimento
      expr: SUM(source.investimento)
    - name: Impressões
      expr: SUM(source.impressoes)
    - name: Cliques
      expr: SUM(source.cliques)
    - name: Receita Atribuída
      expr: SUM(source.receita_atribuida)
    - name: CPC
      expr: "MEASURE(`Investimento`) / NULLIF(MEASURE(`Cliques`), 0)"
    - name: ROAS
      expr: "MEASURE(`Receita Atribuída`) / NULLIF(MEASURE(`Investimento`), 0)"
$$
