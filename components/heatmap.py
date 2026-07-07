# =============================================================================
# components/heatmap.py — Heatmap, Ranking e Série Temporal
# Sprint 3 (rev.2) — MRS Sentinel
#
# Correções v2:
#   • Heatmap: células vazias = NaN (branco/cinza), NÃO mais 0 verde
#   • Temporal: ECharts com curva suave, área gradiente, dataZoom e tooltip rico
#
# Exporta:
#   render_heatmap()        — Heatmap Pátio × Família (NaN = célula em branco)
#   render_ranking()        — Tabela hot-spots + barras horizontais
#   render_serie_temporal() — Série temporal ECharts (fallback Plotly)
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
import plotly.graph_objects as go
import plotly.express as px

try:
    from streamlit_echarts import st_echarts
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

from core.glossarios import nome_ramal

# Paleta MRS
COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_EE       = "#7c3aed"
COR_CRIT     = "#dc2626"
COR_WARN     = "#f59e0b"
COR_OK       = "#16a34a"
COR_NA       = "#e5e7eb"   # cinza claro para células sem dados


def _hex_rgba(hex_cor: str, opacidade: float = 0.10) -> str:
    """Converte #rrggbb para rgba() — Plotly não aceita hex+alpha."""
    h = hex_cor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{opacidade})"

# endregion


# region ====================== SESSÃO 2: render_heatmap() =====================

def render_heatmap(df: pd.DataFrame, gerencia: str = "SP"):
    """
    Heatmap Pátio x Familia de defeito.

    CORREÇÃO PRINCIPAL: fill_value=np.nan
    Células sem nenhuma nota ficam BRANCAS (sem dado), nao verdes (score=0).

    Args:
        df: DataFrame filtrado com score calculado
        gerencia: 'SP', 'VP' ou 'GERAL'
    """
    # Valida colunas obrigatorias
    col_patio   = "origem"
    col_familia = (
        "familia_defeito" if "familia_defeito" in df.columns else
        "familia_cod"     if "familia_cod"     in df.columns else
        None
    )

    if df.empty or col_patio not in df.columns or col_familia is None or "score" not in df.columns:
        st.info("Dados insuficientes para o heatmap (necessario: origem, familia_defeito, score).")
        return

    # Prepara dados
    df_h = df[[col_patio, col_familia, "score"]].copy()
    df_h = df_h.dropna(subset=[col_patio, col_familia])
    df_h[col_patio]   = df_h[col_patio].astype(str).str.strip()
    df_h[col_familia] = df_h[col_familia].astype(str).str.strip()
    df_h = df_h[(df_h[col_patio] != "") & (df_h[col_familia] != "")]

    if df_h.empty:
        st.info("Nenhuma combinacao Patio x Familia disponivel.")
        return

    # Controles
    c1, c2 = st.columns(2)
    with c1:
        top_p = st.slider("Top N patios (linhas)", 5, 40, 15, 5, key=f"hp_{gerencia}")
    with c2:
        top_f = st.slider("Top N familias (colunas)", 3, 20, 10, 1, key=f"hf_{gerencia}")

    # Seleciona top patios e familias por score total
    patios_top   = df_h.groupby(col_patio)["score"].sum().nlargest(top_p).index.tolist()
    familias_top = df_h.groupby(col_familia)["score"].sum().nlargest(top_f).index.tolist()
    df_h = df_h[df_h[col_patio].isin(patios_top) & df_h[col_familia].isin(familias_top)]

    # Pivot com NaN para celulas vazias (CORRECAO PRINCIPAL)
    matrix = df_h.pivot_table(
        index=col_patio,
        columns=col_familia,
        values="score",
        aggfunc="mean",
        fill_value=np.nan,    # <-- NaN: celula em branco no grafico
    )

    # Ordena patios: mais criticos no topo
    ordem = (
        df_h.groupby(col_patio)["score"].sum()
        .reindex(matrix.index)
        .sort_values(ascending=False)
        .index
    )
    matrix = matrix.reindex(ordem)

    if matrix.empty:
        st.info("Matriz vazia com os filtros atuais.")
        return

    score_max = float(np.nanmax(matrix.values)) if not np.all(np.isnan(matrix.values)) else 1.0

    # Figura Plotly Heatmap
    fig = go.Figure(data=go.Heatmap(
        z=matrix.values.tolist(),
        x=matrix.columns.tolist(),
        y=matrix.index.tolist(),
        colorscale=[
            [0.00, "#ffffff"],   # branco: valor zero (nao deve aparecer com fill_value=NaN)
            [0.01, "#dcfce7"],   # verde muito claro
            [0.40, COR_OK],
            [0.70, COR_WARN],
            [1.00, COR_CRIT],
        ],
        zmin=0,
        zmax=score_max,
        hoverongaps=False,      # NaN nao gera hover
        hovertemplate="<b>Patio:</b> %{y}<br><b>Familia:</b> %{x}<br><b>Score medio:</b> %{z:.1f}<extra></extra>",
        colorbar=dict(
            title=dict(text="Score medio", side="right"),
            thickness=14, len=0.85, tickfont=dict(size=10),
        ),
        xgap=2, ygap=2,        # espaco entre celulas (realca os brancos)
    ))

    # plot_bgcolor = cinza claro: celulas NaN aparecem nessa cor de fundo
    fig.update_layout(
        plot_bgcolor=COR_NA,
        paper_bgcolor="white",
        title=dict(text=f"Heatmap Patio x Familia — {gerencia}",
                   font=dict(size=13, color="#1f2937"), x=0),
        xaxis=dict(title="Familia de Defeito", tickangle=-35, tickfont=dict(size=10)),
        yaxis=dict(title="Patio (Origem)", tickfont=dict(size=10), autorange="reversed"),
        height=max(350, len(matrix.index) * 26 + 120),
        margin=dict(l=90, r=20, t=50, b=100),
        font=dict(color="#1f2937", size=11),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Legenda de interpretacao
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown("<small>⬜ Sem dados (branco)</small>", unsafe_allow_html=True)
    c2.markdown(f"<small style='color:{COR_OK}'>🟩 Score baixo (bom)</small>", unsafe_allow_html=True)
    c3.markdown(f"<small style='color:{COR_WARN}'>🟨 Score medio</small>", unsafe_allow_html=True)
    c4.markdown(f"<small style='color:{COR_CRIT}'>🟥 Score alto (critico)</small>", unsafe_allow_html=True)

# endregion


# region ====================== SESSAO 3: render_ranking() =====================

def render_ranking(df: pd.DataFrame, top_n: int = 10,
                   ordem: str = "Score Total", gerencia: str = "SP"):
    """Ranking de hot-spots por patio de origem."""
    if df.empty or "origem" not in df.columns:
        st.info("Sem dados para o ranking.")
        return

    cnt_col = "numero_nota" if "numero_nota" in df.columns else "origem"
    agg_kw  = {"Qtd. Notas": (cnt_col, "count")}
    if "score"           in df.columns: agg_kw["Score Total"]            = ("score",           "sum")
    if "score"           in df.columns: agg_kw["Score Medio"]             = ("score",           "mean")
    if "lead_time_dias"  in df.columns: agg_kw["Lead Time Medio (dias)"] = ("lead_time_dias",  "mean")
    if "ramal"           in df.columns: agg_kw["Ramal"]                  = ("ramal",           "first")
    if "familia_defeito" in df.columns:
        agg_kw["Top Familia"] = (
            "familia_defeito",
            lambda x: x.value_counts().index[0] if len(x.dropna()) > 0 else "—"
        )

    ranking = (
        df.dropna(subset=["origem"])
        .groupby("origem").agg(**agg_kw)
        .reset_index().rename(columns={"origem": "Patio"})
    )

    col_ord = {"Score Total": "Score Total", "Qtd. Notas": "Qtd. Notas",
               "Lead Time Medio (dias)": "Lead Time Medio (dias)"}.get(ordem, "Score Total")
    if col_ord in ranking.columns:
        ranking = ranking.sort_values(col_ord, ascending=False)

    ranking = ranking.head(top_n).reset_index(drop=True)
    ranking.index += 1
    ranking.insert(0, "Pos.", [{1:"🥇",2:"🥈",3:"🥉"}.get(i, f"#{i}") for i in ranking.index])

    if "Ramal" in ranking.columns:
        ranking["Ramal"] = ranking["Ramal"].apply(lambda s: nome_ramal(s, "completo_sigla"))
    for c in ["Score Total", "Score Medio", "Lead Time Medio (dias)"]:
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
            x="Score Total", y="Patio", orientation="h",
            color="Score Total",
            color_continuous_scale=[[0, COR_OK],[0.5, COR_WARN],[1, COR_CRIT]],
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


# region ====================== SESSAO 4: render_serie_temporal() ==============

def _echarts_areaStyle(cor: str) -> dict:
    """Gradiente de area para ECharts a partir de uma cor hex."""
    h = cor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return {
        "color": {
            "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
            "colorStops": [
                {"offset": 0,   "color": f"rgba({r},{g},{b},0.28)"},
                {"offset": 1,   "color": f"rgba({r},{g},{b},0.02)"},
            ],
        }
    }


def _serie_echarts(grp: pd.DataFrame, metrica: str, label_y: str,
                   granularidade: str, gerencia: str):
    """Renderiza serie temporal em ECharts com curva suave e dataZoom."""
    cores = {"VP": COR_PRIMARIA, "EE": COR_EE, "Total": COR_GOLD}
    series_opt = []
    disciplinas = grp["disciplina"].unique().tolist()

    for disc in disciplinas:
        sub = grp[grp["disciplina"] == disc].sort_values("periodo")
        cor = cores.get(disc, COR_PRIMARIA)
        dados = [
            [int(p.timestamp() * 1000), round(float(v), 2) if not np.isnan(v) else None]
            for p, v in zip(sub["periodo"], sub["valor"])
        ]
        series_opt.append({
            "name": disc, "type": "line", "data": dados,
            "smooth": True, "symbol": "circle", "symbolSize": 6,
            "lineStyle":  {"color": cor, "width": 2.5},
            "itemStyle":  {"color": cor},
            "areaStyle":  _echarts_areaStyle(cor),
            "emphasis":   {"focus": "series"},
            "connectNulls": False,
        })

    # Linha de tendencia (regressao linear)
    tot = grp.groupby("periodo")["valor"].mean().reset_index()
    if len(tot) >= 4:
        x_n  = np.arange(len(tot))
        y_v  = tot["valor"].values
        mask = ~np.isnan(y_v)
        if mask.sum() >= 2:
            coef = np.polyfit(x_n[mask], y_v[mask], 1)
            tend = np.polyval(coef, x_n)
            series_opt.append({
                "name": "Tendencia", "type": "line", "symbol": "none",
                "data": [[int(p.timestamp()*1000), round(float(v),2)]
                         for p, v in zip(tot["periodo"], tend)],
                "lineStyle": {"color": "#94a3b8", "width": 1.5, "type": "dashed"},
                "itemStyle": {"color": "#94a3b8"},
            })

    fmt_x = "%b/%Y" if granularidade != "Semanal" else "%d/%m/%Y"

    option = {
        "backgroundColor": "#ffffff",
        "title": {
            "text":    f"{metrica} — {granularidade}",
            "subtext": f"Gerencia {gerencia}",
            "left":    "left",
            "textStyle":    {"color": "#1f2937", "fontSize": 13, "fontWeight": "bold"},
            "subtextStyle": {"color": "#6b7280", "fontSize": 11},
        },
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": COR_PRIMARIA, "borderWidth": 2,
            "padding": [10, 14],
            "extraCssText": "box-shadow:0 4px 16px rgba(0,0,0,0.12);border-radius:10px;",
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            "axisPointer": {
                "type": "cross",
                "lineStyle": {"color": COR_PRIMARIA, "width": 1, "type": "dashed"},
            },
        },
        "legend": {
            "data": disciplinas + (["Tendencia"] if len(tot) >= 4 else []),
            "bottom": "2%",
            "textStyle": {"color": "#374151", "fontSize": 11},
        },
        "grid": {"left": "6%", "right": "4%", "top": "18%", "bottom": "22%", "containLabel": True},
        "xAxis": {
            "type": "time",
            "axisLine":  {"lineStyle": {"color": "#e5e7eb"}},
            "axisLabel": {"color": "#6b7280", "fontSize": 10, "formatter": fmt_x},
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "value", "name": label_y,
            "nameTextStyle": {"color": "#6b7280", "fontSize": 10},
            "axisLine":  {"show": False}, "axisTick": {"show": False},
            "axisLabel": {"color": "#6b7280", "fontSize": 10},
            "splitLine": {"lineStyle": {"color": "#f1f5f9", "type": "dashed"}},
        },
        "dataZoom": [
            {
                "type": "slider", "xAxisIndex": 0,
                "start": 0, "end": 100, "height": 18, "bottom": "8%",
                "borderColor": "#e5e7eb",
                "fillerColor": "rgba(30,58,95,0.12)",
                "handleStyle": {"color": COR_PRIMARIA},
                "textStyle":   {"color": "#6b7280", "fontSize": 9},
            },
            {"type": "inside", "xAxisIndex": 0, "start": 0, "end": 100},
        ],
        "series": series_opt,
        "animation": True, "animationDuration": 600,
    }

    st_echarts(options=option, height="400px",
               key=f"temp_{gerencia}_{metrica}_{granularidade}")


def _serie_plotly(grp: pd.DataFrame, metrica: str, label_y: str,
                  granularidade: str, gerencia: str):
    """Fallback Plotly quando streamlit-echarts nao esta instalado."""
    cores = {"VP": COR_PRIMARIA, "EE": COR_EE, "Total": COR_GOLD}
    fig   = go.Figure()
    for disc in grp["disciplina"].unique():
        sub = grp[grp["disciplina"] == disc].sort_values("periodo")
        cor = cores.get(disc, COR_PRIMARIA)
        fig.add_trace(go.Scatter(
            x=sub["periodo"], y=sub["valor"],
            mode="lines+markers", name=disc,
            line=dict(color=cor, width=2.5), marker=dict(size=6, color=cor),
            fill="tozeroy", fillcolor=_hex_rgba(cor, 0.10),
        ))
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white", height=380,
        hovermode="x unified",
        xaxis=dict(showgrid=False, tickformat="%b/%Y"),
        yaxis=dict(title=label_y, showgrid=True, gridcolor="#f1f5f9", rangemode="tozero"),
        legend=dict(orientation="h", y=1.05, x=1, xanchor="right"),
        margin=dict(l=60, r=20, t=40, b=40),
        font=dict(color="#1f2937", size=11),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("streamlit-echarts nao instalado — usando Plotly")


def render_serie_temporal(df: pd.DataFrame, granularidade: str = "Mensal",
                          metrica: str = "Volume de Notas", gerencia: str = "SP"):
    """
    Serie temporal com ECharts (curva suave, area gradiente, dataZoom).
    Fallback automatico para Plotly se streamlit-echarts ausente.
    """
    if df.empty or "data_nota" not in df.columns:
        st.info("Sem dados temporais disponiveis.")
        return

    df_t = df.copy()
    df_t["data_nota"] = pd.to_datetime(df_t["data_nota"], errors="coerce")
    df_t = df_t.dropna(subset=["data_nota"])
    if df_t.empty:
        st.info("Sem notas com datas validas.")
        return

    freq = {"Mensal": "ME", "Semanal": "W", "Trimestral": "QE"}.get(granularidade, "ME")
    mmap = {
        "Volume de Notas": ("numero_nota" if "numero_nota" in df_t.columns else "data_nota", "count", "Qtd. Notas"),
        "Score Medio":     ("score",         "mean",  "Score Medio"),
        "Lead Time Medio": ("lead_time_dias","mean",  "Lead Time (dias)"),
    }
    col_val, func_agg, label_y = mmap.get(metrica, ("data_nota", "count", "Qtd. Notas"))
    if col_val not in df_t.columns:
        col_val, func_agg = df_t.columns[0], "count"

    tem_disc = "disciplina_label" in df_t.columns and df_t["disciplina_label"].nunique() > 1

    if tem_disc:
        grp = (
            df_t.groupby([pd.Grouper(key="data_nota", freq=freq), "disciplina_label"])
            [col_val].agg(func_agg).reset_index()
        )
        grp.columns = ["periodo", "disciplina", "valor"]
    else:
        grp = df_t.groupby(pd.Grouper(key="data_nota", freq=freq))[col_val].agg(func_agg).reset_index()
        grp.columns = ["periodo", "valor"]
        grp["disciplina"] = "Total"

    grp = grp.dropna(subset=["periodo"])
    if grp.empty:
        st.info("Serie temporal sem dados suficientes.")
        return

    if ECHARTS_OK:
        _serie_echarts(grp, metrica, label_y, granularidade, gerencia)
    else:
        _serie_plotly(grp, metrica, label_y, granularidade, gerencia)

    # Metricas resumidas
    vals = grp.groupby("periodo")["valor"].mean()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Media", f"{vals.mean():.1f}")
    c2.metric("Maximo", f"{vals.max():.1f}")
    c3.metric("Minimo", f"{vals.min():.1f}")
    if len(vals) >= 2:
        delta = vals.iloc[-1] - vals.iloc[-2]
        c4.metric("Delta vs anterior", f"{vals.iloc[-1]:.1f}", delta=f"{delta:+.1f}",
                  delta_color="inverse" if metrica != "Volume de Notas" else "normal")

# endregion
