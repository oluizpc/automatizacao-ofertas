"""Uma rodada de coleta: percorre os termos das coleções com ritmo humano.

Regras (seção 2): sem login, pausa 4–12 s entre ações, até 300 buscas/dia,
pausa longa a cada 40 buscas, e para se for bloqueado (sem tentar contornar).
"""
import ctypes
import logging
import random
import subprocess
import sys
import threading
from datetime import datetime, time as dtime

import yaml
from playwright.sync_api import sync_playwright

import banco
import coleta
import config

log = logging.getLogger("minerador")


def configurar_log():
    config.LOGS.mkdir(exist_ok=True)
    config.ERROS.mkdir(exist_ok=True)
    if log.handlers:
        return
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    arq = logging.FileHandler(config.LOGS / f"{banco.hoje()}.txt", encoding="utf-8")
    arq.setFormatter(fmt)
    arq.setLevel(logging.DEBUG)
    tela = logging.StreamHandler(sys.stdout)
    tela.setFormatter(fmt)
    tela.setLevel(logging.INFO)
    log.addHandler(arq)
    log.addHandler(tela)


def carregar_colecoes() -> dict:
    with open(config.COLECOES, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# --- Energia (Windows) ---------------------------------------------------

_ES_CONTINUOUS, _ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def impedir_suspensao(ligar: bool):
    """Pede ao Windows para não dormir enquanto a rodada estiver ativa."""
    if sys.platform != "win32":
        return
    flags = _ES_CONTINUOUS | (_ES_SYSTEM_REQUIRED if ligar else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def avisar_energia():
    """Avisa se o plano de energia manda o PC dormir (na tomada)."""
    if sys.platform != "win32":
        return
    try:
        saida = subprocess.run(
            ["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        valores = [l.split(":")[-1].strip() for l in saida.splitlines() if ":" in l and "0x" in l]
        ac = int(valores[-2], 16) if len(valores) >= 2 else 0  # penúltimo = na tomada (CA)
        if ac:
            log.warning(
                "O Windows está configurado para dormir após %d min na tomada. O app vai "
                "segurar o PC acordado enquanto roda, mas deixe o notebook ligado na energia.",
                ac // 60,
            )
    except Exception as e:
        log.debug("não consegui ler o plano de energia: %s", e)


# --- Rodada --------------------------------------------------------------

class Rodada:
    def __init__(self, colecoes: list[str], ate: dtime | None = None, teste: bool = False):
        self.colecoes = colecoes
        self.ate = ate
        self.teste = teste
        self.parar_evento = threading.Event()
        self.status = {
            "rodando": False, "termo_atual": None, "buscas": 0, "anuncios_novos": 0,
            "ultimo_erro": None, "mensagem": "",
        }

    # chamado pela interface (fase 4)
    def parar(self):
        self.parar_evento.set()

    def _esperar(self, segundos: float, motivo: str = "") -> bool:
        """Dorme de forma interrompível. Devolve False se pediram para parar."""
        if motivo:
            log.info("%s (%.0f min)", motivo, segundos / 60)
            self.status["mensagem"] = motivo
        return not self.parar_evento.wait(segundos)

    def _pausa_acao(self) -> bool:
        return self._esperar(random.uniform(*config.PAUSA_ACAO))

    def _passou_horario(self) -> bool:
        return self.ate is not None and datetime.now().time() >= self.ate

    def _itens(self, colecoes_cfg: dict):
        itens = []
        for nome in self.colecoes:
            c = colecoes_cfg[nome]
            for pais in c.get("paises_busca", ["BR"]):
                for termo in c.get("termos_pt", []):
                    itens.append((nome, termo, pais))
        return itens[: config.TESTE_TERMOS] if self.teste else itens

    def _print_erro(self, page, rotulo: str):
        nome = f"{datetime.now():%Y-%m-%d_%H%M%S}_{rotulo}.png"
        try:
            page.screenshot(path=str(config.ERROS / nome), full_page=False)
            log.info("  print salvo em logs/erros/%s", nome)
        except Exception as e:
            log.debug("  print falhou: %s", e)

    def executar(self) -> str:
        configurar_log()
        cfg = carregar_colecoes()
        faltando = [c for c in self.colecoes if c not in cfg]
        if faltando:
            raise ValueError(f"Coleções inexistentes em colecoes.yaml: {', '.join(faltando)}")

        con = banco.conectar()
        chave = ",".join(self.colecoes)
        aberta = banco.execucao_aberta(con, chave, self.teste)
        if aberta:
            eid = aberta["id"]
            banco.marcar_status_execucao(con, eid, "rodando")
            log.info("Continuando a execução #%d de hoje, de onde parou.", eid)
        else:
            eid = banco.nova_execucao(con, chave, self.teste, self._itens(cfg))
            log.info("Execução #%d iniciada: %s%s", eid, chave, " (MODO TESTE)" if self.teste else "")

        limite = config.TESTE_ANUNCIOS if self.teste else config.ANUNCIOS_POR_BUSCA
        pendentes = banco.termos_pendentes(con, eid)
        log.info("%d busca(s) pendente(s).", len(pendentes))

        avisar_energia()
        impedir_suspensao(True)
        self.status["rodando"] = True
        resultado_final = "concluida"
        falhas_seguidas = 0
        desde_pausa_longa = 0
        try:
            with sync_playwright() as p:
                nav = p.chromium.launch(headless=config.HEADLESS)
                ctx = nav.new_context(
                    locale=config.LOCALE, user_agent=config.USER_AGENT,
                    viewport={"width": 1366, "height": 900},
                )
                page = ctx.new_page()

                fila = list(pendentes)
                tentativas = {}
                while fila:
                    colecao, termo, pais = fila.pop(0)

                    if self.parar_evento.is_set():
                        resultado_final = "parada"
                        break
                    if self._passou_horario():
                        log.info("Chegou o horário limite (%s). Encerrando.", self.ate.strftime("%H:%M"))
                        resultado_final = "horario"
                        break
                    if banco.buscas_hoje(con) >= config.MAX_BUSCAS_DIA:
                        log.warning("Limite de %d buscas/dia atingido. Encerrando.", config.MAX_BUSCAS_DIA)
                        resultado_final = "limite"
                        break
                    if desde_pausa_longa >= config.PAUSA_LONGA_CADA:
                        if not self._esperar(random.uniform(*config.PAUSA_LONGA),
                                             f"Pausa longa após {desde_pausa_longa} buscas"):
                            resultado_final = "parada"
                            break
                        desde_pausa_longa = 0

                    self.status["termo_atual"] = f"{termo} ({pais})"
                    log.info("Buscando %r em %s [%s]", termo, pais, colecao)
                    r = coleta.buscar_termo(page, termo, pais, limite, self._pausa_acao)
                    desde_pausa_longa += 1
                    self.status["buscas"] += 1
                    banco.somar_execucao(con, eid, "buscas_feitas")

                    novos = 0
                    if r.status in ("ok", "sem_resultados"):
                        falhas_seguidas = 0
                        novos = banco.salvar_anuncios(con, r.anuncios, colecao, termo, pais)
                        banco.marcar_termo(con, eid, colecao, termo, pais, "feito")
                        self.status["anuncios_novos"] += novos
                        log.info("  %s: %d anúncios ativos lidos, %d novos (total na biblioteca: %s)",
                                 r.status, len(r.anuncios), novos, r.total_estimado or "?")
                    else:
                        falhas_seguidas += 1
                        banco.somar_execucao(con, eid, "erros")
                        banco.marcar_termo(con, eid, colecao, termo, pais, "falhou")
                        self.status["ultimo_erro"] = f"{r.status}: {r.detalhe}"
                        log.warning("  %s: %s (falha %d seguida)", r.status, r.detalhe, falhas_seguidas)
                        self._print_erro(page, r.status)
                        # tenta de novo no fim da fila, uma vez
                        k = (colecao, termo, pais)
                        if tentativas.get(k, 0) < 1:
                            tentativas[k] = tentativas.get(k, 0) + 1
                            fila.append(k)

                    banco.registrar_busca(con, eid, colecao, termo, pais, r.status,
                                          r.total_estimado, len(r.anuncios), novos)

                    if falhas_seguidas >= config.FALHAS_SEGUIDAS:
                        banco.somar_execucao(con, eid, "bloqueios")
                        if banco.bloqueios_hoje(con) >= config.MAX_BLOQUEIOS_DIA:
                            log.error("Segundo bloqueio do dia. Encerrando sem tentar contornar.")
                            resultado_final = "bloqueada"
                            break
                        falhas_seguidas = 0
                        if not self._esperar(config.PAUSA_BLOQUEIO,
                                             f"{config.FALHAS_SEGUIDAS} falhas seguidas: possível bloqueio, pausando"):
                            resultado_final = "parada"
                            break

                    if fila and not self._pausa_acao():
                        resultado_final = "parada"
                        break

                nav.close()
        except Exception as e:
            log.exception("Erro inesperado na rodada: %s", e)
            self.status["ultimo_erro"] = str(e)
            resultado_final = "erro"
        finally:
            impedir_suspensao(False)
            self.status["rodando"] = False
            self.status["termo_atual"] = None

        # "parada"/"erro" (ou PC desligado) deixam a execução aberta: ao iniciar de novo
        # no mesmo dia com as mesmas coleções, ela continua de onde parou.
        if resultado_final in ("parada", "erro"):
            banco.marcar_status_execucao(con, eid, resultado_final)
        else:
            banco.fechar_execucao(con, eid, resultado_final)
        log.info("Execução #%d terminou: %s. Buscas: %d, anúncios novos: %d.",
                 eid, resultado_final, self.status["buscas"], self.status["anuncios_novos"])
        con.close()
        return resultado_final
