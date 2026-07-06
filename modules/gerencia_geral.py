# modules/gerencia_geral.py
# Tela de Visão Geral — Consolidação Multi-gerencial SP × VP
# Sprint 4 — Visão Geral + Admin

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from components.unifilar  import render_unifilar
from components.heatmap   import render_ranking_hotspots, render_serie_temporal
from core.indicadores     import (
    render_indicadores_geral,
    calcular_imt,
    calcular_di,
    calcular_aderencia,
    calcular_lead_time_medio,
    _concat_safe,
)
from database.queries     import get_notas_cached, get_ultima_atualizacao
from core.score_engine    import render_score_sidebar, calcular_score
from core.glossarios      import nome_ramal

# region ====================== SESSÃO 1: Constantes ==========================

LABEL_TELA = "Visao Geral — MRS Sentinel"

# cfg padrão para o unifilar (bin_km)
_cfg_score: dict = {"bin_km": 0.5}

# endregion


# region ====================== SESSÃO 2: Tela principal ======================

def render_gerencia_geral() -> None:
    st.markdown(
        f"""
        <div style='
            background: linear-gradient(135deg, #1e3a5f 0%, #7c3aed 100%);
            padding: 16px 24px;
            border-radius: 12px;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        '>
            <div>
                <h2 style='color:#ffffff; margin:0; font-size:22px;'>
                    {LABEL_TELA}
                </h2>
                <p style='color:rgba(255,255,255,0.7); margin:4px 0 0 0; font-size:13px;'>
                    Consolidacao integrada · Gerencias SP + VP · Disciplinas VP + EE
                </p>
            </div>
            <div style='text-align:right;'>
                <span style='
                    background: #ffb000;
                    color: #1e3a5f;
                    font-weight: 700;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                '>SP + VP</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.spinner("Carregando dados de SP e VP..."):
        df_sp_vp = _load("SP", "VP")
        df_sp_ee = _load("SP", "EE")
        df_vp_vp = _load("VP", "VP")
        df_vp_ee = _load("VP", "EE")

    total_notas = sum(
        len(d) for d in [df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee]
        if d is not None
    )

    if total_notas == 0:
        _render_estado_vazio()
        return

    st.sidebar.markdown("---")
    config = render_score_sidebar("VP+EE")

    df_sp_vp = calcular_score(df_sp_vp, config) if df_sp_vp is not None else None
    df_sp_ee = calcular_score(df_sp_ee, config) if df_sp_ee is not None else None
    df_vp_vp = calcular_score(df_vp_vp, config) if df_vp_vp is not None else None
    df_vp_ee = calcular_score(df_vp_ee, config) if df_vp_ee is not None else None

    _render_card_atualizacao()

    tab_cons, tab_comp, tab_uni, tab_temp, tab_rank = st.tabs([
        "Consolidado",
        "Comparativo SP x VP",
        "Unifilar Total",
        "Temporal Global",
        "Top Hot-spots",
    ])

    with tab_cons:
        _render_aba_consolidado(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee)

    with tab_comp:
        _render_aba_comparativo(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee)

    with tab_uni:
        _render_aba_unifilar(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee)

    with tab_temp:
        _render_aba_temporal(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee)

    with tab_rank:
        _render_aba_ranking(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee)

# endregion


# region ====================== SESSÃO 3: Helpers de carregamento =============

def _load(gerencia: str, disciplina: str) -> pd.DataFrame | None:
    df = get_notas_cached(gerencia, disciplina)
    return df if df is not None and not df.empty else None


def _render_card_atualizacao() -> None:
    cols = st.columns([3, 1])
    with cols[1]:
        for ger, disc in [("SP", "VP"), ("SP", "EE"), ("VP", "VP"), ("VP", "EE")]:
            ult = get_ultima_atualizacao(ger, disc)
            st.markdown(
                f"<div style='text-align:right; font-size:10px; color:#9ca3af;'>"
                f"{ger}/{disc}: <b>{ult}</b></div>",
                unsafe_allow_html=True,
            )

# endregion


# region ====================== SESSÃO 4: Aba Consolidado =====================

def _render_aba_consolidado(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee) -> None:
    df_total = _concat_safe(
        _concat_safe(df_sp_vp, df_sp_ee),
        _concat_safe(df_vp_vp, df_vp_ee),
    )
    st.markdown("#### KPIs — Toda a Malha MRS")
    _render_kpis_consolidados(df_total)
    st.markdown("---")
    render_indicadores_geral(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee)


def _render_kpis_consolidados(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        st.info("Sem dados.")
        return

    total = len(df)

    col_status = (
        "status_nota" if "status_nota" in df.columns
        else ("status_usuario" if "status_usuario" in df.columns else None)
    )
    aber = int(df[col_status].dropna().str.upper().str.startswith("AB").sum()) if col_status else 0

    score_m = round(df["score"].dropna().mean(), 1) if "score" in df.columns else 0.0
    lt_raw  = df["lead_time_dias"].dropna().mean() if "lead_time_dias" in df.columns else None
    lt_m    = int(round(lt_raw, 0)) if lt_raw is not None and pd.notna(lt_raw) else 0
    crit    = int(df["prioridade"].str.contains("1-Muito alta", na=False, case=False).sum()) if "prioridade" in df.columns else 0

    ramal_top = "—"
    if "ramal" in df.columns and "score" in df.columns:
        por_r = df.groupby("ramal")["score"].sum().dropna()
        if not por_r.empty:
            try:
                ramal_top = nome_ramal(por_r.idxmax())
            except Exception:
                ramal_top = str(por_r.idxmax())

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _kpi(c1, "Total Notas",     f"{total:,}",       "#1e3a5f")
    _kpi(c2, "Notas Abertas",   f"{aber:,}",        "#f59e0b")
    _kpi(c3, "Prioridade Max.", f"{crit:,}",        "#dc2626")
    _kpi(c4, "Score Medio",     f"{score_m:.1f}",   "#ffb000")
    _kpi(c5, "Lead Time Medio", f"{lt_m} dias",     "#7c3aed")
    _kpi(c6, "Ramal Top",       ramal_top[:18],     "#0891b2")


def _kpi(col, titulo: str, valor: str, cor: str) -> None:
    col.markdown(
        f"""
        <div style='
            background:#f8fafc;
            border-left:3px solid {cor};
            border-radius:10px;
            padding:12px 10px;
            text-align:center;
        '>
            <div style='font-size:10px; color:#6b7280;'>{titulo}</div>
            <div style='font-size:20px; font-weight:700; color:{cor};'>{valor}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# endregion


# region ====================== SESSÃO 5: Aba Comparativo SP × VP =============

def _render_aba_comparativo(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee) -> None:
    df_sp = _concat_safe(df_sp_vp, df_sp_ee)
    df_vp = _concat_safe(df_vp_vp, df_vp_ee)

    st.markdown("#### Volume de Notas por Prioridade — SP x VP")
    col_sp, col_vp = st.columns(2)
    _grafico_criticidade(col_sp, df_sp, "SP")
    _grafico_criticidade(col_vp, df_vp, "VP")

    st.markdown("---")
    st.markdown("#### Score Total por Ramal")
    col_sp2, col_vp2 = st.columns(2)
    _grafico_score_ramal(col_sp2, df_sp, "SP")
    _grafico_score_ramal(col_vp2, df_vp, "VP")

    st.markdown("---")
    st.markdown("#### Lead Time Medio por Familia de Defeito")
    col_sp3, col_vp3 = st.columns(2)
    _grafico_lead_familia(col_sp3, df_sp, "SP")
    _grafico_lead_familia(col_vp3, df_vp, "VP")


def _grafico_criticidade(col, df, ger: str) -> None:
    col.markdown(f"**Gerencia {ger}**")
    if df is None or df.empty or "prioridade" not in df.columns:
        col.caption("_(sem dados)_")
        return
    ordem  = ["1-Muito alta", "2-Alta", "3-Media", "4-Baixa"]
    cores  = ["#dc2626", "#f59e0b", "#0891b2", "#16a34a"]
    cnt    = df["prioridade"].value_counts()
    labels = [p for p in ordem if p in cnt.index]
    values = [cnt.get(p, 0) for p in labels]
    bares  = [cores[i] for i, p in enumerate(ordem) if p in cnt.index]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=bares, text=values, textposition="outside"))
    fig.update_layout(
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        margin=dict(l=5, r=5, t=10, b=30), height=220,
        showlegend=False,
        yaxis=dict(showgrid=True, gridcolor="#f3f4f6"),
        xaxis=dict(tickfont=dict(size=9)),
    )
    col.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def _grafico_score_ramal(col, df, ger: str) -> None:
    col.markdown(f"**Gerencia {ger}**")
    if df is None or df.empty or "ramal" not in df.columns or "score" not in df.columns:
        col.caption("_(sem dados)_")
        return
    por_ramal = (
        df.groupby("ramal")["score"].sum()
        .sort_values(ascending=True)
        .tail(10)
    )
    try:
        nomes = [nome_ramal(s) for s in por_ramal.index]
    except Exception:
        nomes = [str(s) for s in por_ramal.index]
    fig = go.Figure(go.Bar(
        y=nomes, x=por_ramal.values, orientation="h",
        marker_color="#1e3a5f" if ger == "SP" else "#16a34a",
        text=[f"{v:.0f}" for v in por_ramal.values], textposition="outside",
    ))
    fig.update_layout(
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        margin=dict(l=5, r=5, t=10, b=10), height=280,
        showlegend=False,
        xaxis=dict(showgrid=True, gridcolor="#f3f4f6"),
        yaxis=dict(tickfont=dict(size=9)),
    )
    col.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def _grafico_lead_familia(col, df, ger: str) -> None:
    col.markdown(f"**Gerencia {ger}**")
    col_fam = next((c for c in ["familia_defeito", "familia_cod"] if df is not None and c in df.columns), None)
    if df is None or df.empty or not col_fam or "lead_time_dias" not in df.columns:
        col.caption("_(sem dados)_")
        return
    lt_fam = (
        df.groupby(col_fam)["lead_time_dias"]
        .mean().dropna()
        .sort_values(ascending=False)
        .head(8)
    )
    fig = go.Figure(go.Bar(
        y=lt_fam.index.tolist(), x=lt_fam.values.tolist(),
        orientation="h", marker_color="#7c3aed",
        text=[f"{v:.0f}d" for v in lt_fam.values], textposition="outside",
    ))
    fig.update_layout(
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        margin=dict(l=5, r=5, t=10, b=10), height=260,
        showlegend=False,
        xaxis=dict(showgrid=True, gridcolor="#f3f4f6", title="dias"),
        yaxis=dict(tickfont=dict(size=9)),
    )
    col.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

# endregion


# region ====================== SESSÃO 6: Aba Unifilar Total ==================

def _render_aba_unifilar(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee) -> None:
    st.markdown("#### Unifilar Tridisciplinar — SP + VP")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Gerencia SP**")
        df_sp = _concat_safe(df_sp_vp, df_sp_ee)
        if df_sp is not None and not df_sp.empty:
            render_unifilar(df_sp, _cfg_score)
        else:
            st.info("📭 Sem dados de SP.")
    with c2:
        st.markdown("**Gerencia VP**")
        df_vp = _concat_safe(df_vp_vp, df_vp_ee)
        if df_vp is not None and not df_vp.empty:
            render_unifilar(df_vp, _cfg_score)
        else:
            st.info("📭 Sem dados de VP.")

# endregion


# region ====================== SESSÃO 7: Aba Temporal Global =================

def _render_aba_temporal(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee) -> None:
    st.markdown("#### Serie Temporal — Malha MRS (SP + VP)")
    df_total = _concat_safe(
        _concat_safe(df_sp_vp, df_sp_ee),
        _concat_safe(df_vp_vp, df_vp_ee),
    )
    if df_total is None or df_total.empty:
        st.info("Sem dados para a serie temporal.")
        return
    render_serie_temporal(df_total, "SP+VP")

# endregion


# region ====================== SESSÃO 8: Aba Top Hot-spots ===================

def _render_aba_ranking(df_sp_vp, df_sp_ee, df_vp_vp, df_vp_ee) -> None:
    st.markdown("#### Top Hot-spots — Malha MRS (Cross-Gerencial)")

    dfs = []
    for df, ger, disc in [
        (df_sp_vp, "SP", "VP"), (df_sp_ee, "SP", "EE"),
        (df_vp_vp, "VP", "VP"), (df_vp_ee, "VP", "EE"),
    ]:
        if df is not None and not df.empty:
            d = df.copy()
            d["_gerencia"]   = ger
            d["_disciplina"] = disc
            dfs.append(d)

    if not dfs:
        st.info("Sem dados para o ranking.")
        return

    df_all = pd.concat(dfs, ignore_index=True)
    top_n  = st.slider("Top N trechos", min_value=10, max_value=50, value=20, step=5, key="topn_geral")

    group_cols = [c for c in ["_gerencia", "_disciplina", "ramal", "origem"] if c in df_all.columns]
    agg = {}
    if "score" in df_all.columns:
        agg["score"] = "sum"
    if "lead_time_dias" in df_all.columns:
        agg["lead_time_dias"] = "mean"
    agg["numero_nota"] = "count"

    ranking = (
        df_all.groupby(group_cols).agg(agg)
        .reset_index()
        .sort_values("score" if "score" in agg else "numero_nota", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    ranking.index += 1

    rename = {
        "_gerencia": "Gerencia", "_disciplina": "Disciplina",
        "ramal": "Ramal", "origem": "Patio",
        "score": "Score Total", "lead_time_dias": "Lead Time Medio (d)",
        "numero_nota": "N Notas",
    }
    ranking.rename(columns={k: v for k, v in rename.items() if k in ranking.columns}, inplace=True)

    if "Ramal" in ranking.columns:
        try:
            ranking["Ramal"] = ranking["Ramal"].apply(lambda s: nome_ramal(str(s), "completo_sigla"))
        except Exception:
            pass  # mantém a sigla original se glossário não suportar a assinatura
    if "Score Total" in ranking.columns:
        ranking["Score Total"] = ranking["Score Total"].round(1)
    if "Lead Time Medio (d)" in ranking.columns:
        ranking["Lead Time Medio (d)"] = ranking["Lead Time Medio (d)"].round(0).astype("Int64")

    st.dataframe(ranking, use_container_width=True, height=min(700, 45 * len(ranking) + 80))

    csv = ranking.to_csv(index_label="Posicao").encode("utf-8-sig")
    st.download_button(
        "Exportar Ranking CSV", csv,
        file_name="ranking_hotspots_malha_mrs.csv",
        mime="text/csv", key="dl_ranking_geral",
    )

# endregion


# region ====================== SESSÃO 9: Estado Vazio ========================

def _render_estado_vazio() -> None:
    st.markdown(
        """
        <div style='
            text-align: center; padding: 40px;
            background: #f8fafc; border-radius: 16px;
            border: 2px dashed #d1d5db; margin: 20px 0;
        '>
            <div style='font-size: 48px; margin-bottom: 12px;'>&#127758;</div>
            <h3 style='color: #1e3a5f; margin: 0 0 8px 0;'>
                Nenhum dado carregado na plataforma
            </h3>
            <p style='color: #6b7280; font-size: 14px; margin: 0 0 16px 0;'>
                A Visao Geral requer dados das Gerencias SP e/ou VP.<br/>
                Solicite ao Admin o upload das planilhas SAP.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# endregion