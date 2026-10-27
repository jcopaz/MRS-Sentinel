# =============================================================================
# modules/itirapina/defeitos.py — Subaba 🛠️ Defeitos (export Rumo + Vagão)
#
# KPIs, filtros, Pareto por tipo, mapa de calor SB × grupo, histograma de
# dias ativos, bloco "Vagão de Via — pede velocidade abaixo da VMA e não tem
# restrição" (achado acionável) com Excel lat/long, e mapa dos que têm
# coordenada.
# =============================================================================

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.analise_trecho import (
    TRECHO_KM, cobertura_restricao, perfil_trecho, sb_dos_defeitos, faixas_sb,
)
from core.exportacao import gerar_excel_bytes

CFG = {"displaylogo": False}


def _kpis(d: pd.DataFrame) -> None:
    ext = TRECHO_KM[1] - TRECHO_KM[0]
    vel = d["vel_max_classe_kmh"]
    k = st.columns(4)
    k[0].metric("Defeitos ativos", f"{len(d):,}".replace(",", "."), f"{len(d) / ext:.1f}/km",
                delta_color="off")
    k[1].metric("Classe ≤ 40 km/h", int((vel <= 40).sum()))
    k[2].metric("Ativos > 1 ano", int((d["dias_ativo"] > 365).sum()))
    k[3].metric("Corretivos · críticos",
                f"{int((d['classificacao'] == 'Corretivo').sum())} · "
                f"{int((d['classificacao'] == 'Crítico').sum())}")
    k = st.columns(4)
    k[0].metric("Em perímetro urbano", int((d["perimetro_urbano"] == True).sum()))  # noqa: E712
    k[1].metric("Ligados a acidente", int((d["acidente"] == True).sum()))  # noqa: E712
    k[2].metric("Vagão de Via", int((d["origem"] == "VIA").sum()))
    k[3].metric("Com lat/long", int(d["latitude"].notna().sum()))


def _filtros(d: pd.DataFrame) -> pd.DataFrame:
    c = st.columns(6)
    def ms(rot, campo, i):
        op = sorted(d[campo].dropna().astype(str).unique())
        return c[i].multiselect(rot, op, key=f"def_{campo}", placeholder="Todos")
    f_or = ms("Origem", "origem", 0)
    f_gr = ms("Grupo", "grupo", 1)
    f_cl = ms("Classe de via", "classe_via", 2)
    f_sb = ms("SB", "sb_calc", 3)
    f_ln = ms("Linha", "linha", 4)
    viagens = sorted(d["numero_viagem"].dropna().astype(int).unique())
    f_vi = c[5].multiselect("Viagem Vagão", viagens, key="def_viagem", placeholder="Todas")
    for campo, sel in (("origem", f_or), ("grupo", f_gr), ("classe_via", f_cl), ("sb_calc", f_sb),
                       ("linha", f_ln)):
        if sel:
            d = d[d[campo].astype(str).isin(sel)]
    if f_vi:
        d = d[d["numero_viagem"].isin(f_vi)]
    return d


def _graficos(d: pd.DataFrame, dorm: pd.DataFrame) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Pareto por tipo de defeito")
        g = d["nome_defeito"].value_counts().head(15).iloc[::-1]
        fig = go.Figure(go.Bar(orientation="h", y=g.index.str.slice(0, 40), x=g.values,
                               marker_color="#1e3a5f", text=g.values, textposition="outside"))
        fig.update_layout(height=460, margin=dict(l=10, r=40, t=10, b=30), plot_bgcolor="#fff")
        st.plotly_chart(fig, use_container_width=True, config=CFG)
    with c2:
        st.markdown("##### Dias ativo")
        fig = go.Figure(go.Histogram(x=d["dias_ativo"], nbinsx=40, marker_color="#b45309"))
        fig.add_vline(x=365, line=dict(color="#dc2626", dash="dot"))
        fig.update_layout(height=460, margin=dict(l=10, r=10, t=10, b=30), plot_bgcolor="#fff",
                          xaxis_title="dias", yaxis_title="defeitos")
        st.plotly_chart(fig, use_container_width=True, config=CFG)

    if dorm is not None and not dorm.empty:
        st.markdown("##### Mapa de calor SB × grupo (defeitos por km)")
        fx = faixas_sb(dorm).set_index("sb")
        ext = (fx["km_fim"] - fx["km_ini"]).replace(0, np.nan)
        m = d.groupby(["sb_calc", "grupo"]).size().unstack(fill_value=0)
        m = m.reindex([s for s in fx.index if s in m.index])
        dens = m.div(ext.reindex(m.index), axis=0)
        fig = go.Figure(go.Heatmap(z=dens.values, x=dens.columns, y=dens.index, colorscale="Reds",
                                   text=m.values, texttemplate="%{text}",
                                   hovertemplate="SB %{y} · %{x}<br>%{z:.1f}/km (%{text})<extra></extra>"))
        fig.update_layout(height=80 + 26 * len(dens), margin=dict(l=10, r=10, t=10, b=40),
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True, config=CFG)


def _bloco_vagao(defeitos: pd.DataFrame, rel: pd.DataFrame) -> None:
    st.markdown("##### 🚨 Vagão de Via — defeitos que pedem velocidade abaixo da VMA e não têm restrição")
    v = defeitos[defeitos["origem"] == "VIA"]
    if v.empty:
        st.info("Sem defeitos do Vagão de Via nesta base.")
        return
    if rel is None or rel.empty:
        st.warning("Carregue o Relatório de Velocidade da base para cruzar com as restrições.")
        return
    viagens = sorted(v["numero_viagem"].dropna().astype(int).unique())
    c1, c2 = st.columns([1, 3])
    viagem = c1.selectbox("Viagem", viagens, index=len(viagens) - 1, key="vagao_viagem")
    cob = cobertura_restricao(v[v["numero_viagem"] == viagem], rel)
    abaixo = cob[cob["abaixo_vma"]]
    sem = abaixo[~abaixo["coberto"]].sort_values("km")
    menor35 = cob[cob["vel_max_classe_kmh"] < 35]
    k = st.columns(4)
    k[0].metric("Defeitos com classe na viagem", len(cob))
    k[1].metric("Classe abaixo da VMA", len(abaixo))
    k[2].metric("…cobertos por restrição", int(abaixo["coberto"].sum()))
    k[3].metric("…SEM restrição", len(sem), delta_color="off")
    c2.caption(f"Viagem {viagem}: {len(menor35)} defeitos pedem < 35 km/h — "
               f"{int(menor35['coberto'].sum())} cobertos, {int((~menor35['coberto']).sum())} sem restrição. "
               "Coberto = restrição A a até 50 m com velocidade ≤ à da classe.")
    cols = ["km", "sb_calc", "linha", "nome_defeito", "classe_via", "vel_max_classe_kmh", "vma",
            "tamanho", "extensao", "latitude", "longitude"]
    st.dataframe(sem[[c for c in cols if c in sem.columns]].rename(columns={
        "sb_calc": "SB", "nome_defeito": "Defeito", "classe_via": "Classe", "vel_max_classe_kmh": "Vel. classe",
        "vma": "VMA"}), hide_index=True, use_container_width=True, height=360)
    st.download_button("📥 Exportar Excel (com lat/long)",
                       gerar_excel_bytes(sem[[c for c in cols if c in sem.columns]], "Vagao sem restricao"),
                       file_name=f"vagao_viagem{viagem}_sem_restricao.xlsx", key="exp_vagao")
    por_sb = sem["sb_calc"].value_counts().head(6)
    if len(por_sb):
        st.caption("Concentração: " + " · ".join(f"{s} ({n})" for s, n in por_sb.items())
                   + " — tipos: " + " · ".join(f"{t} ({n})" for t, n in
                                               sem["nome_defeito"].value_counts().head(3).items()))


def render_defeitos(dados: dict) -> None:
    d = dados.get("defeitos")
    if d is None or d.empty:
        st.info("📭 Nenhum export de defeitos nesta base — envie na subaba **📤 Upload**.")
        return
    d = d.copy()
    if "status" in d.columns:
        d = d[d["status"].fillna("Ativo") == "Ativo"]
    d["sb_calc"] = sb_dos_defeitos(d, dados.get("dormentes"))
    _kpis(d)
    f = _filtros(d)
    st.caption(f"{len(f):,} defeitos no filtro.".replace(",", "."))
    _graficos(f, dados.get("dormentes"))
    _bloco_vagao(d, dados.get("rel"))

    geo = f.dropna(subset=["latitude", "longitude"])
    if len(geo):
        st.markdown(f"##### 🗺️ Defeitos com coordenada ({len(geo)})")
        st.map(geo.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]], size=20)
