# =============================================================================
# components/kpi_card.py — KPIs Premium com Sparkline
# Sprint 3 — MRS Sentinel
#
# Exporta render_kpi_cards() — exibe 4 KPIs principais com mini-gráfico
# de tendência (sparkline Plotly) e indicador delta vs período anterior.
#
# KPIs exibidos:
#   1. Total de Notas Abertas
#   2. Score Médio da Carteira
#   3. Lead Time Médio (dias)
#   4. Hot-spots Críticos (score no top 25%)
#
# Sessão 1: Imports & constantes
# Sessão 2: Helpers de cálculo
# Sessão 3: _sparkline() — mini-gráfico de tendência
# Sessão 4: _card_kpi() — card individual
# Sessão 5: render_kpi_cards() — ponto de entrada
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_CRIT     = "#dc2626"
COR_WARN     = "#f59e0b"
COR_OK       = "#16a34a"
COR_NA       = "#94a3b8"

# endregion


# region ====================== SESSÃO 2: Helpers de cálculo ===================

def _total_abertas(df: pd.DataFrame) -> int:
    """Conta notas com status iniciado por 'AB' (ABER = Aberta)."""
    if "status_usuario" not in df.columns:
        return len(df)
    return int(df["status_usuario"].str.upper().str.startswith("AB", na=False).sum())


def _score_medio(df: pd.DataFrame) -> float:
    """Score médio; retorna 0.0 se coluna ausente ou vazia."""
    if "score" not in df.columns or df["score"].dropna().empty:
        return 0.0
    return round(float(df["score"].mean()), 1)


def _lead_time_medio(df: pd.DataFrame) -> float:
    """Lead time médio em dias; usa coluna lead_time_dias se disponível."""
    if "lead_time_dias" in df.columns:
        vals = pd.to_numeric(df["lead_time_dias"], errors="coerce").dropna()
        return round(float(vals.mean()), 1) if len(vals) > 0 else 0.0
    return 0.0


def _hotspots_criticos(df: pd.DataFrame) -> int:
    """Conta pontos com score no top 25% (limiar = percentil 75)."""
    if "score" not in df.columns or df["score"].dropna().empty:
        return 0
    limiar = df["score"].quantile(0.75)
    return int((df["score"] >= limiar).sum())


def _delta_periodo_anterior(df: pd.DataFrame, col: str, agg: str = "mean") -> float:
    """
    Calcula delta entre o último mês e o penúltimo.
    Retorna 0.0 se dados insuficientes.
    """
    if "data_nota" not in df.columns or col not in df.columns:
        return 0.0

    df_t = df.copy()
    df_t["data_nota"] = pd.to_datetime(df_t["data_nota"], errors="coerce")
    df_t = df_t.dropna(subset=["data_nota"])

    if df_t.empty:
        return 0.0

    grp = (
        df_t.groupby(pd.Grouper(key="data_nota", freq="ME"))[col]
        .agg(agg)
        .dropna()
    )

    if len(grp) < 2:
        return 0.0

    return round(float(grp.iloc[-1] - grp.iloc[-2]), 1)

# endregion


# region ====================== SESSÃO 3: Sparkline ============================

def _sparkline(df: pd.DataFrame, col: str, agg: str = "mean",
               cor: str = COR_PRIMARIA) -> go.Figure:
    """
    Gera mini-gráfico de linha (sparkline) com a evolução mensal de uma métrica.

    Args:
        df: DataFrame com data_nota e a coluna de métrica
        col: coluna a agregar
        agg: função de agregação ('mean', 'count', 'sum')
        cor: cor da linha

    Returns:
        Figura Plotly minimalista (sem eixos, título, margens)
    """
    fig = go.Figure()

    if "data_nota" not in df.columns or col not in df.columns:
        return fig

    df_t = df.copy()
    df_t["data_nota"] = pd.to_datetime(df_t["data_nota"], errors="coerce")
    df_t = df_t.dropna(subset=["data_nota"])

    if df_t.empty:
        return fig

    grp = (
        df_t.groupby(pd.Grouper(key="data_nota", freq="ME"))[col]
        .agg(agg)
        .dropna()
        .tail(12)   # últimos 12 meses
    )

    if grp.empty:
        return fig

    # Área preenchida suave
    fig.add_trace(go.Scatter(
        x=grp.index,
        y=grp.values,
        mode="lines",
        line=dict(color=cor, width=2),
        fill="tozeroy",
        fillcolor=cor + "22",   # 13% opacidade
        hoverinfo="skip",
    ))

    # Ponto final destacado
    fig.add_trace(go.Scatter(
        x=[grp.index[-1]],
        y=[grp.values[-1]],
        mode="markers",
        marker=dict(color=cor, size=6),
        hoverinfo="skip",
    ))

    fig.update_layout(
        height=60,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )

    return fig

# endregion


# region ====================== SESSÃO 4: Card individual ======================

def _card_kpi(
    col_st,
    titulo: str,
    valor: str,
    delta: float,
    delta_label: str,
    cor_borda: str,
    cor_delta_inverso: bool,
    sparkline_fig: go.Figure,
    icone: str = "📊",
):
    """
    Renderiza um card KPI completo: título, valor, delta e sparkline.

    Args:
        col_st: coluna Streamlit onde renderizar
        titulo: nome do KPI
        valor: valor formatado para exibição
        delta: variação vs período anterior (número)
        delta_label: texto descritivo do delta
        cor_borda: cor da borda esquerda
        cor_delta_inverso: True = delta positivo é ruim (ex: lead time)
        sparkline_fig: figura Plotly do sparkline
        icone: emoji do KPI
    """
    with col_st:
        # Card container
        st.markdown(
            f"""
            <div style='
                background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
                border: 1px solid #e5e7eb;
                border-left: 5px solid {cor_borda};
                padding: 14px 16px 8px 16px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.06);
            '>
                <div style='font-size:0.7rem; color:#6b7280; font-weight:600;
                            text-transform:uppercase; letter-spacing:0.06em;'>
                    {icone} {titulo}
                </div>
                <div style='font-size:1.9rem; font-weight:800;
                            color:{cor_borda}; margin:4px 0 2px 0;'>
                    {valor}
                </div>
                <div style='font-size:0.72rem; color:#9ca3af;'>
                    {delta_label}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Sparkline abaixo do card
        if sparkline_fig and sparkline_fig.data:
            st.plotly_chart(
                sparkline_fig,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"spark_{titulo}",
            )

        # Delta com st.metric (indicador de seta)
        if delta != 0.0:
            delta_color = "normal"
            if cor_delta_inverso:
                # Lead time subindo é ruim → inverte sinal visual
                delta_color = "inverse"
            st.metric(
                label="",
                value="",
                delta=f"{delta:+.1f} vs mês anterior",
                delta_color=delta_color,
                label_visibility="collapsed",
            )

# endregion


# region ====================== SESSÃO 5: Ponto de entrada =====================

def render_kpi_cards(
    df: pd.DataFrame,
    gerencia: str = "SP",
    disciplina: str = "VP+EE",
):
    """
    Renderiza os 4 KPIs principais em linha horizontal.

    KPIs:
        1. Notas Abertas        — total de notas com status ABER
        2. Score Médio          — média do score composto da carteira
        3. Lead Time Médio      — tempo médio de resolução em dias
        4. Hot-spots Críticos   — notas no top 25% de score

    Args:
        df: DataFrame filtrado com score calculado
        gerencia: 'SP', 'VP' ou 'GERAL' (usado nos títulos)
        disciplina: 'VP', 'EE' ou 'VP+EE' (exibido no subtítulo)
    """
    if df.empty:
        st.info("ℹ️ Sem dados para exibir KPIs.")
        return

    # ── Calcula valores ───────────────────────────────────────────────────────
    n_abertas    = _total_abertas(df)
    score_med    = _score_medio(df)
    lt_med       = _lead_time_medio(df)
    n_criticos   = _hotspots_criticos(df)

    # Deltas vs mês anterior
    # count usa coluna auxiliar — se não tiver numero_nota, usa índice
    col_count = "numero_nota" if "numero_nota" in df.columns else df.columns[0]
    delta_abertas  = _delta_periodo_anterior(df, col_count, agg="count")
    delta_score    = _delta_periodo_anterior(df, "score",        agg="mean") if "score" in df.columns else 0.0
    delta_lt       = _delta_periodo_anterior(df, "lead_time_dias",agg="mean") if "lead_time_dias" in df.columns else 0.0

    # ── Cores dinâmicas ───────────────────────────────────────────────────────
    # Score: vermelho se alto (crítico), verde se baixo (bom)
    score_max_ref = 20.0   # referência: score > 20 já é preocupante
    cor_score = (
        COR_CRIT if score_med > score_max_ref * 1.5
        else COR_WARN if score_med > score_max_ref
        else COR_OK
    )

    # Lead time: vermelho > 60 dias, amarelo > 30, verde abaixo
    cor_lt = (
        COR_CRIT if lt_med > 60
        else COR_WARN if lt_med > 30
        else COR_OK
    )

    # ── Sparklines ────────────────────────────────────────────────────────────
    sp_abertas  = _sparkline(df, col_count, agg="count", cor=COR_PRIMARIA)
    sp_score    = _sparkline(df, "score",          agg="mean",  cor=cor_score) if "score" in df.columns else go.Figure()
    sp_lt       = _sparkline(df, "lead_time_dias", agg="mean",  cor=cor_lt)   if "lead_time_dias" in df.columns else go.Figure()
    sp_criticos = _sparkline(df, "score",          agg="count", cor=COR_CRIT) if "score" in df.columns else go.Figure()

    # ── Renderiza os 4 cards em colunas ──────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    _card_kpi(
        col1,
        titulo="Notas Abertas",
        valor=f"{n_abertas:,}",
        delta=delta_abertas,
        delta_label=f"Total: {len(df):,} notas · {disciplina}",
        cor_borda=COR_PRIMARIA,
        cor_delta_inverso=True,   # mais notas abertas = pior
        sparkline_fig=sp_abertas,
        icone="📋",
    )

    _card_kpi(
        col2,
        titulo="Score Médio",
        valor=f"{score_med:.1f}",
        delta=delta_score,
        delta_label="Score composto ponderado",
        cor_borda=cor_score,
        cor_delta_inverso=True,   # score subindo = pior
        sparkline_fig=sp_score,
        icone="⚡",
    )

    _card_kpi(
        col3,
        titulo="Lead Time Médio",
        valor=f"{lt_med:.0f} dias",
        delta=delta_lt,
        delta_label="Tempo médio de resolução",
        cor_borda=cor_lt,
        cor_delta_inverso=True,   # lead time subindo = pior
        sparkline_fig=sp_lt,
        icone="⏱️",
    )

    _card_kpi(
        col4,
        titulo="Hot-spots Críticos",
        valor=f"{n_criticos:,}",
        delta=0.0,   # não calcula delta para hot-spots (muito volátil)
        delta_label="Score no top 25% da carteira",
        cor_borda=COR_CRIT,
        cor_delta_inverso=True,
        sparkline_fig=sp_criticos,
        icone="🔴",
    )

# endregion
