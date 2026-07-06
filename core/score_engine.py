# core/score_engine.py
# Motor de Score Composto configurável + Painel de Transparência
# Sprint 3 — Visualizações por Gerência
#
# Fórmula:
#   Score = peso_prio × mult_status × mult_familia × mult_tipo × (1 + α × anos_aberta)
#
# USO:
#   from core.score_engine import render_score_sidebar, calcular_score, render_painel_transparencia
#
#   config = render_score_sidebar(disciplina="VP")
#   df     = calcular_score(df, config)
#   render_painel_transparencia(df, config)

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date
from dataclasses import dataclass, field

# region ====================== SESSÃO 1: Pesos padrão ========================

# Fonte: 05_PADROES_TECNICOS.md
PESO_PRIORIDADE_PADRAO = {
    "1-Muito alta": 4,
    "2-Alta":       3,
    "3-Média":      2,
    "4-Baixa":      1,
}

MULT_STATUS_PADRAO = {
    "ABER": 1.0,
    "DIFE": 0.5,
}

MULT_TIPO_PADRAO = {
    "CT": 1.5,
    "PV": 1.0,
}

MULT_FAMILIA_VP_PADRAO = {
    "Trilho":            1.5,
    "Geometria":         1.5,
    "AMV":               1.5,
    "Dormente":          1.2,
    "Lastro":            1.2,
    "Junta":             1.0,
    "Solda":             1.0,
    "Cota Salvaguarda":  1.0,
    "Geral Manutenção":  0.8,
    "Outros":            1.0,
}

MULT_FAMILIA_EE_PADRAO = {
    "Wayside":               1.5,
    "Sinalização":           1.3,
    "Energia":               1.2,
    "Sinalização Específica":1.1,
    "Telecomunicações":      1.0,
    "Outros":                1.0,
}

ALPHA_PADRAO = 0.10  # 10% por ano em aberto

# endregion


# region ====================== SESSÃO 2: Dataclass de Configuração ============

@dataclass
class ScoreConfig:
    """
    Configuração imutável do motor de score — criada pelo render_score_sidebar()
    e passada para calcular_score() e render_painel_transparencia().

    Atributos:
        disciplina:      'VP', 'EE' ou 'VP+EE'
        alpha_idade:     peso do fator de envelhecimento (0–1)
        usar_status:     ativa o multiplicador ABER/DIFE
        usar_tipo:       ativa o multiplicador CT/PV
        usar_familia:    ativa o multiplicador por família de defeito
        mult_familia:    dict {familia: multiplicador} ajustado pelo usuário
        peso_prio:       dict {prioridade: peso base}
    """
    disciplina:   str
    alpha_idade:  float = ALPHA_PADRAO
    usar_status:  bool  = True
    usar_tipo:    bool  = True
    usar_familia: bool  = True
    mult_familia: dict  = field(default_factory=dict)
    peso_prio:    dict  = field(default_factory=lambda: PESO_PRIORIDADE_PADRAO.copy())

# endregion


# region ====================== SESSÃO 3: Sidebar de configuração ==============

def render_score_sidebar(disciplina: str) -> ScoreConfig:
    """
    Renderiza controles do score na sidebar e retorna ScoreConfig.

    A renderização usa um expander para não poluir a sidebar.

    Args:
        disciplina: 'VP', 'EE' ou 'VP+EE'

    Returns:
        ScoreConfig populado com as escolhas do usuário
    """
    mult_familia_base = (
        MULT_FAMILIA_EE_PADRAO
        if disciplina == "EE"
        else MULT_FAMILIA_VP_PADRAO
    )

    with st.sidebar.expander("⚖️ Configurar Score", expanded=False):
        st.caption("Ajuste os fatores do score composto:")

        # ── α idade ─────────────────────────────────────────────────────────
        alpha = st.slider(
            "🕰️ Fator Idade (α)",
            min_value=0.0,
            max_value=0.5,
            value=ALPHA_PADRAO,
            step=0.01,
            format="%.2f",
            help="Incremento de score por ano que a nota permanece aberta. "
                 "α=0.10 → nota com 2 anos = +20% de score.",
            key=f"alpha_{disciplina}",
        )

        # ── Status (ABER/DIFE) ────────────────────────────────────────────────
        usar_status = st.checkbox(
            "📍 Penalizar DIFE (×0.5)",
            value=True,
            help="Notas com status DIFE (diferido) recebem peso 0.5 — indicam "
                 "pendência reconhecida mas ainda não atacada.",
            key=f"status_{disciplina}",
        )

        # ── Tipo de atividade (CT/PV) ─────────────────────────────────────────
        usar_tipo = st.checkbox(
            "🛠️ Ampliar CT (×1.5)",
            value=True,
            help="Notas do tipo CT (corretiva) pesam 50% a mais que PV "
                 "(preventiva) — indicam falha já ocorrida.",
            key=f"tipo_{disciplina}",
        )

        # ── Multiplicadores por família ────────────────────────────────────────
        usar_familia = st.checkbox(
            "🏷️ Multiplicador por Família",
            value=True,
            help="Aplica pesos diferenciados por família de defeito "
                 "(ex.: Trilho e AMV pesam mais em VP).",
            key=f"familia_ativo_{disciplina}",
        )

        mult_familia_config = {}
        if usar_familia:
            with st.expander("🔧 Ajustar pesos de família", expanded=False):
                for familia, mult_default in mult_familia_base.items():
                    mult_familia_config[familia] = st.slider(
                        familia,
                        min_value=0.5,
                        max_value=3.0,
                        value=float(mult_default),
                        step=0.1,
                        key=f"fam_{disciplina}_{familia}",
                    )
        else:
            mult_familia_config = {k: 1.0 for k in mult_familia_base}

    return ScoreConfig(
        disciplina=disciplina,
        alpha_idade=alpha,
        usar_status=usar_status,
        usar_tipo=usar_tipo,
        usar_familia=usar_familia,
        mult_familia=mult_familia_config or {k: 1.0 for k in mult_familia_base},
        peso_prio=PESO_PRIORIDADE_PADRAO.copy(),
    )

# endregion


# region ====================== SESSÃO 4: Cálculo do Score ====================

def calcular_score(df: pd.DataFrame, config: ScoreConfig) -> pd.DataFrame:
    """
    Aplica o score composto ao DataFrame e retorna df com coluna 'score' atualizada.

    Fórmula:
        score = peso_prio
              × mult_status       (se config.usar_status)
              × mult_familia      (se config.usar_familia)
              × mult_tipo         (se config.usar_tipo)
              × (1 + α × anos_aberta)

    Proteções:
      - Prioridade ausente → peso 1
      - Status ausente → mult 1.0
      - Família ausente → mult 1.0
      - Tipo ausente → mult 1.0
      - Data ausente ou futura → anos_aberta = 0

    Args:
        df:     DataFrame com as notas
        config: ScoreConfig gerado pelo render_score_sidebar

    Returns:
        DataFrame com coluna 'score' recalculada
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    hoje = pd.Timestamp.now().normalize()

    # ── 4.1: Peso de prioridade ───────────────────────────────────────────────
    if "prioridade" in df.columns:
        df["_peso_prio"] = df["prioridade"].map(config.peso_prio).fillna(1)
    else:
        df["_peso_prio"] = 1.0

    # ── 4.2: Multiplicador de status ─────────────────────────────────────────
    if config.usar_status and "status_usuario" in df.columns:
        df["_mult_status"] = (
            df["status_usuario"]
            .str.upper()
            .map(MULT_STATUS_PADRAO)
            .fillna(1.0)
        )
    else:
        df["_mult_status"] = 1.0

    # ── 4.3: Multiplicador de família ─────────────────────────────────────────
    if config.usar_familia:
        col_fam = "familia_defeito" if "familia_defeito" in df.columns else (
                  "familia_cod"   if "familia_cod"   in df.columns else None)
        if col_fam:
            df["_mult_familia"] = df[col_fam].map(config.mult_familia).fillna(1.0)
        else:
            df["_mult_familia"] = 1.0
    else:
        df["_mult_familia"] = 1.0

    # ── 4.4: Multiplicador de tipo de atividade ───────────────────────────────
    if config.usar_tipo and "tipo_atividade" in df.columns:
        df["_mult_tipo"] = (
            df["tipo_atividade"]
            .str.upper()
            .map(MULT_TIPO_PADRAO)
            .fillna(1.0)
        )
    else:
        df["_mult_tipo"] = 1.0

    # ── 4.5: Fator de idade ───────────────────────────────────────────────────
    # anos_aberta = (hoje - data_nota) / 365  — clampado em [0, inf]
    if "data_nota" in df.columns:
        df["_data_nota_ts"] = pd.to_datetime(df["data_nota"], errors="coerce")
        df["_anos_aberta"] = (
            (hoje - df["_data_nota_ts"]).dt.days / 365
        ).clip(lower=0).fillna(0)
    else:
        df["_anos_aberta"] = 0.0

    # ── 4.6: Score final ──────────────────────────────────────────────────────
    df["score"] = (
        df["_peso_prio"]
        * df["_mult_status"]
        * df["_mult_familia"]
        * df["_mult_tipo"]
        * (1 + config.alpha_idade * df["_anos_aberta"])
    ).round(2)

    # Remove colunas auxiliares (prefixo _)
    df.drop(columns=[c for c in df.columns if c.startswith("_")], inplace=True)

    return df

# endregion


# region ====================== SESSÃO 5: Painel de Transparência ==============

def render_painel_transparencia(df: pd.DataFrame, config: ScoreConfig) -> None:
    """
    Exibe painel explicativo mostrando como o score foi calculado e o impacto
    de cada fator na distribuição final.

    Conteúdo:
      - Tabela de pesos ativos
      - Histograma de distribuição de scores
      - Indicadores de impacto por fator

    Args:
        df:     DataFrame com coluna 'score' calculada
        config: ScoreConfig usado no cálculo
    """
    if df is None or df.empty or "score" not in df.columns:
        st.info("📭 Score não calculado ainda.")
        return

    st.markdown("---")
    st.markdown(
        """
        <div style='
            background:rgba(30,58,95,0.05);
            border-left:4px solid #1e3a5f;
            border-radius:8px;
            padding:10px 16px;
            margin-bottom:12px;
        '>
        <b>🔍 Painel de Transparência do Score</b><br/>
        <span style='font-size:12px;color:#6b7280;'>
        Entenda como cada fator contribui para o score composto.
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1.2, 2])

    with c1:
        st.markdown("**⚙️ Fatores ativos**")

        fatores = [
            ("🕰️ Fator Idade (α)",       f"{config.alpha_idade:.2f}",  True),
            ("📍 Penalizar DIFE",         "×0.5",  config.usar_status),
            ("🛠️ Ampliar CT",            "×1.5",  config.usar_tipo),
            ("🏷️ Mult. por Família",     "variável", config.usar_familia),
        ]

        for nome, valor, ativo in fatores:
            cor = "#16a34a" if ativo else "#9ca3af"
            icone = "✅" if ativo else "⬜"
            st.markdown(
                f"<div style='font-size:13px; color:{cor}; margin-bottom:4px;'>"
                f"{icone} {nome}: <b>{valor}</b></div>",
                unsafe_allow_html=True,
            )

        # Resumo estatístico
        st.markdown("---")
        st.markdown("**📊 Distribuição**")
        scores = df["score"].dropna()
        st.metric("Score Mínimo",  f"{scores.min():.1f}")
        st.metric("Score Médio",   f"{scores.mean():.1f}")
        st.metric("Score Máximo",  f"{scores.max():.1f}")
        st.metric("Desvio Padrão", f"{scores.std():.1f}")

    with c2:
        # Histograma de distribuição de scores
        fig = go.Figure()
        fig.add_trace(
            go.Histogram(
                x=df["score"].dropna(),
                nbinsx=30,
                marker=dict(
                    color="#1e3a5f",
                    line=dict(color="#ffffff", width=0.5),
                ),
                opacity=0.85,
                name="Notas",
            )
        )

        # Linha de score médio
        media = df["score"].mean()
        fig.add_vline(
            x=media,
            line_dash="dash",
            line_color="#ffb000",
            annotation_text=f"  Média: {media:.1f}",
            annotation_font_color="#ffb000",
        )

        # Linha de threshold top 10%
        p90 = df["score"].quantile(0.90)
        fig.add_vline(
            x=p90,
            line_dash="dot",
            line_color="#dc2626",
            annotation_text=f"  Top 10%: {p90:.1f}",
            annotation_font_color="#dc2626",
        )

        fig.update_layout(
            title=f"Distribuição de Scores — {config.disciplina}",
            xaxis_title="Score",
            yaxis_title="Nº de Notas",
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font_color="#1f2937",
            title_font=dict(color="#1e3a5f", size=13),
            margin=dict(l=10, r=10, t=40, b=30),
            height=300,
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

# Alias de compatibilidade — parser.py do Sprint 1 usa este nome
aplicar_score_dataframe = calcular_score

# endregion
