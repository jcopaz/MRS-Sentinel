# components/heatmap.py
# Heatmap Pátio × Família + Ranking Hot-spots + Série Temporal
# Sprint 3 — Visualizações por Gerência
#
# USO:
#   from components.heatmap import render_heatmap_patio_familia
#   from components.heatmap import render_ranking_hotspots
#   from components.heatmap import render_serie_temporal

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from streamlit_echarts import st_echarts
from core.glossarios import nome_ramal

# region ====================== SESSÃO 1: Heatmap Pátio × Família ==============

def render_heatmap_patio_familia(df: pd.DataFrame, disciplina: str = "VP") -> None:
    """
    Renderiza o Heatmap Pátio × Família de Defeito via ECharts.

    Eixos:
      X = Família de defeito (Trilho, AMV, Geometria... / Sinalização, Energia...)
      Y = Pátio (código de origem), filtrado por slider Top N

    Valor da célula = contagem de notas.
    Cores em 10 níveis azul-marinho → dourado → vermelho.

    Args:
        df:         DataFrame filtrado com colunas: origem, familia_defeito
        disciplina: 'VP' ou 'EE' — ajusta rótulo
    """
    if df is None or df.empty:
        st.info("📭 Sem dados para o heatmap.")
        return

    # ── 1.1: Verificação de colunas necessárias ───────────────────────────────
    col_patio   = "origem"        if "origem"        in df.columns else None
    col_familia = "familia_defeito" if "familia_defeito" in df.columns else (
                  "familia_cod"   if "familia_cod"   in df.columns else None
    )

    if not col_patio or not col_familia:
        st.warning("⚠️ Colunas `origem` ou `familia_defeito` não encontradas no DataFrame.")
        return

    # ── 1.2: Slider Top N pátios ──────────────────────────────────────────────
    top_n = st.slider(
        "🔢 Top N pátios (por volume)",
        min_value=5, max_value=30, value=15, step=5,
        help="Exibe apenas os N pátios com mais notas.",
        key=f"slider_topn_{disciplina}",
    )

    # Identifica top N pátios por total de notas
    top_patios = (
        df.groupby(col_patio).size()
        .nlargest(top_n)
        .index.tolist()
    )

    df_top = df[df[col_patio].isin(top_patios)].copy()

    if df_top.empty:
        st.info("📭 Nenhum dado com os pátios selecionados.")
        return

    # ── 1.3: Tabela pivô ─────────────────────────────────────────────────────
    pivot = (
        df_top.groupby([col_patio, col_familia])
        .size()
        .reset_index(name="contagem")
    )

    patios   = sorted(pivot[col_patio].unique().tolist())
    familias = sorted(pivot[col_familia].unique().tolist())

    # Monta matriz de valores para ECharts
    data = []
    for i, patio in enumerate(patios):
        for j, familia in enumerate(familias):
            val = pivot[
                (pivot[col_patio] == patio) & (pivot[col_familia] == familia)
            ]["contagem"].sum()
            data.append([j, i, int(val)])  # ECharts: [x_idx, y_idx, valor]

    max_val = max((d[2] for d in data), default=1) or 1

    # ── 1.4: Configuração ECharts ─────────────────────────────────────────────
    option = {
        "title": {
            "text": f"🔥 Heatmap Pátio × Família — {disciplina}",
            "textStyle": {"color": "#1e3a5f", "fontSize": 14, "fontWeight": "bold"},
            "left": "center",
            "top": 4,
        },
        "tooltip": {
            "position": "top",
            "formatter": "function(p){ return p.name + '<br/>Família: ' + p.data[0_label] + '<br/>Pátio: ' + p.data[1_label] + '<br/>Notas: <b>' + p.data[2] + '</b>'; }",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": "#1e3a5f",
            "borderWidth": 2,
            "textStyle": {"color": "#1f2937", "fontSize": 12},
        },
        "grid": {"left": "12%", "right": "4%", "bottom": "18%", "top": "10%"},
        "xAxis": {
            "type": "category",
            "data": familias,
            "axisLabel": {"rotate": 35, "fontSize": 10, "color": "#1f2937"},
            "splitArea": {"show": True},
        },
        "yAxis": {
            "type": "category",
            "data": patios,
            "axisLabel": {"fontSize": 10, "color": "#1f2937"},
            "splitArea": {"show": True},
        },
        "visualMap": {
            "min": 0,
            "max": max_val,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": "2%",
            "inRange": {
                "color": [
                    "#f0f9ff", "#bae6fd", "#7dd3fc",
                    "#38bdf8", "#0ea5e9", "#0284c7",
                    "#ffb000", "#f59e0b", "#dc2626", "#7f1d1d",
                ]
            },
            "textStyle": {"color": "#1f2937"},
        },
        "series": [
            {
                "name": "Notas",
                "type": "heatmap",
                "data": data,
                "label": {"show": True, "color": "#fff", "fontSize": 9},
                "emphasis": {
                    "itemStyle": {
                        "shadowBlur": 10,
                        "shadowColor": "rgba(0,0,0,0.5)",
                    }
                },
            }
        ],
        "backgroundColor": "#ffffff",
    }

    # Altura dinâmica proporcional ao número de pátios
    altura = max(350, min(800, 40 * len(patios) + 120))
    st_echarts(options=option, height=f"{altura}px", key=f"heatmap_{disciplina}")

# endregion


# region ====================== SESSÃO 2: Ranking Hot-spots ====================

def render_ranking_hotspots(df: pd.DataFrame, disciplina: str = "VP", top_n: int = 20) -> None:
    """
    Renderiza a tabela de Ranking Hot-spots — trechos mais críticos por score.

    Exibe: Posição, Ramal, Pátio, Família, Score Total, Nº Notas, Lead time médio.
    Inclui botão de export CSV.

    Args:
        df:         DataFrame filtrado
        disciplina: 'VP', 'EE' ou 'VP+EE'
        top_n:      número de linhas a exibir
    """
    if df is None or df.empty:
        st.info("📭 Sem dados para o ranking.")
        return

    st.markdown(f"#### 🏆 Ranking Hot-spots — Top {top_n} ({disciplina})")

    # ── 2.1: Agrega por pátio (origem) ────────────────────────────────────────
    cols_necessarias = {"ramal", "origem"}.intersection(df.columns)
    group_cols = list(cols_necessarias)

    if not group_cols:
        st.warning("⚠️ Colunas `ramal` / `origem` não encontradas.")
        return

    agg_dict = {}
    if "score" in df.columns:
        agg_dict["score"]           = "sum"
    if "lead_time_dias" in df.columns:
        agg_dict["lead_time_dias"]  = "mean"
    agg_dict["numero_nota"] = "count"  # total de notas

    if not agg_dict:
        st.warning("⚠️ Sem colunas de métricas disponíveis.")
        return

    ranking = (
        df.groupby(group_cols)
        .agg(agg_dict)
        .reset_index()
        .sort_values("score" if "score" in agg_dict else "numero_nota", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    ranking.index += 1  # posição começa em 1

    # ── 2.2: Formata colunas ─────────────────────────────────────────────────
    rename = {
        "ramal":          "Ramal",
        "origem":         "Pátio",
        "score":          "Score Total",
        "lead_time_dias": "Lead Time Médio (dias)",
        "numero_nota":    "Nº Notas",
    }
    ranking.rename(columns=rename, inplace=True)

    # Converte sigla de ramal para nome completo
    if "Ramal" in ranking.columns:
        ranking["Ramal"] = ranking["Ramal"].apply(
            lambda s: nome_ramal(str(s), "completo_sigla")
        )

    # Arredonda
    if "Score Total" in ranking.columns:
        ranking["Score Total"] = ranking["Score Total"].round(1)
    if "Lead Time Médio (dias)" in ranking.columns:
        ranking["Lead Time Médio (dias)"] = ranking["Lead Time Médio (dias)"].round(0).astype(int)

    # ── 2.3: Exibição ────────────────────────────────────────────────────────
    st.dataframe(
        ranking,
        use_container_width=True,
        height=min(600, 45 * len(ranking) + 80),
    )

    # ── 2.4: Export CSV ───────────────────────────────────────────────────────
    csv = ranking.to_csv(index_label="Posição").encode("utf-8-sig")
    st.download_button(
        label="⬇️ Exportar Ranking CSV",
        data=csv,
        file_name=f"ranking_hotspots_{disciplina}.csv",
        mime="text/csv",
        key=f"download_ranking_{disciplina}",
    )

# endregion


# region ====================== SESSÃO 3: Série Temporal =======================

def render_serie_temporal(df: pd.DataFrame, disciplina: str = "VP") -> None:
    """
    Renderiza a Série Temporal de notas (abertas × encerradas × planejadas).

    Funcionalidades:
      - Agregação mensal ou semanal (selecionável)
      - Dimensão de quebra: Ramal, Pátio, Família, Prioridade, Status, Nenhuma
      - Plotly line chart interativo

    Args:
        df:         DataFrame filtrado com datas
        disciplina: usado apenas no título
    """
    if df is None or df.empty:
        st.info("📭 Sem dados para a série temporal.")
        return

    st.markdown(f"#### 📈 Série Temporal — {disciplina}")

    # ── 3.1: Controles ────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1, 1, 2])

    with c1:
        granularidade = st.selectbox(
            "Granularidade",
            options=["Mensal", "Semanal"],
            key=f"gran_{disciplina}",
        )
    with c2:
        dimensoes_disponiveis = ["Nenhuma"]
        for col, label in [
            ("ramal",          "Ramal"),
            ("origem",         "Pátio"),
            ("familia_defeito","Família"),
            ("prioridade",     "Prioridade"),
            ("status_usuario", "Status"),
        ]:
            if col in df.columns:
                dimensoes_disponiveis.append(label)

        dimensao = st.selectbox(
            "Quebra por",
            options=dimensoes_disponiveis,
            key=f"dim_{disciplina}",
        )
    with c3:
        metrica = st.selectbox(
            "Métrica",
            options=["Notas Abertas", "Notas Encerradas", "Notas Planejadas", "Todas"],
            key=f"met_{disciplina}",
        )

    # ── 3.2: Prepara coluna de data ────────────────────────────────────────────
    col_data_map = {
        "Notas Abertas":     "data_nota",
        "Notas Encerradas":  "data_encerramento",
        "Notas Planejadas":  "data_planejada",
        "Todas":             "data_nota",
    }
    col_data = col_data_map.get(metrica, "data_nota")

    if col_data not in df.columns:
        col_data = next((c for c in ["data_nota", "data_encerramento"] if c in df.columns), None)

    if not col_data:
        st.warning("⚠️ Nenhuma coluna de data encontrada.")
        return

    df_ts = df.copy()
    df_ts[col_data] = pd.to_datetime(df_ts[col_data], errors="coerce")
    # Remove NaT antes de qualquer agregação — evita crash
    df_ts = df_ts.dropna(subset=[col_data])

    if df_ts.empty:
        st.warning("⚠️ Sem datas válidas para plotar.")
        return

    # Filtra pelo status se métrica específica
    if metrica == "Notas Abertas" and "status_usuario" in df_ts.columns:
        df_ts = df_ts[df_ts["status_usuario"].str.upper() == "ABER"]
    elif metrica == "Notas Encerradas" and "status_usuario" in df_ts.columns:
        df_ts = df_ts[df_ts["status_usuario"].str.upper() != "ABER"]

    if df_ts.empty:
        st.info(f"📭 Sem notas para a métrica '{metrica}'.")
        return

    # ── 3.3: Monta período ────────────────────────────────────────────────────
    freq = "ME" if granularidade == "Mensal" else "W"  # pandas >=2.2: ME ao invés de M
    df_ts["_periodo"] = df_ts[col_data].dt.to_period(
        "M" if granularidade == "Mensal" else "W"
    ).dt.to_timestamp()

    # ── 3.4: Mapeia dimensão de quebra ────────────────────────────────────────
    dim_col_map = {
        "Ramal":      "ramal",
        "Pátio":      "origem",
        "Família":    "familia_defeito",
        "Prioridade": "prioridade",
        "Status":     "status_usuario",
        "Nenhuma":    None,
    }
    dim_col = dim_col_map.get(dimensao)

    # ── 3.5: Agrega ───────────────────────────────────────────────────────────
    if dim_col and dim_col in df_ts.columns:
        serie = (
            df_ts.groupby(["_periodo", dim_col])
            .size()
            .reset_index(name="contagem")
        )
        # Para ramal: converte sigla → nome completo no label
        if dim_col == "ramal":
            serie[dim_col] = serie[dim_col].apply(lambda s: nome_ramal(str(s)))

        fig = px.line(
            serie,
            x="_periodo",
            y="contagem",
            color=dim_col,
            markers=True,
            labels={"_periodo": "Período", "contagem": "Nº Notas", dim_col: dimensao},
            title=f"{metrica} por {granularidade} — {disciplina}",
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
    else:
        serie = (
            df_ts.groupby("_periodo")
            .size()
            .reset_index(name="contagem")
        )
        fig = px.line(
            serie,
            x="_periodo",
            y="contagem",
            markers=True,
            labels={"_periodo": "Período", "contagem": "Nº Notas"},
            title=f"{metrica} por {granularidade} — {disciplina}",
        )
        fig.update_traces(line_color="#1e3a5f", line_width=2.5)

    # ── 3.6: Estilização ─────────────────────────────────────────────────────
    fig.update_layout(
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font_color="#1f2937",
        title_font=dict(color="#1e3a5f", size=14, family="sans-serif"),
        legend=dict(orientation="h", y=-0.25),
        hovermode="x unified",
        xaxis=dict(showgrid=True, gridcolor="#f3f4f6"),
        yaxis=dict(showgrid=True, gridcolor="#f3f4f6"),
        margin=dict(l=10, r=10, t=40, b=60),
    )

    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

# endregion
