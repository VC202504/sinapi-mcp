"""Leitura de planilhas XLSX sem dependências (só o que as fontes oficiais usam: valores, textos e fórmulas)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_M = "{%s}" % _NS["m"]


def _indice_coluna(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def nomes_abas(origem: str | Path) -> list[str]:
    with zipfile.ZipFile(origem) as z:
        return re.findall(r'<sheet[^>]*name="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8"))


def ler(origem: str | Path, aba: int | str = 0, formulas: bool = False) -> list[list]:
    """Linhas de uma aba (pelo índice ou pelo nome). Valores: str ou float; célula vazia vira "". Com `formulas`, a
    célula que tem fórmula vem como "=" seguido do texto dela, no lugar do valor guardado."""
    if isinstance(aba, str):
        aba = nomes_abas(origem).index(aba)
    with zipfile.ZipFile(origem) as z:
        compart: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                compart.append("".join(t.text or "" for t in si.iter(f"{_M}t")))
        folhas = ET.fromstring(z.read("xl/workbook.xml")).findall("m:sheets/m:sheet", _NS)
        rid = folhas[aba].get(f"{{{_NS['r']}}}id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        alvo = next(r.get("Target") for r in rels if r.get("Id") == rid)
        caminho = alvo.lstrip("/") if alvo.startswith("/") else "xl/" + alvo
        folha = ET.fromstring(z.read(caminho))
    linhas: list[list] = []
    for row in folha.iter(f"{_M}row"):
        vals: list = []
        for c in row.findall("m:c", _NS):
            j = _indice_coluna(c.get("r", "A1"))
            while len(vals) < j:
                vals.append("")
            t, v = c.get("t"), c.find("m:v", _NS)
            f = c.find("m:f", _NS) if formulas else None
            if f is not None and f.text:
                val = "=" + f.text
            elif t == "s" and v is not None:
                val = compart[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{_M}t"))
            elif t in ("str", "b") and v is not None:
                val = v.text or ""
            elif v is not None and v.text is not None:
                try:
                    val = float(v.text)
                except ValueError:
                    val = v.text
            else:
                val = ""
            vals.append(val)
        linhas.append(vals)
    return linhas
