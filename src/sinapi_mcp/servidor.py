"""Servidor MCP: as ferramentas que o assistente de IA chama."""

from __future__ import annotations

import os

import anyio

try:                                            # SDK do MCP 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:                             # 1.x
    from mcp.server.fastmcp import FastMCP

from . import bdi as _bdi
from .atualizar import atualizar
from .banco import COM_REGIME, Banco, Linha
from .modelo import BASES, REGIMES, UF_FIXA, UFS, ErroFonte, rotulo_competencia
from .orcamento import orcar as _orcar

INSTRUCOES = """\
Preços oficiais de referência de obras do Brasil, num banco local: SINAPI (Caixa/IBGE, 27 UFs), SICRO (DNIT,
rodovias), ORSE (Sergipe) e SEINFRA (Ceará). Os preços são custos unitários SEM BDI.
- Se uma busca não achar nada porque a base não foi baixada, chame atualizar_base (o SINAPI baixa as 27 UFs de uma vez).
- O SINAPI e a SEINFRA têm dois regimes de encargos: "sd" (sem desoneração, o padrão) e "cd" (com desoneração).
- Sempre informe ao usuário a base, a UF, a competência e o regime dos preços citados.
- Preços de referência servem de apoio; o orçamento final é responsabilidade do profissional habilitado."""

mcp = FastMCP("sinapi-mcp", instructions=INSTRUCOES)
_banco: Banco | None = None


def banco() -> Banco:
    global _banco
    if _banco is None:
        _banco = Banco()
    return _banco


def _uf(uf: str | None) -> str | None:
    uf = (uf or os.environ.get("SINAPI_MCP_UF") or "").strip().upper()
    if uf and uf not in UFS:
        raise ValueError(f"UF desconhecida: {uf}")
    return uf or None


def reais(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float, sinal: bool = False) -> str:
    return (f"{v:+.2f}" if sinal else f"{v:.2f}").replace(".", ",") + " %"


def _fonte(x: Linha) -> str:
    reg = REGIMES.get(x.regime, x.regime) if x.base in COM_REGIME else ""
    return " ".join(s for s in (x.base, x.uf, rotulo_competencia(x.competencia), reg) if s)


def _celula(t: str) -> str:
    return (t or "").replace("|", "/").replace("\n", " ")


@mcp.tool()
def bases_disponiveis() -> str:
    """Lista as bases de preços suportadas e o que já está baixado no banco local (UF, regime, competência)."""
    linhas = ["## Bases suportadas", ""] + [f"- **{k}**: {v}" for k, v in BASES.items()] + ["", "## No banco local", ""]
    pacs = banco().pacotes()
    if not pacs:
        linhas.append("Nada baixado ainda. Use atualizar_base (ex.: base SINAPI).")
    else:
        resumo: dict[tuple[str, str, str], list[str]] = {}
        for p in pacs:
            resumo.setdefault((p.base, p.competencia, p.regime), []).append(p.uf)
        for (base, comp, reg), ufs in sorted(resumo.items()):
            r = f", {REGIMES[reg]}" if reg else ""
            linhas.append(f"- {base} {rotulo_competencia(comp)}{r}: {len(ufs)} UF(s) ({', '.join(sorted(ufs))})")
    return "\n".join(linhas)


@mcp.tool()
async def atualizar_base(base: str, ufs: list[str] | None = None, competencia: str | None = None) -> str:
    """Baixa uma base do site oficial e grava no banco local.

    base: SINAPI, SICRO, ORSE ou SEINFRA.
    ufs: obrigatório no SICRO (ex.: ["PB", "PE"]); no SINAPI filtra as UFs (sem filtro entram as 27).
    competencia: "AAAA-MM" (na SEINFRA, a versão, ex. "028"); vazio = a mais recente publicada.
    O SINAPI leva cerca de um minuto; o ORSE, alguns minutos."""
    avisos: list[str] = []
    try:
        pacs = await anyio.to_thread.run_sync(
            lambda: atualizar(banco(), base, ufs, competencia, aviso=avisos.append))
    except ErroFonte as e:
        return f"Não foi possível atualizar: {e}"
    if not pacs:
        return "Nada gravado.\n" + "\n".join(avisos)
    comps = sorted({p.competencia for p in pacs})
    return (f"Gravados {len(pacs)} pacote(s) de {base.upper()} ({', '.join(rotulo_competencia(c) for c in comps)}), "
            f"{sum(p.itens for p in pacs):,} preços.".replace(",", ".") + ("\n" + "\n".join(avisos) if avisos else ""))


@mcp.tool()
def buscar_precos(texto: str, uf: str | None = None, base: str | None = None, regime: str = "sd",
                  competencia: str | None = None, tipo: str | None = None, limite: int = 20) -> str:
    """Busca serviços (composições) e insumos pela descrição ou pelo código.

    texto: palavras da descrição (ex.: "concreto fck 25 bombeado", "alvenaria bloco ceramico 9") ou um código.
    uf: sigla da UF (obrigatória para SINAPI e SICRO; padrão: variável SINAPI_MCP_UF).
    base: SINAPI, SICRO, ORSE ou SEINFRA; vazio = todas as que estiverem baixadas.
    regime: "sd" (sem desoneração) ou "cd" (com desoneração), para SINAPI e SEINFRA.
    competencia: "AAAA-MM"; vazio = a mais recente no banco.
    tipo: "composicao" ou "insumo"; vazio = os dois."""
    uf = _uf(uf)
    bases = [base.upper()] if base else list(BASES)
    pacs, faltam = [], []
    for b in bases:
        p = banco().escolher_pacote(b, uf, regime, competencia)
        if p:
            pacs.append(p)
        elif b in UF_FIXA or uf:
            faltam.append(b)
    if not pacs:
        if not uf and not base:
            return "Diga a UF (ex.: uf=\"PB\") ou configure SINAPI_MCP_UF."
        return (f"Nenhuma base baixada para esse filtro ({', '.join(faltam) or base}). "
                "Chame atualizar_base primeiro.")
    achados = banco().buscar(texto, pacs, tipo, max(1, min(limite, 100)))
    if not achados:
        return f"Nada encontrado para \"{texto}\" em {', '.join(_fonte_p(p) for p in pacs)}."
    linhas = ["| Base | Código | Descrição | Un. | Preço (sem BDI) | Fonte |", "|---|---|---|---|---:|---|"]
    for x in achados:
        linhas.append(f"| {x.base} | {x.codigo} | {_celula(x.descricao)} | {x.unidade} | {reais(x.preco)} | {_fonte(x)} |")
    if not uf and not base:
        linhas.append("\nSINAPI e SICRO ficaram de fora porque são por UF: informe a UF para incluí-los.")
    return "\n".join(linhas)


def _fonte_p(p) -> str:
    reg = f" {REGIMES[p.regime]}" if p.regime else ""
    return f"{p.base} {p.uf} {rotulo_competencia(p.competencia)}{reg}"


@mcp.tool()
def detalhar_item(codigo: str, base: str = "SINAPI", uf: str | None = None, regime: str | None = None) -> str:
    """Descrição completa, grupo e todos os preços guardados de um item (por UF, regime e competência), para ver a
    evolução do preço no tempo."""
    it = banco().item(base, codigo)
    if it is None:
        return f"O código {codigo} não está no banco da base {base.upper()}."
    precos = banco().precos_do_item(base, codigo, _uf(uf), regime)
    linhas = [f"**{it.base} {it.codigo}** ({it.tipo or 'item'}): {it.descricao}", f"Unidade: {it.unidade}"]
    if it.grupo:
        linhas.append(f"Grupo: {it.grupo}")
    linhas += ["", "| Fonte | Preço (sem BDI) |", "|---|---:|"] + [f"| {_fonte(x)} | {reais(x.preco)} |" for x in precos[:120]]
    return "\n".join(linhas)


@mcp.tool()
def comparar_ufs(codigo: str, base: str = "SINAPI", regime: str = "sd", competencia: str | None = None) -> str:
    """O preço de um item em todas as UFs baixadas, do mais barato ao mais caro, na mesma competência e regime."""
    b = base.upper()
    if b in UF_FIXA:
        return f"A base {b} é de uma UF só ({UF_FIXA[b]})."
    if not competencia:
        comps = [p.competencia for p in banco().pacotes(b)]
        if not comps:
            return f"Nenhum pacote de {b} no banco. Chame atualizar_base."
        competencia = max(comps)
    precos = sorted(banco().precos_do_item(b, codigo, None, regime, competencia), key=lambda x: x.preco)
    if not precos:
        return f"O código {codigo} não tem preço em {b} {rotulo_competencia(competencia)}."
    media = sum(x.preco for x in precos) / len(precos)
    linhas = [f"**{b} {codigo}**: {precos[0].descricao} ({precos[0].unidade}), {rotulo_competencia(competencia)}"
              + (f", {REGIMES[regime]}" if b in COM_REGIME else ""), "",
              "| UF | Preço | Em relação à média |", "|---|---:|---:|"]
    for x in precos:
        linhas.append(f"| {x.uf} | {reais(x.preco)} | {pct((x.preco / media - 1) * 100, True)} |")
    linhas.append(f"\nMédia de {len(precos)} UF(s): {reais(media)}")
    return "\n".join(linhas)


@mcp.tool()
def orcar(itens: list[dict], uf: str | None = None, regime: str = "sd", competencia: str | None = None,
          bdi: float = 0.0, base: str = "SINAPI") -> str:
    """Monta um orçamento rápido: código × quantidade × preço da base, com o BDI (%) sobre o custo direto.

    itens: [{"codigo": "103324", "quantidade": 85.4}, {"codigo": "C1234", "quantidade": 10, "base": "SEINFRA"}].
    base: a base usada quando o item não diz a sua."""
    o = _orcar(banco(), itens, _uf(uf), regime, competencia, bdi, base)
    if not o.linhas:
        return "Nenhum item com preço. Confira os códigos, a UF e se a base foi baixada (atualizar_base)."
    linhas = ["| # | Código | Descrição | Un. | Qtd. | Unitário | Total | Fonte |",
              "|---:|---|---|---|---:|---:|---:|---|"]
    for k, x in enumerate(o.linhas, 1):
        qtd = f"{x.quantidade:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")
        linhas.append(f"| {k} | {x.codigo} | {_celula(x.descricao)[:120]} | {x.unidade} | {qtd} | {reais(x.unitario)} | "
                      f"{reais(x.total)} | {x.fonte} |")
    linhas += ["", f"Custo direto: **{reais(o.custo_direto)}**",
               f"BDI ({pct(o.bdi)}): {reais(o.total - o.custo_direto)}", f"Total com BDI: **{reais(o.total)}**"]
    if o.sem_preco:
        linhas.append(f"\nSem preço (fora do total): {', '.join(o.sem_preco)}")
    return "\n".join(linhas)


@mcp.tool()
def calcular_bdi(ac: float, sg: float, r: float, df: float, lucro: float, iss: float = 0.0, pis: float = 0.65,
                 cofins: float = 3.00, cprb: float = 0.0, tipo_obra: str = "edificacoes") -> str:
    """BDI pela fórmula do Acórdão 2622/2013-TCU, comparando cada componente com as faixas do acórdão.

    Valores em %: ac (administração central), sg (seguro + garantia), r (risco), df (despesas financeiras), lucro,
    iss (alíquota efetiva sobre o faturamento), pis, cofins, cprb (4,5 no regime desonerado; senão 0).
    tipo_obra: edificacoes, rodovias_ferrovias, saneamento, energia, portuarias ou fornecimento."""
    try:
        res = _bdi.calcular(ac, sg, r, df, lucro, pis, cofins, iss, cprb, tipo_obra)
    except ValueError as e:
        return str(e)
    linhas = [f"**BDI = {pct(res.bdi)}** (tributos {pct(res.tributos)})",
              "Fórmula: ((1 + AC + S + R + G) × (1 + DF) × (1 + L)) / (1 − I) − 1"]
    faixas = _bdi.FAIXAS_TCU.get(tipo_obra)
    if faixas:
        valores = {"AC": ac, "SG": sg, "R": r, "DF": df, "L": lucro, "BDI": res.bdi}
        linhas += ["", f"Faixas do TCU para {_bdi.NOMES[tipo_obra]}:", "",
                   "| Componente | Valor | 1º quartil | Médio | 3º quartil | Situação |", "|---|---:|---:|---:|---:|---|"]
        for nome, (q1, med, q3) in faixas.items():
            linhas.append(f"| {nome} | {valores[nome]:.2f} | {q1:.2f} | {med:.2f} | {q3:.2f} | {res.situacao[nome]} |")
        linhas.append("\nConfira as faixas no texto oficial do acórdão antes de usar em processo.")
    else:
        linhas.append(f"\nTipo de obra sem faixa de referência: {tipo_obra} (use: {', '.join(_bdi.FAIXAS_TCU)}).")
    return "\n".join(linhas)


def rodar() -> None:
    mcp.run()
