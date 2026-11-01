CREATE OR REPLACE VIEW {cs}.g_funil
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Funil de conversão das lojas (últimos 90 dias): sessões, conversão por etapa e abandono de carrinho/checkout."
  source: {cs}.g_funil_diario
  joins:
    - name: dim_loja
      source: {cs}.s_lojas
      'on': source.loja_id = dim_loja.loja_id
  dimensions:
    - name: Data
      expr: source.data
    - name: Dispositivo
      expr: "CASE source.dispositivo WHEN 'ios' THEN 'iOS' WHEN 'android' THEN 'Android' WHEN 'desktop' THEN 'Desktop' ELSE source.dispositivo END"
    - name: Origem do Tráfego
      expr: "CASE source.origem_trafego WHEN 'organico' THEN 'Busca orgânica' WHEN 'direto' THEN 'Direto' WHEN 'email' THEN 'E-mail' WHEN 'ads_meta' THEN 'Anúncios Meta' WHEN 'ads_google' THEN 'Anúncios Google' WHEN 'whatsapp' THEN 'WhatsApp' WHEN 'social' THEN 'Redes sociais' WHEN 'marketplace' THEN 'Marketplace' ELSE source.origem_trafego END"
    - name: Loja
      expr: dim_loja.nome_loja
    - name: Segmento
      expr: dim_loja.segmento
  measures:
    - name: Sessões
      expr: SUM(source.sessoes)
    - name: Sessões com Carrinho
      expr: SUM(source.sessoes_carrinho)
    - name: Sessões com Checkout
      expr: SUM(source.sessoes_checkout)
    - name: Sessões com Compra
      expr: SUM(source.sessoes_compra)
    - name: Taxa de Conversão
      expr: "MEASURE(`Sessões com Compra`) * 1.0 / MEASURE(`Sessões`)"
    - name: Conversão do Checkout
      expr: "MEASURE(`Sessões com Compra`) * 1.0 / MEASURE(`Sessões com Checkout`)"
      comment: "Das sessões que iniciaram o checkout, quantas compraram"
    - name: Abandono de Carrinho
      expr: "1 - MEASURE(`Sessões com Compra`) * 1.0 / MEASURE(`Sessões com Carrinho`)"
$$
