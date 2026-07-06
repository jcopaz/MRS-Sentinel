# components/unifilar.py
# Unifilar ECharts completo — bolhas por KM Real + Dual Mode + dataZoom
# Restaurado do app1.py (Sprint 3.5)
#
# Uso:
#   from components.unifilar import render_unifilar
#   render_unifilar(df_filtrado, cfg)
#
# cfg vem de render_filtros_sidebar() em components/filtros.py

import math
import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts, JsCode


# ---------------------------------------------------------------------------
# Helpers de agregação
# ---------------------------------------------------------------------------

def _top5_defeitos(x: pd.Series) -> str:
    vc = x.dropna().value_counts().head(5)
    if len(vc) == 0:
        return "—"
    return "<br/>".join(
        f"&nbsp;&nbsp;• {d} <span style='color:#9ca3af;'>({n})</span>"
        for d, n in vc.items()
    )


def _patios_unicos(x: pd.Series) -> str:
    vals = [v for v in x.dropna().unique() if str(v).strip()]
    return ", ".join(sorted(vals)) if vals else "—"


def _top3_inspecoes(x: pd.Series) -> str:
    vc = x.dropna().value_counts().head(3)
    vc = vc[vc.index.astype(str).str.strip() != ""]
    return ", ".join(str(t) for t in vc.index) if len(vc) else "—"


# ---------------------------------------------------------------------------
# Construtor de série (normal + pulsante)
# ---------------------------------------------------------------------------

def _construir_serie(
    df_base: pd.DataFrame,
    bin_km: float,
    y_offset: float = 0,
    label: str = "",
) -> tuple[list, list, pd.DataFrame, float | None, float | None]:
    """
    Agrupa notas por bin_km e retorna:
        pontos_normais, pontos_pulsantes, agreg, km_min, km_max
    """
    if df_base.empty:
        return [], [], pd.DataFrame(), None, None

    df_t = df_base.copy()
    df_t["bin_km"] = (df_t["km_real"] // bin_km) * bin_km

    # Coluna de nota — tenta numero_nota, fallback index
    col_nota = "numero_nota" if "numero_nota" in df_t.columns else df_t.index.name or "index"

    agreg = df_t.groupby("bin_km").agg(
        qtd_notas        =(col_nota,          "count"),
        score_total      =("score",            "sum"),
        score_medio      =("score",            "mean"),
        patios           =("origem",           _patios_unicos),
        defeitos         =("defeito_legivel",  _top5_defeitos),
        tipos_inspecao   =("tipo_atividade",   _top3_inspecoes),
        prio_1           =("prioridade",       lambda x: (x == "1-Muito alta").sum()),
        prio_2           =("prioridade",       lambda x: (x == "2-Alta").sum()),
        lt_medio         =("lead_time_dias",   lambda x: x.dropna().mean() if len(x.dropna()) else None),
    ).reset_index()

    if agreg.empty:
        return [], [], pd.DataFrame(), None, None

    qtd_max   = agreg["qtd_notas"].max()
    score_max = agreg["score_total"].max()

    limiar_pulsante = (
        agreg["score_total"].quantile(0.90) if len(agreg) >= 10 else score_max
    )

    pontos_normais   = []
    pontos_pulsantes = []

    for _, row in agreg.iterrows():
        tamanho = 12 + (row["qtd_notas"] / qtd_max) * 43
        lt_txt = (
            f"⏱️ Lead time médio: <b>{row['lt_medio']:.0f} dias</b><br/>"
            if pd.notna(row.get("lt_medio")) else ""
        )
        hover = (
            f"<div style='min-width:220px;'>"
            f"<div style='font-size:13px;color:#9ca3af;margin-bottom:4px;'>{label}</div>"
            f"<div style='font-size:15px;font-weight:700;color:#1e3a5f;margin-bottom:6px;'>"
            f"KM {row['bin_km']:.1f} → {row['bin_km'] + bin_km:.1f}</div>"
            f"<hr style='border:0;border-top:1px solid #e5e7eb;margin:6px 0;'/>"
            f"📋 <b>{row['qtd_notas']}</b> notas<br/>"
            f"⚡ Score: <b>{row['score_total']:.0f}</b><br/>"
            f"🔴 Muito alta: <b>{row['prio_1']}</b> &nbsp;|&nbsp; "
            f"🟠 Alta: <b>{row['prio_2']}</b><br/>"
            f"{lt_txt}"
            f"📍 Pátio(s): <b>{row['patios']}</b><br/>"
            f"🔍 Inspeção: <b>{row['tipos_inspecao']}</b><br/>"
            f"<div style='margin-top:6px;font-size:12px;color:#6b7280;'><b>Top defeitos:</b></div>"
            f"<div style='font-size:12px;'>{row['defeitos']}</div>"
            f"</div>"
        )

        ponto = {
            "value":       [float(row["bin_km"] + bin_km / 2), y_offset,
                            float(row["score_total"]), int(row["qtd_notas"])],
            "symbolSize":  tamanho,
            "tooltipHTML": hover,
        }

        if row["score_total"] >= limiar_pulsante:
            pontos_pulsantes.append(ponto)
        else:
            pontos_normais.append(ponto)

    km_min = float(agreg["bin_km"].min())
    km_max = float(agreg["bin_km"].max() + bin_km)
    return pontos_normais, pontos_pulsantes, agreg, km_min, km_max


# ---------------------------------------------------------------------------
# Sanitizador contra Infinity / NaN no JSON do ECharts
# ---------------------------------------------------------------------------

def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return 0
    return obj


# ---------------------------------------------------------------------------
# Renderização principal
# ---------------------------------------------------------------------------

def render_unifilar(df_filtrado: pd.DataFrame, cfg: dict) -> None:
    """
    Renderiza o Unifilar ECharts com:
      - Seletor de Matriz (com contagem de notas)
      - Modo Dual (Abertas × Concluídas) quando houver 2 origens
      - Bolhas pulsantes nos top 10% de score
      - dataZoom slider para zoom por KM
      - Métricas abaixo (extensão, densidade, hot-spot, lead time)

    Args:
        df_filtrado: DataFrame já filtrado
        cfg:         dict vindo de render_filtros_sidebar()
    """
    bin_km = cfg.get("bin_km", 0.5)

    # Precisa de km_real e trecho
    df_uni = df_filtrado.dropna(subset=["km_real", "trecho"]).copy()

    if df_uni.empty:
        st.warning(
            "⚠️ Nenhuma nota com KM identificado após os filtros. "
            "Tente liberar mais matrizes, pátios ou bases nos filtros. "
            "Se o problema persistir, faça um novo upload da planilha."
        )
        return

    matrizes_com_dados = sorted(df_uni["trecho"].unique())

    # ── Linha de controles ─────────────────────────────────────────────────
    col_modo, col_matriz = st.columns([1, 3])

    # Detecta se há 2 "origens de base" (Abertas / Concluídas)
    # Usa coluna origem_base se existir; senão usa status_amigavel para separar
    if "origem_base" in df_uni.columns:
        bases = sorted(df_uni["origem_base"].unique())
        modo_dual_possivel = len(bases) == 2
    else:
        # Separa por status: abertas vs concluídas
        abertas    = df_uni["status_amigavel"].isin(["Aberta", "Diferida"]) if "status_amigavel" in df_uni.columns else pd.Series(False, index=df_uni.index)
        concluidas = df_uni["status_amigavel"].isin(["Concluída"]) if "status_amigavel" in df_uni.columns else pd.Series(False, index=df_uni.index)
        if abertas.any() and concluidas.any():
            df_uni.loc[abertas,    "origem_base"] = "Abertas"
            df_uni.loc[concluidas, "origem_base"] = "Concluídas"
            df_uni.loc[~abertas & ~concluidas, "origem_base"] = "Outros"
            bases = ["Abertas", "Concluídas"]
            modo_dual_possivel = True
        else:
            df_uni["origem_base"] = "Notas"
            modo_dual_possivel = False

    with col_modo:
        if modo_dual_possivel:
            modo_view = st.radio(
                "🎬 Modo:",
                ["🎯 Dual", "📊 Empilhado"],
                horizontal=False,
                key="uni_modo",
                help="Dual = Abertas vs Concluídas em 2 linhas. Empilhado = soma.",
            )
            modo_dual = "Dual" in modo_view
        else:
            modo_dual = False
            st.caption("📊 Modo empilhado")

    with col_matriz:
        if len(matrizes_com_dados) == 1:
            trecho_view = matrizes_com_dados[0]
            st.markdown(
                f"<div style='padding:8px 12px;background:#1e3a5f;color:#fff;"
                f"border-radius:8px;text-align:center;margin-top:28px;'>"
                f"🚂 Visualizando: <b>{trecho_view}</b></div>",
                unsafe_allow_html=True,
            )
        else:
            opcoes = []
            for m in matrizes_com_dados:
                qtd = len(df_uni[df_uni["trecho"] == m])
                opcoes.append(f"{m} ({qtd:,})")

            escolha = st.radio(
                "🚂 Matriz:",
                opcoes,
                horizontal=True,
                key="uni_matriz",
                help="Cada Matriz gera seu próprio unifilar. "
                     "Número entre parênteses = notas após filtros.",
            )
            trecho_view = escolha.split(" (")[0]

    df_trecho = df_uni[df_uni["trecho"] == trecho_view].copy()

    st.caption(
        f"Cada bolha = agrupamento de notas em janela de **{bin_km * 1000:.0f} m**. "
        f"**Tamanho** = qtd de notas | **Cor** = score de criticidade | "
        f"**Bolhas pulsantes** = top 10% mais críticos. "
        f"Use a **barra inferior** para dar zoom num intervalo de KM."
    )

    # ── Construir séries ───────────────────────────────────────────────────
    series       = []
    km_min_g     = float("inf")
    km_max_g     = float("-inf")
    score_max_g  = 0.0

    if modo_dual:
        df_a = df_trecho[df_trecho["origem_base"] == "Abertas"]
        df_c = df_trecho[df_trecho["origem_base"] == "Concluídas"]

        pn_a, pp_a, ag_a, kma0, kma1 = _construir_serie(df_a, bin_km, y_offset=1,  label="📋 Abertas")
        pn_c, pp_c, ag_c, kmc0, kmc1 = _construir_serie(df_c, bin_km, y_offset=-1, label="✅ Concluídas")

        for v in [kma0, kma1, kmc0, kmc1]:
            if v is not None and pd.notna(v):
                km_min_g = min(km_min_g, v)
                km_max_g = max(km_max_g, v)

        if km_min_g == float("inf"):
            km_min_g = float(df_trecho["km_real"].min())
            km_max_g = float(df_trecho["km_real"].max())

        if len(ag_a): score_max_g = max(score_max_g, float(ag_a["score_total"].max()))
        if len(ag_c): score_max_g = max(score_max_g, float(ag_c["score_total"].max()))

        # Linha da via
        series += [
            {"name": "Via (Abertas)",    "type": "line",
             "data": [[km_min_g, 1], [km_max_g, 1]],
             "lineStyle": {"color": "#374151", "width": 3},
             "symbol": "none", "silent": True, "tooltip": {"show": False}},
            {"name": "Via (Concluídas)", "type": "line",
             "data": [[km_min_g, -1], [km_max_g, -1]],
             "lineStyle": {"color": "#374151", "width": 3},
             "symbol": "none", "silent": True, "tooltip": {"show": False}},
        ]

        if pn_a:
            series.append({"name": "📋 Abertas", "type": "scatter", "data": pn_a,
                           "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5, "opacity": 0.85}})
        if pn_c:
            series.append({"name": "✅ Concluídas", "type": "scatter", "data": pn_c,
                           "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5, "opacity": 0.85}})
        if pp_a:
            series.append({"name": "🔥 Abertas Críticos", "type": "effectScatter", "data": pp_a,
                           "rippleEffect": {"period": 3, "scale": 2.8, "brushType": "stroke"},
                           "showEffectOn": "render",
                           "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})
        if pp_c:
            series.append({"name": "🔥 Concluídas Críticos", "type": "effectScatter", "data": pp_c,
                           "rippleEffect": {"period": 3, "scale": 2.8, "brushType": "stroke"},
                           "showEffectOn": "render",
                           "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})

        # Legenda dual
        c_l, c_r = st.columns(2)
        c_l.markdown(
            "<div style='text-align:center;padding:8px;background:#fef2f2;"
            "border-left:4px solid #dc2626;border-radius:6px;'>"
            "<b style='color:#dc2626;'>📋 Linha superior = Notas Abertas</b><br>"
            "<span style='color:#6b7280;font-size:12px;'>diagnóstico — o que atacar</span></div>",
            unsafe_allow_html=True,
        )
        c_r.markdown(
            "<div style='text-align:center;padding:8px;background:#f0fdf4;"
            "border-left:4px solid #16a34a;border-radius:6px;'>"
            "<b style='color:#16a34a;'>✅ Linha inferior = Notas Concluídas</b><br>"
            "<span style='color:#6b7280;font-size:12px;'>histórico — o que foi resolvido</span></div>",
            unsafe_allow_html=True,
        )

        qtd_a = len(df_a)
        qtd_c = len(df_c)
        st.markdown(
            f"<div style='text-align:center;font-size:17px;margin:8px 0;color:#1f2937;'>"
            f"<b>Matriz {trecho_view}</b> — "
            f"<span style='color:#dc2626;font-weight:600;'>📋 {qtd_a:,} abertas</span>"
            f" &nbsp;×&nbsp; "
            f"<span style='color:#16a34a;font-weight:600;'>✅ {qtd_c:,} concluídas</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    else:
        pn, pp, ag, kmm, kmx = _construir_serie(
            df_trecho, bin_km, y_offset=0, label=f"📊 {trecho_view}"
        )
        km_min_g = kmm if (kmm is not None and pd.notna(kmm)) else 0.0
        km_max_g = kmx if (kmx is not None and pd.notna(kmx)) else 100.0
        if len(ag):
            score_max_g = float(ag["score_total"].max())

        series.append({
            "name": "Via", "type": "line",
            "data": [[km_min_g, 0], [km_max_g, 0]],
            "lineStyle": {"color": "#374151", "width": 3},
            "symbol": "none", "silent": True, "tooltip": {"show": False},
        })
        if pn:
            series.append({"name": "Notas", "type": "scatter", "data": pn,
                           "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5, "opacity": 0.85}})
        if pp:
            series.append({"name": "🔥 Hot-spots críticos", "type": "effectScatter", "data": pp,
                           "rippleEffect": {"period": 3, "scale": 2.8, "brushType": "stroke"},
                           "showEffectOn": "render",
                           "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})

        st.markdown(
            f"<div style='text-align:center;font-size:17px;margin:8px 0;color:#1f2937;'>"
            f"<b>Matriz {trecho_view}</b> — {len(df_trecho):,} notas distribuídas"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Opções ECharts ─────────────────────────────────────────────────────
    y_range = 2.5 if modo_dual else 1.2

    option = {
        "tooltip": {
            "trigger": "item",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": "#1e3a5f", "borderWidth": 2,
            "padding": [10, 14],
            "extraCssText": (
                "box-shadow:0 6px 20px rgba(0,0,0,0.15);"
                "border-radius:10px;max-width:320px;"
            ),
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            "formatter": JsCode(
                "function(params){ return params.data.tooltipHTML || ''; }"
            ).js_code,
        },
        "visualMap": {
            "min": 0,
            "max": float(score_max_g) if score_max_g > 0 else 100,
            "dimension": 2, "show": True, "orient": "vertical",
            "right": 10, "top": "middle",
            "itemHeight": 120, "itemWidth": 14, "calculable": True,
            "text": ["Crítico", "OK"],
            "textStyle": {"color": "#1f2937", "fontSize": 11},
            "inRange": {
                "color": ["#16a34a", "#84cc16", "#eab308", "#f59e0b", "#dc2626"]
            },
        },
        "grid": {
            "left": 50, "right": 90,
            "top": 20, "bottom": 80,
            "containLabel": True,
        },
        "xAxis": {
            "type": "value",
            "name": "Quilometragem (KM)",
            "nameLocation": "middle", "nameGap": 32,
            "nameTextStyle": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
            "axisLine":  {"lineStyle": {"color": "#9ca3af"}},
            "axisLabel": {"color": "#374151", "fontSize": 11},
            "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}},
        },
        "yAxis": {
            "type": "value",
            "min": -y_range, "max": y_range,
            "show": False,
            "axisLine":  {"show": False},
            "splitLine": {"show": False},
        },
        "dataZoom": [
            {
                "type": "slider", "show": True, "xAxisIndex": [0],
                "bottom": 15, "height": 22,
                "borderColor":    "#d1d5db",
                "fillerColor":    "rgba(30,58,95,0.15)",
                "handleStyle":    {"color": "#1e3a5f"},
                "moveHandleStyle":{"color": "#1e3a5f"},
                "textStyle":      {"color": "#374151", "fontSize": 10},
            },
            {"type": "inside", "xAxisIndex": [0]},
        ],
        "series": series,
    }

    option_safe = _sanitize(option)
    altura = 460 if modo_dual else 380

    st_echarts(
        options=option_safe,
        height=f"{altura}px",
        key=f"unifilar_{trecho_view}_{str(modo_dual)}",
    )

    # ── Métricas abaixo do gráfico ─────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    extensao = (km_max_g - km_min_g) if km_max_g > km_min_g else 0
    c1.metric("📍 Extensão", f"{extensao:.1f} km")
    c2.metric(
        "📊 Densidade",
        f"{len(df_trecho) / max(extensao, 1):.1f} notas/km",
    )

    df_trecho["_bin"] = (df_trecho["km_real"] // bin_km) * bin_km
    agreg_tot = df_trecho.groupby("_bin")["score"].sum()
    if len(agreg_tot):
        hotspot = agreg_tot.idxmax()
        c3.metric("🎯 Hot-spot principal", f"KM {hotspot:.1f}")
    else:
        c3.metric("🎯 Hot-spot principal", "—")

    if "lead_time_dias" in df_trecho.columns and df_trecho["lead_time_dias"].notna().any():
        lt = df_trecho["lead_time_dias"].dropna().mean()
        c4.metric("⏱️ Lead time médio", f"{lt:.0f} dias")
    else:
        c4.metric("⏱️ Lead time médio", "—")
