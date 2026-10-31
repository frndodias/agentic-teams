"""Etapa pedidos: pedidos (CDC), itens, pagamentos (webhooks), envios (rastreio) e disputas.

Inclui as histórias H2 (fraude em Eletrônicos), H4 (atraso da Rota Express no Nordeste),
H6 (Pix x cartão), H7 (checkout iOS) e os pedidos de teste da lacuna da demo.
Sistemas "core" (pedidos, itens, gateway) usam nomes em inglês; parceiros (transportadoras,
adquirente) usam português — a silver padroniza.
"""
from pyspark.sql import Window
from pyspark.sql import functions as F

import vocab as V
from comum import (DIAS_HISTORICO, SEG_DIA, Ctx, da_lista, embaralhar, entre, entre_int, escolher,
                   escrever_csv, escrever_json, ler_interno, salvar_interno, segundos_do_dia, sortear_dia,
                   tabelas_curva, ts_texto, u)
from etapa_base import gerar_pessoas

OFF_FRAUDE = 1 << 36
OFF_TESTE = 1 << 37
DIA_IOS_INI, DIA_IOS_FIM = DIAS_HISTORICO - 62, DIAS_HISTORICO - 52  # H7
JANELA_FRAUDE = 60  # H2
JANELA_ATRASO = 42  # H4

STATUS_EN = {"pendente": "pending", "pago": "paid", "enviado": "shipped", "entregue": "delivered",
             "cancelado": "cancelled", "devolvido": "returned"}
MEIO_EN = {"cartao_credito": "credit_card", "pix": "pix", "boleto": "boleto", "cartao_debito": "debit_card",
           "carteira_digital": "wallet"}


def _mapa(d):
    return F.create_map(*[x for k, v in d.items() for x in (F.lit(k), F.lit(v))])


# ---------------------------------------------------------------- pedidos (cabeçalho)

def pedidos_normais(ctx: Ctx, rel, curvas):
    p = (
        rel.withColumn("k", F.explode(F.sequence(F.lit(0), F.col("n_pedidos") - 1)))
        .withColumn("seq", F.col("rel_num") * 64 + F.col("k"))
        .withColumn("lo", F.col("t0"))
        .withColumn("hi", F.when(F.col("k") == 0, F.col("t0")).otherwise(F.col("t1")))
        .withColumn("u_dia", u(ctx, "dia", "seq"))
    )
    p = sortear_dia(p, ctx, curvas, "lo", "hi", "u_dia", "dia")
    s = "seq"
    canal_1a = (F.when(F.col("canal_aquisicao") == "Marketplace", "Marketplace")
                .when(F.col("canal_aquisicao") == "Instagram", "Instagram")
                .when(F.col("canal_aquisicao") == "WhatsApp", "WhatsApp")
                .when((F.col("canal_aquisicao") == "Anúncios Google") & (u(ctx, "gs", s) < 0.4), "Google Shopping")
                .when(u(ctx, "tt", s) < 0.12, "TikTok Shop").otherwise("Loja Online"))
    canal_n = escolher(u(ctx, "canal", s), [("Loja Online", 50), ("Marketplace", 14), ("Instagram", 16),
                                            ("WhatsApp", 12), ("Google Shopping", 5), ("TikTok Shop", 3)])
    origem_1a = _mapa({"Busca orgânica": "organico", "Anúncios Meta": "ads_meta", "Anúncios Google": "ads_google",
                       "Indicação": "direto", "Instagram": "social", "WhatsApp": "whatsapp",
                       "Marketplace": "marketplace"})[F.col("canal_aquisicao")]
    origem_n = escolher(u(ctx, "origem", s), [("organico", 28), ("direto", 22), ("email", 15), ("ads_meta", 14),
                                              ("ads_google", 11), ("whatsapp", 10)])
    p = (
        p.withColumn("canal", F.when(F.col("k") == 0, canal_1a).otherwise(canal_n))
        .withColumn("origem_trafego", F.when(F.col("canal") == "Marketplace", "marketplace")
                    .when(F.col("k") == 0, origem_1a).otherwise(origem_n))
        .withColumn("dispositivo", escolher(u(ctx, "disp", s), [("ios", 30), ("android", 42), ("desktop", 28)]))
        # H7: 30% dos pedidos iOS "somem" na janela do checkout quebrado
        .where(~((F.col("dispositivo") == "ios") & F.col("dia").between(DIA_IOS_INI, DIA_IOS_FIM - 1)
                 & (u(ctx, "ios_perdido", s) < 0.30)))
        .withColumn("comprador_id", F.when(F.col("tem_dup") & (u(ctx, "usa_dup", s) < 0.4), F.col("comprador_dup_id"))
                    .otherwise(F.col("comprador_id")))
        .withColumn("tipo", F.lit("normal"))
    )
    return p


def pedidos_fraude(ctx: Ctx, lojas, normais):
    """H2: contas novas, ticket alto, cartão à vista e CEPs concentrados nas lojas marcadas."""
    janela = DIAS_HISTORICO - JANELA_FRAUDE
    cont = (normais.where(F.col("loja_fraude") & (F.col("dia") >= janela))
            .groupBy("loja_id").count().orderBy("loja_id").collect())
    linhas, ini = [], 0
    for r in cont:
        n = max(1, round(r["count"] * 0.18))
        linhas.append((r["loja_id"], ini, n))
        ini += n
    if not linhas:
        return None, None
    faixas = ctx.spark.createDataFrame(linhas, "loja_id string, ini long, n long")
    f = faixas.select("loja_id", F.explode(F.sequence("ini", F.col("ini") + F.col("n") - 1)).alias("fraude_num"))
    pessoas = gerar_pessoas(ctx, ini, "f", offset=0).withColumnRenamed("pessoa_id", "fraude_num")
    k = "fraude_num"
    ceps = ["08260", "08270", "08290", "08320", "08340"]
    lj = lojas.select("loja_id", "segmento", "perfil", F.col("uf").alias("uf_loja"),
                      F.col("regiao").alias("regiao_loja"), "frete_gratis_min", "loja_fraude", "inicio_ativo", "fim_idx")
    f = (
        f.join(pessoas, "fraude_num").join(F.broadcast(lj), "loja_id")
        .withColumn("uf", F.lit("SP")).withColumn("cidade", F.lit("São Paulo")).withColumn("regiao", F.lit("Sudeste"))
        .withColumn("cep", F.concat(da_lista(u(ctx, "fcep", k), ceps), F.lit("-"),
                                    F.lpad(entre_int(u(ctx, "fcep2", k), 0, 999).cast("string"), 3, "0")))
        .withColumn("seq", F.lit(OFF_FRAUDE) + F.col("fraude_num"))
        .withColumn("pessoa_id", F.lit(OFF_FRAUDE) + F.col("fraude_num"))
        .withColumn("rel_num", F.lit(None).cast("long"))
        .withColumn("comprador_id", embaralhar(F.col("seq")))
        .withColumn("dia", entre_int(u(ctx, "fdia", k), janela, DIAS_HISTORICO - 1))
        .withColumn("canal", F.lit("Loja Online"))
        .withColumn("origem_trafego", escolher(u(ctx, "forig", k), [("ads_meta", 60), ("direto", 40)]))
        .withColumn("dispositivo", escolher(u(ctx, "fdisp", k), [("android", 60), ("desktop", 40)]))
        .withColumn("canal_aquisicao", F.lit("Anúncios Meta"))
        .withColumn("tipo_cadastro", F.lit("conta"))
        .withColumn("tipo", F.lit("fraude"))
    )
    compradores = f.select(
        "comprador_id", "loja_id", "nome", "email", "cpf", "telefone", "cep", "cidade", "uf",
        F.date_format(F.timestamp_seconds(F.lit(ctx.inicio_s) + F.col("dia") * SEG_DIA), "yyyy-MM-dd").alias("data_cadastro"),
        "tipo_cadastro", "canal_aquisicao")
    return f, compradores


def pedidos_teste(ctx: Ctx, lojas):
    """Pedidos de teste do lojista: valor <= R$ 1,00, comprador "teste", concentrados no início da loja."""
    k = "loja_id"
    lj = lojas.select("loja_id", "num", "segmento", "perfil", F.col("uf").alias("uf_loja"),
                      F.col("regiao").alias("regiao_loja"), "frete_gratis_min", "loja_fraude",
                      "inicio_ativo", "fim_idx", "abertura_idx", "cidade")
    t = (
        lj.withColumn("n_teste", entre_int(u(ctx, "nteste", k), 0, 18))
        .where("n_teste > 0")
        .withColumn("t", F.explode(F.sequence(F.lit(1), F.col("n_teste"))))
        .withColumn("seq", F.lit(OFF_TESTE) + F.col("num") * 32 + F.col("t"))
        .withColumn("cad", F.when(u(ctx, "tcad", "seq") < 0.6, 1).otherwise(2))
        .withColumn("comprador_id", embaralhar(F.lit(OFF_TESTE) + F.col("num") * 4 + F.col("cad")))
        .withColumn("dia", F.when(F.col("abertura_idx") >= 0,
                                  F.least(F.col("abertura_idx") + entre_int(u(ctx, "tdia", "seq"), 0, 13), F.col("fim_idx")))
                    .otherwise(entre_int(u(ctx, "tdia", "seq"), 0, DIAS_HISTORICO - 1)))
        .where(F.col("dia") <= F.col("fim_idx"))
        .withColumn("pessoa_id", F.lit(None).cast("long")).withColumn("rel_num", F.lit(None).cast("long"))
        .withColumn("uf", F.col("uf_loja")).withColumn("regiao", F.col("regiao_loja"))
        .withColumn("cep", F.lit("01310-100"))
        .withColumn("canal", F.lit("Loja Online")).withColumn("origem_trafego", F.lit("direto"))
        .withColumn("dispositivo", F.lit("desktop"))
        .withColumn("canal_aquisicao", F.lit(None).cast("string"))
        .withColumn("tipo", F.lit("teste"))
    )
    slug = F.lower(F.regexp_replace(F.translate("loja_id", "L", "l"), "[^a-z0-9]", ""))
    comp = (
        t.select("comprador_id", "loja_id", "cad", "abertura_idx", "inicio_ativo").dropDuplicates(["comprador_id"])
        .withColumn("nome", da_lista(u(ctx, "tnome", "comprador_id"), ["Teste", "Teste Loja", "TESTE", "teste teste", "Test User"]))
        .withColumn("email", F.when(F.col("cad") == 1, F.concat(F.lit("teste@loja-"), slug, F.lit(".com.br")))
                    .otherwise(da_lista(u(ctx, "temail", "comprador_id"), ["test@test.com", "teste123@gmail.com", "lojista+teste@gmail.com"])))
        .withColumn("cpf", da_lista(u(ctx, "tcpf", "comprador_id"), ["", "00000000000", "12345678909"]))
        .select("comprador_id", "loja_id", "nome", "email", F.when(F.col("cpf") == "", None).otherwise(F.col("cpf")).alias("cpf"),
                F.lit(None).cast("string").alias("telefone"), F.lit("01310-100").alias("cep"),
                F.lit("São Paulo").alias("cidade"), F.lit("SP").alias("uf"),
                F.date_format(F.timestamp_seconds(F.lit(ctx.inicio_s) + F.col("inicio_ativo") * SEG_DIA), "yyyy-MM-dd").alias("data_cadastro"),
                F.lit("conta").alias("tipo_cadastro"), F.lit(None).cast("string").alias("canal_aquisicao"))
    )
    return t, comp


COLS_PEDIDO = ["seq", "loja_id", "comprador_id", "pessoa_id", "rel_num", "tipo", "dia", "canal", "origem_trafego",
               "dispositivo", "canal_aquisicao", "segmento", "perfil", "uf", "regiao", "cep", "uf_loja",
               "regiao_loja", "frete_gratis_min", "loja_fraude"]


# ---------------------------------------------------------------- itens e valores

def gerar_itens(ctx: Ctx, pedidos, lojas, produtos):
    s = "seq"
    top = (produtos.join(lojas.where("loja_fraude").select("loja_id"), "loja_id")
           .withColumn("_r", F.row_number().over(Window.partitionBy("loja_id").orderBy(F.desc("preco"), "idx")))
           .where("_r <= 5").groupBy("loja_id").agg(F.collect_list("idx").alias("top_idx")))
    it = (
        pedidos.select("seq", "loja_id", "tipo", "dia")
        .join(F.broadcast(lojas.select("loja_id", "n_produtos")), "loja_id")
        .join(F.broadcast(top), "loja_id", "left")
        .withColumn("n_itens", F.when(F.col("tipo") == "teste", 1)
                    .when(F.col("tipo") == "fraude", entre_int(u(ctx, "fni", s), 1, 2))
                    .otherwise(escolher(u(ctx, "ni", s), [(1, 42), (2, 26), (3, 14), (4, 9), (5, 5), (6, 4)])))
        .withColumn("item_seq", F.explode(F.sequence(F.lit(1), F.col("n_itens"))))
        .withColumn("_ui", u(ctx, "item", "seq", "item_seq"))
        .withColumn("idx", F.when(F.col("tipo") == "teste", 0)
                    .when(F.col("tipo") == "fraude", F.element_at("top_idx", (F.floor(F.col("_ui") * F.size("top_idx")) + 1).cast("int")))
                    .otherwise(F.floor(F.col("n_produtos") * F.pow(F.col("_ui"), 2.2)).cast("int")))
    )
    it = it.join(produtos.select("loja_id", "idx", "produto_id", "sku", "preco", "categoria"), ["loja_id", "idx"])
    it = (
        it.withColumn("quantidade", F.when(F.col("tipo") == "teste", 1)
                      .when(F.col("tipo") == "fraude", entre_int(u(ctx, "fq", "seq", "item_seq"), 1, 3))
                      .otherwise(escolher(u(ctx, "q", "seq", "item_seq"), [(1, 80), (2, 14), (3, 6)])))
        .withColumn("preco_unitario", F.when(F.col("tipo") == "teste",
                                             F.round(entre(u(ctx, "tpreco", "seq"), 0.01, 1.0), 2))
                    .otherwise(F.col("preco")))
        .withColumn("desconto_item", F.when((F.col("tipo") == "normal") & (u(ctx, "promo", "seq", "item_seq") < 0.05),
                                            F.round(F.col("preco_unitario") * F.col("quantidade") * 0.1, 2)).otherwise(0.0))
    )
    return it.select("seq", "item_seq", "loja_id", "produto_id", "sku", "categoria", "quantidade", "preco_unitario",
                     "desconto_item", "tipo", "dia")


def calcular_valores(ctx: Ctx, pedidos, itens):
    agg = itens.groupBy("seq").agg(
        F.round(F.sum(F.col("quantidade") * F.col("preco_unitario") - F.col("desconto_item")), 2).alias("valor_produtos"),
        F.array_distinct(F.collect_list("categoria")).alias("categorias"))
    s = "seq"
    p = pedidos.join(agg, "seq")
    frete_base = (F.when(F.col("uf") == F.col("uf_loja"), entre(u(ctx, "fr", s), 12, 19))
                  .when(F.col("regiao") == F.col("regiao_loja"), entre(u(ctx, "fr", s), 15, 25))
                  .otherwise(entre(u(ctx, "fr", s), 22, 45)) + F.when(F.col("regiao") == "Norte", 10).otherwise(0))
    tem_cupom = (F.col("tipo") == "normal") & (u(ctx, "cupom", s) < 0.22)
    p = (
        p.withColumn("cupom", F.when(tem_cupom, da_lista(u(ctx, "cupom_cod", s), V.CUPONS)))
        .withColumn("desconto", F.when(tem_cupom, F.round(F.col("valor_produtos") * entre(u(ctx, "cupom_pct", s), 0.05, 0.20), 2))
                    .otherwise(0.0))
        .withColumn("frete", F.when(F.col("tipo") == "teste", 0.0)
                    .when((F.col("frete_gratis_min") > 0) & (F.col("valor_produtos") >= F.col("frete_gratis_min")), 0.0)
                    .otherwise(F.round(frete_base, 2)))
        .withColumn("valor_total", F.round(F.col("valor_produtos") - F.col("desconto") + F.col("frete"), 2))
    )
    return p


# ---------------------------------------------------------------- pagamento e ciclo de vida

def ciclo_de_vida(ctx: Ctx, p):
    s = "seq"
    t = F.col("dia") / DIAS_HISTORICO
    um = u(ctx, "meio", s)
    pix, bol, deb, cart = 0.35 + 0.13 * t, 0.10 - 0.05 * t, F.lit(0.03), F.lit(0.04)
    meio_normal = (F.when(um < pix, "pix").when(um < pix + bol, "boleto").when(um < pix + bol + deb, "cartao_debito")
                   .when(um < pix + bol + deb + cart, "carteira_digital").otherwise("cartao_credito"))
    p = (
        p.withColumn("ts_pedido", (F.lit(ctx.inicio_s).cast("long") + F.col("dia") * SEG_DIA + segundos_do_dia(ctx, "ped", s)).cast("long"))
        .withColumn("hora", F.floor(F.pmod(F.col("ts_pedido"), F.lit(SEG_DIA)) / 3600))
        .withColumn("meio", F.when(F.col("tipo") == "fraude", "cartao_credito")
                    .when(F.col("tipo") == "teste", F.when(u(ctx, "tmeio", s) < 0.6, "pix").otherwise("cartao_credito"))
                    .otherwise(meio_normal))
        .withColumn("parcelas", F.when((F.col("meio") == "cartao_credito") & (F.col("tipo") == "normal"),
                                       escolher(u(ctx, "parc", s), [(1, 45), (2, 10), (3, 15), (4, 5), (5, 5), (6, 10), (10, 6), (12, 4)]))
                    .otherwise(1))
    )
    cartao = F.col("meio").isin("cartao_credito", "cartao_debito", "carteira_digital")
    p_recusa = (F.when(F.col("tipo") == "teste", 0.0).when(F.col("tipo") == "fraude", 0.05)
                .when(F.col("meio") == "carteira_digital", 0.03)
                .when(F.col("hora") < 6, 0.18).otherwise(0.07))  # H6: recusa maior de madrugada
    recusou1 = (cartao & (u(ctx, "rec1", s) < p_recusa)) | ((F.col("meio") == "pix") & (u(ctx, "pixexp", s) < 0.03)) \
        | ((F.col("meio") == "boleto") & (u(ctx, "bolv", s) < 0.25))
    p = (
        p.withColumn("recusou1", recusou1)
        .withColumn("motivo_recusa", F.when(F.col("recusou1"), F.when(F.col("meio") == "pix", "expirado")
                                            .when(F.col("meio") == "boleto", "vencido")
                                            .otherwise(escolher(u(ctx, "motrec", s), [("saldo_insuficiente", 40), ("antifraude", 25),
                                                                                      ("dados_invalidos", 20), ("cartao_expirado", 15)]))))
        .withColumn("ts_resp1", F.col("ts_pedido") + F.when(F.col("meio") == "pix",
                                                            F.when(F.col("recusou1"), 1800).otherwise(entre_int(u(ctx, "pixt", s), 60, 1200)))
                    .when(F.col("meio") == "boleto", F.when(F.col("recusou1"), 3 * SEG_DIA)
                          .otherwise(entre_int(u(ctx, "bolt", s), SEG_DIA, 2 * SEG_DIA)))
                    .otherwise(entre_int(u(ctx, "cart", s), 2, 60)))
        .withColumn("retentou", F.col("recusou1") & cartao & (u(ctx, "retry", s) < 0.72))
        .withColumn("ts_resp2", F.when(F.col("retentou"), F.col("ts_resp1") + entre_int(u(ctx, "rt2", s), 120, 900)))
        .withColumn("pago", ~F.col("recusou1") | F.col("retentou"))
        .withColumn("ts_pago", F.when(F.col("pago"), F.coalesce("ts_resp2", "ts_resp1")))
        .withColumn("score_antifraude",
                    F.when(F.col("tipo") == "fraude", entre_int(u(ctx, "fscore", s), 45, 75))
                    .when(F.col("motivo_recusa") == "antifraude", entre_int(u(ctx, "ascore", s), 70, 99))
                    .otherwise(F.floor(F.pow(u(ctx, "score", s), 2) * 40).cast("int")))
    )
    # cancelamentos: pagamento não concluído, ruptura pós-pagamento (1,5%) e pedidos de teste (60%)
    cancela_lojista = F.col("pago") & (
        ((F.col("tipo") == "normal") & (u(ctx, "cancl", s) < 0.015))
        | ((F.col("tipo") == "teste") & (u(ctx, "tcanc", s) < 0.60)))
    p = (
        p.withColumn("ts_cancelado", F.when(~F.col("pago"), F.col("ts_resp1") + 60)
                     .when(cancela_lojista, F.col("ts_pago") + entre_int(u(ctx, "tcl", s), 3600, 2 * SEG_DIA)))
        .withColumn("estornado", F.col("pago") & F.col("ts_cancelado").isNotNull())
        .withColumn("envia", F.col("pago") & F.col("ts_cancelado").isNull() & (F.col("tipo") != "teste"))
    )
    # envio (H4: Rota Express atrasa ~4 dias no Nordeste nas últimas 6 semanas)
    rapido_sul_ok = F.col("regiao_loja").isin("Sul", "Sudeste")
    transp = escolher(u(ctx, "transp", s), V.TRANSPORTADORAS)
    janela_atraso = F.lit(ctx.ancora_s - JANELA_ATRASO * SEG_DIA)
    p = (
        p.withColumn("transportadora", F.when(F.col("envia"), F.when((transp == "Rápido Sul") & ~rapido_sul_ok, "Postal Brasil")
                                               .otherwise(transp)))
        .withColumn("ts_postagem", F.when(F.col("envia"), F.col("ts_pago") + entre_int(u(ctx, "post", s), 4 * 3600, 3 * SEG_DIA)))
        .withColumn("prazo_prometido", F.when(F.col("envia"),
                                               (F.when(F.col("uf") == F.col("uf_loja"), entre_int(u(ctx, "pz", s), 2, 4))
                                                .when(F.col("regiao") == F.col("regiao_loja"), entre_int(u(ctx, "pz", s), 3, 6))
                                                .otherwise(entre_int(u(ctx, "pz", s), 5, 10)))
                                               + F.when(F.col("regiao") == "Norte", 4).otherwise(0)))
        .withColumn("h4", F.col("envia") & (F.col("transportadora") == "Rota Express") & (F.col("regiao") == "Nordeste")
                    & (F.col("ts_postagem") >= janela_atraso))
        .withColumn("atraso_dias", escolher(u(ctx, "atr", s), [(-2, 10), (-1, 20), (0, 45), (1, 13), (2, 6), (3, 3), (4, 2), (6, 1)])
                    + F.when(F.col("h4"), 4).otherwise(0))
        .withColumn("extraviado", F.col("envia") & (u(ctx, "extr", s) < F.when(F.col("h4"), 0.012).otherwise(0.003)))
        .withColumn("ts_entrega", F.when(F.col("envia") & ~F.col("extraviado"),
                                         F.col("ts_postagem") + F.greatest(F.lit(1), F.col("prazo_prometido") + F.col("atraso_dias")) * SEG_DIA
                                         + entre_int(u(ctx, "entr_h", s), -6 * 3600, 6 * 3600)))
        .withColumn("ts_devolvido", F.when(F.col("ts_entrega").isNotNull() & (u(ctx, "devol", s) < 0.025),
                                           F.col("ts_entrega") + entre_int(u(ctx, "devt", s), 7 * SEG_DIA, 25 * SEG_DIA)))
    )
    # disputas: chargeback (cartão) e MED (Pix)
    atrasado = (F.col("atraso_dias") >= 3) | F.col("extraviado")
    p_cb = (F.when(F.col("tipo") == "fraude", 0.35)
            .when(F.col("tipo") == "teste", 0.0)
            .otherwise(0.006 + F.when(F.col("envia") & atrasado, 0.03).otherwise(0.0)))
    elegivel_cb = F.col("pago") & F.col("meio").isin("cartao_credito", "cartao_debito")
    elegivel_med = F.col("pago") & (F.col("meio") == "pix") & (F.col("tipo") == "normal")
    p = (
        p.withColumn("disputa_tipo", F.when(elegivel_cb & (u(ctx, "cb", s) < p_cb), "chargeback")
                     .when(elegivel_med & (u(ctx, "med", s) < 0.001), "MED"))
        .withColumn("disputa_motivo", F.when(F.col("disputa_tipo").isNull(), None)
                    .when(F.col("tipo") == "fraude", "Fraude / não reconhecida")
                    .when(F.col("disputa_tipo") == "MED", "Golpe / fraude Pix")
                    .when(F.col("envia") & atrasado & (u(ctx, "cbnr", s) < 0.8), "Produto não recebido")
                    .otherwise(escolher(u(ctx, "cbmot", s), [("Fraude / não reconhecida", 45), ("Produto não recebido", 15),
                                                             ("Produto diferente do anunciado", 12), ("Produto com defeito", 10),
                                                             ("Cobrança duplicada", 8), ("Cancelamento não processado", 10)])))
        .withColumn("ts_disputa", F.when(F.col("disputa_tipo") == "MED", F.col("ts_pago") + entre_int(u(ctx, "dmt", s), SEG_DIA, 30 * SEG_DIA))
                    .when(F.col("tipo") == "fraude", F.col("ts_pago") + entre_int(u(ctx, "dft", s), 20 * SEG_DIA, 45 * SEG_DIA))
                    .when(F.col("disputa_tipo").isNotNull(), F.col("ts_pago") + entre_int(u(ctx, "dt", s), 5 * SEG_DIA, 75 * SEG_DIA)))
        .withColumn("ts_disputa_analise", F.col("ts_disputa") + entre_int(u(ctx, "dan", s), SEG_DIA, 3 * SEG_DIA))
        .withColumn("ts_disputa_fim", F.col("ts_disputa") + entre_int(u(ctx, "dfim", s), 15 * SEG_DIA, 45 * SEG_DIA))
        .withColumn("disputa_resultado", F.when(F.col("disputa_tipo").isNotNull(), F.when(
            u(ctx, "dres", s) < F.when(F.col("tipo") == "fraude", 0.85).when(F.col("disputa_tipo") == "MED", 0.5).otherwise(0.65),
            "perdida").otherwise("ganha")))
    )
    return p


def status_na_ancora(ctx: Ctx, p):
    """Status final de cada pedido na data âncora (verdade usada nos gabaritos)."""
    a = F.lit(ctx.ancora_s)
    antes = lambda c: F.col(c).isNotNull() & (F.col(c) < a)  # noqa: E731
    return (F.when(antes("ts_devolvido"), "devolvido").when(antes("ts_cancelado"), "cancelado")
            .when(antes("ts_entrega"), "entregue").when(antes("ts_postagem"), "enviado")
            .when(antes("ts_pago"), "pago").otherwise("pendente"))


# ---------------------------------------------------------------- exportação

def exportar(ctx: Ctx, p, itens):
    a = F.lit(ctx.ancora_s)
    status_en = _mapa(STATUS_EN)
    meio_en = _mapa(MEIO_EN)
    p = p.withColumn("pedido_id", embaralhar(F.col("seq")))

    # pedidos: CDC estilo Debezium (op c/u, ts_ms, after) a cada mudança de status até a âncora
    mudancas = F.filter(F.array(
        F.struct(F.lit("pendente").alias("st"), F.col("ts_pedido").cast("long").alias("ts")),
        F.struct(F.lit("pago").alias("st"), F.col("ts_pago").cast("long").alias("ts")),
        F.struct(F.lit("cancelado").alias("st"), F.col("ts_cancelado").cast("long").alias("ts")),
        F.struct(F.lit("enviado").alias("st"), F.col("ts_postagem").cast("long").alias("ts")),
        F.struct(F.lit("entregue").alias("st"), F.col("ts_entrega").cast("long").alias("ts")),
        F.struct(F.lit("devolvido").alias("st"), F.col("ts_devolvido").cast("long").alias("ts")),
    ), lambda x: x["ts"].isNotNull() & (x["ts"] < a))
    cdc = (
        p.select("*", F.explode(mudancas).alias("m"))
        .select(
            F.when(F.col("m.st") == "pendente", "c").otherwise("u").alias("op"),
            (F.col("m.ts") * 1000 + entre_int(u(ctx, "cdcms", "seq", F.col("m.st")), 0, 999)).alias("ts_ms"),
            F.struct(F.lit("loja_core").alias("db"), F.lit("orders").alias("table")).alias("source"),
            F.struct(
                F.col("pedido_id").alias("id"), F.col("loja_id").alias("store_id"), F.col("comprador_id").alias("customer_id"),
                ts_texto(F.col("ts_pedido")).alias("created_at"), F.col("canal").alias("channel"),
                F.col("origem_trafego").alias("traffic_source"), F.col("dispositivo").alias("device"),
                F.col("cupom").alias("coupon_code"), F.col("valor_produtos").alias("subtotal"),
                F.col("desconto").alias("discount"), F.col("frete").alias("shipping_cost"), F.col("valor_total").alias("total"),
                status_en[F.col("m.st")].alias("status"), ts_texto(F.col("m.ts")).alias("updated_at"),
            ).alias("after"))
    )
    escrever_json(ctx, cdc, "pedidos_cdc")

    itens_out = (
        itens.join(p.select("seq", "pedido_id", "ts_pedido"), "seq")
        .where(F.col("ts_pedido") < a)
        .select(F.col("pedido_id").alias("order_id"), F.col("item_seq").alias("line"), F.col("produto_id").alias("product_id"),
                "sku", F.col("quantidade").alias("quantity"), F.col("preco_unitario").alias("unit_price"),
                F.col("desconto_item").alias("discount"), ts_texto(F.col("ts_pedido")).alias("created_at"))
    )
    escrever_json(ctx, itens_out, "itens_pedido")

    # pagamentos: webhooks do gateway (1ª tentativa e, se houve, a 2ª)
    pg = p.withColumn("pag1", embaralhar(F.col("seq") * 2)).withColumn("pag2", embaralhar(F.col("seq") * 2 + 1))
    ev = F.filter(F.array(
        F.struct(F.col("pag1").alias("pid"), F.lit("payment.created").alias("tp"), F.col("ts_pedido").cast("long").alias("ts"), F.lit(None).cast("string").alias("mot")),
        F.struct(F.col("pag1").alias("pid"), F.when(F.col("recusou1"), "payment.declined").otherwise("payment.approved").alias("tp"),
                 F.col("ts_resp1").cast("long").alias("ts"), F.col("motivo_recusa").alias("mot")),
        F.struct(F.col("pag2").alias("pid"), F.lit("payment.created").alias("tp"),
                 F.when(F.col("retentou"), F.col("ts_resp2") - 30).cast("long").alias("ts"), F.lit(None).cast("string").alias("mot")),
        F.struct(F.col("pag2").alias("pid"), F.lit("payment.approved").alias("tp"), F.col("ts_resp2").cast("long").alias("ts"), F.lit(None).cast("string").alias("mot")),
        F.struct(F.coalesce(F.when(F.col("retentou"), F.col("pag2")), F.col("pag1")).alias("pid"), F.lit("payment.refunded").alias("tp"),
                 F.when(F.col("estornado"), F.col("ts_cancelado")).otherwise(F.col("ts_devolvido")).cast("long").alias("ts"),
                 F.lit(None).cast("string").alias("mot")),
    ), lambda x: x["ts"].isNotNull() & (x["ts"] < a))
    pag = (
        pg.select("*", F.explode(ev).alias("e"))
        .select(F.substring(F.md5(F.concat_ws("|", F.col("e.pid"), F.col("e.tp"), F.lit(ctx.seed))), 1, 20).alias("event_id"),
                F.col("e.pid").alias("payment_id"), F.col("pedido_id").alias("order_id"), F.col("e.tp").alias("type"),
                ts_texto(F.col("e.ts")).alias("occurred_at"), meio_en[F.col("meio")].alias("method"),
                F.col("parcelas").alias("installments"), F.col("valor_total").alias("amount"),
                F.col("e.mot").alias("decline_reason"), F.col("score_antifraude").alias("risk_score"))
    )
    escrever_json(ctx, pag, "pagamentos_eventos")

    # envios: eventos de rastreio das transportadoras
    env = p.where("envia").withColumn("envio_id", embaralhar(F.col("seq") * 2 + 1))
    evs = F.filter(F.array(
        F.struct(F.lit("postado").alias("ev"), F.col("ts_postagem").cast("long").alias("ts")),
        F.struct(F.lit("em_transito").alias("ev"), (F.col("ts_postagem") + 14 * 3600).cast("long").alias("ts")),
        F.struct(F.lit("saiu_para_entrega").alias("ev"), (F.col("ts_entrega") - 5 * 3600).cast("long").alias("ts")),
        F.struct(F.lit("entregue").alias("ev"), F.col("ts_entrega").cast("long").alias("ts")),
        F.struct(F.lit("extraviado").alias("ev"),
                 F.when(F.col("extraviado"), F.col("ts_postagem") + (F.col("prazo_prometido") + 10) * SEG_DIA).cast("long").alias("ts")),
    ), lambda x: x["ts"].isNotNull() & (x["ts"] < a))
    rastreio = (
        env.select("*", F.explode(evs).alias("e"))
        .select("envio_id", F.col("pedido_id"), "transportadora",
                F.concat(F.upper(F.substring(F.md5(F.col("envio_id").cast("string")), 1, 2)),
                         F.lpad((F.col("envio_id") % 1_000_000_000).cast("string"), 9, "0"), F.lit("BR")).alias("codigo_rastreio"),
                F.col("cep").alias("cep_destino"), F.col("uf").alias("uf_destino"),
                F.col("prazo_prometido").alias("prazo_prometido_dias"),
                ts_texto(F.col("ts_postagem")).alias("data_postagem"),
                F.date_format(F.timestamp_seconds(F.col("ts_postagem") + F.col("prazo_prometido") * SEG_DIA), "yyyy-MM-dd").alias("data_entrega_prevista"),
                F.col("e.ev").alias("evento"), ts_texto(F.col("e.ts")).alias("ocorrido_em"), F.col("frete").alias("custo_frete"))
    )
    escrever_json(ctx, rastreio, "envios_eventos")

    # disputas: eventos do adquirente / MED
    dsp = p.where(F.col("disputa_tipo").isNotNull()).withColumn("disputa_id", F.concat(F.lit("DSP"), embaralhar(F.col("seq")).cast("string")))
    evd = F.filter(F.array(
        F.struct(F.lit("aberta").alias("ev"), F.col("ts_disputa").cast("long").alias("ts")),
        F.struct(F.lit("em_analise").alias("ev"), F.col("ts_disputa_analise").cast("long").alias("ts")),
        F.struct(F.col("disputa_resultado").alias("ev"), F.col("ts_disputa_fim").cast("long").alias("ts")),
    ), lambda x: x["ts"] < a)
    disputas = (
        dsp.select("*", F.explode(evd).alias("e"))
        .select("disputa_id", "pedido_id", F.coalesce(F.when(F.col("retentou"), embaralhar(F.col("seq") * 2 + 1)),
                                                     embaralhar(F.col("seq") * 2)).alias("pagamento_id"),
                F.col("disputa_tipo").alias("tipo"), F.col("disputa_motivo").alias("motivo"), F.col("valor_total").alias("valor"),
                F.col("e.ev").alias("evento"), ts_texto(F.col("e.ts")).alias("ocorrido_em"))
    )
    escrever_json(ctx, disputas, "disputas_eventos", arquivos=4)
    return p


def rodar(ctx: Ctx):
    curvas = tabelas_curva(ctx)
    lojas = ler_interno(ctx, "lojas")
    produtos = ler_interno(ctx, "produtos")
    rel = ler_interno(ctx, "relacoes")

    normais = pedidos_normais(ctx, rel, curvas)
    salvar_interno(ctx, normais.select(*COLS_PEDIDO), "pedidos_base_normais")
    normais = ler_interno(ctx, "pedidos_base_normais")
    fraude, comp_fraude = pedidos_fraude(ctx, lojas, normais)
    teste, comp_teste = pedidos_teste(ctx, lojas)
    base = normais.unionByName(teste.select(*COLS_PEDIDO))
    if fraude is not None:
        base = base.unionByName(fraude.select(*COLS_PEDIDO))
    salvar_interno(ctx, base, "pedidos_base")
    base = ler_interno(ctx, "pedidos_base")

    # cadastros extras: compradores de fraude (contas novas) e de teste
    extras = comp_teste if comp_fraude is None else comp_teste.unionByName(comp_fraude)
    escrever_csv(ctx, extras, "compradores", modo="append")

    itens = gerar_itens(ctx, base, lojas, produtos)
    salvar_interno(ctx, itens, "itens")
    itens = ler_interno(ctx, "itens")

    p = ciclo_de_vida(ctx, calcular_valores(ctx, base, itens))
    p = p.withColumn("status_final", status_na_ancora(ctx, p))
    p = exportar(ctx, p, itens)
    salvar_interno(ctx, p.drop("hora"), "pedidos")
    print(f"pedidos ok: {ler_interno(ctx, 'pedidos').count()}")
