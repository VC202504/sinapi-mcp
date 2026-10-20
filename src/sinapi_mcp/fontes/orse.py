"""ORSE (CEHOP, Sergipe): a base de serviços de um mês, lida da consulta pública do site.

O arquivo mensal que o site oferece (downloads/AAAAMM01-00.ORSE) é de formato fechado e não é usado. A consulta de
serviços, com a descrição em branco, lista a base inteira; o leitor percorre grupo a grupo (para guardar o grupo de
cada serviço), com uma pausa entre as páginas para não pesar no servidor. Leva alguns minutos.
"""

from __future__ import annotations

import html
import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from ..modelo import AGENTE, ErroFonte, Item

URL = "https://orse.cehop.se.gov.br/servicosargumento.asp"
PAUSA = 0.4       # s entre as páginas

_PERIODO = re.compile(r'<option value="(\d{4})-(\d{1,2})-(\d+)"')
_CELULA = re.compile(r"<td class=\"CorpoTabela\".*?</td>", re.S)
_PAGINAS = re.compile(r"P[áa]gina\s+(\d+)\s+de\s+(\d+)")


class _Sessao:
    def __init__(self):
        self._ab = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def ler(self, url: str, dados: dict | None = None) -> str:
        corpo = urllib.parse.urlencode(dados, encoding="latin-1").encode("ascii") if dados else None
        req = urllib.request.Request(url, data=corpo, headers={"User-Agent": AGENTE, "Referer": URL})
        try:
            with self._ab.open(req, timeout=40) as r:
                return r.read().decode("latin-1")
        except (urllib.error.URLError, TimeoutError, OSError) as ex:
            raise ErroFonte(f"o site do ORSE não respondeu ({ex})") from ex


def _texto(celula: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", celula)).split())


def periodos_de(pagina: str) -> list[str]:
    """Meses de referência oferecidos pelo site, do mais novo para o mais antigo ("2026-7-1")."""
    return [f"{a}-{m}-{o}" for a, m, o in _PERIODO.findall(pagina)]


def itens_de(pagina: str, grupo: str = "") -> list[Item]:
    """Serviços de uma página de resultado: código, descrição, unidade e custo unitário (sem BDI)."""
    out = []
    celulas = [_texto(c) for c in _CELULA.findall(pagina)]
    for k in range(0, len(celulas) - 3, 4):                  # quatro células por serviço
        cod, desc, un, custo = celulas[k:k + 4]
        try:
            preco = float(custo.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        if cod and desc and preco > 0:
            out.append(Item(cod, desc, un, preco, "composicao", grupo))
    return out


def _grupos(inicio: str) -> list[tuple[str, str]]:
    k = inicio.find("sltGrupoServico")
    fim = inicio.find("</select>", k)
    return [(v, " ".join(html.unescape(t).split()))
            for v, t in re.findall(r'<option value="(\d+)"[^>]*>([^<]+)', inicio[k:fim]) if v != "0"]


def competencias() -> list[str]:
    """Competências "AAAA-MM" oferecidas, da mais nova para a mais antiga."""
    inicio = _Sessao().ler(URL)
    return [f"{p.split('-')[0]}-{int(p.split('-')[1]):02d}" for p in periodos_de(inicio)]


def obter(competencia: str | None = None, progresso=None, pausa: float = PAUSA) -> tuple[str, list[Item]]:
    """(competência, serviços) do ORSE. Sem competência, a mais nova. `progresso(feito, total)`: opcional."""
    s = _Sessao()
    inicio = s.ler(URL)
    periodos = periodos_de(inicio)
    if not periodos:
        raise ErroFonte("a página de consulta do ORSE não trouxe os meses de referência (o site mudou?)")
    if competencia:
        ano, mes = competencia.split("-")
        periodo = next((p for p in periodos if p.startswith(f"{ano}-{int(mes)}-")), None)
        if periodo is None:
            raise ErroFonte(f"o ORSE não oferece a competência {competencia}")
    else:
        periodo = periodos[0]
    a, m, *_ = periodo.split("-")
    comp = f"{a}-{int(m):02d}"
    grupos = _grupos(inicio)
    itens: dict[str, Item] = {}
    for n, (gid, nome) in enumerate(grupos, 1):
        pagina = s.ler(URL + "?tarefa=consultar", {"sltFonte": "ORSE", "sltPeriodo": periodo, "sltGrupoServico": gid,
                                                   "rdbCriterio": "2", "txtDescricao": "", "Submit": "Consultar"})
        mt = _PAGINAS.search(html.unescape(pagina))
        total, k = (int(mt.group(2)) if mt else 1), 1
        while True:
            for i in itens_de(pagina, nome):
                itens.setdefault(i.codigo, i)
            if k >= total:
                break
            k += 1
            time.sleep(pausa)
            pagina = s.ler(f"{URL}?tarefa=consultar&page={k}")
        if progresso:
            progresso(n, len(grupos))
        time.sleep(pausa)
    return comp, list(itens.values())
