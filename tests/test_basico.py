import zipfile
from xml.sax.saxutils import escape

import pytest

from sinapi_mcp import bdi, servidor
from sinapi_mcp.banco import Banco, consulta_fts
from sinapi_mcp.fontes import sinapi
from sinapi_mcp.modelo import UFS, Item
from sinapi_mcp.orcamento import orcar


@pytest.fixture
def banco(tmp_path, monkeypatch):
    b = Banco(tmp_path / "t.db")
    b.importar("SINAPI", "PB", "sd", "2026-08", [
        Item("103328", "ALVENARIA DE VEDAÇÃO DE BLOCOS CERÂMICOS FURADOS 9X19X19 CM", "M2", 100.00, "composicao", "ALVE"),
        Item("1379", "CIMENTO PORTLAND COMPOSTO CP II-32", "KG", 0.70, "insumo"),
    ])
    b.importar("SINAPI", "PB", "sd", "2026-09", [
        Item("103328", "ALVENARIA DE VEDAÇÃO DE BLOCOS CERÂMICOS FURADOS 9X19X19 CM", "M2", 104.84, "composicao", "ALVE"),
        Item("1379", "CIMENTO PORTLAND COMPOSTO CP II-32", "KG", 0.72, "insumo"),
        Item("34493", "CONCRETO USINADO BOMBEAVEL, CLASSE DE RESISTENCIA C25", "M3", 580.92, "insumo"),
    ])
    b.importar("SINAPI", "SP", "sd", "2026-09", [Item("1379", "CIMENTO PORTLAND COMPOSTO CP II-32", "KG", 0.80, "insumo")])
    b.importar("SEINFRA", "CE", "sd", "028", [Item("C0074", "ALVENARIA DE TIJOLO CERÂMICO FURADO (9x19x19)cm", "M2", 116.27,
                                                   "composicao")])
    monkeypatch.setattr(servidor, "_banco", b)
    yield b
    b.fechar()


def test_consulta_fts_usa_radical():
    assert consulta_fts("concreto bombeado 25") == '"concre"* "bombea"* "25"*'
    assert consulta_fts("a b", " OR ") == '"a"* OR "b"*'


def test_busca_sem_acento_e_competencia_mais_recente(banco):
    p = banco.escolher_pacote("SINAPI", "PB", "sd", None)
    assert p.competencia == "2026-09"
    achados = banco.buscar("alvenaria ceramico", [p])
    assert [x.codigo for x in achados] == ["103328"]
    assert achados[0].preco == 104.84


def test_busca_por_codigo_e_por_palavra_aproximada(banco):
    p = banco.escolher_pacote("SINAPI", "PB", "sd", None)
    assert banco.buscar("1379", [p])[0].descricao.startswith("CIMENTO")
    assert banco.buscar("concreto bombeado", [p])[0].codigo == "34493"          # "bombeado" acha "bombeável"
    assert banco.buscar("concreto inexistentexyz", [p])[0].codigo == "34493"    # sem todas as palavras, as que houver


def test_reimportar_substitui_o_pacote(banco):
    banco.importar("SINAPI", "SP", "sd", "2026-09", [Item("1379", "CIMENTO PORTLAND COMPOSTO CP II-32", "KG", 0.90, "insumo")])
    assert [x.preco for x in banco.precos_do_item("SINAPI", "1379", "SP")] == [0.90]


def test_historico_de_precos(banco):
    hist = banco.precos_do_item("SINAPI", "103328", "PB", "sd")
    assert [(x.competencia, x.preco) for x in hist] == [("2026-09", 104.84), ("2026-08", 100.00)]


def test_uf_fixa_das_bases_estaduais(banco):
    p = banco.escolher_pacote("SEINFRA", None, "sd", None)
    assert p.uf == "CE" and banco.buscar("tijolo", [p])[0].codigo == "C0074"


def test_orcamento(banco):
    o = orcar(banco, [{"codigo": "103328", "quantidade": 10}, {"codigo": "1379", "quantidade": 100},
                      {"codigo": "999999", "quantidade": 1}], "PB", "sd", None, bdi=25)
    assert o.custo_direto == 1048.40 + 72.00
    assert o.total == round(1120.40 * 1.25, 2)
    assert o.sem_preco == ["SINAPI 999999"]


def test_bdi_formula_do_tcu():
    r = bdi.calcular(ac=4.0, sg=0.8, r=1.27, df=1.23, lucro=7.4, iss=2.5)
    esperado = ((1 + 0.0607) * 1.0123 * 1.074 / (1 - 0.0615) - 1) * 100
    assert r.bdi == round(esperado, 2)
    assert r.tributos == 6.15
    assert r.situacao["AC"] == "dentro" and r.situacao["L"] == "dentro"
    assert bdi.calcular(ac=10, sg=0.8, r=1.27, df=1.23, lucro=7.4).situacao["AC"] == "acima"


def test_ferramentas_do_servidor(banco):
    assert "R$ 104,84" in servidor.buscar_precos("alvenaria", uf="PB")
    assert "informe a UF" in servidor.buscar_precos("alvenaria")
    assert "SEINFRA" in servidor.buscar_precos("tijolo", base="SEINFRA")
    cmp = servidor.comparar_ufs("1379")
    assert cmp.index("| PB |") < cmp.index("| SP |")
    assert "Total com BDI" in servidor.orcar([{"codigo": "103328", "quantidade": 2}], uf="PB", bdi=20)
    assert "BDI =" in servidor.calcular_bdi(4, 0.8, 1.27, 1.23, 7.4, iss=2.5)
    assert "SINAPI 09/2026" in servidor.bases_disponiveis()


def test_codigo_e_preco_do_sinapi():
    assert sinapi.codigo('=HYPERLINK("https://x", 104658)') == "104658"
    assert sinapi.codigo(1379.0) == "1379"
    assert sinapi.preco("1.234,56") == 1234.56
    assert sinapi.preco(12.5) == 12.5
    assert sinapi.preco("") is None


def _xlsx(caminho, abas: dict[str, list[list]]):
    def cel(ref, v):
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'

    def col(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(caminho, "w") as z:
        folhas = "".join(f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(abas))
        z.writestr("xl/workbook.xml", f"<workbook {ns} {rns}><sheets>{folhas}</sheets></workbook>")
        rels = "".join(f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(abas)))
        z.writestr("xl/_rels/workbook.xml.rels",
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for i, linhas in enumerate(abas.values()):
            rows = "".join(f'<row r="{k + 1}">' + "".join(cel(f"{col(j)}{k + 1}", v) for j, v in enumerate(ln)) + "</row>"
                           for k, ln in enumerate(linhas))
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", f"<worksheet {ns}><sheetData>{rows}</sheetData></worksheet>")


def test_conversor_do_sinapi(tmp_path):
    cab = ["Grupo", "Código", "Descrição", "Unidade", *UFS]
    comp = [["SINAPI"], cab, ["ALVE", 103328, "ALVENARIA 9X19X19", "M2", *[100.0 + k for k in range(27)]]]
    ins = [cab, ["", 1379, "CIMENTO CP II-32", "KG", *(["0,72"] * 26 + [""])]]
    arq = tmp_path / "ref.xlsx"
    _xlsx(arq, {"CSD": comp, "CCD": comp, "ISD": ins, "ICD": ins})
    bases = sinapi.converter(arq)
    assert len(bases) == 54
    pb = {i.codigo: i for i in bases[("PB", "sd")]}
    assert pb["103328"].preco == 100.0 + UFS.index("PB") and pb["1379"].preco == 0.72
    assert "1379" not in {i.codigo for i in bases[("TO", "cd")]}      # sem preço na UF: fica de fora
