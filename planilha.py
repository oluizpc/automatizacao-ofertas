"""Gera a planilha do dia (seção 9): abas Ofertas, Descartados e Checagem ES."""
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config
import regras as R

# (título da coluna, largura, função que extrai o valor da oferta)
COLUNAS = [
    ("nicho", 18, lambda o: o["nicho"]),
    ("nome do produto", 30, lambda o: o["nome_produto"]),
    ("anunciante", 24, lambda o: o["anunciante_principal"]),
    ("link da biblioteca", 18, lambda o: o["link_biblioteca"]),
    ("link da página de vendas", 34, lambda o: o["url_pagina"] or _destino_sem_url(o)),
    ("nº anúncios ativos", 11, lambda o: o["n_anuncios"]),
    ("data do anúncio mais antigo", 13, lambda o: _data(o["inicio_mais_antigo"])),
    ("país", 9, lambda o: o["paises"]),
    ("idioma", 8, lambda o: o["idioma"]),
    ("preço", 12, lambda o: o["preco"] or "pendente"),
    ("order bumps/upsell", 18, lambda o: o["bumps"]),
    ("formato dominante", 12, lambda o: o["formato_dominante"]),
    ("promessa principal", 50, lambda o: o["promessa"]),
    ("ângulo dos criativos", 30, lambda o: o["angulo"]),
    ("já existe em espanhol?", 12, lambda o: o["existe_es"] or "pendente"),
    ("nota LATAM", 8, lambda o: o["nota"]),
    ("motivo da nota", 60, lambda o: o["motivo_nota"]),
    ("tendência 7 dias", 11, lambda o: _tendencia(o["tendencia_7d"])),
    ("nº de anunciantes", 11, lambda o: o["n_anunciantes"]),
]
COLUNAS_LINK = {"link da biblioteca", "link da página de vendas"}
COLUNAS_QUEBRA = {"promessa principal", "motivo da nota", "ângulo dos criativos", "nome do produto"}

CAB_FONTE = Font(bold=True, color="FFFFFF")
CAB_FUNDO = PatternFill("solid", fgColor="1F3A5F")
CORES_NOTA = {5: "1E8449", 4: "52BE80", 3: "F4D03F", 2: "F0B27A", 1: "D5D8DC"}


def _data(iso):
    return datetime.strptime(iso, "%Y-%m-%d").date() if iso else None


def _tendencia(v):
    return "sem histórico" if v is None else f"{v:+.0f}%"


def _destino_sem_url(o):
    return {"whatsapp": "WhatsApp", "sem_link": "sem link (formulário/direct)"}.get(o["tipo_destino"])


def _escrever_aba(ws, ofertas, extras=()):
    colunas = list(COLUNAS) + list(extras)
    for i, (titulo, largura, _) in enumerate(colunas, 1):
        c = ws.cell(row=1, column=i, value=titulo)
        c.font, c.fill = CAB_FONTE, CAB_FUNDO
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.row_dimensions[1].height = 32
    for lin, o in enumerate(ofertas, 2):
        for col, (titulo, _, f) in enumerate(colunas, 1):
            v = f(o)
            c = ws.cell(row=lin, column=col, value=v)
            if titulo in COLUNAS_LINK and isinstance(v, str) and v.startswith("http"):
                c.hyperlink = v
                c.value = "abrir anúncio" if titulo == "link da biblioteca" else v
                c.font = Font(color="0563C1", underline="single")
            elif titulo == "data do anúncio mais antigo" and v:
                c.number_format = "DD/MM/YYYY"
            elif titulo == "nota LATAM" and v:
                c.fill = PatternFill("solid", fgColor=CORES_NOTA.get(v, "FFFFFF"))
                c.font = Font(bold=True)
                c.alignment = Alignment(horizontal="center")
            if titulo in COLUNAS_QUEBRA:
                c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "C2"
    if ofertas:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(colunas))}{len(ofertas) + 1}"


def gerar(con):
    """Cria saida/ofertas_AAAA-MM-DD.xlsx e devolve o caminho."""
    desde = (date.today() - timedelta(days=R.DIAS_RECENTES)).isoformat()
    todas = con.execute(
        "SELECT * FROM ofertas WHERE visto_ultimo_em >= ? ORDER BY nota DESC, n_anuncios DESC,"
        " n_anunciantes DESC",
        (desde,),
    ).fetchall()
    boas = [o for o in todas if not o["descarte"] and o["status"] != "descartada"]
    descartadas = [o for o in todas if o["descarte"] or o["status"] == "descartada"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Ofertas"
    _escrever_aba(ws, boas, extras=[("status", 12, lambda o: o["status"])])

    ws = wb.create_sheet("Descartados")
    _escrever_aba(ws, descartadas, extras=[
        ("motivo do descarte", 45, lambda o: o["descarte"] or "descartada manualmente"),
    ])

    ws = wb.create_sheet("Checagem ES")
    cab = ["nome do produto", "anunciante", "termo em espanhol", "anúncios no mundo",
           "top 3 anunciantes em ES", "já existe em espanhol?"]
    for i, t in enumerate(cab, 1):
        c = ws.cell(row=1, column=i, value=t)
        c.font, c.fill = CAB_FONTE, CAB_FUNDO
        ws.column_dimensions[get_column_letter(i)].width = 28
    ws.cell(row=2, column=1, value="Preenchida na fase 3 (checagem ES).").font = Font(italic=True)

    pasta = config.RAIZ / "saida"
    pasta.mkdir(exist_ok=True)
    arq = pasta / f"ofertas_{date.today().isoformat()}.xlsx"
    try:
        wb.save(arq)
    except PermissionError:  # aberta no Excel: salva com a hora no nome
        arq = pasta / f"ofertas_{datetime.now():%Y-%m-%d_%H%M}.xlsx"
        wb.save(arq)
    return arq, len(boas), len(descartadas)
