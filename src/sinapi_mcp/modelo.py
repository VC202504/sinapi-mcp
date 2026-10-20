"""Tipos comuns às fontes e ao banco."""

from __future__ import annotations

from dataclasses import dataclass

from . import __version__

AGENTE = f"Mozilla/5.0 (compatible; sinapi-mcp/{__version__}; +https://github.com/VC202504/sinapi-mcp)"

UFS = ("AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ",
       "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO")

BASES = {
    "SINAPI": "SINAPI (Caixa e IBGE): 27 UFs, mensal, sem e com desoneração",
    "SICRO": "SICRO (DNIT): obras rodoviárias, por UF, trimestral",
    "ORSE": "ORSE (CEHOP, Sergipe): mensal, cobre itens que o SINAPI não traz",
    "SEINFRA": "SEINFRA (Ceará): por versão, sem e com desoneração",
}

# regime de encargos sociais: "sd" = sem desoneração (onerado), "cd" = com desoneração; "" = a base não separa
REGIMES = {"sd": "sem desoneração", "cd": "com desoneração", "": "único"}

# UF fixa das bases estaduais
UF_FIXA = {"ORSE": "SE", "SEINFRA": "CE"}


class ErroFonte(RuntimeError):
    """A fonte oficial não respondeu ou mudou de formato. A mensagem vai pronta para o usuário."""


@dataclass
class Item:
    codigo: str
    descricao: str
    unidade: str
    preco: float
    tipo: str = ""        # composicao | insumo
    grupo: str = ""


def rotulo_competencia(c: str) -> str:
    """"2026-09" → "09/2026"; versões ("028.1") ficam como estão."""
    return f"{c[5:]}/{c[:4]}" if len(c) == 7 and c[4] == "-" else c
