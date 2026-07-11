# =============================================================================
# components/visao_gerencial.py — Aba "Visão Gerencial" (Sprint 4.5)
#
# Recupera as 7 seções que existiam no app1.py (validado com o GG em 25/06/2026)
# e que não foram migradas no pivot para a plataforma multi-gerencial. Adaptado
# ao schema do Sentinel (ramal em vez de trecho, nome_ramal() na UI, disciplina
# VP+EE, STATUS_BASE dos 17 códigos oficiais).
#
# Reutilizável nas 3 telas: gerencia_sp.py, gerencia_vp.py, gerencia_geral.py.
#
# Exporta:
#   render_visao_gerencial(df, gerencia) — orquestra as 7 seções
#
# Sessão 1: Imports & constantes
# Sessão 2: Quantidade por Criticidade
# Sessão 3: Status Concluída — Ordem
# Sessão 4: Notas por Tipo de Inspeção
# Sessão 5: Quantidade por Código de Anomalia
# Sessão 6: Notas por Mês/Semana/Dia — Abertos × Encerrados
# Sessão 7: Planejado × Realizado
# Sessão 8: Quadro Resumo — Detalhamento Executivo
# Sessão 9: render_visao_gerencial() — orquestração
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd
import numpy as np

try:
    from streamlit_echarts import st_echarts, JsCode
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

from core.glossarios import GLOSSARIO_VP, GLOSSARIO_EE, STATUS_BASE, nome_ramal, status_base_label

# Glossário combinado só para tradução de código de anomalia na UI.
# Seguro: prefixos VP (TR/TJ/SD/AM/DM/DO/GE/LA/GM/CS) e EE (SN/EN/TE/WS/S1)
# não colidem.
_GLOSSARIO_ANOMALIA = {**GLOSSARIO_VP, **GLOSSARIO_EE}

COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_CRIT     = "#dc2626"
COR_WARN     = "#f59e0b"
COR_OK       = "#16a34a"

ORDEM_PRIORIDADE = ["1-Muito alta", "2-Alta", "3-Média", "4-Baixa"]
CORES_PRIORIDADE = {
    "1-Muito alta": "#dc2626", "2-Alta": "#f59e0b",
    "3-Média": "#eab308", "4-Baixa": "#16a34a",
}

MESES_PT_ABREV = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}

# endregion


# region ====================== SESSÃO 2: Quantidade por Criticidade ===========

def _render_criticidade(df: pd.DataFrame, gerencia: str):
    st.markdown("##### 📊 Quantidade por Criticidade")

    if "prioridade" not in df.columns or df["prioridade"].dropna().empty:
        st.info("Sem dados de prioridade no filtro atual.")
        return

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        return

    crit_counts = df["prioridade"].value_counts().reindex(ORDEM_PRIORIDADE, fill_value=0)

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": COR_PRIMARIA, "borderWidth": 1,
            "textStyle": {"color": "#1f2937"},
        },
        "grid": {"left": "3%", "right": "5%", "top": "8%", "bottom": "10%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": ORDEM_PRIORIDADE,
            "axisLabel": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
            "axisLine": {"lineStyle": {"color": "#9ca3af"}},
        },
        "yAxis": {
            "type": "value", "axisLabel": {"color": "#374151"},
            "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}},
        },
        "series": [{
            "type": "bar",
            "data": [
                {"value": int(v), "itemStyle": {"color": CORES_PRIORIDADE.get(k, "#6b7280")}}
                for k, v in crit_counts.items()
            ],
            "label": {"show": True, "position": "top", "color": "#1f2937",
                      "fontSize": 13, "fontWeight": "bold", "formatter": "{c}"},
            "barWidth": "55%",
        }],
    }
    st_echarts(opt, height="320px", key=f"vg_criticidade_{gerencia}")

# endregion


# region ====================== SESSÃO 3: Status Concluída — Ordem =============

def _render_status_ordem(df: pd.DataFrame, gerencia: str):
    st.markdown("##### 🎯 Status Concluída — Ordem")

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        return

    tem_status_ordem = (
        "status_nota_ordem" in df.columns
        and df["status_nota_ordem"].astype(str).str.strip().replace("nan", "").any()
    )

    if tem_status_ordem:
        status_counts = df["status_nota_ordem"].fillna("—").replace("", "—").value_counts()
    elif "status_usuario" in df.columns:
        status_counts = df["status_usuario"].apply(status_base_label).value_counts()
    else:
        st.info("Sem dados de status no filtro atual.")
        return

    cores_status = {
        "NOK": COR_PRIMARIA, "OK": COR_GOLD,
        "Aberta": COR_CRIT, "Concluída": COR_OK,
        "Diferida": COR_WARN, "Cancelada": "#9ca3af",
        "—": "#9ca3af",
    }
    donut_data = [
        {"value": int(v), "name": str(k),
         "itemStyle": {"color": cores_status.get(str(k), "#6b7280")}}
        for k, v in status_counts.items()
    ]
    opt = {
        "tooltip": {
            "trigger": "item", "formatter": "{b}: <b>{c}</b> ({d}%)",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": COR_PRIMARIA, "textStyle": {"color": "#1f2937"},
        },
        "legend": {"top": "5%", "left": "center", "textStyle": {"color": "#374151"}},
        "series": [{
            "type": "pie", "radius": ["45%", "70%"], "center": ["50%", "58%"],
            "avoidLabelOverlap": True,
            "label": {"show": True, "formatter": "{c}\n({d}%)",
                      "color": "#1f2937", "fontSize": 13, "fontWeight": "bold"},
            "labelLine": {"show": True, "lineStyle": {"color": "#9ca3af"}},
            "data": donut_data,
        }],
    }
    st_echarts(opt, height="320px", key=f"vg_status_ordem_{gerencia}")

# endregion


# region ====================== SESSÃO 4: Notas por Tipo de Inspeção ===========

def _gradiente_azul_dourado(idx: int, total: int) -> str:
    """Verde-azulado (topo) para dourado (fim) — gradiente MRS."""
    if total <= 1:
        return COR_PRIMARIA
    ratio = idx / (total - 1)
    r = int(30 + (245 - 30) * ratio)
    g = int(58 + (158 - 58) * ratio)
    b = int(95 + (11 - 95) * ratio)
    return f"rgb({r},{g},{b})"


def _render_tipo_inspecao(df: pd.DataFrame, gerencia: str):
    st.markdown("##### 🔍 Notas por Tipo de Inspeção")
    st.caption(
        "Distribuição das notas pela origem — como foi descoberta a anomalia "
        "(Ronda, Drone, Trackstar, Inspeção técnica de AMV etc.)."
    )

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        return

    if "tipo_atividade" not in df.columns:
        st.info("Coluna 'tipo_atividade' não disponível nos dados.")
        return

    df_ta = df.copy()
    df_ta["tipo_atividade"] = df_ta["tipo_atividade"].fillna("(Sem tipo)").replace("", "(Sem tipo)")
    ta_counts = df_ta["tipo_atividade"].value_counts().head(15)

    if ta_counts.empty:
        st.info("Sem dados de tipo de inspeção no filtro atual.")
        return

    labels = ta_counts.index.tolist()[::-1]
    valores = [int(v) for v in ta_counts.values.tolist()[::-1]]
    cores = [_gradiente_azul_dourado(i, len(valores)) for i in range(len(valores))]

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA,
            "textStyle": {"color": "#1f2937"}, "formatter": "<b>{b}</b><br/>Qtd: <b>{c}</b> notas",
        },
        "grid": {"left": "3%", "right": "8%", "top": "5%", "bottom": "5%", "containLabel": True},
        "xAxis": {"type": "value", "axisLabel": {"color": "#374151"},
                  "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
        "yAxis": {
            "type": "category", "data": labels,
            "axisLabel": {"color": "#374151", "fontSize": 11, "fontWeight": "bold",
                          "width": 180, "overflow": "truncate"},
        },
        "series": [{
            "type": "bar",
            "data": [{"value": v, "itemStyle": {"color": cores[i]}} for i, v in enumerate(valores)],
            "label": {"show": True, "position": "right", "color": "#1f2937",
                      "fontSize": 11, "fontWeight": "bold"},
            "barWidth": "60%",
        }],
    }
    altura = max(300, 30 * len(labels) + 80)
    st_echarts(opt, height=f"{altura}px", key=f"vg_tipo_insp_{gerencia}")

    total_dist = df["tipo_atividade"].nunique()
    if total_dist > 15:
        st.caption(f"⚠️ Mostrando os **15 tipos com mais notas**. Total distintos: **{total_dist:,}**.")

# endregion


# region ====================== SESSÃO 5: Quantidade por Código de Anomalia ====

def _gradiente_vermelho(idx: int, total: int) -> str:
    if total <= 1:
        return COR_CRIT
    ratio = 1 - (idx / (total - 1))
    r = int(220 + (245 - 220) * (1 - ratio))
    g = int(38 + (158 - 38) * (1 - ratio))
    b = int(38 + (11 - 38) * (1 - ratio))
    return f"rgb({r},{g},{b})"


def _render_codigo_anomalia(df: pd.DataFrame, gerencia: str):
    st.markdown("##### 🚨 Quantidade por Código de Anomalia")
    st.caption(
        "Top códigos de anomalia (TJ04, AM13, SN63...) com tradução técnica. "
        "Mostra quais defeitos mais ocorrem na malha filtrada."
    )

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        return

    if "code_codificacao" not in df.columns:
        st.info("Coluna 'code_codificacao' não disponível nos dados.")
        return

    df_an = df.copy()
    df_an["code_codificacao"] = df_an["code_codificacao"].fillna("(Sem código)").replace("", "(Sem código)")
    anom_counts = df_an["code_codificacao"].value_counts().head(20)

    if anom_counts.empty:
        st.info("Sem dados de código de anomalia no filtro atual.")
        return

    labels = []
    for cod in anom_counts.index.tolist():
        if cod == "(Sem código)":
            labels.append(cod)
        else:
            desc = _GLOSSARIO_ANOMALIA.get(str(cod), "Outros / Não catalogado")
            labels.append(f"{cod} — {desc}")

    labels = labels[::-1]
    valores = [int(v) for v in anom_counts.values.tolist()[::-1]]
    cores = [_gradiente_vermelho(i, len(valores)) for i in range(len(valores))]

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_CRIT, "borderWidth": 2,
            "padding": [10, 14], "textStyle": {"color": "#1f2937"},
            "formatter": "<b>{b}</b><br/>Ocorrências: <b>{c}</b> notas",
            "extraCssText": "max-width:350px;border-radius:8px;",
        },
        "grid": {"left": "3%", "right": "10%", "top": "5%", "bottom": "5%", "containLabel": True},
        "xAxis": {"type": "value", "axisLabel": {"color": "#374151"},
                  "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
        "yAxis": {
            "type": "category", "data": labels,
            "axisLabel": {"color": "#374151", "fontSize": 11, "fontWeight": "bold",
                          "width": 280, "overflow": "truncate"},
        },
        "series": [{
            "type": "bar",
            "data": [{"value": v, "itemStyle": {"color": cores[i]}} for i, v in enumerate(valores)],
            "label": {"show": True, "position": "right", "color": "#1f2937",
                      "fontSize": 11, "fontWeight": "bold"},
            "barWidth": "65%",
        }],
    }
    altura = max(400, 28 * len(labels) + 80)
    st_echarts(opt, height=f"{altura}px", key=f"vg_anomalia_{gerencia}")

    total_dist = df["code_codificacao"].nunique()
    if total_dist > 20:
        st.caption(f"⚠️ Mostrando os **20 códigos com mais ocorrências**. Total distintos: **{total_dist:,}**.")

# endregion


# region ====================== SESSÃO 6: Notas por Mês/Semana/Dia =============

def _fmt_data_drill(d, fmt):
    try:
        ts = pd.Timestamp(d) if not isinstance(d, pd.Timestamp) else d
        if pd.isna(ts):
            return "—"
        return ts.strftime(fmt)
    except (ValueError, TypeError):
        return str(d)


def _render_notas_periodo(df: pd.DataFrame, gerencia: str):
    st.markdown("##### 📅 Notas por Mês/Semana/Dia — Abertas × Encerradas")

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        return

    if "data_nota" not in df.columns:
        st.info("Coluna 'data_nota' não disponível nos dados.")
        return

    col_g, col_desc = st.columns([1, 3])
    with col_g:
        granul = st.radio(
            "Granularidade:", ["Mês", "Semana", "Dia"], horizontal=False,
            key=f"vg_granul_{gerencia}",
        )
    with col_desc:
        st.caption(
            "Azul = notas que **abriram**. Laranja = notas que **encerraram**. "
            "Quando azul > laranja consistentemente, o backlog cresce."
        )

    d = df.copy()
    d["dt_abert"] = pd.to_datetime(d.get("data_nota"), errors="coerce")
    d["dt_encer"] = pd.to_datetime(d.get("data_encerramento"), errors="coerce")

    d_abert = d.dropna(subset=["dt_abert"])
    d_encer = d.dropna(subset=["dt_encer"])

    if granul == "Dia":
        s_a = d_abert.groupby(d_abert["dt_abert"].dt.date).size()
        s_e = d_encer.groupby(d_encer["dt_encer"].dt.date).size()
        fmt_label = "%d/%m/%y"
    elif granul == "Semana":
        s_a = d_abert.groupby(d_abert["dt_abert"].dt.to_period("W").dt.start_time).size()
        s_e = d_encer.groupby(d_encer["dt_encer"].dt.to_period("W").dt.start_time).size()
        fmt_label = "Sem %d/%m/%y"
    else:  # Mês
        s_a = d_abert.groupby(d_abert["dt_abert"].dt.to_period("M").dt.start_time).size()
        s_e = d_encer.groupby(d_encer["dt_encer"].dt.to_period("M").dt.start_time).size()
        fmt_label = "%b/%y"

    todas_datas = sorted(set(s_a.index) | set(s_e.index))
    if not todas_datas:
        st.info("Sem dados temporais para a granularidade escolhida.")
        return

    rotulos = [_fmt_data_drill(dd, fmt_label) for dd in todas_datas]
    vals_a = [int(s_a.get(dd, 0)) for dd in todas_datas]
    vals_e = [int(s_e.get(dd, 0)) for dd in todas_datas]

    def _topk(vals, k=3):
        return set(sorted(range(len(vals)), key=lambda i: vals[i], reverse=True)[:k])

    picos_a, picos_e = _topk(vals_a), _topk(vals_e)

    def _marcado(vals, picos, cor, cor_label):
        return [
            {"value": v, "itemStyle": {"color": cor, "borderColor": "#fff", "borderWidth": 2},
             "symbolSize": 14, "label": {"show": True, "position": "top",
                                          "color": cor_label, "fontWeight": "bold"}}
            if i in picos else v
            for i, v in enumerate(vals)
        ]

    opt = {
        "tooltip": {
            "trigger": "axis", "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": COR_PRIMARIA, "textStyle": {"color": "#1f2937"},
            "axisPointer": {"type": "line", "lineStyle": {"color": COR_PRIMARIA, "type": "dashed"}},
        },
        "legend": {"data": ["Abertas", "Encerradas"], "top": 0, "textStyle": {"color": "#374151"}},
        "grid": {"left": "3%", "right": "3%", "top": "12%", "bottom": "20%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": rotulos,
            "axisLabel": {"color": "#374151", "rotate": 45 if len(rotulos) > 12 else 0,
                          "fontSize": 10, "interval": "auto"},
        },
        "yAxis": {"type": "value", "axisLabel": {"color": "#374151"},
                  "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
        "dataZoom": [
            {"type": "slider", "show": True, "bottom": 5, "height": 18,
             "borderColor": "#d1d5db", "fillerColor": "rgba(30,58,95,0.15)",
             "handleStyle": {"color": COR_PRIMARIA}},
            {"type": "inside"},
        ],
        "series": [
            {"name": "Abertas", "type": "line",
             "data": _marcado(vals_a, picos_a, COR_PRIMARIA, COR_PRIMARIA),
             "smooth": False, "lineStyle": {"color": COR_PRIMARIA, "width": 2},
             "itemStyle": {"color": COR_PRIMARIA}, "symbol": "circle", "symbolSize": 6},
            {"name": "Encerradas", "type": "line",
             "data": _marcado(vals_e, picos_e, COR_GOLD, "#b45309"),
             "smooth": False, "lineStyle": {"color": COR_GOLD, "width": 2},
             "itemStyle": {"color": COR_GOLD}, "symbol": "circle", "symbolSize": 6},
        ],
    }
    st_echarts(opt, height="400px", key=f"vg_drill_{gerencia}_{granul}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"📂 Total Abertas ({granul.lower()})", f"{sum(vals_a):,}")
    c2.metric(f"✅ Total Encerradas ({granul.lower()})", f"{sum(vals_e):,}")
    media_a = sum(vals_a) / max(len(vals_a), 1)
    media_e = sum(vals_e) / max(len(vals_e), 1)
    c3.metric(f"📊 Média Abertas/{granul.lower()}", f"{media_a:.1f}")
    c4.metric(f"📊 Média Encerradas/{granul.lower()}", f"{media_e:.1f}")

# endregion


# region ====================== SESSÃO 7: Planejado × Realizado ================

def _render_planejado_realizado(df: pd.DataFrame, gerencia: str):
    st.markdown("##### 📅 Planejado × Realizado — Execução vs Cronograma")
    st.caption(
        "Comparativo mensal de notas planejadas (data_planejada) vs realizadas "
        "(data_encerramento). Aderência = % do realizado sobre o planejado, "
        "limitada a 150% para evitar distorções."
    )

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        return

    if "data_planejada" not in df.columns or df["data_planejada"].dropna().empty:
        st.info(
            "ℹ️ Sem dados de planejamento para o filtro atual. "
            "Esse gráfico exige a coluna `data_planejada` preenchida."
        )
        return

    d = df.copy()
    d["dt_plan"] = pd.to_datetime(d.get("data_planejada"), errors="coerce")
    d["dt_real"] = pd.to_datetime(d.get("data_encerramento"), errors="coerce")

    d_plan = d.dropna(subset=["dt_plan"])
    d_real = d.dropna(subset=["dt_real"])

    if d_plan.empty and d_real.empty:
        st.info("Sem dados de planejamento ou encerramento para o filtro atual.")
        return

    d_plan = d_plan.copy()
    d_real = d_real.copy()
    d_plan["mes"] = d_plan["dt_plan"].dt.to_period("M").dt.to_timestamp()
    d_real["mes"] = d_real["dt_real"].dt.to_period("M").dt.to_timestamp()

    serie_plan = d_plan.groupby("mes").size()
    serie_real = d_real.groupby("mes").size()
    todos_meses = sorted(set(serie_plan.index) | set(serie_real.index))
    rotulos = [f"{MESES_PT_ABREV[m.month]}/{str(m.year)[-2:]}" for m in todos_meses]
    vals_plan = [int(serie_plan.get(m, 0)) for m in todos_meses]
    vals_real = [int(serie_real.get(m, 0)) for m in todos_meses]

    aderencia = []
    for p, r in zip(vals_plan, vals_real):
        if p > 0:
            aderencia.append(min(round((r / p) * 100, 1), 150))
        else:
            aderencia.append(None)

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA, "borderWidth": 2,
            "padding": [10, 14], "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
            "textStyle": {"color": "#1f2937"},
        },
        "legend": {
            "data": ["📋 Planejado", "✅ Realizado", "📈 Aderência (%)"], "top": 0,
            "textStyle": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"}, "itemGap": 22,
        },
        "grid": {"left": "3%", "right": "10%", "top": "15%", "bottom": "18%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": rotulos,
            "axisLabel": {"color": "#374151", "rotate": 35 if len(rotulos) > 8 else 0, "fontSize": 11},
            "axisLine": {"lineStyle": {"color": "#9ca3af"}},
        },
        "yAxis": [
            {"type": "value", "name": "Qtd Notas", "position": "left",
             "axisLabel": {"color": "#374151"},
             "nameTextStyle": {"color": "#374151", "fontSize": 11, "fontWeight": "bold"},
             "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
            {"type": "value", "name": "Aderência (%)", "position": "right",
             "axisLabel": {"color": COR_OK, "formatter": "{value}%", "fontSize": 11},
             "nameTextStyle": {"color": COR_OK, "fontSize": 11, "fontWeight": "bold"},
             "splitLine": {"show": False}, "min": 0, "max": 150},
        ],
        "series": [
            {"name": "📋 Planejado", "type": "bar", "data": vals_plan,
             "itemStyle": {"color": "#7c3aed", "borderRadius": [3, 3, 0, 0]},
             "label": {"show": True, "position": "top", "color": "#5b21b6",
                       "fontSize": 10, "fontWeight": "bold"}, "barGap": "20%"},
            {"name": "✅ Realizado", "type": "bar", "data": vals_real,
             "itemStyle": {"color": COR_OK, "borderRadius": [3, 3, 0, 0]},
             "label": {"show": True, "position": "top", "color": "#166534",
                       "fontSize": 10, "fontWeight": "bold"}},
            {"name": "📈 Aderência (%)", "type": "line", "data": aderencia, "yAxisIndex": 1,
             "smooth": True, "connectNulls": False,
             "lineStyle": {"color": COR_GOLD, "width": 3},
             "itemStyle": {"color": COR_GOLD, "borderColor": "#fff", "borderWidth": 2},
             "symbol": "circle", "symbolSize": 9,
             "label": {"show": True, "position": "top", "formatter": "{c}%",
                       "color": "#b45309", "fontSize": 10, "fontWeight": "bold"},
             "markLine": {
                 "silent": True, "symbol": ["none", "none"],
                 "data": [
                     {"yAxis": 100, "lineStyle": {"color": COR_OK, "type": "dashed", "width": 2},
                      "label": {"show": True, "position": "insideEndTop", "formatter": "Meta 100%",
                                "color": COR_OK, "fontSize": 11, "fontWeight": "bold"}},
                     {"yAxis": 80, "lineStyle": {"color": COR_GOLD, "type": "dotted", "width": 1.5},
                      "label": {"show": True, "position": "insideEndTop", "formatter": "Aceitável 80%",
                                "color": "#b45309", "fontSize": 10}},
                 ],
             }},
        ],
    }
    st_echarts(opt, height="450px", key=f"vg_plan_real_{gerencia}")

    total_plan = sum(vals_plan)
    total_real = sum(vals_real)
    aderencia_global = (total_real / total_plan * 100) if total_plan else 0
    ader_color = "🟢" if aderencia_global >= 90 else ("🟡" if aderencia_global >= 70 else "🔴")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Total Planejado", f"{total_plan:,}")
    c2.metric("✅ Total Realizado", f"{total_real:,}")
    c3.metric(f"{ader_color} Aderência Global", f"{aderencia_global:.1f}%",
              help="(Total Realizado / Total Planejado) × 100")
    saldo = total_real - total_plan
    c4.metric("📊 Saldo (Real - Plan)", f"{saldo:+,}",
              delta_color="normal" if saldo >= 0 else "inverse")

# endregion


# region ====================== SESSÃO 8: Quadro Resumo =========================

_COLUNAS_QUADRO = [
    ("data_nota",          "Data da Nota"),
    ("numero_nota",        "Número da Nota"),
    ("tipo_atividade",     "Tipo de Inspeção"),
    ("local_instalacao",   "Local de Instalação (TPLNR)"),
    ("ramal",              "Ramal"),
    ("origem",             "Pátio"),
    ("prioridade",         "Prioridade"),
    ("familia_defeito",    "Família de Defeito"),
    ("texto_longo",        "Texto Longo da Nota"),
    ("ordem",              "Nº Ordem"),
    ("status_nota_ordem",  "Status Nota c/ Ordem"),
    ("status_usuario",     "Status Base"),
    ("data_encerramento",  "Data Encerramento"),
    ("data_planejada",     "Data Conclusão Desejada"),
]


def _render_quadro_resumo(df: pd.DataFrame, gerencia: str):
    st.markdown("##### 📋 Quadro Resumo — Detalhamento Executivo")
    st.caption(
        "Tabela com as colunas-chave para reunião de rotina. "
        "Ordenada por Data da Nota (mais recente primeiro). Exportável."
    )

    cols_existentes = [(orig, novo) for orig, novo in _COLUNAS_QUADRO if orig in df.columns]
    if not cols_existentes:
        st.info("Nenhuma coluna do quadro resumo disponível nos dados.")
        return

    df_q = df[[c[0] for c in cols_existentes]].copy()
    df_q = df_q.rename(columns={c[0]: c[1] for c in cols_existentes})

    if "Ramal" in df_q.columns:
        df_q["Ramal"] = df_q["Ramal"].apply(lambda s: nome_ramal(s, "completo_sigla") if pd.notna(s) else "—")

    if "Status Base" in df_q.columns:
        df_q["Status Base"] = df_q["Status Base"].apply(status_base_label)

    for col_dt in ["Data da Nota", "Data Encerramento", "Data Conclusão Desejada"]:
        if col_dt in df_q.columns:
            df_q[col_dt] = pd.to_datetime(df_q[col_dt], errors="coerce").dt.strftime("%d/%m/%Y").fillna("—")

    if "Texto Longo da Nota" in df_q.columns:
        df_q["Texto Longo da Nota"] = (
            df_q["Texto Longo da Nota"].fillna("").astype(str)
            .apply(lambda x: x[:120] + "..." if len(x) > 120 else x)
        )

    for col in df_q.select_dtypes(include=["object"]).columns:
        df_q[col] = df_q[col].fillna("—").replace("", "—")

    if "Data da Nota" in df_q.columns:
        df_q_ord = df_q.copy()
        df_q_ord["_sort"] = pd.to_datetime(df_q["Data da Nota"], format="%d/%m/%Y", errors="coerce")
        df_q_ord = df_q_ord.sort_values("_sort", ascending=False).drop(columns="_sort")
    else:
        df_q_ord = df_q

    col_lim, col_info = st.columns([1, 2])
    with col_lim:
        limite = st.selectbox(
            "Mostrar:", [50, 100, 250, 500, "Todas"], index=1,
            key=f"vg_quadro_limite_{gerencia}",
        )
    with col_info:
        st.caption(f"📊 Total de notas no filtro: **{len(df_q_ord):,}**")

    df_show = df_q_ord if limite == "Todas" else df_q_ord.head(int(limite))
    st.dataframe(df_show, use_container_width=True, height=500, hide_index=True)

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_q_ord.to_excel(writer, index=False, sheet_name="Quadro Resumo")
    buffer.seek(0)

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "⬇️ Baixar Quadro Resumo (Excel)", data=buffer,
            file_name=f"quadro_resumo_{gerencia}_{datetime.now():%Y%m%d_%H%M}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"vg_dl_xlsx_{gerencia}",
        )
    with col_dl2:
        csv_bytes = df_q_ord.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            "⬇️ Baixar Quadro Resumo (CSV)", data=csv_bytes,
            file_name=f"quadro_resumo_{gerencia}_{datetime.now():%Y%m%d_%H%M}.csv",
            mime="text/csv", key=f"vg_dl_csv_{gerencia}",
        )

# endregion


# region ====================== SESSÃO 9: Orquestração ==========================

def render_visao_gerencial(df: pd.DataFrame, gerencia: str = "SP"):
    """
    Renderiza a aba completa "Visão Gerencial" — 7 seções recuperadas do
    app1.py (Sprint 4.5). Reutilizável em SP, VP e Geral.

    Args:
        df: DataFrame já filtrado (mesmo df usado nas outras abas da tela)
        gerencia: 'SP', 'VP' ou 'GERAL' — usado só para chaves únicas dos widgets
    """
    if df.empty:
        st.warning("⚠️ Sem dados após filtros.")
        return

    _render_criticidade(df, gerencia)
    st.markdown("---")

    _render_status_ordem(df, gerencia)
    st.markdown("---")

    _render_tipo_inspecao(df, gerencia)
    st.markdown("---")

    _render_codigo_anomalia(df, gerencia)
    st.markdown("---")

    _render_notas_periodo(df, gerencia)
    st.markdown("---")

    _render_planejado_realizado(df, gerencia)
    st.markdown("---")

    _render_quadro_resumo(df, gerencia)

# endregion
