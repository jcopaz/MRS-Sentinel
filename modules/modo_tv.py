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
#   3. Escolher a Gerência e a Coordenação (tela única, só na primeira
#      vez — fica salva pro resto da sessão) e clicar em "▶️ Iniciar".
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
# Coordenação selecionável só em SP e VP: são as únicas gerências com o
# mapeamento sigla-de-centro completo em core/glossarios.py
# (CENTROS_POR_GERENCIA) — as 4 gerências novas (FN/FS/RJ/LC) têm nome de
# coordenação cadastrado mas ainda não têm a sigla de centro_trab
# correspondente (mesma limitação já registrada no projeto). Generalizar
# pras outras 4 é só preencher CENTROS_POR_GERENCIA quando o dado
# existir.
#
# ⚠️ centro_trab NÃO é a sigla da coordenação (CIJN) — o formato real é
# "V.SP.<PÁTIO>" (ex.: "V.SP.IPA"), onde o ÚLTIMO segmento é o PÁTIO, não
# a coordenação. Bug real 2026-08-31: comparar contra "CIJN" nunca batia
# porque "CIJN" nunca aparece sozinho no dado — o filtro certo é contra a
# LISTA de pátios da coordenação (core/glossarios.py::PATIOS_POR_CENTRO,
# ex. CIJN → [IJN, ILA, IAB]). Achado nesse mesmo diagnóstico: os dados
# de SP carregados até agora só têm pátios de Piaçaguera (IPA) e
# Paranapiacaba (IPG) + um "PJU" não catalogado — nenhum pátio de
# Jundiaí (IJN/ILA/IAB) ainda. Não é mais bug de código: é upload
# pendente pra essa coordenação especificamente.
#
# Sessão 1: Imports & configuração
# Sessão 2: CSS do Modo TV (esconde sidebar + controles interativos)
# Sessão 3: Tela de seleção (Gerência + Coordenação) + botão de sair
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
from core.glossarios import (
    normalizar_coluna_ramal, CENTROS_POR_GERENCIA, COORDENACOES_POR_GERENCIA,
    PATIOS_POR_CENTRO,
)
from database.queries import get_notas_cached

INTERVALO_SLIDE_SEGUNDOS = 25

# Chaves de session_state usadas por este módulo — centralizado aqui pra
# _sair_do_modo_tv() saber exatamente o que limpar.
_CHAVES_SESSAO_TV = [
    "tv_gerencia", "tv_patios", "tv_centro_sigla", "tv_nome_local",
    "tv_slide_idx", "_css_modo_tv_injetado",
]

# {gerencia: {"Nome bonito da coordenação": [lista de pátios, ex. "IPA"]}}
# — encadeia COORDENACOES_POR_GERENCIA (nome) → CENTROS_POR_GERENCIA
# (sigla, ex. "CIJN") → PATIOS_POR_CENTRO (pátios reais que aparecem no
# último segmento de centro_trab). Só pras gerências com as 3 listas
# preenchidas em glossarios.py.
COORDENACOES_TV: dict[str, dict[str, list[str]]] = {
    g: {
        nome: PATIOS_POR_CENTRO.get(sigla, [])
        for nome, sigla in zip(COORDENACOES_POR_GERENCIA.get(g, []), CENTROS_POR_GERENCIA[g])
    }
    for g in CENTROS_POR_GERENCIA
}

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
    Tela de escolha de Gerência + Coordenação — aparece só na primeira
    vez (sidebar normal, sem CSS de esconder). Depois de "▶️ Iniciar",
    a escolha fica em st.session_state pro resto da sessão (não pergunta
    de novo a cada rerun do loop).

    Retorna True se a escolha já está pronta (pode seguir pro loop),
    False se ainda está mostrando a tela de seleção (o caller deve parar
    por aqui nesse rerun).
    """
    if st.session_state.get("tv_gerencia") and st.session_state.get("tv_patios"):
        return True

    st.markdown("## 📺 Modo TV — Configuração")
    st.caption(
        "Escolha a Gerência e a Coordenação que vão ficar em loop na TV. "
        "Só precisa fazer isso uma vez — fica salvo pro resto da sessão."
    )

    gerencias_disp = sorted(COORDENACOES_TV.keys())
    if not gerencias_disp:
        st.error("🚫 Nenhuma Gerência com Coordenação cadastrada pro Modo TV ainda.")
        return False

    gerencia_sel = st.selectbox("Gerência", gerencias_disp, key="tv_sel_gerencia")
    coords = COORDENACOES_TV.get(gerencia_sel, {})
    if not coords:
        st.warning(f"⚠️ Gerência {gerencia_sel} ainda não tem Coordenação cadastrada.")
        return False

    coord_nome_sel = st.selectbox("Coordenação", sorted(coords.keys()), key="tv_sel_coord")

    if st.button("▶️ Iniciar Modo TV", type="primary"):
        # Sigla da coordenação (ex. "CIJN") -- só pra formar keys únicas
        # dos gráficos (gerencia=f"TV_{chave_local}"), não usada no
        # filtro (que compara contra tv_patios, a lista de pátios reais).
        sigla_coord = next(
            sigla for nome, sigla in zip(
                COORDENACOES_POR_GERENCIA.get(gerencia_sel, []),
                CENTROS_POR_GERENCIA[gerencia_sel],
            ) if nome == coord_nome_sel
        )
        st.session_state["tv_gerencia"] = gerencia_sel
        st.session_state["tv_patios"] = coords[coord_nome_sel]
        st.session_state["tv_centro_sigla"] = sigla_coord
        st.session_state["tv_nome_local"] = coord_nome_sel
        if not _loop:
            return True
        st.rerun()

    return False

# endregion


# region ====================== SESSÃO 4: Carregamento de dados =================

@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados_tv(gerencia: str, patios: tuple[str, ...]) -> pd.DataFrame:
    """VP+EE da Gerência escolhida, filtrado nos pátios da Coordenação
    escolhida. Mesma lógica de
    modules/gerencia_dashboard.py::_carregar_dados, sem os widgets.

    `patios` é tuple (não list) porque st.cache_data precisa de argumentos
    hasheáveis pra formar a chave do cache.
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

    if "centro_trab" in df.columns and patios:
        # centro_trab chega bruto do parser, no formato hierárquico
        # completo "V.SP.<PÁTIO>" (ex.: "V.SP.IPA") — o ÚLTIMO segmento é
        # o PÁTIO, NÃO a sigla da coordenação (bug real 2026-08-31: uma
        # coordenação como "CIJN" nunca aparece sozinha no dado — precisa
        # comparar contra a LISTA de pátios dela, PATIOS_POR_CENTRO).
        # .split(".") num valor já sem prefixo devolve o próprio valor,
        # então cobre os dois formatos.
        sigla = (
            df["centro_trab"].astype(str).str.strip().str.upper()
            .str.split(".").str[-1]
        )
        patios_upper = {p.upper() for p in patios}
        df = df[sigla.isin(patios_upper)].copy()

    return df


def _valores_centro_trab_disponiveis(gerencia: str) -> list[str]:
    """
    Diagnóstico pro aviso de "sem dado" — lista os centro_trab realmente
    presentes nos dados da gerência escolhida, pra identificar rápido se
    a coordenação escolhida simplesmente não tem upload ainda.
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
    quando ainda não escolheu Gerência/Coordenação nesta sessão): tela de
    seleção (Sessão 3). Depois disso, gira sozinho entre os slides
    definidos em _SLIDES, sem recarregar a página (ver docstring do
    módulo — preserva o login). Admin sempre acessa; outros perfis só
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
    patios = tuple(st.session_state["tv_patios"])
    nome_local = st.session_state["tv_nome_local"]
    chave_local = st.session_state.get("tv_centro_sigla", nome_local)

    _injetar_css_tv()
    _botao_sair()

    df_raw = _carregar_dados_tv(gerencia, patios)
    if df_raw.empty:
        st.warning(
            f"⚠️ Nenhum dado encontrado para {nome_local} "
            f"(pátios {', '.join(patios) or '—'}, Gerência {gerencia})."
        )
        # Diagnóstico: mostra os centro_trab que REALMENTE existem nos
        # dados da gerência — se nenhum terminar em algum dos pátios
        # esperados, é sinal de que essa coordenação ainda não tem
        # upload (não é bug de código).
        disponiveis = _valores_centro_trab_disponiveis(gerencia)
        if disponiveis:
            st.caption(
                f"Centro de Trabalho disponíveis nos dados de {gerencia}: "
                + ", ".join(f"`{c}`" for c in disponiveis)
            )
        else:
            st.caption(
                f"Nenhum dado carregado pra Gerência {gerencia} ainda "
                "(nem de outros pátios) — pode ser upload pendente."
            )
        return

    # Mesma config única de Administração → Configurações → 🎯 Score (não
    # mais o ScoreConfig() padrão fixo) — o Modo TV passa a refletir os
    # mesmos pesos que as telas de Gerência usam (core/score_engine.py).
    df = calcular_score_dataframe(df_raw, carregar_score_config())

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
