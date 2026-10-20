"""Orçamento rápido: itens das bases × quantidades, com BDI."""

from __future__ import annotations

from dataclasses import dataclass, field

from .banco import COM_REGIME, Banco
from .modelo import REGIMES, rotulo_competencia


@dataclass
class LinhaOrcamento:
    base: str
    codigo: str
    descricao: str
    unidade: str
    quantidade: float
    unitario: float
    total: float
    fonte: str


@dataclass
class Orcamento:
    linhas: list[LinhaOrcamento] = field(default_factory=list)
    sem_preco: list[str] = field(default_factory=list)
    custo_direto: float = 0.0
    bdi: float = 0.0
    total: float = 0.0


def orcar(banco: Banco, itens: list[dict], uf: str | None, regime: str | None = "sd", competencia: str | None = None,
          bdi: float = 0.0, base_padrao: str = "SINAPI") -> Orcamento:
    """`itens`: [{"codigo": "94965", "quantidade": 12.5, "base": "SINAPI"}]. Preço unitário sem BDI da base; o BDI
    (em %) entra sobre o custo direto total."""
    o = Orcamento(bdi=bdi)
    for it in itens:
        base = str(it.get("base") or base_padrao).upper()
        cod = str(it["codigo"]).strip().upper()
        qtd = float(it.get("quantidade", 1))
        pac = banco.escolher_pacote(base, uf, regime, competencia)
        precos = banco.precos_do_item(base, cod, pac.uf, pac.regime, pac.competencia) if pac else []
        if not precos:
            o.sem_preco.append(f"{base} {cod}")
            continue
        p = precos[0]
        total = round(qtd * p.preco, 2)
        reg = REGIMES.get(p.regime, "") if p.base in COM_REGIME else ""
        fonte = " ".join(x for x in (p.base, p.uf, rotulo_competencia(p.competencia), reg) if x)
        o.linhas.append(LinhaOrcamento(base, cod, p.descricao, p.unidade, qtd, p.preco, total, fonte))
    o.custo_direto = round(sum(x.total for x in o.linhas), 2)
    o.total = round(o.custo_direto * (1 + bdi / 100), 2)
    return o
