# =============================================================================
# modules/gerencia_geral.py — Visão Geral Multi-Gerencial (SP + VP)
# Sprint 4 — MRS Sentinel
#
# Cruza dados das duas gerências para visão consolidada.
# Usa indicadores IMT, DI, Aderência e Lead Time do core/indicadores.py.
#
# Estrutura:
#   Sessão 1: Imports & Config
#   Sessão 2: Carregamento e preparação de dados unificados
#   Sessão 3: Componentes visuais locais (semáforo, comparativo)
#   Sessão 4: Função principal render_gerencia_geral()
#   Sessão 5: Abas
#     5.1 — Consolidado (KPIs + Indicadores IMT/DI)
#     5.2 — Comparativo SP × VP
#     5.3 — Unifilar Total (SP + VP)
#     5.4 — Temporal Global
#     5.5 — Top Hot-spots (ranking unificado)
# =============================================================================

# region ====================== SESSÃO 1: Imports & Config ======================
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# Componentes visuais
from components.kpi_card import render_kpi_cards
from components.unifilar import render_unifilar_dual
from components.heatmap import render_ranking, render_serie_temporal
from components.filtros import render_filtros_atributos, aplicar_filtros_atributos
from components.visao_gerencial import render_visao_gerencial

# Indicadores IMT/DI/Aderência/Lead Time
from core.indicadores import (
    calcular_imt,
    calcular_di,
    calcular_aderencia,
    calcular_lead_time_medio,
    render_indicadores_geral,
    render_semaforo,
)

# Motor de score
from core.score_engine import calcular_score_dataframe, render_score_sidebar

# Normalização de ramais
from core.glossarios import normalizar_coluna_ramal, nome_ramal, RAMAIS_MRS

# Queries
from database.queries import get_notas_gerencia

# Paleta MRS
COR_SP   = "#1e3a5f"   # azul-marinho SP
COR_VP   = "#0f4c35"   # verde-escuro VP
COR_GOLD = "#ffb000"   # dourado MRS
COR_CRIT = "#dc2626"   # vermelho crítico
COR_WARN = "#f59e0b"   # amarelo atenção
COR_OK   = "#16a34a"   # verde normal

# endregion


# region ====================== SESSÃO 2: Carregamento de dados ================

@st.cache_data(ttl=300, show_spinner=False)
def _carregar_tudo() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carrega VP+EE das duas gerências em paralelo (cache 5 min).
    Retorna (df_sp, df_vp) já normalizados.

    Usa cache para evitar recargas desnecessárias ao navegar entre abas.
    """
    def _load(gerencia: str) -> pd.DataFrame:
        frames = []
        for disc in ("VP", "EE"):
            df_d = get_notas_gerencia(gerencia, disc)
            if not df_d.empty:
                df_d["disciplina_label"] = disc
                df_d["gerencia_label"] = gerencia
                frames.append(df_d)
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        df = normalizar_coluna_ramal(df, "ramal")
        if "data_nota" in df.columns:
            df["data_nota"] = pd.to_datetime(df["data_nota"], errors="coerce")
        if "lead_time_dias" in df.columns:
            df["lead_time_dias"] = pd.to_numeric(df["lead_time_dias"], errors="coerce")
        return df

    return _load("SP"), _load("VP")


def _combinar(df_sp: pd.DataFrame, df_vp: pd.DataFrame) -> pd.DataFrame:
    """Une as duas gerências em um único DataFrame, se ambas tiverem dados."""
    frames = [df for df in (df_sp, df_vp) if not df.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)

# endregion


# region ====================== SESSÃO 3: Componentes locais ===================

def _card_metrica(label: str, valor: str, delta: str = "", cor: str = COR_SP):
    """
    Renderiza um card de métrica estilizado com borda colorida.
    Usado no comparativo SP × VP para manter consistência visual.
    """
    st.markdown(
        f"""
        <div style='
            background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e5e7eb;
            border-left: 4px solid {cor};
            padding: 14px 16px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            text-align: center;
        '>
            <div style='font-size: 0.75rem; color: #6b7280; font-weight: 600;
                        text-transform: uppercase; letter-spacing: 0.05em;'>
                {label}
            </div>
            <div style='font-size: 1.8rem; font-weight: 700; color: {cor}; margin: 4px 0;'>
                {valor}
            </div>
            <div style='font-size: 0.75rem; color: #9ca3af;'>{delta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _grafico_barras_comparativo(
    df_sp: pd.DataFrame,
    df_vp: pd.DataFrame,
    coluna: str,
    titulo: str,
    unidade: str = "",
) -> go.Figure:
    """
    Gera gráfico de barras horizontais comparando SP × VP por ramal.
    Normaliza siglas para nomes completos no eixo Y.

    Args:
        df_sp, df_vp: DataFrames já filtrados e com score calculado
        coluna: coluna a agregar (ex: 'score', 'lead_time_dias')
        titulo: título do gráfico
        unidade: sufixo da unidade (ex: ' dias', ' pts')
    """
    def _agg(df: pd.DataFrame, label: str) -> pd.DataFrame:
        if df.empty or coluna not in df.columns:
            return pd.DataFrame()
        grp = (
            df.groupby("ramal")[coluna]
            .mean()
            .reset_index()
            .rename(columns={coluna: "valor"})
        )
        grp["gerencia"] = label
        grp["ramal_nome"] = grp["ramal"].apply(lambda s: nome_ramal(s, "completo_sigla"))
        return grp

    df_plot = pd.concat([_agg(df_sp, "SP"), _agg(df_vp, "VP")], ignore_index=True)

    if df_plot.empty:
        return go.Figure()

    fig = px.bar(
        df_plot,
        x="valor",
        y="ramal_nome",
        color="gerencia",
        orientation="h",
        barmode="group",
        color_discrete_map={"SP": COR_SP, "VP": COR_VP},
        labels={"valor": f"{titulo}{unidade}", "ramal_nome": "Ramal", "gerencia": "Gerência"},
        title=titulo,
    )
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_color="#1f2937",
        title_font_size=14,
        height=max(350, len(df_plot["ramal_nome"].unique()) * 28),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig

# endregion


# region ====================== SESSÃO 4: Função principal =====================

def render_gerencia_geral():
    """
    Ponto de entrada da Visão Geral multi-gerencial.
    Chamado pelo app.py quando o usuário navega para 'Geral'.
    """

    # ── Cabeçalho ──────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='
            background: linear-gradient(135deg, #312e81 0%, #4c1d95 100%);
            padding: 20px 24px;
            border-radius: 12px;
            margin-bottom: 20px;
        '>
            <h2 style='color: #ffb000; margin: 0; font-size: 1.6rem;'>
                🌐 Visão Geral — SP + VP Consolidado
            </h2>
            <p style='color: #c4b5fd; margin: 4px 0 0 0; font-size: 0.9rem;'>
                Cruza dados de ambas as gerências · Indicadores IMT e DI integrados
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🌐 Visão Geral")

        # Filtro de disciplina para o consolidado
        disciplina_geral = st.radio(
            "📊 Disciplina",
            ["VP+EE", "VP", "EE"],
            index=0,
            horizontal=False,
        )

        # Filtro de gerência (permite ver só uma)
        gerencias_vis = st.multiselect(
            "🏭 Gerências visíveis",
            options=["SP", "VP"],
            default=["SP", "VP"],
            help="Desmarque uma gerência para excluí-la da visualização",
        )
        if not gerencias_vis:
            gerencias_vis = ["SP", "VP"]  # segurança: nunca vazio

        st.markdown("---")

        # Score unificado (mesmos pesos para as duas gerências na visão geral)
        score_cfg = render_score_sidebar(gerencia="GERAL")

        st.markdown("---")

    # ── Carrega dados (cached) ────────────────────────────────────────────────
    with st.spinner("⏳ Carregando dados consolidados..."):
        df_sp_raw, df_vp_raw = _carregar_tudo()

    # Filtra disciplinas
    def _filtrar_disc(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "disciplina_label" not in df.columns:
            return df
        if disciplina_geral == "VP":
            return df[df["disciplina_label"] == "VP"].copy()
        elif disciplina_geral == "EE":
            return df[df["disciplina_label"] == "EE"].copy()
        return df.copy()

    df_sp = _filtrar_disc(df_sp_raw) if "SP" in gerencias_vis else pd.DataFrame()
    df_vp = _filtrar_disc(df_vp_raw) if "VP" in gerencias_vis else pd.DataFrame()

    df_total = _combinar(df_sp, df_vp)

    # ── Filtros de atributo: Prioridade, Família, Tipo de inspeção, Status Base
    # (Sprint 4.5 — sem cascata geográfica aqui, a Geral não tem essa hierarquia)
    with st.sidebar:
        st.markdown("### 🎛️ Filtros de Atributo")
        filtros_attrs = render_filtros_atributos(df_total, gerencia="GERAL")

    df_sp = aplicar_filtros_atributos(df_sp, filtros_attrs)
    df_vp = aplicar_filtros_atributos(df_vp, filtros_attrs)
    df_total = aplicar_filtros_atributos(df_total, filtros_attrs)

    # Calcula score
    if not df_sp.empty:
        df_sp = calcular_score_dataframe(df_sp, score_cfg)
    if not df_vp.empty:
        df_vp = calcular_score_dataframe(df_vp, score_cfg)
    if not df_total.empty:
        df_total = calcular_score_dataframe(df_total, score_cfg)

    # Avisa se não há nenhum dado
    if df_total.empty:
        st.warning(
            "⚠️ Nenhum dado encontrado para as gerências selecionadas. "
            "Solicite upload das planilhas."
        )
        return

    # Contador resumido
    with st.sidebar:
        total = len(df_total)
        n_sp = len(df_sp) if not df_sp.empty else 0
        n_vp = len(df_vp) if not df_vp.empty else 0
        st.markdown(
            f"<div style='background:rgba(255,176,0,0.1); padding:10px; "
            f"border-radius:8px; border-left:3px solid #ffb000;'>"
            f"<b style='color:#ffb000;'>📌 {total:,}</b> notas totais<br>"
            f"<small style='color:#6b7280;'>SP: {n_sp:,} · VP: {n_vp:,}</small>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── 6 Abas ────────────────────────────────────────────────────────────────
    aba_cons, aba_ger, aba_comp, aba_unif, aba_temp, aba_rank = st.tabs([
        "📊 Consolidado",
        "🎯 Visão Gerencial",
        "⚖️ SP × VP",
        "🗺️ Unifilar Total",
        "📈 Temporal Global",
        "🏆 Top Hot-spots",
    ])

    # endregion

    # region =================== SESSÃO 5.1: Aba — Consolidado =================
    with aba_cons:
        st.markdown("#### 📊 Painel Consolidado SP + VP")

        # Indicadores IMT / DI / Aderência / Lead Time (core/indicadores.py)
        render_indicadores_geral(df_total)

        st.markdown("---")
        st.markdown("#### 🚦 Semáforo de Saúde da Malha")
        render_semaforo(df_sp=df_sp, df_vp=df_vp)

        st.markdown("---")
        st.markdown("#### 📊 KPIs Unificados")
        render_kpi_cards(df_total, gerencia="GERAL", disciplina=disciplina_geral)

    # endregion

    # region =================== SESSÃO 5.1B: Aba — Visão Gerencial ============
    with aba_ger:
        render_visao_gerencial(df_total, gerencia="GERAL")

    # endregion

    # region =================== SESSÃO 5.2: Aba — Comparativo SP × VP =========
    with aba_comp:
        st.markdown("#### ⚖️ Comparativo Gerência SP × VP")

        # Linha de métricas rápidas SP vs VP
        col_sp, col_sep, col_vp = st.columns([5, 1, 5])

        with col_sp:
            st.markdown(f"<h5 style='color:{COR_SP}; text-align:center;'>🏭 SP — São Paulo</h5>", unsafe_allow_html=True)
            if not df_sp.empty:
                _card_metrica("Total de Notas", f"{len(df_sp):,}", cor=COR_SP)
                st.markdown("<br>", unsafe_allow_html=True)

                score_med_sp = df_sp["score"].mean() if "score" in df_sp.columns else 0
                _card_metrica("Score Médio", f"{score_med_sp:.1f}", cor=COR_SP)
                st.markdown("<br>", unsafe_allow_html=True)

                lt_sp = df_sp["lead_time_dias"].mean() if "lead_time_dias" in df_sp.columns else 0
                _card_metrica("Lead Time Médio", f"{lt_sp:.0f} dias", cor=COR_SP)
            else:
                st.info("Sem dados para SP")

        with col_sep:
            st.markdown(
                "<div style='width:2px; background:#e5e7eb; height:200px; margin:20px auto;'></div>",
                unsafe_allow_html=True,
            )

        with col_vp:
            st.markdown(f"<h5 style='color:{COR_VP}; text-align:center;'>🏭 VP — Vale do Paraíba</h5>", unsafe_allow_html=True)
            if not df_vp.empty:
                _card_metrica("Total de Notas", f"{len(df_vp):,}", cor=COR_VP)
                st.markdown("<br>", unsafe_allow_html=True)

                score_med_vp = df_vp["score"].mean() if "score" in df_vp.columns else 0
                _card_metrica("Score Médio", f"{score_med_vp:.1f}", cor=COR_VP)
                st.markdown("<br>", unsafe_allow_html=True)

                lt_vp = df_vp["lead_time_dias"].mean() if "lead_time_dias" in df_vp.columns else 0
                _card_metrica("Lead Time Médio", f"{lt_vp:.0f} dias", cor=COR_VP)
            else:
                st.info("Sem dados para VP")

        st.markdown("---")
        st.markdown("#### 📊 Score Médio por Ramal — SP × VP")

        # Gráfico de barras comparativo por ramal
        fig_score = _grafico_barras_comparativo(
            df_sp, df_vp, coluna="score",
            titulo="Score Médio por Ramal", unidade=" pts"
        )
        if fig_score.data:
            st.plotly_chart(fig_score, use_container_width=True)
        else:
            st.caption("Dados insuficientes para o gráfico.")

        st.markdown("#### ⏱️ Lead Time Médio por Ramal — SP × VP")
        fig_lt = _grafico_barras_comparativo(
            df_sp, df_vp, coluna="lead_time_dias",
            titulo="Lead Time Médio por Ramal", unidade=" dias"
        )
        if fig_lt.data:
            st.plotly_chart(fig_lt, use_container_width=True)
        else:
            st.caption("Dados insuficientes para o gráfico.")

    # endregion

    # region =================== SESSÃO 5.3: Aba — Unifilar Total ==============
    with aba_unif:
        st.markdown("#### 🗺️ Unifilar Total — SP + VP Integradas")
        st.caption(
            "Visualização unificada das duas gerências. "
            "Bolhas SP em azul-marinho · Bolhas VP em verde · "
            "Pulso = hot-spot crítico"
        )

        # O componente unifilar suporta gerencia='GERAL' para mostrar ambas
        render_unifilar_dual(df_total, gerencia="GERAL")

    # endregion

    # region =================== SESSÃO 5.4: Aba — Temporal Global ============
    with aba_temp:
        st.markdown("#### 📈 Evolução Temporal — SP + VP")

        col_gran, col_met, col_split = st.columns(3)
        with col_gran:
            granularidade = st.selectbox(
                "Granularidade",
                ["Mensal", "Semanal", "Trimestral"],
                index=0,
                key="gran_geral",
            )
        with col_met:
            metrica = st.selectbox(
                "Métrica",
                ["Volume de Notas", "Score Médio", "Lead Time Médio"],
                index=0,
                key="met_geral",
            )
        with col_split:
            separar = st.checkbox(
                "Separar por gerência",
                value=True,
                help="Exibe SP e VP em séries distintas",
            )

        if separar:
            # Duas séries no mesmo gráfico
            col_s, col_v = st.columns(2)
            with col_s:
                st.markdown(f"<b style='color:{COR_SP};'>SP</b>", unsafe_allow_html=True)
                render_serie_temporal(df_sp, granularidade=granularidade, metrica=metrica, gerencia="SP")
            with col_v:
                st.markdown(f"<b style='color:{COR_VP};'>VP</b>", unsafe_allow_html=True)
                render_serie_temporal(df_vp, granularidade=granularidade, metrica=metrica, gerencia="VP")
        else:
            # Série unificada
            render_serie_temporal(df_total, granularidade=granularidade, metrica=metrica, gerencia="GERAL")

    # endregion

    # region =================== SESSÃO 5.5: Aba — Top Hot-spots ==============
    with aba_rank:
        st.markdown("#### 🏆 Top Hot-spots — SP + VP Unificados")

        col_n, col_ord, col_ger = st.columns(3)
        with col_n:
            top_n = st.selectbox("Top N", [5, 10, 15, 20], index=1, key="topn_geral")
        with col_ord:
            ordem = st.selectbox(
                "Ordenar por",
                ["Score Total", "Qtd. Notas", "Lead Time Médio (dias)"],
                index=0,
                key="ord_geral",
            )
        with col_ger:
            ger_rank = st.selectbox(
                "Gerência",
                ["Todas", "SP", "VP"],
                index=0,
                key="ger_rank",
            )

        # Aplica filtro de gerência para o ranking
        df_rank = df_total.copy()
        if ger_rank != "Todas" and "gerencia_label" in df_rank.columns:
            df_rank = df_rank[df_rank["gerencia_label"] == ger_rank]

        render_ranking(df_rank, top_n=top_n, ordem=ordem, gerencia="GERAL")

    # endregion
