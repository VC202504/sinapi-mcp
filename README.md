# sinapi-mcp

**Preços oficiais de obras do Brasil dentro do Claude, do Cursor e de qualquer assistente compatível com MCP.**

SINAPI (Caixa e IBGE), SICRO (DNIT), ORSE (CEHOP, Sergipe) e SEINFRA (Ceará): o servidor baixa as tabelas direto dos
sites oficiais, guarda num banco local e deixa a IA buscar composições e insumos, comparar UFs, ver a evolução do preço
no tempo, montar um orçamento rápido e calcular o BDI pelo Acórdão 2622/2013 do TCU.

[![CI](https://github.com/VC202504/sinapi-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/VC202504/sinapi-mcp/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-servidor-8A2BE2)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

> *English summary at the end.*

## O que dá para pedir

> Quanto custa o m² de alvenaria de bloco cerâmico 9x19x19 na Paraíba, sem desoneração?

> Monte um orçamento com 120 m² de alvenaria 103328 e 8,5 m³ de concreto C25 34493 na PB, com BDI de 22,12 %.

> Compare o preço do cimento CP II-32 entre os estados.

> Esse BDI está dentro das faixas do TCU para edificações? AC 4, seguro e garantia 0,8, risco 1,27, despesas
> financeiras 1,23, lucro 7,4, ISS 2,5.

Resposta típica do `orcar`:

| # | Código | Descrição | Un. | Qtd. | Unitário | Total | Fonte |
|---:|---|---|---|---:|---:|---:|---|
| 1 | 103328 | ALVENARIA DE VEDAÇÃO DE BLOCOS CERÂMICOS FURADOS NA HORIZONTAL DE 9X19X19 CM (ESPESSURA 9 CM)... | M2 | 120 | R$ 104,84 | R$ 12.580,80 | SINAPI PB 09/2026 sem desoneração |
| 2 | 34493 | CONCRETO USINADO BOMBEAVEL, CLASSE DE RESISTENCIA C25, COM BRITA 0 E 1, SLUMP = 100 +/- 20 MM... | M3 | 8,5 | R$ 580,92 | R$ 4.937,82 | SINAPI PB 09/2026 sem desoneração |

Custo direto: **R$ 17.518,62** · BDI (22,12 %): R$ 3.875,12 · Total com BDI: **R$ 21.393,74**

## Ferramentas

| Ferramenta | O que faz |
|---|---|
| `atualizar_base` | Baixa a competência mais recente (ou a pedida) do site oficial e grava no banco local |
| `buscar_precos` | Busca por palavras ou código, sem precisar de acento, em uma base ou em todas |
| `detalhar_item` | Descrição completa, grupo e todos os preços guardados do item (evolução no tempo) |
| `comparar_ufs` | O mesmo item em todas as UFs, do mais barato ao mais caro, com a diferença para a média |
| `orcar` | Código × quantidade × preço, com BDI sobre o custo direto |
| `calcular_bdi` | Fórmula do Acórdão 2622/2013-TCU e comparação com as faixas por tipo de obra |
| `bases_disponiveis` | O que já está no banco local |

## Bases

| Base | Órgão | Cobertura | Periodicidade | Download |
|---|---|---|---|---|
| SINAPI | Caixa e IBGE | 27 UFs, composições e insumos, sem e com desoneração | mensal | cerca de 16 MB, menos de 1 minuto |
| SICRO | DNIT | obras rodoviárias, composições e materiais, por UF | trimestral | por UF, cerca de 1 minuto |
| ORSE | CEHOP (SE) | serviços, inclusive itens que o SINAPI não traz | mensal | leitura da consulta pública, alguns minutos |
| SEINFRA | Governo do Ceará | serviços e insumos, sem e com desoneração | por versão | cerca de 1 minuto |

Tudo vem das fontes públicas originais, no momento em que você pede. Nenhum dado passa por servidor de terceiros.
As competências antigas ficam guardadas, então um orçamento pode ser refeito com os preços da sua data.

## Instalação

Precisa do [uv](https://docs.astral.sh/uv/) (ou de Python 3.10+ com `pip`).

### Claude Code

```bash
claude mcp add sinapi -e SINAPI_MCP_UF=PB -- uvx --from "sinapi-mcp[sicro] @ git+https://github.com/VC202504/sinapi-mcp" sinapi-mcp
```

### Claude Desktop, Cursor, Windsurf e outros

No arquivo de configuração de servidores MCP (no Claude Desktop: Configurações ▸ Desenvolvedor ▸ Editar configuração):

```json
{
  "mcpServers": {
    "sinapi": {
      "command": "uvx",
      "args": ["--from", "sinapi-mcp[sicro] @ git+https://github.com/VC202504/sinapi-mcp", "sinapi-mcp"],
      "env": { "SINAPI_MCP_UF": "PB" }
    }
  }
}
```

`SINAPI_MCP_UF` é a UF padrão das buscas (opcional). `SINAPI_MCP_DADOS` muda a pasta do banco (padrão:
`%LOCALAPPDATA%\sinapi-mcp` no Windows, `~/.local/share/sinapi-mcp` no Linux e no macOS).

### Linha de comando

```bash
pip install "sinapi-mcp[sicro] @ git+https://github.com/VC202504/sinapi-mcp"
sinapi-mcp atualizar SINAPI            # 27 UFs, os dois regimes
sinapi-mcp atualizar SICRO --uf PB,PE
sinapi-mcp buscar "concreto usinado c25" --uf PB
sinapi-mcp bases
```

Dica: rode o `atualizar` do SINAPI uma vez pela linha de comando antes de usar no assistente, para a primeira
conversa já começar com a base pronta.

## Como funciona

```
assistente de IA ⇄ MCP (stdio) ⇄ sinapi-mcp ⇄ banco SQLite local (busca de texto FTS5)
                                     │
                                     └─ atualizar_base: Caixa, DNIT, CEHOP e SEINFRA-CE
```

- A busca ignora acentos, aceita o começo das palavras ("bombeado" acha "bombeável") e, quando nenhum item tem todas
  as palavras, devolve os que têm mais.
- Os preços são custos unitários **sem BDI**, como publicados pelos órgãos.
- O SICRO vem em `.7z`; o extra `[sicro]` instala o `py7zr` (ou use o 7-Zip instalado).
- Uma importação que chega com poucos itens (sinal de que o órgão mudou o formato) não é gravada.

## Avisos

Ferramenta de apoio. Preço de referência não substitui a análise do profissional habilitado, e o orçamento final, a ART
e as escolhas de composição continuam sendo responsabilidade de quem assina. Confira as faixas de BDI no texto oficial
do acórdão antes de usar em processo. O projeto não tem vínculo com a Caixa, o IBGE, o DNIT, a CEHOP ou a SEINFRA.

## Contribuindo

Issues e pull requests são bem-vindos, principalmente para novas bases estaduais (SETOP-MG, EMOP-RJ, SIURB-SP,
SUDECAP, AGETOP) e para composições analíticas.

```bash
git clone https://github.com/VC202504/sinapi-mcp && cd sinapi-mcp
python -m venv .venv && .venv/bin/pip install -e ".[dev,sicro]"
.venv/bin/pytest
```

## Autor

[Kenyo Veloso Chianca](https://github.com/VC202504), engenheiro civil. Os leitores das bases nasceram no
[BLOCKINFRA](https://github.com/VC202504/sobre-blockinfra), programa de projeto de infraestrutura e orçamento.

Licença MIT.

---

## English summary

MCP server that gives AI assistants (Claude, Cursor, etc.) access to Brazil's official construction cost databases:
**SINAPI** (Caixa/IBGE, all 27 states, monthly), **SICRO** (DNIT, roads), **ORSE** (Sergipe) and **SEINFRA** (Ceará).
It downloads the public files straight from the government sources into a local SQLite/FTS5 database, then exposes
tools to search items, compare prices across states, track price history, build quick budgets and compute BDI (markup)
using the formula and reference ranges of Brazil's Federal Court of Accounts (TCU Ruling 2622/2013).

```bash
claude mcp add sinapi -- uvx --from "sinapi-mcp[sicro] @ git+https://github.com/VC202504/sinapi-mcp" sinapi-mcp
```
