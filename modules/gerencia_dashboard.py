# =============================================================================
# modules/gerencia_dashboard.py — Tela genérica de Gerência
#
# Substitui modules/gerencia_sp.py + gerencia_vp.py, que eram ~95% código
# idêntico (só trocava "SP"↔"VP", cor e nome dos centros em ~15 pontos).
# render_gerencia(sigla) atende qualquer gerência cadastrada em
# core/glossarios.py (NOME_GERENCIA, COR_GERENCIA, COORDENACOES_POR_GERENCIA)
# — adicionar uma gerência nova não pede mais um arquivo de tela novo.
#
#   Sessão 1: Imports & Config
#   Sessão 2: Carregamento e filtros (genéricos por gerência)
#   Sessão 3: render_gerencia(sigla) — 7 abas
# =============================================================================

# region ====================== SESSÃO 1: Imports & Config ======================
import streamlit as st
import pandas as pd

from components.kpi_card import render_kpi_cards
from components.unifilar import render_unifilar_dual
from components.heatmap import render_heatmap, render_ranking, render_serie_temporal
from components.filtros import render_filtros_cascata, aplicar_filtros_atributos
from components.visao_gerencial import render_visao_gerencial

from core.score_engine import render_score_sidebar, calcular_score_dataframe, render_painel_transparencia
from core.glossarios import (
    normalizar_coluna_ramal, NOME_CURTO_GERENCIA, COR_GERENCIA, COORDENACOES_POR_GERENCIA,
)

from database.queries import get_notas_cached

# endregion


# region ====================== SESSÃO 2: Funções auxiliares ====================

@st.cache_data(ttl=300, show_spinner=False)
def _carregar_dados(gerencia: str, disciplina_sel: str) -> pd.DataFrame:
    """
    Carrega dados do Supabase para uma gerência. Aplica normalização de
    aliases (ASP→VSU) antes de qualquer uso.

    Cacheado por (gerencia, disciplina_sel) — 5 min. Sem isso, trocar o
    toggle VP/EE/VP+EE refazia a concatenação + normalização do zero a
    cada clique, mesmo com get_notas_cached já em cache.

    Args:
        gerencia: sigla da gerência (SP, VP, FN, FS, RJ, LC, ...)
        disciplina_sel: 'VP', 'EE' ou 'VP+EE'

    Returns:
        DataFrame unificado, já com coluna 'ramal' normalizada.
    """
    frames = []

    # get_notas_cached (st.cache_data) já retorna uma cópia isolada do cache
    # a cada chamada — seguro mutar direto, sem custo extra de memória.
    if disciplina_sel in ("VP", "VP+EE"):
        df_vp = get_notas_cached(gerencia, "VP")
        if not df_vp.empty:
            df_vp["disciplina_label"] = "VP"
            frames.append(df_vp)

    if disciplina_sel in ("EE", "VP+EE"):
        df_ee = get_notas_cached(gerencia, "EE")
        if not df_ee.empty:
            df_ee["disciplina_label"] = "EE"
            frames.append(df_ee)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # ⭐ ESSENCIAL: normaliza aliases antes de qualquer agrupamento
    df = normalizar_coluna_ramal(df, "ramal")

    if "data_nota" in df.columns:
        df["data_nota"] = pd.to_datetime(df["data_nota"], errors="coerce")
    if "lead_time_dias" in df.columns:
        df["lead_time_dias"] = pd.to_numeric(df["lead_time_dias"], errors="coerce")

    return df


def _aplicar_filtros(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """
    Aplica os filtros retornados pelo componente de filtros em cascata.
    Defensivo contra colunas ausentes e listas vazias. Não depende de
    gerência — é a mesma lógica pra qualquer uma.
    """
    if df.empty:
        return df

    centros = filtros.get("centros", [])
    if centros and "centro_trab" in df.columns:
        df = df[df["centro_trab"].isin(centros)]

    ramais = filtros.get("ramais", [])
    if ramais and "ramal" in df.columns:
        df = df[df["ramal"].isin(ramais)]

    trechos = filtros.get("trechos", [])
    if trechos and "trecho" in df.columns:
        df = df[df["trecho"].isin(trechos)]

    patios = filtros.get("patios", [])
    if patios and "origem" in df.columns:
        df = df[df["origem"].isin(patios)]

    # Filtro de KM Início/Fim (mesmo eixo do gráfico Unifilar). Só filtra
    # quando o usuário estreitou o intervalo (filtro_km_ativo) — senão
    # notas sem km_real (fora da cobertura do KMZ) seriam descartadas.
    if filtros.get("filtro_km_ativo") and "km_real" in df.columns:
        col_km = pd.to_numeric(df["km_real"], errors="coerce")
        km_ini = filtros.get("km_ini")
        km_fim = filtros.get("km_fim")
        if km_ini is not None:
            df = df[col_km >= km_ini]
        if km_fim is not None:
            df = df[col_km <= km_fim]

    # Filtro de Abertura da Nota — dt.date() evita bug de meia-noite
    data_ab_ini = filtros.get("data_abertura_ini") or filtros.get("data_ini")
    data_ab_fim = filtros.get("data_abertura_fim") or filtros.get("data_fim")
    if "data_nota" in df.columns:
        col = pd.to_datetime(df["data_nota"], errors="coerce")
        if data_ab_ini:
            df = df[col.dt.date >= data_ab_ini]
        if data_ab_fim:
            df = df[col.dt.date <= data_ab_fim]

    # Filtro de Encerramento — só entra em ação se o usuário estreitou o
    # período (filtro_enc_ativo), senão notas ainda em aberto seriam descartadas.
    data_enc_ini = filtros.get("data_enc_ini")
    data_enc_fim = filtros.get("data_enc_fim")
    if "data_encerramento" in df.columns and filtros.get("filtro_enc_ativo"):
        col_enc = pd.to_datetime(df["data_encerramento"], errors="coerce")
        if data_enc_ini:
            df = df[col_enc.dt.date >= data_enc_ini]
        if data_enc_fim:
            df = df[col_enc.dt.date <= data_enc_fim]

    # Prioridade, Família, Tipo de inspeção, Status Base
    df = aplicar_filtros_atributos(df, filtros)

    return df.copy()

# endregion


# region ====================== SESSÃO 3: render_gerencia(sigla) ================

def render_gerencia(sigla: str) -> None:
    """
    Ponto de entrada da tela de uma Gerência. Chamado por app.py com a
    sigla certa (ex.: render_gerencia("SP"), render_gerencia("FN")).
    """
    nome_curto = NOME_CURTO_GERENCIA.get(sigla, sigla)
    cor_ini, cor_fim = COR_GERENCIA.get(sigla, ("#1e3a5f", "#2d5a8e"))
    coordenacoes = " · ".join(COORDENACOES_POR_GERENCIA.get(sigla, []))

    # ── Cabeçalho ──────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style='
            background: linear-gradient(135deg, {cor_ini} 0%, {cor_fim} 100%);
            padding: 20px 24px;
            border-radius: 12px;
            margin-bottom: 20px;
        '>
            <h2 style='color: #ffb000; margin: 0; font-size: 1.6rem;'>
                🏭 Gerência {sigla} — {nome_curto}
            </h2>
            <p style='color: #cbd5e1; margin: 4px 0 0 0; font-size: 0.9rem;'>
                Coordenações: {coordenacoes} &nbsp;|&nbsp; Disciplinas: VP + EE integradas
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Sidebar — Toggle VP/EE e Score ────────────────────────────────────────
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"### 🔧 Gerência {sigla}")

        # key= persiste a escolha ao navegar pra outra tela e voltar
        disciplina_sel = st.radio(
            "📊 Disciplina",
            options=["VP+EE", "VP", "EE"],
            key=f"disciplina_{sigla.lower()}",
            horizontal=False,
            help="VP = Via Permanente · EE = Eletroeletrônica · VP+EE = Ambas",
        )

        st.markdown("---")
        score_cfg = render_score_sidebar(gerencia=sigla)
        st.markdown("---")

    # ── Carrega dados ─────────────────────────────────────────────────────────
    with st.spinner(f"⏳ Carregando dados da Gerência {sigla}..."):
        df_raw = _carregar_dados(sigla, disciplina_sel)

    if df_raw.empty:
        st.warning(
            f"⚠️ Nenhum dado encontrado para a Gerência {sigla}. "
            "Solicite ao assistente que faça o upload das planilhas.",
            icon="📋",
        )
        return

    # ── Filtros em cascata (sidebar) ──────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 🔍 Filtros")
        filtros = render_filtros_cascata(df_raw, gerencia=sigla, disciplina_sel=disciplina_sel)

    df = _aplicar_filtros(df_raw, filtros)

    if df.empty:
        st.info("ℹ️ Nenhuma nota encontrada com os filtros aplicados.")
        return

    # ── Score no DataFrame filtrado (todas as abas usam o mesmo df) ──────────
    df = calcular_score_dataframe(df, score_cfg)

    # ── Contador rápido na sidebar ────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"<div style='background:rgba(255,176,0,0.1); padding:10px; "
            f"border-radius:8px; border-left:3px solid #ffb000; margin-top:8px;'>"
            f"<b style='color:#ffb000;'>📌 {len(df):,}</b> notas filtradas<br>"
            f"<small style='color:#6b7280;'>de {len(df_raw):,} totais</small>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── 7 Abas principais ─────────────────────────────────────────────────────
    aba_kpi, aba_ger, aba_unif, aba_heat, aba_rank, aba_temp, aba_ee = st.tabs([
        "📊 Visão Geral",
        "🎯 Visão Gerencial",
        "🗺️ Unifilar",
        "🌡️ Heatmap",
        "🏆 Ranking",
        "📈 Temporal",
        "🔌 Inteligência EE",
    ])

    with aba_kpi:
        st.markdown(f"#### 📊 KPIs da Gerência {sigla}")
        render_kpi_cards(df, gerencia=sigla, disciplina=disciplina_sel)
        st.markdown("---")
        render_painel_transparencia(score_cfg)

    with aba_ger:
        render_visao_gerencial(df, gerencia=sigla)

    with aba_unif:
        st.markdown("#### 🗺️ Unifilar Dual — VP + EE por Ramal")
        col_info, col_legenda = st.columns([3, 1])
        with col_info:
            st.caption(
                "Cada bolha representa um pátio. "
                "Tamanho = volume de notas · Cor = score médio · "
                "Pulso = hot-spot crítico"
            )
        with col_legenda:
            st.markdown(
                "<small>🔴 Crítico &nbsp; 🟡 Alerta &nbsp; 🟢 Normal</small>",
                unsafe_allow_html=True,
            )
        render_unifilar_dual(df, gerencia=sigla)

    with aba_heat:
        st.markdown("#### 🌡️ Heatmap — Pátio × Família de Defeito")
        st.caption("Intensidade = score médio das notas naquela combinação Pátio × Família")
        render_heatmap(df, gerencia=sigla)

    with aba_rank:
        st.markdown("#### 🏆 Ranking de Hot-spots")
        col_n, col_ord = st.columns([1, 2])
        with col_n:
            top_n = st.selectbox("Top N", [5, 10, 15, 20], index=1)
        with col_ord:
            ordem = st.selectbox(
                "Ordenar por",
                ["Score Total", "Qtd. Notas", "Lead Time Médio (dias)"],
                index=0,
            )
        render_ranking(df, top_n=top_n, ordem=ordem, gerencia=sigla)

    with aba_temp:
        st.markdown("#### 📈 Evolução Temporal")
        col_gran, col_met = st.columns(2)
        with col_gran:
            granularidade = st.selectbox(
                "Granularidade",
                ["Mensal", "Semanal", "Trimestral"],
                index=0,
            )
        with col_met:
            metrica = st.selectbox(
                "Métrica",
                ["Volume de Notas", "Score Médio", "Lead Time Médio"],
                index=0,
            )
        render_serie_temporal(df, granularidade=granularidade, metrica=metrica, gerencia=sigla)

    with aba_ee:
        from components.inteligencia_ee import render_inteligencia_ee
        from database.queries_rasf import get_rasf_cached
        from database.queries_baseline import get_baseline_cached

        with st.spinner("⏳ Carregando base RASF (Eletroeletrônica)..."):
            df_rasf = get_rasf_cached(sigla)
            df_base_2025 = get_baseline_cached(sigla)   # camada YoY (Sprint 7)
        render_inteligencia_ee(df_rasf, escopo=sigla, df_baseline=df_base_2025)

# endregion
