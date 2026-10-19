"""Agrupa os anúncios em ofertas, aplica os filtros e calcula a nota LATAM (fase 2).

Chave da oferta (seção 5):
  - site comum ........ domínio da página de destino
  - checkout .......... domínio + código do produto (pay.hotmart.com/ABC123)
  - WhatsApp / sem link anunciante + 1ª frase do texto
  - app / perfil ...... anunciante (vão para Descartados: não são página de vendas)
"""
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from urllib.parse import urlparse

import banco
import regras as R
import seletores as S

_PROIBIDOS = {cat: [re.compile(p) for p in ps] for cat, ps in R.NICHOS_PROIBIDOS.items()}
_URL_PROIBIDA = {cat: [re.compile(p) for p in ps] for cat, ps in R.URL_PROIBIDA.items()}
_SIMPLES = [re.compile(p) for p in R.PRODUTO_SIMPLES]
_SO_PT = R.PALAVRAS_PT - R.PALAVRAS_ES
_SO_ES = R.PALAVRAS_ES - R.PALAVRAS_PT


def normalizar(txt: str | None) -> str:
    """Minúsculas, sem acento."""
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt.lower())
    return "".join(c for c in txt if not unicodedata.combining(c))


def primeira_frase(txt: str | None, palavras: int = 8) -> str:
    n = normalizar(txt)
    n = re.split(r"[.!?\n]", n, maxsplit=1)[0]
    return " ".join(re.findall(r"[a-z0-9]+", n)[:palavras])


def _host_em(host: str, lista) -> bool:
    return any(host == h or host.endswith("." + h) for h in lista)


def _chave_conversa(anunciante, texto) -> str:
    """WhatsApp / sem link: a frase de abertura identifica a oferta.

    Com 5+ palavras ela basta sozinha, e assim páginas diferentes rodando o mesmo texto
    caem na mesma oferta (sinal de "2+ anunciantes"). Frase curta ou vazia é genérica
    demais: junta com o anunciante.
    """
    frase = primeira_frase(texto)
    if len(frase.split()) >= R.PALAVRAS_FRASE_CHAVE:
        return f"conversa:{frase}"
    return f"conversa:{normalizar(anunciante) or '?'}|{frase}"


def classificar_destino(link: str | None, anunciante: str | None, texto: str | None):
    """Devolve (tipo_destino, chave, checkout)."""
    quem = normalizar(anunciante) or "?"
    if not link:
        return "sem_link", _chave_conversa(anunciante, texto), None
    if link == S.DESTINO_WHATSAPP:
        return "whatsapp", _chave_conversa(anunciante, texto), None
    p = urlparse(link)
    host = p.netloc.lower().split(":")[0].removeprefix("www.")
    if _host_em(host, R.HOSTS_WHATSAPP):
        return "whatsapp", _chave_conversa(anunciante, texto), None
    if _host_em(host, R.HOSTS_APP):
        return "app", f"app:{quem}", None
    if _host_em(host, R.HOSTS_PERFIL):
        return "perfil", f"perfil:{quem}", None
    for nome, hosts in R.CHECKOUTS.items():
        if _host_em(host, hosts):
            seg = next((s for s in p.path.split("/") if s), "")
            return "checkout", f"{host}/{seg}".rstrip("/"), nome
    return "site", host, None


def detectar_idioma(textos) -> str | None:
    palavras = re.findall(r"[a-z]+", normalizar(" ".join(t for t in textos if t)))
    pt = sum(1 for w in palavras if w in _SO_PT)
    es = sum(1 for w in palavras if w in _SO_ES)
    if pt + es < 3:
        return None
    if pt >= es * 1.5:
        return "pt"
    if es >= pt * 1.5:
        return "es"
    return "pt/es"


def nicho_proibido(textos, url: str | None) -> str | None:
    """Categoria proibida se pelo menos FRACAO_PROIBIDO dos anúncios (ou a URL) a citarem."""
    normais = [normalizar(t) for t in textos]
    url_n = normalizar(url)
    for cat, padroes in _URL_PROIBIDA.items():
        if url_n and any(p.search(url_n) for p in padroes):
            return cat
    for cat, padroes in _PROIBIDOS.items():
        if url_n and any(p.search(url_n) for p in padroes):
            return cat
        hits = sum(1 for t in normais if any(p.search(t) for p in padroes))
        if normais and hits / len(normais) >= R.FRACAO_PROIBIDO:
            return cat
    return None


def produto_simples(textos, url: str | None) -> str | None:
    """Devolve a palavra que indicou produto simples (pdf, devocional, moldes…)."""
    tudo = normalizar(" ".join(t for t in textos if t) + " " + (url or ""))
    for p in _SIMPLES:
        m = p.search(tudo)
        if m:
            return m.group(0).strip()
    return None


def nota_de(pontos: int) -> int:
    for minimo, nota in R.FAIXAS_NOTA:
        if pontos >= minimo:
            return nota
    return 1


def _mais_comum(valores):
    c = Counter(v for v in valores if v)
    return c.most_common(1)[0][0] if c else None


def _tendencia(con, oferta_id: int, dia: str, n_atual: int) -> float | None:
    """Variação % entre o snapshot mais antigo dos últimos 7 dias e o de `dia`."""
    inicio = (date.fromisoformat(dia) - timedelta(days=7)).isoformat()
    r = con.execute(
        "SELECT n_anuncios_ativos FROM snapshots WHERE oferta_id=? AND data>=? AND data<?"
        " ORDER BY data LIMIT 1",
        (oferta_id, inicio, dia),
    ).fetchone()
    if not r or not r[0]:
        return None
    return round((n_atual - r[0]) / r[0] * 100, 1)


def processar(con) -> dict:
    """Recalcula todas as ofertas a partir da tabela de anúncios."""
    hoje = date.today()
    anuncios = con.execute("SELECT * FROM anuncios").fetchall()
    vistos = defaultdict(set)
    for r in con.execute("SELECT id_biblioteca, data FROM anuncio_vistos"):
        vistos[r[0]].add(r[1])

    grupos = defaultdict(list)
    tipos = defaultdict(Counter)
    checkouts = {}
    for a in anuncios:
        tipo, chave, checkout = classificar_destino(a["link_destino"], a["anunciante"], a["texto"])
        grupos[chave].append(a)
        tipos[chave][tipo] += 1
        if checkout:
            checkouts[chave] = checkout

    stats = Counter()
    for chave, ads in grupos.items():
        tipo = tipos[chave].most_common(1)[0][0]
        checkout = checkouts.get(chave)
        con.execute("INSERT OR IGNORE INTO ofertas (chave, status) VALUES (?, 'nova')", (chave,))
        of = con.execute("SELECT * FROM ofertas WHERE chave=?", (chave,)).fetchone()
        oid = of["id"]
        con.executemany("UPDATE anuncios SET oferta_id=? WHERE id_biblioteca=?",
                        [(oid, a["id_biblioteca"]) for a in ads])

        # "Ativos" = anúncios vistos no último dia em que a oferta apareceu.
        ultimo_dia = max((d for a in ads for d in vistos[a["id_biblioteca"]]),
                         default=(ads[0]["visto_ultimo_em"] or banco.agora())[:10])
        ativos = [a for a in ads if ultimo_dia in vistos[a["id_biblioteca"]]] or ads
        n_anuncios = sum(a["n_variacoes"] or 1 for a in ativos)
        anunciantes = {normalizar(a["anunciante"]) for a in ativos if a["anunciante"]}
        n_anunciantes = len(anunciantes)
        inicios = [a["inicio_veiculacao"] for a in ativos if a["inicio_veiculacao"]]
        mais_antigo = min(inicios) if inicios else None
        idade = (hoje - date.fromisoformat(mais_antigo)).days if mais_antigo else 0
        textos = [a["texto"] for a in ativos if a["texto"]]
        url = _mais_comum(a["link_destino"] for a in ativos)
        if url == S.DESTINO_WHATSAPP:
            url = None
        principal = max(ativos, key=lambda a: a["n_variacoes"] or 1)

        # snapshot do dia (base da tendência e das "novidades" da fase 5)
        con.execute(
            "INSERT OR REPLACE INTO snapshots (oferta_id, data, n_anuncios_ativos, n_anunciantes)"
            " VALUES (?,?,?,?)",
            (oid, ultimo_dia, n_anuncios, n_anunciantes),
        )
        tendencia = _tendencia(con, oid, ultimo_dia, n_anuncios)

        # descarte automático
        descarte = None
        if tipo == "app":
            descarte = "destino é app (loja de aplicativos), não página de vendas"
        elif tipo == "perfil":
            descarte = "destino é perfil/rede social, não página de vendas"
        cat = nicho_proibido(textos, url)
        if cat:
            descarte = f"nicho proibido: {cat}"

        # pontos (seção 7) — sinais que dependem da fase 3 ficam de fora por enquanto
        pontos, motivo = 0, []
        if n_anuncios >= 30:
            pontos += R.PONTOS["anuncios_30"]
        elif n_anuncios >= 15:
            pontos += R.PONTOS["anuncios_15"]
        motivo.append(f"{n_anuncios} anúncio{'s' if n_anuncios != 1 else ''}")
        if n_anunciantes >= 2:
            pontos += R.PONTOS["anunciantes_2"]
            motivo.append(f"{n_anunciantes} anunciantes (validada pelo mercado)")
        else:
            motivo.append("1 anunciante")
        if idade >= 60:
            pontos += R.PONTOS["idade_60"]
        elif idade >= 14:
            pontos += R.PONTOS["idade_14"]
        if mais_antigo:
            motivo.append(f"{idade} dias no ar")
        if tendencia is not None:
            if tendencia >= 30:
                pontos += R.PONTOS["crescimento_30"]
            motivo.append(f"tendência {tendencia:+.0f}% em 7 dias")
        simples = produto_simples(textos, url)
        if simples:
            pontos += R.PONTOS["produto_simples"]
            motivo.append(f"produto simples ({simples})")
        if checkout:
            motivo.append(f"checkout {checkout}")
        motivo.append("ES e preço: pendentes (fase 3)")
        nota = nota_de(pontos)

        con.execute(
            """UPDATE ofertas SET
                 tipo_destino=?, n_anuncios=?, n_anunciantes=?, inicio_mais_antigo=?, paises=?,
                 idioma=?, colecoes=?, link_biblioteca=?, tendencia_7d=?, pontos=?, nota=?,
                 motivo_nota=?, descarte=?, visto_ultimo_em=?, atualizado_em=?,
                 anunciante_principal=?, url_pagina=COALESCE(?, url_pagina),
                 formato_dominante=?,
                 nome_produto=COALESCE(nome_produto, ?),
                 nicho=COALESCE(nicho, ?),
                 checkout=COALESCE(checkout, ?),
                 promessa=COALESCE(promessa, ?)
               WHERE id=?""",
            (
                tipo, n_anuncios, n_anunciantes, mais_antigo,
                ",".join(sorted({a["pais_busca"] for a in ads if a["pais_busca"]})),
                detectar_idioma(textos),
                ",".join(sorted({a["colecao"] for a in ads if a["colecao"]})),
                S.URL_ANUNCIO.format(id=principal["id_biblioteca"]),
                tendencia, pontos, nota, ", ".join(motivo), descarte, ultimo_dia, banco.agora(),
                _mais_comum(a["anunciante"] for a in ativos), url,
                _mais_comum(a["formato"] for a in ativos),
                _mais_comum(a["titulo_link"] for a in ativos
                            if normalizar(a["titulo_link"]) != normalizar(a["anunciante"]))
                or _nome_padrao(tipo, chave, principal),
                _mais_comum(a["colecao"] for a in ativos),
                checkout,
                _resumo_promessa(textos),
                oid,
            ),
        )
        stats["descartadas" if descarte else "ofertas"] += 1
        stats[f"tipo_{tipo}"] += 1

    # ofertas que ficaram sem anúncio (ex.: regra de agrupamento mudou) e que ninguém marcou
    stats["removidas"] = con.execute(
        "DELETE FROM ofertas WHERE status='nova' AND id NOT IN"
        " (SELECT DISTINCT oferta_id FROM anuncios WHERE oferta_id IS NOT NULL)"
    ).rowcount
    con.commit()
    return dict(stats)


def _nome_padrao(tipo, chave, ad) -> str:
    if tipo in ("site", "checkout"):
        return chave
    return ad["anunciante"] or chave


def _resumo_promessa(textos) -> str | None:
    """Provisório até a fase 6: 1ª frase do texto mais repetido da oferta."""
    t = _mais_comum(textos)
    if not t:
        return None
    frase = re.split(r"(?<=[.!?])\s|\n", t.strip(), maxsplit=1)[0]
    return frase[:180]
