# =============================================================================
# modules/gerencia_sp.py — Tela da Gerência SP (São Paulo)
# Sprint 3 — MRS Sentinel
#
# Estrutura:
#   Sessão 1: Imports & Config
#   Sessão 2: Carregamento e preparação de dados
#   Sessão 3: Sidebar — filtros e toggle VP/EE
#   Sessão 4: Abas principais (5 abas)
#     4.1 — Visão Geral (KPIs + Score)
#     4.2 — Unifilar Dual
#     4.3 — Heatmap Pátio × Família
#     4.4 — Ranking Hot-spots
#     4.5 — Série Temporal
# =============================================================================

# region ====================== SESSÃO 1: Imports & Config ======================
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date

# Componentes visuais reutilizáveis
from components.kpi_card import render_kpi_cards
from components.unifilar import render_unifilar_dual
from components.heatmap import render_heatmap, render_ranking, render_serie_temporal
from components.filtros import render_filtros_cascata

# Motor de score e indicadores
from core.score_engine import render_score_sidebar, calcular_score_dataframe

# Glossários e normalização
from core.glossarios import (
    normalizar_coluna_ramal,
    nome_ramal,
    RAMAIS_MRS,
)

# Queries do banco
from database.queries import get_notas_gerencia, get_kpis_gerencia, get_ranking_hotspots

# endregion


# region ====================== SESSÃO 2: Funções auxiliares ====================

def _carregar_dados(disciplina_sel: str) -> pd.DataFrame:
    """
    Carrega dados do Supabase para a gerência SP.
    Aplica normalização de aliases (ASP→VSU) antes de qualquer uso.

    Args:
        disciplina_sel: 'VP', 'EE' ou 'VP+EE'

    Returns:
        DataFrame unificado, já com coluna 'ramal' normalizada.
    """
    frames = []

    if disciplina_sel in ("VP", "VP+EE"):
        df_vp = get_notas_gerencia("SP", "VP")
        if not df_vp.empty:
            df_vp["disciplina_label"] = "VP"
            frames.append(df_vp)

    if disciplina_sel in ("EE", "VP+EE"):
        df_ee = get_notas_gerencia("SP", "EE")
        if not df_ee.empty:
            df_ee["disciplina_label"] = "EE"
            frames.append(df_ee)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # ⭐ ESSENCIAL: normaliza aliases antes de qualquer agrupamento
    df = normalizar_coluna_ramal(df, "ramal")

    # Garante coluna de data como datetime
    if "data_nota" in df.columns:
        df["data_nota"] = pd.to_datetime(df["data_nota"], errors="coerce")

    # Garante lead_time numérico
    if "lead_time_dias" in df.columns:
        df["lead_time_dias"] = pd.to_numeric(df["lead_time_dias"], errors="coerce")

    return df


def _aplicar_filtros(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """
    Aplica os filtros retornados pelo componente de filtros em cascata.
    Defensivo contra colunas ausentes e listas vazias.
    """
    if df.empty:
        return df

    # Filtro de Centro de Trabalho
    centros = filtros.get("centros", [])
    if centros and "centro_trab" in df.columns:
        df = df[df["centro_trab"].isin(centros)]

    # Filtro de Ramal (siglas canônicas)
    ramais = filtros.get("ramais", [])
    if ramais and "ramal" in df.columns:
        df = df[df["ramal"].isin(ramais)]

    # Filtro de Trecho
    trechos = filtros.get("trechos", [])
    if trechos and "trecho" in df.columns:
        df = df[df["trecho"].isin(trechos)]

    # Filtro de Pátio (origem)
    patios = filtros.get("patios", [])
    if patios and "origem" in df.columns:
        df = df[df["origem"].isin(patios)]

    # Filtro de período
    data_ini = filtros.get("data_ini")
    data_fim = filtros.get("data_fim")
    if data_ini and "data_nota" in df.columns:
        df = df[df["data_nota"] >= pd.Timestamp(data_ini)]
    if data_fim and "data_nota" in df.columns:
        df = df[df["data_nota"] <= pd.Timestamp(data_fim)]

    return df.copy()

# endregion


# region ====================== SESSÃO 3: Função principal =====================

def render_gerencia_sp():
    """
    Ponto de entrada da tela da Gerência SP.
    Chamado diretamente pelo app.py quando o usuário navega para esta gerência.
    """

    # ── Cabeçalho ──────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='
            background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%);
            padding: 20px 24px;
            border-radius: 12px;
            margin-bottom: 20px;
        '>
            <h2 style='color: #ffb000; margin: 0; font-size: 1.6rem;'>
                🏭 Gerência SP — São Paulo
            </h2>
            <p style='color: #cbd5e1; margin: 4px 0 0 0; font-size: 0.9rem;'>
                Centros: CIPA · CIPG · CIJN &nbsp;|&nbsp; Disciplinas: VP + EE integradas
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar — Toggle VP/EE e Score ────────────────────────────────────────
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🔧 Gerência SP")

        # Toggle de disciplina
        disciplina_sel = st.radio(
            "📊 Disciplina",
            options=["VP+EE", "VP", "EE"],
            index=0,
            horizontal=False,
            help="VP = Via Permanente · EE = Eletroeletrônica · VP+EE = Ambas",
        )

        st.markdown("---")

        # Configuração de score (retorna ScoreConfig)
        score_cfg = render_score_sidebar(gerencia="SP")

        st.markdown("---")

    # ── Carrega dados ─────────────────────────────────────────────────────────
    with st.spinner("⏳ Carregando dados da Gerência SP..."):
        df_raw = _carregar_dados(disciplina_sel)

    if df_raw.empty:
        st.warning(
            "⚠️ Nenhum dado encontrado para a Gerência SP. "
            "Solicite ao assistente que faça o upload das planilhas.",
            icon="📋",
        )
        return

    # ── Filtros em cascata (sidebar) ──────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔍 Filtros")
        filtros = render_filtros_cascata(df_raw, gerencia="SP")

    df = _aplicar_filtros(df_raw, filtros)

    if df.empty:
        st.info("ℹ️ Nenhuma nota encontrada com os filtros aplicados.")
        return

    # ── Calcula score no DataFrame filtrado ───────────────────────────────────
    # Feito aqui para que todas as abas usem o mesmo df com score atualizado
    df = calcular_score_dataframe(df, score_cfg)

    # ── Contador rápido na sidebar ────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"<div style='background:rgba(255,176,0,0.1); padding:10px; "
            f"border-radius:8px; border-left:3px solid #ffb000; margin-top:8px;'>"
            f"<b style='color:#ffb000;'>📌 {len(df):,}</b> notas filtradas<br>"
            f"<small style='color:#6b7280;'>de {len(df_raw):,} totais</small>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── 5 Abas principais ─────────────────────────────────────────────────────
    aba_kpi, aba_unif, aba_heat, aba_rank, aba_temp = st.tabs([
        "📊 Visão Geral",
        "🗺️ Unifilar",
        "🌡️ Heatmap",
        "🏆 Ranking",
        "📈 Temporal",
    ])

    # endregion

    # region =================== SESSÃO 4.1: Aba — Visão Geral (KPIs) ==========
    with aba_kpi:
        st.markdown("#### 📊 KPIs da Gerência SP")

        # KPIs premium com sparkline
        render_kpi_cards(df, gerencia="SP", disciplina=disciplina_sel)

        # Separador
        st.markdown("---")

        # Painel de transparência do score (explica pesos ativos)
        from core.score_engine import render_painel_transparencia
        render_painel_transparencia(score_cfg)

    # endregion

    # region =================== SESSÃO 4.2: Aba — Unifilar Dual ===============
    with aba_unif:
        st.markdown("#### 🗺️ Unifilar Dual — VP + EE por Ramal")

        col_info, col_legenda = st.columns([3, 1])
        with col_info:
            st.caption(
                "Cada bolha representa um pátio. "
                "Tamanho = volume de notas · Cor = score médio · "
                "Pulso = hot-spot crítico"
            )
        with col_legenda:
            st.markdown(
                "<small>🔴 Crítico &nbsp; 🟡 Alerta &nbsp; 🟢 Normal</small>",
                unsafe_allow_html=True,
            )

        render_unifilar_dual(df, gerencia="SP")

    # endregion

    # region =================== SESSÃO 4.3: Aba — Heatmap ====================
    with aba_heat:
        st.markdown("#### 🌡️ Heatmap — Pátio × Família de Defeito")
        st.caption("Intensidade = score médio das notas naquela combinação Pátio × Família")
        render_heatmap(df, gerencia="SP")

    # endregion

    # region =================== SESSÃO 4.4: Aba — Ranking ====================
    with aba_rank:
        st.markdown("#### 🏆 Ranking de Hot-spots")

        col_n, col_ord = st.columns([1, 2])
        with col_n:
            top_n = st.selectbox("Top N", [5, 10, 15, 20], index=1)
        with col_ord:
            ordem = st.selectbox(
                "Ordenar por",
                ["Score Total", "Qtd. Notas", "Lead Time Médio (dias)"],
                index=0,
            )

        render_ranking(df, top_n=top_n, ordem=ordem, gerencia="SP")

    # endregion

    # region =================== SESSÃO 4.5: Aba — Série Temporal =============
    with aba_temp:
        st.markdown("#### 📈 Evolução Temporal")

        col_gran, col_met = st.columns(2)
        with col_gran:
            granularidade = st.selectbox(
                "Granularidade",
                ["Mensal", "Semanal", "Trimestral"],
                index=0,
            )
        with col_met:
            metrica = st.selectbox(
                "Métrica",
                ["Volume de Notas", "Score Médio", "Lead Time Médio"],
                index=0,
            )

        render_serie_temporal(
            df,
            granularidade=granularidade,
            metrica=metrica,
            gerencia="SP",
        )

    # endregion
