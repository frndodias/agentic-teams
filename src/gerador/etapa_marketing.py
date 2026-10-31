"""Etapa marketing: investimento diário por plataforma, cada uma com seu schema de CSV. Inclui H8."""
import math
from datetime import timedelta

from pyspark.sql import functions as F

from comum import DIAS_HISTORICO, SEG_DIA, Ctx, _black_friday, data_texto, entre, escrever_csv, ler_interno, u

DIAS_H8 = 90  # H8: a Meta renomeou amount_spent -> spend há ~3 meses


def _dias_bf(ctx: Ctx):
    dias = []
    for ano in {ctx.inicio.year, ctx.ancora.year}:
        bf = _black_friday(ano)
        for d in range(-4, 5):
            idx = ctx.dia_idx(bf + timedelta(days=d))
            if 0 <= idx < DIAS_HISTORICO:
                dias.append(idx)
    return dias


def rodar(ctx: Ctx):
    lojas = ler_interno(ctx, "lojas")
    k = "loja_id"
    anunc = (
        lojas.where(u(ctx, "ads", k) < F.when(F.col("peso") > 2, 0.6).otherwise(0.3))
        .withColumn("meta", u(ctx, "meta", k) < 0.8)
        .withColumn("google", u(ctx, "google", k) < 0.55)
        .withColumn("base", F.col("peso") * entre(u(ctx, "base", k), 15, 60))
        .withColumn("dia", F.explode(F.sequence("inicio_ativo", "fim_idx")))
        .withColumn("chave", F.concat_ws("|", "loja_id", F.col("dia").cast("string")))
    )
    bf = _dias_bf(ctx)
    fator = (F.exp(F.lit(math.log(1.5) / 365) * F.col("dia")) * entre(u(ctx, "ruido", "chave"), 0.7, 1.3)
             * F.when(F.col("dia").isin(bf), 2.5).otherwise(1.0))
    campanha = F.when(F.col("dia").isin(bf), "black_friday").otherwise(
        F.when(u(ctx, "camp", "chave") < 0.6, "always_on").otherwise("remarketing"))
    data = data_texto(F.lit(ctx.inicio_s).cast("long") + F.col("dia") * SEG_DIA)
    num = F.regexp_replace("loja_id", "L", "")

    meta = (
        anunc.where("meta")
        .withColumn("valor", F.round(F.col("base") * fator, 2))
        .withColumn("impressions", F.floor(F.col("valor") / entre(u(ctx, "cpm", "chave"), 12, 25) * 1000).cast("long"))
        .withColumn("link_clicks", F.floor(F.col("impressions") * entre(u(ctx, "ctr", "chave"), 0.008, 0.022)).cast("long"))
        .select(data.alias("date"), F.concat(F.lit("act_"), num).alias("account_id"), F.col("loja_id").alias("store_ref"),
                campanha.alias("campaign_name"), "valor", "impressions", "link_clicks", "dia")
    )
    corte = DIAS_HISTORICO - DIAS_H8
    cols = ["date", "account_id", "store_ref", "campaign_name"]
    escrever_csv(ctx, meta.where(F.col("dia") < corte).select(*cols, F.col("valor").alias("amount_spent"), "impressions", "link_clicks"),
                 "marketing_meta", arquivos=8)
    escrever_csv(ctx, meta.where(F.col("dia") >= corte).select(*cols, F.col("valor").alias("spend"), "impressions", "link_clicks"),
                 "marketing_meta", arquivos=2, modo="append")

    google = (
        anunc.where("google")
        .withColumn("valor", F.col("base") * 0.8 * fator)
        .withColumn("impressions", F.floor(F.col("valor") / entre(u(ctx, "gcpm", "chave"), 8, 20) * 1000).cast("long"))
        .select(data.alias("day"), F.concat(F.lit("cust-"), num).alias("customer_id"), F.col("loja_id").alias("store_ref"),
                campanha.alias("campaign"), F.floor(F.col("valor") * 1_000_000).cast("long").alias("cost_micros"), "impressions",
                F.floor(F.col("impressions") * entre(u(ctx, "gctr", "chave"), 0.01, 0.04)).cast("long").alias("clicks"))
    )
    escrever_csv(ctx, google, "marketing_google", arquivos=8)
    print("marketing ok")
