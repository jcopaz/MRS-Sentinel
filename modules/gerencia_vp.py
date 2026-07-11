# =============================================================================
# modules/gerencia_vp.py — Tela da Gerência VP (Vale do Paraíba)
# Sprint 3 — MRS Sentinel
#
# Estrutura espelhada com gerencia_sp.py — mesma arquitetura de 5 abas.
# Diferenças: centros CFAN/CFTA/CFPI, pátios VP, cor de destaque própria.
#
#   Sessão 1: Imports & Config
#   Sessão 2: Funções auxiliares (carga, filtros)
#   Sessão 3: Função principal render_gerencia_vp()
#   Sessão 4: Abas
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
from components.filtros import render_filtros_cascata, aplicar_filtros_atributos
from components.visao_gerencial import render_visao_gerencial

# Motor de score
from core.score_engine import (
    render_score_sidebar,
    calcular_score_dataframe,
    render_painel_transparencia,
)

# Glossários e normalização
from core.glossarios import normalizar_coluna_ramal, nome_ramal, RAMAIS_MRS

# Queries do banco
from database.queries import get_notas_gerencia

# endregion


# region ====================== SESSÃO 2: Funções auxiliares ====================

def _carregar_dados_vp(disciplina_sel: str) -> pd.DataFrame:
    """
    Carrega notas da Gerência VP do Supabase.
    Aplica normalização de aliases (ASP→VSU) antes de retornar.

    Args:
        disciplina_sel: 'VP', 'EE' ou 'VP+EE'

    Returns:
        DataFrame unificado com coluna 'ramal' normalizada.
    """
    frames = []

    if disciplina_sel in ("VP", "VP+EE"):
        df_vp = get_notas_gerencia("VP", "VP")
        if not df_vp.empty:
            df_vp["disciplina_label"] = "VP"
            frames.append(df_vp)

    if disciplina_sel in ("EE", "VP+EE"):
        df_ee = get_notas_gerencia("VP", "EE")
        if not df_ee.empty:
            df_ee["disciplina_label"] = "EE"
            frames.append(df_ee)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # ⭐ Normaliza aliases antes de qualquer agrupamento
    df = normalizar_coluna_ramal(df, "ramal")

    # Converte tipos
    if "data_nota" in df.columns:
        df["data_nota"] = pd.to_datetime(df["data_nota"], errors="coerce")
    if "lead_time_dias" in df.columns:
        df["lead_time_dias"] = pd.to_numeric(df["lead_time_dias"], errors="coerce")

    return df


def _aplicar_filtros_vp(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """
    Aplica filtros em cascata retornados pelo componente render_filtros_cascata.
    Defensivo: ignora filtros cujas colunas não existem no DataFrame.
    """
    if df.empty:
        return df

    centros = filtros.get("centros", [])
    if centros and "centro_trab" in df.columns:
        df = df[df["centro_trab"].isin(centros)]

    ramais = filtros.get("ramais", [])
    if ramais and "ramal" in df.columns:
        df = df[df["ramal"].isin(ramais)]

    trechos = filtros.get("trechos", [])
    if trechos and "trecho" in df.columns:
        df = df[df["trecho"].isin(trechos)]

    patios = filtros.get("patios", [])
    if patios and "origem" in df.columns:
        df = df[df["origem"].isin(patios)]

    # Filtro de Abertura da Nota
    # Usa dt.date() para evitar bug de meia-noite (pd.Timestamp corta notas do dia)
    data_ab_ini = filtros.get("data_abertura_ini") or filtros.get("data_ini")
    data_ab_fim = filtros.get("data_abertura_fim") or filtros.get("data_fim")
    if "data_nota" in df.columns:
        col = pd.to_datetime(df["data_nota"], errors="coerce")
        if data_ab_ini:
            df = df[col.dt.date >= data_ab_ini]
        if data_ab_fim:
            df = df[col.dt.date <= data_ab_fim]

    # Filtro de Encerramento da Nota
    # Só entra em ação se o usuário estreitou o período (filtro_enc_ativo),
    # senão notas ainda em aberto (sem data_encerramento) seriam descartadas.
    data_enc_ini = filtros.get("data_enc_ini")
    data_enc_fim = filtros.get("data_enc_fim")
    if "data_encerramento" in df.columns and filtros.get("filtro_enc_ativo"):
        col_enc = pd.to_datetime(df["data_encerramento"], errors="coerce")
        if data_enc_ini:
            df = df[col_enc.dt.date >= data_enc_ini]
        if data_enc_fim:
            df = df[col_enc.dt.date <= data_enc_fim]

    # Filtros de atributo: Prioridade, Família, Tipo de inspeção, Status Base
    # (Sprint 4.5 — recuperados do app1.py)
    df = aplicar_filtros_atributos(df, filtros)

    return df.copy()

# endregion


# region ====================== SESSÃO 3: Função principal =====================

def render_gerencia_vp():
    """
    Ponto de entrada da tela da Gerência VP.
    Chamado pelo app.py quando o usuário navega para esta gerência.
    """

    # ── Cabeçalho (tom verde-azulado para diferenciar de SP) ─────────────────
    st.markdown(
        """
        <div style='
            background: linear-gradient(135deg, #0f4c35 0%, #1a6b4a 100%);
            padding: 20px 24px;
            border-radius: 12px;
            margin-bottom: 20px;
        '>
            <h2 style='color: #ffb000; margin: 0; font-size: 1.6rem;'>
                🏭 Gerência VP — Vale do Paraíba
            </h2>
            <p style='color: #a7f3d0; margin: 4px 0 0 0; font-size: 0.9rem;'>
                Centros: CFAN · CFTA · CFPI &nbsp;|&nbsp; Disciplinas: VP + EE integradas
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar — Toggle e Score ───────────────────────────────────────────────
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🔧 Gerência VP")

        disciplina_sel = st.radio(
            "📊 Disciplina",
            options=["VP+EE", "VP", "EE"],
            index=0,
            horizontal=False,
            help="VP = Via Permanente · EE = Eletroeletrônica · VP+EE = Ambas",
        )

        st.markdown("---")

        # Configuração de score específica para VP
        # O render_score_sidebar usa gerencia='VP' para aplicar pesos distintos
        score_cfg = render_score_sidebar(gerencia="VP")

        st.markdown("---")

    # ── Carrega dados ─────────────────────────────────────────────────────────
    with st.spinner("⏳ Carregando dados da Gerência VP..."):
        df_raw = _carregar_dados_vp(disciplina_sel)

    if df_raw.empty:
        st.warning(
            "⚠️ Nenhum dado encontrado para a Gerência VP. "
            "Solicite ao assistente que faça o upload das planilhas.",
            icon="📋",
        )
        return

    # ── Filtros em cascata ────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔍 Filtros")
        filtros = render_filtros_cascata(df_raw, gerencia="VP")

    df = _aplicar_filtros_vp(df_raw, filtros)

    if df.empty:
        st.info("ℹ️ Nenhuma nota encontrada com os filtros aplicados.")
        return

    # ── Score no DataFrame filtrado ───────────────────────────────────────────
    df = calcular_score_dataframe(df, score_cfg)

    # ── Contador na sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"<div style='background:rgba(255,176,0,0.1); padding:10px; "
            f"border-radius:8px; border-left:3px solid #ffb000; margin-top:8px;'>"
            f"<b style='color:#ffb000;'>📌 {len(df):,}</b> notas filtradas<br>"
            f"<small style='color:#6b7280;'>de {len(df_raw):,} totais</small>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── 6 Abas ────────────────────────────────────────────────────────────────
    aba_kpi, aba_ger, aba_unif, aba_heat, aba_rank, aba_temp = st.tabs([
        "📊 Visão Geral",
        "🎯 Visão Gerencial",
        "🗺️ Unifilar",
        "🌡️ Heatmap",
        "🏆 Ranking",
        "📈 Temporal",
    ])

    # endregion

    # region =================== SESSÃO 4.1: Aba — Visão Geral =================
    with aba_kpi:
        st.markdown("#### 📊 KPIs da Gerência VP")

        render_kpi_cards(df, gerencia="VP", disciplina=disciplina_sel)

        st.markdown("---")

        # Painel de transparência: mostra pesos do score configurados
        render_painel_transparencia(score_cfg)

    # endregion

    # region =================== SESSÃO 4.1B: Aba — Visão Gerencial ============
    with aba_ger:
        render_visao_gerencial(df, gerencia="VP")

    # endregion

    # region =================== SESSÃO 4.2: Aba — Unifilar ===================
    with aba_unif:
        st.markdown("#### 🗺️ Unifilar Dual — VP + EE por Ramal")

        col_info, col_leg = st.columns([3, 1])
        with col_info:
            st.caption(
                "Bolha = pátio · Tamanho = volume de notas · "
                "Cor = score médio · Pulso = hot-spot crítico"
            )
        with col_leg:
            st.markdown(
                "<small>🔴 Crítico &nbsp; 🟡 Alerta &nbsp; 🟢 Normal</small>",
                unsafe_allow_html=True,
            )

        render_unifilar_dual(df, gerencia="VP")

    # endregion

    # region =================== SESSÃO 4.3: Aba — Heatmap ====================
    with aba_heat:
        st.markdown("#### 🌡️ Heatmap — Pátio × Família de Defeito")
        st.caption("Intensidade = score médio das notas naquela combinação")
        render_heatmap(df, gerencia="VP")

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

        render_ranking(df, top_n=top_n, ordem=ordem, gerencia="VP")

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
            gerencia="VP",
        )

    # endregion
