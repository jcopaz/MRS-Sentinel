# =============================================================================
# core/indicadores.py — Indicadores IMT, DI, Aderência e Lead Time
# Sprint 4 — MRS Sentinel
#
# Exporta:
#   calcular_imt()             — Índice de Manutenção Técnica
#   calcular_di()              — Desempenho de Intervenção
#   calcular_aderencia()       — Aderência ao Planejamento
#   calcular_lead_time_medio() — Lead Time Médio (dias)
#   render_indicadores_geral() — painel visual na aba Consolidado
#   render_semaforo()          — semáforo SP × VP de saúde da malha
#
# Sessão 1: Imports & constantes
# Sessão 2: Funções de cálculo
# Sessão 3: render_indicadores_geral()
# Sessão 4: render_semaforo()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# Limites de referência (podem ser sobrescritos via configuracoes no Supabase)
LIMITE_IMT_CRITICO  = 70.0   # IMT abaixo disso = crítico
LIMITE_IMT_ATENCAO  = 85.0   # IMT entre 70–85 = atenção
LIMITE_DI_CRITICO   = 60.0   # DI abaixo disso = crítico
LIMITE_DI_ATENCAO   = 80.0
LIMITE_ADH_CRITICO  = 70.0   # Aderência abaixo = crítico
LIMITE_ADH_ATENCAO  = 85.0
LIMITE_LT_CRITICO   = 60     # Lead Time acima = crítico (dias)
LIMITE_LT_ATENCAO   = 30     # Lead Time entre 30–60 = atenção

COR_CRIT = "#dc2626"
COR_WARN = "#f59e0b"
COR_OK   = "#16a34a"
COR_NA   = "#94a3b8"

# endregion


# region ====================== SESSÃO 2: Funções de cálculo ===================

def calcular_imt(df: pd.DataFrame) -> float:
    """
    Índice de Manutenção Técnica (IMT).

    Lógica simplificada:
        IMT = (notas encerradas / notas totais) × 100

    Retorna 0.0 se DataFrame vazio ou sem coluna de status.
    """
    if df.empty or "status_usuario" not in df.columns:
        return 0.0

    total = len(df)
    if total == 0:
        return 0.0

    # Considera encerradas as notas com status diferente de ABER
    encerradas = df[~df["status_usuario"].str.upper().str.startswith("AB", na=False)]
    return round((len(encerradas) / total) * 100, 1)


def calcular_di(df: pd.DataFrame) -> float:
    """
    Desempenho de Intervenção (DI).

    Lógica:
        DI = (notas encerradas dentro do prazo / notas encerradas) × 100

    Considera "dentro do prazo": encerradas antes da data_planejada.
    Retorna 0.0 se não houver notas encerradas com data_planejada.
    """
    if df.empty:
        return 0.0

    cols_ok = (
        "status_usuario" in df.columns
        and "data_encerramento" in df.columns
        and "data_planejada" in df.columns
    )
    if not cols_ok:
        return 0.0

    encerradas = df[
        ~df["status_usuario"].str.upper().str.startswith("AB", na=False)
    ].copy()

    if encerradas.empty:
        return 0.0

    enc = encerradas.dropna(subset=["data_encerramento", "data_planejada"]).copy()
    enc["data_encerramento"] = pd.to_datetime(enc["data_encerramento"], errors="coerce")
    enc["data_planejada"]    = pd.to_datetime(enc["data_planejada"],    errors="coerce")
    enc = enc.dropna(subset=["data_encerramento", "data_planejada"])

    if enc.empty:
        return 0.0

    no_prazo = enc[enc["data_encerramento"] <= enc["data_planejada"]]
    return round((len(no_prazo) / len(enc)) * 100, 1)


def calcular_aderencia(df: pd.DataFrame) -> float:
    """
    Aderência ao Planejamento.

    Lógica:
        Aderência = (notas com data_planejada definida / notas totais abertas) × 100

    Mede se as notas abertas têm planejamento registrado.
    """
    if df.empty:
        return 0.0

    abertas = df[
        df.get("status_usuario", pd.Series(dtype=str))
        .str.upper().str.startswith("AB", na=False)
    ] if "status_usuario" in df.columns else df

    total_abertas = len(abertas)
    if total_abertas == 0:
        return 100.0  # nenhuma nota aberta = 100% de aderência

    if "data_planejada" not in abertas.columns:
        return 0.0

    com_plano = abertas["data_planejada"].notna().sum()
    return round((com_plano / total_abertas) * 100, 1)


def calcular_lead_time_medio(df: pd.DataFrame) -> float:
    """
    Lead Time Médio (dias).
    Usa coluna 'lead_time_dias' se disponível; senão calcula pela diferença
    entre data_encerramento e data_nota.
    """
    if df.empty:
        return 0.0

    if "lead_time_dias" in df.columns:
        vals = pd.to_numeric(df["lead_time_dias"], errors="coerce").dropna()
        return round(vals.mean(), 1) if len(vals) > 0 else 0.0

    # Fallback: calcula pela diferença de datas
    if "data_encerramento" in df.columns and "data_nota" in df.columns:
        df_c = df.copy()
        df_c["data_encerramento"] = pd.to_datetime(df_c["data_encerramento"], errors="coerce")
        df_c["data_nota"]         = pd.to_datetime(df_c["data_nota"], errors="coerce")
        df_c = df_c.dropna(subset=["data_encerramento", "data_nota"])
        if not df_c.empty:
            lt = (df_c["data_encerramento"] - df_c["data_nota"]).dt.days
            return round(lt[lt >= 0].mean(), 1)

    return 0.0

# endregion


# region ====================== SESSÃO 3: render_indicadores_geral() ===========

def _cor_indicador(valor: float, lim_crit: float, lim_aten: float,
                   inverso: bool = False) -> str:
    """
    Retorna cor CSS baseada no valor vs limites.
    inverso=True: quanto maior o valor, pior (ex: lead time).
    """
    if valor == 0.0:
        return COR_NA
    if inverso:
        if valor >= lim_crit:   return COR_CRIT
        elif valor >= lim_aten: return COR_WARN
        else:                   return COR_OK
    else:
        if valor < lim_crit:    return COR_CRIT
        elif valor < lim_aten:  return COR_WARN
        else:                   return COR_OK


def _card_indicador(label: str, valor: str, descricao: str, cor: str):
    """Card visual para um indicador."""
    st.markdown(
        f"""
        <div style='
            background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e5e7eb;
            border-left: 5px solid {cor};
            padding: 16px 18px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            text-align: center;
            margin-bottom: 8px;
        '>
            <div style='font-size:0.7rem; color:#6b7280; font-weight:600;
                        text-transform:uppercase; letter-spacing:0.06em;'>
                {label}
            </div>
            <div style='font-size:2rem; font-weight:800; color:{cor}; margin:6px 0;'>
                {valor}
            </div>
            <div style='font-size:0.72rem; color:#9ca3af;'>{descricao}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_indicadores_geral(df: pd.DataFrame):
    """
    Renderiza o painel de 4 indicadores principais na aba Consolidado.

    Exibe IMT, DI, Aderência e Lead Time em cards coloridos (semáforo).

    Args:
        df: DataFrame unificado SP + VP com score calculado
    """
    imt  = calcular_imt(df)
    di   = calcular_di(df)
    adh  = calcular_aderencia(df)
    lt   = calcular_lead_time_medio(df)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        cor = _cor_indicador(imt, LIMITE_IMT_CRITICO, LIMITE_IMT_ATENCAO)
        _card_indicador(
            "IMT — Índice Manutenção Técnica",
            f"{imt:.1f}%",
            f"Meta ≥ {LIMITE_IMT_ATENCAO:.0f}%",
            cor,
        )

    with col2:
        cor = _cor_indicador(di, LIMITE_DI_CRITICO, LIMITE_DI_ATENCAO)
        _card_indicador(
            "DI — Desempenho de Intervenção",
            f"{di:.1f}%",
            f"Meta ≥ {LIMITE_DI_ATENCAO:.0f}%",
            cor,
        )

    with col3:
        cor = _cor_indicador(adh, LIMITE_ADH_CRITICO, LIMITE_ADH_ATENCAO)
        _card_indicador(
            "Aderência ao Planejamento",
            f"{adh:.1f}%",
            f"Meta ≥ {LIMITE_ADH_ATENCAO:.0f}%",
            cor,
        )

    with col4:
        cor = _cor_indicador(
            lt, LIMITE_LT_CRITICO, LIMITE_LT_ATENCAO, inverso=True
        )
        _card_indicador(
            "Lead Time Médio",
            f"{lt:.0f} dias",
            f"Meta ≤ {LIMITE_LT_ATENCAO} dias",
            cor,
        )

    # Barra de contexto
    total = len(df)
    abertas = (
        df["status_usuario"].str.upper().str.startswith("AB", na=False).sum()
        if "status_usuario" in df.columns else 0
    )
    st.caption(
        f"Base: **{total:,}** notas totais · "
        f"**{abertas:,}** abertas · "
        f"**{total - abertas:,}** encerradas"
    )

# endregion


# region ====================== SESSÃO 4: render_semaforo() ====================

def render_semaforo(df_sp: pd.DataFrame, df_vp: pd.DataFrame):
    """
    Exibe um semáforo comparativo de saúde da malha SP × VP.

    Para cada gerência exibe: IMT, DI, Aderência, Lead Time
    com ícones coloridos de semáforo.

    Args:
        df_sp: DataFrame da Gerência SP (pode ser vazio)
        df_vp: DataFrame da Gerência VP (pode ser vazio)
    """
    def _semaforo_icon(valor: float, lim_crit: float, lim_aten: float,
                       inverso: bool = False) -> str:
        """Retorna emoji de semáforo baseado no valor."""
        if valor == 0.0:
            return "⚫"
        cor = _cor_indicador(valor, lim_crit, lim_aten, inverso)
        return {"#16a34a": "🟢", "#f59e0b": "🟡", "#dc2626": "🔴"}.get(cor, "⚫")

    indicadores = [
        ("IMT (%)",         "imt",  False, LIMITE_IMT_CRITICO,  LIMITE_IMT_ATENCAO),
        ("DI (%)",          "di",   False, LIMITE_DI_CRITICO,   LIMITE_DI_ATENCAO),
        ("Aderência (%)",   "adh",  False, LIMITE_ADH_CRITICO,  LIMITE_ADH_ATENCAO),
        ("Lead Time (dias)","lt",   True,  LIMITE_LT_CRITICO,   LIMITE_LT_ATENCAO),
    ]

    # Calcula para SP e VP
    vals_sp = {
        "imt": calcular_imt(df_sp),
        "di":  calcular_di(df_sp),
        "adh": calcular_aderencia(df_sp),
        "lt":  calcular_lead_time_medio(df_sp),
    } if not df_sp.empty else {}

    vals_vp = {
        "imt": calcular_imt(df_vp),
        "di":  calcular_di(df_vp),
        "adh": calcular_aderencia(df_vp),
        "lt":  calcular_lead_time_medio(df_vp),
    } if not df_vp.empty else {}

    # Cabeçalho
    col_ind, col_sp, col_vp = st.columns([2, 1, 1])
    with col_ind:
        st.markdown("**Indicador**")
    with col_sp:
        st.markdown("**🏭 SP**")
    with col_vp:
        st.markdown("**🏭 VP**")

    st.markdown("<hr style='margin:4px 0;'>", unsafe_allow_html=True)

    for label, key, inverso, lim_c, lim_a in indicadores:
        col_ind, col_sp, col_vp = st.columns([2, 1, 1])

        val_sp = vals_sp.get(key, 0.0)
        val_vp = vals_vp.get(key, 0.0)

        icon_sp = _semaforo_icon(val_sp, lim_c, lim_a, inverso)
        icon_vp = _semaforo_icon(val_vp, lim_c, lim_a, inverso)

        fmt = "{:.0f} dias" if key == "lt" else "{:.1f}%"

        with col_ind:
            st.markdown(f"<small>{label}</small>", unsafe_allow_html=True)
        with col_sp:
            txt = fmt.format(val_sp) if vals_sp else "—"
            st.markdown(f"{icon_sp} **{txt}**")
        with col_vp:
            txt = fmt.format(val_vp) if vals_vp else "—"
            st.markdown(f"{icon_vp} **{txt}**")

    st.caption("🟢 Meta atingida · 🟡 Atenção · 🔴 Crítico · ⚫ Sem dados")

# endregion
