# components/kpi_card.py
# Cards KPI Premium com sparkline para as telas de gerência
# Sprint 3 — Visualizações por Gerência
#
# USO:
#   from components.kpi_card import render_kpi_cards
#   render_kpi_cards(df, disciplina="VP")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date
from core.glossarios import nome_ramal

# region ====================== SESSÃO 1: Paleta de Cores =======================

CORES = {
    "navy":    "#1e3a5f",
    "gold":    "#ffb000",
    "success": "#16a34a",
    "warning": "#f59e0b",
    "danger":  "#dc2626",
    "info":    "#0891b2",
    "purple":  "#7c3aed",
    "muted":   "#6b7280",
}

# endregion


# region ====================== SESSÃO 2: Funções auxiliares ====================

def _sparkline(series: pd.Series, cor: str = "#1e3a5f") -> go.Figure:
    """
    Gera um sparkline minimalista (sem eixos, sem fundo) para embed nos cards.

    Args:
        series: valores mensais ordenados (mais antigo → mais recente)
        cor:    cor da linha

    Returns:
        go.Figure pronto para st.plotly_chart
    """
    fig = go.Figure(
        go.Scatter(
            y=series.tolist(),
            mode="lines",
            line=dict(color=cor, width=2),
            fill="tozeroy",
            fillcolor=f"rgba({int(cor[1:3],16)},{int(cor[3:5],16)},{int(cor[5:7],16)},0.1)",
        )
    )
    fig.update_layout(
        height=40,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


def _serie_mensal(df: pd.DataFrame, col_data: str = "data_nota") -> pd.Series:
    """
    Agrega notas por mês dos últimos 12 meses.
    Retorna série com contagem mensal (índice = período).
    """
    if col_data not in df.columns:
        return pd.Series(dtype=float)

    df_copy = df.copy()
    df_copy[col_data] = pd.to_datetime(df_copy[col_data], errors="coerce")
    df_valid = df_copy.dropna(subset=[col_data])

    if df_valid.empty:
        return pd.Series(dtype=float)

    # Últimos 12 meses
    hoje = pd.Timestamp.now()
    inicio = hoje - pd.DateOffset(months=12)
    df_12m = df_valid[df_valid[col_data] >= inicio]

    if df_12m.empty:
        return pd.Series(dtype=float)

    serie = (
        df_12m.groupby(df_12m[col_data].dt.to_period("M"))
        .size()
        .sort_index()
    )
    return serie


def _card_html(
    titulo: str,
    valor: str,
    delta: str = "",
    delta_positivo: bool = True,
    cor_borda: str = "#1e3a5f",
    icone: str = "📊",
) -> str:
    """
    Retorna HTML de um card KPI com estilo padrão MRS.

    Args:
        titulo:          label do KPI
        valor:           valor principal (str formatado)
        delta:           variação vs período anterior (opcional)
        delta_positivo:  True = verde, False = vermelho
        cor_borda:       cor da borda esquerda
        icone:           emoji do card
    """
    cor_delta = CORES["success"] if delta_positivo else CORES["danger"]
    delta_html = (
        f"<span style='color:{cor_delta}; font-size:11px;'>{delta}</span>"
        if delta else ""
    )
    return f"""
    <div style='
        background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid #e5e7eb;
        border-left: 4px solid {cor_borda};
        padding: 14px 16px 10px 16px;
        border-radius: 12px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        margin-bottom: 4px;
        min-height: 80px;
    '>
        <div style='font-size:11px; color:#6b7280; margin-bottom:4px;'>{icone} {titulo}</div>
        <div style='font-size:24px; font-weight:700; color:#1f2937; line-height:1.1;'>{valor}</div>
        {delta_html}
    </div>
    """

# endregion


# region ====================== SESSÃO 3: Render Principal =====================

def render_kpi_cards(df: pd.DataFrame, disciplina: str = "VP") -> None:
    """
    Renderiza linha de KPIs Premium com sparklines para uma tela de gerência.

    KPIs exibidos:
      1. Total de notas
      2. Notas abertas (ABER)
      3. Score médio
      4. Lead time médio (dias)
      5. Ramal mais crítico
      6. Notas prioridade 1 (muito alta)
      + Sparkline de notas abertas por mês (últimos 12 meses)

    Args:
        df:         DataFrame filtrado com as notas
        disciplina: 'VP', 'EE' ou 'VP+EE' — usado no label
    """
    if df is None or df.empty:
        st.info("📭 Nenhuma nota encontrada com os filtros aplicados.")
        return

    # ── 3.1: Calcular os KPIs ─────────────────────────────────────────────────

    total_notas = len(df)

    # Notas abertas
    col_status = "status_usuario" if "status_usuario" in df.columns else None
    n_aber = (
        int((df[col_status].str.upper() == "ABER").sum())
        if col_status else 0
    )

    # Score médio — protege contra coluna ausente
    score_medio = (
        df["score"].dropna().mean()
        if "score" in df.columns and not df["score"].dropna().empty
        else 0.0
    )

    # Lead time médio
    lead_medio = (
        df["lead_time_dias"].dropna().mean()
        if "lead_time_dias" in df.columns and not df["lead_time_dias"].dropna().empty
        else 0.0
    )

    # Ramal mais crítico (maior score total)
    ramal_critico = "—"
    if "ramal" in df.columns and "score" in df.columns:
        por_ramal = (
            df.groupby("ramal")["score"].sum().dropna()
        )
        if not por_ramal.empty:
            sigla_top = por_ramal.idxmax()
            ramal_critico = nome_ramal(sigla_top)

    # Notas prioridade máxima
    col_prio = "prioridade" if "prioridade" in df.columns else None
    n_muito_alta = (
        int((df[col_prio].str.contains("1-Muito alta", na=False)).sum())
        if col_prio else 0
    )

    # Sparkline — notas abertas por mês
    if col_status:
        df_aber = df[df[col_status].str.upper() == "ABER"]
        serie_spark = _serie_mensal(df_aber)
    else:
        serie_spark = _serie_mensal(df)

    # ── 3.2: Renderizar em 3 colunas + 1 coluna de sparkline ────────────────

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1.6])

    with col1:
        st.markdown(
            _card_html("Total de Notas", f"{total_notas:,}", icone="📋", cor_borda=CORES["navy"]),
            unsafe_allow_html=True,
        )
        st.markdown(
            _card_html(
                "Prioridade Máxima",
                f"{n_muito_alta:,}",
                icone="🚨",
                cor_borda=CORES["danger"],
                delta_positivo=False,
            ),
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            _card_html(
                "Notas Abertas",
                f"{n_aber:,}",
                icone="📂",
                cor_borda=CORES["warning"],
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            _card_html(
                "Lead Time Médio",
                f"{lead_medio:.0f} dias",
                icone="⏱️",
                cor_borda=CORES["purple"],
                delta_positivo=(lead_medio <= 30),
            ),
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            _card_html(
                "Score Médio",
                f"{score_medio:.1f}",
                icone="⚖️",
                cor_borda=CORES["gold"],
            ),
            unsafe_allow_html=True,
        )
        ramal_display = ramal_critico[:22] + "…" if len(ramal_critico) > 22 else ramal_critico
        st.markdown(
            _card_html(
                "Ramal Mais Crítico",
                ramal_display,
                icone="🚂",
                cor_borda=CORES["danger"],
                delta_positivo=False,
            ),
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            """
            <div style='
                background: linear-gradient(145deg,#ffffff 0%,#f8fafc 100%);
                border: 1px solid #e5e7eb;
                border-left: 4px solid #0891b2;
                padding: 12px 16px 6px 16px;
                border-radius: 12px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.06);
            '>
            <div style='font-size:11px; color:#6b7280; margin-bottom:2px;'>
                📈 Notas Abertas — Últimos 12 meses
            </div>
            """,
            unsafe_allow_html=True,
        )

        if not serie_spark.empty and len(serie_spark) > 1:
            fig_spark = _sparkline(serie_spark, cor=CORES["info"])
            st.plotly_chart(fig_spark, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("_(dados insuficientes para sparkline)_")

        st.markdown("</div>", unsafe_allow_html=True)

# endregion
