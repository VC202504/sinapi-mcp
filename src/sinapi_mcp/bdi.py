"""BDI pela fórmula do Acórdão 2622/2013 do TCU (Plenário), com as faixas de referência por tipo de obra.

    BDI = ((1 + AC + S + R + G) × (1 + DF) × (1 + L)) / (1 − I) − 1

AC = administração central, S + G = seguro e garantia, R = risco, DF = despesas financeiras, L = lucro e
I = tributos sobre o faturamento (PIS, COFINS, ISS e, na desoneração da folha, a CPRB). Todos em %.

As faixas (1º quartil, média e 3º quartil) são as da tabela do acórdão. Confira no texto oficial antes de usar em
processo: este módulo é ferramenta de apoio, não substitui a análise do orçamentista.
"""

from __future__ import annotations

from dataclasses import dataclass

# tipo de obra: {componente: (1º quartil, médio, 3º quartil)}, em %
FAIXAS_TCU: dict[str, dict[str, tuple[float, float, float]]] = {
    "edificacoes": {"AC": (3.00, 4.00, 5.50), "SG": (0.80, 0.80, 1.00), "R": (0.97, 1.27, 1.27),
                    "DF": (0.59, 1.23, 1.39), "L": (6.16, 7.40, 8.96), "BDI": (20.34, 22.12, 25.00)},
    "rodovias_ferrovias": {"AC": (3.80, 4.01, 4.67), "SG": (0.32, 0.40, 0.74), "R": (0.50, 0.56, 0.97),
                           "DF": (1.02, 1.11, 1.21), "L": (6.64, 7.30, 8.69), "BDI": (19.60, 20.97, 24.23)},
    "saneamento": {"AC": (3.43, 4.93, 6.71), "SG": (0.28, 0.49, 0.75), "R": (1.00, 1.39, 1.74),
                   "DF": (0.94, 0.99, 1.17), "L": (6.74, 8.04, 9.40), "BDI": (20.76, 24.18, 26.44)},
    "energia": {"AC": (5.29, 5.92, 7.93), "SG": (0.25, 0.51, 0.56), "R": (1.00, 1.48, 2.97),
                "DF": (1.01, 1.07, 1.11), "L": (8.00, 8.31, 9.51), "BDI": (24.00, 25.84, 27.86)},
    "portuarias": {"AC": (4.00, 5.52, 7.85), "SG": (0.81, 1.22, 1.99), "R": (1.46, 2.32, 3.16),
                   "DF": (0.94, 1.02, 1.33), "L": (7.14, 8.40, 10.43), "BDI": (22.80, 27.48, 30.95)},
    "fornecimento": {"AC": (1.50, 3.45, 4.49), "SG": (0.30, 0.48, 0.82), "R": (0.56, 0.85, 0.89),
                     "DF": (0.85, 0.85, 1.11), "L": (3.50, 5.11, 6.22), "BDI": (11.10, 14.02, 16.80)},
}
NOMES = {
    "edificacoes": "Construção de edifícios",
    "rodovias_ferrovias": "Construção de rodovias e ferrovias",
    "saneamento": "Redes de abastecimento de água, coleta de esgoto e correlatas",
    "energia": "Estações e redes de distribuição de energia elétrica",
    "portuarias": "Obras portuárias, marítimas e fluviais",
    "fornecimento": "Fornecimento de materiais e equipamentos",
}


@dataclass
class ResultadoBDI:
    bdi: float                      # %
    tributos: float                 # %
    situacao: dict[str, str]        # componente → "abaixo", "dentro" ou "acima" da faixa do TCU
    faixa_bdi: tuple[float, float, float] | None


def calcular(ac: float, sg: float, r: float, df: float, lucro: float, pis: float = 0.65, cofins: float = 3.00,
             iss: float = 0.0, cprb: float = 0.0, tipo_obra: str | None = "edificacoes") -> ResultadoBDI:
    """BDI em % a partir dos componentes em %. `iss` é a alíquota efetiva sobre o faturamento (alíquota do município
    × parcela tributável); `cprb` só entra no regime desonerado (4,5 % na construção)."""
    tributos = pis + cofins + iss + cprb
    if tributos >= 100:
        raise ValueError("os tributos somam 100 % ou mais")
    bdi = ((1 + (ac + sg + r) / 100) * (1 + df / 100) * (1 + lucro / 100) / (1 - tributos / 100) - 1) * 100
    faixas = FAIXAS_TCU.get(tipo_obra or "")
    situacao: dict[str, str] = {}
    if faixas:
        for nome, valor in (("AC", ac), ("SG", sg), ("R", r), ("DF", df), ("L", lucro), ("BDI", bdi)):
            q1, _med, q3 = faixas[nome]
            situacao[nome] = "abaixo" if valor < q1 - 1e-9 else "acima" if valor > q3 + 1e-9 else "dentro"
    return ResultadoBDI(round(bdi, 2), round(tributos, 2), situacao, faixas["BDI"] if faixas else None)
