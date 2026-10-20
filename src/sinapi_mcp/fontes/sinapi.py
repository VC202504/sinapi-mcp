"""SINAPI (Caixa e IBGE): do pacote mensal nacional às bases por UF e regime.

Fonte: https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/SINAPI-AAAA-MM-formato-xlsx.zip (cerca de 16 MB),
com a planilha SINAPI_Referência_AAAA_MM.xlsx: uma coluna de custo por UF nas abas CSD e CCD (composições sem e com
desoneração) e ISD e ICD (insumos). Item sem preço na UF fica de fora.
"""

from __future__ import annotations

import re
import urllib.error
import zipfile
from pathlib import Path

from .. import xlsx
from ..modelo import UFS, ErroFonte, Item
from . import abrir, baixar, meses_ate

URL = "https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/SINAPI-{ano}-{mes:02d}-formato-xlsx.zip"
ABAS = {"sd": ("CSD", "ISD"), "cd": ("CCD", "ICD")}


def url(competencia: str) -> str:
    ano, mes = competencia.split("-")
    return URL.format(ano=int(ano), mes=int(mes))


def existe(competencia: str) -> bool:
    """A Caixa já publicou a competência? Quando não, o endereço entra num redirecionamento sem fim."""
    try:
        with abrir(url(competencia), "HEAD", timeout=40) as r:
            return r.status == 200 and "zip" in (r.headers.get("Content-Type") or "").lower()
    except (urllib.error.URLError, OSError):
        return False


def mais_recente(ate: str | None = None) -> str:
    for c in meses_ate(ate, 4):
        if existe(c):
            return c
    raise ErroFonte("nenhuma competência do SINAPI dos últimos 4 meses respondeu no site da Caixa "
                    "(o site pode estar fora do ar ou o endereço mudou)")


def planilha_de_referencia(pacote: Path, pasta: Path) -> Path:
    """Extrai do zip a planilha SINAPI_Referência (o nome vem com o acento em codificações diferentes)."""
    with zipfile.ZipFile(pacote) as z:
        alvo = next((i for i in z.infolist() if "Refer" in i.filename and i.filename.lower().endswith(".xlsx")), None)
        if alvo is None:
            raise ErroFonte("o pacote do SINAPI não trouxe a planilha SINAPI_Referência (o formato mudou?)")
        saida = pasta / "SINAPI_Referencia.xlsx"
        saida.write_bytes(z.read(alvo))
    return saida


def codigo(v) -> str:
    """O código vem como número ou como fórmula de hiperlink: =HYPERLINK("...", 104658)."""
    s = str(v or "").strip()
    if s.startswith("="):
        m = re.search(r",\s*\"?(\d+)\"?\)\s*$", s)
        return m.group(1) if m else ""
    m = re.match(r"(\d+)", s)
    return m.group(1) if m else ""


def preco(v) -> float | None:
    """O custo vem como número ou como texto ("1.234,56" ou "1234.56")."""
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if not t or t.startswith("="):
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def ler_aba(planilha: Path, nome: str, tipo: str) -> dict[str, list[Item]]:
    """{UF: itens} de uma aba. O cabeçalho com as siglas das UFs fica nas primeiras linhas, sobre a coluna do custo."""
    # nas composições o código é uma fórmula de hiperlink (o valor guardado é zero); nos insumos, um número
    linhas = xlsx.ler(planilha, nome, formulas=tipo == "composicao")
    k = next((i for i, ln in enumerate(linhas[:15]) if sum(1 for c in ln if str(c).strip() in UFS) >= 20), None)
    if k is None:
        raise ErroFonte(f"a aba {nome} do SINAPI não tem o cabeçalho com as UFs (o formato mudou?)")
    cab = [str(c).strip() for c in linhas[k]]
    colunas = {uf: cab.index(uf) for uf in UFS if uf in cab}
    out: dict[str, list[Item]] = {uf: [] for uf in colunas}
    for ln in linhas[k + 1:]:
        if len(ln) < 4:
            continue
        cod = codigo(ln[1])
        if not cod:
            continue
        grupo, desc, un = str(ln[0] or "").strip(), str(ln[2] or "").strip(), str(ln[3] or "").strip()
        for uf, col in colunas.items():
            v = preco(ln[col] if col < len(ln) else "")
            if v is not None and v > 0:
                out[uf].append(Item(cod, desc, un, round(v, 2), tipo, grupo))
    return out


def converter(planilha: Path) -> dict[tuple[str, str], list[Item]]:
    """{(UF, regime): itens} com composições e insumos."""
    out: dict[tuple[str, str], list[Item]] = {}
    for regime, (comp, ins) in ABAS.items():
        a, b = ler_aba(planilha, comp, "composicao"), ler_aba(planilha, ins, "insumo")
        for uf in a:
            out[(uf, regime)] = a[uf] + b.get(uf, [])
    return out


def obter(competencia: str, pasta: Path) -> dict[tuple[str, str], list[Item]]:
    """Baixa o pacote nacional da competência e devolve as bases das 27 UFs nos dois regimes."""
    pacote = baixar(url(competencia), pasta / f"sinapi-{competencia}.zip")
    return converter(planilha_de_referencia(pacote, pasta))
