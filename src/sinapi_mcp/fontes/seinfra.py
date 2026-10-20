"""SEINFRA (Ceará): da tabela de custos em HTML à base de serviços e insumos.

Fonte: https://sin.seinfra.ce.gov.br/site-seinfra/siproce/{onerada|desonerada}/tabela-custo-download.html, que
oferece a tabela inteira em HTML compactado. A tabela não é mensal: sai por versão (028 sem desoneração e 028.1 com
desoneração, em vigor desde 24/10/2023). A "competência" do pacote é o número da versão.

No pacote: páginas de subgrupo ("1.1.html") com os serviços (conta, código, descrição, unidade e valor) e uma página
por insumo ("I0001.html") com o preço adotado e a unidade.
"""

from __future__ import annotations

import html
import re
import ssl
import urllib.error
import zipfile
from pathlib import Path

from ..modelo import ErroFonte, Item
from . import abrir, baixar

RAIZ = "https://sin.seinfra.ce.gov.br/site-seinfra/siproce"
REGIMES = {"sd": "onerada", "cd": "desonerada"}     # sem desoneração = encargos cheios ("onerada")
_LINHA = re.compile(r"<tr[^>]*>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>\s*<a[^>]*>([CI]\d+)</a>\s*</td>\s*<td[^>]*>\s*<a[^>]*>(.*?)</a>"
                    r"\s*</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>([\d.,]+)</td>", re.S)
_SUBGRUPO = re.compile(r"<td[^>]*>([\d.]+)</td>\s*<td[^>]*>\s*<a href=\"[^\"]+\">(.*?)</a>", re.S)
_INSUMO = re.compile(r"<th[^>]*>\s*(I\d+)\s*-\s*(.*?)</th>.*?Pre(?:&ccedil;|ç)o Adotado:\s*([\d.,]+).*?Unid:\s*([^<]+)<", re.S)


def _certificado_ruim(exc: BaseException) -> bool:
    return isinstance(getattr(exc, "reason", None), ssl.SSLError) or isinstance(exc, ssl.SSLError)


def versao_no_site(regime: str) -> tuple[str, str, bool]:
    """(versão, endereço do zip, lido sem conferir o certificado) anunciados na página de download do regime."""
    pagina = f"{RAIZ}/{REGIMES[regime]}/tabela-custo-download.html"
    inseguro = False
    try:
        with abrir(pagina) as r:
            txt = r.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        # o certificado do servidor da SEINFRA às vezes está vencido ou incompleto: lê mesmo assim e avisa
        if not _certificado_ruim(e):
            raise ErroFonte(f"o site da SEINFRA não respondeu ({e})") from e
        inseguro = True
        with abrir(pagina, inseguro=True) as r:
            txt = r.read().decode("utf-8", "replace")
    m = re.search(r'href="((\d+(?:\.\d+)?)---[^"]*-html\.zip)', txt)
    if not m:
        raise ErroFonte("a página de download da SEINFRA não trouxe a versão da tabela (o site mudou?)")
    return m.group(2), f"{RAIZ}/{REGIMES[regime]}/{m.group(1)}".replace(" ", "%20"), inseguro


def _num(t: str) -> float:
    return float(t.strip().replace(".", "").replace(",", "."))


def _txt(t: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())


def converter(pacote: Path) -> list[Item]:
    """Serviços (com o grupo) e insumos da tabela."""
    with zipfile.ZipFile(pacote) as z:
        paginas = {n.rsplit("/", 1)[-1]: n for n in z.namelist() if n.lower().endswith(".html")}

        def ler(nome: str) -> str:
            return z.read(paginas[nome]).decode("utf-8", "replace")

        grupos: dict[str, str] = {}
        for nome in paginas:
            if re.fullmatch(r"(?:\d+|tabela-seinfra)\.html", nome):
                for conta, rot in _SUBGRUPO.findall(ler(nome)):
                    grupos[conta] = _txt(rot)
        itens: dict[str, Item] = {}
        for nome in paginas:
            if not re.fullmatch(r"\d+(?:\.\d+)+\.html", nome):
                continue
            conta_pag = nome[:-5]
            grupo = " / ".join(x for x in (grupos.get(conta_pag.split(".")[0], ""), grupos.get(conta_pag, "")) if x)
            for _conta, cod, desc, un, valor in _LINHA.findall(ler(nome)):
                try:
                    v = _num(valor)
                except ValueError:
                    continue
                if v > 0 and cod not in itens:
                    itens[cod] = Item(cod, _txt(desc), _txt(un), round(v, 4), "composicao", grupo)
        for nome in paginas:
            if not re.fullmatch(r"I\d+\.html", nome):
                continue
            m = _INSUMO.search(ler(nome))
            if not m:
                continue
            try:
                v = _num(m.group(3))
            except ValueError:
                continue
            if v > 0:
                itens.setdefault(m.group(1), Item(m.group(1), _txt(m.group(2)), _txt(m.group(4)), round(v, 4), "insumo", ""))
    return list(itens.values())


def obter(regime: str, endereco: str, pasta: Path, inseguro: bool = False) -> list[Item]:
    return converter(baixar(endereco, pasta / f"seinfra-{regime}.zip", inseguro=inseguro))
