# =============================================================================
# components/filtros.py — Filtros em cascata
# Sprint 3 — MRS Sentinel
#
# Exporta render_filtros_cascata() — filtros hierárquicos na sidebar:
#   Centro de Trabalho → Ramal → Trecho → Pátio → Período
#
# Cada nível reage ao anterior (cascata real):
#   - Ao selecionar Centro, só aparecem os Ramais daquele Centro
#   - Ao selecionar Ramal, só aparecem os Trechos daquele Ramal
#   - etc.
#
# Sessão 1: Imports & constantes
# Sessão 2: Helpers de extração de opções
# Sessão 3: render_filtros_cascata()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from core.glossarios import nome_ramal, RAMAIS_MRS

# Centros de trabalho por gerência (fonte: 08_GLOSSARIOS.md)
CENTROS_POR_GERENCIA = {
    "SP":    ["CIPA", "CIPG", "CIJN"],
    "VP":    ["CFAN", "CFTA", "CFPI"],
    "GERAL": ["CIPA", "CIPG", "CIJN", "CFAN", "CFTA", "CFPI"],
}

# endregion


# region ====================== SESSÃO 2: Helpers ==============================

def _opcoes_centros(df: pd.DataFrame, gerencia: str) -> list[str]:
    """
    Retorna lista de centros presentes nos dados.
    Prioriza os centros conhecidos da gerência; inclui eventuais extras.
    """
    conhecidos = CENTROS_POR_GERENCIA.get(gerencia, [])
    if "centro_trab" in df.columns:
        presentes = df["centro_trab"].dropna().unique().tolist()
        # Ordena: conhecidos primeiro, extras depois
        ordenados = [c for c in conhecidos if c in presentes]
        extras    = [c for c in presentes  if c not in conhecidos]
        return ordenados + sorted(extras)
    return conhecidos


def _opcoes_ramais(df: pd.DataFrame, centros_sel: list[str]) -> list[str]:
    """
    Retorna ramais disponíveis nos dados, filtrados pelos centros selecionados.
    Usa nome completo no label e sigla como valor interno.
    """
    if "ramal" not in df.columns:
        return []

    df_f = df.copy()
    if centros_sel and "centro_trab" in df_f.columns:
        df_f = df_f[df_f["centro_trab"].isin(centros_sel)]

    siglas = sorted(df_f["ramal"].dropna().unique().tolist())
    return siglas


def _opcoes_trechos(df: pd.DataFrame, centros_sel: list[str], ramais_sel: list[str]) -> list[str]:
    """Retorna trechos disponíveis após filtro de centros e ramais."""
    if "trecho" not in df.columns:
        return []

    df_f = df.copy()
    if centros_sel and "centro_trab" in df_f.columns:
        df_f = df_f[df_f["centro_trab"].isin(centros_sel)]
    if ramais_sel and "ramal" in df_f.columns:
        df_f = df_f[df_f["ramal"].isin(ramais_sel)]

    return sorted(df_f["trecho"].dropna().unique().tolist())


def _opcoes_patios(
    df: pd.DataFrame,
    centros_sel: list[str],
    ramais_sel: list[str],
    trechos_sel: list[str],
) -> list[str]:
    """Retorna pátios (origem) disponíveis após filtros anteriores."""
    if "origem" not in df.columns:
        return []

    df_f = df.copy()
    if centros_sel and "centro_trab" in df_f.columns:
        df_f = df_f[df_f["centro_trab"].isin(centros_sel)]
    if ramais_sel and "ramal" in df_f.columns:
        df_f = df_f[df_f["ramal"].isin(ramais_sel)]
    if trechos_sel and "trecho" in df_f.columns:
        df_f = df_f[df_f["trecho"].isin(trechos_sel)]

    return sorted(df_f["origem"].dropna().unique().tolist())

# endregion


# region ====================== SESSÃO 3: render_filtros_cascata() =============

def render_filtros_cascata(df: pd.DataFrame, gerencia: str = "SP") -> dict:
    """
    Renderiza filtros em cascata na sidebar com botões Aplicar / Limpar.

    Usa st.form para que o app só recarregue os dados quando o usuário
    clicar em "✅ Aplicar Filtros" — evita reruns a cada seleção.

    Hierarquia:
        Centro de Trabalho → Ramal → Trecho → Pátio → Período

    Returns:
        dict com chaves: centros, ramais, trechos, patios, data_ini, data_fim
    """
    uid = gerencia  # prefixo de key único por gerência

    # ── Datas mín/máx (calculadas fora do form, pois dependem do df bruto) ───
    data_min = date(2018, 1, 1)
    data_max = date.today()
    if "data_nota" in df.columns:
        datas_validas = pd.to_datetime(df["data_nota"], errors="coerce").dropna()
        if not datas_validas.empty:
            data_min = datas_validas.min().date()
            data_max = datas_validas.max().date()

    # ── Botão Limpar (fora do form — limpa session_state e rerun imediato) ───
    if st.button(
        "🗑️ Limpar filtros",
        key=f"filtro_reset_{uid}",
        use_container_width=True,
        type="secondary",
    ):
        for key in [
            f"filtro_centros_{uid}", f"filtro_ramais_{uid}",
            f"filtro_trechos_{uid}", f"filtro_patios_{uid}",
            f"filtro_data_ini_{uid}", f"filtro_data_fim_{uid}",
        ]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # ── Formulário: todos os filtros + botão Aplicar ──────────────────────────
    with st.form(key=f"form_filtros_{uid}"):

        # 1. Centro de Trabalho
        opcoes_centros = _opcoes_centros(df, gerencia)
        centros_sel = st.multiselect(
            "🏢 Centro de Trabalho",
            options=opcoes_centros,
            default=opcoes_centros,
            key=f"filtro_centros_{uid}",
            help="Filtre por centro de coordenação regional",
        )
        if not centros_sel:
            centros_sel = opcoes_centros

        # 2. Ramal (nome completo na exibição, sigla internamente)
        siglas_disp = _opcoes_ramais(df, centros_sel)
        opcoes_ramal_label = {
            nome_ramal(s, "completo_sigla"): s for s in siglas_disp
        }
        ramais_nome_sel = st.multiselect(
            "🚂 Ramal",
            options=list(opcoes_ramal_label.keys()),
            default=list(opcoes_ramal_label.keys()),
            key=f"filtro_ramais_{uid}",
            help="Nome completo do ramal conforme nomenclatura ANTT/MRS",
        )
        ramais_sel = [
            opcoes_ramal_label[n]
            for n in ramais_nome_sel
            if n in opcoes_ramal_label
        ]
        if not ramais_sel and siglas_disp:
            ramais_sel = siglas_disp

        # 3. Trecho
        opcoes_trechos = _opcoes_trechos(df, centros_sel, ramais_sel)
        if opcoes_trechos:
            trechos_sel = st.multiselect(
                "📍 Trecho (Origem → Destino)",
                options=opcoes_trechos,
                default=opcoes_trechos,
                key=f"filtro_trechos_{uid}",
                help="Par Origem-Destino dentro do ramal",
            )
            if not trechos_sel:
                trechos_sel = opcoes_trechos
        else:
            trechos_sel = []

        # 4. Pátio
        opcoes_patios = _opcoes_patios(df, centros_sel, ramais_sel, trechos_sel)
        if opcoes_patios:
            patios_sel = st.multiselect(
                "🚉 Pátio (Origem)",
                options=opcoes_patios,
                default=opcoes_patios,
                key=f"filtro_patios_{uid}",
                help="Estação/ponto de origem da nota de manutenção",
            )
            if not patios_sel:
                patios_sel = opcoes_patios
        else:
            patios_sel = []

        # 5. Período
        st.markdown("**📅 Período**")
        col_ini, col_fim = st.columns(2)
        with col_ini:
            data_ini = st.date_input(
                "De",
                value=data_min,
                min_value=data_min,
                max_value=data_max,
                key=f"filtro_data_ini_{uid}",
            )
        with col_fim:
            data_fim = st.date_input(
                "Até",
                value=data_max,
                min_value=data_min,
                max_value=data_max,
                key=f"filtro_data_fim_{uid}",
            )

        if data_ini > data_fim:
            st.warning("⚠️ Data inicial maior que a final.")
            data_ini, data_fim = data_fim, data_ini

        # Botão Aplicar (dentro do form — dispara o rerun com novos valores)
        st.form_submit_button(
            "✅ Aplicar Filtros",
            use_container_width=True,
            type="primary",
        )

    return {
        "centros":  centros_sel,
        "ramais":   ramais_sel,
        "trechos":  trechos_sel,
        "patios":   patios_sel,
        "data_ini": data_ini,
        "data_fim": data_fim,
    }

# endregion
