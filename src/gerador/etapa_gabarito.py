"""Gabarito da lacuna da demo: taxa de recompra em 90 dias (versão correta x ingênua).

Correta: identidade real da pessoa dentro da loja, só pedidos pagos (pagamento aprovado, status
diferente de cancelado/pendente, sem chargeback perdido), sem pedidos de teste.
Ingênua: comprador_id cru e todos os pedidos da janela.
Grava em _interno/gabarito e numa cópia CSV na pasta do usuário no workspace.
"""
import os

from pyspark.sql import functions as F

from comum import DIAS_HISTORICO, Ctx, ler_interno, salvar_interno

JANELA = 90


def _taxas(df, chave_pessoa: str, dims: list[str], versao: str):
    """Comprador = (loja, pessoa). Recorrente = 2+ pedidos distintos na janela (na dimensão, se houver)."""
    def agrega(grupo):
        por = df.groupBy("loja_id", chave_pessoa, *grupo).agg(F.countDistinct("seq").alias("n"))
        return por.groupBy(*grupo).agg(
            F.count("*").alias("compradores_ativos"),
            F.sum(F.when(F.col("n") >= 2, 1).otherwise(0)).alias("compradores_recorrentes"))

    out = agrega([]).select(F.lit(versao).alias("versao"), F.lit("geral").alias("dimensao"), F.lit("total").alias("valor"),
                            "compradores_ativos", "compradores_recorrentes")
    for d in dims:
        out = out.unionByName(agrega([d]).select(F.lit(versao).alias("versao"), F.lit(d).alias("dimensao"),
                                                 F.col(d).cast("string").alias("valor"),
                                                 "compradores_ativos", "compradores_recorrentes"))
    return out.withColumn("taxa_recompra", F.round(F.col("compradores_recorrentes") / F.col("compradores_ativos"), 4))


def rodar(ctx: Ctx):
    a = F.lit(ctx.ancora_s)
    p = ler_interno(ctx, "pedidos").where((F.col("dia") >= DIAS_HISTORICO - JANELA) & (F.col("ts_pedido") < a))
    rel = ler_interno(ctx, "relacoes").select("rel_num", F.col("canal_aquisicao").alias("canal_rel"))
    p = (p.join(rel, "rel_num", "left")
         .withColumn("canal_aquisicao", F.coalesce("canal_rel", "canal_aquisicao"))
         .withColumn("categoria", F.explode("categorias")))
    cb_perdido = (F.col("disputa_resultado") == "perdida") & (F.col("ts_disputa_fim") < a)
    correto = p.where((F.col("tipo") != "teste") & F.col("pago") & ~F.col("status_final").isin("cancelado", "pendente")
                      & ~F.coalesce(cb_perdido, F.lit(False)))
    dims = ["categoria", "segmento", "canal_aquisicao"]
    g = _taxas(correto, "pessoa_id", dims, "correta").unionByName(_taxas(p, "comprador_id", dims, "ingenua"))
    salvar_interno(ctx, g, "gabarito_recompra")
    pdf = ler_interno(ctx, "gabarito_recompra").orderBy("versao", "dimensao", F.desc("compradores_ativos")).toPandas()

    usuario = ctx.spark.sql("select current_user() u").first()["u"]
    pasta = f"/Workspace/Users/{usuario}/agentic-teams/gabarito"
    try:
        os.makedirs(pasta, exist_ok=True)
        pdf.to_csv(f"{pasta}/gabarito_recompra_{ctx.escala}.csv", index=False)
        print(f"gabarito em {pasta}")
    except OSError as e:  # sem acesso a /Workspace no compute: fica só no _interno
        print(f"aviso: não gravou no workspace ({e}); gabarito em {ctx.interno}/gabarito_recompra")
    print(pdf[pdf["dimensao"].isin(["geral", "segmento", "canal_aquisicao"])].to_string())
