"""Etapa operação: tickets de atendimento (comprador -> loja e lojista -> plataforma)."""
from pyspark.sql import functions as F

import vocab as V
from comum import DIAS_HISTORICO, SEG_DIA, Ctx, da_lista, entre_int, escolher, escrever_json, ler_interno, ts_texto, u
from etapa_base import DIA_REAJUSTE
from etapa_pedidos import DIA_IOS_FIM, DIA_IOS_INI

TEXTOS = {
    "Onde está meu pedido?": [
        "Olá, meu pedido {pedido} ainda não chegou e o prazo já passou. O rastreio da {transportadora} não atualiza há {dias} dias.",
        "Comprei há mais de duas semanas e nada do pedido {pedido}. Podem verificar com a {transportadora}?",
        "Pedido {pedido} atrasado. Preciso dele com urgência, qual a nova previsão de entrega?",
        "Boa tarde! O pedido {pedido} consta como em trânsito há {dias} dias. Está tudo certo?"],
    "Troca ou devolução": [
        "Gostaria de devolver o pedido {pedido}, o tamanho não serviu.",
        "Quero trocar um item do pedido {pedido}. Como faço?",
        "Recebi o pedido {pedido}, mas não gostei. Quero o estorno."],
    "Produto com defeito": [
        "O produto do pedido {pedido} chegou com defeito.",
        "Um item do pedido {pedido} veio quebrado, quero a troca."],
    "Dúvida sobre pagamento": [
        "Paguei o pedido {pedido} via Pix, mas ainda aparece como pendente.",
        "Fui cobrado duas vezes no pedido {pedido}?",
        "Meu cartão foi recusado no pedido {pedido}. Por quê?"],
    "Cancelamento": [
        "Quero cancelar o pedido {pedido}.",
        "Desisti da compra do pedido {pedido}, podem cancelar?"],
    "Configuração da loja": [
        "Não consigo configurar meu domínio próprio na loja {loja}.",
        "Como altero o layout da página inicial da {loja}?"],
    "Integração com marketplace": [
        "Meus produtos não estão sincronizando com o marketplace.",
        "Os pedidos do marketplace não aparecem no painel da {loja}."],
    "Meios de pagamento": [
        "Os pagamentos via Pix estão demorando para compensar.",
        "Como ativo o parcelamento sem juros na {loja}?"],
    "Frete e envios": [
        "A {transportadora} está atrasando muitas entregas dos meus clientes.",
        "Como configuro frete grátis acima de um valor?"],
    "Plano e cobrança": [
        "Recebi o aviso de reajuste do plano Inicial e o valor subiu muito. Estou pensando em cancelar.",
        "Por que a mensalidade aumentou para R$ 69?",
        "Quero mudar de plano, o Inicial ficou caro para o meu volume."],
    "Problema no checkout": [
        "Clientes estão reclamando que o checkout trava no iPhone.",
        "Muitos carrinhos abandonados no iOS desde a última atualização.",
        "No Safari, o botão de finalizar compra não funciona."],
}
ASSUNTOS_COMPRADOR = [("Onde está meu pedido?", 35), ("Troca ou devolução", 20), ("Produto com defeito", 15),
                      ("Dúvida sobre pagamento", 15), ("Cancelamento", 15)]
ASSUNTOS_LOJISTA = [("Configuração da loja", 30), ("Integração com marketplace", 20), ("Meios de pagamento", 20),
                    ("Frete e envios", 20), ("Plano e cobrança", 10)]


def _texto(ctx: Ctx, chave: str):
    """Sorteia o template do assunto e preenche os campos."""
    tpl = F.lit(None).cast("string")
    for assunto, lista in TEXTOS.items():
        tpl = F.when(F.col("assunto") == assunto, da_lista(u(ctx, "tpl", chave), lista)).otherwise(tpl)
    t = F.regexp_replace(tpl, "\\{pedido\\}", F.concat(F.lit("#"), F.coalesce(F.col("pedido_id").cast("string"), F.lit(""))))
    t = F.regexp_replace(t, "\\{transportadora\\}", F.coalesce(F.col("transportadora"), F.lit("transportadora")))
    t = F.regexp_replace(t, "\\{dias\\}", entre_int(u(ctx, "tdias", chave), 3, 9).cast("string"))
    return F.regexp_replace(t, "\\{loja\\}", F.col("nome_loja"))


def rodar(ctx: Ctx):
    a = F.lit(ctx.ancora_s)
    p = ler_interno(ctx, "pedidos").where(F.col("tipo") != "teste")
    lojas = ler_interno(ctx, "lojas")
    nomes = lojas.select("loja_id", "nome_loja")
    s = "seq"
    atrasado = F.col("envia") & ((F.col("atraso_dias") >= 3) | F.col("extraviado"))
    devolvido = F.col("ts_devolvido").isNotNull()
    prob = F.when(atrasado, 0.35).when(devolvido, 0.5).otherwise(0.012)
    comp = (
        p.where(u(ctx, "tk", s) < prob)
        .withColumn("assunto", F.when(atrasado, "Onde está meu pedido?").when(devolvido, "Troca ou devolução")
                    .otherwise(escolher(u(ctx, "tkas", s), ASSUNTOS_COMPRADOR)))
        .withColumn("ts_aberto", F.when(atrasado, F.col("ts_postagem") + (F.col("prazo_prometido") + 1) * SEG_DIA)
                    .when(devolvido, F.col("ts_entrega") + entre_int(u(ctx, "tkd", s), 2 * SEG_DIA, 6 * SEG_DIA))
                    .otherwise(F.col("ts_pedido") + entre_int(u(ctx, "tkb", s), SEG_DIA, 10 * SEG_DIA)))
        .withColumn("csat", F.when(u(ctx, "csatnull", s) < 0.4, None)
                    .when(atrasado, entre_int(u(ctx, "csat", s), 1, 3)).otherwise(entre_int(u(ctx, "csat", s), 3, 5)))
        .select(F.concat(F.lit("TK"), F.col("pedido_id").cast("string")).alias("ticket_id"),
                F.lit("comprador_loja").alias("origem"), "loja_id", "pedido_id", "transportadora", "assunto",
                escolher(u(ctx, "tkcanal", s), [("email", 40), ("chat", 35), ("whatsapp", 25)]).alias("canal"),
                "ts_aberto", "csat", F.col("seq").cast("string").alias("chave"))
    )
    # lojista -> plataforma: ~1 por mês ativo + picos das histórias H3 (reajuste) e H7 (checkout iOS)
    k = "chave"
    meses = (
        lojas.select("loja_id", "inicio_ativo", "fim_idx", "afetado_reajuste",
                     F.explode(F.sequence(F.lit(0), F.lit(DIAS_HISTORICO // 30 - 1))).alias("mes"))
        .withColumn("dia_ini", F.col("mes") * 30)
        .where((F.col("dia_ini") >= F.col("inicio_ativo")) & (F.col("dia_ini") <= F.col("fim_idx")))
        .withColumn("chave", F.concat_ws("|", "loja_id", "mes"))
        .withColumn("n", escolher(u(ctx, "ltn", k), [(0, 45), (1, 35), (2, 15), (3, 5)]))
        .where("n > 0")
        .withColumn("i", F.explode(F.sequence(F.lit(1), F.col("n"))))
        .withColumn("chave", F.concat_ws("|", "chave", "i"))
        .withColumn("assunto", escolher(u(ctx, "ltas", k), ASSUNTOS_LOJISTA))
        .withColumn("dia", F.least(F.col("dia_ini") + entre_int(u(ctx, "ltd", k), 0, 29), F.col("fim_idx")))
    )
    h3 = (
        lojas.where(F.col("afetado_reajuste") & (F.col("inicio_ativo") <= DIA_REAJUSTE) & (F.col("fim_idx") >= DIA_REAJUSTE))
        .withColumn("chave", F.concat_ws("|", "loja_id", F.lit("h3")))
        .where(u(ctx, "h3", k) < 0.45)
        .withColumn("assunto", F.lit("Plano e cobrança"))
        .withColumn("dia", F.least(F.lit(DIA_REAJUSTE) + entre_int(u(ctx, "h3d", k), 0, 45), F.col("fim_idx")))
    )
    h7 = (
        lojas.where((F.col("inicio_ativo") <= DIA_IOS_INI) & (F.col("fim_idx") >= DIA_IOS_FIM))
        .withColumn("chave", F.concat_ws("|", "loja_id", F.lit("h7")))
        .where(u(ctx, "h7", k) < 0.30)
        .withColumn("assunto", F.lit("Problema no checkout"))
        .withColumn("dia", entre_int(u(ctx, "h7d", k), DIA_IOS_INI, DIA_IOS_FIM - 1))
    )
    cols = ["loja_id", "chave", "assunto", "dia"]
    loj = (
        meses.select(*cols).unionByName(h3.select(*cols)).unionByName(h7.select(*cols))
        .withColumn("ts_aberto", F.lit(ctx.inicio_s).cast("long") + F.col("dia") * SEG_DIA + entre_int(u(ctx, "lth", k), 8 * 3600, 20 * 3600))
        .select(F.concat(F.lit("TL"), F.substring(F.md5(F.concat(F.col("chave"), F.lit(ctx.seed))), 1, 12)).alias("ticket_id"),
                F.lit("lojista_plataforma").alias("origem"), "loja_id", F.lit(None).cast("long").alias("pedido_id"),
                da_lista(u(ctx, "ltt", k), [t for t, _ in V.TRANSPORTADORAS]).alias("transportadora"), "assunto",
                escolher(u(ctx, "ltc", k), [("email", 50), ("chat", 50)]).alias("canal"), "ts_aberto",
                F.when(u(ctx, "lcsn", k) < 0.5, None).otherwise(entre_int(u(ctx, "lcs", k), 2, 5)).alias("csat"), "chave")
    )
    tickets = (
        comp.unionByName(loj).where(F.col("ts_aberto") < a)
        .join(F.broadcast(nomes), "loja_id")
        .withColumn("texto", _texto(ctx, "chave"))
        .withColumn("ts_resolvido", F.col("ts_aberto") + entre_int(u(ctx, "res", "chave"), 2 * 3600, 5 * SEG_DIA))
        .select("ticket_id", "origem", "loja_id", "pedido_id", "canal", "assunto", "texto",
                ts_texto(F.col("ts_aberto")).alias("aberto_em"),
                F.when(F.col("ts_resolvido") < a, ts_texto(F.col("ts_resolvido"))).alias("resolvido_em"),
                F.when(F.col("ts_resolvido") < a, F.col("csat")).alias("csat"))
    )
    escrever_json(ctx, tickets, "tickets", arquivos=16)
    print("tickets ok")
