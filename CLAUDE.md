# Minerador de Ofertas

Varre a Biblioteca de Anúncios da Meta (página pública, sem login), agrupa anúncios em ofertas,
dá nota de oportunidade LATAM (1–5) e gera planilha. Especificação completa: [minerador-ofertas.md](minerador-ofertas.md).

## Regras de trabalho

- **NÃO fazer commit nem push sem autorização explícita do usuário.**
- Construir uma fase por vez (seção 11 da especificação) e testar com `python app.py --teste` antes de entregar.
- Responder em português. O usuário não é programador: explicar resultados de forma simples.
- Nunca usar login, nunca contornar bloqueio, manter o ritmo humano (seção 2 da especificação).

## Status das fases

| Fase | Status |
|---|---|
| 1. Coleta | ✅ feita e testada (rodada real `cristao_familia`: 12 buscas, 14 min, 0 bloqueios) |
| 2. Agrupamento + nota + planilha | ✅ feita e testada (657 anúncios → 236 ofertas + 66 descartadas) |
| 3. Página de vendas + checagem ES | ⏳ próxima |
| 4. Interface (FastAPI, Iniciar/Parar, ranking, atalho .bat) | ⏳ |
| 5. Snapshots + tendência + "novidades desde ontem" | ⏳ (snapshots e tendência já são gravados na fase 2; falta a parte de "novidades") |
| 6. Classificação com Claude (opcional) | ⏳ |

## Comandos

```
python app.py --teste                              # 2 termos, 20 anúncios cada (valida seletores)
python app.py --colecoes cristao_familia           # roda coleção inteira (gera planilha no fim)
python app.py --colecoes a,b --ate 18:00           # várias coleções até um horário
python app.py --listar                             # lista coleções
python app.py --ver                                # CSV cru dos anúncios (saida/anuncios_*.csv), abre no Excel
python app.py --planilha [--nao-abrir]             # agrupa, dá nota, gera saida/ofertas_AAAA-MM-DD.xlsx
```

Python 3.14, Windows. Dependências: `pip install -r requirements.txt` + `python -m playwright install chromium`.

## Arquivos

- `seletores.py` — **tudo que depende do HTML da Meta** (URL, regex do card, ícones SVG das plataformas, textos de bloqueio). Quando a coleta quebrar, só ajustar aqui.
- `regras.py` — listas e pontos do agrupamento/filtro/nota (hosts de app/perfil/WhatsApp/checkout, nichos proibidos, produto simples, idioma, faixas da nota).
- `coleta.py` — busca 1 termo com Playwright e converte cada card em dict (`parse_card`).
- `rodada.py` — orquestra: ritmo 4–12 s, 300 buscas/dia, pausa longa a cada 40, 3 falhas seguidas → pausa 60 min, 2º bloqueio do dia → encerra; retomada por termo; impede o Windows de dormir.
- `ofertas.py` — agrupa anúncios em ofertas, descarta, calcula pontos/nota/motivo, grava snapshot.
- `planilha.py` — gera o .xlsx (abas Ofertas, Descartados, Checagem ES).
- `banco.py` — SQLite `minerador.db` (schema + migração automática de colunas em `COLUNAS_EXTRAS`).
- `config.py` — constantes (ritmo, limites, HEADLESS, caminhos).
- `logs/AAAA-MM-DD.txt` e `logs/erros/*.png`; saídas em `saida/` (ambos no .gitignore, assim como o .db).

## Decisões tomadas (e o porquê)

- **Card do anúncio** é achado pelo texto "Identificação da biblioteca: N" subindo até o maior bloco com um único ID — não depende de classes CSS (que a Meta ofusca).
- **Plataformas** são SVGs sem rótulo: identificadas pelo início do `path d=` (`PLATAFORMAS_SVG`).
- **Anúncios inativos** às vezes aparecem mesmo com filtro de ativos → descartados no parse.
- **Espera da página**: laço consultando o estado por até 30 s (a 1ª visita às vezes recarrega sozinha e derrubava um `wait_for_function`, gerando falsa "página vazia").
- **WhatsApp** não tem `<a>` no card: `link_destino = "whatsapp"`.
- **"Ativos" de uma oferta** = soma de `n_variacoes` dos anúncios vistos no último dia em que a oferta apareceu (tabela `anuncio_vistos`).
- **Chave da oferta**: site → domínio; checkout → domínio + código do produto; app/perfil → anunciante (vão para Descartados); **WhatsApp/sem link → frase de abertura (5+ palavras) sozinha**, para juntar páginas diferentes com o mesmo texto (desvio consciente da spec, que dizia anunciante + frase; frase curta ainda junta com anunciante). Ex.: "Se você é mãe e sente seu filho…" = 168 anúncios, 4 anunciantes.
- **Filtro de nicho proibido**: precisa aparecer em ≥30% dos anúncios da oferta (ou na URL). Termos foram restringidos depois de falsos positivos ("apostavam" ≠ aposta; falar de dízimo ≠ vaquinha).
- **Nota hoje** (sem fase 3): anúncios, idade, 2+ anunciantes, crescimento (snapshots), produto simples. Preço e ES ficam "pendente" → nota máxima atual na prática é 4. Faixas: ≤1→1, 2–3→2, 4–6→3, 7–9→4, 10+→5.
- `promessa` é provisória (1ª frase do texto mais repetido) até a fase 6; `nome_produto`/`nicho`/`checkout`/`promessa` usam COALESCE para não sobrescrever valores futuros.
- Aba Ofertas mostra só ofertas vistas nos últimos 7 dias (`DIAS_RECENTES`).
- `titulo_link` igual ao nome do anunciante é ignorado (não diz nada do produto).

## Observações dos dados (para próximas fases)

- `cristao_familia`: termos PT nos EUA trazem pouco; "novena" nos EUA traz muito ruído em espanhol (usuário ainda não decidiu se remove).
- Ofertas sem link (formulário/direct) e WhatsApp são grande parte do volume.
- osmend.com = devocional de 40 dias **em espanhol** já escalado (concorrência ES).
- Usuário pode ter a planilha de referência `ofertas_mineradas_LATAM.xlsx` — se aparecer na pasta, alinhar colunas/abas a ela.

## Próximo passo: fase 3

Abrir a página de vendas de cada oferta (1x/dia; tipo site/checkout): título, preço(s), checkout (hotmart, kiwify…), order bumps. Checagem ES: buscar `termos_es` em todos os países (`country=ALL`), contar resultados, top 3 anunciantes, preencher `existe_es`/`n_es`/`top_es` e a aba Checagem ES. Somar na nota: ES (+3/+1/−2), ticket ≤ R$50/US$15 (+1), ES 50+ do mesmo player (−3). Buscas ES contam no limite de 300/dia e seguem o mesmo ritmo.
