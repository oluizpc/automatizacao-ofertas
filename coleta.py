"""Coleta de 1 termo na Biblioteca de Anúncios (página pública, sem login)."""
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import config
import seletores as S

log = logging.getLogger("minerador")

_RE_ID = re.compile(S.RE_ID)
_RE_INICIO = re.compile(S.RE_INICIO)
_RE_VARIACOES = re.compile(S.RE_VARIACOES)
_RE_TOTAL = re.compile(S.RE_TOTAL, re.I)
_RE_TEMPO = re.compile(S.RE_TEMPO_VIDEO)
_RE_SEM_RESULTADO = re.compile(S.RE_SEM_RESULTADO, re.I | re.M)
_RE_LEGENDA = re.compile(S.RE_LEGENDA_DOMINIO)
_RE_DATA_PT = re.compile(r"(\d{1,2})\s+de\s+([a-zç]{3})\w*\.?\s+de\s+(\d{4})", re.I)
_RE_DATA_EN = re.compile(r"([A-Za-z]{3})\w*\.?\s+(\d{1,2}),\s*(\d{4})")
_INVISIVEIS = "​‌‍﻿\xa0"


@dataclass
class ResultadoBusca:
    status: str                      # ok / sem_resultados / bloqueio / vazia / erro
    total_estimado: int | None = None
    anuncios: list = field(default_factory=list)
    detalhe: str = ""


# --- Parsing ---------------------------------------------------------------

def parse_data(txt: str) -> str | None:
    m = _RE_DATA_PT.search(txt)
    if m:
        dia, mes, ano = m.groups()
    else:
        m = _RE_DATA_EN.search(txt)
        if not m:
            return None
        mes, dia, ano = m.groups()
    n = S.MESES.get(mes[:3].lower())
    if not n:
        return None
    try:
        return date(int(ano), n, int(dia)).isoformat()
    except ValueError:
        return None


def parse_total(txt: str) -> int | None:
    m = _RE_TOTAL.search(txt)
    if not m:
        return None
    num, mil = m.groups()
    if mil:  # "1,2 mil resultados"
        return int(float(num.replace(".", "").replace(",", ".")) * 1000)
    return int(re.sub(r"[.,]", "", num))


def desembrulhar_link(href: str) -> str:
    """l.facebook.com/l.php?u=... -> URL real, sem fbclid/utm_*."""
    p = urlparse(href)
    if p.netloc.endswith("l.facebook.com") and p.path.startswith("/l.php"):
        href = parse_qs(p.query).get("u", [href])[0]
        p = urlparse(href)
    q = [(k, v) for k, vs in parse_qs(p.query, keep_blank_values=True).items() for v in vs
         if not (k.startswith("utm_") or k in ("fbclid", "gclid"))]
    return urlunparse(p._replace(query=urlencode(q)))


def _eh_link_fb(href: str) -> bool:
    host = urlparse(href).netloc
    return host.endswith("facebook.com") and not host.startswith("l.")


def _plataformas(prefixos) -> str:
    nomes = []
    for d in prefixos:
        nome = next((v for k, v in S.PLATAFORMAS_SVG.items() if d.startswith(k)), None)
        if nome and nome not in nomes:
            nomes.append(nome)
    return ",".join(nomes)


def parse_card(card: dict) -> dict | None:
    """Converte o card bruto (do JS) em um anúncio. None se inativo."""
    linhas = [l.strip(_INVISIVEIS + " \t") for l in card["texto"].split("\n")]
    linhas = [l for l in linhas if l]
    if any(l in S.ROTULO_INATIVO for l in linhas[:4]):
        return None
    texto_card = "\n".join(linhas)

    m = _RE_INICIO.search(texto_card)
    inicio = parse_data(m.group(1)) if m else None
    m = _RE_VARIACOES.search(texto_card)
    variacoes = int(m.group(1)) if m else 1

    pagina = next((l for l in card["links"] if _eh_link_fb(l["href"])), None)
    destino = next((l for l in card["links"] if not _eh_link_fb(l["href"])), None)
    anunciante = pagina["texto"].strip() if pagina else None
    if destino:
        link_destino = desembrulhar_link(destino["href"])
    elif any(l in S.MARCAS_WHATSAPP for l in linhas):
        link_destino = S.DESTINO_WHATSAPP
    else:
        link_destino = None

    # Texto do anúncio: depois de "Patrocinado" até a legenda do link ou o tempo do vídeo.
    corpo = []
    try:
        i = next(i for i, l in enumerate(linhas) if l in S.ROTULO_PATROCINADO)
        legenda = destino["texto"].strip().split("\n")[0].strip() if destino else None
        for l in linhas[i + 1:]:
            if (legenda and l == legenda) or _RE_TEMPO.match(l) or _RE_LEGENDA.match(l):
                break
            corpo.append(l)
    except StopIteration:
        pass
    if not anunciante:
        try:
            anunciante = linhas[linhas.index(next(l for l in linhas if l in S.ROTULO_PATROCINADO)) - 1]
        except (StopIteration, ValueError):
            anunciante = None

    # Formato: vídeo tem contador "0:00 / 0:16"; carrossel tem vários links de destino.
    n_destinos = sum(1 for l in card["links"] if not _eh_link_fb(l["href"]))
    if any(_RE_TEMPO.match(l) for l in linhas):
        formato = "video"
    elif n_destinos > 1:
        formato = "carrossel"
    else:
        formato = "imagem"

    # Título do link: a linha logo depois da legenda do domínio ("CAFECOMDEUSPAI.COM").
    titulo_link = None
    for i, l in enumerate(linhas[:-1]):
        if _RE_LEGENDA.match(l):
            prox = linhas[i + 1]
            # muitas vezes é só o nome da página: aí não diz nada sobre o produto
            mesmo_anunciante = anunciante and prox.casefold() == anunciante.casefold()
            if prox not in S.MARCAS_WHATSAPP and not _RE_LEGENDA.match(prox) and not mesmo_anunciante:
                titulo_link = prox
            break

    return {
        "id_biblioteca": card["id"],
        "anunciante": anunciante,
        "pagina_fb": pagina["href"] if pagina else None,
        "inicio_veiculacao": inicio,
        "n_variacoes": variacoes,
        "plataformas": _plataformas(card.get("plataformas", [])),
        "texto": "\n".join(corpo).strip() or None,
        "link_destino": link_destino,
        "formato": formato,
        "titulo_link": titulo_link,
    }


# --- Navegação -----------------------------------------------------------

def _ler_cards(page) -> list[dict]:
    return page.evaluate(S.JS_CARDS, {"reId": S.RE_ID, "rotulosPlat": S.ROTULO_PLATAFORMAS})


def _estado_pagina(page) -> tuple[str, str]:
    """Classifica a página: ok / sem_resultados / bloqueio / vazia."""
    url = page.url.lower()
    if any(b in url for b in S.URL_BLOQUEIO):
        return "bloqueio", f"redirecionado para {page.url}"
    try:
        corpo = page.inner_text("body", timeout=10_000)
    except Exception:
        corpo = ""
    baixo = corpo.lower()
    for t in S.TEXTOS_BLOQUEIO:
        if t in baixo:
            return "bloqueio", f"texto de bloqueio: {t!r}"
    if _RE_ID.search(corpo):
        return "ok", ""
    if _RE_SEM_RESULTADO.search(corpo):
        return "sem_resultados", ""
    return "vazia", "nenhum card nem mensagem de resultado"


def buscar_termo(page, termo: str, pais: str, limite: int, pausar) -> ResultadoBusca:
    """Abre a busca, rola até `limite` anúncios ou o fim e devolve os anúncios ativos.

    `pausar()` é chamada entre rolagens (ritmo humano); deve devolver False se o
    usuário pediu para parar.
    """
    url = S.url_busca(termo, pais)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=config.TIMEOUT_PAGINA)
    except Exception as e:
        return ResultadoBusca("erro", detalhe=f"falha ao abrir: {e}")

    # Espera aparecer um card, "nenhum resultado" ou um bloqueio. Consulta em laço porque
    # a página às vezes recarrega sozinha na 1ª visita (o que derruba um wait_for_function).
    estado, detalhe = "vazia", ""
    for _ in range(config.ESPERA_CONTEUDO):
        page.wait_for_timeout(1000)
        try:
            estado, detalhe = _estado_pagina(page)
        except Exception:
            continue
        if estado != "vazia":
            break
    page.wait_for_timeout(1500)  # deixa terminar de pintar os primeiros cards
    try:
        total = parse_total(page.inner_text("body", timeout=10_000))
    except Exception:
        total = None
    if estado != "ok":
        return ResultadoBusca(estado, total_estimado=total, detalhe=detalhe)

    cards = _ler_cards(page)
    sem_novidade = 0
    while len(cards) < limite and sem_novidade < config.ROLAGENS_SEM_NOVIDADE:
        if not pausar():
            break
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(2500)
        novos = _ler_cards(page)
        sem_novidade = sem_novidade + 1 if len(novos) <= len(cards) else 0
        cards = novos
        log.debug("  rolagem: %d cards", len(cards))

    anuncios = []
    for c in cards[:limite]:
        try:
            a = parse_card(c)
        except Exception as e:  # um card estranho não derruba a busca
            log.warning("  card %s não lido: %s", c.get("id"), e)
            continue
        if a:
            anuncios.append(a)
    return ResultadoBusca("ok", total_estimado=total, anuncios=anuncios)
