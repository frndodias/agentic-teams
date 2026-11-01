CREATE OR REPLACE VIEW {cs}.g_vendas
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Vendas no nível de item: GMV de produtos por categoria, marca, loja, canal e tempo. Use para perguntas de vendas por produto/categoria."
  source: {cs}.s_itens_pedido
  joins:
    - name: dim_pedido
      source: {cs}.s_pedidos
      'on': source.pedido_id = dim_pedido.pedido_id
      joins:
        - name: dim_loja
          source: {cs}.s_lojas
          'on': dim_pedido.loja_id = dim_loja.loja_id
    - name: dim_produto
      source: {cs}.s_produtos
      'on': source.produto_id = dim_produto.produto_id
  dimensions:
    - name: Data
      expr: "DATE(dim_pedido.data_hora_pedido)"
    - name: Mês
      expr: "DATE_TRUNC('MONTH', dim_pedido.data_hora_pedido)"
    - name: Ano
      expr: "YEAR(dim_pedido.data_hora_pedido)"
    - name: Dia da Semana
      expr: "DATE_FORMAT(dim_pedido.data_hora_pedido, 'EEEE')"
    - name: Loja
      expr: dim_pedido.dim_loja.nome_loja
    - name: ID Loja
      expr: dim_pedido.loja_id
    - name: Segmento
      expr: dim_pedido.dim_loja.segmento
    - name: UF da Loja
      expr: dim_pedido.dim_loja.uf
    - name: Região da Loja
      expr: dim_pedido.dim_loja.regiao
    - name: Tier
      expr: dim_pedido.dim_loja.tier
    - name: Categoria
      expr: dim_produto.categoria
    - name: Subcategoria
      expr: dim_produto.subcategoria
    - name: Marca
      expr: dim_produto.marca
    - name: Canal
      expr: dim_pedido.canal
    - name: Origem do Tráfego
      expr: "CASE dim_pedido.origem_trafego WHEN 'organico' THEN 'Busca orgânica' WHEN 'direto' THEN 'Direto' WHEN 'email' THEN 'E-mail' WHEN 'ads_meta' THEN 'Anúncios Meta' WHEN 'ads_google' THEN 'Anúncios Google' WHEN 'whatsapp' THEN 'WhatsApp' WHEN 'social' THEN 'Redes sociais' WHEN 'marketplace' THEN 'Marketplace' ELSE dim_pedido.origem_trafego END"
    - name: Dispositivo
      expr: "CASE dim_pedido.dispositivo WHEN 'ios' THEN 'iOS' WHEN 'android' THEN 'Android' WHEN 'desktop' THEN 'Desktop' ELSE dim_pedido.dispositivo END"
    - name: Status do Pedido
      expr: "INITCAP(dim_pedido.status_pedido)"
  measures:
    - name: GMV Bruto
      expr: SUM(source.quantidade * source.preco_unitario - source.desconto_item)
      comment: "Valor dos itens de todos os pedidos, inclusive cancelados e pendentes"
    - name: GMV
      expr: SUM(source.quantidade * source.preco_unitario - source.desconto_item) FILTER (WHERE dim_pedido.status_pedido NOT IN ('cancelado', 'pendente'))
      comment: "Valor dos itens dos pedidos válidos (exclui cancelados e pendentes)"
    - name: Itens Vendidos
      expr: SUM(source.quantidade) FILTER (WHERE dim_pedido.status_pedido NOT IN ('cancelado', 'pendente'))
    - name: Pedidos
      expr: COUNT(DISTINCT source.pedido_id) FILTER (WHERE dim_pedido.status_pedido NOT IN ('cancelado', 'pendente'))
    - name: Ticket Médio de Produtos
      expr: "MEASURE(`GMV`) / MEASURE(`Pedidos`)"
$$
