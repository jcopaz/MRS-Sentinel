# =============================================================================
# components/unifilar.py — Unifilar ECharts (KM Real + effectScatter)
# Sprint 3 (rev.3) — MRS Sentinel
#
# FIEL AO app1.py:
#   • KM real no eixo X (fallback sequencial quando km_real ausente)
#   • effectScatter pulsante nos top 10% por score
#   • visualMap score → cor (verde → vermelho)
#   • dataZoom slider + scroll do mouse
#   • Tooltip HTML rico: KM, notas, score, pátio, defeitos
#   • Modo Dual (Abertas × Concluídas) quando coluna origem_base disponível
#
# Exporta:
#   construir_serie_unifilar(df, bin_km, y_offset, label)
#   render_unifilar(df, bin_km, gerencia)
#
# Sessão 1: Imports & constantes
# Sessão 2: construir_serie_unifilar()
# Sessão 3: render_unifilar()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import math
import streamlit as st
import pandas as pd
import numpy as np

try:
    from streamlit_echarts import st_echarts, JsCode
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

import plotly.graph_objects as go

from core.glossarios import nome_ramal

COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_CRIT     = "#dc2626"
COR_OK       = "#16a34a"
COR_WARN     = "#f59e0b"
# endregion


# region ====================== SESSÃO 2: construir_serie_unifilar() ============

def _top5_defeitos(x):
    vc = x.dropna().value_counts().head(5)
    if len(vc) == 0:
        return "—"
    return "<br/>".join(
        [f"&nbsp;&nbsp;• {d} <span style='color:#9ca3af;'>({n})</span>"
         for d, n in vc.items()]
    )


def _patios_unicos(x):
    valores = [v for v in x.dropna().unique() if str(v).strip()]
    return ", ".join(sorted(valores)) if valores else "—"


def _top3_inspecoes(x):
    vc = x.dropna().value_counts().head(3)
    vc = vc[vc.index.astype(str).str.strip() != ""]
    return ", ".join([str(t) for t in vc.index]) if len(vc) > 0 else "—"


def construir_serie_unifilar(df_base: pd.DataFrame, bin_km: float,
                              y_offset: float = 0, label: str = "") -> tuple:
    """
    Agrega notas em bins de KM e retorna pontos normais e pulsantes.
    FIEL AO app1.py — mesma lógica de agregação, tamanho e limiar pulsante.

    Returns:
        (pontos_normais, pontos_pulsantes, agreg_df, km_min, km_max)
    """
    if len(df_base) == 0:
        return [], [], pd.DataFrame(), None, None

    df_t = df_base.copy()

    # Detecta colunas (suporta naming do app1 e do Sentinel)
    col_nota   = "nota"       if "nota"       in df_t.columns else (
                 "numero_nota" if "numero_nota" in df_t.columns else None)
    col_origem = "origem"      if "origem"      in df_t.columns else None
    col_sub    = "sub_trecho"  if "sub_trecho"  in df_t.columns else (
                 "trecho"      if "trecho"      in df_t.columns else None)
    col_def    = "defeito_legivel" if "defeito_legivel" in df_t.columns else (
                 "familia_defeito" if "familia_defeito" in df_t.columns else None)
    col_tipo   = "tipo_atividade" if "tipo_atividade" in df_t.columns else None
    col_lt     = "lead_time_dias" if "lead_time_dias" in df_t.columns else None

    if "score"      not in df_t.columns: df_t["score"]      = 1.0
    if "prioridade" not in df_t.columns: df_t["prioridade"] = "3-Média"

    df_t["bin_km"] = (df_t["km_real"] // bin_km) * bin_km

    # Dicionário de agregação
    agg_dict = {}
    if col_nota: agg_dict["qtd_notas"] = (col_nota, "count")
    else:        agg_dict["qtd_notas"] = ("score",  "count")
    agg_dict["score_total"] = ("score", "sum")
    agg_dict["score_medio"] = ("score", "mean")
    agg_dict["prio_1"] = ("prioridade", lambda x: (x == "1-Muito alta").sum())
    agg_dict["prio_2"] = ("prioridade", lambda x: (x == "2-Alta").sum())
    if col_origem: agg_dict["patios"]      = (col_origem, _patios_unicos)
    if col_sub:    agg_dict["sub_trechos"] = (col_sub,    _patios_unicos)
    if col_def:    agg_dict["defeitos"]    = (col_def,    _top5_defeitos)
    if col_tipo:   agg_dict["tipos_insp"] = (col_tipo,   _top3_inspecoes)
    if col_lt:     agg_dict["lt_medio"]   = (col_lt,
                                             lambda x: x.dropna().mean()
                                             if x.dropna().any() else None)

    agreg = df_t.groupby("bin_km").agg(**agg_dict).reset_index()
    if len(agreg) == 0:
        return [], [], pd.DataFrame(), None, None

    qtd_max   = agreg["qtd_notas"].max()
    score_max = agreg["score_total"].max()

    # Top 10% → pulsante (igual app1)
    limiar = agreg["score_total"].quantile(0.90) if len(agreg) >= 10 else score_max

    def calc_tamanho(qtd):
        return 12 + (qtd / qtd_max) * 43   # 12–55 px (igual app1)

    pontos_normais   = []
    pontos_pulsantes = []

    for _, row in agreg.iterrows():
        tamanho = calc_tamanho(row["qtd_notas"])

        lt_txt = (
            f"⏱️ Lead time médio: <b>{row['lt_medio']:.0f} dias</b><br/>"
            if "lt_medio" in row.index and pd.notna(row.get("lt_medio")) else ""
        )
        patios_txt  = row.get("patios",      "—")
        subtrc_txt  = row.get("sub_trechos", "—")
        def_txt     = row.get("defeitos",    "—")
        tipo_txt    = row.get("tipos_insp",  "—")

        # Tooltip HTML idêntico ao app1
        hover = (
            f"<div style='min-width:220px;'>"
            f"<div style='font-size:13px;color:#9ca3af;margin-bottom:4px;'>{label}</div>"
            f"<div style='font-size:15px;font-weight:700;color:#1e3a5f;margin-bottom:6px;'>"
            f"KM {row['bin_km']:.1f} → {row['bin_km']+bin_km:.1f}</div>"
            f"<hr style='border:0;border-top:1px solid #e5e7eb;margin:6px 0;'/>"
            f"📋 <b>{row['qtd_notas']}</b> notas<br/>"
            f"⚡ Score: <b>{row['score_total']:.0f}</b><br/>"
            f"🔴 Muito alta: <b>{row['prio_1']}</b> &nbsp;|&nbsp; "
            f"🟠 Alta: <b>{row['prio_2']}</b><br/>"
            f"{lt_txt}"
            f"📍 Pátio(s): <b>{patios_txt}</b><br/>"
            f"🚂 Trecho(s): <b>{subtrc_txt}</b><br/>"
            f"🔍 Inspeção(ões): <b>{tipo_txt}</b><br/>"
            f"<div style='margin-top:6px;font-size:12px;color:#6b7280;'>"
            f"<b>Top defeitos:</b></div>"
            f"<div style='font-size:12px;'>{def_txt}</div>"
            f"</div>"
        )

        ponto = {
            "value": [
                float(row["bin_km"] + bin_km / 2),
                y_offset,
                float(row["score_total"]),
                int(row["qtd_notas"]),
            ],
            "symbolSize": tamanho,
            "tooltipHTML": hover,
        }

        if row["score_total"] >= limiar:
            pontos_pulsantes.append(ponto)
        else:
            pontos_normais.append(ponto)

    km_min = float(agreg["bin_km"].min()) if len(agreg) else None
    km_max = float(agreg["bin_km"].max() + bin_km) if len(agreg) else None
    return pontos_normais, pontos_pulsantes, agreg, km_min, km_max

# endregion


# region ====================== SESSÃO 3: render_unifilar() ====================

def _sanitize(obj):
    """Remove Infinity/NaN do option dict — idêntico ao app1."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return 0
    return obj


def _criar_km_sequencial(df: pd.DataFrame, col_ramal: str,
                          bin_km: float = 0.5) -> pd.DataFrame:
    """
    KM fictício quando não há coluna km_real.
    Cada pátio único = posição sequencial × (bin_km × 4).
    Sprint 6 substituirá pelo KM real do Supabase.
    """
    df = df.copy()
    if "origem" in df.columns:
        df["km_real"] = df.groupby(col_ramal)["origem"].transform(
            lambda x: pd.Categorical(x, categories=x.unique()).codes.astype(float)
            * bin_km * 4
        )
    else:
        df["km_real"] = pd.Series(range(len(df)), dtype=float) * bin_km
    return df


def render_unifilar(df: pd.DataFrame, bin_km: float = 0.5,
                    gerencia: str = "SP"):
    """
    Renderiza o Unifilar ECharts — fiel ao app1.py.

    Adapta nomes de colunas do Sentinel para o padrão do app1:
      numero_nota  → nota
      ramal        → trecho (agrupador de Matriz)
      trecho       → sub_trecho (par Origem-Destino)
      familia_defeito → defeito_legivel

    Args:
        df:      DataFrame filtrado (todas as notas da gerência)
        bin_km:  janela de agrupamento (km) — vem do slider na sidebar
        gerencia: 'SP', 'VP' ou 'GERAL'
    """
    if df.empty:
        st.info("Sem dados para o unifilar.")
        return

    df_u = df.copy()

    # ── Normaliza colunas ────────────────────────────────────────────────────
    if "nota" not in df_u.columns and "numero_nota" in df_u.columns:
        df_u["nota"] = df_u["numero_nota"]

    # Ramal = agrupador de Matriz (trecho no app1)
    col_matriz = "ramal" if "ramal" in df_u.columns else (
                 "trecho" if "trecho" in df_u.columns else None)

    # sub_trecho = par Origem-Destino
    if "sub_trecho" not in df_u.columns and "trecho" in df_u.columns:
        df_u["sub_trecho"] = df_u["trecho"]

    # defeito_legivel
    if "defeito_legivel" not in df_u.columns:
        for c in ["familia_defeito", "codigo_defeito", "tipo_anomalia"]:
            if c in df_u.columns:
                df_u["defeito_legivel"] = df_u[c]
                break
        else:
            df_u["defeito_legivel"] = "—"

    if "score" not in df_u.columns:
        df_u["score"] = 1.0

    # ── KM real (ou sequencial) ───────────────────────────────────────────────
    if "km_real" not in df_u.columns or df_u["km_real"].isna().all():
        df_u = _criar_km_sequencial(df_u, col_matriz or "ramal", bin_km)
        km_ficticio = True
    else:
        km_ficticio = False

    # ── Origem base (para Modo Dual) ──────────────────────────────────────────
    if "origem_base" not in df_u.columns:
        if "status_amigavel" in df_u.columns:
            df_u["origem_base"] = df_u["status_amigavel"].map(
                {"Aberto": "Abertas", "Encerrado": "Concluídas"}
            ).fillna("Abertas")
        else:
            df_u["origem_base"] = "Abertas"

    # ── Filtra notas com KM e matriz ──────────────────────────────────────────
    df_unifilar = df_u.dropna(subset=["km_real"]).copy()
    if col_matriz:
        df_unifilar = df_unifilar.dropna(subset=[col_matriz])

    if len(df_unifilar) == 0:
        st.warning(
            "⚠️ Nenhuma nota com KM identificado. "
            "Tente liberar mais filtros ou aguardar Sprint 6 (KM real)."
        )
        return

    if km_ficticio:
        st.caption(
            "ℹ️ **KM real não disponível** — posição sequencial por pátio. "
            "Sprint 6 substituirá por KM real."
        )

    # ── Seleciona Matriz (Ramal) ──────────────────────────────────────────────
    bases_disponiveis  = sorted(df_unifilar["origem_base"].unique())
    modo_dual_possivel = len(bases_disponiveis) == 2
    matrizes = sorted(df_unifilar[col_matriz].dropna().unique())                if col_matriz else ["Geral"]

    col_modo, col_ramal_sel = st.columns([1, 3])

    with col_modo:
        if modo_dual_possivel:
            modo_raw = st.radio(
                "🎬 Modo:",
                ["🎯 Dual", "📊 Empilhado"],
                horizontal=False,
                help="Dual = Abertas × Concluídas em 2 linhas.",
                key=f"modo_unif_{gerencia}",
            )
            modo_view = "Dual" if "Dual" in modo_raw else "Empilhado"
        else:
            modo_view = "Empilhado"

    with col_ramal_sel:
        if len(matrizes) == 1:
            ramal_view = matrizes[0]
            label_m = nome_ramal(ramal_view, "completo")                       if col_matriz == "ramal" else str(ramal_view)
            st.markdown(
                f"<div style='padding:8px 12px;background:#1e3a5f;color:#fff;"
                f"border-radius:8px;text-align:center;margin-top:28px;'>"
                f"🚂 Visualizando: <b>{label_m}</b></div>",
                unsafe_allow_html=True,
            )
        else:
            opcoes = []
            for m in matrizes:
                qtd = len(df_unifilar[df_unifilar[col_matriz] == m])                       if col_matriz else len(df_unifilar)
                lbl = nome_ramal(m, "completo")                       if col_matriz == "ramal" else str(m)
                opcoes.append(f"{lbl} ({qtd:,})")

            escolha = st.radio(
                "🚂 Ramal:",
                opcoes,
                horizontal=True,
                key=f"ramal_unif_{gerencia}",
                help="Cada ramal gera seu próprio unifilar.",
            )
            ramal_view = matrizes[opcoes.index(escolha)]

    # Filtra pelo ramal
    if col_matriz and len(matrizes) > 1:
        df_t_completo = df_unifilar[df_unifilar[col_matriz] == ramal_view].copy()
    else:
        df_t_completo = df_unifilar.copy()

    label_ramal_final = nome_ramal(ramal_view, "completo")                         if col_matriz == "ramal" else str(ramal_view)

    st.caption(
        f"Cada bolha = agrupamento de notas em **{bin_km*1000:.0f} m**. "
        f"**Tamanho** = qtd de notas | **Cor** = score de criticidade | "
        f"**Bolhas pulsantes** = top 10% mais críticos. "
        f"Use a barra inferior para **zoom** no KM."
    )

    # ── Monta séries ──────────────────────────────────────────────────────────
    series           = []
    km_min_global    = float("inf")
    km_max_global    = float("-inf")
    score_max_global = 0

    if modo_dual_possivel and modo_view == "Dual":
        df_a = df_t_completo[df_t_completo["origem_base"] == "Abertas"]
        df_c = df_t_completo[df_t_completo["origem_base"] == "Concluídas"]

        pn_a, pp_a, agreg_a, kma_min, kma_max = construir_serie_unifilar(
            df_a, bin_km, y_offset=1, label="📋 Abertas (Diagnóstico)"
        )
        pn_c, pp_c, agreg_c, kmc_min, kmc_max = construir_serie_unifilar(
            df_c, bin_km, y_offset=-1, label="✅ Concluídas (Realizado)"
        )

        for v in [kma_min, kmc_min]:
            if v is not None and pd.notna(v):
                km_min_global = min(km_min_global, v)
        for v in [kma_max, kmc_max]:
            if v is not None and pd.notna(v):
                km_max_global = max(km_max_global, v)
        if len(agreg_a):
            score_max_global = max(score_max_global,
                                   float(agreg_a["score_total"].max()))
        if len(agreg_c):
            score_max_global = max(score_max_global,
                                   float(agreg_c["score_total"].max()))

        # Linhas da via (Abertas = y+1, Concluídas = y-1)
        series += [
            {"name": "Via (Abertas)", "type": "line",
             "data": [[km_min_global, 1], [km_max_global, 1]],
             "lineStyle": {"color": "#374151", "width": 3},
             "symbol": "none", "silent": True, "tooltip": {"show": False}},
            {"name": "Via (Concluídas)", "type": "line",
             "data": [[km_min_global, -1], [km_max_global, -1]],
             "lineStyle": {"color": "#374151", "width": 3},
             "symbol": "none", "silent": True, "tooltip": {"show": False}},
        ]
        if pn_a:
            series.append({
                "name": "📋 Abertas", "type": "scatter", "data": pn_a,
                "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5,
                              "opacity": 0.85}})
        if pn_c:
            series.append({
                "name": "✅ Concluídas", "type": "scatter", "data": pn_c,
                "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5,
                              "opacity": 0.85}})
        # effectScatter — pulsante (fiel ao app1: period=3, scale=2.8)
        if pp_a:
            series.append({
                "name": "🔥 Abertas Críticos", "type": "effectScatter",
                "data": pp_a,
                "rippleEffect": {"period": 3, "scale": 2.8,
                                 "brushType": "stroke"},
                "showEffectOn": "render",
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})
        if pp_c:
            series.append({
                "name": "🔥 Concluídas Críticos", "type": "effectScatter",
                "data": pp_c,
                "rippleEffect": {"period": 3, "scale": 2.8,
                                 "brushType": "stroke"},
                "showEffectOn": "render",
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})

        qtd_a = len(df_a); qtd_c = len(df_c)
        st.markdown(
            f"<div style='text-align:center;font-size:17px;"
            f"margin-bottom:8px;color:#1f2937;'>"
            f"<b>Ramal {label_ramal_final}</b> — "
            f"<span style='color:#dc2626;font-weight:600;'>"
            f"📋 {qtd_a:,} abertas</span>"
            f" &nbsp;×&nbsp; "
            f"<span style='color:#16a34a;font-weight:600;'>"
            f"✅ {qtd_c:,} concluídas</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        # Empilhado / base única
        pn, pp, agreg, kmm, kmx = construir_serie_unifilar(
            df_t_completo, bin_km, y_offset=0, label=f"📊 {label_ramal_final}"
        )
        if kmm is not None and pd.notna(kmm): km_min_global = kmm
        if kmx is not None and pd.notna(kmx): km_max_global = kmx
        if km_min_global == float("inf"):  km_min_global = 0.0
        if km_max_global == float("-inf"): km_max_global = 100.0
        if len(agreg):
            score_max_global = float(agreg["score_total"].max())

        series.append({
            "name": "Via", "type": "line",
            "data": [[km_min_global, 0], [km_max_global, 0]],
            "lineStyle": {"color": "#374151", "width": 3},
            "symbol": "none", "silent": True, "tooltip": {"show": False},
        })
        if pn:
            series.append({
                "name": "Notas", "type": "scatter", "data": pn,
                "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5,
                              "opacity": 0.85}})
        # effectScatter pulsante — fiel ao app1
        if pp:
            series.append({
                "name": "🔥 Hot-spots críticos", "type": "effectScatter",
                "data": pp,
                "rippleEffect": {"period": 3, "scale": 2.8,
                                 "brushType": "stroke"},
                "showEffectOn": "render",
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})

        st.markdown(
            f"<div style='text-align:center;font-size:17px;"
            f"margin-bottom:8px;color:#1f2937;'>"
            f"<b>Ramal {label_ramal_final}</b> — "
            f"{len(df_t_completo):,} notas distribuídas</div>",
            unsafe_allow_html=True,
        )

    if km_min_global == float("inf"):  km_min_global = 0.0
    if km_max_global == float("-inf"): km_max_global = 100.0

    # ── Fallback Plotly ───────────────────────────────────────────────────────
    if not ECHARTS_OK:
        fig = go.Figure()
        for s in series:
            if s["type"] in ("scatter", "effectScatter"):
                xs = [p["value"][0] for p in s["data"]]
                ys = [p["value"][1] for p in s["data"]]
                ss = [p["symbolSize"] for p in s["data"]]
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="markers", name=s["name"],
                    marker=dict(size=[sz / 3 for sz in ss]),
                ))
            elif s["type"] == "line":
                fig.add_trace(go.Scatter(
                    x=[p[0] for p in s["data"]],
                    y=[p[1] for p in s["data"]],
                    mode="lines", name=s["name"],
                    line=dict(color="#374151", width=2),
                ))
        fig.update_layout(
            height=380, plot_bgcolor="white", paper_bgcolor="white",
            xaxis_title="KM", margin=dict(l=50, r=20, t=20, b=60),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("streamlit-echarts não instalado — usando Plotly")
        return

    # ── Opção ECharts (fiel ao app1) ──────────────────────────────────────────
    option = {
        "tooltip": {
            "trigger": "item",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": COR_PRIMARIA, "borderWidth": 2,
            "padding": [10, 14],
            "extraCssText": (
                "box-shadow:0 6px 20px rgba(0,0,0,0.15);"
                "border-radius:10px;max-width:320px;"
            ),
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            # Tooltip usa a prop tooltipHTML de cada ponto — idêntico ao app1
            "formatter": JsCode(
                "function(params){ return params.data.tooltipHTML || ''; }"
            ).js_code,
        },
        # visualMap: score → cor (verde → vermelho) — idêntico ao app1
        "visualMap": {
            "min": 0,
            "max": float(score_max_global) if score_max_global > 0 else 100,
            "dimension": 2,
            "show": True, "orient": "vertical",
            "right": 10, "top": "middle",
            "itemHeight": 120, "itemWidth": 14,
            "calculable": True,
            "text": ["Crítico", "OK"],
            "textStyle": {"color": "#1f2937", "fontSize": 11},
            "inRange": {
                "color": ["#16a34a", "#84cc16", "#eab308",
                          "#f59e0b", "#dc2626"]
            },
        },
        "grid": {
            "left": 50, "right": 90, "top": 20, "bottom": 80,
            "containLabel": True,
        },
        "xAxis": {
            "type": "value",
            "name": "Quilometragem (KM)" if not km_ficticio
                    else "Posição sequencial",
            "nameLocation": "middle", "nameGap": 32,
            "nameTextStyle": {
                "color": "#374151", "fontSize": 12, "fontWeight": "bold"
            },
            "axisLine":  {"lineStyle": {"color": "#9ca3af"}},
            "axisLabel": {"color": "#374151", "fontSize": 11},
            "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}},
        },
        "yAxis": {
            "type": "value",
            "min": -2.5 if modo_dual_possivel and modo_view == "Dual" else -1.2,
            "max":  2.5 if modo_dual_possivel and modo_view == "Dual" else  1.2,
            "show": False,
            "axisLine": {"show": False}, "splitLine": {"show": False},
        },
        # dataZoom: slider + scroll do mouse — idêntico ao app1
        "dataZoom": [
            {
                "type": "slider", "show": True, "xAxisIndex": [0],
                "bottom": 15, "height": 22,
                "borderColor": "#d1d5db",
                "fillerColor": "rgba(30,58,95,0.15)",
                "handleStyle": {"color": COR_PRIMARIA},
                "moveHandleStyle": {"color": COR_PRIMARIA},
                "textStyle": {"color": "#374151", "fontSize": 10},
            },
            {"type": "inside", "xAxisIndex": [0]},
        ],
        "series": series,
    }

    option_safe = _sanitize(option)
    altura = 460 if modo_dual_possivel and modo_view == "Dual" else 380
    st_echarts(
        options=option_safe,
        height=f"{altura}px",
        key=f"unif_{gerencia}_{str(ramal_view)}",
    )

# endregion

# Alias de compatibilidade — gerencia_sp/vp/geral importam render_unifilar_dual
render_unifilar_dual = render_unifilar
