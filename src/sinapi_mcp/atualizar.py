"""Baixa a competência de uma base no site oficial e grava no banco local."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .banco import Banco, Pacote
from .fontes import orse, seinfra, sicro, sinapi
from .modelo import UFS, ErroFonte

# abaixo disto o arquivo veio quebrado ou o formato mudou: não grava
MINIMO = {"SINAPI": 3000, "SICRO": 3000, "ORSE": 5000, "SEINFRA": 3000}


def atualizar(banco: Banco, base: str, ufs: list[str] | None = None, competencia: str | None = None,
              aviso=print, minimo: dict[str, int] | None = None) -> list[Pacote]:
    """Importa a competência pedida (a mais recente publicada, se vazia). `ufs` vale para o SICRO (obrigatório) e
    filtra o SINAPI (que vem nacional: sem filtro, entram as 27 UFs). Devolve os pacotes gravados."""
    base = base.upper()
    minimo = MINIMO if minimo is None else minimo
    ufs = [u.upper() for u in (ufs or [])]
    for u in ufs:
        if u not in UFS:
            raise ErroFonte(f"UF desconhecida: {u}")
    gravados: list[Pacote] = []

    def gravar(uf: str, regime: str, comp: str, itens) -> None:
        if len(itens) < minimo.get(base, 0):
            aviso(f"{base} {uf} {regime} {comp}: só {len(itens)} itens; não gravado (o formato da fonte mudou?)")
            return
        gravados.append(banco.importar(base, uf, regime, comp, itens))

    with tempfile.TemporaryDirectory(prefix="sinapi-mcp-") as t:
        pasta = Path(t)
        if base == "SINAPI":
            comp = competencia or sinapi.mais_recente()
            aviso(f"SINAPI {comp}: baixando o pacote nacional da Caixa (cerca de 16 MB)")
            for (uf, regime), itens in sorted(sinapi.obter(comp, pasta).items()):
                if not ufs or uf in ufs:
                    gravar(uf, regime, comp, itens)
        elif base == "SICRO":
            if not ufs:
                raise ErroFonte("o SICRO é publicado por UF: diga quais (ex.: PB, PE)")
            for uf in ufs:
                if competencia:
                    endereco = sicro.achar(uf, competencia)
                    if not endereco:
                        raise ErroFonte(f"o DNIT não publicou o SICRO {uf} de {competencia}")
                    comp = competencia
                else:
                    comp, endereco = sicro.mais_recente(uf)
                aviso(f"SICRO {uf} {comp}: baixando do site do DNIT")
                gravar(uf, "", comp, sicro.obter(uf, endereco, pasta))
        elif base == "ORSE":
            aviso("ORSE: lendo a consulta pública da CEHOP grupo a grupo (leva alguns minutos)")
            comp, itens = orse.obter(competencia, lambda n, tot: aviso(f"  grupo {n} de {tot}") if n % 25 == 0 else None)
            gravar("SE", "", comp, itens)
        elif base == "SEINFRA":
            for regime in ("sd", "cd"):
                versao, endereco, inseguro = seinfra.versao_no_site(regime)
                if competencia and competencia != versao:
                    aviso(f"SEINFRA: o site só oferece a versão em vigor ({versao}), não a {competencia}")
                if inseguro:
                    aviso("SEINFRA: o site respondeu com certificado inválido; a tabela foi lida assim mesmo, "
                          "confira alguns preços no site oficial")
                aviso(f"SEINFRA {regime} versão {versao}: baixando")
                gravar("CE", regime, versao, seinfra.obter(regime, endereco, pasta, inseguro))
        else:
            raise ErroFonte(f"base desconhecida: {base} (use SINAPI, SICRO, ORSE ou SEINFRA)")
    return gravados
