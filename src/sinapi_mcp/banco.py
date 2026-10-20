"""Banco local (SQLite com busca de texto FTS5) com as bases importadas.

Cada importação é um "pacote": uma base, uma UF, um regime e uma competência. As descrições ficam uma vez por base e
código; os preços, um por pacote. Competências antigas continuam guardadas, então dá para refazer um orçamento com os
preços da sua data e ver a evolução de um item.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from .modelo import UF_FIXA, Item

ESQUEMA = """
CREATE TABLE IF NOT EXISTS pacote(
    id INTEGER PRIMARY KEY, base TEXT NOT NULL, uf TEXT NOT NULL, regime TEXT NOT NULL, competencia TEXT NOT NULL,
    itens INTEGER NOT NULL, importado TEXT NOT NULL, UNIQUE(base, uf, regime, competencia));
CREATE TABLE IF NOT EXISTS item(
    id INTEGER PRIMARY KEY, base TEXT NOT NULL, codigo TEXT NOT NULL, descricao TEXT NOT NULL, unidade TEXT,
    tipo TEXT, grupo TEXT, UNIQUE(base, codigo));
CREATE TABLE IF NOT EXISTS preco(
    pacote INTEGER NOT NULL, item INTEGER NOT NULL, valor REAL NOT NULL, PRIMARY KEY(pacote, item)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS preco_item ON preco(item);
CREATE VIRTUAL TABLE IF NOT EXISTS item_fts USING fts5(descricao, grupo, tokenize="unicode61 remove_diacritics 2");
"""

# bases que separam o regime de encargos (as outras gravam regime "")
COM_REGIME = {"SINAPI", "SEINFRA"}


def pasta_padrao() -> Path:
    if os.environ.get("SINAPI_MCP_DADOS"):
        return Path(os.environ["SINAPI_MCP_DADOS"])
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "sinapi-mcp"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "sinapi-mcp"


@dataclass
class Pacote:
    id: int
    base: str
    uf: str
    regime: str
    competencia: str
    itens: int
    importado: str


@dataclass
class Linha:
    base: str
    codigo: str
    descricao: str
    unidade: str
    tipo: str
    grupo: str
    preco: float | None = None
    uf: str = ""
    regime: str = ""
    competencia: str = ""


RADICAL = 6      # palavras longas viram prefixo do radical: "bombeado" acha "bombeável", "cerâmico" acha "cerâmica"


def consulta_fts(texto: str, juncao: str = " ") -> str:
    """Texto livre → consulta FTS5, cada palavra como prefixo ("concreto fck 25" → "concre"* "fck"* "25"*). Com
    `juncao` " OR ", basta uma das palavras (a ordenação por relevância põe primeiro quem tem mais)."""
    palavras = re.findall(r"\w+", texto.lower())
    return juncao.join(f'"{p[:RADICAL] if len(p) > RADICAL + 1 else p}"*' for p in palavras)


class Banco:
    def __init__(self, caminho: str | Path | None = None):
        if caminho is None:
            caminho = pasta_padrao() / "precos.db"
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho = caminho
        self.con = sqlite3.connect(caminho, check_same_thread=False)
        self.con.executescript(ESQUEMA)

    def fechar(self) -> None:
        self.con.close()

    # ------------------------------------------------------------------ gravação

    def importar(self, base: str, uf: str, regime: str, competencia: str, itens: list[Item]) -> Pacote:
        """Grava (ou substitui) um pacote."""
        base, uf = base.upper(), uf.upper()
        regime = regime if base in COM_REGIME else ""
        c = self.con
        with c:
            antigo = c.execute("SELECT id FROM pacote WHERE base=? AND uf=? AND regime=? AND competencia=?",
                               (base, uf, regime, competencia)).fetchone()
            if antigo:
                c.execute("DELETE FROM preco WHERE pacote=?", antigo)
                c.execute("DELETE FROM pacote WHERE id=?", antigo)
            agora = dt.datetime.now().isoformat(timespec="seconds")
            pid = c.execute("INSERT INTO pacote(base, uf, regime, competencia, itens, importado) VALUES (?,?,?,?,?,?)",
                            (base, uf, regime, competencia, len(itens), agora)).lastrowid
            conhecidos = {cod: (iid, d, g) for iid, cod, d, g in
                          c.execute("SELECT id, codigo, descricao, grupo FROM item WHERE base=?", (base,))}
            precos = []
            for it in itens:
                atual = conhecidos.get(it.codigo)
                if atual is None:
                    iid = c.execute("INSERT INTO item(base, codigo, descricao, unidade, tipo, grupo) VALUES (?,?,?,?,?,?)",
                                    (base, it.codigo, it.descricao, it.unidade, it.tipo, it.grupo)).lastrowid
                    c.execute("INSERT INTO item_fts(rowid, descricao, grupo) VALUES (?,?,?)", (iid, it.descricao, it.grupo))
                    conhecidos[it.codigo] = (iid, it.descricao, it.grupo)
                else:
                    iid = atual[0]
                    if (it.descricao, it.grupo) != atual[1:]:        # a descrição mais recente prevalece
                        c.execute("UPDATE item SET descricao=?, unidade=?, tipo=?, grupo=? WHERE id=?",
                                  (it.descricao, it.unidade, it.tipo, it.grupo, iid))
                        c.execute("DELETE FROM item_fts WHERE rowid=?", (iid,))
                        c.execute("INSERT INTO item_fts(rowid, descricao, grupo) VALUES (?,?,?)",
                                  (iid, it.descricao, it.grupo))
                        conhecidos[it.codigo] = (iid, it.descricao, it.grupo)
                precos.append((pid, iid, it.preco))
            c.executemany("INSERT OR REPLACE INTO preco(pacote, item, valor) VALUES (?,?,?)", precos)
        return Pacote(pid, base, uf, regime, competencia, len(itens), agora)

    # ------------------------------------------------------------------ leitura

    def pacotes(self, base: str | None = None) -> list[Pacote]:
        sql = "SELECT id, base, uf, regime, competencia, itens, importado FROM pacote"
        args: tuple = ()
        if base:
            sql += " WHERE base=?"
            args = (base.upper(),)
        return [Pacote(*r) for r in self.con.execute(sql + " ORDER BY base, uf, regime, competencia DESC", args)]

    def escolher_pacote(self, base: str, uf: str | None, regime: str | None, competencia: str | None) -> Pacote | None:
        """O pacote de uma base para a UF, o regime e a competência pedidos (a mais recente, se vazia)."""
        base = base.upper()
        uf = UF_FIXA.get(base) or (uf or "").upper()
        if not uf:
            return None
        reg = (regime or "sd") if base in COM_REGIME else ""
        sql = "SELECT id, base, uf, regime, competencia, itens, importado FROM pacote WHERE base=? AND uf=? AND regime=?"
        args: list = [base, uf, reg]
        if competencia:
            sql += " AND competencia=?"
            args.append(competencia)
        r = self.con.execute(sql + " ORDER BY competencia DESC LIMIT 1", args).fetchone()
        return Pacote(*r) if r else None

    def _linhas(self, sql: str, args) -> list[Linha]:
        return [Linha(*r) for r in self.con.execute(sql, args)]

    def buscar(self, texto: str, pacotes: list[Pacote], tipo: str | None = None, limite: int = 20) -> list[Linha]:
        """Itens dos pacotes cuja descrição (ou grupo) tem todas as palavras do texto, os mais relevantes primeiro.
        Um código exato também é achado."""
        if not pacotes:
            return []
        ids = ",".join(str(p.id) for p in pacotes)
        filtro_tipo = " AND i.tipo=?" if tipo else ""
        extra = [tipo] if tipo else []
        campos = ("i.base, i.codigo, i.descricao, i.unidade, i.tipo, i.grupo, p.valor, k.uf, k.regime, k.competencia "
                  "FROM item i JOIN preco p ON p.item=i.id JOIN pacote k ON k.id=p.pacote")
        exatos = self._linhas(f"SELECT {campos} WHERE i.codigo=? AND k.id IN ({ids}){filtro_tipo}",
                              [texto.strip().upper(), *extra])
        achados = []
        for juncao in (" ", " OR "):              # todas as palavras; se nada, as que houver
            q = consulta_fts(texto, juncao)
            if not q:
                break
            achados = self._linhas(f"SELECT {campos} JOIN item_fts f ON f.rowid=i.id WHERE item_fts MATCH ? "
                                   f"AND k.id IN ({ids}){filtro_tipo} ORDER BY bm25(item_fts, 4.0, 1.0) LIMIT ?",
                                   [q, *extra, limite])
            if achados or exatos:
                break
        vistos = {(x.base, x.codigo, x.uf) for x in exatos}
        return (exatos + [x for x in achados if (x.base, x.codigo, x.uf) not in vistos])[:limite]

    def item(self, base: str, codigo: str) -> Linha | None:
        r = self.con.execute("SELECT base, codigo, descricao, unidade, tipo, grupo FROM item WHERE base=? AND codigo=?",
                             (base.upper(), codigo.strip().upper())).fetchone()
        return Linha(*r) if r else None

    def precos_do_item(self, base: str, codigo: str, uf: str | None = None, regime: str | None = None,
                       competencia: str | None = None) -> list[Linha]:
        """Todos os preços guardados de um item, filtrando por UF, regime e competência."""
        sql = ("SELECT i.base, i.codigo, i.descricao, i.unidade, i.tipo, i.grupo, p.valor, k.uf, k.regime, k.competencia "
               "FROM item i JOIN preco p ON p.item=i.id JOIN pacote k ON k.id=p.pacote WHERE i.base=? AND i.codigo=?")
        args: list = [base.upper(), codigo.strip().upper()]
        for campo, v in (("k.uf", uf and uf.upper()), ("k.regime", regime if base.upper() in COM_REGIME else None),
                         ("k.competencia", competencia)):
            if v:
                sql += f" AND {campo}=?"
                args.append(v)
        return self._linhas(sql + " ORDER BY k.competencia DESC, k.uf, k.regime", args)
