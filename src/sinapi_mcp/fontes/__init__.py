"""Leitores das fontes oficiais. Cada módulo baixa o arquivo público do órgão e devolve os itens."""

from __future__ import annotations

import datetime as dt
import shutil
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from ..modelo import AGENTE


def pedido(url: str, metodo: str = "GET", dados: bytes | None = None, cabecalhos: dict | None = None) -> urllib.request.Request:
    return urllib.request.Request(url, data=dados, method=metodo, headers={"User-Agent": AGENTE, **(cabecalhos or {})})


def abrir(url: str, metodo: str = "GET", timeout: float = 60, inseguro: bool = False):
    ctx = None
    if inseguro:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(pedido(url, metodo), timeout=timeout, context=ctx)


def baixar(url: str, destino: Path, timeout: float = 900, tentativas: int = 3, inseguro: bool = False) -> Path:
    """Grava o arquivo em `destino`, tentando de novo quando o download corta no meio."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    for k in range(tentativas):
        try:
            with abrir(url, timeout=timeout, inseguro=inseguro) as r, open(destino, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            return destino
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if k == tentativas - 1:
                raise
    return destino


def meses_ate(ate: str | None, quantos: int) -> list[str]:
    """Os `quantos` meses até `ate` ("2026-10"; hoje, se vazio), do mais novo para o mais antigo."""
    ano, mes = (int(x) for x in (ate or dt.date.today().strftime("%Y-%m")).split("-"))
    out = []
    for _ in range(quantos):
        out.append(f"{ano}-{mes:02d}")
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return out
