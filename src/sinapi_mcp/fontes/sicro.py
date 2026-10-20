"""SICRO (DNIT): do pacote trimestral de cada UF à base de composições e materiais.

Fonte: gov.br/dnit, Custos Referenciais ▸ Sistemas de Custos ▸ SICRO ▸ Relatórios, organizados por região, estado,
ano e mês (janeiro, abril, julho e outubro). Cada mês tem um arquivo compactado (.7z; .zip ou .rar nos antigos) com
as planilhas "Relatório Sintético de Composições de Custos" e "Relatório Sintético de Materiais".

A extração usa o py7zr (pip install "sinapi-mcp[sicro]") ou, na falta dele, o 7-Zip instalado.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
import urllib.error
import zipfile
from pathlib import Path

from .. import xlsx
from ..modelo import ErroFonte, Item
from . import abrir, baixar

BASE = ("https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/sistemas-de-custos/sicro/"
        "relatorios/relatorios-sicro")
MESES = {1: "janeiro", 4: "abril", 7: "julho", 10: "outubro"}
ESTADOS = {   # UF: (região, endereço do estado)
    "AC": ("norte", "acre"), "AM": ("norte", "amazonas"), "AP": ("norte", "amapa"), "PA": ("norte", "para"),
    "RO": ("norte", "rondonia"), "RR": ("norte", "roraima"), "TO": ("norte", "tocantins"),
    "AL": ("nordeste", "alagoas"), "BA": ("nordeste", "bahia"), "CE": ("nordeste", "ceara"),
    "MA": ("nordeste", "maranhao"), "PB": ("nordeste", "paraiba"), "PE": ("nordeste", "pernambuco"),
    "PI": ("nordeste", "piaui"), "RN": ("nordeste", "rio-grande-do-norte"), "SE": ("nordeste", "sergipe"),
    "DF": ("centro-oeste", "distrito-federal"), "GO": ("centro-oeste", "goias"),
    "MS": ("centro-oeste", "mato-grosso-do-sul"), "MT": ("centro-oeste", "mato-grosso"),
    "ES": ("sudeste", "espirito-santo"), "MG": ("sudeste", "minas-gerais"), "RJ": ("sudeste", "rio-de-janeiro"),
    "SP": ("sudeste", "sao-paulo"),
    "PR": ("sul", "parana"), "RS": ("sul", "rio-grande-do-sul"), "SC": ("sul", "santa-catarina"),
}
PLANILHAS = ("*sint*composi*.xlsx", "*sint*materiais*.xlsx")


def competencias_possiveis(ate: str | None, quantas: int = 3) -> list[str]:
    """As últimas competências trimestrais até o mês `ate`, da mais nova para a mais antiga."""
    from . import meses_ate
    return [c for c in meses_ate(ate, 12) if int(c[5:]) in MESES][:quantas]


def achar(uf: str, competencia: str) -> str | None:
    """Endereço do arquivo da UF na competência, ou None se o DNIT ainda não publicou. Tenta o endereço direto e,
    se não houver, lê a página do mês (os nomes variam: "revisado", .zip, .rar)."""
    regiao, estado = ESTADOS[uf]
    ano, mes = (int(x) for x in competencia.split("-"))
    nome = MESES.get(mes)
    if nome is None:
        return None
    pasta = f"{BASE}/{regiao}/{estado}/{ano}/{nome}"
    direto = f"{pasta}/{uf.lower()}-{mes:02d}-{ano}.7z"
    try:
        with abrir(direto, "HEAD") as r:
            if r.status == 200 and "html" not in (r.headers.get("Content-Type") or "").lower():
                return direto
    except (urllib.error.URLError, OSError):
        pass
    for pagina in (f"{pasta}/{nome}-{ano}", f"{pasta}-{ano}/{nome}-{ano}", f"{pasta}-{ano}/{nome}-{ano}-revisado",
                   f"{pasta}/{nome}-{ano}-revisado"):
        try:
            with abrir(pagina) as r:
                txt = r.read(2_000_000).decode("utf-8", "replace")
        except (urllib.error.URLError, OSError):
            continue
        m = re.search(r'href="([^"]+\.(?:7z|zip|rar))"', txt, re.I)
        if m:
            return m.group(1) if m.group(1).startswith("http") else pagina.rsplit("/", 1)[0] + "/" + m.group(1)
    return None


def mais_recente(uf: str, ate: str | None = None) -> tuple[str, str]:
    """(competência, endereço) da publicação mais nova da UF."""
    if uf not in ESTADOS:
        raise ErroFonte(f"UF desconhecida: {uf}")
    for c in competencias_possiveis(ate, 3):
        u = achar(uf, c)
        if u:
            return c, u
    raise ErroFonte(f"nenhuma competência recente do SICRO {uf} foi achada no site do DNIT")


def _sete_zip() -> str | None:
    for c in (shutil.which("7z"), shutil.which("7za"), r"C:\Program Files\7-Zip\7z.exe",
              r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if c and Path(c).is_file():
            return c
    return None


def _quer(nome: str) -> bool:
    base = nome.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return any(fnmatch.fnmatch(base, p) for p in PLANILHAS)


def extrair(pacote: Path, pasta: Path) -> list[Path]:
    """Extrai só as duas planilhas sintéticas (composições e materiais)."""
    pasta.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(pacote):
        with zipfile.ZipFile(pacote) as z:
            for n in z.namelist():
                if _quer(n):
                    (pasta / n.replace("\\", "/").rsplit("/", 1)[-1]).write_bytes(z.read(n))
        return sorted(pasta.glob("*.xlsx"))
    try:
        import py7zr
    except ImportError:
        py7zr = None
    if py7zr is not None and py7zr.is_7zfile(pacote):
        with py7zr.SevenZipFile(pacote) as z:
            alvos = [n for n in z.getnames() if _quer(n)]
            z.extract(path=pasta, targets=alvos)
        for p in pasta.rglob("*.xlsx"):
            if p.parent != pasta:
                shutil.move(str(p), pasta / p.name)
        return sorted(pasta.glob("*.xlsx"))
    sz = _sete_zip()
    if sz is None:
        raise ErroFonte('o SICRO vem em .7z: instale o extra (pip install "sinapi-mcp[sicro]") ou o 7-Zip')
    subprocess.run([sz, "e", "-y", f"-o{pasta}", str(pacote), "*Sint*Composi*.xlsx", "*Sint*Materiais*.xlsx", "-r"],
                   check=True, capture_output=True)
    return sorted(pasta.glob("*.xlsx"))


def _planilha(caminho: Path, tipo: str) -> list[Item]:
    linhas = xlsx.ler(caminho)
    k = next((i for i, ln in enumerate(linhas[:20]) if ln and "digo" in str(ln[0]).lower() and len(ln) >= 4), None)
    if k is None:
        raise ErroFonte(f"a planilha {caminho.name} do SICRO não tem o cabeçalho esperado")
    out = []
    for ln in linhas[k + 1:]:
        if len(ln) < 4 or not str(ln[0]).strip():
            continue
        v = ln[3]
        if not isinstance(v, (int, float)):
            try:
                v = float(str(v).replace(".", "").replace(",", "."))
            except ValueError:
                continue
        if v <= 0:
            continue
        cod = str(ln[0]).strip()
        if cod.endswith(".0"):
            cod = cod[:-2]
        out.append(Item(cod, str(ln[1]).strip(), str(ln[2]).strip(), round(float(v), 4), tipo, ""))
    return out


def converter(planilhas: list[Path]) -> list[Item]:
    """Composições (custo unitário) e materiais (preço unitário) de uma UF."""
    out: list[Item] = []
    for p in planilhas:
        nome = p.name.lower()
        if "composi" in nome:
            out += _planilha(p, "composicao")
        elif "materiais" in nome:
            out += _planilha(p, "insumo")
    return out


def obter(uf: str, endereco: str, pasta: Path) -> list[Item]:
    arq = baixar(endereco, pasta / f"sicro-{uf}{Path(endereco).suffix}")
    return converter(extrair(arq, pasta / f"sicro-{uf}"))
