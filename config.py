"""Configurações gerais do Minerador de Ofertas."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DB = RAIZ / "minerador.db"
COLECOES = RAIZ / "colecoes.yaml"
LOGS = RAIZ / "logs"
ERROS = LOGS / "erros"

# Ritmo humano (seção 2 da especificação)
PAUSA_ACAO = (4, 12)                 # segundos entre ações (busca, rolagem)
MAX_BUSCAS_DIA = 300
PAUSA_LONGA_CADA = 40                # buscas
PAUSA_LONGA = (15 * 60, 30 * 60)     # segundos

# Bloqueio
FALHAS_SEGUIDAS = 3                  # captcha / "tente mais tarde" / página vazia
PAUSA_BLOQUEIO = 60 * 60             # segundos
MAX_BLOQUEIOS_DIA = 2                # no 2º bloqueio do dia, encerra

# Coleta
ANUNCIOS_POR_BUSCA = 100
ROLAGENS_SEM_NOVIDADE = 3            # para de rolar após N rolagens sem cards novos
TIMEOUT_PAGINA = 60_000              # ms
ESPERA_CONTEUDO = 30                 # s esperando os cards aparecerem

# Modo teste
TESTE_TERMOS = 2
TESTE_ANUNCIOS = 20

HEADLESS = True
LOCALE = "pt-BR"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
