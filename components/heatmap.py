# =============================================================================
# components/heatmap.py — Heatmap, Ranking e Série Temporal
# Sprint 3 (rev.3) — MRS Sentinel
#
# FIEL AO app1.py:
#   • Heatmap: ECharts + visualMap (não Plotly) — fill_value=0, branco=mín
#   • Temporal: ECharts xAxis category "jan/24", granul. por dimensão
#   • Ranking: tabela + barras Plotly horizontais
#
# Sessão 1: Imports & constantes
# Sessão 2: render_heatmap()
# Sessão 3: render_ranking()
# Sessão 4: render_serie_temporal()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

try:
    from streamlit_echarts import st_echarts, JsCode
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

from core.glossarios import nome_ramal

COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_EE       = "#7c3aed"
COR_CRIT     = "#dc2626"
COR_WARN     = "#f59e0b"
COR_OK       = "#16a34a"
COR_NA       = "#e5e7eb"

PALETTE = [
    "#1e3a5f","#dc2626","#f59e0b","#16a34a","#7c3aed",
    "#0891b2","#ea580c","#84cc16","#db2777","#0284c7",
    "#65a30d","#9333ea","#b45309","#0d9488","#475569",
]

MESES_PT = {
    1:"jan",2:"fev",3:"mar",4:"abr",
    5:"mai",6:"jun",7:"jul",8:"ago",
    9:"set",10:"out",11:"nov",12:"dez",
}


def _hex_rgba(hex_cor: str, opacidade: float = 0.10) -> str:
    """Converte #rrggbb para rgba() — Plotly não aceita hex+alpha."""
    h = hex_cor.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{opacidade})"

# endregion


# region ====================== SESSÃO 2: render_heatmap() =====================

def render_heatmap(df: pd.DataFrame, gerencia: str = "SP"):
    """
    Heatmap Pátio × Família — ECharts + visualMap interativo.

    FIEL AO app1.py:
    - fill_value=0: células sem nota ficam com valor 0
    - visualMap: cor mínima #f0fdf4 (branco) → 0 = branco, escala → vermelho
    - Labels dentro de cada célula (ocultas se valor=0, via JsCode)
    - splitArea nos eixos → grade visual entre células
    - Tooltip rico: Pátio + Família + Valor
    """
    col_patio   = "origem"
    col_familia = (
        "familia_defeito" if "familia_defeito" in df.columns else
        "familia_cod"     if "familia_cod"     in df.columns else
        None
    )

    if df.empty or col_patio not in df.columns or col_familia is None:
        st.info("Dados insuficientes para o heatmap (necessário: origem, familia_defeito).")
        return

    c_metr, c_top = st.columns([1, 2])
    with c_metr:
        metrica = st.radio(
            "📊 Métrica:",
            ["Quantidade de notas", "Score de criticidade"],
            horizontal=False,
            key=f"heat_metrica_{gerencia}",
        )
    with c_top:
        top_n_patios = st.slider(
            "Top N pátios (por volume):",
            min_value=10, max_value=80, value=30, step=5,
            key=f"heat_top_{gerencia}",
            help="Limita a visualização aos pátios com mais notas.",
        )

    valor_col = ("numero_nota" if "numero_nota" in df.columns else col_patio) \
                if metrica == "Quantidade de notas" else "score"
    agg_func  = "count" if metrica == "Quantidade de notas" else "sum"

    if metrica == "Score de criticidade" and "score" not in df.columns:
        st.warning("Coluna 'score' não encontrada — usando contagem de notas.")
        valor_col, agg_func = col_patio, "count"

    # fill_value=0 (igual app1) — visualMap mapeia 0 para branco automaticamente
    pivot = df.pivot_table(
        index=col_patio,
        columns=col_familia,
        values=valor_col,
        aggfunc=agg_func,
        fill_value=0,
    )

    if pivot.empty:
        st.info("Sem dados suficientes para gerar o heatmap.")
        return

    pivot["__total__"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("__total__", ascending=False).drop(columns="__total__")
    pivot = pivot.head(top_n_patios)

    patios_lista   = pivot.index.tolist()
    familias_lista = pivot.columns.tolist()

    heat_data   = []
    valor_max   = 0
    valor_total = pivot.values.sum()

    for y_idx, patio in enumerate(patios_lista):
        for x_idx, fam in enumerate(familias_lista):
            v = int(pivot.loc[patio, fam])
            heat_data.append([x_idx, y_idx, v])
            if v > valor_max:
                valor_max = v

    if not ECHARTS_OK:
        # Fallback Plotly quando streamlit-echarts não instalado
        matrix = pivot.copy().astype(float)
        matrix[matrix == 0] = np.nan
        fig = go.Figure(data=go.Heatmap(
            z=matrix.values.tolist(),
            x=familias_lista, y=patios_lista,
            colorscale=[[0,"#f0fdf4"],[0.4,COR_OK],[0.7,COR_WARN],[1,COR_CRIT]],
            hoverongaps=False, xgap=2, ygap=2,
        ))
        fig.update_layout(
            plot_bgcolor=COR_NA,
            height=max(350, len(patios_lista)*26+120),
            margin=dict(l=90,r=20,t=50,b=100),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("streamlit-echarts não instalado — usando Plotly")
        return

    # Tooltip JS rico (igual app1)
    tooltip_js = JsCode("""
        function(p) {
            var familias = """ + str(familias_lista) + """;
            var patios   = """ + str(patios_lista)   + """;
            var val = p.value[2];
            return (
                "<div style='min-width:180px;'>" +
                "<div style='font-size:13px; color:#9ca3af;'>Pátio</div>" +
                "<div style='font-size:15px; font-weight:700; color:#1e3a5f;'>" +
                patios[p.value[1]] + "</div>" +
                "<hr style='border:0; border-top:1px solid #e5e7eb; margin:6px 0;'/>" +
                "🛠️ Família: <b>" + familias[p.value[0]] + "</b><br/>" +
                "📋 Valor: <b>" + val.toLocaleString('pt-BR') + "</b>" +
                "</div>"
            );
        }
    """).js_code

    opt_heat = {
        "tooltip": {
            "position": "top",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": "#1e3a5f", "borderWidth": 2,
            "padding": [10, 14],
            "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            "formatter": tooltip_js,
        },
        "grid": {
            "height": "78%", "top": "8%",
            "left": 80, "right": 30, "bottom": 40,
            "containLabel": True,
        },
        "xAxis": {
            "type": "category",
            "data": familias_lista,
            "position": "top",
            "splitArea": {"show": True},
            "axisLabel": {
                "color": "#1f2937", "fontSize": 11, "fontWeight": "bold",
                "rotate": 0,
            },
            "axisLine": {"lineStyle": {"color": "#9ca3af"}},
        },
        "yAxis": {
            "type": "category",
            "data": patios_lista,
            "splitArea": {"show": True},
            "axisLabel": {"color": "#1f2937", "fontSize": 11, "fontWeight": "bold"},
            "axisLine": {"lineStyle": {"color": "#9ca3af"}},
            "inverse": True,
        },
        # visualMap: escala de cores interativa — 0 = branco, max = vermelho
        "visualMap": {
            "min": 0,
            "max": max(valor_max, 1),
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 5,
            "itemWidth": 18,
            "itemHeight": 200,
            "text": ["Alto", "Baixo"],
            "textStyle": {"color": "#1f2937"},
            "inRange": {
                "color": [
                    "#f0fdf4","#bbf7d0","#86efac",
                    "#fde68a","#fbbf24","#f59e0b",
                    "#f97316","#ea580c","#dc2626","#991b1b",
                ]
            },
        },
        "series": [{
            "name": metrica,
            "type": "heatmap",
            "data": heat_data,
            "label": {
                "show": True,
                "color": "#1f2937",
                "fontSize": 10,
                "fontWeight": "bold",
                # Oculta label em células com valor 0 (sem dados)
                "formatter": JsCode(
                    "function(p){ return p.value[2] > 0 ? p.value[2] : ''; }"
                ).js_code,
            },
            "emphasis": {
                "itemStyle": {
                    "shadowBlur": 12,
                    "shadowColor": "rgba(30,58,95,0.5)",
                    "borderColor": "#1e3a5f",
                    "borderWidth": 2,
                }
            },
        }],
    }

    altura_heat = max(450, 28 * len(patios_lista) + 100)
    st_echarts(opt_heat, height=f"{altura_heat}px", key=f"heatmap_{gerencia}")

    # Mini-KPIs (igual app1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📊 Pátios exibidos", f"{len(patios_lista):,}")
    c2.metric("🛠️ Famílias",       f"{len(familias_lista):,}")
    c3.metric(f"📋 Total {metrica.split()[0]}", f"{int(valor_total):,}")
    patio_top = patios_lista[0] if patios_lista else "—"
    valor_top = int(pivot.iloc[0].sum()) if len(pivot) else 0
    c4.metric("🥇 Pátio top", patio_top, f"{valor_top:,} notas")

# endregion


# region ====================== SESSÃO 3: render_ranking() =====================

def render_ranking(df: pd.DataFrame, top_n: int = 10,
                   ordem: str = "Score Total", gerencia: str = "SP"):
    """Ranking de hot-spots por pátio de origem — tabela + barras horizontais."""
    if df.empty or "origem" not in df.columns:
        st.info("Sem dados para o ranking.")
        return

    cnt_col = "numero_nota" if "numero_nota" in df.columns else "origem"
    agg_kw  = {"Qtd. Notas": (cnt_col, "count")}
    if "score"          in df.columns: agg_kw["Score Total"]            = ("score",          "sum")
    if "score"          in df.columns: agg_kw["Score Médio"]            = ("score",          "mean")
    if "lead_time_dias" in df.columns: agg_kw["Lead Time Médio (dias)"] = ("lead_time_dias", "mean")
    if "ramal"          in df.columns: agg_kw["Ramal"]                  = ("ramal",          "first")
    if "familia_defeito" in df.columns:
        agg_kw["Top Família"] = (
            "familia_defeito",
            lambda x: x.value_counts().index[0] if len(x.dropna()) > 0 else "—"
        )

    ranking = (
        df.dropna(subset=["origem"])
        .groupby("origem").agg(**agg_kw)
        .reset_index().rename(columns={"origem": "Pátio"})
    )

    col_ord = {
        "Score Total":            "Score Total",
        "Qtd. Notas":             "Qtd. Notas",
        "Lead Time Médio (dias)": "Lead Time Médio (dias)",
    }.get(ordem, "Score Total")
    if col_ord in ranking.columns:
        ranking = ranking.sort_values(col_ord, ascending=False)

    ranking = ranking.head(top_n).reset_index(drop=True)
    ranking.index += 1
    ranking.insert(0, "Pos.", [{1:"🥇",2:"🥈",3:"🥉"}.get(i, f"#{i}") for i in ranking.index])

    if "Ramal" in ranking.columns:
        ranking["Ramal"] = ranking["Ramal"].apply(lambda s: nome_ramal(s, "completo_sigla"))
    for c in ["Score Total", "Score Médio", "Lead Time Médio (dias)"]:
        if c in ranking.columns:
            ranking[c] = ranking[c].round(1)

    st.markdown(f"**Top {top_n} Hot-spots — {gerencia}** · Ordenado por: {ordem}")

    col_cfg = {}
    if "Score Total" in ranking.columns:
        col_cfg["Score Total"] = st.column_config.ProgressColumn(
            min_value=0, max_value=float(ranking["Score Total"].max()), format="%.1f")
    st.dataframe(ranking, use_container_width=True, hide_index=True, column_config=col_cfg)

    if "Score Total" in ranking.columns and not ranking.empty:
        fig = px.bar(
            ranking.sort_values("Score Total"),
            x="Score Total", y="Pátio", orientation="h",
            color="Score Total",
            color_continuous_scale=[[0,COR_OK],[0.5,COR_WARN],[1,COR_CRIT]],
            text="Score Total",
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            coloraxis_showscale=False,
            height=max(300, top_n * 32),
            margin=dict(l=10, r=60, t=10, b=10),
            font=dict(color="#1f2937", size=11), showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

# endregion


# region ====================== SESSÃO 4: render_serie_temporal() ==============

def render_serie_temporal(df: pd.DataFrame, granularidade: str = "Mensal",
                          metrica: str = "Volume de Notas", gerencia: str = "SP"):
    """
    Série temporal ECharts — FIEL AO app1.py.

    Correções vs versão anterior:
    - xAxis type: "category" com rótulos "jan/24" (não timestamps UNIX)
    - Granularidade por DIMENSÃO dos dados: Ramal/Pátio/Família/Prioridade/Tipo
    - Top N séries configurável; demais → "Outras"
    - Sem linha de tendência (app1 não tem)
    - dataZoom slider + inside (igual app1)
    - Fallback Plotly automático se streamlit-echarts ausente
    """
    if df.empty or "data_nota" not in df.columns:
        st.info("Sem dados temporais disponíveis.")
        return

    df_t = df.copy()
    df_t["data_nota"] = pd.to_datetime(df_t["data_nota"], errors="coerce")
    df_t = df_t.dropna(subset=["data_nota"])
    if df_t.empty:
        st.info("Sem notas com datas válidas.")
        return

    df_t["ano_mes"] = df_t["data_nota"].dt.to_period("M")

    col_gran, col_top = st.columns([2, 1])
    with col_gran:
        granul_serie = st.radio(
            "📐 Detalhar por:",
            ["Total geral","Ramal","Pátio","Família de defeito","Prioridade","Tipo de inspeção"],
            horizontal=True,
            key=f"serie_granul_{gerencia}",
        )
    with col_top:
        top_n_serie = st.slider(
            "Top N séries:", min_value=3, max_value=15, value=8, step=1,
            key=f"serie_top_{gerencia}",
            help="Limita séries para legibilidade. Demais → 'Outras'.",
        )

    mapa_granul = {
        "Total geral":        None,
        "Ramal":              "ramal",
        "Pátio":              "origem",
        "Família de defeito": "familia_defeito",
        "Prioridade":         "prioridade",
        "Tipo de inspeção":   "tipo_atividade",
    }
    col_q = mapa_granul.get(granul_serie)

    if col_q and col_q not in df_t.columns:
        col_q = None
        st.caption(f"Coluna '{mapa_granul[granul_serie]}' não disponível — usando total geral.")

    # ---- Monta séries ----
    if col_q is None:
        serie_total   = df_t.groupby("ano_mes").size().sort_index()
        meses_serie   = serie_total.index.tolist()
        rotulos_serie = [f"{MESES_PT[m.month]}/{str(m.year)[-2:]}" for m in meses_serie]
        vals_serie    = [int(v) for v in serie_total.values]
        total_periodo = int(serie_total.sum())

        series_data = [{
            "name": "Total de notas",
            "type": "line",
            "data": vals_serie,
            "smooth": True,
            "lineStyle": {"color": COR_PRIMARIA, "width": 3},
            "itemStyle": {"color": COR_PRIMARIA},
            "symbol": "circle",
            "symbolSize": 8,
            "areaStyle": {
                "color": {
                    "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                    "colorStops": [
                        {"offset": 0, "color": "rgba(30,58,95,0.35)"},
                        {"offset": 1, "color": "rgba(30,58,95,0.02)"},
                    ],
                }
            },
            "emphasis": {"focus": "series"},
        }]
        legend_data = ["Total de notas"]

    else:
        serie = (
            df_t.groupby(["ano_mes", col_q]).size()
            .unstack(fill_value=0).sort_index()
        )
        totais   = serie.sum(axis=0).sort_values(ascending=False)
        top_cats = totais.head(top_n_serie).index.tolist()
        demais   = [c for c in totais.index if c not in top_cats]
        if demais:
            serie["Outras"] = serie[demais].sum(axis=1)
            serie = serie.drop(columns=demais)
            top_cats.append("Outras")

        meses_serie   = serie.index.tolist()
        rotulos_serie = [f"{MESES_PT[m.month]}/{str(m.year)[-2:]}" for m in meses_serie]
        total_periodo = int(df_t.shape[0])
        series_data   = []
        legend_data   = []

        for idx, cat in enumerate(top_cats):
            cor   = PALETTE[idx % len(PALETTE)] if cat != "Outras" else "#9ca3af"
            label = nome_ramal(cat, "completo_sigla") if col_q == "ramal" else str(cat)
            series_data.append({
                "name": label,
                "type": "line",
                "data": [int(v) for v in serie[cat].values],
                "smooth": True,
                "lineStyle": {"color": cor, "width": 2.5},
                "itemStyle": {"color": cor},
                "symbol": "circle",
                "symbolSize": 6,
                "emphasis": {"focus": "series"},
            })
            legend_data.append(label)

    # ---- Renderiza ----
    if not ECHARTS_OK:
        fig = go.Figure()
        for s in series_data:
            cor = s["lineStyle"]["color"]
            fig.add_trace(go.Scatter(
                x=rotulos_serie, y=s["data"], name=s["name"],
                mode="lines+markers",
                line=dict(color=cor, width=2.5),
                marker=dict(size=6, color=cor),
                fill="tozeroy", fillcolor=_hex_rgba(cor, 0.12),
            ))
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white", height=420,
            hovermode="x unified",
            xaxis=dict(showgrid=False),
            yaxis=dict(title="Qtd de notas", showgrid=True,
                       gridcolor="#f1f5f9", rangemode="tozero"),
            legend=dict(orientation="h", y=1.05, x=1, xanchor="right"),
            margin=dict(l=60,r=20,t=40,b=40),
            font=dict(color="#1f2937", size=11),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("streamlit-echarts não instalado — usando Plotly")
    else:
        opt_serie = {
            "tooltip": {
                "trigger": "axis",
                "backgroundColor": "rgba(255,255,255,0.98)",
                "borderColor": COR_PRIMARIA, "borderWidth": 2,
                "padding": [10, 14],
                "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
                "textStyle": {"color": "#1f2937", "fontSize": 12},
                "axisPointer": {
                    "type": "line",
                    "lineStyle": {"color": COR_PRIMARIA, "type": "dashed"},
                },
            },
            "legend": {
                "data": legend_data,
                "top": 8,
                "textStyle": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
                "itemGap": 18,
            },
            "grid": {
                "left": "3%", "right": "3%", "top": "15%", "bottom": "18%",
                "containLabel": True,
            },
            "xAxis": {
                "type": "category",          # igual app1: não usa timestamps
                "data": rotulos_serie,        # "jan/24", "fev/24" ...
                "axisLabel": {
                    "color": "#374151", "fontSize": 11,
                    "rotate": 35 if len(rotulos_serie) > 10 else 0,
                    "interval": "auto",
                },
                "axisLine": {"lineStyle": {"color": "#9ca3af"}},
                "boundaryGap": False,
            },
            "yAxis": {
                "type": "value",
                "name": "Qtd de notas",
                "nameTextStyle": {"color": "#374151", "fontSize": 11, "fontWeight": "bold"},
                "axisLabel": {"color": "#374151"},
                "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}},
            },
            "dataZoom": [
                {
                    "type": "slider", "show": True, "bottom": 10, "height": 22,
                    "borderColor": "#d1d5db",
                    "fillerColor": "rgba(30,58,95,0.15)",
                    "handleStyle": {"color": COR_PRIMARIA},
                    "textStyle": {"color": "#374151", "fontSize": 10},
                },
                {"type": "inside"},
            ],
            "series": series_data,
        }
        st_echarts(opt_serie, height="500px", key=f"serie_{gerencia}_{granul_serie}")

    # Mini-KPIs (igual app1)
    media_mensal = total_periodo / max(len(meses_serie), 1)
    if len(meses_serie) >= 2:
        primeiro = df_t[df_t["ano_mes"] == meses_serie[0]].shape[0]
        ultimo   = df_t[df_t["ano_mes"] == meses_serie[-1]].shape[0]
        tend_pct = ((ultimo / primeiro - 1) * 100) if primeiro else 0
        tend_emoji = "📈" if tend_pct > 5 else ("📉" if tend_pct < -5 else "➡️")
    else:
        tend_pct, tend_emoji = 0, "➡️"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Total no período", f"{total_periodo:,}")
    c2.metric("📅 Média mensal",     f"{media_mensal:.0f}")
    c3.metric("🗓️ Meses analisados", f"{len(meses_serie)}")
    c4.metric("📊 Tendência", f"{tend_emoji} {abs(tend_pct):.1f}%",
              delta=f"{tend_pct:+.1f}%", delta_color="inverse")

# endregion
