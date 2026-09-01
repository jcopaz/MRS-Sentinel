# =============================================================================
# modules/modo_tv.py — "Modo TV": painel em loop pra TV/monitor
# Sprint TV (2026-08-30) — MRS Sentinel
#
# Pedido do Julio (coordenador de Jundiaí): uma TV parada na coordenação,
# conectada por HDMI a um PC/notebook, mostrando em loop as notas e o
# Unifilar do trecho de Jundiaí — sem ninguém precisando mexer em nada.
#
# Como usar na TV (uma vez só, no PC/notebook conectado):
#   1. Logar normalmente no navegador (perfil admin, ou um usuário com
#      "Acesso ao Modo TV" marcado no Painel Admin).
#   2. Clicar em "📺 Modo TV" na barra lateral.
#   3. Deixar o navegador em tela cheia (F11) e a sessão aberta —
#      a tela gira sozinha, sem precisar recarregar a página.
#
# Por que não recarrega a página pra trocar de slide: o login deste app
# vive só em st.session_state (sem cookie/token persistente — ver
# auth/session.py) — um location.reload()/navegação JS derrubaria a
# sessão a cada troca. Em vez disso, o loop é INTERNO: time.sleep() +
# st.rerun() dentro da MESMA sessão, sem nunca recarregar o navegador.
#
# Escopo desta v1 (limitação consciente, documentada): 3 "slides" —
# KPIs, Unifilar (por KM + de Ativo + rankings, tudo junto — render_unifilar
# hoje é uma função só, sem como pedir "só uma parte" sem duplicar lógica
# interna arriscada) e Ranking de hot-spots por pátio. Os controles
# interativos do Unifilar (sliders, radios, tabela, downloads) ficam
# escondidos via CSS — a lógica deles continua rodando por baixo com os
# valores padrão, só não aparece na tela.
#
# Sessão 1: Imports & configuração
# Sessão 2: CSS do Modo TV (esconde sidebar + controles interativos)
# Sessão 3: Carregamento de dados (fixo em SP / Jundiaí)
# Sessão 4: Slides
# Sessão 5: render_modo_tv() — orquestração + loop
# =============================================================================

# region ====================== SESSÃO 1: Imports & Configuração ===============
import time
from datetime import datetime

import streamlit as st
import pandas as pd

from auth.permissions import require_modo_tv
from components.kpi_card import render_kpi_cards
from components.unifilar import render_unifilar_dual
from components.heatmap import render_ranking
from core.score_engine import calcular_score_dataframe, ScoreConfig
from core.glossarios import normalizar_coluna_ramal
from database.queries import get_notas_cached

# Centro de Trabalho de Jundiaí (coordenação CIJN, Gerência SP) — ver
# core/glossarios.py: CENTROS_POR_GERENCIA["SP"] / COORDENACOES_POR_GERENCIA.
# Fixo por enquanto (v1 pensada pra essa TV específica); generalizar pra
# outras coordenações/gerências é um parâmetro fácil de expor depois.
GERENCIA_TV = "SP"
CENTRO_TRAB_TV = "CIJN"
NOME_LOCAL_TV = "Jundiaí"

INTERVALO_SLIDE_SEGUNDOS = 25

# endregion


# region ====================== SESSÃO 2: CSS do Modo TV ========================

def _injetar_css_tv():
    """
    Esconde sidebar + todo controle interativo (o Modo TV é só pra ASSISTIR,
    ninguém deve mexer em nada) e aumenta fonte/contraste pra leitura de
    longe. Idempotente via flag de sessão (mesmo padrão do resto do app).
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
       botões, downloads, tabela completa, formulários) — a lógica por trás
       continua rodando com os valores padrão, só não aparece na tela. */
    [data-testid="stSlider"], [data-testid="stRadio"],
    [data-testid="stMultiSelect"], [data-testid="stSelectbox"],
    [data-testid="stButton"], [data-testid="stDownloadButton"],
    [data-testid="stDataFrame"], [data-testid="stForm"],
    [data-testid="stFormSubmitButton"] {
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


# region ====================== SESSÃO 3: Carregamento de dados =================

@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados_tv() -> pd.DataFrame:
    """VP+EE da Gerência fixa, filtrado no Centro de Trabalho fixo (ver
    constantes no topo do arquivo). Mesma lógica de
    modules/gerencia_dashboard.py::_carregar_dados, sem os widgets."""
    frames = []
    for disc in ("VP", "EE"):
        df_d = get_notas_cached(GERENCIA_TV, disc)
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

    if "centro_trab" in df.columns:
        # centro_trab chega bruto do parser, no formato hierárquico
        # completo (ex.: "V.SP.CIJN"), não a sigla pura — mesma lógica
        # defensiva de core/parser.py::detectar_gerencia_nota (pega o
        # ÚLTIMO segmento separado por "."), que também cobre o caso de
        # já vir só a sigla sem prefixo (split de string sem "." devolve
        # a própria string). Bug real corrigido 2026-08-31: o filtro
        # antigo comparava direto com "CIJN" e nunca batia.
        sigla = (
            df["centro_trab"].astype(str).str.strip().str.upper()
            .str.split(".").str[-1]
        )
        df = df[sigla == CENTRO_TRAB_TV].copy()

    return df


def _valores_centro_trab_disponiveis() -> list[str]:
    """
    Diagnóstico pro aviso de "sem dado" — lista os centro_trab realmente
    presentes nos dados de GERENCIA_TV, pra identificar rápido se o
    código fixo (CENTRO_TRAB_TV) mudou ou está errado, sem precisar
    investigar direto no banco.
    """
    frames = []
    for disc in ("VP", "EE"):
        df_d = get_notas_cached(GERENCIA_TV, disc)
        if not df_d.empty and "centro_trab" in df_d.columns:
            frames.append(df_d[["centro_trab"]])
    if not frames:
        return []
    todos = pd.concat(frames, ignore_index=True)
    return sorted(todos["centro_trab"].dropna().astype(str).str.strip().unique().tolist())

# endregion


# region ====================== SESSÃO 4: Slides =================================

def _slide_kpis(df: pd.DataFrame):
    st.markdown(f"### 📊 Resumo — {NOME_LOCAL_TV}")
    render_kpi_cards(df, gerencia=GERENCIA_TV, disciplina="VP+EE")


def _slide_unifilar(df: pd.DataFrame):
    st.markdown(f"### 🗺️ Unifilar — {NOME_LOCAL_TV}")
    render_unifilar_dual(df, gerencia=f"TV_{CENTRO_TRAB_TV}")


def _slide_ranking(df: pd.DataFrame):
    st.markdown(f"### 🏆 Hot-spots por Pátio — {NOME_LOCAL_TV}")
    render_ranking(df, top_n=10, ordem="Score Total", gerencia=f"TV_{CENTRO_TRAB_TV}")


_SLIDES = [_slide_kpis, _slide_unifilar, _slide_ranking]

# endregion


# region ====================== SESSÃO 5: render_modo_tv() ======================

def render_modo_tv(_loop: bool = True):
    """
    Ponto de entrada do Modo TV (rota 'modo_tv'). Gira sozinho entre os
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
    _injetar_css_tv()

    df_raw = _carregar_dados_tv()
    if df_raw.empty:
        st.warning(
            f"⚠️ Nenhum dado encontrado para {NOME_LOCAL_TV} "
            f"(Centro de Trabalho '{CENTRO_TRAB_TV}', Gerência {GERENCIA_TV})."
        )
        # Diagnóstico: mostra os centro_trab que REALMENTE existem nos
        # dados de SP — se '{CENTRO_TRAB_TV}' não estiver nessa lista, é
        # sinal de que o código fixo no topo deste arquivo está errado
        # (ver CENTRO_TRAB_TV) e precisa ser ajustado pro valor real.
        disponiveis = _valores_centro_trab_disponiveis()
        if disponiveis:
            st.caption(
                "Centro de Trabalho disponíveis nos dados de "
                f"{GERENCIA_TV}: " + ", ".join(f"`{c}`" for c in disponiveis)
            )
        else:
            st.caption(
                f"Nenhum dado carregado pra Gerência {GERENCIA_TV} ainda "
                "(nem de outros pátios) — pode ser upload pendente."
            )
        return

    df = calcular_score_dataframe(df_raw, ScoreConfig())

    idx = st.session_state.get("tv_slide_idx", 0) % len(_SLIDES)

    st.caption(
        f"📺 Modo TV · {NOME_LOCAL_TV} · slide {idx + 1}/{len(_SLIDES)} · "
        f"atualizado às {datetime.now():%H:%M} · próxima troca em "
        f"{INTERVALO_SLIDE_SEGUNDOS}s"
    )
    _SLIDES[idx](df)

    if not _loop:
        return

    time.sleep(INTERVALO_SLIDE_SEGUNDOS)
    st.session_state["tv_slide_idx"] = (idx + 1) % len(_SLIDES)
    st.rerun()

# endregion
