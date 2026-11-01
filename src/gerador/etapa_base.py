"""Etapa base: lojas, assinaturas, catálogo, estoque, pessoas, relações pessoa-loja e compradores."""

from pyspark.sql import Window
from pyspark.sql import functions as F

import vocab as V
from comum import (DIAS_HISTORICO, SEG_DIA, Ctx, da_lista, data_texto, embaralhar, entre, entre_int,
                   escolher, escrever_csv, escrever_json, geometrica, salvar_interno, segundos_do_dia,
                   sortear_dia, tabelas_curva, ts_texto, u)

DIA_REAJUSTE = DIAS_HISTORICO - 150  # H3: reajuste do plano Inicial há ~5 meses
N_FRAUDE_POR_LOJA = 0.004  # H2: ~40 lojas na escala M


def _tabela_segmentos(ctx: Ctx):
    linhas = []
    for seg, _ in V.SEGMENTOS:
        linhas.append((seg, V.PERFIL_SAZONAL.get(seg, "geral"), V.PREFIXOS_LOJA[seg], V.MARCAS[seg],
                       [c[0] for c in V.CATALOGO[seg]]))
    return ctx.spark.createDataFrame(
        linhas, "segmento string, perfil string, prefixos array<string>, marcas array<string>, categorias array<string>")


def _tabela_ufs(ctx: Ctx):
    linhas = [(uf, r, ddd, lo, hi, cid) for uf, (r, ddd, lo, hi, cid) in V.UFS.items()]
    return ctx.spark.createDataFrame(
        linhas, "uf string, regiao string, ddd int, cep_min int, cep_max int, cidades array<string>")


def _tabela_categorias(ctx: Ctx):
    """(segmento, bucket 0..99) -> categoria, faixa de preço e tipos."""
    linhas = []
    for seg, cats in V.CATALOGO.items():
        tot = sum(c[1] for c in cats)
        b = 0
        for i, (cat, peso, pmin, pmax, tipos) in enumerate(cats):
            n = 100 - b if i == len(cats) - 1 else round(100 * peso / tot)
            for _ in range(n):
                linhas.append((seg, b, cat, float(pmin), float(pmax), tipos))
                b += 1
    return ctx.spark.createDataFrame(
        linhas, "segmento string, bucket int, categoria string, pmin double, pmax double, tipos array<string>")


def _pick(arr_col: str, uc):
    return F.element_at(F.col(arr_col), (F.floor(uc * F.size(F.col(arr_col))) + 1).cast("int"))


# ---------------------------------------------------------------- lojas

def gerar_lojas(ctx: Ctx):
    k = "num"
    segs = F.broadcast(_tabela_segmentos(ctx))
    ufs = F.broadcast(_tabela_ufs(ctx))
    df = (
        ctx.spark.range(ctx.n_lojas).withColumnRenamed("id", "num")
        .withColumn("loja_id", F.concat(F.lit("L"), F.lpad((F.col("num") + 1).cast("string"), 6, "0")))
        .withColumn("segmento", escolher(u(ctx, "seg", k), V.SEGMENTOS))
        .withColumn("uf", escolher(u(ctx, "uf_loja", k), V.UF_LOJAS))
        .withColumn("peso", F.least(F.pow(1 - u(ctx, "peso", k), F.lit(-1 / 1.3)), F.lit(200.0)))
        .withColumn("tier", F.when(F.col("peso") > 30, "Enterprise").when(F.col("peso") > 5, "Mid").otherwise("SMB"))
        .join(segs, "segmento").join(ufs, "uf")
        .withColumn("nome_loja", F.concat_ws(" ", _pick("prefixos", u(ctx, "pref", k)),
                                             da_lista(u(ctx, "nome", k), V.NOMES_LOJA)))
        .withColumn("subsegmento", _pick("categorias", u(ctx, "subseg", k)))
        .withColumn("cidade", _pick("cidades", u(ctx, "cid_loja", k)))
        # 25% das lojas abriram dentro da janela de histórico; as demais até 6 anos antes
        .withColumn("abertura_idx", F.when(
            u(ctx, "nova", k) < 0.25, entre_int(u(ctx, "abre", k), 0, DIAS_HISTORICO - 30)
        ).otherwise(-entre_int(u(ctx, "abre", k), 1, 6 * 365)))
    )
    plano = (
        F.when(F.col("tier") == "SMB", escolher(u(ctx, "plano", k), [("Inicial", 50), ("Básico", 35), ("Essencial", 15)]))
        .when(F.col("tier") == "Mid", escolher(u(ctx, "plano", k), [("Básico", 20), ("Essencial", 45), ("Profissional", 35)]))
        .otherwise(escolher(u(ctx, "plano", k), [("Profissional", 40), ("Avançado", 60)]))
    )
    churn = F.create_map(*[x for p, c in V.CHURN_MENSAL.items() for x in (F.lit(p), F.lit(c / 30))])
    df = (
        df.withColumn("plano_inicial", plano)
        .withColumn("inicio_ativo", F.greatest(F.col("abertura_idx"), F.lit(0)))
        .withColumn("tem_upgrade", (u(ctx, "upg", k) < 0.15) & (F.col("plano_inicial") != "Avançado"))
        .withColumn("upgrade_idx", F.when(F.col("tem_upgrade"), F.col("inicio_ativo") + F.floor(
            u(ctx, "upg_d", k) * (DIAS_HISTORICO - F.col("inicio_ativo"))).cast("int")))
        # H3: só o Inicial que ainda era Inicial no reajuste sofre o aumento de churn
        .withColumn("afetado_reajuste", (F.col("plano_inicial") == "Inicial") & (
            F.col("upgrade_idx").isNull() | (F.col("upgrade_idx") > DIA_REAJUSTE)))
        .withColumn("r0", churn[F.col("plano_inicial")] * F.when(F.col("peso") < 1.5, 1.4).otherwise(1.0))
        .withColumn("r1", F.col("r0") * F.when(F.col("afetado_reajuste"), 2.2).otherwise(1.0))
        .withColumn("r2", F.col("r0") * F.when(F.col("afetado_reajuste"), 1.4).otherwise(1.0))
    )
    # Tempo até o churn por inversão da taxa acumulada (3 trechos: antes / 90 dias após / depois do reajuste)
    a = F.col("inicio_ativo").cast("double")
    p1 = F.greatest(a, F.lit(float(DIA_REAJUSTE)))
    p2 = F.greatest(a, F.lit(float(DIA_REAJUSTE + 90)))
    e = -F.log(F.greatest(u(ctx, "churn", k), F.lit(1e-12)))
    h1 = F.col("r0") * (p1 - a)
    h2 = F.col("r1") * (p2 - p1)
    t = (F.when(e <= h1, a + e / F.col("r0"))
         .when(e <= h1 + h2, p1 + (e - h1) / F.col("r1"))
         .otherwise(p2 + (e - h1 - h2) / F.col("r2")))
    df = (
        df.withColumn("churn_idx", F.floor(t).cast("int"))
        .withColumn("churnou", F.col("churn_idx") < DIAS_HISTORICO)
        .withColumn("fim_idx", F.when(F.col("churnou"), F.col("churn_idx")).otherwise(DIAS_HISTORICO - 1))
        .withColumn("upgrade_idx", F.when(F.col("upgrade_idx") < F.col("fim_idx"), F.col("upgrade_idx")))
        .withColumn("dias_ativos", F.col("fim_idx") - F.col("inicio_ativo") + 1)
        .withColumn("n_produtos", F.least(F.greatest(
            F.round(15 + 40 * F.pow(F.col("peso"), 0.6)), F.lit(15)), F.lit(600)).cast("int"))
        .withColumn("frete_gratis_min", escolher(u(ctx, "fg", k), [(0.0, 40), (149.0, 15), (199.0, 30), (299.0, 15)]))
    )
    # H2: lojas de Eletrônicos ativas há pelo menos 60 dias recebem o grupo de fraude
    n_fraude = max(2, round(ctx.n_lojas * N_FRAUDE_POR_LOJA))
    elegivel = (F.col("segmento") == "Eletrônicos") & ~F.col("churnou") & (F.col("abertura_idx") < DIAS_HISTORICO - 60)
    w = Window.orderBy(F.when(elegivel, 0).otherwise(1), u(ctx, "fraude_rank", k))
    df = df.withColumn("loja_fraude", elegivel & (F.row_number().over(w) <= n_fraude))
    return df.drop("prefixos", "categorias", "cidades", "ddd", "cep_min", "cep_max", "r0", "r1", "r2")


def exportar_lojas(ctx: Ctx, lojas):
    inicio = F.lit(ctx.inicio_s)
    b_lojas = lojas.select(
        "loja_id", "nome_loja", "segmento", "subsegmento", "uf", "cidade", "tier",
        data_texto(inicio + F.col("abertura_idx") * SEG_DIA).alias("data_abertura"),
        F.when(F.col("churnou"), "inativa").otherwise("ativa").alias("status"),
        F.when(F.col("churnou"), data_texto(inicio + F.col("churn_idx") * SEG_DIA)).alias("data_churn"),
    )
    escrever_csv(ctx, b_lojas, "lojas", arquivos=1)

    preco = F.create_map(*[x for p, c in V.PRECO_PLANO.items() for x in (F.lit(p), F.lit(c))])
    proximo = F.create_map(*[x for i, p in enumerate(V.PLANOS[:-1]) for x in (F.lit(p), F.lit(V.PLANOS[i + 1]))])
    plano_upg = proximo[F.col("plano_inicial")]
    ev = [
        lojas.select("loja_id", F.lit("novo").alias("tipo"), F.col("plano_inicial").alias("plano"),
                     preco[F.col("plano_inicial")].alias("preco_mensal"), F.col("abertura_idx").alias("dia")),
        lojas.where(F.col("upgrade_idx").isNotNull()).select(
            "loja_id", F.lit("upgrade").alias("tipo"), plano_upg.alias("plano"),
            preco[plano_upg].alias("preco_mensal"), F.col("upgrade_idx").alias("dia")),
        lojas.where(F.col("afetado_reajuste") & (F.col("abertura_idx") <= DIA_REAJUSTE)
                    & (F.col("fim_idx") >= DIA_REAJUSTE)).select(
            "loja_id", F.lit("reajuste").alias("tipo"), F.lit("Inicial").alias("plano"),
            F.lit(V.PRECO_INICIAL_REAJUSTADO).alias("preco_mensal"), F.lit(DIA_REAJUSTE).alias("dia")),
        lojas.where("churnou").select(
            "loja_id", F.lit("cancelamento").alias("tipo"), F.lit(None).cast("string").alias("plano"),
            F.lit(None).cast("double").alias("preco_mensal"), F.col("churn_idx").alias("dia")),
    ]
    eventos = ev[0].unionByName(ev[1]).unionByName(ev[2]).unionByName(ev[3])
    eventos = eventos.withColumn("ts", inicio + F.col("dia") * SEG_DIA + segundos_do_dia(ctx, "ass", "loja_id", "tipo"))
    eventos = eventos.select(
        F.substring(F.md5(F.concat_ws("|", "loja_id", "tipo", F.lit(ctx.seed))), 1, 16).alias("evento_id"),
        "loja_id", "tipo", "plano", "preco_mensal", ts_texto(F.col("ts")).alias("ocorrido_em"))
    escrever_json(ctx, eventos, "assinaturas_eventos", arquivos=1)


# ---------------------------------------------------------------- catálogo e estoque

def gerar_produtos(ctx: Ctx, lojas):
    cats = F.broadcast(_tabela_categorias(ctx))
    k = "produto_id"
    df = (
        lojas.select("loja_id", "segmento", "marcas", "inicio_ativo", "abertura_idx",
                     F.explode(F.sequence(F.lit(0), F.col("n_produtos") - 1)).alias("idx"))
        .withColumn("produto_id", F.concat("loja_id", F.lit("-P"), F.lpad(F.col("idx").cast("string"), 4, "0")))
        .withColumn("bucket", F.floor(u(ctx, "cat", k) * 100).cast("int"))
        .join(cats, ["segmento", "bucket"])
        .withColumn("subcategoria", _pick("tipos", u(ctx, "tipo", k)))
        .withColumn("marca", _pick("marcas", u(ctx, "marca", k)))
        .withColumn("nome", F.concat_ws(" ", "subcategoria", "marca", da_lista(u(ctx, "adj", k), V.ADJETIVOS)))
        # preço log-uniforme na faixa da categoria, terminando em ,90
        .withColumn("preco", F.floor(F.exp(F.log("pmin") + u(ctx, "preco", k) * (F.log("pmax") - F.log("pmin")))) + 0.9)
        .withColumn("custo", F.round(F.col("preco") * entre(u(ctx, "custo", k), 0.35, 0.6), 2))
        .withColumn("peso_g", entre_int(u(ctx, "pg", k), 50, 5000))
        .withColumn("ativo", u(ctx, "ativo", k) >= 0.08)
        .withColumn("sku", F.upper(F.substring(F.md5(F.concat(F.col(k), F.lit(ctx.seed))), 1, 10)))
        .withColumn("criacao_idx", F.col("inicio_ativo") + F.floor(
            u(ctx, "pcria", k) * F.greatest(F.lit(1), DIAS_HISTORICO - F.col("inicio_ativo")) * 0.5).cast("int"))
    )
    return df.select("produto_id", "loja_id", "idx", "sku", "nome", "categoria", "subcategoria", "marca",
                     "preco", "custo", "peso_g", "ativo", "criacao_idx")


def exportar_produtos(ctx: Ctx, produtos):
    b = produtos.select("produto_id", "loja_id", "sku", "nome", "categoria", "subcategoria", "marca", "preco",
                        "custo", "peso_g", "ativo",
                        data_texto(F.lit(ctx.inicio_s) + F.greatest(F.col("criacao_idx"), F.lit(-3000)) * SEG_DIA)
                        .alias("data_criacao"))
    escrever_json(ctx, b, "produtos")
    k = "produto_id"
    estoque = produtos.select(
        "produto_id", "loja_id",
        F.when(u(ctx, "ruptura", k) < 0.06, 0).otherwise(
            F.floor(F.pow(u(ctx, "qtd", k), 2.0) * 500) + 1).cast("int").alias("quantidade"),
        ts_texto(F.lit(ctx.ancora_s) - entre_int(u(ctx, "est_ts", k), 600, 172_800)).alias("atualizado_em"))
    escrever_csv(ctx, estoque, "estoque", arquivos=4)


# ---------------------------------------------------------------- pessoas, relações e compradores

def _cpf(ctx: Ctx, sal: str, k: str):
    """CPF de 11 dígitos com dígitos verificadores válidos."""
    base = F.lpad(F.floor(u(ctx, sal, k) * 999_999_998 + 1).cast("long").cast("string"), 9, "0")
    d = [F.substring(base, i + 1, 1).cast("int") for i in range(9)]
    s1 = sum(d[i] * (10 - i) for i in range(9))
    dv1 = F.when(F.pmod(s1 * 10, F.lit(11)) == 10, 0).otherwise(F.pmod(s1 * 10, F.lit(11)))
    s2 = sum(d[i] * (11 - i) for i in range(9)) + dv1 * 2
    dv2 = F.when(F.pmod(s2 * 10, F.lit(11)) == 10, 0).otherwise(F.pmod(s2 * 10, F.lit(11)))
    return F.concat(base, dv1.cast("string"), dv2.cast("string"))


def formatar_cpf(cpf):
    return F.concat(F.substring(cpf, 1, 3), F.lit("."), F.substring(cpf, 4, 3), F.lit("."),
                    F.substring(cpf, 7, 3), F.lit("-"), F.substring(cpf, 10, 2))


_ACENTOS, _SEM_ACENTO = "áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ", "aaaaeeiooouucAAAAEEIOOOUUC"


def gerar_pessoas(ctx: Ctx, n: int, sal: str, offset: int = 0):
    ufs = F.broadcast(_tabela_ufs(ctx))
    k = "pessoa_id"
    df = (
        ctx.spark.range(offset, offset + n).withColumnRenamed("id", "pessoa_id")
        .withColumn("primeiro_nome", da_lista(u(ctx, sal + "pn", k), V.PRIMEIROS_NOMES))
        .withColumn("sobrenome", F.concat_ws(" ", da_lista(u(ctx, sal + "sn1", k), V.SOBRENOMES),
                                             da_lista(u(ctx, sal + "sn2", k), V.SOBRENOMES)))
        .withColumn("nome", F.concat_ws(" ", "primeiro_nome", "sobrenome"))
        .withColumn("uf", escolher(u(ctx, sal + "uf", k), V.UF_PESSOAS))
        .join(ufs, "uf")
        .withColumn("cidade", _pick("cidades", u(ctx, sal + "cid", k)))
        .withColumn("cep", F.concat(
            F.lpad((F.col("cep_min") + F.floor(u(ctx, sal + "cep1", k) * (F.col("cep_max") - F.col("cep_min") + 1)))
                   .cast("int").cast("string"), 2, "0"),
            F.lpad(F.floor(u(ctx, sal + "cep2", k) * 1000).cast("int").cast("string"), 3, "0"), F.lit("-"),
            F.lpad(F.floor(u(ctx, sal + "cep3", k) * 1000).cast("int").cast("string"), 3, "0")))
        .withColumn("telefone", F.concat(F.lit("("), F.col("ddd").cast("string"), F.lit(") 9"),
                                         F.lpad(F.floor(u(ctx, sal + "tel", k) * 1e8).cast("long").cast("string"), 8, "0")))
        .withColumn("cpf", _cpf(ctx, sal + "cpf", k))
        .withColumn("email", F.concat(
            F.lower(F.translate(F.col("primeiro_nome"), _ACENTOS, _SEM_ACENTO)), F.lit("."),
            F.lower(F.translate(F.element_at(F.split("sobrenome", " "), 1), _ACENTOS, _SEM_ACENTO)),
            F.when(u(ctx, sal + "emn", k) < 0.6, F.floor(u(ctx, sal + "emnum", k) * 999).cast("int").cast("string"))
            .otherwise(F.lit("")),
            F.lit("@"), escolher(u(ctx, sal + "prov", k), V.PROVEDORES_EMAIL)))
    )
    return df.drop("cidades", "cep_min", "cep_max", "ddd", "primeiro_nome", "sobrenome")


def gerar_relacoes(ctx: Ctx, lojas, pessoas, curvas):
    """Cada relação = uma pessoa comprando numa loja (12% das pessoas compram em 2-3 lojas)."""
    k = "pessoa_id"
    # slots de loja proporcionais a peso x dias ativos (amostragem ponderada por equi-join)
    tot = lojas.agg(F.sum(F.col("peso") * F.col("dias_ativos")).alias("t")).first()["t"]
    fator = tot / 200_000
    w = Window.orderBy("num").rowsBetween(Window.unboundedPreceding, -1)
    slots = (
        lojas.select("num", "loja_id", F.greatest(F.lit(1), F.round(F.col("peso") * F.col("dias_ativos") / fator))
                     .cast("long").alias("n_slots"))
        .withColumn("ini", F.coalesce(F.sum("n_slots").over(w), F.lit(0)))
        .select("loja_id", F.explode(F.sequence(F.col("ini"), F.col("ini") + F.col("n_slots") - 1)).alias("slot"))
    )
    n_slots = slots.count()
    rel = (
        pessoas.withColumn("n_lojas", F.when(u(ctx, "multi", k) < 0.12,
                                             F.when(u(ctx, "multi3", k) < 0.3, 3).otherwise(2)).otherwise(1))
        .withColumn("j", F.explode(F.sequence(F.lit(1), F.col("n_lojas"))))
        .withColumn("rel_num", F.col("pessoa_id") * 4 + F.col("j"))
        .withColumn("slot", F.floor(u(ctx, "slot", "rel_num") * n_slots).cast("long"))
        .join(F.broadcast(slots), "slot")
        # mesma pessoa sorteando a mesma loja duas vezes: fica só a primeira (determinístico)
        .withColumn("_rn", F.row_number().over(Window.partitionBy("pessoa_id", "loja_id").orderBy("j")))
        .where("_rn = 1")
        .drop("slot", "j", "n_lojas", "_rn")
    )
    loja_cols = lojas.select("loja_id", "segmento", "perfil", "inicio_ativo", "fim_idx",
                             F.col("uf").alias("uf_loja"), F.col("regiao").alias("regiao_loja"),
                             "frete_gratis_min", "loja_fraude")
    rel = rel.join(F.broadcast(loja_cols), "loja_id")
    r = "rel_num"
    # calibrado no XS: recompra 90d ~15% geral, Pet ~3x a média, WhatsApp ~2x Ads (gabarito confere)
    seg_mult = (F.when(F.col("segmento") == "Pet Shop", 5.5)
                .when(F.col("segmento").isin("Alimentos & Bebidas", "Saúde & Bem-estar"), 1.3)
                .when(F.col("segmento") == "Beleza & Cosméticos", 1.2).otherwise(1.0))
    canal_mult = (F.when(F.col("canal_aquisicao") == "WhatsApp", 2.0)
                  .when(F.col("canal_aquisicao").isin("Anúncios Meta", "Anúncios Google"), 0.6)
                  .when(F.col("canal_aquisicao") == "Indicação", 1.2)
                  .when(F.col("canal_aquisicao") == "Marketplace", 0.8).otherwise(1.0))
    pet = F.col("segmento") == "Pet Shop"
    rel = (
        rel.withColumn("canal_aquisicao", escolher(u(ctx, "canal_aq", r), V.CANAIS_AQUISICAO))
        .withColumn("recorrente", u(ctx, "recorr", r) < F.least(F.lit(0.08) * seg_mult * canal_mult, F.lit(0.85)))
        .withColumn("q", F.when(pet, 0.90).otherwise(0.76))
        .withColumn("n_pedidos", F.when(F.col("recorrente"), 1 + geometrica(u(ctx, "npd", r), F.col("q"), 39))
                    .otherwise(1))
        .withColumn("span", F.when(pet, entre_int(u(ctx, "span", r), 150, 420))
                    .otherwise(entre_int(u(ctx, "span", r), 120, 720)))
        .withColumn("u_t0", u(ctx, "t0", r))
    )
    rel = sortear_dia(rel, ctx, curvas, "inicio_ativo", "fim_idx", "u_t0", "t0")
    rel = (
        rel.withColumn("t1", F.least(F.col("t0") + F.col("span"), F.col("fim_idx")))
        .withColumn("comprador_id", embaralhar(F.col("rel_num") * 2))
        # Armadilha: parte dos recorrentes às vezes compra como convidado, e cada checkout de convidado
        # cria um cadastro novo (ver etapa_pedidos). Pelo comprador_id cru, o recorrente vira vários "compradores de 1 pedido".
        .withColumn("compra_convidado", F.col("recorrente") & (u(ctx, "conv", r) < 0.45))
        .withColumn("tipo_cadastro", F.when(u(ctx, "tipo_cad", r) < 0.75, "conta").otherwise("convidado"))
        .drop("q", "span", "u_t0")
    )
    return rel


def compradores_de(ctx: Ctx, rel):
    """Cadastro principal de cada relação (os cadastros de convidado nascem por pedido, na etapa pedidos)."""
    r = "rel_num"
    inicio = F.lit(ctx.inicio_s)
    cpf_principal = F.when(u(ctx, "cpf_fmt", r) < 0.2, formatar_cpf(F.col("cpf"))).otherwise(F.col("cpf"))
    principal = rel.select(
        F.col("comprador_id"), "loja_id", "nome", "email", cpf_principal.alias("cpf"), "telefone", "cep", "cidade",
        "uf", data_texto(inicio + F.greatest(F.col("t0") - entre_int(u(ctx, "cad", r), 0, 30), F.col("inicio_ativo"))
                         * SEG_DIA).alias("data_cadastro"),
        "tipo_cadastro", "canal_aquisicao")
    return principal


def rodar(ctx: Ctx):
    curvas = tabelas_curva(ctx)
    lojas = gerar_lojas(ctx)
    salvar_interno(ctx, lojas, "lojas")
    lojas = ctx.spark.read.parquet(f"{ctx.interno}/lojas")
    exportar_lojas(ctx, lojas)

    produtos = gerar_produtos(ctx, lojas)
    salvar_interno(ctx, produtos, "produtos")
    produtos = ctx.spark.read.parquet(f"{ctx.interno}/produtos")
    exportar_produtos(ctx, produtos)

    pessoas = gerar_pessoas(ctx, ctx.n_pessoas, "p")
    rel = gerar_relacoes(ctx, lojas, pessoas, curvas)
    salvar_interno(ctx, rel, "relacoes")
    rel = ctx.spark.read.parquet(f"{ctx.interno}/relacoes")
    escrever_csv(ctx, compradores_de(ctx, rel), "compradores")
    st = rel.agg(F.count("*").alias("rel"), F.sum("n_pedidos").alias("ped")).first()
    print(f"base ok: lojas={lojas.count()} produtos={produtos.count()} relacoes={st['rel']} "
          f"pedidos_normais={st['ped']} pedidos_por_relacao={st['ped'] / st['rel']:.3f}")
