"""Minerador de Ofertas — ponto de entrada.

Fase 1 (coleta), pela linha de comando:
    python app.py --teste                          # 2 termos, 20 anúncios cada
    python app.py --colecoes cristao_familia --ate 18:00
    python app.py --listar                         # mostra as coleções
"""
import argparse
import sys
from datetime import datetime

import banco
import rodada


def _hora(txt: str):
    return datetime.strptime(txt, "%H:%M").time()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Minerador de Ofertas (Biblioteca de Anúncios da Meta)")
    ap.add_argument("--teste", action="store_true", help="roda 2 termos, 20 anúncios cada")
    ap.add_argument("--colecoes", help="coleções separadas por vírgula (padrão no teste: a 1ª)")
    ap.add_argument("--ate", type=_hora, help="rodar até HH:MM")
    ap.add_argument("--listar", action="store_true", help="lista as coleções de colecoes.yaml")
    ap.add_argument("--ver", action="store_true", help="exporta os anúncios minerados para CSV e abre no Excel")
    ap.add_argument("--planilha", action="store_true",
                    help="agrupa em ofertas, calcula a nota e abre a planilha .xlsx do dia")
    ap.add_argument("--nao-abrir", action="store_true", help="gera a planilha sem abrir o Excel")
    args = ap.parse_args()

    if args.ver:
        _exportar_anuncios()
        return
    if args.planilha:
        _gerar_planilha(abrir=not args.nao_abrir)
        return

    cfg = rodada.carregar_colecoes()
    if args.listar:
        for nome, c in cfg.items():
            print(f"{nome}: {len(c.get('termos_pt', []))} termos x {c.get('paises_busca')}")
        return

    if args.colecoes:
        colecoes = [c.strip() for c in args.colecoes.split(",") if c.strip()]
    elif args.teste:
        colecoes = [next(iter(cfg))]
    else:
        ap.error("informe --colecoes (ou use --teste). A interface gráfica chega na fase 4.")

    r = rodada.Rodada(colecoes, ate=args.ate, teste=args.teste)
    resultado = r.executar()

    if args.teste:
        _resumo_teste()
    if resultado != "erro":
        _gerar_planilha(abrir=False)
    sys.exit(0 if resultado in ("concluida", "horario", "limite") else 1)


def _gerar_planilha(abrir: bool):
    import os

    import ofertas
    import planilha

    con = banco.conectar()
    st = ofertas.processar(con)
    arq, n_boas, n_desc = planilha.gerar(con)
    con.close()
    print(f"\nOfertas: {n_boas} | descartadas: {n_desc} "
          f"(site {st.get('tipo_site', 0)}, checkout {st.get('tipo_checkout', 0)}, "
          f"WhatsApp {st.get('tipo_whatsapp', 0)}, sem link {st.get('tipo_sem_link', 0)}, "
          f"app {st.get('tipo_app', 0)}, perfil {st.get('tipo_perfil', 0)})")
    print(f"Planilha: {arq}")
    if abrir and sys.platform == "win32":
        os.startfile(arq)


def _exportar_anuncios():
    """Visão provisória (até a planilha da fase 2): todos os anúncios em um CSV para o Excel."""
    import csv
    import os

    import config
    import seletores

    pasta = config.RAIZ / "saida"
    pasta.mkdir(exist_ok=True)
    arq = pasta / f"anuncios_{banco.hoje()}.csv"
    con = banco.conectar()
    linhas = con.execute(
        "SELECT * FROM anuncios ORDER BY link_destino, inicio_veiculacao"
    ).fetchall()
    cab = ["anunciante", "início veiculação", "variações", "plataformas", "link de destino",
           "link da biblioteca", "texto", "termo", "país", "coleção", "visto primeiro em",
           "visto último em", "página do FB"]
    try:
        f = open(arq, "w", newline="", encoding="utf-8-sig")  # utf-8-sig: acentos certos no Excel
    except PermissionError:
        print(f"Feche o arquivo {arq.name} no Excel e rode de novo.")
        return
    with f:
        w = csv.writer(f, delimiter=";")  # ";" é o separador do Excel em português
        w.writerow(cab)
        for a in linhas:
            w.writerow([
                a["anunciante"], a["inicio_veiculacao"], a["n_variacoes"], a["plataformas"],
                a["link_destino"], seletores.URL_ANUNCIO.format(id=a["id_biblioteca"]),
                (a["texto"] or "").replace("\n", " "), a["termo"], a["pais_busca"], a["colecao"],
                a["visto_primeiro_em"], a["visto_ultimo_em"], a["pagina_fb"],
            ])
    con.close()
    print(f"{len(linhas)} anúncios exportados para {arq}")
    if sys.platform == "win32":
        os.startfile(arq)


def _resumo_teste():
    """Mostra amostras do que foi salvo, para conferir se os seletores estão certos."""
    con = banco.conectar()
    total = con.execute("SELECT COUNT(*) FROM anuncios").fetchone()[0]
    campos = ["anunciante", "inicio_veiculacao", "n_variacoes", "plataformas", "link_destino", "texto"]
    print(f"\n=== Conferência dos seletores — {total} anúncios no banco ===")
    for c in campos:
        cheios = con.execute(f"SELECT COUNT(*) FROM anuncios WHERE {c} IS NOT NULL AND {c}!=''").fetchone()[0]
        print(f"  {c:<18} preenchido em {cheios}/{total}")
    print("\nAmostra:")
    for a in con.execute("SELECT * FROM anuncios ORDER BY visto_ultimo_em DESC LIMIT 5"):
        texto = (a["texto"] or "").replace("\n", " ")[:90]
        print(f"- {a['id_biblioteca']} | {a['anunciante']} | início {a['inicio_veiculacao']} | "
              f"{a['n_variacoes']} var. | {a['plataformas']}\n    {a['link_destino']}\n    {texto}")
    con.close()


if __name__ == "__main__":
    main()
