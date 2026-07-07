# =============================================================================
# core/score_engine.py — Motor de Score Composto
# Sprint 3 — MRS Sentinel
#
# Fórmula:
#   Score = peso_prio × mult_status × mult_familia × mult_tipo × (1 + α × anos)
#
# Exporta:
#   ScoreConfig              — dataclass com pesos configuráveis
#   render_score_sidebar()   — painel sidebar com sliders
#   calcular_score_dataframe() — aplica score a todo o DataFrame
#   render_painel_transparencia() — exibe pesos ativos ao usuário
#
# Sessão 1: Imports & constantes de peso
# Sessão 2: ScoreConfig (dataclass)
# Sessão 3: calcular_score_linha() — cálculo por linha
# Sessão 4: calcular_score_dataframe() — vetorizado
# Sessão 5: render_score_sidebar() — controles na sidebar
# Sessão 6: render_painel_transparencia() — explicação dos pesos
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# Pesos base (conforme 05_PADROES_TECNICOS.md)
PESO_PRIORIDADE_PADRAO = {
    "1-Muito alta": 4,
    "2-Alta":       3,
    "3-Média":      2,
    "4-Baixa":      1,
}

MULT_STATUS_PADRAO = {
    "ABER": 1.0,   # nota aberta = peso total
    "DIFE": 0.5,   # diferida = metade do peso
}

MULT_FAMILIA_VP_PADRAO = {
    "Trilho":           1.5,
    "Geometria":        1.5,
    "AMV":              1.5,
    "Dormente":         1.2,
    "Lastro":           1.2,
    "Junta":            1.0,
    "Solda":            1.0,
    "Cota Salvaguarda": 1.0,
    "Geral Manutenção": 0.8,
    "Outros":           1.0,
}

MULT_FAMILIA_EE_PADRAO = {
    "Wayside":               1.5,
    "Sinalização":           1.3,
    "Energia":               1.2,
    "Telecomunicações":      1.0,
    "Sinalização Específica":1.1,
    "Outros":                1.0,
}

MULT_TIPO_PADRAO = {
    "CT": 1.5,   # corretiva = mais urgente
    "PV": 1.0,   # preventiva
}

ALPHA_PADRAO = 0.10  # 10% de acréscimo por ano aberto

# endregion


# region ====================== SESSÃO 2: ScoreConfig ==========================

@dataclass
class ScoreConfig:
    """
    Configuração completa dos pesos do score composto.
    Todos os campos têm valores padrão — basta instanciar sem argumentos
    para obter o comportamento canônico.
    """
    # Multiplicador de idade (% por ano em aberto)
    alpha: float = ALPHA_PADRAO

    # Pesos configuráveis via sidebar
    peso_prioridade: dict = field(default_factory=lambda: dict(PESO_PRIORIDADE_PADRAO))
    mult_status:     dict = field(default_factory=lambda: dict(MULT_STATUS_PADRAO))
    mult_familia_vp: dict = field(default_factory=lambda: dict(MULT_FAMILIA_VP_PADRAO))
    mult_familia_ee: dict = field(default_factory=lambda: dict(MULT_FAMILIA_EE_PADRAO))
    mult_tipo:       dict = field(default_factory=lambda: dict(MULT_TIPO_PADRAO))

    # Flags de ativação (permite desligar componentes do score)
    usar_familia:    bool = True
    usar_tipo:       bool = True
    usar_idade:      bool = True

# endregion


# region ====================== SESSÃO 3: Cálculo por linha ====================

def _anos_abertos(data_nota) -> float:
    """
    Calcula quantos anos a nota está aberta até hoje.
    Defensivo: retorna 0 se data for inválida.
    """
    try:
        if pd.isna(data_nota):
            return 0.0
        dt = pd.Timestamp(data_nota)
        delta = (pd.Timestamp(date.today()) - dt).days
        return max(delta / 365.25, 0.0)
    except Exception:
        return 0.0


def calcular_score_linha(row: pd.Series, cfg: ScoreConfig) -> float:
    """
    Calcula o score composto de uma linha do DataFrame.

    Fórmula:
        score = peso_prio × mult_status × mult_familia × mult_tipo × (1 + α × anos)

    Args:
        row: Series com campos peso_prio, status_usuario, familia_defeito,
             tipo_nota, data_nota, disciplina_label
        cfg: ScoreConfig com pesos configuráveis

    Returns:
        float: score arredondado a 2 casas decimais
    """
    # Base: peso de prioridade
    prio_raw = str(row.get("prioridade", "4-Baixa")).strip()
    score = float(cfg.peso_prioridade.get(prio_raw, 1))

    # Usa peso_prio direto se disponível (mais preciso)
    peso_prio_col = row.get("peso_prio")
    if peso_prio_col and not pd.isna(peso_prio_col):
        score = float(peso_prio_col)

    # Multiplicador de status
    status_raw = str(row.get("status_usuario", "ABER")).strip().upper()[:4]
    score *= cfg.mult_status.get(status_raw, 1.0)

    # Multiplicador de família (VP ou EE)
    if cfg.usar_familia:
        disc = str(row.get("disciplina_label", row.get("disciplina", "VP"))).upper()
        familia = str(row.get("familia_defeito", row.get("familia_cod", "Outros"))).strip()
        if "EE" in disc:
            score *= cfg.mult_familia_ee.get(familia, 1.0)
        else:
            score *= cfg.mult_familia_vp.get(familia, 1.0)

    # Multiplicador de tipo de nota
    if cfg.usar_tipo:
        tipo = str(row.get("tipo_nota", "PV")).strip().upper()[:2]
        score *= cfg.mult_tipo.get(tipo, 1.0)

    # Fator de envelhecimento
    if cfg.usar_idade:
        anos = _anos_abertos(row.get("data_nota"))
        score *= (1 + cfg.alpha * anos)

    return round(score, 2)

# endregion


# region ====================== SESSÃO 4: Vetorizado ===========================

def calcular_score_dataframe(df: pd.DataFrame, cfg: Optional[ScoreConfig] = None) -> pd.DataFrame:
    """
    Aplica o score composto a todo o DataFrame de forma eficiente.

    Cria (ou sobrescreve) a coluna 'score' em cada linha.
    Defensivo: se o DataFrame estiver vazio, retorna sem modificar.

    Args:
        df: DataFrame com notas
        cfg: ScoreConfig; se None, usa configuração padrão

    Returns:
        DataFrame com coluna 'score' adicionada/atualizada
    """
    if df.empty:
        return df

    if cfg is None:
        cfg = ScoreConfig()

    df = df.copy()

    # Aplica por linha (axis=1)
    # Nota: para datasets muito grandes (>100k), considerar vetorização numpy
    df["score"] = df.apply(lambda row: calcular_score_linha(row, cfg), axis=1)

    return df

# endregion


# region ====================== SESSÃO 5: Sidebar de configuração ==============

def render_score_sidebar(gerencia: str = "SP") -> ScoreConfig:
    """
    Renderiza o painel de configuração de score na sidebar.
    Usa st.expander para não poluir a sidebar com muitos controles.

    Args:
        gerencia: 'SP', 'VP' ou 'GERAL' — usado no título do expander

    Returns:
        ScoreConfig com os pesos escolhidos pelo usuário
    """
    cfg = ScoreConfig()

    with st.expander(f"⚙️ Score — {gerencia}", expanded=False):

        # ── Alpha (envelhecimento) ────────────────────────────────────────────
        cfg.usar_idade = st.checkbox(
            "📅 Penalizar notas antigas",
            value=True,
            key=f"sc_usar_idade_{gerencia}",
            help="Acrescenta peso para notas abertas há mais tempo",
        )
        if cfg.usar_idade:
            cfg.alpha = st.slider(
                "α — Acréscimo por ano em aberto",
                min_value=0.0, max_value=0.5,
                value=ALPHA_PADRAO, step=0.01,
                format="%.2f",
                key=f"sc_alpha_{gerencia}",
                help="0.10 = +10% por ano. Nota com 2 anos → ×1.20",
            )

        st.markdown("---")

        # ── Família de defeito ────────────────────────────────────────────────
        cfg.usar_familia = st.checkbox(
            "🔩 Multiplicar por família de defeito",
            value=True,
            key=f"sc_usar_familia_{gerencia}",
        )

        st.markdown("---")

        # ── Tipo de nota ──────────────────────────────────────────────────────
        cfg.usar_tipo = st.checkbox(
            "📋 Multiplicar por tipo (CT/PV)",
            value=True,
            key=f"sc_usar_tipo_{gerencia}",
            help="CT (Corretiva) = ×1.5 · PV (Preventiva) = ×1.0",
        )

        st.markdown("---")

        # ── Pesos de prioridade ───────────────────────────────────────────────
        st.markdown("**🎯 Pesos de prioridade**")
        col1, col2 = st.columns(2)
        with col1:
            cfg.peso_prioridade["1-Muito alta"] = st.number_input(
                "Muito Alta", min_value=1, max_value=10,
                value=4, step=1, key=f"sc_p1_{gerencia}",
            )
            cfg.peso_prioridade["3-Média"] = st.number_input(
                "Média", min_value=1, max_value=10,
                value=2, step=1, key=f"sc_p3_{gerencia}",
            )
        with col2:
            cfg.peso_prioridade["2-Alta"] = st.number_input(
                "Alta", min_value=1, max_value=10,
                value=3, step=1, key=f"sc_p2_{gerencia}",
            )
            cfg.peso_prioridade["4-Baixa"] = st.number_input(
                "Baixa", min_value=1, max_value=10,
                value=1, step=1, key=f"sc_p4_{gerencia}",
            )

    return cfg

# endregion


# region ====================== SESSÃO 6: Painel de transparência ==============

def render_painel_transparencia(cfg: ScoreConfig):
    """
    Exibe um painel explicando os pesos ativos do score.
    Fundamental para que gestores entendam como o ranking é calculado.

    Args:
        cfg: ScoreConfig com os pesos configurados pelo usuário
    """
    with st.expander("🔍 Como o score é calculado?", expanded=False):
        st.markdown(
            """
            **Fórmula:**
            ```
            Score = Peso Prioridade
                  × Multiplicador Status
                  × Multiplicador Família
                  × Multiplicador Tipo
                  × (1 + α × Anos em aberto)
            ```
            """
        )

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("**🎯 Pesos de prioridade ativos**")
            df_prio = pd.DataFrame(
                list(cfg.peso_prioridade.items()),
                columns=["Prioridade", "Peso Base"]
            )
            st.dataframe(df_prio, hide_index=True, use_container_width=True)

            st.markdown("**📋 Status**")
            df_status = pd.DataFrame(
                list(cfg.mult_status.items()),
                columns=["Status", "Multiplicador"]
            )
            st.dataframe(df_status, hide_index=True, use_container_width=True)

        with col_b:
            st.markdown("**📅 Envelhecimento**")
            if cfg.usar_idade:
                st.success(f"✅ Ativo — α = {cfg.alpha:.2f} (+{cfg.alpha*100:.0f}% por ano)")
                st.caption("Exemplo: nota com 3 anos → ×{:.2f}".format(1 + cfg.alpha * 3))
            else:
                st.info("⏸️ Desativado")

            st.markdown("**🔩 Família**")
            st.success("✅ Ativa") if cfg.usar_familia else st.info("⏸️ Desativada")

            st.markdown("**📋 Tipo CT/PV**")
            st.success("✅ Ativo") if cfg.usar_tipo else st.info("⏸️ Desativado")

        st.caption(
            "ℹ️ Scores altos = maior criticidade. Use os controles em "
            "⚙️ Score na sidebar para ajustar os pesos."
        )

# endregion
