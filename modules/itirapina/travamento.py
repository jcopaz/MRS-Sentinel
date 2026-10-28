# =============================================================================
# modules/itirapina/travamento.py — Visão 🎯 Travamento
#
# Enxuta: avanço (4 números) · mapa de calor por equipamento (LP em cima, LD
# embaixo, paleta do slide) com pontos C/T e Top 10 · Top 10 curvas |
# tangentes · ficha do equipamento por clique. Quadro (plano × base ×
# defeitos × restrições × execução) em cache por base.
# =============================================================================

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import cores_itirapina as cores
from core.analise_trecho import TRECHO_KM, restricoes_trecho
from core.plano_itirapina import DORM_POR_DIA, avanco_travamento, quadro_equipamentos, top_n
from modules.itirapina.execucao import MSG_FASE2, carregar_execucao

CFG = {"displaylogo": False, "displayModeBar": False}
# rótulo → (coluna, limiares, sufixo)
CORES_POR = {
    "Inservíveis": ("taxa_pct", cores.LIMIARES_SLIDE, "%"),
    "Travamento": ("dorm_travamento", (10.0, 30.0, 60.0, 100.0), " dorm."),
    "Executado": ("pct_exec", (0.0, 25.0, 50.0, 90.0), "%"),
}
CORES_EXEC = ("#cbd5e1", "#fde68a", "#fbbf24", "#86efac", "#15803d")


@st.cache_data(ttl=600, show_spinner=False)
def quadro_cache(base_id: int, assinatura_exec: tuple, _plano, _dados: dict, _e) -> pd.DataFrame:
    defe = _dados.get("defeitos")
    if defe is not None and not defe.empty and "status" in defe.columns:
        defe = defe[defe["status"].fillna("Ativo") == "Ativo"]
    rel = _dados.get("rel")
    rA = restricoes_trecho(rel) if rel is not None and not rel.empty else None
    return quadro_equipamentos(_plano, _dados.get("dormentes"), defe, rA, _e)


def assinatura(e: pd.DataFrame) -> tuple:
    return (len(e), str(e["data"].max()) if len(e) else "")


def _avanco(plano, e) -> None:
    av = avanco_travamento(plano, e)
    k = st.columns(4)
    k[0].metric("Trecho travado", f"{av['pct'] * 100:.0f}%",
                f"{av['executado']:,} de {av['travamento']:,} dormentes".replace(",", "."), delta_color="off")
    k[1].metric("Pontos críticos travados", f"{av['pontos_concluidos']} de {len(av['pontos'])}",
                help="C1–C3 / T1–T4 com ≥ 90% do travamento executado.")
    k[2].metric("Top 20 resolvidos", f"{av['top20_concluidos']} de 20")
    k[3].metric("Dias de equipe restantes", f"{av['equip']['dias_equipe'].sum():,.0f}".replace(",", "."),
                help=f"Travamento que falta ÷ {DORM_POR_DIA} dormentes/dia.")


def fig_mapa(f: pd.DataFrame, cor_por: str, pontos: pd.DataFrame | None, top: pd.DataFrame,
             km: tuple | None = None) -> go.Figure:
    col, lim, suf = CORES_POR[cor_por]
    paleta = CORES_EXEC if cor_por == "Executado" else cores.CORES_SLIDE
    fig = go.Figure()
    for linha, y in (("LP", 1), ("LD", 0)):
        g = f[f["linha"] == linha]
        if g.empty:
            continue
        fig.add_trace(go.Bar(
            x=g["ext_km"], base=g["km_inicio"], y=[y] * len(g), orientation="h", width=0.7,
            marker=dict(color=[cores.cor_por_faixa(v, lim, paleta) for v in g[col]], line_width=0),
            customdata=np.stack([g["equipamento_siv"], g["linha"]], axis=1),
            hovertext=[f"<b>{r.equipamento_siv}</b> · {r.linha}<br>km {r.km_inicio:.1f}–{r.km_fim:.1f} · "
                       f"{r.taxa_pct:.0f}% inservíveis · travamento {r.dorm_travamento:.0f} · "
                       f"executado {r.pct_exec:.0f}%" for r in g.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", showlegend=False))
    if pontos is not None and len(pontos):
        for p in pontos[pontos["ponto"].astype(str).str.match(r"^[CT]\d+$")].itertuples():
            fig.add_vrect(x0=p.km_inicio, x1=p.km_fim, fillcolor=cores.AZUL, opacity=0.08, line_width=0,
                          annotation_text=f"<b>{p.ponto}</b>", annotation_position="top left",
                          annotation_font=dict(size=11, color=cores.AZUL))
    t = top[top["linha"] == "LP"]
    if len(t):
        txt = [("C" if r.tipo == "curva" else "T") + str(int(r.rank_calc)) for r in t.itertuples()]
        fig.add_trace(go.Scatter(x=(t["km_inicio"] + t["km_fim"]) / 2, y=[1.5] * len(t), mode="markers",
                                 marker=dict(symbol="triangle-down", size=8, color=cores.AZUL),
                                 hovertext=[f"Top {x} · {r.equipamento_siv}" for x, r in zip(txt, t.itertuples())],
                                 hovertemplate="%{hovertext}<extra></extra>", showlegend=False))
    fig.update_layout(height=230, margin=dict(l=10, r=10, t=24, b=24), plot_bgcolor="#fff", bargap=0.1,
                      xaxis=dict(range=list(km or TRECHO_KM), ticksuffix=" km", showgrid=False),
                      yaxis=dict(tickvals=[0, 1], ticktext=["LD", "LP"], range=[-0.6, 1.8], fixedrange=True))
    return fig


def _legenda(cor_por: str) -> None:
    _, lim, suf = CORES_POR[cor_por]
    paleta = CORES_EXEC if cor_por == "Executado" else cores.CORES_SLIDE
    rot = [f"≤ {lim[0]:.0f}{suf}"] + [f"{a:.0f}–{b:.0f}" for a, b in zip(lim, lim[1:])] + [f"> {lim[-1]:.0f}{suf}"]
    st.markdown(" ".join(f"<span style='background:{c};color:{'#fff' if i else '#334155'};padding:1px 8px;"
                         f"border-radius:4px;font-size:0.75rem'>{r}</span>"
                         for i, (c, r) in enumerate(zip(paleta, rot))), unsafe_allow_html=True)


def _top10(q: pd.DataFrame, top: pd.DataFrame) -> None:
    t = top.merge(q[["equipamento_siv", "linha", "pct_exec", "taxa_pct"]], on=["equipamento_siv", "linha"],
                  how="left")
    c1, c2 = st.columns(2)
    for c, tipo, rot in ((c1, "curva", "curvas"), (c2, "tangente", "tangentes")):
        g = t[t["tipo"] == tipo]
        c.markdown(f"**Top 10 {rot}**")
        c.dataframe(g[["rank_calc", "equipamento_siv", "km_inicio", "taxa_pct", "dorm_travamento", "pct_exec"]],
                    hide_index=True, use_container_width=True, height=388, column_config={
                        "rank_calc": "#", "equipamento_siv": "Equipamento",
                        "km_inicio": st.column_config.NumberColumn("km", format="%.1f"),
                        "taxa_pct": st.column_config.NumberColumn("Inserv.", format="%.0f%%"),
                        "dorm_travamento": "Travam.",
                        "pct_exec": st.column_config.ProgressColumn("Executado", format="%.0f%%",
                                                                    min_value=0, max_value=100)})


def _ficha(q: pd.DataFrame, chave: tuple, dados: dict) -> None:
    sel = q[(q["equipamento_siv"] == chave[0]) & (q["linha"] == chave[1])]
    if sel.empty:
        return
    r = sel.iloc[0]
    geo = f"curva R {r.raio:.0f} m" if r.tipo == "curva" and pd.notna(r.raio) else "tangente"
    marca = " · ".join(x for x in (f"ponto {r.ponto_critico}" if pd.notna(r.ponto_critico) else "",
                                   f"Top 10 #{int(r.rank_top10)}" if pd.notna(r.rank_top10) else "") if x)
    with st.container(border=True):
        st.markdown(f"**📇 {r.equipamento_siv} · {r.linha}** — km {r.km_inicio:.3f}–{r.km_fim:.3f} · {geo} · "
                    f"SB {r.sb}" + (f" · **{marca}**" if marca else ""))
        k = st.columns(4)
        k[0].metric("Inservíveis", f"{r.taxa_pct:.1f}%",
                    f"{r.taxa_pct - r.taxa_mz_pct:+.1f} p.p." if pd.notna(r.taxa_mz_pct) and
                    abs(r.taxa_pct - r.taxa_mz_pct) > 0.05 else None, delta_color="inverse")
        k[1].metric("Travamento", f"{r.dorm_travamento:.0f} dorm.", f"meta 20%: {r.dorm_meta20:.0f}",
                    delta_color="off")
        k[2].metric("Executado", f"{r.pct_exec:.0f}%", f"{r.dias_equipe:.0f} dia(s) de equipe", delta_color="off")
        k[3].metric("Defeitos ativos", f"{r.defeitos:.0f}")
        st.caption(f"Restrições A: {r.restricoes or 'nenhuma'}")


def render_travamento(dados: dict, refs: dict, base_id: int) -> None:
    plano = refs.get("plano")
    if plano is None or plano.empty:
        st.warning(MSG_FASE2.format("plano"))
        return
    e, aviso = carregar_execucao()
    if aviso:
        st.caption(aviso)
    q = quadro_cache(base_id, assinatura(e), plano, dados, e)
    _avanco(plano, e)

    c1, c2, c3 = st.columns([2, 1.3, 1.5])
    cor_por = c1.segmented_control("Cor por", list(CORES_POR), default="Inservíveis", key="trv_cor") \
        or "Inservíveis"
    linha = c2.segmented_control("Linha", ["LP", "LD", "Ambas"], default="Ambas", key="trv_linha") or "Ambas"
    sem_restr = c3.toggle("Só sem restrição", key="trv_sem",
                          help="Dormentação ruim rodando na VMA (nenhuma restrição A sobre o equipamento).")
    f = q if linha == "Ambas" else q[q["linha"] == linha]
    if sem_restr:
        f = f[(f["restr_via"] + f["restr_antt"]) == 0]
    top = top_n(plano, 10)
    pontos = refs.get("pontos")
    ev = st.plotly_chart(fig_mapa(f, cor_por, pontos, top, st.session_state.get("itp_km")),
                         use_container_width=True, config=CFG, on_select="rerun", selection_mode="points",
                         key="trv_mapa")
    _legenda(cor_por)
    st.caption("Sombreado = ponto crítico · ▼ = Top 10 · clique numa barra para ver o equipamento.")

    pts = getattr(getattr(ev, "selection", None), "points", None) or []
    cd = next((p.get("customdata") for p in pts if p.get("customdata")), None)
    if cd:
        st.session_state["trv_ficha"] = (cd[0], cd[1])
    if st.session_state.get("trv_ficha"):
        _ficha(q, st.session_state["trv_ficha"], dados)
    _top10(q, top)
