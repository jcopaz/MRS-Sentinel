# components/unifilar.py
# Unifilar Dual: gráfico hero com bolhas pulsantes VP + EE sobre o km da malha
# Sprint 3 — Visualizações por Gerência
#
# USO:
#   from components.unifilar import render_unifilar_dual
#   render_unifilar_dual(df_vp, df_ee)
#
# NOTAS:
#   - Usa streamlit-echarts (ECharts effectScatter para top críticos)
#   - X = km_real, Y = banda disciplina (VP=1, EE=0)
#   - Tamanho da bolha = score; Cor = prioridade
#   - Top 10% de score → effectScatter pulsante
#   - Tooltip rico: KM, pátio, defeito, prioridade, lead time

import streamlit as st
import pandas as pd
import numpy as np
import math
from streamlit_echarts import st_echarts, JsCode
from core.glossarios import nome_ramal

# region ====================== SESSÃO 1: Configurações visuais ================

CORES_PRIORIDADE = {
    "1-Muito alta": "#dc2626",
    "2-Alta":       "#f59e0b",
    "3-Média":      "#0891b2",
    "4-Baixa":      "#16a34a",
    "Desconhecida": "#9ca3af",
}

BANDA_Y = {"VP": 2, "EE": 0}

# endregion


# region ====================== SESSÃO 2: Preparação dos dados =================

def _normalizar_score_para_raio(scores: pd.Series, min_r: float = 6, max_r: float = 30) -> pd.Series:
    s_min = scores.min()
    s_max = scores.max()
    if s_max == s_min:
        return pd.Series([min_r + (max_r - min_r) / 2] * len(scores), index=scores.index)
    return min_r + (scores - s_min) / (s_max - s_min) * (max_r - min_r)


def _preparar_serie(df: pd.DataFrame, disciplina: str, top10_pct: bool) -> list[dict]:
    if df is None or df.empty:
        return []

    df = df.copy()

    if "km_real" not in df.columns:
        return []

    df["km_real"] = pd.to_numeric(df["km_real"], errors="coerce")
    df = df.dropna(subset=["km_real"])

    if df.empty:
        return []

    if "score" not in df.columns or df["score"].isna().all():
        df["score"] = 1.0
    else:
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(1.0)

    df["_raio"] = _normalizar_score_para_raio(df["score"])
    threshold = df["score"].quantile(0.90)

    if top10_pct:
        df = df[df["score"] >= threshold]
    else:
        df = df[df["score"] < threshold]

    if df.empty:
        return []

    y_base = BANDA_Y.get(disciplina, 1)
    pontos = []

    for _, row in df.iterrows():
        km = round(float(row["km_real"]), 3)
        raio = round(float(row["_raio"]), 1)

        prio = str(row.get("prioridade", "Desconhecida"))
        cor = CORES_PRIORIDADE.get(prio, CORES_PRIORIDADE["Desconhecida"])

        ramal_txt = nome_ramal(str(row.get("ramal", "")), "completo_sigla")
        patio_txt  = str(row.get("origem", "—"))
        defeito    = str(row.get("defeito_legivel", row.get("code_codificacao", "—")))
        lead       = row.get("lead_time_dias", "—")
        nota_num   = row.get("numero_nota", "—")
        score_val  = round(float(row.get("score", 0)), 1)

        tooltip = (
            f"<b>[{disciplina}] Nota {nota_num}</b><br/>"
            f"KM: {km}<br/>"
            f"Ramal: {ramal_txt}<br/>"
            f"Patio: {patio_txt}<br/>"
            f"Defeito: {defeito}<br/>"
            f"Prioridade: {prio}<br/>"
            f"Score: {score_val}<br/>"
            f"Lead time: {lead} dias"
        )

        pontos.append({
            "value": [km, y_base, raio],
            "itemStyle": {"color": cor},
            "tooltip": {"formatter": tooltip},
        })

    return pontos


# endregion


# region ====================== SESSÃO 3: Render do gráfico ====================

def render_unifilar_dual(
    df_vp: pd.DataFrame | None = None,
    df_ee: pd.DataFrame | None = None,
    titulo: str = "Unifilar Dual — VP + EE",
    altura: int = 500,
) -> None:
    tem_vp = df_vp is not None and not df_vp.empty
    tem_ee = df_ee is not None and not df_ee.empty

    if not tem_vp and not tem_ee:
        st.info("Nenhum dado disponível para o Unifilar.")
        return

    pontos_vp_norm = _preparar_serie(df_vp, "VP", top10_pct=False) if tem_vp else []
    pontos_ee_norm = _preparar_serie(df_ee, "EE", top10_pct=False) if tem_ee else []
    pontos_vp_top  = _preparar_serie(df_vp, "VP", top10_pct=True)  if tem_vp else []
    pontos_ee_top  = _preparar_serie(df_ee, "EE", top10_pct=True)  if tem_ee else []

    todos_km = []
    for dset in [df_vp, df_ee]:
        if dset is not None and "km_real" in dset.columns:
            todos_km.extend(pd.to_numeric(dset["km_real"], errors="coerce").dropna().tolist())

    km_min = math.floor(min(todos_km)) if todos_km else 0
    km_max = math.ceil(max(todos_km))  if todos_km else 100

    tooltip_base = {
        "trigger": "item",
        "backgroundColor": "rgba(255,255,255,0.98)",
        "borderColor": "#1e3a5f",
        "borderWidth": 2,
        "padding": [10, 14],
        "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
        "textStyle": {"color": "#1f2937", "fontSize": 12},
    }

    _symbol_size_fn = JsCode("function(val){ return val[2]; }")

    series = []

    if pontos_vp_norm:
        series.append({
            "name": "VP",
            "type": "scatter",
            "data": pontos_vp_norm,
            "symbolSize": _symbol_size_fn,
            "itemStyle": {"opacity": 0.65},
            "tooltip": tooltip_base,
        })

    if pontos_ee_norm:
        series.append({
            "name": "EE",
            "type": "scatter",
            "data": pontos_ee_norm,
            "symbolSize": _symbol_size_fn,
            "itemStyle": {"opacity": 0.65},
            "tooltip": tooltip_base,
        })

    if pontos_vp_top:
        series.append({
            "name": "VP Critico",
            "type": "effectScatter",
            "data": pontos_vp_top,
            "symbolSize": _symbol_size_fn,
            "rippleEffect": {"brushType": "stroke", "scale": 3, "period": 3},
            "itemStyle": {"opacity": 0.9},
            "tooltip": tooltip_base,
        })

    if pontos_ee_top:
        series.append({
            "name": "EE Critico",
            "type": "effectScatter",
            "data": pontos_ee_top,
            "symbolSize": _symbol_size_fn,
            "rippleEffect": {"brushType": "stroke", "scale": 3, "period": 3},
            "itemStyle": {"opacity": 0.9},
            "tooltip": tooltip_base,
        })

    option = {
        "title": {
            "text": titulo,
            "textStyle": {"color": "#1e3a5f", "fontSize": 15, "fontWeight": "bold"},
            "left": "center",
            "top": 6,
        },
        "tooltip": tooltip_base,
        "legend": {
            "data": ["VP", "EE", "VP Critico", "EE Critico"],
            "bottom": 4,
            "textStyle": {"color": "#1f2937"},
        },
        "grid": {"left": "5%", "right": "5%", "top": "12%", "bottom": "10%"},
        "xAxis": {
            "type": "value",
            "name": "KM",
            "nameLocation": "end",
            "min": km_min,
            "max": km_max,
            "axisLabel": {"formatter": "{value} km", "color": "#6b7280", "fontSize": 10},
            "splitLine": {"lineStyle": {"color": "#f3f4f6"}},
        },
        "yAxis": {
            "type": "value",
            "min": -0.5,
            "max": 3.0,
            "axisLabel": {
                "formatter": JsCode("function(v){ if(v===2) return 'VP'; if(v===0) return 'EE'; return ''; }"),
                "color": "#1e3a5f",
                "fontSize": 12,
                "fontWeight": "bold",
            },
            "splitLine": {"show": False},
            "axisTick": {"show": False},
        },
        "series": series,
        "backgroundColor": "#ffffff",
    }

    st_echarts(options=option, height=f"{altura}px", key=f"unifilar_{id(df_vp)}_{id(df_ee)}")
    _render_legenda_prioridade()


def _render_legenda_prioridade() -> None:
    itens = [
        ("1-Muito Alta", CORES_PRIORIDADE["1-Muito alta"]),
        ("2-Alta",       CORES_PRIORIDADE["2-Alta"]),
        ("3-Media",      CORES_PRIORIDADE["3-Média"]),
        ("4-Baixa",      CORES_PRIORIDADE["4-Baixa"]),
    ]
    cols = st.columns(len(itens) + 2)
    cols[0].caption("**Prioridade:**")
    for i, (label, cor) in enumerate(itens):
        cols[i + 1].markdown(
            f"<span style='color:{cor}; font-weight:600; font-size:12px;'>&#9679; {label}</span>",
            unsafe_allow_html=True,
        )
    cols[-1].caption("Pulsante = Top 10%")

# endregion