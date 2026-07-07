# =============================================================================
# components/heatmap.py — Heatmap, Ranking e Série Temporal
# Sprint 3 — MRS Sentinel
#
# Exporta 3 funções reutilizadas pelas 3 telas de gerência:
#   • render_heatmap()        — Heatmap Pátio × Família de defeito
#   • render_ranking()        — Tabela de hot-spots ordenada
#   • render_serie_temporal() — Evolução temporal (volume/score/lead time)
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

from core.glossarios import nome_ramal

# Paleta MRS
COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_CRIT     = "#dc2626"
COR_WARN     = "#f59e0b"
COR_OK       = "#16a34a"

# endregion


# region ====================== SESSÃO 2: render_heatmap() =====================

def render_heatmap(df: pd.DataFrame, gerencia: str = "SP"):
    """
    Renderiza heatmap Pátio × Família de defeito.
    Intensidade = score médio das notas naquela combinação.

    Fallback: se não houver colunas suficientes, exibe mensagem amigável.

    Args:
        df: DataFrame filtrado com score calculado
        gerencia: 'SP', 'VP' ou 'GERAL' (usado no título)
    """
    # ── Validação de colunas obrigatórias ─────────────────────────────────────
    col_patio  = "origem"         # pátio de origem do defeito
    col_familia = "familia_defeito" if "familia_defeito" in df.columns \
                  else ("familia_cod" if "familia_cod" in df.columns else None)
    col_score  = "score"

    cols_ok = (
        col_patio in df.columns
        and col_familia is not None
        and col_score in df.columns
        and not df.empty
    )

    if not cols_ok:
        st.info(
            "ℹ️ Dados insuficientes para o heatmap. "
            "Verifique se as colunas `origem`, `familia_defeito` e `score` estão presentes."
        )
        return

    # ── Prepara pivot (Pátio × Família) ──────────────────────────────────────
    df_heat = df[[col_patio, col_familia, col_score]].copy()
    df_heat = df_heat.dropna(subset=[col_patio, col_familia])
    df_heat[col_patio]  = df_heat[col_patio].astype(str).str.strip()
    df_heat[col_familia] = df_heat[col_familia].astype(str).str.strip()

    if df_heat.empty:
        st.info("ℹ️ Nenhuma combinação Pátio × Família disponível.")
        return

    # Agrupa: score médio por combinação
    pivot_df = (
        df_heat.groupby([col_patio, col_familia])[col_score]
        .mean()
        .reset_index()
    )

    # Controles de exibição
    col_top_p, col_top_f = st.columns(2)
    with col_top_p:
        top_patios = st.slider(
            "Top N pátios (linhas)",
            min_value=5, max_value=40, value=15, step=5,
            key=f"heat_patios_{gerencia}",
        )
    with col_top_f:
        top_familias = st.slider(
            "Top N famílias (colunas)",
            min_value=3, max_value=20, value=10, step=1,
            key=f"heat_familias_{gerencia}",
        )

    # Seleciona top pátios e famílias por score total
    top_p = (
        pivot_df.groupby(col_patio)[col_score].sum()
        .nlargest(top_patios).index.tolist()
    )
    top_f = (
        pivot_df.groupby(col_familia)[col_score].sum()
        .nlargest(top_familias).index.tolist()
    )

    pivot_df = pivot_df[
        pivot_df[col_patio].isin(top_p) &
        pivot_df[col_familia].isin(top_f)
    ]

    # Cria matriz pivot
    matrix = pivot_df.pivot_table(
        index=col_patio, columns=col_familia,
        values=col_score, aggfunc="mean", fill_value=0
    )

    if matrix.empty:
        st.info("ℹ️ Dados insuficientes para o heatmap com os filtros atuais.")
        return

    # ── Figura Plotly ─────────────────────────────────────────────────────────
    fig = go.Figure(data=go.Heatmap(
        z=matrix.values,
        x=matrix.columns.tolist(),
        y=matrix.index.tolist(),
        colorscale=[
            [0.0, "#f0fdf4"],   # verde claro (score baixo = bom)
            [0.4, COR_OK],
            [0.7, COR_WARN],
            [1.0, COR_CRIT],    # vermelho (score alto = crítico)
        ],
        hoverongaps=False,
        hovertemplate=(
            "<b>Pátio:</b> %{y}<br>"
            "<b>Família:</b> %{x}<br>"
            "<b>Score médio:</b> %{z:.1f}<extra></extra>"
        ),
        colorbar=dict(
            title=dict(text="Score médio", side="right"),
            thickness=14,
            len=0.8,
        ),
    ))

    fig.update_layout(
        title=f"🌡️ Heatmap Pátio × Família — {gerencia}",
        xaxis=dict(title="Família de Defeito", tickangle=-35),
        yaxis=dict(title="Pátio (Origem)"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=max(350, len(matrix.index) * 24 + 100),
        margin=dict(l=80, r=20, t=50, b=80),
        font=dict(color="#1f2937", size=11),
    )

    st.plotly_chart(fig, use_container_width=True)

# endregion


# region ====================== SESSÃO 3: render_ranking() =====================

def render_ranking(
    df: pd.DataFrame,
    top_n: int = 10,
    ordem: str = "Score Total",
    gerencia: str = "SP",
):
    """
    Exibe ranking de hot-spots (pátios mais críticos).

    Agrupa por pátio de origem e calcula:
    - Score Total (soma)
    - Qtd. Notas
    - Score Médio
    - Lead Time Médio

    Args:
        df: DataFrame filtrado com score calculado
        top_n: quantos pátios exibir
        ordem: coluna para ordenar ('Score Total', 'Qtd. Notas', 'Lead Time Médio (dias)')
        gerencia: usado no título
    """
    if df.empty or "origem" not in df.columns:
        st.info("ℹ️ Sem dados para o ranking.")
        return

    # ── Agrupamento por pátio ─────────────────────────────────────────────────
    agg_dict = {
        "Qtd. Notas": ("numero_nota", "count") if "numero_nota" in df.columns
                       else ("origem", "count"),
    }
    if "score" in df.columns:
        agg_dict["Score Total"]  = ("score", "sum")
        agg_dict["Score Médio"]  = ("score", "mean")
    if "lead_time_dias" in df.columns:
        agg_dict["Lead Time Médio (dias)"] = ("lead_time_dias", "mean")
    if "ramal" in df.columns:
        agg_dict["Ramal"] = ("ramal", "first")
    if "familia_defeito" in df.columns:
        agg_dict["Top Família"] = ("familia_defeito", lambda x: x.value_counts().index[0] if len(x) > 0 else "—")

    ranking = (
        df.dropna(subset=["origem"])
        .groupby("origem")
        .agg(**agg_dict)
        .reset_index()
        .rename(columns={"origem": "Pátio"})
    )

    # Ordenação
    col_ord_map = {
        "Score Total": "Score Total",
        "Qtd. Notas": "Qtd. Notas",
        "Lead Time Médio (dias)": "Lead Time Médio (dias)",
    }
    col_ord = col_ord_map.get(ordem, "Score Total")

    if col_ord in ranking.columns:
        ranking = ranking.sort_values(col_ord, ascending=False)

    ranking = ranking.head(top_n).reset_index(drop=True)
    ranking.index += 1  # começa do 1

    # Adiciona medalhas para top 3
    def _medalha(pos):
        return {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, f"#{pos}")

    ranking.insert(0, "Pos.", [_medalha(i) for i in ranking.index])

    # Enriquece nome do ramal se disponível
    if "Ramal" in ranking.columns:
        ranking["Ramal"] = ranking["Ramal"].apply(lambda s: nome_ramal(s, "completo_sigla"))

    # Arredonda numéricos
    for col in ["Score Total", "Score Médio", "Lead Time Médio (dias)"]:
        if col in ranking.columns:
            ranking[col] = ranking[col].round(1)

    # ── Exibe tabela ──────────────────────────────────────────────────────────
    st.markdown(f"**🏆 Top {top_n} Hot-spots — {gerencia}** · Ordenado por: {ordem}")

    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Pos.": st.column_config.TextColumn(width="small"),
            "Score Total": st.column_config.ProgressColumn(
                min_value=0,
                max_value=float(ranking["Score Total"].max()) if "Score Total" in ranking.columns else 100,
                format="%.1f",
            ) if "Score Total" in ranking.columns else None,
            "Qtd. Notas": st.column_config.NumberColumn(format="%d"),
        },
    )

    # ── Gráfico de barras horizontais ─────────────────────────────────────────
    if "Score Total" in ranking.columns and not ranking.empty:
        fig = px.bar(
            ranking.sort_values("Score Total"),
            x="Score Total",
            y="Pátio",
            orientation="h",
            color="Score Total",
            color_continuous_scale=[COR_OK, COR_WARN, COR_CRIT],
            text="Score Total",
            labels={"Score Total": "Score Total", "Pátio": ""},
        )
        fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            coloraxis_showscale=False,
            height=max(300, top_n * 32),
            margin=dict(l=10, r=60, t=10, b=10),
            font=dict(color="#1f2937", size=11),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

# endregion


# region ====================== SESSÃO 4: render_serie_temporal() ==============

def render_serie_temporal(
    df: pd.DataFrame,
    granularidade: str = "Mensal",
    metrica: str = "Volume de Notas",
    gerencia: str = "SP",
):
    """
    Exibe a evolução temporal da métrica escolhida.

    Suporta separação automática por disciplina (VP vs EE) se a coluna
    'disciplina_label' estiver presente.

    Args:
        df: DataFrame filtrado com score calculado e data_nota parseada
        granularidade: 'Mensal', 'Semanal' ou 'Trimestral'
        metrica: 'Volume de Notas', 'Score Médio' ou 'Lead Time Médio'
        gerencia: usado no título
    """
    if df.empty or "data_nota" not in df.columns:
        st.info("ℹ️ Sem dados temporais disponíveis.")
        return

    df_t = df.dropna(subset=["data_nota"]).copy()
    df_t["data_nota"] = pd.to_datetime(df_t["data_nota"], errors="coerce")
    df_t = df_t.dropna(subset=["data_nota"])

    if df_t.empty:
        st.info("ℹ️ Sem notas com datas válidas.")
        return

    # ── Frequência pandas ─────────────────────────────────────────────────────
    freq_map = {"Mensal": "ME", "Semanal": "W", "Trimestral": "QE"}
    freq = freq_map.get(granularidade, "ME")

    # ── Métrica de agregação ──────────────────────────────────────────────────
    metrica_map = {
        "Volume de Notas": ("numero_nota", "count", "Qtd. Notas"),
        "Score Médio":     ("score",        "mean",  "Score Médio"),
        "Lead Time Médio": ("lead_time_dias","mean", "Lead Time (dias)"),
    }
    col_val, func_agg, label_y = metrica_map.get(
        metrica, ("numero_nota", "count", "Qtd. Notas")
    )

    # Usa coluna alternativa se a principal não existir
    if col_val not in df_t.columns:
        col_val = df_t.columns[0]
        func_agg = "count"

    # ── Agrupa: por período (e por disciplina se disponível) ──────────────────
    tem_disciplina = (
        "disciplina_label" in df_t.columns
        and df_t["disciplina_label"].nunique() > 1
    )

    if tem_disciplina:
        grp = df_t.groupby(
            [pd.Grouper(key="data_nota", freq=freq), "disciplina_label"]
        )[col_val].agg(func_agg).reset_index()
        grp.columns = ["periodo", "disciplina", "valor"]
    else:
        grp = df_t.groupby(
            pd.Grouper(key="data_nota", freq=freq)
        )[col_val].agg(func_agg).reset_index()
        grp.columns = ["periodo", "valor"]
        grp["disciplina"] = "Total"

    grp = grp.dropna(subset=["periodo"])

    if grp.empty:
        st.info("ℹ️ Série temporal sem dados suficientes.")
        return

    # ── Figura Plotly ─────────────────────────────────────────────────────────
    cores_disc = {"VP": COR_PRIMARIA, "EE": "#7c3aed", "Total": COR_GOLD}

    fig = go.Figure()

    for disc in grp["disciplina"].unique():
        sub = grp[grp["disciplina"] == disc].sort_values("periodo")
        cor = cores_disc.get(disc, COR_PRIMARIA)

        # Linha principal
        fig.add_trace(go.Scatter(
            x=sub["periodo"],
            y=sub["valor"],
            mode="lines+markers",
            name=disc,
            line=dict(color=cor, width=2.5),
            marker=dict(size=6, color=cor),
            hovertemplate=(
                f"<b>{disc}</b><br>"
                "%{x|%b/%Y}<br>"
                f"{label_y}: <b>%{{y:.1f}}</b><extra></extra>"
            ),
        ))

        # Área preenchida suave
        fig.add_trace(go.Scatter(
            x=sub["periodo"],
            y=sub["valor"],
            fill="tozeroy",
            fillcolor=cor.replace(")", ", 0.08)").replace("rgb", "rgba")
                       if cor.startswith("rgb") else cor + "14",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        ))

    # Linha de tendência (regressão linear) se >= 4 pontos
    total_grp = grp.groupby("periodo")["valor"].mean().reset_index()
    if len(total_grp) >= 4:
        x_num = np.arange(len(total_grp))
        y_vals = total_grp["valor"].values
        mask = ~np.isnan(y_vals)
        if mask.sum() >= 2:
            coef = np.polyfit(x_num[mask], y_vals[mask], 1)
            tendencia = np.polyval(coef, x_num)
            fig.add_trace(go.Scatter(
                x=total_grp["periodo"],
                y=tendencia,
                mode="lines",
                name="Tendência",
                line=dict(color="#94a3b8", width=1.5, dash="dash"),
                hoverinfo="skip",
            ))

    fig.update_layout(
        title=dict(
            text=f"📈 {metrica} — {granularidade} · {gerencia}",
            font=dict(size=13, color="#1f2937"),
            x=0,
        ),
        xaxis=dict(
            title="Período",
            showgrid=True,
            gridcolor="#f1f5f9",
            tickformat="%b/%Y" if granularidade != "Semanal" else "%d/%m/%Y",
        ),
        yaxis=dict(
            title=label_y,
            showgrid=True,
            gridcolor="#f1f5f9",
            rangemode="tozero",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="x unified",
        height=380,
        margin=dict(l=60, r=20, t=50, b=60),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
        ),
        font=dict(color="#1f2937", size=11),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── Estatísticas resumidas abaixo ─────────────────────────────────────────
    col_a, col_b, col_c, col_d = st.columns(4)
    vals_total = grp.groupby("periodo")["valor"].mean()

    with col_a:
        st.metric("Média do período", f"{vals_total.mean():.1f}")
    with col_b:
        st.metric("Máximo", f"{vals_total.max():.1f}")
    with col_c:
        st.metric("Mínimo", f"{vals_total.min():.1f}")
    with col_d:
        if len(vals_total) >= 2:
            delta = vals_total.iloc[-1] - vals_total.iloc[-2]
            st.metric(
                "Δ vs período anterior",
                f"{vals_total.iloc[-1]:.1f}",
                delta=f"{delta:+.1f}",
                delta_color="inverse" if metrica != "Volume de Notas" else "normal",
            )

# endregion
