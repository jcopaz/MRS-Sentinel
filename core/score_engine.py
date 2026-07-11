# =============================================================================
# core/score_engine.py — Motor de Score Composto
# Sprint 3 — MRS Sentinel (fórmula estendida na Sprint 4.5)
#
# Fórmula:
#   Score = peso_prio × mult_status × mult_familia × mult_tipo
#         × (1 + α × anos_aberta)
#         × (1 + β × (n_ocorrencias_local - 1))
#
# mult_status: neutro (1.0) para todos os códigos desde 10/07/2026 — decisão
#   do Julio de não penalizar/bonificar por status, só por tempo aberto e
#   criticidade do local/família.
# n_ocorrencias_local: reincidência do mesmo defeito no mesmo local — conta
#   quantas notas do DataFrame atual compartilham ramal+origem+familia_defeito
#   (mesma granularidade do motor de alertas, core/alertas.py).
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
    "DIFE": 1.0,   # diferida = peso neutro (decisão do Julio, 10/07/2026 — Sprint 4.5)
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

# Reincidência: mesmo ramal+origem+familia_defeito repetido no DataFrame atual.
# Mesma granularidade de "local" usada em core/alertas.py (hot-spots crônicos).
BETA_REINCIDENCIA_PADRAO = 0.15       # +15% de score por ocorrência repetida no local
REINCIDENCIA_MULT_MAX_PADRAO = 3.0    # trava o multiplicador (evita disparo com clusters gigantes)

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

    # Reincidência: peso extra por nota repetida no mesmo ramal+origem+família
    beta_reincidencia:      float = BETA_REINCIDENCIA_PADRAO
    reincidencia_mult_max:  float = REINCIDENCIA_MULT_MAX_PADRAO

    # Flags de ativação (permite desligar componentes do score)
    usar_familia:      bool = True
    usar_tipo:         bool = True
    usar_idade:        bool = True
    usar_reincidencia: bool = True

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
        score = peso_prio × mult_status × mult_familia × mult_tipo
              × (1 + α × anos_aberta) × (1 + β × (n_ocorrencias_local - 1))

    Args:
        row: Series com campos peso_prio, status_usuario, familia_defeito,
             tipo_nota, data_nota, disciplina_label, n_ocorrencias_local
             (esta última pré-calculada por calcular_score_dataframe — ver
             Sessão 4; ausente aqui = trata como ocorrência única)
        cfg: ScoreConfig com pesos configuráveis

    Returns:
        float: score arredondado a 2 casas decimais
    """
    # Guarda defensiva: se cfg não for ScoreConfig (ex: string passada por engano),
    # usa configuração padrão em vez de explodir com AttributeError
    if not isinstance(cfg, ScoreConfig):
        cfg = ScoreConfig()

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

    # Fator de reincidência: mesmo defeito repetido no mesmo local
    # (ramal + origem + familia_defeito). n_ocorrencias_local vem pré-calculado
    # por calcular_score_dataframe; se ausente, assume ocorrência única (sem efeito).
    if cfg.usar_reincidencia:
        n_local = row.get("n_ocorrencias_local", 1)
        try:
            n_local = int(n_local) if pd.notna(n_local) else 1
        except (TypeError, ValueError):
            n_local = 1
        mult_reinc = 1 + cfg.beta_reincidencia * max(0, n_local - 1)
        mult_reinc = min(mult_reinc, cfg.reincidencia_mult_max)
        score *= mult_reinc

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

    # Guarda defensiva: se cfg não for ScoreConfig (ex: string passada por engano),
    # usa configuração padrão em vez de explodir com AttributeError
    if cfg is None or not isinstance(cfg, ScoreConfig):
        cfg = ScoreConfig()

    df = df.copy()

    # Pré-calcula reincidência local (ramal+origem+familia_defeito) ANTES do
    # apply por linha — precisa ver o DataFrame inteiro para contar ocorrências.
    # Mesma granularidade de "local" do motor de alertas (core/alertas.py).
    grupo_cols = ["ramal", "origem", "familia_defeito"]
    if cfg.usar_reincidencia and all(c in df.columns for c in grupo_cols):
        df["n_ocorrencias_local"] = (
            df.groupby(grupo_cols, dropna=False)[grupo_cols[0]].transform("size")
        )
    else:
        df["n_ocorrencias_local"] = 1

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

        # ── Reincidência no local ────────────────────────────────────────────
        cfg.usar_reincidencia = st.checkbox(
            "🔁 Penalizar reincidência no mesmo local",
            value=True,
            key=f"sc_usar_reincidencia_{gerencia}",
            help="Mesmo ramal+pátio+família com múltiplas notas pesa mais — "
                 "mesma lógica dos hot-spots crônicos (aba Alertas).",
        )
        if cfg.usar_reincidencia:
            cfg.beta_reincidencia = st.slider(
                "β — Acréscimo por ocorrência repetida",
                min_value=0.0, max_value=0.5,
                value=BETA_REINCIDENCIA_PADRAO, step=0.01,
                format="%.2f",
                key=f"sc_beta_reinc_{gerencia}",
                help="0.15 = +15% por repetição. 4ª nota no mesmo local → ×1.45",
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
                  × Multiplicador Status (neutro — ver nota abaixo)
                  × Multiplicador Família
                  × Multiplicador Tipo
                  × (1 + α × Anos em aberto)
                  × (1 + β × Ocorrências repetidas no mesmo local - 1)
            ```
            """
        )
        st.caption(
            "ℹ️ Status (ABER/DIFE/etc.) não pondera mais o score — decisão de "
            "10/07/2026. A criticidade agora vem de: tempo aberto, família do "
            "defeito e reincidência no mesmo local (ramal+pátio+família)."
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

            st.markdown("**🔁 Reincidência no local**")
            if cfg.usar_reincidencia:
                st.success(f"✅ Ativa — β = {cfg.beta_reincidencia:.2f} (+{cfg.beta_reincidencia*100:.0f}% por repetição, teto ×{cfg.reincidencia_mult_max:.1f})")
                st.caption("Exemplo: 4ª nota no mesmo ramal+pátio+família → ×{:.2f}".format(
                    min(1 + cfg.beta_reincidencia * 3, cfg.reincidencia_mult_max)
                ))
            else:
                st.info("⏸️ Desativada")

        st.caption(
            "ℹ️ Scores altos = maior criticidade. Use os controles em "
            "⚙️ Score na sidebar para ajustar os pesos."
        )

# endregion


# =============================================================================
# Aliases de compatibilidade
# core/parser.py (Sprint 2) importa pelo nome antigo 'aplicar_score_dataframe'.
# O alias garante retrocompatibilidade sem alterar o parser.
# =============================================================================
aplicar_score_dataframe = calcular_score_dataframe
