# components/filtros.py
# Filtros completos na sidebar + configuração de score
# Restaurado do app1.py (Sprint 3.5)
#
# Uso:
#   from components.filtros import render_filtros_sidebar
#   df_filtrado, cfg = render_filtros_sidebar(df)
#
# Retorna:
#   df_filtrado — DataFrame filtrado pronto para uso
#   cfg         — dict com configurações de score e bin_km

import streamlit as st
import pandas as pd


# ---------------------------------------------------------------------------
# Pesos de prioridade (local — não depende de score_engine)
# ---------------------------------------------------------------------------
_PESO_PRIORIDADE: dict[str, int] = {
    "1-Muito alta": 4,
    "2-Alta":       3,
    "3-Média":      2,
    "4-Baixa":      1,
}

_MULT_FAMILIA: dict[str, float] = {
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

_MULT_STATUS: dict[str, float] = {
    "ABER": 1.0,
    "DIFE": 0.5,
}

_MULT_TIPO: dict[str, float] = {
    "CT": 1.5,
    "PV": 1.0,
}


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def render_filtros_sidebar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Renderiza todos os filtros na sidebar e retorna o DataFrame filtrado
    junto com o dict de configuração de score/bin_km.

    Args:
        df: DataFrame completo de notas (já carregado do Supabase)

    Returns:
        df_filtrado: DataFrame após aplicação de todos os filtros
        cfg: {
            "bin_km": float,
            "alpha_idade": float,
            "fator_idade": bool,
            "fator_status": bool,
            "fator_familia": bool,
            "fator_tipo": bool,
            "mult_status": dict,
            "mult_familia": dict,
            "mult_tipo": dict,
        }
    """
    if df is None or df.empty:
        return pd.DataFrame(), _cfg_default()

    total = len(df)

    # ── Seção: Filtros ─────────────────────────────────────────────────────
    st.sidebar.markdown("### 🎛️ Filtros")

    # Filtro 1: Status
    status_disponiveis = sorted(df["status_usuario"].dropna().unique().tolist())
    status_padrao = [s for s in status_disponiveis
                     if any(k in str(s).upper() for k in ("ABER", "DIFE"))]
    status_sel = st.sidebar.multiselect(
        "Status:",
        options=status_disponiveis,
        default=status_padrao if status_padrao else status_disponiveis,
        key="fil_status",
        help="ABER=Aberta | DIFE=Diferida | CONC=Concluída | CANC=Cancelada",
    )
    if not status_sel:
        status_sel = status_disponiveis

    # Pré-filtro para cascata de centro
    df_pre_centro = df[df["status_usuario"].isin(status_sel)]

    # Filtro 2: Centro de Trabalho (topo da hierarquia geográfica)
    centros_disp = sorted([
        c for c in df_pre_centro["centro_trab"].dropna().unique() if c
    ])
    centro_sel = st.sidebar.multiselect(
        "🏢 Centro de trabalho:",
        options=centros_disp,
        default=centros_disp,
        key="fil_centro",
        help="CIPA, CIPG, CIJN... Filtra Trecho e Pátio em cascata.",
    )
    if not centro_sel:
        centro_sel = centros_disp

    if len(centro_sel) < len(centros_disp):
        st.sidebar.caption(
            f"🔍 Restringindo: **{len(centro_sel)}** de **{len(centros_disp)}** centros"
        )

    # Filtro 3: Prioridade
    prio_sel = st.sidebar.multiselect(
        "Prioridade:",
        options=list(_PESO_PRIORIDADE.keys()),
        default=list(_PESO_PRIORIDADE.keys()),
        key="fil_prio",
    )
    if not prio_sel:
        prio_sel = list(_PESO_PRIORIDADE.keys())

    # Filtro 4: Família de defeito
    familias_disp = sorted(df["familia_defeito"].dropna().unique().tolist())
    familia_sel = st.sidebar.multiselect(
        "🛠️ Família de defeito:",
        options=familias_disp,
        default=familias_disp,
        key="fil_familia",
    )
    if not familia_sel:
        familia_sel = familias_disp

    # Filtro 5: Tipo de inspeção/atividade
    tipos_disp = sorted([
        t for t in df["tipo_atividade"].dropna().unique()
        if t and str(t).strip()
    ])
    tipo_sel = st.sidebar.multiselect(
        "🔍 Tipo de inspeção:",
        options=tipos_disp,
        default=tipos_disp,
        key="fil_tipo_ativ",
        help="Ronda, Drone, Trackstar, Inspeção técnica de AMV...",
    )
    if not tipo_sel:
        tipo_sel = tipos_disp

    # Pré-filtro para pátio (cascata pelo centro)
    df_pre_patio = df_pre_centro[df_pre_centro["centro_trab"].isin(centro_sel)]
    patios_disp = sorted([
        p for p in df_pre_patio["origem"].dropna().unique() if p
    ])
    patio_sel = st.sidebar.multiselect(
        "📍 Pátio:",
        options=patios_disp,
        default=patios_disp,
        key="fil_patio",
        help="Lista restrita aos pátios dos Centros selecionados.",
    )
    if not patio_sel:
        patio_sel = patios_disp

    if len(patio_sel) < len(patios_disp):
        st.sidebar.caption(
            f"🔍 Restringindo: **{len(patio_sel)}** de **{len(patios_disp)}** pátios"
        )

    # Filtro 7: Período
    periodo = None
    col_data = "data_nota"
    if col_data in df.columns and df[col_data].notna().any():
        datas_validas = df[col_data].dropna()
        data_min = datas_validas.min()
        data_max = datas_validas.max()

        if hasattr(data_min, "date"):
            data_min = data_min.date()
        if hasattr(data_max, "date"):
            data_max = data_max.date()

        try:
            periodo = st.sidebar.date_input(
                "📅 Período (data da nota):",
                value=(data_min, data_max),
                min_value=data_min,
                max_value=data_max,
                key="fil_periodo",
            )
        except Exception:
            periodo = None

    # ── Seção: Resolução do Mapa ───────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔬 Resolução do Mapa")
    bin_km = st.sidebar.slider(
        "Janela de agrupamento (m):",
        min_value=100, max_value=2000, value=500, step=100,
        key="fil_bin_km",
        help="Menor = mais detalhe | Maior = visão macro.",
    ) / 1000.0

    # ── Seção: Configuração do Score ───────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ Configuração do Score")

    with st.sidebar.expander("ℹ️ Como o score é calculado", expanded=False):
        st.caption(
            "Cada nota recebe um **peso pela prioridade** (1 a 4). "
            "Ative os **fatores adicionais** para refinar a criticidade. "
            "Sem fatores extras, usa só o peso da prioridade (padrão simples)."
        )

    fator_idade = st.sidebar.checkbox(
        "🕰️ Considerar idade da nota",
        value=True,
        key="fil_fator_idade",
        help="Notas mais antigas indicam descontrole — cada ano aberto adiciona α.",
    )
    alpha_idade = 0.0
    if fator_idade:
        alpha_idade = st.sidebar.slider(
            "  └─ Intensidade (α):",
            min_value=0.05, max_value=0.50, value=0.10, step=0.05,
            key="fil_alpha",
        )

    fator_status = st.sidebar.checkbox(
        "📍 Penalizar diferimento (DIFE)",
        value=False,
        key="fil_fator_status",
    )

    fator_familia = st.sidebar.checkbox(
        "🛠️ Pesar por família de defeito",
        value=False,
        key="fil_fator_familia",
    )

    fator_tipo = st.sidebar.checkbox(
        "🚨 Diferenciar Corretiva × Preventiva",
        value=False,
        key="fil_fator_tipo",
    )

    if st.sidebar.button("🔄 Resetar para padrão simples", use_container_width=True, key="fil_reset"):
        for k in ["fil_fator_idade", "fil_fator_status", "fil_fator_familia", "fil_fator_tipo"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

    # ── Aplicar filtros ────────────────────────────────────────────────────
    mask = (
        df["status_usuario"].isin(status_sel)
        & df["centro_trab"].isin(centro_sel)
        & df["familia_defeito"].isin(familia_sel)
        & df["prioridade"].isin(prio_sel)
        & df["origem"].isin(patio_sel)
    )

    # tipo_atividade pode ter nulos
    if tipos_disp:
        mask = mask & df["tipo_atividade"].fillna("").isin(tipo_sel + [""])

    df_filtrado = df[mask].copy()

    # Filtro de período
    if periodo and len(periodo) == 2:
        try:
            df_filtrado = df_filtrado[
                (pd.to_datetime(df_filtrado[col_data]).dt.date >= periodo[0])
                & (pd.to_datetime(df_filtrado[col_data]).dt.date <= periodo[1])
            ]
        except Exception:
            pass

    # ── Score ajustado ─────────────────────────────────────────────────────
    algum_fator = fator_idade or fator_status or fator_familia or fator_tipo
    if algum_fator and len(df_filtrado) > 0:
        df_filtrado = _aplicar_score_ajustado(
            df_filtrado, fator_idade, alpha_idade,
            fator_status, fator_familia, fator_tipo,
        )

        score_orig = df_filtrado.get("score_original", df_filtrado["score"])
        score_novo = df_filtrado["score"]
        med_orig = score_orig.mean()
        med_novo = score_novo.mean()
        delta = ((med_novo / med_orig - 1) * 100) if med_orig else 0
        emoji = "🟢" if abs(delta) < 10 else ("🟡" if abs(delta) < 30 else "🔴")

        fatores_txt = []
        if fator_idade:
            fatores_txt.append(f"🕰️ α={alpha_idade}")
        if fator_status:
            fatores_txt.append("📍 DIFE")
        if fator_familia:
            fatores_txt.append("🛠️ Família")
        if fator_tipo:
            fatores_txt.append("🚨 CT×PV")

        st.sidebar.markdown(
            f"<div style='background:rgba(124,58,237,0.15); padding:10px; "
            f"border-radius:8px; border-left:3px solid #7c3aed; margin-top:8px;'>"
            f"<b style='color:#fff;'>{emoji} Score Ajustado</b><br>"
            f"<small style='color:#e9d5ff;'>Fatores: {', '.join(fatores_txt)}<br>"
            f"Médio: <b>{med_orig:.2f}</b> → <b>{med_novo:.2f}</b> "
            f"({delta:+.1f}%)</small></div>",
            unsafe_allow_html=True,
        )

    # ── Contador final ─────────────────────────────────────────────────────
    pct = (len(df_filtrado) / total * 100) if total else 0
    st.sidebar.markdown(
        f"<div style='background:rgba(255,176,0,0.1); padding:10px; border-radius:8px; "
        f"border-left:3px solid #ffb000; margin-top:10px;'>"
        f"<b>📊 {len(df_filtrado):,}</b> notas após filtros<br>"
        f"<small>de {total:,} no total ({pct:.1f}%)</small></div>",
        unsafe_allow_html=True,
    )

    cfg = {
        "bin_km":        bin_km,
        "alpha_idade":   alpha_idade,
        "fator_idade":   fator_idade,
        "fator_status":  fator_status,
        "fator_familia": fator_familia,
        "fator_tipo":    fator_tipo,
        "mult_status":   _MULT_STATUS,
        "mult_familia":  _MULT_FAMILIA,
        "mult_tipo":     _MULT_TIPO,
    }

    return df_filtrado, cfg


def render_filtros_geograficos(df: pd.DataFrame, df_filtrado: pd.DataFrame) -> pd.DataFrame:
    """
    Renderiza os filtros geográficos em cascata (Matriz → Trecho)
    na área principal (abaixo dos KPIs).

    Retorna df_filtrado com Matriz e Trecho aplicados.
    """
    if df_filtrado.empty:
        return df_filtrado

    st.markdown(
        "<div style='background:linear-gradient(90deg,#f0f9ff 0%,#fef3c7 100%);"
        "border:1px solid #e5e7eb; border-left:5px solid #1e3a5f;"
        "padding:12px 18px; border-radius:10px; margin-bottom:16px;'>"
        "<div style='font-size:13px;color:#6b7280;font-weight:600;"
        "text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;'>"
        "🌐 Filtros Geográficos</div>"
        "<div style='font-size:12px;color:#9ca3af;'>"
        "🔗 Filtrados em cascata pelo <b>Centro de Trabalho</b> da barra lateral.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    col_mat, col_trc = st.columns([1, 2])

    matrizes_disp = sorted([t for t in df_filtrado["trecho"].dropna().unique() if t])

    with col_mat:
        if not matrizes_disp:
            st.warning("⚠️ Nenhuma Matriz disponível com os filtros atuais.")
            return df_filtrado

        matriz_sel = st.multiselect(
            "🗺️ Matriz",
            options=matrizes_disp,
            default=matrizes_disp,
            key="geo_matriz",
            help=f"{len(matrizes_disp)} matrizes disponíveis.",
        )
        if not matriz_sel:
            matriz_sel = matrizes_disp

    trechos_disp = sorted([
        s for s in df_filtrado[df_filtrado["trecho"].isin(matriz_sel)]["trecho"].dropna().unique()
        if s
    ])

    with col_trc:
        if not trechos_disp:
            trecho_sel = []
        else:
            trecho_sel = st.multiselect(
                "🚂 Trecho",
                options=trechos_disp,
                default=trechos_disp,
                key="geo_trecho",
                help=f"{len(trechos_disp)} trechos disponíveis.",
            )
            if not trecho_sel:
                trecho_sel = trechos_disp

    # Indicador de cascata ativa
    cascata = []
    if len(matriz_sel) < len(matrizes_disp):
        cascata.append(f"🗺️ **{len(matriz_sel)}** matriz(es)")
    if trecho_sel and len(trecho_sel) < len(trechos_disp):
        cascata.append(f"🚂 **{len(trecho_sel)}** trecho(s)")
    if cascata:
        st.caption(f"🔗 Cascata ativa: {' → '.join(cascata)}")

    df_geo = df_filtrado[df_filtrado["trecho"].isin(matriz_sel)]
    if trecho_sel:
        df_geo = df_geo[df_geo["trecho"].isin(trecho_sel)]

    return df_geo.copy()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _cfg_default() -> dict:
    return {
        "bin_km": 0.5, "alpha_idade": 0.0,
        "fator_idade": False, "fator_status": False,
        "fator_familia": False, "fator_tipo": False,
        "mult_status": _MULT_STATUS,
        "mult_familia": _MULT_FAMILIA,
        "mult_tipo": _MULT_TIPO,
    }


def _aplicar_score_ajustado(
    df: pd.DataFrame,
    fator_idade: bool,
    alpha_idade: float,
    fator_status: bool,
    fator_familia: bool,
    fator_tipo: bool,
) -> pd.DataFrame:
    """Recalcula score com fatores adicionais, preservando score_original."""
    data_ref = pd.Timestamp.now()
    df = df.copy()
    df["score_original"] = df["score"]

    def _calc(row):
        score = float(row.get("peso_prio") or 1)
        if fator_status:
            s = str(row.get("status_usuario", "")).strip().upper()
            score *= _MULT_STATUS.get(s, 1.0)
        if fator_familia:
            score *= _MULT_FAMILIA.get(str(row.get("familia_defeito", "Outros")), 1.0)
        if fator_tipo:
            score *= _MULT_TIPO.get(str(row.get("tipo_nota", "")).strip(), 1.0)
        if fator_idade:
            dn = row.get("data_nota")
            if dn is not None and not pd.isna(dn):
                try:
                    dias = (data_ref - pd.Timestamp(dn)).days
                    score *= (1 + alpha_idade * max(0, dias / 365.25))
                except Exception:
                    pass
        return round(score, 2)

    df["score"] = df.apply(_calc, axis=1)
    return df
