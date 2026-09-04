# =============================================================================
# modules/modo_tv.py — "Modo TV": painel em loop pra TV/monitor
# Sprint TV (2026-08-30/31) — MRS Sentinel
#
# Pedido do Julio (coordenador de Jundiaí): uma TV parada na coordenação,
# conectada por HDMI a um PC/notebook, mostrando em loop as notas e o
# Unifilar do trecho — sem ninguém precisando mexer em nada.
#
# Como usar na TV (uma vez só, no PC/notebook conectado):
#   1. Logar normalmente no navegador (perfil admin, ou um usuário com
#      "Acesso ao Modo TV" marcado no Painel Admin).
#   2. Clicar em "📺 Modo TV" na barra lateral.
#   3. Escolher a Gerência e o(s) Centro(s) de Trabalho — e, se quiser,
#      um Trecho específico (tela única, só na primeira vez — fica salva
#      pro resto da sessão) — e clicar em "▶️ Iniciar".
#   4. Deixar o navegador em tela cheia (F11) e a sessão aberta —
#      a partir daí a tela gira sozinha, sem precisar recarregar a página.
#   5. "🚪 Sair do Modo TV" (canto superior) volta pro painel normal a
#      qualquer momento — único controle que fica visível de propósito.
#
# Por que não recarrega a página pra trocar de slide: o login deste app
# vive só em st.session_state (sem cookie/token persistente — ver
# auth/session.py) — um location.reload()/navegação JS derrubaria a
# sessão a cada troca. Em vez disso, o loop é INTERNO: time.sleep() +
# st.rerun() dentro da MESMA sessão, sem nunca recarregar o navegador.
#
# ⚠️ Sessão SEM expiração por tempo (não existe token/JWT persistido —
# confirmado em auth/login.py), MAS ela É perdida se o processo do
# Streamlit reiniciar por qualquer motivo (novo deploy/push, o servidor
# reiniciando sozinho, um crash) — nesse caso a TV cai pra tela de login
# e fica parada lá até alguém ir presencialmente logar de novo (não tem
# como reconectar sozinha sem sessão salva). Em fase de desenvolvimento
# ativo (deploys frequentes) isso pode acontecer; depois de estabilizar,
# fica bem mais raro.
#
# Escopo desta v1 (limitação consciente, documentada): 3 "slides" —
# KPIs, Unifilar (por KM + de Ativo + rankings, tudo junto — render_unifilar
# hoje é uma função só, sem como pedir "só uma parte" sem duplicar lógica
# interna arriscada) e Ranking de hot-spots por pátio. Os controles
# interativos do Unifilar (sliders, radios, tabela, downloads) ficam
# escondidos via CSS — a lógica deles continua rodando por baixo com os
# valores padrão, só não aparece na tela.
#
# ⚠️ HISTÓRICO DO FILTRO (pra não repetir os mesmos erros): a v1 filtrava
# por "Coordenação" (ex. Jundiaí), tentando derivar isso de centro_trab.
# Duas tentativas erradas antes desta versão:
#   1ª) comparar o último segmento de centro_trab contra a SIGLA da
#       coordenação (ex. "CIJN") — nunca batia, "CIJN" nunca aparece
#       sozinho no dado (formato real é "V.SP.<algo>").
#   2ª) trocar por comparar contra a LISTA DE PÁTIOS da coordenação
#       (core/glossarios.py::PATIOS_POR_CENTRO) — corrigia a comparação,
#       mas ainda dependia de COORDENACOES_POR_GERENCIA/CENTROS_POR_GERENCIA
#       estarem 100% preenchidos e alinhados (só SP/VP tinham), e mesmo
#       corrigido o Julio reportou "ainda não apareceu nada" numa
#       coordenação com dado real.
# SOLUÇÃO 2026-09-02 (pedido explícito do Julio: "Voce deverá filtrar o
# centro de Trabalho apenas. Deixar a Opção para filtrar os Trechos"):
# abandona a ideia de "Coordenação" inteiramente. Filtra DIRETO pelo valor
# bruto de centro_trab (comparação simples .isin(), sem split/parsing de
# hierarquia nenhum) — exatamente o mesmo mecanismo já usado e comprovado
# em components/filtros.py (filtro "🏢 Centro de Trabalho" de toda tela de
# Gerência). Trecho entra como filtro OPCIONAL adicional, mesma lógica.
# Funciona pra QUALQUER gerência com dado carregado, sem depender de
# nenhum glossário de coordenação/pátio estar preenchido.
#
# Sessão 1: Imports & configuração
# Sessão 2: CSS do Modo TV (esconde sidebar + controles interativos)
# Sessão 3: Tela de seleção (Gerência + Centro de Trabalho + Trecho) + botão de sair
# Sessão 4: Carregamento de dados
# Sessão 5: Slides
# Sessão 6: render_modo_tv() — orquestração + loop
# =============================================================================

# region ====================== SESSÃO 1: Imports & Configuração ===============
import time
from datetime import datetime

import streamlit as st
import pandas as pd

from auth.permissions import require_modo_tv
from auth.session import set_pagina
from components.kpi_card import render_kpi_cards
from components.unifilar import render_unifilar_dual
from components.heatmap import render_ranking
from core.score_engine import calcular_score_dataframe, carregar_score_config
from core.glossarios import normalizar_coluna_ramal, LISTA_GERENCIAS
from database.queries import get_notas_cached

INTERVALO_SLIDE_SEGUNDOS = 25

# Chaves de session_state usadas por este módulo — centralizado aqui pra
# _sair_do_modo_tv() saber exatamente o que limpar.
_CHAVES_SESSAO_TV = [
    "tv_gerencia", "tv_centros", "tv_trechos", "tv_nome_local",
    "tv_slide_idx", "_css_modo_tv_injetado",
]

# endregion


# region ====================== SESSÃO 2: CSS do Modo TV ========================

def _injetar_css_tv():
    """
    Esconde sidebar + todo controle interativo (o Modo TV é só pra ASSISTIR,
    ninguém deve mexer em nada) e aumenta fonte/contraste pra leitura de
    longe. Idempotente via flag de sessão (mesmo padrão do resto do app).
    NÃO é chamada na tela de seleção (Sessão 3) — lá os widgets precisam
    aparecer normalmente.

    stButton NÃO entra na lista de esconder — é o único jeito de deixar o
    botão "🚪 Sair do Modo TV" visível (o Unifilar/Ranking não usam
    st.button "solto" em nenhum ponto do fluxo mostrado aqui, só
    st.download_button, que tem seu próprio testid já coberto abaixo).
    """
    if st.session_state.get("_css_modo_tv_injetado"):
        return
    st.session_state["_css_modo_tv_injetado"] = True

    st.markdown("""
    <style>
    /* Esconde sidebar por completo — Modo TV é tela cheia */
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }
    [data-testid="stMainBlockContainer"] {
        max-width: 100% !important;
        padding: 1.2rem 2rem !important;
    }
    /* Esconde controles interativos do Unifilar (sliders, radios, multiselect,
       downloads, tabela completa, formulários) — a lógica por trás continua
       rodando com os valores padrão, só não aparece na tela. stButton fica
       DE FORA de propósito (ver docstring acima). */
    [data-testid="stSlider"], [data-testid="stRadio"],
    [data-testid="stMultiSelect"], [data-testid="stSelectbox"],
    [data-testid="stDownloadButton"], [data-testid="stDataFrame"],
    [data-testid="stForm"], [data-testid="stFormSubmitButton"] {
        display: none !important;
    }
    /* Fundo escuro + fonte maior — leitura de longe, estilo painel de sala
       de controle. */
    .stApp { background-color: #0f172a !important; }
    [data-testid="stMainBlockContainer"] * {
        color: #f1f5f9;
    }
    h2, h3, h4, h5 { font-size: 1.4em !important; }
    </style>
    """, unsafe_allow_html=True)

# endregion


# region ============ SESSÃO 3: Tela de seleção + botão de sair =================

def _sair_do_modo_tv():
    """Limpa o estado do Modo TV e volta pro painel normal (Visão Geral
    da Gerência escolhida, ou 'gerencia_sp' como fallback antes de
    escolher)."""
    gerencia = st.session_state.get("tv_gerencia") or "SP"
    for chave in _CHAVES_SESSAO_TV:
        st.session_state.pop(chave, None)
    set_pagina(f"gerencia_{gerencia.lower()}")
    st.rerun()


def _botao_sair():
    """Botão fixo de saída — único controle que fica visível de propósito
    durante o loop (ver _injetar_css_tv)."""
    if st.button("🚪 Sair do Modo TV", key="tv_btn_sair"):
        _sair_do_modo_tv()


def _tela_selecao(_loop: bool = True) -> bool:
    """
    Tela de escolha de Gerência + Centro de Trabalho (+ Trecho opcional) —
    aparece só na primeira vez (sidebar normal, sem CSS de esconder).
    Depois de "▶️ Iniciar", a escolha fica em st.session_state pro resto
    da sessão (não pergunta de novo a cada rerun do loop). Ver histórico
    do filtro no cabeçalho do módulo — Centro de Trabalho é comparação
    DIRETA contra o dado bruto, sem depender de nenhum glossário de
    coordenação/pátio.

    Retorna True se a escolha já está pronta (pode seguir pro loop),
    False se ainda está mostrando a tela de seleção (o caller deve parar
    por aqui nesse rerun).
    """
    if st.session_state.get("tv_gerencia") and st.session_state.get("tv_centros"):
        return True

    st.markdown("## 📺 Modo TV — Configuração")
    st.caption(
        "Escolha o(s) Centro(s) de Trabalho que vão ficar em loop na TV — "
        "e, se quiser, restrinja também por Trecho. Só precisa fazer isso "
        "uma vez — fica salvo pro resto da sessão."
    )

    gerencia_sel = st.selectbox("Gerência", LISTA_GERENCIAS, key="tv_sel_gerencia")

    with st.spinner("Carregando Centros de Trabalho disponíveis..."):
        centros_disp = _valores_centro_trab_disponiveis(gerencia_sel)

    if not centros_disp:
        st.warning(
            f"⚠️ Nenhum dado carregado ainda pra Gerência {gerencia_sel} — "
            "faça upload em Upload de Dados primeiro."
        )
        return False

    centros_sel = st.multiselect(
        "🏢 Centro de Trabalho", options=centros_disp, key="tv_sel_centros",
        help="Selecione um ou mais — o Modo TV mostra só as notas desses "
             "Centros de Trabalho (mesma lista usada no filtro das telas de Gerência).",
    )

    trechos_sel: list[str] = []
    if centros_sel:
        trechos_disp = _opcoes_trecho_tv(gerencia_sel, centros_sel)
        if trechos_disp:
            trechos_sel = st.multiselect(
                "🛤️ Trecho (opcional)", options=trechos_disp, key="tv_sel_trechos",
                help="Deixe vazio pra mostrar todos os trechos dos Centros escolhidos.",
            )

    if st.button("▶️ Iniciar Modo TV", type="primary", disabled=not centros_sel, key="tv_btn_iniciar"):
        nome_local = centros_sel[0] if len(centros_sel) == 1 else f"{len(centros_sel)} Centros de Trabalho"
        if trechos_sel:
            nome_local += f" · {len(trechos_sel)} trecho(s)"

        st.session_state["tv_gerencia"] = gerencia_sel
        st.session_state["tv_centros"] = centros_sel
        st.session_state["tv_trechos"] = trechos_sel
        st.session_state["tv_nome_local"] = nome_local
        if not _loop:
            return True
        st.rerun()

    if not centros_sel:
        st.caption("Selecione ao menos um Centro de Trabalho pra habilitar o botão.")

    return False

# endregion


# region ====================== SESSÃO 4: Carregamento de dados =================

@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados_tv(
    gerencia: str, centros: tuple[str, ...], trechos: tuple[str, ...] = (),
) -> pd.DataFrame:
    """VP+EE da Gerência escolhida, filtrado nos Centros de Trabalho (e,
    opcionalmente, Trechos) escolhidos. Mesma lógica de
    modules/gerencia_dashboard.py::_carregar_dados/_aplicar_filtros — mas
    aqui os valores já são raiz, direto, sem widget.

    `centros`/`trechos` são tuple (não list) porque st.cache_data precisa
    de argumentos hasheáveis pra formar a chave do cache.
    """
    frames = []
    for disc in ("VP", "EE"):
        df_d = get_notas_cached(gerencia, disc)
        if not df_d.empty:
            df_d["disciplina_label"] = disc
            frames.append(df_d)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = normalizar_coluna_ramal(df, "ramal")
    if "data_nota" in df.columns:
        df["data_nota"] = pd.to_datetime(df["data_nota"], errors="coerce")
    if "lead_time_dias" in df.columns:
        df["lead_time_dias"] = pd.to_numeric(df["lead_time_dias"], errors="coerce")

    # Filtro por Centro de Trabalho — comparação DIRETA contra o valor
    # bruto de centro_trab (.isin(), sem split/parsing de hierarquia
    # nenhum). Mesmo mecanismo já usado e comprovado em
    # components/filtros.py/modules/gerencia_dashboard.py — ver histórico
    # de tentativas erradas no cabeçalho do módulo.
    if "centro_trab" in df.columns and centros:
        df = df[df["centro_trab"].isin(centros)].copy()

    # Trecho é filtro OPCIONAL adicional (pedido do Julio: "Deixar a
    # Opção para filtrar os Trechos") — tupla vazia = sem filtro, mostra
    # todos os trechos dos Centros escolhidos.
    if "trecho" in df.columns and trechos:
        df = df[df["trecho"].isin(trechos)].copy()

    return df


def _valores_centro_trab_disponiveis(gerencia: str) -> list[str]:
    """
    Centro de Trabalho (valor bruto) realmente presentes nos dados da
    Gerência — usada tanto pra popular o multiselect da tela de seleção
    quanto pro diagnóstico do aviso de "sem dado" (mesma fonte, sem
    duplicar lógica).
    """
    frames = []
    for disc in ("VP", "EE"):
        df_d = get_notas_cached(gerencia, disc)
        if not df_d.empty and "centro_trab" in df_d.columns:
            frames.append(df_d[["centro_trab"]])
    if not frames:
        return []
    todos = pd.concat(frames, ignore_index=True)
    return sorted(todos["centro_trab"].dropna().astype(str).str.strip().unique().tolist())


def _opcoes_trecho_tv(gerencia: str, centros_sel: list[str]) -> list[str]:
    """
    Trechos reais disponíveis nos Centros de Trabalho já escolhidos —
    mesma lógica de components/filtros.py::_opcoes_trechos, sem os
    widgets/cascata completa (aqui só depende de Centro, não de Ramal).
    """
    frames = []
    for disc in ("VP", "EE"):
        df_d = get_notas_cached(gerencia, disc)
        if not df_d.empty and "trecho" in df_d.columns and "centro_trab" in df_d.columns:
            frames.append(df_d[["centro_trab", "trecho"]])
    if not frames:
        return []
    todos = pd.concat(frames, ignore_index=True)
    if centros_sel:
        todos = todos[todos["centro_trab"].isin(centros_sel)]
    return sorted(todos["trecho"].dropna().astype(str).str.strip().unique().tolist())

# endregion


# region ====================== SESSÃO 5: Slides =================================

def _slide_kpis(df: pd.DataFrame, gerencia: str, nome_local: str, chave_local: str):
    st.markdown(f"### 📊 Resumo — {nome_local}")
    render_kpi_cards(df, gerencia=gerencia, disciplina="VP+EE")


def _slide_unifilar(df: pd.DataFrame, gerencia: str, nome_local: str, chave_local: str):
    st.markdown(f"### 🗺️ Unifilar — {nome_local}")
    render_unifilar_dual(df, gerencia=f"TV_{chave_local}")


def _slide_ranking(df: pd.DataFrame, gerencia: str, nome_local: str, chave_local: str):
    st.markdown(f"### 🏆 Hot-spots por Pátio — {nome_local}")
    render_ranking(df, top_n=10, ordem="Score Total", gerencia=f"TV_{chave_local}")


_SLIDES = [_slide_kpis, _slide_unifilar, _slide_ranking]

# endregion


# region ====================== SESSÃO 6: render_modo_tv() ======================

def render_modo_tv(_loop: bool = True):
    """
    Ponto de entrada do Modo TV (rota 'modo_tv'). Primeiro rerun (ou
    quando ainda não escolheu Gerência/Centro de Trabalho nesta sessão):
    tela de seleção (Sessão 3). Depois disso, gira sozinho entre os
    slides definidos em _SLIDES, sem recarregar a página (ver docstring
    do módulo — preserva o login). Admin sempre acessa; outros perfis só
    com 'acesso_tv' marcado (ver auth/permissions.py::can_access_modo_tv).

    _loop=False (só pra teste automatizado): pula o time.sleep()+st.rerun()
    final, renderizando só o slide atual e retornando. Em produção sempre
    roda com o default (_loop=True) — sem esse parâmetro, o AppTest entra
    em loop infinito, porque ele processa cada st.rerun() de forma
    síncrona dentro da MESMA chamada (diferente do navegador real, que
    faz um round-trip de rede a cada rerun).
    """
    require_modo_tv()

    if not _tela_selecao(_loop=_loop):
        return

    gerencia = st.session_state["tv_gerencia"]
    centros = tuple(st.session_state["tv_centros"])
    trechos = tuple(st.session_state.get("tv_trechos") or [])
    nome_local = st.session_state["tv_nome_local"]
    # Chave só pra dar keys únicas aos gráficos (gerencia=f"TV_{chave_local}")
    # — sanitizada porque vira parte de key= de widget (sem espaço/pontuação).
    chave_local = "_".join(c.strip().replace(" ", "").replace(".", "") for c in centros)[:60] or "TV"

    _injetar_css_tv()
    _botao_sair()

    df_raw = _carregar_dados_tv(gerencia, centros, trechos)
    if df_raw.empty:
        st.warning(f"⚠️ Nenhum dado encontrado para {nome_local} (Gerência {gerencia}).")
        # Diagnóstico: mostra os centro_trab que REALMENTE existem nos
        # dados da gerência — se o(s) Centro(s) escolhido(s) não estiver
        # na lista, é sinal de que ainda não tem upload pra esse Centro
        # (não é bug de código).
        disponiveis = _valores_centro_trab_disponiveis(gerencia)
        if disponiveis:
            st.caption(
                f"Centro de Trabalho disponíveis nos dados de {gerencia}: "
                + ", ".join(f"`{c}`" for c in disponiveis)
            )
        else:
            st.caption(
                f"Nenhum dado carregado pra Gerência {gerencia} ainda — "
                "pode ser upload pendente."
            )
        return

    # Config de Administração → Configurações → 🎯 Score DESSA Gerência (não
    # mais o ScoreConfig() padrão fixo) — o Modo TV passa a refletir os
    # mesmos pesos que a tela de Gerência correspondente usa (config é por
    # Gerência, ver core/score_engine.py).
    df = calcular_score_dataframe(df_raw, carregar_score_config(gerencia))

    idx = st.session_state.get("tv_slide_idx", 0) % len(_SLIDES)

    st.caption(
        f"📺 Modo TV · {nome_local} · slide {idx + 1}/{len(_SLIDES)} · "
        f"atualizado às {datetime.now():%H:%M} · próxima troca em "
        f"{INTERVALO_SLIDE_SEGUNDOS}s"
    )
    _SLIDES[idx](df, gerencia, nome_local, chave_local)

    if not _loop:
        return

    time.sleep(INTERVALO_SLIDE_SEGUNDOS)
    st.session_state["tv_slide_idx"] = (idx + 1) % len(_SLIDES)
    st.rerun()

# endregion
