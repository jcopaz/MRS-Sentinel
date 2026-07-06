# core/indicadores.py
# Indicadores integrados VP + EE: IMT, DI e derivados
# Sprint 4 — Visão Geral + Admin
#
# IMT = Índice de Manutenção Total
#       Mede a pressão de manutenção em função do volume e criticidade das notas
#       IMT = (Σ score) / km_malha × fator_disciplina
#
# DI  = Densidade de Intervenção
#       DI  = n_notas / km_malha
#
# USO:
#   from core.indicadores import calcular_imt, calcular_di, render_indicadores_geral

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from core.glossarios import nome_ramal

# region ====================== SESSÃO 1: Constantes ==========================

# Extensão aproximada de malha por gerência (km) — atualizar conforme dado real
KM_MALHA = {
    "SP": 320.0,   # Gerência SP
    "VP": 410.0,   # Gerência VP
    "total": 730.0,
}

# Fator de peso disciplina para IMT
FATOR_DISCIPLINA = {
    "VP": 1.0,
    "EE": 0.8,   # EE tem impacto operacional diferente — ajustável
}

# Referências para semáforo de IMT (calibrar com a equipe MRS)
IMT_CRITICO  = 5.0   # acima → vermelho
IMT_ATENCAO  = 2.5   # acima → amarelo
# abaixo de IMT_ATENCAO → verde

# endregion


# region ====================== SESSÃO 2: Cálculo dos indicadores =============

def calcular_imt(
    df: pd.DataFrame,
    gerencia: str,
    disciplina: str = "VP",
) -> float:
    """
    Calcula o IMT — Índice de Manutenção Total.

    Fórmula:
        IMT = (Σ score_notas_abertas) / km_malha × fator_disciplina

    Protege contra divisão por zero e dados ausentes.

    Args:
        df:         DataFrame com notas (já filtradas)
        gerencia:   'SP' ou 'VP' — determina km_malha
        disciplina: 'VP' ou 'EE' — aplica fator de peso

    Returns:
        float: IMT arredondado a 2 casas, ou 0.0 em caso de erro
    """
    if df is None or df.empty:
        return 0.0

    km = KM_MALHA.get(gerencia, 1.0) or 1.0
    fator = FATOR_DISCIPLINA.get(disciplina, 1.0)

    # Soma apenas notas abertas
    df_aber = df.copy()
    if "status_usuario" in df_aber.columns:
        df_aber = df_aber[df_aber["status_usuario"].str.upper() == "ABER"]

    if "score" not in df_aber.columns or df_aber["score"].isna().all():
        # Fallback: conta notas abertas como proxy de score
        soma_score = len(df_aber) * 1.0
    else:
        soma_score = df_aber["score"].dropna().sum()

    imt = (soma_score / km) * fator
    return round(float(imt), 2)


def calcular_di(df: pd.DataFrame, gerencia: str) -> float:
    """
    Calcula DI — Densidade de Intervenção.

    Fórmula:
        DI = n_notas_abertas / km_malha

    Args:
        df:       DataFrame com notas
        gerencia: 'SP' ou 'VP'

    Returns:
        float: DI arredondado a 2 casas
    """
    if df is None or df.empty:
        return 0.0

    km = KM_MALHA.get(gerencia, 1.0) or 1.0

    df_aber = df.copy()
    if "status_usuario" in df_aber.columns:
        df_aber = df_aber[df_aber["status_usuario"].str.upper() == "ABER"]

    di = len(df_aber) / km
    return round(float(di), 2)


def calcular_aderencia(df: pd.DataFrame) -> float:
    """
    Calcula a Aderência ao Planejamento (%).

    Aderência = (notas encerradas dentro do prazo planejado) / total planejadas × 100

    Args:
        df: DataFrame com colunas data_planejada e data_encerramento

    Returns:
        float: percentual de aderência (0–100)
    """
    if df is None or df.empty:
        return 0.0
    if "data_planejada" not in df.columns or "data_encerramento" not in df.columns:
        return 0.0

    df_c = df.copy()
    df_c["data_planejada"]    = pd.to_datetime(df_c["data_planejada"],    errors="coerce")
    df_c["data_encerramento"] = pd.to_datetime(df_c["data_encerramento"], errors="coerce")

    df_plan = df_c.dropna(subset=["data_planejada"])
    if df_plan.empty:
        return 0.0

    # Considera "dentro do prazo" se encerrado antes ou na data planejada
    df_enc = df_plan.dropna(subset=["data_encerramento"])
    n_no_prazo = (df_enc["data_encerramento"] <= df_enc["data_planejada"]).sum()

    aderencia = (n_no_prazo / len(df_plan)) * 100
    return round(float(aderencia), 1)


def calcular_lead_time_medio(df: pd.DataFrame) -> float:
    """Lead time médio (dias) das notas com data_nota e data_encerramento."""
    if df is None or df.empty:
        return 0.0
    if "lead_time_dias" in df.columns:
        val = df["lead_time_dias"].dropna().mean()
        return round(float(val), 1) if not np.isnan(val) else 0.0
    return 0.0

# endregion


# region ====================== SESSÃO 3: Render dos indicadores ==============

def _semaforo_imt(imt: float) -> tuple[str, str]:
    """Retorna (emoji_cor, texto_status) baseado no valor do IMT."""
    if imt >= IMT_CRITICO:
        return "🔴", "Crítico"
    if imt >= IMT_ATENCAO:
        return "🟡", "Atenção"
    return "🟢", "Normal"


def render_indicadores_geral(
    df_sp_vp: pd.DataFrame | None,
    df_sp_ee: pd.DataFrame | None,
    df_vp_vp: pd.DataFrame | None,
    df_vp_ee: pd.DataFrame | None,
) -> None:
    """
    Renderiza o painel de indicadores integrados na Visão Geral.

    Exibe IMT e DI para cada combinação Gerência × Disciplina,
    mais indicadores consolidados (SP+VP).

    Args:
        df_sp_vp: notas SP - Via Permanente
        df_sp_ee: notas SP - Eletroeletrônica
        df_vp_vp: notas VP - Via Permanente
        df_vp_ee: notas VP - Eletroeletrônica
    """
    st.markdown(
        """
        <div style='
            background: rgba(30,58,95,0.05);
            border-left: 4px solid #1e3a5f;
            border-radius: 8px;
            padding: 10px 16px;
            margin-bottom: 12px;
        '>
        <b>📡 Indicadores Integrados MRS Sentinel</b>
        <span style='font-size:11px; color:#6b7280; margin-left:8px;'>
        IMT = Índice de Manutenção Total &nbsp;|&nbsp; DI = Densidade de Intervenção
        </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 3.1: Calcula todos os indicadores ────────────────────────────────────
    imt_sp_vp = calcular_imt(df_sp_vp, "SP", "VP")
    imt_sp_ee = calcular_imt(df_sp_ee, "SP", "EE")
    imt_vp_vp = calcular_imt(df_vp_vp, "VP", "VP")
    imt_vp_ee = calcular_imt(df_vp_ee, "VP", "EE")

    di_sp = calcular_di(_concat_safe(df_sp_vp, df_sp_ee), "SP")
    di_vp = calcular_di(_concat_safe(df_vp_vp, df_vp_ee), "VP")

    ader_sp = calcular_aderencia(_concat_safe(df_sp_vp, df_sp_ee))
    ader_vp = calcular_aderencia(_concat_safe(df_vp_vp, df_vp_ee))

    lt_sp = calcular_lead_time_medio(_concat_safe(df_sp_vp, df_sp_ee))
    lt_vp = calcular_lead_time_medio(_concat_safe(df_vp_vp, df_vp_ee))

    # ── 3.2: Tabela de IMT por gerência × disciplina ──────────────────────────
    st.markdown("#### 📊 IMT por Gerência × Disciplina")

    dados_imt = {
        "Gerência": ["SP", "SP", "VP", "VP"],
        "Disciplina": ["VP (Via Permanente)", "EE (Eletroeletrônica)", "VP (Via Permanente)", "EE (Eletroeletrônica)"],
        "IMT": [imt_sp_vp, imt_sp_ee, imt_vp_vp, imt_vp_ee],
    }
    df_imt = pd.DataFrame(dados_imt)

    # Gráfico de barras agrupadas IMT
    fig_imt = go.Figure()
    for ger in ["SP", "VP"]:
        sub = df_imt[df_imt["Gerência"] == ger]
        fig_imt.add_trace(go.Bar(
            name=f"Gerência {ger}",
            x=sub["Disciplina"],
            y=sub["IMT"],
            text=[f"{v:.2f}" for v in sub["IMT"]],
            textposition="outside",
            marker_color="#1e3a5f" if ger == "SP" else "#16a34a",
        ))

    fig_imt.add_hline(
        y=IMT_CRITICO, line_dash="dot", line_color="#dc2626",
        annotation_text=f"  Crítico ({IMT_CRITICO})",
        annotation_font_color="#dc2626",
    )
    fig_imt.add_hline(
        y=IMT_ATENCAO, line_dash="dash", line_color="#f59e0b",
        annotation_text=f"  Atenção ({IMT_ATENCAO})",
        annotation_font_color="#f59e0b",
    )
    fig_imt.update_layout(
        barmode="group",
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        margin=dict(l=10, r=10, t=20, b=40),
        height=280,
        legend=dict(orientation="h", y=1.08),
        yaxis=dict(title="IMT", showgrid=True, gridcolor="#f3f4f6"),
        font_color="#1f2937",
    )
    st.plotly_chart(fig_imt, use_container_width=True, config={"displaylogo": False})

    # ── 3.3: Cards de DI, Aderência e Lead time ────────────────────────────────
    st.markdown("#### 🏷️ Indicadores Operacionais")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    _mini_card(c1, "DI — SP", f"{di_sp:.1f}", "notas/km", "#1e3a5f")
    _mini_card(c2, "DI — VP", f"{di_vp:.1f}", "notas/km", "#16a34a")
    _mini_card(c3, "Aderência SP", f"{ader_sp:.0f}%", "ao planejado",
               "#16a34a" if ader_sp >= 80 else "#f59e0b" if ader_sp >= 60 else "#dc2626")
    _mini_card(c4, "Aderência VP", f"{ader_vp:.0f}%", "ao planejado",
               "#16a34a" if ader_vp >= 80 else "#f59e0b" if ader_vp >= 60 else "#dc2626")
    _mini_card(c5, "Lead Time SP", f"{lt_sp:.0f} d", "média geral", "#7c3aed")
    _mini_card(c6, "Lead Time VP", f"{lt_vp:.0f} d", "média geral", "#7c3aed")

    # ── 3.4: Semáforo de IMT ──────────────────────────────────────────────────
    st.markdown("#### 🚦 Semáforo de IMT")
    s1, s2, s3, s4 = st.columns(4)

    for col, imt, label in [
        (s1, imt_sp_vp, "SP — Via Permanente"),
        (s2, imt_sp_ee, "SP — Eletroeletrônica"),
        (s3, imt_vp_vp, "VP — Via Permanente"),
        (s4, imt_vp_ee, "VP — Eletroeletrônica"),
    ]:
        emoji, status = _semaforo_imt(imt)
        col.markdown(
            f"""
            <div style='
                background: #f8fafc;
                border-radius: 10px;
                border: 1px solid #e5e7eb;
                padding: 12px;
                text-align: center;
            '>
                <div style='font-size:28px;'>{emoji}</div>
                <div style='font-size:20px; font-weight:700; color:#1f2937;'>{imt:.2f}</div>
                <div style='font-size:10px; color:#6b7280;'>{label}</div>
                <div style='font-size:11px; font-weight:600; color:#4b5563;'>{status}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _concat_safe(
    df_a: pd.DataFrame | None,
    df_b: pd.DataFrame | None,
) -> pd.DataFrame:
    """Concatena dois DataFrames de forma segura, ignorando Nones vazios."""
    dfs = [d for d in [df_a, df_b] if d is not None and not d.empty]
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def _mini_card(col, titulo: str, valor: str, subtitulo: str, cor: str) -> None:
    """Card compacto para indicadores operacionais."""
    col.markdown(
        f"""
        <div style='
            background: #f8fafc;
            border-left: 3px solid {cor};
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        '>
            <div style='font-size:9px; color:#6b7280;'>{titulo}</div>
            <div style='font-size:20px; font-weight:700; color:{cor};'>{valor}</div>
            <div style='font-size:9px; color:#9ca3af;'>{subtitulo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# endregion
