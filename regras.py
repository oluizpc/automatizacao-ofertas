"""Regras de agrupamento, filtro e nota (seções 5 e 7 da especificação).

Ajuste aqui as listas de palavras e os pontos; a lógica fica em ofertas.py.
Os textos são comparados sem acento e em minúsculas.
"""

# --- Destinos ---------------------------------------------------------------
# Destinos que NÃO são página de vendas: agrupados por anunciante e mandados para Descartados.
HOSTS_APP = ["play.google.com", "apps.apple.com", "itunes.apple.com", "onelink.me", "app.link"]
HOSTS_PERFIL = [
    "instagram.com", "facebook.com", "fb.me", "m.me", "fb.com", "youtube.com", "youtu.be",
    "tiktok.com", "linktr.ee", "threads.net", "threads.com", "t.me", "x.com", "twitter.com",
    "spotify.com", "open.spotify.com", "linkin.bio", "beacons.ai",
]
HOSTS_WHATSAPP = ["wa.me", "api.whatsapp.com", "whatsapp.com", "chat.whatsapp.com", "wa.link"]
# WhatsApp/sem link: frase de abertura com pelo menos N palavras agrupa sozinha (sem anunciante).
PALAVRAS_FRASE_CHAVE = 5

# Checkouts: a chave da oferta inclui o 1º trecho do caminho (o código do produto).
CHECKOUTS = {
    "hotmart": ["hotmart.com", "hotmart.host", "hotm.art"],
    "kiwify": ["kiwify.com.br", "kiwify.app", "kiwify.com"],
    "eduzz": ["eduzz.com", "sun.eduzz.com", "chk.eduzz.com"],
    "payt": ["payt.com.br"],
    "perfectpay": ["perfectpay.com.br"],
    "wiapy": ["wiapy.com", "wiapy.com.br"],
    "ticto": ["ticto.app", "ticto.com.br"],
    "lastlink": ["lastlink.com"],
    "monetizze": ["monetizze.com.br"],
    "braip": ["braip.com", "ev.braip.com"],
    "cakto": ["cakto.com.br", "pay.cakto.com.br"],
    "greenn": ["greenn.com.br", "payfast.greenn.com.br"],
}

# --- Nichos proibidos (seção 2): a oferta vai para Descartados ------------
# Expressões regulares; \b = limite de palavra.
NICHOS_PROIBIDOS = {
    # "aposta" sozinho pega "todos apostavam que…": só termos de jogo de verdade.
    "cassino/apostas": [r"\bcassino", r"\bcasino\b", r"casa de apostas", r"apostas? esportiv",
                        r"apostas? online", r"\bbets?\b", r"\broleta", r"tigrinho", r"\bslots?\b",
                        r"jogo do bicho", r"\bblaze\b", r"\bapuestas\b"],
    "cripto": [r"\bcripto", r"\bcrypto", r"bitcoin", r"\bbtc\b", r"day ?trade", r"\bforex",
               r"opcoes binarias"],
    "renda fácil": [r"renda facil", r"dinheiro facil", r"ganhe dinheiro rapido",
                    r"enriquec\w* rapid", r"renda passiva garantida", r"dinero facil"],
    "saúde com promessa médica": [r"emagrec", r"perder \d+ ?kg", r"\bdiabetes", r"glicemia",
                                  r"pressao alta", r"hipertensao", r"colesterol", r"\bremedio",
                                  r"medicamento", r"disfuncao eretil", r"impotencia", r"artrose",
                                  r"neuropatia", r"bajar de peso", r"adelgaz"],
    "conteúdo adulto": [r"\+18\b", r"\bsexo\b", r"\bsexual", r"\berotic", r"\bnudes?\b",
                        r"onlyfans", r"conteudo adulto", r"\blibido"],
    # Só pedido explícito de dinheiro: falar de dízimo/doação não basta.
    "vaquinha/doação": [r"vaquinha", r"vakinha", r"\bdoe agora", r"\bdoe qualquer valor",
                        r"faca (sua|uma) doacao", r"qualquer valor", r"contribua agora",
                        r"ajude com \w+ valor", r"\bdona ahora", r"haz tu donacion",
                        r"cualquier monto"],
}
# Na URL (ex.: doe.site.com.br, site.com/doacao) basta aparecer uma vez.
URL_PROIBIDA = {"vaquinha/doação": [r"(^|[/.])doe[./]", r"doacao", r"vakinha", r"vaquinha",
                                    r"donacion"]}
# Fração mínima dos anúncios da oferta que precisa citar o termo para descartar
# (evita descartar um devocional que fala "doe seu tempo" em um anúncio só).
FRACAO_PROIBIDO = 0.3

# --- Produto simples de reproduzir (+1) ---------------------------------
PRODUTO_SIMPLES = [r"\bpdf\b", r"\be-?book", r"apostila", r"devocional", r"\bmoldes?\b",
                   r"\bkit\b", r"planner", r"caderno", r"\bguia\b", r"livro digital",
                   r"imprim", r"atividades", r"estudo biblico", r"novena", r"plano de leitura",
                   r"\bpatrones\b", r"actividades", r"imprimible", r"libro digital"]

# --- Idioma ------------------------------------------------------------------
PALAVRAS_PT = {"voce", "nao", "do", "da", "dos", "das", "seu", "sua", "com", "uma", "isso",
               "pelo", "pela", "tambem", "sao", "nos", "ate", "agora", "filho", "filhos", "mae",
               "oracao", "voces", "meu", "minha", "aqui", "muito"}
PALAVRAS_ES = {"usted", "tu", "el", "los", "las", "del", "con", "mas", "que", "su", "sus",
               "muy", "hoy", "y", "hijos", "mama", "nuestro", "nuestra", "mi", "mis", "esta",
               "este", "aqui", "ahora", "oracion", "puedes", "tienes"}
# (palavras em comum são descontadas automaticamente)

# --- Nota (seção 7) ---------------------------------------------------------
PONTOS = {
    "anuncios_15": 2, "anuncios_30": 3,
    "idade_14": 1, "idade_60": 2,
    "anunciantes_2": 2,
    "crescimento_30": 2,
    "produto_simples": 1,
}
# pontos -> nota: até 1 = 1, 2-3 = 2, 4-6 = 3, 7-9 = 4, 10+ = 5
FAIXAS_NOTA = [(10, 5), (7, 4), (4, 3), (2, 2)]

# Ofertas vistas há mais de N dias saem da aba Ofertas (continuam no banco).
DIAS_RECENTES = 7
