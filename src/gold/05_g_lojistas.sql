CREATE OR REPLACE VIEW {cs}.g_lojistas
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Base de lojistas: lojas ativas, churn e MRR por plano, segmento e localização. Plano = último plano da loja."
  source: |
    SELECT l.*, a.plano, a.preco_mensal
    FROM {cs}.s_lojas l
    LEFT JOIN (
      SELECT loja_id, max_by(plano, inicio) AS plano, max_by(preco_mensal, inicio) AS preco_mensal
      FROM {cs}.s_assinaturas GROUP BY loja_id
    ) a ON l.loja_id = a.loja_id
  dimensions:
    - name: Segmento
      expr: segmento
    - name: Tier
      expr: tier
    - name: Plano
      expr: plano
    - name: UF
      expr: uf
    - name: Região
      expr: regiao
    - name: Status
      expr: status
    - name: Mês de Abertura
      expr: "DATE_TRUNC('MONTH', data_abertura)"
    - name: Mês do Churn
      expr: "DATE_TRUNC('MONTH', data_churn)"
  measures:
    - name: Lojas
      expr: COUNT(1)
    - name: Lojas Ativas
      expr: COUNT(1) FILTER (WHERE status = 'ativa')
    - name: Lojas que Cancelaram
      expr: COUNT(1) FILTER (WHERE status = 'inativa')
    - name: Taxa de Churn
      expr: "MEASURE(`Lojas que Cancelaram`) * 1.0 / MEASURE(`Lojas`)"
    - name: MRR
      expr: SUM(preco_mensal) FILTER (WHERE status = 'ativa')
      comment: "Receita mensal recorrente das assinaturas ativas"
$$
