"""Linha de comando.

    sinapi-mcp                         inicia o servidor MCP (stdio), para Claude Desktop, Claude Code, Cursor etc.
    sinapi-mcp atualizar SINAPI        baixa a base do site oficial (opções: --uf PB,PE  --competencia 2026-09)
    sinapi-mcp buscar "concreto 25" --uf PB [--base SINAPI] [--regime cd]
    sinapi-mcp bases                   o que está no banco local
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sinapi-mcp", description="Preços oficiais de obras (SINAPI, SICRO, ORSE, SEINFRA) via MCP")
    ap.add_argument("--version", action="version", version=f"sinapi-mcp {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("servir", help="inicia o servidor MCP (padrão)")
    a = sub.add_parser("atualizar", help="baixa uma base do site oficial")
    a.add_argument("base", choices=["SINAPI", "SICRO", "ORSE", "SEINFRA", "sinapi", "sicro", "orse", "seinfra"])
    a.add_argument("--uf", default="", help="UFs separadas por vírgula (obrigatório no SICRO)")
    a.add_argument("--competencia", default=None, help="AAAA-MM (vazio = a mais recente)")
    b = sub.add_parser("buscar", help="busca no banco local")
    b.add_argument("texto")
    b.add_argument("--uf", default=None)
    b.add_argument("--base", default=None)
    b.add_argument("--regime", default="sd", choices=["sd", "cd"])
    b.add_argument("--limite", type=int, default=20)
    sub.add_parser("bases", help="o que está no banco local")
    args = ap.parse_args(argv)

    if args.cmd in (None, "servir"):
        from .servidor import rodar
        rodar()
        return 0
    for f in (sys.stdout, sys.stderr):
        if hasattr(f, "reconfigure"):
            f.reconfigure(encoding="utf-8")
    from . import servidor
    if args.cmd == "atualizar":
        from .atualizar import atualizar
        from .modelo import ErroFonte
        ufs = [u.strip() for u in args.uf.split(",") if u.strip()]
        try:
            pacs = atualizar(servidor.banco(), args.base, ufs, args.competencia,
                             aviso=lambda m: print(m, file=sys.stderr, flush=True))
        except ErroFonte as e:
            print(f"erro: {e}", file=sys.stderr)
            return 1
        print(f"{len(pacs)} pacote(s) gravado(s), {sum(p.itens for p in pacs)} preços, em {servidor.banco().caminho}")
        return 0
    if args.cmd == "buscar":
        print(servidor.buscar_precos(args.texto, args.uf, args.base, args.regime, None, None, args.limite))
        return 0
    if args.cmd == "bases":
        print(servidor.bases_disponiveis())
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
