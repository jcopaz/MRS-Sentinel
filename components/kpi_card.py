# =============================================================================
# components/kpi_card.py — KPI Cards com Sparklines ECharts
# Sprint 3 (rev.3) — MRS Sentinel
#
# FIEL AO app1.py:
#   • kpi_card_sparkline() com ECharts (smooth line + areaStyle gradiente)
#   • gerar_sparkline()    filtra últimos 12 meses
#   • render_kpi_cards()   4 KPIs: Total, Prio Alta, Ramal top, Lead Time
#
# Sessão 1: Imports & helpers
# Sessão 2: gerar_sparkline()
# Sessão 3: kpi_card_sparkline()
# Sessão 4: render_kpi_cards()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Helpers ====================
import streamlit as st
import pandas as pd
import numpy as np

try:
    from streamlit_echarts import st_echarts
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

import plotly.graph_objects as go

from core.glossarios import nome_ramal

COR_PRIMARIA = "#1e3a5f"
COR_CRIT     = "#dc2626"
COR_WARN     = "#f59e0b"
COR_OK       = "#16a34a"
COR_EE       = "#7c3aed"

MESES_PT = {
    1:"Jan", 2:"Fev", 3:"Mar", 4:"Abr", 5:"Mai", 6:"Jun",
    7:"Jul", 8:"Ago", 9:"Set", 10:"Out", 11:"Nov", 12:"Dez",
}
# endregion


# region ====================== SESSÃO 2: gerar_sparkline() ====================

def gerar_sparkline(df_base: pd.DataFrame, agg_func: str = "count",
                    coluna: str = "numero_nota") -> dict:
    """
    Gera dados de sparkline dos últimos 12 meses.
    FIEL AO app1.py — mesma lógica, mesmo formato de saída.
    """
    col_nota = "numero_nota" if "numero_nota" in df_base.columns else (
               "nota" if "nota" in df_base.columns else None)

    if len(df_base) == 0 or "data_nota" not in df_base.columns:
        return {"meses": [], "valores": []}

    s = df_base.dropna(subset=["data_nota"]).copy()
    if s.empty:
        return {"meses": [], "valores": []}

    s["data_nota"] = pd.to_datetime(s["data_nota"], errors="coerce")
    s = s.dropna(subset=["data_nota"])
    s["mes"] = s["data_nota"].dt.to_period("M").dt.to_timestamp()

    col_eff = coluna if coluna in s.columns else (col_nota or s.columns[0])

    if agg_func == "count":
        serie = s.groupby("mes").size()
    else:
        serie = s.groupby("mes")[col_eff].agg(agg_func)

    serie = serie.tail(12)
    rotulos = [f"{MESES_PT[d.month]}/{str(d.year)[-2:]}" for d in serie.index]
    return {"meses": rotulos, "valores": [float(v) for v in serie.values]}

# endregion


# region ====================== SESSÃO 3: kpi_card_sparkline() =================

def kpi_card_sparkline(col, valor: str, label: str, sparkline_data: dict,
                       cor_principal: str, icone: str, spark_key: str = ""):
    """
    KPI Card com sparkline ECharts.
    FIEL AO app1.py: card HTML + sparkline smooth + areaStyle gradiente.

    Nota: ECharts aceita hex+alpha (#rrggbbaa), diferente do Plotly.
          Por isso usamos cor_principal + '50' e '05' diretamente.
    """
    with col:
        # Card HTML (igual app1)
        st.markdown(
            f"""
            <div style='
                background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
                border: 1px solid #e5e7eb;
                border-left: 4px solid {cor_principal};
                padding: 16px 18px;
                border-radius: 12px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.06);
                margin-bottom: 8px;
            '>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <div>
                        <div style='font-size:12px; color:#6b7280; font-weight:600;
                                    text-transform:uppercase; letter-spacing:0.5px;'>
                            {icone} {label}
                        </div>
                        <div style='font-size:28px; font-weight:800;
                                    color:{cor_principal}; line-height:1.2; margin-top:4px;'>
                            {valor}
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        meses   = sparkline_data.get("meses", [])
        valores = sparkline_data.get("valores", [])

        if valores and len(valores) >= 2:
            if ECHARTS_OK:
                # ECharts sparkline — igual app1
                # ECharts aceita #rrggbbaa (8 chars hex+alpha)
                spark_opt = {
                    "grid": {"left": 5, "right": 5, "top": 10, "bottom": 5,
                             "containLabel": False},
                    "xAxis": {
                        "type": "category", "show": False,
                        "data": meses, "boundaryGap": False,
                    },
                    "yAxis": {"type": "value", "show": False, "scale": True},
                    "tooltip": {
                        "trigger": "axis",
                        "backgroundColor": "rgba(255,255,255,0.98)",
                        "borderColor": cor_principal,
                        "borderWidth": 2,
                        "padding": [8, 12],
                        "textStyle": {"color": "#1f2937", "fontSize": 13,
                                     "fontWeight": "bold"},
                        "extraCssText": (
                            "box-shadow:0 4px 12px rgba(0,0,0,0.15);"
                            "border-radius:8px;"
                        ),
                        "axisPointer": {
                            "type": "line",
                            "lineStyle": {"color": cor_principal, "width": 1,
                                         "type": "dashed"},
                        },
                    },
                    "series": [{
                        "type": "line",
                        "data": valores,
                        "smooth": True,
                        "showSymbol": False,
                        "emphasis": {
                            "itemStyle": {
                                "color": cor_principal,
                                "borderColor": "#fff", "borderWidth": 2,
                            },
                            "scale": 2,
                        },
                        "lineStyle": {"color": cor_principal, "width": 2.5},
                        # ECharts aceita hex+alpha — igual app1
                        "areaStyle": {
                            "color": {
                                "type": "linear",
                                "x": 0, "y": 0, "x2": 0, "y2": 1,
                                "colorStops": [
                                    {"offset": 0,
                                     "color": f"{cor_principal}50"},
                                    {"offset": 1,
                                     "color": f"{cor_principal}05"},
                                ],
                            }
                        },
                    }],
                }
                st_echarts(
                    spark_opt, height="55px",
                    key=f"spark_{spark_key}_{label.replace(' ', '_')}",
                )
            else:
                # Fallback Plotly — converte hex para rgba
                h = cor_principal.lstrip("#")
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=meses, y=valores, mode="lines",
                    line=dict(color=cor_principal, width=2),
                    fill="tozeroy",
                    fillcolor=f"rgba({r},{g},{b},0.15)",
                ))
                fig.update_layout(
                    height=55, margin=dict(l=0, r=0, t=0, b=0),
                    plot_bgcolor="white", paper_bgcolor="white",
                    xaxis=dict(visible=False),
                    yaxis=dict(visible=False),
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)

# endregion


# region ====================== SESSÃO 4: render_kpi_cards() ===================

def render_kpi_cards(df: pd.DataFrame, gerencia: str = "SP",
                     disciplina: str = "VP"):
    """
    Renderiza 4 KPI Cards com sparklines ECharts.
    FIEL AO app1.py — mesma lógica dos 4 KPIs.

    KPIs:
      1. Total de Notas         (azul)   — sparkline volume mensal
      2. Prio Alta/Muito Alta % (vermelho)
      3. Ramal mais crítico     (amarelo)
      4. Lead Time Médio (verde) OR Pátio mais crítico (roxo)
    """
    if df.empty:
        st.info("Sem dados para exibir KPIs.")
        return

    total_notas = len(df)

    # ── Prioridade Alta ────────────────────────────────────────────────────────
    col_prio = "prioridade" if "prioridade" in df.columns else None
    if col_prio:
        mask_alta   = df[col_prio].isin(["1-Muito alta", "2-Alta"])
        pct_critica = (mask_alta.sum() / total_notas * 100) if total_notas else 0.0
    else:
        mask_alta   = pd.Series([False] * len(df), index=df.index)
        pct_critica = 0.0

    # ── Ramal mais crítico ─────────────────────────────────────────────────────
    col_ramal = "ramal" if "ramal" in df.columns else (
                "trecho" if "trecho" in df.columns else None)
    if col_ramal and "score" in df.columns and total_notas > 0:
        ramal_top       = df.groupby(col_ramal)["score"].sum().idxmax()
        ramal_top_label = nome_ramal(ramal_top, "sigla") if ramal_top else "—"
    else:
        ramal_top = ramal_top_label = "—"

    # ── Pátio mais crítico ─────────────────────────────────────────────────────
    col_patio = "origem" if "origem" in df.columns else None
    if col_patio and "score" in df.columns and total_notas > 0:
        patio_top = df.groupby(col_patio)["score"].sum().idxmax()
    else:
        patio_top = "—"

    # ── Lead Time ─────────────────────────────────────────────────────────────
    lead_time_medio = None
    if "lead_time_dias" in df.columns:
        lt_valido = pd.to_numeric(df["lead_time_dias"], errors="coerce").dropna()
        if len(lt_valido) > 0:
            lead_time_medio = lt_valido.mean()

    # ── Sparklines ────────────────────────────────────────────────────────────
    spark_total    = gerar_sparkline(df)
    spark_critica  = gerar_sparkline(df[mask_alta])
    spark_ramal    = (
        gerar_sparkline(df[df[col_ramal] == ramal_top])
        if ramal_top != "—" and col_ramal else {"meses": [], "valores": []}
    )

    if lead_time_medio is not None:
        df_lt = df.dropna(subset=["data_nota", "lead_time_dias"]).copy()
        df_lt["data_nota"] = pd.to_datetime(df_lt["data_nota"], errors="coerce")
        df_lt = df_lt.dropna(subset=["data_nota"])
        if not df_lt.empty:
            df_lt["mes"] = df_lt["data_nota"].dt.to_period("M").dt.to_timestamp()
            serie_lt = df_lt.groupby("mes")["lead_time_dias"].mean().tail(12)
            spark_kpi4 = {
                "meses":   [f"{MESES_PT[d.month]}/{str(d.year)[-2:]}"
                            for d in serie_lt.index],
                "valores": [round(float(v), 0) for v in serie_lt.values],
            }
        else:
            spark_kpi4 = {"meses": [], "valores": []}
    else:
        spark_kpi4 = (
            gerar_sparkline(df[df[col_patio] == patio_top])
            if patio_top != "—" and col_patio else {"meses": [], "valores": []}
        )

    # ── Renderiza ─────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    kp = f"{gerencia}_{disciplina}"

    kpi_card_sparkline(col1, f"{total_notas:,}",
                       "Total de Notas", spark_total, COR_PRIMARIA, "📋", kp)
    kpi_card_sparkline(col2, f"{pct_critica:.1f}%",
                       "Prio. Alta/Muito Alta", spark_critica, COR_CRIT, "🔴", kp)
    kpi_card_sparkline(col3, ramal_top_label,
                       "Ramal mais crítico", spark_ramal, COR_WARN, "🗺️", kp)

    if lead_time_medio is not None:
        kpi_card_sparkline(col4, f"{lead_time_medio:.0f} dias",
                           "Lead Time Médio", spark_kpi4, COR_OK, "⏱️", kp)
    else:
        kpi_card_sparkline(col4, str(patio_top),
                           "Pátio mais crítico", spark_kpi4, COR_EE, "📍", kp)

# endregion
