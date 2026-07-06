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

# Mapeamento prioridade → cor
CORES_PRIORIDADE = {
    "1-Muito alta": "#dc2626",  # vermelho
    "2-Alta":       "#f59e0b",  # âmbar
    "3-Média":      "#0891b2",  # azul info
    "4-Baixa":      "#16a34a",  # verde
    "Desconhecida": "#9ca3af",  # cinza
}

# Banda Y para cada disciplina (para plotar lado a lado)
BANDA_Y = {"VP": 2, "EE": 0}

# endregion


# region ====================== SESSÃO 2: Preparação dos dados =================

def _normalizar_score_para_raio(scores: pd.Series, min_r: float = 6, max_r: float = 30) -> pd.Series:
    """
    Normaliza scores para raio de bolha entre min_r e max_r.
    Evita divisão por zero quando todos os scores são iguais.
    """
    s_min = scores.min()
    s_max = scores.max()
    if s_max == s_min:
        return pd.Series([min_r + (max_r - min_r) / 2] * len(scores), index=scores.index)
    return min_r + (scores - s_min) / (s_max - s_min) * (max_r - min_r)


def _preparar_serie(df: pd.DataFrame, disciplina: str, top10_pct: bool) -> list[dict]:
    """
    Converte o DataFrame em lista de pontos para ECharts.

    Args:
        df:          DataFrame de uma disciplina (VP ou EE)
        disciplina:  'VP' ou 'EE'
        top10_pct:   True = retorna apenas os top 10% de score (para effectScatter)
                     False = retorna os demais 90%

    Returns:
        Lista de dicts no formato ECharts { value: [x, y, raio], ... }
    """
    if df is None or df.empty:
        return []

    df = df.copy()

    # Garante coluna km_real
    if "km_real" not in df.columns:
        return []

    df["km_real"] = pd.to_numeric(df["km_real"], errors="coerce")
    df = df.dropna(subset=["km_real"])

    if df.empty:
        return []

    # Score — usa 1.0 como fallback
    if "score" not in df.columns or df["score"].isna().all():
        df["score"] = 1.0
    else:
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(1.0)

    # Raio da bolha proporcional ao score
    df["_raio"] = _normalizar_score_para_raio(df["score"])

    # Threshold dos top 10%
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

        # Determina cor pela prioridade
        prio = str(row.get("prioridade", "Desconhecida"))
        cor = CORES_PRIORIDADE.get(prio, CORES_PRIORIDADE["Desconhecida"])

        # Monta tooltip rich
        ramal_txt = nome_ramal(str(row.get("ramal", "")), "completo_sigla")
        patio_txt  = str(row.get("origem", "—"))
        defeito    = str(row.get("defeito_legivel", row.get("code_codificacao", "—")))
        lead       = row.get("lead_time_dias", "—")
        nota_num   = row.get("numero_nota", "—")
        score_val  = round(float(row.get("score", 0)), 1)

        tooltip = (
            f"<b>[{disciplina}] Nota {nota_num}</b><br/>"
            f"📍 KM: {km}<br/>"
            f"🚂 Ramal: {ramal_txt}<br/>"
            f"🏗️ Pátio: {patio_txt}<br/>"
            f"🔧 Defeito: {defeito}<br/>"
            f"🚨 Prioridade: {prio}<br/>"
            f"⚖️ Score: {score_val}<br/>"
            f"⏱️ Lead time: {lead} dias"
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
    titulo: str = "📡 Unifilar Dual — VP + EE",
    altura: int = 500,
) -> None:
    """
    Renderiza o Unifilar Dual: gráfico hero com bolhas sobre o traçado km.

    Layout visual:
      Banda VP (y=2): bolhas VP — cinza e coloridas, top 10% pulsam em vermelho
      Linha km (y=1): eixo horizontal representando o km da malha
      Banda EE (y=0): bolhas EE — mesmo padrão

    Args:
        df_vp:  DataFrame de Via Permanente (pode ser None)
        df_ee:  DataFrame de Eletroeletrônica (pode ser None)
        titulo: título do gráfico
        altura: altura em pixels
    """
    tem_vp = df_vp is not None and not df_vp.empty
    tem_ee = df_ee is not None and not df_ee.empty

    if not tem_vp and not tem_ee:
        st.info("📭 Nenhum dado disponível para o Unifilar.")
        return

    # ── 3.1: Prepara as séries ─────────────────────────────────────────────

    # Scatter normal (90% menos críticos) — opacidade reduzida
    pontos_vp_norm = _preparar_serie(df_vp, "VP", top10_pct=False) if tem_vp else []
    pontos_ee_norm = _preparar_serie(df_ee, "EE", top10_pct=False) if tem_ee else []

    # EffectScatter (top 10% críticos) — pulsam
    pontos_vp_top  = _preparar_serie(df_vp, "VP", top10_pct=True) if tem_vp else []
    pontos_ee_top  = _preparar_serie(df_ee, "EE", top10_pct=True) if tem_ee else []

    # ── 3.2: Monta configuração ECharts ──────────────────────────────────────

    # Determina range do eixo X
    todos_km = []
    for dset in [df_vp, df_ee]:
        if dset is not None and "km_real" in dset.columns:
            todos_km.extend(pd.to_numeric(dset["km_real"], errors="coerce").dropna().tolist())

    km_min = math.floor(min(todos_km)) if todos_km else 0
    km_max = math.ceil(max(todos_km)) if todos_km else 100

    tooltip_base = {
        "trigger": "item",
        "backgroundColor": "rgba(255,255,255,0.98)",
        "borderColor": "#1e3a5f",
        "borderWidth": 2,
        "padding": [10, 14],
        "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
        "textStyle": {"color": "#1f2937", "fontSize": 12},
    }

    series = []

    _symbol_size_fn = JsCode("function(val){ return val[2]; }")

    # Scatter VP (fundo)
    if pontos_vp_norm:
        series.append({
            "name": "VP",
            "type": "scatter",
            "data": pontos_vp_norm,
            "symbolSize": _symbol_size_fn,
            "itemStyle": {"opacity": 0.65},
            "tooltip": tooltip_base,
        })

    # Scatter EE (fundo)
    if pontos_ee_norm:
        series.append({
            "name": "EE",
            "type": "scatter",
            "data": pontos_ee_norm,
            "symbolSize": _symbol_size_fn,
            "itemStyle": {"opacity": 0.65},
            "tooltip": tooltip_base,
        })

    # EffectScatter VP (top críticos — pulsam)
    if pontos_vp_top:
        series.append({
            "name": "VP Crítico",
            "type": "effectScatter",
            "data": pontos_vp_top,
            "symbolSize": _symbol_size_fn,
            "rippleEffect": {"brushType": "stroke", "scale": 3, "period": 3},
            "itemStyle": {"opacity": 0.9},
            "tooltip": tooltip_base,
        })

    # EffectScatter EE (top críticos — pulsam)
    if pontos_ee_top:
        series.append({
            "name": "EE Crítico",
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
            "data": ["VP", "EE", "VP Crítico", "EE Crítico"],
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

    # Legenda de cores de prioridade
    _render_legenda_prioridade()


def _render_legenda_prioridade() -> None:
    """Exibe pequena legenda de cores de prioridade abaixo do gráfico."""
    itens = [
        ("🔴", "1-Muito Alta", CORES_PRIORIDADE["1-Muito alta"]),
        ("🟠", "2-Alta", CORES_PRIORIDADE["2-Alta"]),
        ("🔵", "3-Média", CORES_PRIORIDADE["3-Média"]),
        ("🟢", "4-Baixa", CORES_PRIORIDADE["4-Baixa"]),
    ]
    cols = st.columns(len(itens) + 2)
    cols[0].caption("**Prioridade:**")
    for i, (emoji, label, cor) in enumerate(itens):
        cols[i + 1].markdown(
            f"<span style='color:{cor}; font-weight:600; font-size:12px;'>"
            f"{emoji} {label}</span>",
            unsafe_allow_html=True,
        )
    cols[-1].caption("🔆 Pulsante = Top 10% crítico")

# endregion