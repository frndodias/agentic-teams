"""Ponto de entrada do gerador: python gerar.py --etapa <base|pedidos|operacao|eventos_web|marketing|gabarito>."""
import os
import sys

# Em tarefas Python serverless o script roda via exec() e __file__ não existe: usa sys.argv[0].
_script = globals().get("__file__") or sys.argv[0]
sys.path.insert(0, os.path.dirname(os.path.abspath(_script)))

from comum import criar_ctx, ler_args  # noqa: E402


def main():
    args = ler_args()
    ctx = criar_ctx(args)
    print(f"etapa={args.etapa} escala={ctx.escala} ancora={ctx.ancora} lojas={ctx.n_lojas} "
          f"pessoas={ctx.n_pessoas} relacoes={ctx.n_relacoes} pedidos~{ctx.n_pedidos}")
    if args.etapa == "base":
        import etapa_base as e
    elif args.etapa == "pedidos":
        import etapa_pedidos as e
    elif args.etapa == "operacao":
        import etapa_operacao as e
    elif args.etapa == "eventos_web":
        import etapa_web as e
    elif args.etapa == "marketing":
        import etapa_marketing as e
    elif args.etapa == "gabarito":
        import etapa_gabarito as e
    else:
        raise SystemExit(f"etapa desconhecida: {args.etapa}")
    e.rodar(ctx)


if __name__ == "__main__":
    main()
