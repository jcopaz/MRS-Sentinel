# =============================================================================
# components/unifilar.py — Unifilar Dual VP + EE
# Sprint 3 (rev.2) — MRS Sentinel
#
# Problema resolvido: agrupamento granular por trecho gerava dezenas de
# bolhinhas. Agora o nível de agrupamento é configurável pelo usuário:
#   • Ramal  → 1 bolha por ramal (visão ampla, padrão)
#   • Pátio  → 1 bolha por pátio de origem dentro dos ramais selecionados
#   • Trecho → 1 bolha por par Origem-Destino (detalhe máximo)
#
# Estrutura:
#   Sessão 1: Imports & constantes
#   Sessão 2: Funções de agregação
#   Sessão 3: Funções de layout (posições x, y)
#   Sessão 4: Funções de renderização Plotly
#   Sessão 5: Ponto de entrada render_unifilar_dual()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from core.glossarios import nome_ramal, RAMAIS_MRS, normalizar_coluna_ramal

# Paleta MRS
COR_VP      = "#1e3a5f"   # azul-marinho VP
COR_EE      = "#7c3aed"   # roxo EE
COR_CRIT    = "#dc2626"   # vermelho — score alto (crítico)
COR_WARN    = "#f59e0b"   # amarelo — score médio (atenção)
COR_OK      = "#16a34a"   # verde — score baixo (normal)
COR_BG      = "#f8fafc"   # fundo do gráfico
COR_TRILHO  = "#94a3b8"   # cor da "linha ferroviária"

# Escala de cor score (verde → amarelo → vermelho)
COLORSCALE = [
    [0.0,  COR_OK],
    [0.5,  COR_WARN],
    [1.0,  COR_CRIT],
]

# Posição Y por disciplina (dual lane)
Y_VP = 1.0    # trilho superior = Via Permanente
Y_EE = -1.0   # trilho inferior = Eletroeletrônica
Y_GERAL = 0.0 # linha central para visão combinada

# endregion


# region ====================== SESSÃO 2: Funções de agregação =================

def _top3_defeitos(serie: pd.Series) -> str:
    """
    Retorna os 3 defeitos mais frequentes como string HTML.
    Defensivo: ignora NaN e listas vazias.
    """
    vc = serie.dropna().value_counts().head(3)
    if vc.empty:
        return "—"
    return "<br>".join(f"• {d}" for d in vc.index)


def _agregar(df: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """
    Agrega o DataFrame no nível escolhido: 'Ramal', 'Pátio' ou 'Trecho'.

    Colunas produzidas:
        label       — nome exibido no eixo X e no hover
        chave       — identificador interno (sigla ou código)
        ramal_sigla — sigla do ramal pai (para ordenação e cor)
        disciplina  — 'VP', 'EE' ou 'VP+EE'
        qtd         — total de notas
        score_med   — score médio (ou 0 se ausente)
        lt_med      — lead time médio em dias
        top_defeitos— string HTML com top-3 defeitos
        y_pos       — posição y no gráfico (lane VP ou EE)
    """
    if df.empty:
        return pd.DataFrame()

    # Define a coluna de agrupamento conforme o nível
    if nivel == "Ramal":
        col_chave = "ramal"
    elif nivel == "Pátio":
        col_chave = "origem"
    else:  # Trecho
        # Constrói coluna trecho = "ORIGEM → DESTINO"
        if "origem" in df.columns and "destino" in df.columns:
            df = df.copy()
            df["_trecho_label"] = (
                df["origem"].fillna("?") + " → " + df["destino"].fillna("?")
            )
            col_chave = "_trecho_label"
        else:
            col_chave = "trecho"

    # Garante que a coluna existe
    if col_chave not in df.columns:
        return pd.DataFrame()

    # Agrega por chave + disciplina
    # Usa disciplina_label para separar VP de EE nas lanes
    disc_col = "disciplina_label" if "disciplina_label" in df.columns else None

    group_cols = [col_chave]
    if disc_col:
        group_cols.append(disc_col)

    agg = (
        df.groupby(group_cols, dropna=False)
        .agg(
            qtd=("numero_nota", "count") if "numero_nota" in df.columns
                else (col_chave, "count"),
            score_med=("score", "mean") if "score" in df.columns
                else (col_chave, lambda x: 0),
            lt_med=("lead_time_dias", "mean") if "lead_time_dias" in df.columns
                else (col_chave, lambda x: 0),
            ramal_sigla=("ramal", "first") if "ramal" in df.columns
                else (col_chave, "first"),
            top_defeitos=("defeito_legivel", _top3_defeitos)
                if "defeito_legivel" in df.columns
                else (col_chave, lambda x: "—"),
        )
        .reset_index()
    )

    agg = agg.rename(columns={col_chave: "chave"})

    # Rótulo legível (nome completo para ramal, sigla direta para pátio/trecho)
    if nivel == "Ramal":
        agg["label"] = agg["chave"].apply(lambda s: nome_ramal(s, "completo_sigla"))
    else:
        agg["label"] = agg["chave"].fillna("?")
        # Garante que ramal_sigla não é a chave errada
        if "ramal_sigla" not in agg.columns and "ramal" in df.columns:
            agg["ramal_sigla"] = df["ramal"].iloc[0]

    # Posição Y (lane VP ou EE)
    if disc_col and disc_col in agg.columns:
        agg["y_pos"] = agg[disc_col].map({"VP": Y_VP, "EE": Y_EE}).fillna(Y_GERAL)
        agg["disciplina"] = agg[disc_col]
    else:
        agg["y_pos"] = Y_GERAL
        agg["disciplina"] = "VP+EE"

    # Limpa NaN numéricos
    agg["score_med"] = agg["score_med"].fillna(0)
    agg["lt_med"]    = agg["lt_med"].fillna(0)

    return agg

# endregion


# region ====================== SESSÃO 3: Layout (posições x) ==================

def _atribuir_posicoes_x(agg: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """
    Atribui posição x a cada ponto do unifilar.

    Estratégia:
    - Ordena os ramais pela ordem oficial MRS (lista RAMAIS_MRS)
    - Pátios/trechos são ordenados dentro do ramal pai
    - Garante separação visual entre ramais distintos (gap de 1.5)
    """
    if agg.empty:
        return agg

    agg = agg.copy()

    # Ordem canônica dos ramais (por posição no dict RAMAIS_MRS)
    ordem_ramais = list(RAMAIS_MRS.keys())

    def _ordem_ramal(sigla):
        try:
            return ordem_ramais.index(str(sigla).strip().upper())
        except ValueError:
            return len(ordem_ramais)  # desconhecidos no final

    agg["_ordem_ramal"] = agg["ramal_sigla"].apply(_ordem_ramal)

    if nivel == "Ramal":
        # Ordena por posição oficial do ramal
        agg = agg.sort_values(["_ordem_ramal", "disciplina"]).reset_index(drop=True)
        # X = índice sequencial dentro de cada ramal (VP e EE ficam na mesma coluna x)
        ramais_unicos = agg["chave"].unique()
        pos_x = {r: i * 2.0 for i, r in enumerate(ramais_unicos)}
        agg["x_pos"] = agg["chave"].map(pos_x)

    else:
        # Para Pátio/Trecho: ordena por ramal pai, depois por chave
        agg = agg.sort_values(["_ordem_ramal", "chave", "disciplina"]).reset_index(drop=True)
        # Calcula posição x com gap entre ramais
        x_atual = 0.0
        ramal_ant = None
        posicoes = []
        for _, row in agg.iterrows():
            if ramal_ant is not None and row["ramal_sigla"] != ramal_ant:
                x_atual += 1.5  # gap entre ramais
            posicoes.append(x_atual)
            x_atual += 1.0
            ramal_ant = row["ramal_sigla"]
        agg["x_pos"] = posicoes

    return agg

# endregion


# region ====================== SESSÃO 4: Renderização Plotly ==================

def _cor_por_score(score: float, score_max: float) -> str:
    """Retorna cor hex interpolada entre verde e vermelho pelo score relativo."""
    if score_max == 0:
        return COR_OK
    ratio = min(score / score_max, 1.0)
    if ratio < 0.5:
        # verde → amarelo
        t = ratio * 2
        r = int(22  + t * (245 - 22))
        g = int(163 + t * (158 - 163))
        b = int(74  + t * (11  - 74))
    else:
        # amarelo → vermelho
        t = (ratio - 0.5) * 2
        r = int(245 + t * (220 - 245))
        g = int(158 + t * (38  - 158))
        b = int(11  + t * (38  - 11))
    return f"rgb({r},{g},{b})"


def _construir_figura(agg: pd.DataFrame, gerencia: str, nivel: str) -> go.Figure:
    """
    Constrói a figura Plotly do unifilar.

    Layout:
    - Linha "trilho" horizontal conectando os pontos
    - Bolhas = notas agregadas (tamanho ∝ qtd, cor ∝ score)
    - Hover rico com nome completo, qtd, score, lead time, top defeitos
    - Labels abaixo das bolhas (nomes curtos)
    """
    if agg.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="Sem dados para exibir",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(size=16, color="#6b7280"),
        )
        return fig

    score_max = agg["score_med"].max() if agg["score_med"].max() > 0 else 1.0

    # Normaliza tamanho das bolhas (mín 18, máx 60 px)
    qtd_max = agg["qtd"].max() if agg["qtd"].max() > 0 else 1
    agg["_size"] = 18 + (agg["qtd"] / qtd_max) * 42

    fig = go.Figure()

    # ── Linhas de trilho (uma por disciplina/lane) ──────────────────────────
    for disciplina, y_val, cor_linha in [
        ("VP", Y_VP, COR_VP),
        ("EE", Y_EE, COR_EE),
    ]:
        sub = agg[agg["y_pos"] == y_val].sort_values("x_pos")
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["x_pos"],
            y=[y_val] * len(sub),
            mode="lines",
            line=dict(color=cor_linha, width=3, dash="solid"),
            name=f"Trilho {disciplina}",
            hoverinfo="skip",
            showlegend=True,
        ))

    # Trilho central (se disciplina única / visão geral)
    sub_geral = agg[agg["y_pos"] == Y_GERAL].sort_values("x_pos")
    if not sub_geral.empty:
        fig.add_trace(go.Scatter(
            x=sub_geral["x_pos"],
            y=[Y_GERAL] * len(sub_geral),
            mode="lines",
            line=dict(color=COR_TRILHO, width=3),
            name="Trilho",
            hoverinfo="skip",
            showlegend=False,
        ))

    # ── Bolhas por linha ────────────────────────────────────────────────────
    cores = agg["score_med"].apply(lambda s: _cor_por_score(s, score_max))

    hover_texts = []
    for _, row in agg.iterrows():
        ger_tag = f"<b>Gerência: {row.get('gerencia_label', gerencia)}</b><br>" \
                  if "gerencia_label" in row else ""
        disc_tag = f"Disciplina: {row.get('disciplina','—')}<br>"
        texto = (
            f"<b>{row['label']}</b><br>"
            f"{ger_tag}{disc_tag}"
            f"📌 Notas: <b>{int(row['qtd']):,}</b><br>"
            f"⚡ Score médio: <b>{row['score_med']:.1f}</b><br>"
            f"⏱️ Lead time médio: <b>{row['lt_med']:.0f} dias</b><br>"
            f"─────────────<br>"
            f"Top defeitos:<br>{row['top_defeitos']}"
        )
        hover_texts.append(texto)

    fig.add_trace(go.Scatter(
        x=agg["x_pos"],
        y=agg["y_pos"],
        mode="markers+text",
        marker=dict(
            size=agg["_size"],
            color=cores,
            opacity=0.88,
            line=dict(color="white", width=2),
        ),
        text=agg["label"].apply(
            lambda s: s[:20] + "…" if len(s) > 20 else s
        ),
        textposition="bottom center",
        textfont=dict(size=9, color="#1f2937"),
        hovertext=hover_texts,
        hoverinfo="text",
        hoverlabel=dict(
            bgcolor="white",
            bordercolor="#1e3a5f",
            font_size=12,
            font_color="#1f2937",
        ),
        name="Notas",
        showlegend=False,
    ))

    # ── Rótulos de ramal (faixa de fundo entre grupos) ──────────────────────
    if nivel in ("Pátio", "Trecho"):
        ramais_grp = agg.groupby("ramal_sigla")["x_pos"].agg(["min", "max"]).reset_index()
        for _, rg in ramais_grp.iterrows():
            mid_x = (rg["min"] + rg["max"]) / 2
            fig.add_annotation(
                x=mid_x, y=1.55,
                text=f"<b>{nome_ramal(rg['ramal_sigla'], 'completo_sigla')}</b>",
                showarrow=False,
                font=dict(size=9, color="#1e3a5f"),
                bgcolor="rgba(30,58,95,0.08)",
                bordercolor="#1e3a5f",
                borderwidth=1,
                borderpad=3,
            )
            # linha divisória entre ramais
            if rg["min"] > agg["x_pos"].min():
                fig.add_vline(
                    x=rg["min"] - 0.75,
                    line=dict(color="#e5e7eb", width=1, dash="dot"),
                )

    # ── Labels fixos de lane ─────────────────────────────────────────────────
    x_label = agg["x_pos"].min() - 1.2 if not agg.empty else -1
    if agg["y_pos"].isin([Y_VP]).any():
        fig.add_annotation(x=x_label, y=Y_VP, text="<b>VP</b>",
                           showarrow=False, font=dict(size=11, color=COR_VP))
    if agg["y_pos"].isin([Y_EE]).any():
        fig.add_annotation(x=x_label, y=Y_EE, text="<b>EE</b>",
                           showarrow=False, font=dict(size=11, color=COR_EE))

    # ── Layout geral ─────────────────────────────────────────────────────────
    titulo_nivel = {"Ramal": "por Ramal", "Pátio": "por Pátio", "Trecho": "por Trecho"}
    x_range = [
        agg["x_pos"].min() - 1.5,
        agg["x_pos"].max() + 1.5,
    ] if not agg.empty else [-1, 10]

    fig.update_layout(
        title=dict(
            text=f"🗺️ Unifilar Dual VP + EE — {titulo_nivel.get(nivel, '')}",
            font=dict(size=14, color="#1f2937"),
            x=0,
        ),
        xaxis=dict(
            showgrid=False, zeroline=False,
            showticklabels=False,
            range=x_range,
        ),
        yaxis=dict(
            showgrid=False, zeroline=False,
            showticklabels=False,
            range=[-2.0, 2.2],
            fixedrange=True,
        ),
        plot_bgcolor=COR_BG,
        paper_bgcolor="white",
        height=420,
        margin=dict(l=60, r=20, t=50, b=60),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.18,
            xanchor="center", x=0.5,
            font=dict(size=11),
        ),
        hovermode="closest",
        dragmode="pan",
    )

    # Barra de cor (legenda de score)
    fig.add_trace(go.Scatter(
        x=[None], y=[None],
        mode="markers",
        marker=dict(
            colorscale=COLORSCALE,
            showscale=True,
            cmin=0, cmax=score_max,
            colorbar=dict(
                title=dict(text="Score", side="right"),
                thickness=12, len=0.6,
                tickfont=dict(size=10),
            ),
        ),
        hoverinfo="skip",
        showlegend=False,
    ))

    return fig

# endregion


# region ====================== SESSÃO 5: Ponto de entrada =====================

def render_unifilar_dual(df: pd.DataFrame, gerencia: str = "SP"):
    """
    Renderiza o unifilar dual VP+EE com nível de detalhe configurável.

    Controles exibidos acima do gráfico:
    - Nível de agrupamento: Ramal | Pátio | Trecho
    - Multiselect de ramais (filtra quais ramais aparecem)
    - Checkbox para mostrar apenas hot-spots críticos

    Args:
        df: DataFrame já filtrado e com score calculado
        gerencia: 'SP', 'VP' ou 'GERAL'
    """
    if df.empty:
        st.info("ℹ️ Sem dados para o unifilar. Aplique um upload de dados primeiro.")
        return

    # ── Controles acima do gráfico ───────────────────────────────────────────
    col_nivel, col_ramais, col_crit = st.columns([1, 3, 1])

    with col_nivel:
        nivel = st.selectbox(
            "🔎 Nível de detalhe",
            options=["Ramal", "Pátio", "Trecho"],
            index=0,
            help=(
                "Ramal = visão ampla (1 bolha por ramal)\n"
                "Pátio = detalha os pátios de origem\n"
                "Trecho = máximo detalhe (par Origem→Destino)"
            ),
            key=f"unif_nivel_{gerencia}",
        )

    with col_ramais:
        # Ramais disponíveis nos dados (normalizados)
        if "ramal" in df.columns:
            ramais_disp = sorted(df["ramal"].dropna().unique())
        else:
            ramais_disp = []

        # Monta labels nome completo → sigla
        opcoes_label = {
            nome_ramal(s, "completo_sigla"): s
            for s in ramais_disp
        }

        selecionados_nome = st.multiselect(
            "🚂 Ramais visíveis",
            options=list(opcoes_label.keys()),
            default=list(opcoes_label.keys()),
            help="Desmarque ramais para removê-los do unifilar",
            key=f"unif_ramais_{gerencia}",
        )

        # Converte de volta para siglas (uso interno no DataFrame)
        ramais_sel_sigla = [opcoes_label[n] for n in selecionados_nome]

    with col_crit:
        apenas_criticos = st.checkbox(
            "🔴 Só críticos",
            value=False,
            help="Mostra apenas pontos com score acima de 75% do máximo",
            key=f"unif_crit_{gerencia}",
        )

    # ── Filtra pelos ramais selecionados ─────────────────────────────────────
    df_plot = df.copy()

    if ramais_sel_sigla and "ramal" in df_plot.columns:
        df_plot = df_plot[df_plot["ramal"].isin(ramais_sel_sigla)]

    if df_plot.empty:
        st.warning("Nenhum dado com os ramais selecionados.")
        return

    # ── Filtra hot-spots críticos se pedido ──────────────────────────────────
    if apenas_criticos and "score" in df_plot.columns:
        limiar = df_plot["score"].quantile(0.75)
        df_plot = df_plot[df_plot["score"] >= limiar]
        if df_plot.empty:
            st.info("Sem hot-spots críticos com os filtros aplicados.")
            return

    # ── Agrega no nível escolhido ────────────────────────────────────────────
    agg = _agregar(df_plot, nivel)

    if agg.empty:
        st.warning("Dados insuficientes para montar o unifilar.")
        return

    # ── Atribui posições x ───────────────────────────────────────────────────
    agg = _atribuir_posicoes_x(agg, nivel)

    # ── Constrói e exibe figura ──────────────────────────────────────────────
    fig = _construir_figura(agg, gerencia, nivel)
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})

    # ── Resumo em texto abaixo do gráfico ────────────────────────────────────
    n_pontos = len(agg)
    n_ramais = agg["ramal_sigla"].nunique() if "ramal_sigla" in agg.columns else "?"
    st.caption(
        f"📍 {n_pontos} pontos exibidos · "
        f"🚂 {n_ramais} ramal(is) · "
        f"Nível: {nivel} · "
        f"Use o scroll do mouse para zoom"
    )

    # ── Tabela drill-down (expander) ─────────────────────────────────────────
    with st.expander("📋 Ver tabela detalhada dos pontos"):
        tab_exib = agg[["label", "disciplina", "qtd", "score_med", "lt_med", "top_defeitos"]].copy()
        tab_exib.columns = ["Ponto", "Disciplina", "Qtd. Notas", "Score Médio", "Lead Time (dias)", "Top Defeitos"]
        tab_exib["Score Médio"] = tab_exib["Score Médio"].round(1)
        tab_exib["Lead Time (dias)"] = tab_exib["Lead Time (dias)"].round(0).astype(int)
        tab_exib = tab_exib.sort_values("Score Médio", ascending=False)
        # Remove HTML das células de defeitos para exibição limpa
        tab_exib["Top Defeitos"] = tab_exib["Top Defeitos"].str.replace("<br>", " | ", regex=False).str.replace("•", "→", regex=False)
        st.dataframe(tab_exib, use_container_width=True, hide_index=True)

# endregion
