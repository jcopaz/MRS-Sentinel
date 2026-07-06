# components/filtros.py
# Filtros em cascata reutilizáveis: Centro → Ramal → Trecho → Pátio
# Sprint 3 — Visualizações por Gerência

import streamlit as st
import pandas as pd
from core.glossarios import nome_ramal, RAMAIS_MRS

# region ====================== SESSÃO 1: Centros por Gerência =================

CENTROS_POR_GERENCIA = {
    "SP": ["CIPA", "CIPG", "CIJN"],
    "VP": ["CFAN", "CFTA", "CFPI"],
}

# endregion


# region ====================== SESSÃO 2: Render dos Filtros ===================

def render_filtros_sidebar(
    df: pd.DataFrame,
    gerencia: str,
    disciplina: str,
    prefix: str = "",
) -> tuple[pd.DataFrame, dict]:
    if df is None or df.empty:
        st.sidebar.info("Nenhum dado carregado para filtrar.")
        return df, {}

    selecoes = {}

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
        '>Filtros — {disciplina}</div>
        """,
        unsafe_allow_html=True,
    )

    # ── 1. Centro de Trabalho ────────────────────────────────────────────────
    centros_base = CENTROS_POR_GERENCIA.get(gerencia, [])
    centros_disponiveis = sorted(
        [c for c in centros_base if c in df["centro_trab"].dropna().unique()]
    ) if "centro_trab" in df.columns else []

    if not centros_disponiveis and "centro_trab" in df.columns:
        centros_disponiveis = sorted(df["centro_trab"].dropna().unique().tolist())

    if centros_disponiveis:
        centros_sel = st.sidebar.multiselect(
            "Centro de Trabalho",
            options=centros_disponiveis,
            default=centros_disponiveis,
            key=f"{prefix}_centros_{gerencia}_{disciplina}",
        )
        selecoes["centros"] = centros_sel
        df_c = df[df["centro_trab"].isin(centros_sel)] if centros_sel else df.copy()
    else:
        df_c = df.copy()
        selecoes["centros"] = []

    # ── 2. Ramal ─────────────────────────────────────────────────────────────
    if "ramal" in df_c.columns:
        ramais_disponiveis = sorted(df_c["ramal"].dropna().unique().tolist())
        opcoes_ramal = {sigla: nome_ramal(sigla) for sigla in ramais_disponiveis}

        ramais_nomes_sel = st.sidebar.multiselect(
            "Ramal",
            options=list(opcoes_ramal.values()),
            default=list(opcoes_ramal.values()),
            key=f"{prefix}_ramais_{gerencia}_{disciplina}",
        )
        ramal_sel = [s for s, n in opcoes_ramal.items() if n in ramais_nomes_sel]
        selecoes["ramais"] = ramal_sel
        df_r = df_c[df_c["ramal"].isin(ramal_sel)] if ramal_sel else df_c.copy()
    else:
        df_r = df_c.copy()
        selecoes["ramais"] = []

    # ── 3. Trecho (par Origem-Destino) ───────────────────────────────────────
    if "origem" in df_r.columns and "destino" in df_r.columns:
        df_r = df_r.copy()
        # Só constrói label quando ambos os campos têm valor real
        mask_valido = (
            df_r["origem"].notna() & df_r["destino"].notna() &
            (df_r["origem"].astype(str).str.strip() != "") &
            (df_r["destino"].astype(str).str.strip() != "")
        )
        df_r["_trecho_label"] = ""
        df_r.loc[mask_valido, "_trecho_label"] = (
            df_r.loc[mask_valido, "origem"].astype(str).str.strip()
            + " → "
            + df_r.loc[mask_valido, "destino"].astype(str).str.strip()
        )
        trechos_disponiveis = sorted(
            t for t in df_r["_trecho_label"].unique() if t and t != " → "
        )
    elif "trecho" in df_r.columns:
        df_r = df_r.copy()
        trechos_disponiveis = sorted(df_r["trecho"].dropna().unique().tolist())
        df_r["_trecho_label"] = df_r["trecho"]
    else:
        df_r = df_r.copy()
        trechos_disponiveis = []
        df_r["_trecho_label"] = ""

    if trechos_disponiveis:
        trechos_sel = st.sidebar.multiselect(
            "Trecho (Origem → Destino)",
            options=trechos_disponiveis,
            default=trechos_disponiveis,
            key=f"{prefix}_trechos_{gerencia}_{disciplina}",
        )
        selecoes["trechos"] = trechos_sel
        df_t = df_r[df_r["_trecho_label"].isin(trechos_sel)] if trechos_sel else df_r.copy()
    else:
        df_t = df_r.copy()
        selecoes["trechos"] = []

    # ── 4. Pátio ─────────────────────────────────────────────────────────────
    col_patio = "origem" if "origem" in df_t.columns else None

    if col_patio:
        patios_disponiveis = sorted(df_t[col_patio].dropna().unique().tolist())
        patios_sel = st.sidebar.multiselect(
            "Patio",
            options=patios_disponiveis,
            default=patios_disponiveis,
            key=f"{prefix}_patios_{gerencia}_{disciplina}",
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
        f"<div style='font-size:11px; color:#6b7280; padding:4px 0;'>"
        f"Cascata: <b>{total_filt:,}</b>/{total_orig:,} notas ({pct:.0f}%)</div>",
        unsafe_allow_html=True,
    )

    if "_trecho_label" in df_filtrado.columns:
        df_filtrado = df_filtrado.drop(columns=["_trecho_label"])

    return df_filtrado, selecoes

# endregion