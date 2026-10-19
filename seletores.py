"""Tudo que depende do HTML/texto da Biblioteca de Anúncios fica AQUI.

Quando a Meta mudar a página e a coleta quebrar, só este arquivo deve ser ajustado.
Rode `python app.py --teste` depois de qualquer mudança para validar.
"""
from urllib.parse import quote

URL_BUSCA = (
    "https://www.facebook.com/ads/library/?active_status=active&ad_type=all"
    "&country={pais}&q={termo}&search_type=keyword_unordered&media_type=all"
)
URL_ANUNCIO = "https://www.facebook.com/ads/library/?id={id}"


def url_busca(termo: str, pais: str) -> str:
    return URL_BUSCA.format(pais=pais, termo=quote(termo))


# --- Card de anúncio -------------------------------------------------------
# O card é achado a partir do texto "Identificação da biblioteca: 123...":
# sobe-se na árvore até o maior bloco que contém um único ID.
RE_ID = r"(?:Identificação da biblioteca|Library ID|Identificador de la biblioteca):\s*(\d+)"
RE_INICIO = (
    r"(?:Veiculação iniciada em|Started running on|Empezó a circular el)\s*"
    r"(.+?\d{4})"
)
RE_VARIACOES = r"(\d+)\s+(?:anúncios usam|ads use|anuncios usan)"
RE_TOTAL = r"~?\s*([\d.,]+)\s*(mil)?\s*(?:resultados|results)"
RE_TEMPO_VIDEO = r"^\d+:\d\d\s*/\s*\d+:\d\d$"
# Legenda do link no card, ex. "CAFECOMDEUSPAI.COM" ou "API.WHATSAPP.COM": marca o fim do texto.
RE_LEGENDA_DOMINIO = r"^[A-Z0-9-]+(?:\.[A-Z0-9-]+)*\.[A-Z]{2,}(?:/\S*)?$"

# Anúncio que leva ao WhatsApp não tem <a>: só a legenda e o botão.
MARCAS_WHATSAPP = [
    "API.WHATSAPP.COM", "WA.ME", "Enviar mensagem pelo WhatsApp",
    "Send WhatsApp message", "Send message on WhatsApp", "Enviar mensaje de WhatsApp",
]
DESTINO_WHATSAPP = "whatsapp"

ROTULO_PATROCINADO = {"Patrocinado", "Sponsored"}
ROTULO_ATIVO = {"Ativo", "Active", "Activo"}
ROTULO_INATIVO = {"Inativo", "Inactive", "Inactivo"}
ROTULO_PLATAFORMAS = ["Plataformas", "Platforms"]

MESES = {
    "jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5,
    "jun": 6, "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "out": 10, "oct": 10,
    "nov": 11, "dez": 12, "dec": 12, "dic": 12, "ene": 1,
}

# Ícones de plataforma são SVGs sem rótulo: identificados pelo início do 1º <path d="...">.
PLATAFORMAS_SVG = {
    "M12 6.022C12": "facebook",
    "M6 3.227a2.7": "instagram",
    "M6 0c3.17 0 ": "audience_network",
    "M6 0C2.706 0": "messenger",
    "M6.006.06c1.": "threads",
    "M4.28 2.92a.": "whatsapp",
}

# --- Estado da página -----------------------------------------------------
TEXTOS_BLOQUEIO = [
    "captcha", "tente novamente mais tarde", "try again later",
    "temporariamente bloqueado", "temporarily blocked", "you're temporarily blocked",
    "inténtalo de nuevo más tarde", "security check", "verificação de segurança",
]
URL_BLOQUEIO = ["/checkpoint", "/login", "captcha"]
# "0 resultados" sem pegar "10 resultados"; avaliado sem diferenciar maiúsculas.
RE_SEM_RESULTADO = (
    r"(?:^|[^\d.,])~?0\s+(?:resultados|results)\b"
    r"|nenhum anúncio corresponde|no ads match|não encontramos nenhum"
)

# JS executado na página: devolve os dados brutos de cada card.
JS_CARDS = r"""
(args) => {
  const reId = new RegExp(args.reId);
  const contaIds = (t) => (t.match(new RegExp(args.reId, 'g')) || []).length;
  const folhas = [...document.querySelectorAll('span,div')]
    .filter(e => e.childElementCount === 0 && reId.test(e.textContent));
  const vistos = new Set();
  const cards = [];
  for (const folha of folhas) {
    const id = folha.textContent.match(reId)[1];
    if (vistos.has(id)) continue;
    vistos.add(id);
    let n = folha;
    while (n.parentElement && n.parentElement !== document.body) {
      if (contaIds(n.parentElement.textContent) > 1) break;
      n = n.parentElement;
    }
    let plataformas = [];
    const rot = [...n.querySelectorAll('span')]
      .find(s => args.rotulosPlat.includes(s.textContent.trim()));
    if (rot && rot.nextElementSibling) {
      plataformas = [...rot.nextElementSibling.querySelectorAll('svg')]
        .map(svg => { const p = svg.querySelector('path'); return p ? (p.getAttribute('d') || '') : ''; });
    }
    cards.push({
      id,
      texto: n.innerText,
      links: [...n.querySelectorAll('a[href]')].map(a => ({href: a.href, texto: a.innerText})),
      plataformas,
    });
  }
  return cards;
}
"""
