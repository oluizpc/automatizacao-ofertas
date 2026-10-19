"""Banco SQLite (arquivo único minerador.db)."""
import sqlite3
from datetime import date, datetime

import config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS anuncios (
    id_biblioteca     TEXT PRIMARY KEY,
    oferta_id         INTEGER,
    anunciante        TEXT,
    pagina_fb         TEXT,
    inicio_veiculacao TEXT,            -- AAAA-MM-DD
    n_variacoes       INTEGER,
    plataformas       TEXT,            -- separadas por vírgula
    texto             TEXT,
    link_destino      TEXT,
    pais_busca        TEXT,
    termo             TEXT,
    colecao           TEXT,
    visto_primeiro_em TEXT,
    visto_ultimo_em   TEXT
);
CREATE INDEX IF NOT EXISTS ix_anuncios_oferta ON anuncios(oferta_id);

-- Em que dias cada anúncio foi visto ativo (base para os snapshots).
CREATE TABLE IF NOT EXISTS anuncio_vistos (
    id_biblioteca TEXT,
    data          TEXT,
    PRIMARY KEY (id_biblioteca, data)
);

CREATE TABLE IF NOT EXISTS ofertas (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    chave                TEXT UNIQUE,
    nicho                TEXT,
    nome_produto         TEXT,
    anunciante_principal TEXT,
    url_pagina           TEXT,
    preco                TEXT,
    checkout             TEXT,
    bumps                TEXT,
    formato_dominante    TEXT,
    promessa             TEXT,
    angulo               TEXT,
    existe_es            TEXT,         -- sim / pouco / não
    n_es                 INTEGER,
    top_es               TEXT,
    nota                 INTEGER,
    motivo_nota          TEXT,
    status               TEXT DEFAULT 'nova'  -- nova/acompanhando/descartada/modelando
);

CREATE TABLE IF NOT EXISTS snapshots (
    oferta_id         INTEGER,
    data              TEXT,
    n_anuncios_ativos INTEGER,
    n_anunciantes     INTEGER,
    PRIMARY KEY (oferta_id, data)
);

CREATE TABLE IF NOT EXISTS execucoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio        TEXT,
    fim           TEXT,
    colecoes      TEXT,
    teste         INTEGER DEFAULT 0,
    buscas_feitas INTEGER DEFAULT 0,
    bloqueios     INTEGER DEFAULT 0,
    erros         INTEGER DEFAULT 0,
    status        TEXT                -- rodando / concluida / parada / bloqueada / limite / horario
);

-- Progresso por termo: permite continuar de onde parou se o PC reiniciar.
CREATE TABLE IF NOT EXISTS execucao_termos (
    execucao_id INTEGER,
    colecao     TEXT,
    termo       TEXT,
    pais        TEXT,
    status      TEXT DEFAULT 'pendente',   -- pendente / feito / falhou
    PRIMARY KEY (execucao_id, colecao, termo, pais)
);

CREATE TABLE IF NOT EXISTS buscas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    execucao_id    INTEGER,
    data_hora      TEXT,
    colecao        TEXT,
    termo          TEXT,
    pais           TEXT,
    status         TEXT,          -- ok / sem_resultados / bloqueio / vazia / erro
    total_estimado INTEGER,
    n_anuncios     INTEGER,
    n_novos        INTEGER
);
"""


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def hoje() -> str:
    return date.today().isoformat()


# Colunas acrescentadas depois da fase 1: entram sozinhas em bancos já existentes.
COLUNAS_EXTRAS = {
    "anuncios": {"formato": "TEXT", "titulo_link": "TEXT"},
    "ofertas": {
        "tipo_destino": "TEXT",          # site / checkout / whatsapp / sem_link / app / perfil
        "n_anuncios": "INTEGER",         # ativos no último dia em que a oferta foi vista
        "n_anunciantes": "INTEGER",
        "inicio_mais_antigo": "TEXT",
        "paises": "TEXT",
        "idioma": "TEXT",
        "colecoes": "TEXT",
        "link_biblioteca": "TEXT",
        "tendencia_7d": "REAL",          # variação % no nº de anúncios (snapshots)
        "pontos": "INTEGER",
        "descarte": "TEXT",              # motivo do descarte automático (nicho proibido etc.)
        "visto_ultimo_em": "TEXT",
        "atualizado_em": "TEXT",
    },
}


def _migrar(con):
    for tabela, colunas in COLUNAS_EXTRAS.items():
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
        for nome, tipo in colunas.items():
            if nome not in existentes:
                con.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
    con.commit()


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(ESQUEMA)
    _migrar(con)
    return con


# --- Execuções -----------------------------------------------------------

def execucao_aberta(con, colecoes: str, teste: bool):
    """Execução de hoje, com as mesmas coleções, que não terminou (PC reiniciou etc.)."""
    return con.execute(
        "SELECT * FROM execucoes WHERE fim IS NULL AND colecoes=? AND teste=? "
        "AND substr(inicio,1,10)=? ORDER BY id DESC LIMIT 1",
        (colecoes, int(teste), hoje()),
    ).fetchone()


def nova_execucao(con, colecoes: str, teste: bool, itens) -> int:
    cur = con.execute(
        "INSERT INTO execucoes (inicio, colecoes, teste, status) VALUES (?,?,?,'rodando')",
        (agora(), colecoes, int(teste)),
    )
    eid = cur.lastrowid
    con.executemany(
        "INSERT OR IGNORE INTO execucao_termos (execucao_id, colecao, termo, pais) VALUES (?,?,?,?)",
        [(eid, c, t, p) for c, t, p in itens],
    )
    con.commit()
    return eid


def termos_pendentes(con, eid: int):
    return [
        (r["colecao"], r["termo"], r["pais"])
        for r in con.execute(
            "SELECT * FROM execucao_termos WHERE execucao_id=? AND status!='feito' ORDER BY rowid",
            (eid,),
        )
    ]


def marcar_termo(con, eid, colecao, termo, pais, status):
    con.execute(
        "UPDATE execucao_termos SET status=? WHERE execucao_id=? AND colecao=? AND termo=? AND pais=?",
        (status, eid, colecao, termo, pais),
    )
    con.commit()


def somar_execucao(con, eid, campo: str, n: int = 1):
    assert campo in ("buscas_feitas", "bloqueios", "erros")
    con.execute(f"UPDATE execucoes SET {campo}={campo}+? WHERE id=?", (n, eid))
    con.commit()


def fechar_execucao(con, eid, status: str):
    con.execute("UPDATE execucoes SET fim=?, status=? WHERE id=?", (agora(), status, eid))
    con.commit()


def marcar_status_execucao(con, eid, status: str):
    con.execute("UPDATE execucoes SET status=? WHERE id=?", (status, eid))
    con.commit()


def buscas_hoje(con) -> int:
    return con.execute(
        "SELECT COUNT(*) FROM buscas WHERE substr(data_hora,1,10)=?", (hoje(),)
    ).fetchone()[0]


def bloqueios_hoje(con) -> int:
    return con.execute(
        "SELECT COALESCE(SUM(bloqueios),0) FROM execucoes WHERE substr(inicio,1,10)=?", (hoje(),)
    ).fetchone()[0]


def registrar_busca(con, eid, colecao, termo, pais, status, total, n_anuncios, n_novos):
    con.execute(
        "INSERT INTO buscas (execucao_id, data_hora, colecao, termo, pais, status, total_estimado,"
        " n_anuncios, n_novos) VALUES (?,?,?,?,?,?,?,?,?)",
        (eid, agora(), colecao, termo, pais, status, total, n_anuncios, n_novos),
    )
    con.commit()


# --- Anúncios ------------------------------------------------------------

def salvar_anuncios(con, anuncios, colecao, termo, pais) -> int:
    """Insere ou atualiza (sem duplicar pelo ID). Devolve quantos eram novos."""
    ts, dia = agora(), hoje()
    novos = 0
    for a in anuncios:
        existe = con.execute(
            "SELECT 1 FROM anuncios WHERE id_biblioteca=?", (a["id_biblioteca"],)
        ).fetchone()
        if existe:
            con.execute(
                "UPDATE anuncios SET anunciante=?, pagina_fb=?, inicio_veiculacao=?, n_variacoes=?,"
                " plataformas=?, texto=?, link_destino=?, formato=?, titulo_link=?, visto_ultimo_em=?"
                " WHERE id_biblioteca=?",
                (a["anunciante"], a["pagina_fb"], a["inicio_veiculacao"], a["n_variacoes"],
                 a["plataformas"], a["texto"], a["link_destino"], a.get("formato"),
                 a.get("titulo_link"), ts, a["id_biblioteca"]),
            )
        else:
            novos += 1
            con.execute(
                "INSERT INTO anuncios (id_biblioteca, anunciante, pagina_fb, inicio_veiculacao,"
                " n_variacoes, plataformas, texto, link_destino, formato, titulo_link, pais_busca,"
                " termo, colecao, visto_primeiro_em, visto_ultimo_em)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (a["id_biblioteca"], a["anunciante"], a["pagina_fb"], a["inicio_veiculacao"],
                 a["n_variacoes"], a["plataformas"], a["texto"], a["link_destino"],
                 a.get("formato"), a.get("titulo_link"), pais, termo, colecao, ts, ts),
            )
        con.execute(
            "INSERT OR IGNORE INTO anuncio_vistos (id_biblioteca, data) VALUES (?,?)",
            (a["id_biblioteca"], dia),
        )
    con.commit()
    return novos
