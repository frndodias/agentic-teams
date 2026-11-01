"""Base do gerador: contexto, aleatoriedade determinística, calendário e escrita na landing.

Toda aleatoriedade vem de hash(seed, sal, chaves) -> mesmos parâmetros = mesmos dados,
independente de particionamento ou do número de workers.
"""
import argparse
import math
from dataclasses import dataclass
from datetime import date, timedelta

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

ESCALAS = {
    "XS": dict(lojas=50, pedidos=30_000),  # só para testar o código
    "S": dict(lojas=500, pedidos=1_000_000),
    "M": dict(lojas=10_000, pedidos=30_000_000),
    "L": dict(lojas=50_000, pedidos=150_000_000),
}
PEDIDOS_POR_RELACAO = 1.50  # medido na escala M após calibrar a recompra (~85% compram uma vez só)
RELACOES_POR_PESSOA = 1.156  # 12% das pessoas compram em 2-3 lojas
DIAS_HISTORICO = 730
DIAS_EVENTOS_WEB = 90
BUCKETS_CURVA = 20_000
SEG_DIA = 86_400


@dataclass
class Ctx:
    spark: SparkSession
    catalog: str
    schema: str
    escala: str
    seed: int
    ancora: date

    @property
    def n_lojas(self) -> int:
        return ESCALAS[self.escala]["lojas"]

    @property
    def n_pedidos(self) -> int:
        return ESCALAS[self.escala]["pedidos"]

    @property
    def n_relacoes(self) -> int:
        return round(self.n_pedidos / PEDIDOS_POR_RELACAO)

    @property
    def n_pessoas(self) -> int:
        return round(self.n_relacoes / RELACOES_POR_PESSOA)

    @property
    def inicio(self) -> date:
        return self.ancora - timedelta(days=DIAS_HISTORICO)

    @property
    def inicio_s(self) -> int:
        return (self.inicio - date(1970, 1, 1)).days * SEG_DIA

    @property
    def ancora_s(self) -> int:
        return (self.ancora - date(1970, 1, 1)).days * SEG_DIA

    @property
    def landing(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/landing"

    @property
    def interno(self) -> str:
        return f"{self.landing}/_interno"

    def dia_idx(self, d: date) -> int:
        return (d - self.inicio).days


def ler_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--etapa", required=True)
    p.add_argument("--catalog", default="fc_catalog")
    p.add_argument("--schema", default="ecommerce")
    p.add_argument("--escala", default="M", choices=list(ESCALAS))
    p.add_argument("--seed", default="42")
    p.add_argument("--data_ancora", default="hoje")
    return p.parse_args()


def criar_ctx(args: argparse.Namespace) -> Ctx:
    spark = SparkSession.builder.getOrCreate()
    # Timestamps do gerador são "hora local ingênua": força UTC para não haver deslocamento.
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    ancora = date.today() if args.data_ancora in ("", "hoje") else date.fromisoformat(args.data_ancora)
    return Ctx(spark, args.catalog, args.schema, args.escala, int(args.seed), ancora)


# ---------------------------------------------------------------- aleatoriedade

_PRIMO = 2_147_483_647


def u(ctx: Ctx, sal: str, *cols) -> Column:
    """Uniforme [0,1) determinística a partir de (seed, sal, colunas)."""
    h = F.xxhash64(F.lit(ctx.seed), F.lit(sal), *[F.col(c) if isinstance(c, str) else c for c in cols])
    return F.pmod(h, F.lit(_PRIMO)).cast("double") / F.lit(float(_PRIMO))


def escolher(uc: Column, opcoes) -> Column:
    """Escolha categórica ponderada: opcoes = [(valor, peso), ...]."""
    total = float(sum(p for _, p in opcoes))
    acc, expr = 0.0, None
    for i, (valor, peso) in enumerate(opcoes):
        acc += peso / total
        cond = F.lit(True) if i == len(opcoes) - 1 else uc < F.lit(acc)
        expr = F.when(cond, F.lit(valor)) if expr is None else expr.when(cond, F.lit(valor))
    return expr


def da_lista(uc: Column, lista) -> Column:
    """Elemento uniforme de uma lista Python."""
    arr = F.array(*[F.lit(x) for x in lista])
    return F.element_at(arr, (F.floor(uc * len(lista)) + 1).cast("int"))


def entre(uc: Column, lo, hi) -> Column:
    return F.lit(lo) + uc * F.lit(hi - lo)


def entre_int(uc: Column, lo: int, hi: int) -> Column:
    """Inteiro uniforme em [lo, hi]."""
    return (F.lit(lo) + F.floor(uc * (hi - lo + 1))).cast("int")


def geometrica(uc: Column, q: Column, maximo: int) -> Column:
    """Nº de sucessos extras com probabilidade de continuar q (P(N>=k) = q^k)."""
    n = F.floor(F.log(F.greatest(uc, F.lit(1e-12))) / F.log(q))
    return F.least(n, F.lit(maximo)).cast("int")


_M40 = (1 << 40) - 1


def embaralhar(col: Column) -> Column:
    """Bijeção em [0, 2^40) para ids não sequenciais: (x*ímpar mod 2^40) e xorshift, duas rodadas.

    Multiplicadores pequenos mantêm o produto abaixo de 2^63 (sem overflow com ANSI ligado).
    """
    x = col.cast("long")
    for mult in (40_503, 52_429):
        x = (x * F.lit(mult)).bitwiseAND(F.lit(_M40))
        x = x.bitwiseXOR(F.shiftright(x, 20))
    return x + F.lit(10_000_000)


def ts_texto(ts_s: Column) -> Column:
    return F.date_format(F.timestamp_seconds(ts_s), "yyyy-MM-dd HH:mm:ss")


def data_texto(ts_s: Column) -> Column:
    return F.date_format(F.timestamp_seconds(ts_s), "yyyy-MM-dd")


# ---------------------------------------------------------------- calendário

PESO_DIA_SEMANA = [1.12, 1.10, 1.05, 1.00, 0.95, 0.85, 0.93]  # seg..dom
PESO_HORA = [0.6, 0.35, 0.2, 0.15, 0.15, 0.25, 0.5, 0.9, 1.3, 1.7, 2.0, 2.1,
             2.1, 2.0, 2.0, 2.0, 2.0, 2.1, 2.3, 2.7, 3.2, 3.4, 2.9, 1.6]
PERFIS = ["geral", "moda_beleza", "pet"]


def _black_friday(ano: int) -> date:
    d = date(ano, 11, 1)
    quintas = [d + timedelta(days=i) for i in range(30) if (d + timedelta(days=i)).weekday() == 3]
    return quintas[3] + timedelta(days=1)


def _dia_das_maes(ano: int) -> date:
    d = date(ano, 5, 1)
    domingos = [d + timedelta(days=i) for i in range(31) if (d + timedelta(days=i)).weekday() == 6]
    return domingos[1]


def peso_dia(d: date, idx: int, perfil: str) -> float:
    """Peso relativo de vendas no dia (tendência x dia da semana x datas sazonais)."""
    w = math.exp(math.log(1.5) / 365 * idx) * PESO_DIA_SEMANA[d.weekday()]
    bf = _black_friday(d.year)
    maes = _dia_das_maes(d.year)
    forte = {"geral": 1.0, "moda_beleza": 1.0, "pet": 0.5}[perfil]
    if d == bf:
        w *= 1 + 3.0 * forte
    elif d == bf + timedelta(days=3):  # Cyber Monday
        w *= 1 + 1.8 * forte
    elif bf - timedelta(days=4) <= d <= bf + timedelta(days=4):
        w *= 1 + 1.5 * forte
    elif d.month == 12 and d.day <= 22:
        w *= 1 + 0.4 * forte
    elif d.month == 12 and 23 <= d.day <= 26:
        w *= 0.8
    elif d.month == 1 and d.day == 1:
        w *= 0.6
    if maes - timedelta(days=8) <= d < maes:
        w *= 1.7 if perfil == "moda_beleza" else 1.15
    if date(d.year, 6, 4) <= d <= date(d.year, 6, 11):  # Dia dos Namorados
        w *= 1.5 if perfil == "moda_beleza" else 1.15
    return w


def tabelas_curva(ctx: Ctx):
    """(curva_cum, curva_bucket): CDF diária por perfil e lookup bucket -> dia."""
    linhas_cum, linhas_bkt = [], []
    for perfil in PERFIS:
        pesos = [peso_dia(ctx.inicio + timedelta(days=i), i, perfil) for i in range(DIAS_HISTORICO)]
        tot = sum(pesos)
        cum, acc = [], 0.0
        for i, w in enumerate(pesos):
            linhas_cum.append((perfil, i, acc / tot))
            acc += w
            cum.append(acc / tot)
        linhas_cum.append((perfil, DIAS_HISTORICO, 1.0))
        j = 0
        for b in range(BUCKETS_CURVA):
            alvo = (b + 0.5) / BUCKETS_CURVA
            while cum[j] < alvo:
                j += 1
            linhas_bkt.append((perfil, b, j))
    s = ctx.spark
    curva_cum = s.createDataFrame(linhas_cum, "perfil string, dia int, cum double")
    curva_bkt = s.createDataFrame(linhas_bkt, "perfil string, bucket int, dia_sorteado int")
    return curva_cum, curva_bkt


def sortear_dia(df: DataFrame, ctx: Ctx, curvas, col_lo: str, col_hi: str, col_u: str, saida: str) -> DataFrame:
    """Sorteia um dia em [lo, hi] (índices de dia, inclusive) seguindo a curva sazonal do perfil."""
    curva_cum, curva_bkt = curvas
    c_lo = curva_cum.select(F.col("perfil").alias("_p1"), F.col("dia").alias("_d1"), F.col("cum").alias("_c_lo"))
    c_hi = curva_cum.select(F.col("perfil").alias("_p2"), F.col("dia").alias("_d2"), F.col("cum").alias("_c_hi"))
    out = (
        df.join(F.broadcast(c_lo), (F.col("perfil") == F.col("_p1")) & (F.col(col_lo) == F.col("_d1")))
        .join(F.broadcast(c_hi), (F.col("perfil") == F.col("_p2")) & ((F.col(col_hi) + 1) == F.col("_d2")))
        .withColumn("_bucket", F.least(
            F.floor((F.col("_c_lo") + F.col(col_u) * (F.col("_c_hi") - F.col("_c_lo"))) * BUCKETS_CURVA),
            F.lit(BUCKETS_CURVA - 1)).cast("int"))
    )
    bkt = curva_bkt.select(F.col("perfil").alias("_p3"), F.col("bucket").alias("_b3"), "dia_sorteado")
    out = (
        out.join(F.broadcast(bkt), (F.col("perfil") == F.col("_p3")) & (F.col("_bucket") == F.col("_b3")))
        # o bucket pode cair um dia fora do intervalo nas bordas: prende em [lo, hi]
        .withColumn(saida, F.least(F.greatest(F.col("dia_sorteado"), F.col(col_lo)), F.col(col_hi)))
        .drop("_p1", "_d1", "_c_lo", "_p2", "_d2", "_c_hi", "_bucket", "_p3", "_b3", "dia_sorteado")
    )
    return out


def segundos_do_dia(ctx: Ctx, sal: str, *chaves) -> Column:
    """Segundo do dia seguindo a curva horária (pico 20h-22h)."""
    hora = escolher(u(ctx, sal + "_h", *chaves), list(enumerate(PESO_HORA)))
    return hora * 3600 + entre_int(u(ctx, sal + "_s", *chaves), 0, 3599)


# ---------------------------------------------------------------- escrita

def escrever_json(ctx: Ctx, df: DataFrame, fonte: str, arquivos: int | None = None, modo: str = "overwrite"):
    if arquivos:
        df = df.repartition(arquivos)
    df.write.mode(modo).option("compression", "gzip").json(f"{ctx.landing}/{fonte}")


def escrever_csv(ctx: Ctx, df: DataFrame, fonte: str, arquivos: int | None = None, modo: str = "overwrite"):
    if arquivos:
        df = df.repartition(arquivos)
    df.write.mode(modo).option("header", True).csv(f"{ctx.landing}/{fonte}")


def salvar_interno(ctx: Ctx, df: DataFrame, nome: str):
    df.write.mode("overwrite").parquet(f"{ctx.interno}/{nome}")


def ler_interno(ctx: Ctx, nome: str) -> DataFrame:
    return ctx.spark.read.parquet(f"{ctx.interno}/{nome}")
