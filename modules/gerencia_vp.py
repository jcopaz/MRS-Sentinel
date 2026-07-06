# modules/gerencia_vp.py
# Tela da Gerência VP — Via Permanente + Eletroeletrônica
# Sprint 3 — Visualizações por Gerência
#
# Estrutura idêntica à Gerência SP — mantida separada intencionalmente
# para facilitar customizações futuras por gerência (ramais, centros, etc.)
#
# Diferenças em relação à SP:
#   GERENCIA = "VP"
#   CENTROS  = CFAN, CFTA, CFPI (ao invés de CIPA, CIPG, CIJN)
#   Ramais principais: Aço Minas, Miguel Burnier, Porto Sudeste, Itaguaí...

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from components.filtros  import render_filtros_sidebar
from components.kpi_card import render_kpi_cards
from components.unifilar import render_unifilar
from components.heatmap  import (
    render_heatmap_patio_familia,
    render_ranking_hotspots,
    render_serie_temporal,
)
from core.score_engine import (
    render_score_sidebar,
    calcular_score,
    render_painel_transparencia,
)
from database.queries import (
    get_notas_cached,
    get_ultima_atualizacao,
)
from core.glossarios import nome_ramal

# region ====================== SESSÃO 1: Constantes ==========================

GERENCIA       = "VP"
LABEL_GERENCIA = "🏭 Gerência VP — Vale do Paraíba"
CENTROS_VP     = ["CFAN", "CFTA", "CFPI"]

# cfg retornado por render_filtros_sidebar — contém bin_km para o unifilar
_cfg_score: dict = {"bin_km": 0.5}

# endregion


# region ====================== SESSÃO 2: Tela principal ======================

def render_gerencia_vp() -> None:
    """
    Ponto de entrada da tela da Gerência VP.
    Chamado pelo app.py quando o usuário navega para Gerência VP.
    """

    # ── 2.1: Cabeçalho ─────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style='
            background: linear-gradient(135deg, #1e3a5f 0%, #1a4a2e 100%);
            padding: 16px 24px;
            border-radius: 12px;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        '>
            <div>
                <h2 style='color:#ffffff; margin:0; font-size:22px;'>
                    {LABEL_GERENCIA}
                </h2>
                <p style='color:rgba(255,255,255,0.7); margin:4px 0 0 0; font-size:13px;'>
                    Ramais: Aço Minas · Miguel Burnier · Porto Sudeste · Itaguaí · 
                    Olhos D'Água · Paraibuna · Cimento Barroso · Wilson Lobato
                </p>
            </div>
            <div style='text-align:right;'>
                <span style='
                    background: #16a34a;
                    color: #ffffff;
                    font-weight: 700;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                '>VP</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 2.2: Toggle de disciplina ────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("**🔀 Disciplina**")

    disciplina_sel = st.sidebar.radio(
        label="Disciplina ativa",
        options=["VP", "EE", "VP+EE"],
        index=0,
        key="disciplina_vp",
        horizontal=False,
        label_visibility="collapsed",
        help=(
            "VP = Via Permanente (trilhos, dormentes, geometria...)\n"
            "EE = Eletroeletrônica (sinalização, energia, telecom, wayside)\n"
            "VP+EE = Visão integrada"
        ),
    )

    st.sidebar.markdown("---")

    # ── 2.3: Carrega dados ─────────────────────────────────────────────────
    with st.spinner("🔄 Carregando dados..."):
        df_vp, df_ee = _carregar_dados(disciplina_sel)

    if _dados_vazios(df_vp, df_ee, disciplina_sel):
        _render_estado_vazio(disciplina_sel)
        return

    # ── 2.4: Score engine ────────────────────────────────────────────────────
    config_score = render_score_sidebar(disciplina_sel)

    # ── 2.5: Calcula score ────────────────────────────────────────────────────
    if df_vp is not None and not df_vp.empty:
        df_vp = calcular_score(df_vp, config_score)
    if df_ee is not None and not df_ee.empty:
        df_ee = calcular_score(df_ee, config_score)

    # ── 2.6: Filtros em cascata ───────────────────────────────────────────────
    df_vp_filt, df_ee_filt = _aplicar_filtros(df_vp, df_ee, disciplina_sel)

    # ── 2.7: Última atualização ────────────────────────────────────────────────
    _render_card_atualizacao(disciplina_sel)

    # ── 2.8: Abas ─────────────────────────────────────────────────────────────
    tab_geral, tab_hotspot, tab_temporal, tab_gerencial, tab_score = st.tabs([
        "📊 Visão Geral",
        "🔥 Hot-spots",
        "📈 Temporal",
        "🧑‍💼 Gerencial",
        "⚖️ Score",
    ])

    with tab_geral:
        _render_aba_visao_geral(df_vp_filt, df_ee_filt, disciplina_sel)

    with tab_hotspot:
        _render_aba_hotspots(df_vp_filt, df_ee_filt, disciplina_sel)

    with tab_temporal:
        _render_aba_temporal(df_vp_filt, df_ee_filt, disciplina_sel)

    with tab_gerencial:
        _render_aba_gerencial(df_vp_filt, df_ee_filt, disciplina_sel)

    with tab_score:
        _render_aba_score(df_vp_filt, df_ee_filt, disciplina_sel, config_score)

# endregion


# region ====================== SESSÃO 3: Carregamento de dados ================

def _carregar_dados(
    disciplina_sel: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    df_vp = None
    df_ee = None

    if disciplina_sel in ("VP", "VP+EE"):
        df_vp = get_notas_cached(GERENCIA, "VP")
        if df_vp is not None and df_vp.empty:
            df_vp = None

    if disciplina_sel in ("EE", "VP+EE"):
        df_ee = get_notas_cached(GERENCIA, "EE")
        if df_ee is not None and df_ee.empty:
            df_ee = None

    return df_vp, df_ee


def _dados_vazios(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
) -> bool:
    if disciplina_sel == "VP":
        return df_vp is None
    if disciplina_sel == "EE":
        return df_ee is None
    return df_vp is None and df_ee is None

# endregion


# region ====================== SESSÃO 4: Filtros ==============================

def _aplicar_filtros(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    global _cfg_score

    # Monta df combinado para sidebar única (evita renderizar sidebar duas vezes)
    dfs = []
    if df_vp is not None:
        dfs.append(df_vp)
    if df_ee is not None:
        dfs.append(df_ee)
    df_combined = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    df_filt, _cfg_score = render_filtros_sidebar(df_combined)

    # Separa de volta por disciplina
    df_vp_filt = None
    df_ee_filt = None

    if df_vp is not None and not df_filt.empty:
        if "disciplina" in df_filt.columns:
            df_vp_filt = df_filt[df_filt["disciplina"] == "VP"].copy()
        else:
            df_vp_filt = df_filt.copy()

    if df_ee is not None and not df_filt.empty:
        if "disciplina" in df_filt.columns:
            df_ee_filt = df_filt[df_filt["disciplina"] == "EE"].copy()
        else:
            df_ee_filt = df_filt.copy()

    return df_vp_filt, df_ee_filt

# endregion


# region ====================== SESSÃO 5: Card de atualização ==================

def _render_card_atualizacao(disciplina_sel: str) -> None:
    cols = st.columns([3, 1])
    with cols[1]:
        if disciplina_sel in ("VP", "VP+EE"):
            ult_vp = get_ultima_atualizacao(GERENCIA, "VP")
            st.markdown(
                f"<div style='text-align:right; font-size:11px; color:#6b7280;'>"
                f"🛤️ VP: <b>{ult_vp}</b></div>",
                unsafe_allow_html=True,
            )
        if disciplina_sel in ("EE", "VP+EE"):
            ult_ee = get_ultima_atualizacao(GERENCIA, "EE")
            st.markdown(
                f"<div style='text-align:right; font-size:11px; color:#6b7280;'>"
                f"⚡ EE: <b>{ult_ee}</b></div>",
                unsafe_allow_html=True,
            )

# endregion


# region ====================== SESSÃO 6: Aba Visão Geral =====================

def _render_aba_visao_geral(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
) -> None:
    if disciplina_sel == "VP+EE":
        st.markdown("#### 🛤️ Via Permanente")
        if df_vp is not None:
            render_kpi_cards(df_vp, "VP")
        else:
            st.info("📭 Sem dados de VP.")

        st.markdown("#### ⚡ Eletroeletrônica")
        if df_ee is not None:
            render_kpi_cards(df_ee, "EE")
        else:
            st.info("📭 Sem dados de EE.")
    else:
        df_ativo = df_vp if disciplina_sel == "VP" else df_ee
        render_kpi_cards(df_ativo, disciplina_sel)

    st.markdown("---")

    # Combina VP e/ou EE conforme seleção e passa cfg com bin_km
    dfs_uni = []
    if df_vp is not None:
        dfs_uni.append(df_vp)
    if df_ee is not None:
        dfs_uni.append(df_ee)
    df_uni = pd.concat(dfs_uni, ignore_index=True) if dfs_uni else pd.DataFrame()
    if not df_uni.empty:
        render_unifilar(df_uni, _cfg_score)

# endregion


# region ====================== SESSÃO 7: Aba Hot-spots =======================

def _render_aba_hotspots(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
) -> None:
    if disciplina_sel == "VP+EE":
        sub_vp, sub_ee = st.tabs(["🛤️ VP", "⚡ EE"])

        with sub_vp:
            if df_vp is not None:
                render_heatmap_patio_familia(df_vp, "VP")
                st.markdown("---")
                render_ranking_hotspots(df_vp, "VP")
            else:
                st.info("📭 Sem dados de VP.")

        with sub_ee:
            if df_ee is not None:
                render_heatmap_patio_familia(df_ee, "EE")
                st.markdown("---")
                render_ranking_hotspots(df_ee, "EE")
            else:
                st.info("📭 Sem dados de EE.")
    else:
        df_ativo = df_vp if disciplina_sel == "VP" else df_ee
        if df_ativo is not None:
            render_heatmap_patio_familia(df_ativo, disciplina_sel)
            st.markdown("---")
            render_ranking_hotspots(df_ativo, disciplina_sel)
        else:
            st.info(f"📭 Sem dados de {disciplina_sel}.")

# endregion


# region ====================== SESSÃO 8: Aba Temporal ========================

def _render_aba_temporal(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
) -> None:
    if disciplina_sel == "VP+EE":
        sub_vp, sub_ee = st.tabs(["🛤️ VP", "⚡ EE"])
        with sub_vp:
            if df_vp is not None:
                render_serie_temporal(df_vp, "VP")
            else:
                st.info("📭 Sem dados de VP.")
        with sub_ee:
            if df_ee is not None:
                render_serie_temporal(df_ee, "EE")
            else:
                st.info("📭 Sem dados de EE.")
    else:
        df_ativo = df_vp if disciplina_sel == "VP" else df_ee
        if df_ativo is not None:
            render_serie_temporal(df_ativo, disciplina_sel)
        else:
            st.info(f"📭 Sem dados de {disciplina_sel}.")

# endregion


# region ====================== SESSÃO 9: Aba Gerencial (9 elementos) =========

def _render_aba_gerencial(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
) -> None:
    """
    9 Elementos Gerenciais — idênticos à Gerência SP, com contexto VP.
    """
    df = _combinar_df(df_vp, df_ee, disciplina_sel)

    if df is None or df.empty:
        st.info("📭 Sem dados para o painel gerencial.")
        return

    col1, col2 = st.columns(2)
    with col1:
        _elem1_criticidade(df, disciplina_sel)
    with col2:
        _elem2_status_donut(df, disciplina_sel)

    st.markdown("---")

    col3, col4 = st.columns(2)
    with col3:
        _elem3_tipo_inspecao(df, disciplina_sel)
    with col4:
        _elem4_notas_por_mes(df, disciplina_sel)

    st.markdown("---")

    col5, col6 = st.columns(2)
    with col5:
        _elem5_drill_semanal(df, disciplina_sel)
    with col6:
        _elem6_planejado_realizado(df, disciplina_sel)

    st.markdown("---")
    _elem7_codigo_anomalia(df, disciplina_sel)

    st.markdown("---")
    _elem8_tabela_cruzada(df, disciplina_sel)

    st.markdown("---")
    _elem9_quadro_resumo(df, disciplina_sel)


def _combinar_df(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
) -> pd.DataFrame | None:
    if disciplina_sel == "VP":
        return df_vp
    if disciplina_sel == "EE":
        return df_ee

    dfs = []
    if df_vp is not None and not df_vp.empty:
        df_vp_copy = df_vp.copy()
        df_vp_copy["_disc"] = "VP"
        dfs.append(df_vp_copy)
    if df_ee is not None and not df_ee.empty:
        df_ee_copy = df_ee.copy()
        df_ee_copy["_disc"] = "EE"
        dfs.append(df_ee_copy)

    return pd.concat(dfs, ignore_index=True) if dfs else None


# ── Elemento 1 ────────────────────────────────────────────────────────────────
def _elem1_criticidade(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 1️⃣ Notas por Criticidade")
    if "prioridade" not in df.columns:
        st.caption("_(coluna prioridade não encontrada)_")
        return
    ordem = ["1-Muito alta", "2-Alta", "3-Média", "4-Baixa"]
    cores  = ["#dc2626", "#f59e0b", "#0891b2", "#16a34a"]
    contagem = df["prioridade"].value_counts()
    labels = [p for p in ordem if p in contagem.index]
    values = [contagem.get(p, 0) for p in labels]
    bar_cores = [cores[i] for i, p in enumerate(ordem) if p in contagem.index]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=bar_cores, text=values, textposition="outside"))
    fig.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff", margin=dict(l=10,r=10,t=20,b=40), height=260, showlegend=False, yaxis=dict(showgrid=True, gridcolor="#f3f4f6"))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ── Elemento 2 ────────────────────────────────────────────────────────────────
def _elem2_status_donut(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 2️⃣ Status Concluída-Ordem")
    col = next((c for c in ["status_nota_ordem","status_final","status_usuario"] if c in df.columns), None)
    if not col:
        st.caption("_(coluna de status não encontrada)_")
        return
    contagem = df[col].fillna("N/D").value_counts().head(6)
    fig = go.Figure(go.Pie(labels=contagem.index.tolist(), values=contagem.values.tolist(), hole=0.55, marker=dict(colors=px.colors.qualitative.Safe), textinfo="percent+label", textfont=dict(size=10)))
    fig.update_layout(margin=dict(l=10,r=10,t=20,b=20), height=260, showlegend=False, paper_bgcolor="#fff")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ── Elemento 3 ────────────────────────────────────────────────────────────────
def _elem3_tipo_inspecao(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 3️⃣ Notas por Tipo de Atividade")
    col = next((c for c in ["tipo_atividade","tipo_nota"] if c in df.columns), None)
    if not col:
        st.caption("_(coluna tipo_atividade não encontrada)_")
        return
    contagem = df[col].fillna("N/D").value_counts()
    fig = go.Figure(go.Bar(y=contagem.index.tolist(), x=contagem.values.tolist(), orientation="h", marker_color="#1e3a5f", text=contagem.values.tolist(), textposition="outside"))
    fig.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff", margin=dict(l=10,r=10,t=20,b=20), height=260, showlegend=False, xaxis=dict(showgrid=True, gridcolor="#f3f4f6"))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ── Elemento 4 ────────────────────────────────────────────────────────────────
def _elem4_notas_por_mes(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 4️⃣ Notas Abertas × Encerradas por Mês")
    if "data_nota" not in df.columns:
        st.caption("_(coluna data_nota não encontrada)_")
        return
    df_c = df.copy()
    df_c["data_nota"] = pd.to_datetime(df_c["data_nota"], errors="coerce")
    df_ok = df_c.dropna(subset=["data_nota"])
    serie = df_ok.groupby(df_ok["data_nota"].dt.to_period("M")).size().reset_index(name="abertas")
    serie["_mes"] = serie["data_nota"].dt.to_timestamp()
    fig = go.Figure(go.Bar(x=serie["_mes"], y=serie["abertas"], name="Abertas", marker_color="#1e3a5f", opacity=0.85))
    if "data_encerramento" in df_c.columns:
        df_c["data_encerramento"] = pd.to_datetime(df_c["data_encerramento"], errors="coerce")
        df_enc = df_c.dropna(subset=["data_encerramento"])
        s_enc = df_enc.groupby(df_enc["data_encerramento"].dt.to_period("M")).size().reset_index(name="enc")
        s_enc["_mes"] = s_enc["data_encerramento"].dt.to_timestamp()
        fig.add_trace(go.Bar(x=s_enc["_mes"], y=s_enc["enc"], name="Encerradas", marker_color="#16a34a", opacity=0.85))
    fig.update_layout(barmode="group", plot_bgcolor="#fff", paper_bgcolor="#fff", margin=dict(l=10,r=10,t=20,b=40), height=260, legend=dict(orientation="h", y=1.05), yaxis=dict(showgrid=True, gridcolor="#f3f4f6"))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ── Elemento 5 ────────────────────────────────────────────────────────────────
def _elem5_drill_semanal(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 5️⃣ Drill Semanal — Backlog × Vazão")
    if "data_nota" not in df.columns:
        st.caption("_(coluna data_nota não encontrada)_")
        return
    df_c = df.copy()
    df_c["data_nota"] = pd.to_datetime(df_c["data_nota"], errors="coerce")
    cutoff = pd.Timestamp.now() - pd.Timedelta(weeks=12)
    df_ok = df_c.dropna(subset=["data_nota"])
    df_12w = df_ok[df_ok["data_nota"] >= cutoff]
    if df_12w.empty:
        st.info("📭 Sem dados nas últimas 12 semanas.")
        return
    backlog = df_12w.groupby(df_12w["data_nota"].dt.to_period("W")).size().reset_index(name="backlog")
    backlog["_sem"] = backlog["data_nota"].dt.to_timestamp()
    fig = go.Figure(go.Scatter(x=backlog["_sem"], y=backlog["backlog"], name="Abertas", mode="lines+markers", line=dict(color="#dc2626", width=2), fill="tozeroy", fillcolor="rgba(220,38,38,0.1)"))
    if "data_encerramento" in df_c.columns:
        df_c["data_encerramento"] = pd.to_datetime(df_c["data_encerramento"], errors="coerce")
        df_enc_ok = df_c.dropna(subset=["data_encerramento"])
        df_enc_12w = df_enc_ok[df_enc_ok["data_encerramento"] >= cutoff]
        if not df_enc_12w.empty:
            vazao = df_enc_12w.groupby(df_enc_12w["data_encerramento"].dt.to_period("W")).size().reset_index(name="enc")
            vazao["_sem"] = vazao["data_encerramento"].dt.to_timestamp()
            fig.add_trace(go.Scatter(x=vazao["_sem"], y=vazao["enc"], name="Encerradas", mode="lines+markers", line=dict(color="#16a34a", width=2), fill="tozeroy", fillcolor="rgba(22,163,74,0.1)"))
    fig.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff", margin=dict(l=10,r=10,t=20,b=40), height=260, legend=dict(orientation="h", y=1.05), hovermode="x unified", yaxis=dict(showgrid=True, gridcolor="#f3f4f6"))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ── Elemento 6 ────────────────────────────────────────────────────────────────
def _elem6_planejado_realizado(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 6️⃣ Planejado × Realizado (Aderência)")
    if "data_planejada" not in df.columns:
        st.caption("_(coluna data_planejada não encontrada)_")
        return
    df_c = df.copy()
    df_c["data_planejada"] = pd.to_datetime(df_c["data_planejada"], errors="coerce")
    df_ok = df_c.dropna(subset=["data_planejada"])
    plan = df_ok.groupby(df_ok["data_planejada"].dt.to_period("M")).size().reset_index(name="plan")
    plan["_mes"] = plan["data_planejada"].dt.to_timestamp()
    fig = go.Figure(go.Bar(x=plan["_mes"], y=plan["plan"], name="Planejadas", marker_color="#ffb000", opacity=0.85))
    if "data_encerramento" in df_c.columns:
        df_c["data_encerramento"] = pd.to_datetime(df_c["data_encerramento"], errors="coerce")
        df_enc = df_c.dropna(subset=["data_encerramento"])
        real = df_enc.groupby(df_enc["data_encerramento"].dt.to_period("M")).size().reset_index(name="real")
        real["_mes"] = real["data_encerramento"].dt.to_timestamp()
        fig.add_trace(go.Bar(x=real["_mes"], y=real["real"], name="Realizadas", marker_color="#1e3a5f", opacity=0.85))
    fig.update_layout(barmode="group", plot_bgcolor="#fff", paper_bgcolor="#fff", margin=dict(l=10,r=10,t=20,b=40), height=260, legend=dict(orientation="h", y=1.05), yaxis=dict(showgrid=True, gridcolor="#f3f4f6"))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ── Elemento 7 ────────────────────────────────────────────────────────────────
def _elem7_codigo_anomalia(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 7️⃣ Top 15 Códigos de Anomalia")
    col = next((c for c in ["code_codificacao","defeito_legivel"] if c in df.columns), None)
    if not col:
        st.caption("_(coluna de código de anomalia não encontrada)_")
        return
    top15 = df[col].fillna("N/D").value_counts().head(15)
    fig = go.Figure(go.Bar(y=top15.index.tolist(), x=top15.values.tolist(), orientation="h", marker=dict(color=top15.values.tolist(), colorscale=[[0,"#bfdbfe"],[1,"#1e3a5f"]]), text=top15.values.tolist(), textposition="outside"))
    fig.update_layout(plot_bgcolor="#fff", paper_bgcolor="#fff", margin=dict(l=10,r=10,t=20,b=20), height=400, showlegend=False, xaxis=dict(showgrid=True, gridcolor="#f3f4f6"), yaxis=dict(tickfont=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


# ── Elemento 8 ────────────────────────────────────────────────────────────────
def _elem8_tabela_cruzada(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 8️⃣ Tabela Cruzada — Código × Família")
    col_cod = next((c for c in ["code_codificacao"] if c in df.columns), None)
    col_fam = next((c for c in ["familia_defeito","familia_cod"] if c in df.columns), None)
    if not col_cod or not col_fam:
        st.caption("_(colunas necessárias não encontradas)_")
        return
    pivot = df.groupby([col_fam, col_cod]).size().reset_index(name="Contagem").sort_values("Contagem", ascending=False).head(50)
    pivot.rename(columns={col_fam: "Família", col_cod: "Código"}, inplace=True)
    st.dataframe(pivot, use_container_width=True, height=300)
    csv = pivot.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Exportar CSV", csv, file_name=f"cruzada_codigo_familia_vp_{disc}.csv", mime="text/csv", key=f"dl_cruzada_vp_{disc}")


# ── Elemento 9 ────────────────────────────────────────────────────────────────
def _elem9_quadro_resumo(df: pd.DataFrame, disc: str) -> None:
    st.markdown("##### 9️⃣ Quadro Resumo por Ramal")
    if "ramal" not in df.columns:
        st.caption("_(coluna ramal não encontrada)_")
        return
    agg = {}
    if "score" in df.columns:
        agg["score"] = ["sum", "mean", "count"]
    if "lead_time_dias" in df.columns:
        agg["lead_time_dias"] = "mean"
    if "prioridade" in df.columns:
        df["_muito_alta"] = df["prioridade"].str.contains("1-Muito alta", na=False).astype(int)
        agg["_muito_alta"] = "sum"
    if not agg:
        st.caption("_(sem métricas para resumo)_")
        return
    resumo = df.groupby("ramal").agg(agg).reset_index()
    resumo.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c for c in resumo.columns]
    col_rename = {"ramal":"Ramal","score_sum":"Score Total","score_mean":"Score Médio","score_count":"Nº Notas","lead_time_dias_mean":"Lead Time Médio","_muito_alta_sum":"Prioridade Máxima"}
    resumo.rename(columns={k:v for k,v in col_rename.items() if k in resumo.columns}, inplace=True)
    if "Ramal" in resumo.columns:
        try:
            resumo["Ramal"] = resumo["Ramal"].apply(lambda s: nome_ramal(str(s), "completo_sigla"))
        except Exception:
            pass  # mantém a sigla original se glossário não suportar a assinatura
    for c in ["Score Total","Score Médio","Lead Time Médio"]:
        if c in resumo.columns:
            resumo[c] = resumo[c].round(1)
    if "Score Total" in resumo.columns:
        resumo = resumo.sort_values("Score Total", ascending=False)
    st.dataframe(resumo, use_container_width=True, hide_index=True)
    csv = resumo.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Exportar Quadro Resumo CSV", csv, file_name=f"quadro_resumo_vp_{disc}.csv", mime="text/csv", key=f"dl_resumo_vp_{disc}")
    if "_muito_alta" in df.columns:
        df.drop(columns=["_muito_alta"], inplace=True)

# endregion


# region ====================== SESSÃO 10: Aba Score ==========================

def _render_aba_score(
    df_vp: pd.DataFrame | None,
    df_ee: pd.DataFrame | None,
    disciplina_sel: str,
    config_score,
) -> None:
    df = _combinar_df(df_vp, df_ee, disciplina_sel)
    if df is None or df.empty:
        st.info("📭 Sem dados para o painel de transparência.")
        return
    render_painel_transparencia(df, config_score)

# endregion


# region ====================== SESSÃO 11: Estado Vazio =======================

def _render_estado_vazio(disciplina_sel: str) -> None:
    st.markdown("---")
    st.markdown(
        f"""
        <div style='
            text-align: center;
            padding: 40px;
            background: #f8fafc;
            border-radius: 16px;
            border: 2px dashed #d1d5db;
            margin: 20px 0;
        '>
            <div style='font-size: 48px; margin-bottom: 12px;'>📭</div>
            <h3 style='color: #1e3a5f; margin: 0 0 8px 0;'>
                Nenhum dado de {disciplina_sel} encontrado para Gerência VP
            </h3>
            <p style='color: #6b7280; font-size: 14px; margin: 0 0 16px 0;'>
                Os dados precisam ser carregados por um Assistente ou Admin 
                através da tela de Upload de Dados.
            </p>
            <div style='
                background: rgba(255,176,0,0.1);
                border: 1px solid #ffb000;
                border-radius: 8px;
                padding: 10px 16px;
                display: inline-block;
                font-size: 13px;
                color: #92400e;
            '>
                💡 Acesse o menu lateral → <b>📤 Upload de Dados</b> para importar a planilha SAP
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# endregion
