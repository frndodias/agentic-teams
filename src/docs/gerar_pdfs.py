"""Gera os PDFs do volume ecommerce.docs (fictícios, para a base mock).

uv run --with reportlab python src/docs/gerar_pdfs.py <pasta_saida>
"""
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

DOCS = {
    "contrato_de_dados_pedidos_e_compradores.pdf": {
        "titulo": "Contrato de Dados — Pedidos e Compradores",
        "subtitulo": "Domínio: Commerce · Dono: Time de Dados de Commerce · Versão 2.3",
        "secoes": [
            ("1. Objetivo", [
                "Este contrato define as regras de negócio oficiais para uso dos dados de pedidos e compradores "
                "das lojas da plataforma. Toda métrica publicada na camada gold deve seguir estas definições.",
            ]),
            ("2. Fontes e tabelas", [
                ["ecommerce.s_pedidos — estado atual de cada pedido (um por pedido).",
                 "ecommerce.s_itens_pedido — itens de cada pedido.",
                 "ecommerce.s_pagamentos — tentativas de pagamento (um pedido pode ter mais de uma).",
                 "ecommerce.s_disputas — chargebacks (cartão) e MED (Pix).",
                 "ecommerce.s_compradores — cadastros de clientes das lojas.",
                 "Tabelas b_* (bronze) não devem ser usadas para métricas: contêm dado bruto e dado pessoal em claro."],
            ]),
            ("3. Pedido pago (pedido válido para métricas de cliente)", [
                "Um pedido é considerado PAGO quando, cumulativamente:",
                ["possui ao menos uma tentativa de pagamento aprovada (status aprovado ou estornado em s_pagamentos);",
                 "o status_pedido NÃO é 'cancelado' nem 'pendente';",
                 "NÃO possui disputa do tipo chargeback com status 'perdida'."],
                "Pedidos devolvidos continuam contando como pedidos pagos (a compra aconteceu).",
            ]),
            ("4. Pedido de teste", [
                "Lojistas costumam fazer pedidos de teste ao configurar a loja. Esses pedidos DEVEM ser excluídos "
                "de qualquer métrica de vendas ou de comportamento de compradores. Considere pedido de teste quando:",
                ["valor_total for menor ou igual a R$ 1,00; ou",
                 "o nome ou o e-mail do comprador contiver 'teste' ou 'test' (sem diferenciar maiúsculas)."],
            ]),
            ("5. Comprador e identidade", [
                "O cadastro de comprador é POR LOJA: a mesma pessoa que compra em duas lojas tem dois cadastros "
                "(comprador_id diferentes). Dentro de uma mesma loja, a mesma pessoa também pode ter mais de um "
                "cadastro (ex.: compra com conta e depois como convidado).",
                "Regra oficial de identidade dentro da loja (resolução de identidade):",
                ["chave primária: CPF normalizado (somente dígitos);",
                 "na ausência de CPF: e-mail normalizado (sem espaços nas pontas e em minúsculas);",
                 "cadastros com a mesma chave na mesma loja representam o MESMO comprador."],
                "Métricas de comprador (ativos, recorrentes, recompra) são calculadas por loja, salvo pedido "
                "explícito da área de negócio para a visão consolidada da plataforma.",
            ]),
            ("6. Dados pessoais (LGPD)", [
                ["CPF, e-mail, telefone e nome são dados pessoais.",
                 "CPF em claro só é visível ao grupo dados_pii; os demais veem o hash (SHA-256 do CPF normalizado).",
                 "Produtos de dados na gold NÃO podem expor dado pessoal: publicar apenas agregados ou chaves anonimizadas.",
                 "Agentes e processos automáticos só podem usar a versão com hash."],
            ]),
            ("7. Qualidade mínima esperada", [
                ["s_pedidos: pedido_id único; valor_total = valor_produtos - desconto + frete.",
                 "s_itens_pedido: todo item referencia um pedido existente.",
                 "Métricas de comprador: um comprador unificado conta uma única vez por loja."],
            ]),
        ],
    },
    "glossario_de_metricas.pdf": {
        "titulo": "Glossário de Métricas — Commerce",
        "subtitulo": "Definições oficiais usadas nos dashboards, no Genie e nas metric views (g_*)",
        "tabela": [
            ["Métrica", "Definição"],
            ["GMV", "Soma do valor dos itens dos pedidos válidos (exclui cancelados e pendentes)."],
            ["GMV Total", "Soma de valor_total (produtos - desconto + frete) dos pedidos válidos."],
            ["Ticket Médio", "GMV Total / número de pedidos válidos."],
            ["Taxa de Cancelamento", "Pedidos cancelados / pedidos criados."],
            ["Taxa de Chargeback", "Pedidos com chargeback / pedidos válidos."],
            ["Taxa de Aprovação", "Tentativas de pagamento aprovadas / tentativas."],
            ["Comprador ativo (janela)", "Comprador unificado com pelo menos 1 pedido pago na janela, na mesma loja."],
            ["Comprador recorrente (janela)", "Comprador unificado com 2 ou mais pedidos pagos na janela, na mesma loja."],
            ["Taxa de Recompra", "Compradores recorrentes / compradores ativos na janela (padrão: últimos 90 dias). "
                                 "Ver regras de pedido pago, pedido de teste e identidade no Contrato de Dados."],
            ["Churn de lojistas", "Lojas que cancelaram a assinatura / lojas no período."],
            ["MRR", "Soma das mensalidades das assinaturas ativas."],
            ["ROAS", "Receita atribuída a anúncios / investimento em mídia."],
        ],
    },
    "politica_de_chargeback_e_med.pdf": {
        "titulo": "Política de Chargeback e MED",
        "subtitulo": "Disputas de pagamento — orientações para lojistas",
        "secoes": [
            ("Chargeback (cartão)", [
                "Chargeback é a contestação de uma compra feita pelo portador do cartão junto ao banco emissor. "
                "O lojista tem até 7 dias corridos para enviar a defesa (comprovante de entrega, nota fiscal, conversa com o cliente).",
                ["Motivos mais comuns: fraude / não reconhecida, produto não recebido, produto diferente do anunciado, "
                 "produto com defeito, cobrança duplicada, cancelamento não processado.",
                 "Disputa perdida: o valor é estornado ao comprador e debitado do lojista.",
                 "Taxa de chargeback acima de 1% coloca a loja em monitoramento de risco."],
            ]),
            ("MED (Pix)", [
                "O Mecanismo Especial de Devolução (MED) permite a devolução de valores de Pix em casos de fraude ou golpe. "
                "O pedido de devolução é aberto pelo pagador no próprio banco.",
            ]),
            ("Boas práticas", [
                ["Use transportadoras com rastreio e guarde o comprovante de entrega.",
                 "Desconfie de pedidos de alto valor, à vista, de contas recém-criadas e com vários pedidos para o mesmo CEP.",
                 "Responda rápido aos tickets de 'onde está meu pedido': atraso é a principal causa de 'produto não recebido'."],
            ]),
        ],
    },
    "manual_do_lojista.pdf": {
        "titulo": "Manual do Lojista",
        "subtitulo": "Planos, pagamentos, frete e boas práticas",
        "secoes": [
            ("Planos", [
                ["Inicial — R$ 69/mês (era R$ 49 até o reajuste comunicado há cerca de 5 meses).",
                 "Básico — R$ 99/mês.  Essencial — R$ 199/mês.  Profissional — R$ 399/mês.  Avançado — R$ 899/mês.",
                 "Upgrade pode ser feito a qualquer momento pelo painel; o cancelamento encerra a loja ao fim do ciclo."],
            ]),
            ("Pagamentos", [
                ["Meios aceitos: Pix, cartão de crédito (até 12x), cartão de débito, boleto e carteiras digitais.",
                 "O Pix é aprovado na hora; o boleto compensa em até 2 dias úteis e vence em 3 dias.",
                 "Recusas de cartão acontecem mais de madrugada, quando o antifraude dos emissores é mais rigoroso."],
            ]),
            ("Frete e envios", [
                ["Transportadoras parceiras: Postal Brasil, Rota Express, Leva Já, Entrega Certa e Rápido Sul (Sul/Sudeste).",
                 "Configure frete grátis acima de um valor mínimo para aumentar a conversão.",
                 "Acompanhe atrasos por região: atrasos geram tickets e disputas por produto não recebido."],
            ]),
            ("Checkout", [
                "Se clientes relatarem problemas para finalizar a compra em um dispositivo específico (por exemplo, iPhone/Safari), "
                "abra um ticket com o assunto 'Problema no checkout' informando dispositivo e navegador.",
            ]),
        ],
    },
}


def _bloco(item, estilo):
    if isinstance(item, list):
        return ListFlowable([ListItem(Paragraph(x, estilo)) for x in item], bulletType="bullet", leftIndent=14)
    return Paragraph(item, estilo)


def gerar(saida: Path):
    saida.mkdir(parents=True, exist_ok=True)
    st = getSampleStyleSheet()
    for nome, d in DOCS.items():
        doc = SimpleDocTemplate(str(saida / nome), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                                topMargin=2 * cm, bottomMargin=2 * cm, title=d["titulo"])
        corpo = [Paragraph(d["titulo"], st["Title"]), Paragraph(d["subtitulo"], st["Italic"]), Spacer(1, 12)]
        for titulo, itens in d.get("secoes", []):
            corpo.append(Paragraph(titulo, st["Heading2"]))
            corpo.extend(_bloco(i, st["BodyText"]) for i in itens)
            corpo.append(Spacer(1, 6))
        if "tabela" in d:
            linhas = [[Paragraph(c, st["BodyText"]) for c in linha] for linha in d["tabela"]]
            t = Table(linhas, colWidths=[5 * cm, 12 * cm])
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            corpo.append(t)
        doc.build(corpo)
        print(saida / nome)


if __name__ == "__main__":
    gerar(Path(sys.argv[1] if len(sys.argv) > 1 else "dist/docs"))
