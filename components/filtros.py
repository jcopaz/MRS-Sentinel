# components/filtros.py
# Filtros em cascata reutilizáveis: Centro → Ramal → Trecho → Pátio
# Sprint 3 — Visualizações por Gerência
#
# USO:
#   from components.filtros import render_filtros_sidebar
#   df_filtrado, sel = render_filtros_sidebar(df, gerencia="SP", disciplina="VP")

import streamlit as st
import pandas as pd
from core.glossarios import nome_ramal, RAMAIS_MRS

# region ====================== SESSÃO 1: Centros por Gerência ======================

# Centros de trabalho mapeados por gerência (fonte: 08_GLOSSARIOS.md)
CENTROS_POR_GERENCIA = {
    "SP": ["CIPA", "CIPG", "CIJN"],
    "VP": ["CFAN", "CFTA", "CFPI"],
}

# endregion


# region ====================== SESSÃO 2: Render dos Filtros =======================

def render_filtros_sidebar(
    df: pd.DataFrame,
    gerencia: str,
    disciplina: str,
    prefix: str = "",
) -> tuple[pd.DataFrame, dict]:
    """
    Renderiza filtros em cascata na sidebar e retorna o DataFrame filtrado.

    A cascata segue a hierarquia oficial MRS:
      Centro de Trabalho → Ramal → Trecho → Pátio

    Args:
        df:         DataFrame já carregado com colunas: centro_trab, ramal,
                    trecho, origem, destino
        gerencia:   'SP' ou 'VP' — determina centros disponíveis
        disciplina: 'VP', 'EE' ou 'VP+EE' — usado apenas para label visual
        prefix:     prefixo para evitar conflito de chaves de session_state
                    quando múltiplas disciplinas estão ativas

    Returns:
        (df_filtrado, selecoes) onde selecoes é dict com as escolhas do usuário
    """
    if df is None or df.empty:
        st.sidebar.info("ℹ️ Nenhum dado carregado para filtrar.")
        return df, {}

    selecoes = {}

    # ── Separador visual na sidebar ──────────────────────────────────────────
    st.sidebar.markdown(
        f"""
        <div style='
            background: rgba(255,176,0,0.12);
            border-left: 3px solid #ffb000;
            border-radius: 6px;
            padding: 6px 10px;
            margin: 8px 0;
            font-size: 12px;
            color: #1e3a5f;
            font-weight: 600;
        '>🔽 Filtros — {disciplina}</div>
        """,
        unsafe_allow_html=True,
    )

    # ── 1. Centro de Trabalho ────────────────────────────────────────────────
    centros_base = CENTROS_POR_GERENCIA.get(gerencia, [])

    # Só exibe centros que realmente existem no DataFrame
    centros_disponiveis = sorted(
        [c for c in centros_base if c in df["centro_trab"].dropna().unique()]
    )

    # Se não encontrou centros mapeados, usa os que existem no df
    if not centros_disponiveis:
        centros_disponiveis = sorted(df["centro_trab"].dropna().unique().tolist())

    centros_sel = st.sidebar.multiselect(
        "🏢 Centro de Trabalho",
        options=centros_disponiveis,
        default=centros_disponiveis,
        key=f"{prefix}_centros_{gerencia}_{disciplina}",
        help="Filtra por centro de trabalho. Afeta Ramal, Trecho e Pátio abaixo.",
    )
    selecoes["centros"] = centros_sel

    # Aplica filtro de centro para cascata
    df_c = df[df["centro_trab"].isin(centros_sel)] if centros_sel else df.copy()

    # ── 2. Ramal ─────────────────────────────────────────────────────────────
    # UI mostra nome completo, internamente usa sigla
    ramais_disponiveis = sorted(df_c["ramal"].dropna().unique().tolist())
    opcoes_ramal = {sigla: nome_ramal(sigla) for sigla in ramais_disponiveis}

    # Exibe nome completo no multiselect
    ramais_nomes_sel = st.sidebar.multiselect(
        "🚂 Ramal",
        options=list(opcoes_ramal.values()),
        default=list(opcoes_ramal.values()),
        key=f"{prefix}_ramais_{gerencia}_{disciplina}",
        help="Selecione os ramais a visualizar. Afeta Trecho e Pátio abaixo.",
    )

    # Converte de volta para siglas para filtrar no df
    ramal_sel = [
        sigla for sigla, nome in opcoes_ramal.items()
        if nome in ramais_nomes_sel
    ]
    selecoes["ramais"] = ramal_sel
    selecoes["ramais_nomes"] = ramais_nomes_sel

    df_r = df_c[df_c["ramal"].isin(ramal_sel)] if ramal_sel else df_c.copy()

    # ── 3. Trecho (par Origem-Destino) ───────────────────────────────────────
    # Constrói label "Origem → Destino" para exibição
    if "origem" in df_r.columns and "destino" in df_r.columns:
        df_r = df_r.copy()
        df_r["_trecho_label"] = (
            df_r["origem"].fillna("?") + " → " + df_r["destino"].fillna("?")
        )
        trechos_disponiveis = sorted(df_r["_trecho_label"].dropna().unique().tolist())
    elif "trecho" in df_r.columns:
        trechos_disponiveis = sorted(df_r["trecho"].dropna().unique().tolist())
        df_r["_trecho_label"] = df_r["trecho"]
    else:
        trechos_disponiveis = []
        df_r["_trecho_label"] = ""

    if trechos_disponiveis:
        trechos_sel = st.sidebar.multiselect(
            "📍 Trecho (Origem → Destino)",
            options=trechos_disponiveis,
            default=trechos_disponiveis,
            key=f"{prefix}_trechos_{gerencia}_{disciplina}",
            help="Par Origem-Destino dentro do ramal.",
        )
        selecoes["trechos"] = trechos_sel
        df_t = df_r[df_r["_trecho_label"].isin(trechos_sel)] if trechos_sel else df_r.copy()
    else:
        df_t = df_r.copy()
        selecoes["trechos"] = []

    # ── 4. Pátio ─────────────────────────────────────────────────────────────
    # Usa coluna 'origem' como pátio (nomenclatura oficial MRS)
    col_patio = "origem" if "origem" in df_t.columns else None

    if col_patio:
        patios_disponiveis = sorted(df_t[col_patio].dropna().unique().tolist())
        patios_sel = st.sidebar.multiselect(
            "🏗️ Pátio",
            options=patios_disponiveis,
            default=patios_disponiveis,
            key=f"{prefix}_patios_{gerencia}_{disciplina}",
            help="Pátio (estação) de origem da nota.",
        )
        selecoes["patios"] = patios_sel
        df_filtrado = df_t[df_t[col_patio].isin(patios_sel)] if patios_sel else df_t.copy()
    else:
        df_filtrado = df_t.copy()
        selecoes["patios"] = []

    # ── Indicador de cascata ativa ────────────────────────────────────────────
    total_orig = len(df)
    total_filt = len(df_filtrado)
    pct = (total_filt / total_orig * 100) if total_orig > 0 else 0

    st.sidebar.markdown(
        f"""
        <div style='
            background: rgba(30,58,95,0.06);
            border-radius: 6px;
            padding: 6px 10px;
            margin-top: 6px;
            font-size: 11px;
            color: #6b7280;
        '>🔗 Cascata ativa: <b>{total_filt:,}</b>/{total_orig:,} notas ({pct:.0f}%)</div>
        """,
        unsafe_allow_html=True,
    )

    # Remove coluna auxiliar antes de retornar
    if "_trecho_label" in df_filtrado.columns:
        df_filtrado = df_filtrado.drop(columns=["_trecho_label"])

    return df_filtrado, selecoes

# endregion
