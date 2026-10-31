"""Etapa eventos web (últimos 90 dias): sessões de compra + sessões sem conversão. Inclui H7."""
from pyspark.sql import functions as F

from comum import (DIAS_EVENTOS_WEB, DIAS_HISTORICO, SEG_DIA, Ctx, entre_int, escolher, escrever_json,
                   ler_interno, segundos_do_dia, ts_texto, u)
from etapa_pedidos import DIA_IOS_FIM, DIA_IOS_INI

TIPOS_SESSAO = [("bounce", 55), ("produto", 25), ("carrinho", 12), ("checkout", 8)]
SESSOES_EXTRAS_MAX = 47  # média ~23,5 sessões sem compra por pedido (conversão ~4%)


def _eventos_sessao(ctx: Ctx, tipo_col, chave: str):
    pv = F.array_repeat(F.lit("page_view"), entre_int(u(ctx, "npv", chave), 1, 3))
    vi = F.array_repeat(F.lit("view_item"), entre_int(u(ctx, "nvi", chave), 1, 3))
    return (F.when(tipo_col == "compra", F.concat(pv, vi, F.array(F.lit("add_to_cart"), F.lit("begin_checkout"), F.lit("purchase"))))
            .when(tipo_col == "bounce", F.array(F.lit("page_view")))
            .when(tipo_col == "produto", F.concat(F.array(F.lit("page_view")), vi))
            .when(tipo_col == "carrinho", F.array(F.lit("page_view"), F.lit("view_item"), F.lit("add_to_cart")))
            .otherwise(F.array(F.lit("page_view"), F.lit("view_item"), F.lit("add_to_cart"), F.lit("begin_checkout"))))


def rodar(ctx: Ctx):
    a = F.lit(ctx.ancora_s)
    ini = DIAS_HISTORICO - DIAS_EVENTOS_WEB
    lojas = ler_interno(ctx, "lojas").select("loja_id", "n_produtos")
    p = (ler_interno(ctx, "pedidos").where((F.col("dia") >= ini) & (F.col("ts_pedido") < a))
         .select("seq", "pedido_id", "loja_id", "comprador_id", "dia", "ts_pedido", "dispositivo", "origem_trafego"))
    s = "seq"
    compra = p.select(
        "loja_id", "dia", "dispositivo", "origem_trafego", "comprador_id", "pedido_id",
        F.lit("compra").alias("tipo_sessao"), F.concat(F.col("seq").cast("string"), F.lit("|c")).alias("chave"),
        (F.col("ts_pedido") - entre_int(u(ctx, "sini", s), 300, 2400)).alias("ts_ini"))
    sem = (
        p.withColumn("j", F.explode(F.sequence(F.lit(0), entre_int(u(ctx, "nsess", s), 0, SESSOES_EXTRAS_MAX))))
        .where("j > 0")
        .withColumn("chave", F.concat_ws("|", F.col("seq").cast("string"), F.col("j").cast("string")))
        .select("loja_id", "dia",
                escolher(u(ctx, "sdisp", "chave"), [("ios", 30), ("android", 42), ("desktop", 28)]).alias("dispositivo"),
                escolher(u(ctx, "sorig", "chave"), [("organico", 30), ("direto", 18), ("social", 14), ("ads_meta", 15),
                                                    ("ads_google", 12), ("email", 6), ("whatsapp", 5)]).alias("origem_trafego"),
                F.when(u(ctx, "slog", "chave") < 0.2, F.col("comprador_id")).alias("comprador_id"),
                F.lit(None).cast("long").alias("pedido_id"),
                escolher(u(ctx, "stipo", "chave"), TIPOS_SESSAO).alias("tipo_sessao"), "chave",
                (F.lit(ctx.inicio_s).cast("long") + F.col("dia") * SEG_DIA + segundos_do_dia(ctx, "sts", "chave")).alias("ts_ini"))
    )
    # H7: checkouts abandonados extras no iOS durante a janela do bug (~ -30% na conversão do checkout)
    h7 = (
        p.where((F.col("dispositivo") == "ios") & F.col("dia").between(DIA_IOS_INI, DIA_IOS_FIM - 1))
        .withColumn("j", F.explode(F.sequence(F.lit(1), F.when(u(ctx, "h7x", s) < 0.25, 2).otherwise(1))))
        .withColumn("chave", F.concat_ws("|", F.col("seq").cast("string"), F.lit("h7"), F.col("j").cast("string")))
        .select("loja_id", "dia", F.lit("ios").alias("dispositivo"), "origem_trafego",
                F.lit(None).cast("long").alias("comprador_id"), F.lit(None).cast("long").alias("pedido_id"),
                F.lit("checkout").alias("tipo_sessao"), "chave",
                (F.col("ts_pedido") + entre_int(u(ctx, "h7t", "chave"), -7200, 7200)).alias("ts_ini"))
    )
    sess = (
        compra.unionByName(sem).unionByName(h7)
        .withColumn("sessao_id", F.substring(F.md5(F.concat(F.col("chave"), F.lit(ctx.seed))), 1, 20))
        .withColumn("evs", _eventos_sessao(ctx, F.col("tipo_sessao"), "chave"))
        .join(F.broadcast(lojas), "loja_id")
    )
    ev = (
        sess.select("*", F.posexplode("evs").alias("pos", "tipo"))
        .withColumn("ts", F.col("ts_ini") + F.col("pos") * entre_int(u(ctx, "gap", "chave"), 15, 120))
        .where(F.col("ts") < a)
        .select(F.substring(F.md5(F.concat_ws("|", "chave", F.col("pos").cast("string"))), 1, 24).alias("evento_id"),
                "sessao_id", "loja_id", "comprador_id", ts_texto(F.col("ts")).alias("ts"), "tipo",
                F.when(F.col("tipo").isin("view_item", "add_to_cart"),
                       F.concat("loja_id", F.lit("-P"), F.lpad(F.floor(u(ctx, "evp", "chave", "pos") * F.col("n_produtos"))
                                                               .cast("int").cast("string"), 4, "0"))).alias("produto_id"),
                F.when(F.col("tipo") == "purchase", F.col("pedido_id")).alias("pedido_id"),
                "dispositivo", "origem_trafego",
                F.when(F.col("origem_trafego").isin("ads_meta", "ads_google"),
                       escolher(u(ctx, "utm", "chave"), [("always_on", 50), ("remarketing", 30), ("prospeccao", 20)])).alias("utm_campaign"))
    )
    escrever_json(ctx, ev, "eventos_web")
    print("eventos_web ok")
