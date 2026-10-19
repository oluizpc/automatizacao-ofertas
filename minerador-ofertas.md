# Minerador de Ofertas — especificação para construir

> Documento para entregar ao Claude Code (VS Code) e construir o app do zero.
> Objetivo: abrir o app de manhã, escolher uma **coleção de palavras-chave**, clicar em **Iniciar** e, à noite, encontrar uma **planilha e um painel** com as ofertas escaladas do dia, já com nota de oportunidade para LATAM.

---

## 1. O que o app faz (em uma frase)

Varre a **Biblioteca de Anúncios da Meta** (página pública, sem login) por palavras-chave, agrupa os anúncios por oferta, mede sinais de escala, confere se já existe versão em espanhol, lê a página de vendas e entrega um ranking de ofertas para modelar.

## 2. Regras que não mudam

1. **Nunca usar login.** Nada de conta pessoal, Gerenciador de Anúncios, Business, Hotmart ou checkout. Só páginas públicas.
2. **Ritmo humano.** Pausa aleatória de 4–12 s entre ações, no máximo ~300 buscas por dia, e pausa longa (15–30 min) a cada 40 buscas.
3. **Se for bloqueado, para.** Se aparecer captcha, "tente mais tarde" ou página vazia 3 vezes seguidas: pausa 60 min. Na segunda vez no mesmo dia, encerra e registra no log. Não tentar contornar bloqueio.
4. **Não baixar criativos em massa.** Guardar só o link do anúncio e uma miniatura pequena (opcional).
5. **Ignorar nichos proibidos:** cassino/apostas, cripto, "renda fácil", saúde com promessa médica, conteúdo adulto, vaquinhas.

> **Atenção:** os Termos da Meta restringem a coleta automatizada. Por isso o app roda devagar, sem login, só para pesquisa pessoal, e sem revender dados. O risco prático é ter o IP bloqueado temporariamente; não envolve a conta de anúncios, já que não há login.

## 3. Stack sugerida

| Parte | Tecnologia | Por quê |
|---|---|---|
| Navegação | **Python + Playwright** (Chromium headless) | A Biblioteca é carregada via JavaScript |
| Banco | **SQLite** (arquivo único `minerador.db`) | Histórico entre dias, sem servidor |
| Interface | **FastAPI + uma página HTML simples** (ou Streamlit) | Abrir no navegador em `localhost:8000` |
| Exportação | **openpyxl** | Planilha `.xlsx` do dia |
| Classificação (opcional) | **API do Claude** (modelo barato, ex.: Haiku) | Escrever promessa, ângulo e nicho em 1 linha |
| Agendamento | Botão Iniciar/Parar + "rodar até HH:MM" | Simples; nada de serviço do Windows |

Rodar no Windows com `python app.py`, e de preferência criar um atalho `.bat` na área de trabalho.

## 4. Coleções de palavras-chave

Arquivo `colecoes.yaml`, editável pela interface:

```yaml
cristao_familia:
  paises_busca: [BR, US]
  termos_pt: [devocional, "devocional para casais", "oração pelos filhos", "21 dias de oração", novena, "estudo bíblico pdf"]
  termos_es: ["devocional para parejas", "oración por mis hijos", novena, "estudio bíblico pdf"]
artesanato_renda_extra:
  paises_busca: [BR]
  termos_pt: [moldes, "crochê pdf", "apostila", "projetos de", "receitas pdf"]
  termos_es: [moldes, "crochet pdf", "patrones"]
maternidade_infantil:
  paises_busca: [BR, US]
  termos_pt: ["atividades para crianças", "kit atividades", "desenvolvimento infantil"]
  termos_es: ["actividades para niños", "estimulación"]
sazonal_natal:
  paises_busca: [BR]
  termos_pt: ["natal moldes", "decoração de natal pdf", "ceia de natal"]
  termos_es: ["moldes navideños", "decoración navideña"]
```

O usuário escolhe uma ou mais coleções e clica em **Iniciar**.

## 5. Fluxo de uma rodada

```
Para cada termo da coleção (país de busca, "Todos os anúncios", ativos):
  1. Abrir a busca na Biblioteca e rolar até ~100 anúncios ou o fim.
  2. Extrair de cada card: ID da biblioteca, anunciante, página do FB,
     data "Veiculação iniciada em", nº "X anúncios usam este criativo",
     plataformas, texto do anúncio, link de destino.
  3. Salvar no banco (sem duplicar pelo ID do anúncio).
Agrupar os anúncios em OFERTAS (chave = domínio da página de destino;
  se o destino for WhatsApp, chave = anunciante + 1ª frase do texto).
Para cada oferta nova ou alterada:
  4. Abrir a página de vendas (1 vez por dia) e extrair: título, preço(s),
     plataforma de checkout (hotmart, kiwify, wiapy, payt, eduzz, perfectpay…),
     order bump/planos visíveis.
  5. Checagem ES: buscar o termo equivalente em espanhol em TODOS os países
     e contar os resultados (guardar os 3 maiores anunciantes).
  6. (Opcional) Mandar texto do anúncio + página para o Claude e receber
     JSON: nicho, nome do produto, promessa (1 linha), ângulo (1 linha).
  7. Calcular a nota (seção 7).
Gerar a planilha do dia e atualizar o painel.
```

## 6. Banco de dados (mínimo)

- `anuncios`: id_biblioteca, oferta_id, anunciante, inicio_veiculacao, n_variacoes, texto, link_destino, pais_busca, termo, visto_primeiro_em, visto_ultimo_em
- `ofertas`: id, chave, nicho, nome_produto, anunciante_principal, url_pagina, preco, checkout, bumps, formato_dominante, promessa, angulo, existe_es (sim/pouco/não), n_es, top_es, nota, motivo_nota, status (nova/acompanhando/descartada/modelando)
- `snapshots`: oferta_id, data, n_anuncios_ativos, n_anunciantes (**é o que mostra se a oferta está crescendo ou morrendo**)
- `execucoes`: início, fim, coleções, buscas feitas, bloqueios, erros

## 7. Nota de oportunidade LATAM (1 a 5)

Pontos somados e convertidos em nota de 1 a 5:

| Sinal | Pontos |
|---|---|
| 15+ anúncios ativos | +2 (30+ = +3) |
| Anúncio mais antigo com 14+ dias | +1 (60+ dias = +2) |
| 2+ anunciantes diferentes com o mesmo ângulo | +2 (**oferta validada pelo mercado**) |
| Crescimento ≥ 30% no nº de anúncios em 7 dias (snapshots) | +2 |
| Espanhol: 0–10 anúncios no mundo | +3 · 11–40: +1 · 40+: −2 |
| Produto simples de reproduzir (PDF, kit, devocional, moldes) | +1 |
| Ticket até US$ 15 / R$ 50 | +1 |
| Já existe versão ES com 50+ anúncios do mesmo player | −3 |
| Nicho proibido (seção 2) | descarta |

Toda nota vem com o **motivo** escrito ("40 anúncios, 3 anunciantes, 0 em ES, PDF a R$ 14,90").

## 8. Interface (uma página)

1. **Topo:** escolher coleções, campo "rodar até" (ex.: 18:00) e botões **Iniciar / Parar**, mais o status ao vivo (termo atual, buscas feitas, ofertas novas, último erro).
2. **Ranking do dia:** tabela ordenada por nota, com filtros (nicho, nota mínima, só novas, tem ES?) e as colunas da seção 9.
3. **Ficha da oferta** (clique na linha): os anúncios, a evolução de anúncios ativos por dia (gráfico simples), a página de vendas, a checagem ES e os botões de status (Descartar / Acompanhar / Vou modelar).
4. **Exportar .xlsx** (abas: Ofertas, Descartados, Checagem ES), no mesmo formato da planilha `ofertas_mineradas_LATAM.xlsx` que já usamos.
5. **Novidades desde ontem:** ofertas novas e ofertas que **cresceram** mais de 30%.

## 9. Colunas da planilha (igual à que já usamos)

nicho · nome do produto · anunciante · link da biblioteca · link da página de vendas · nº anúncios ativos · data do anúncio mais antigo · país · idioma · preço · order bumps/upsell · formato dominante · promessa principal · ângulo dos criativos · já existe em espanhol? · nota LATAM · motivo da nota · **tendência 7 dias** · **nº de anunciantes**

## 10. Robustez

- **Seletores em um único arquivo** (`seletores.py`): a Meta muda o HTML com frequência, e quando quebrar, só esse arquivo é ajustado.
- **Salvar progresso a cada termo:** se o PC reiniciar, continua de onde parou.
- **Log** em `logs/AAAA-MM-DD.txt` e print da tela quando algo falhar (`logs/erros/`).
- **Modo teste:** `python app.py --teste` roda 2 termos, 20 anúncios cada, para validar seletores.
- PC ligado e sem suspender enquanto roda. O app avisa se a energia estiver configurada para dormir.

## 11. Fases de construção (pedir ao Claude Code uma por vez)

1. **Coleta:** script que busca 1 termo e salva os anúncios no SQLite. Validar com o modo teste.
2. **Agrupamento + nota + planilha:** gera o `.xlsx` a partir do banco.
3. **Página de vendas + checagem ES.**
4. **Interface** com Iniciar/Parar, ranking e exportação.
5. **Snapshots diários + tendência + "novidades desde ontem".**
6. (Opcional) **Classificação com o Claude** (promessa/ângulo/nicho), com limite de gasto diário configurável.

Instrução padrão para o Claude Code em cada fase:
> "Construa a fase X do arquivo minerador-ofertas.md. Teste com o modo teste antes de me entregar. **NÃO faça commit nem push sem minha autorização.**"

## 12. O que o app não faz (de propósito)

- Não copia criativos, textos ou PDFs de ninguém: aponta **o que** modelar. O produto é sempre nosso e original.
- Não decide sozinho o que lançar. A palavra final é sempre a análise humana sobre as 3 melhores do dia.
