# =============================================================================
# modules/itirapina/travamento.py — Subaba 🎯 Travamento (curvas e tangentes)
#
# O raciocínio dos slides "Mapa de calor" e "Top 10" dentro do app:
#   - mapa de calor por equipamento (LP em cima, LD embaixo) com o indicador
#     e a escala de cor escolhidos (preset do slide, meta 20% ou personalizada);
#   - pontos C/T oficiais do estudo sombreados + Top N numerado;
#   - "Recalcular" pontos críticos (core/plano_itirapina.pontos_criticos);
#   - quadro do Top N (curvas | tangentes) com travamento previsto × executado;
#   - ficha do equipamento (clique na barra ou seleção na lista).
# Dados: itp_plano (referência fixa) × base selecionada × itp_execucao.
# =============================================================================

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import cores_itirapina as cores
from core.analise_trecho import TRECHO_KM, restricoes_trecho
from core.plano_itirapina import (
    DORM_POR_DIA, pontos_criticos, quadro_equipamentos, top_n,
)
from modules.itirapina.execucao import MSG_FASE2, carregar_execucao

CFG = {"displaylogo": False}
# rótulo → (coluna, formato, é percentual?)
INDICADORES = {
    "Taxa de inservíveis (%)":       ("taxa_pct", "{:.1f}%", True),
    "Inservíveis (qtd)":             ("inserv_atual", "{:.0f}", False),
    "Malhas ≥ 3 seguidos":           ("malhas_3", "{:.0f}", False),
    "Dormentes de travamento":       ("dorm_travamento", "{:.0f}", False),
    "Meta 20% (dormentes)":          ("dorm_meta20", "{:.0f}", False),
    "Defeitos por km":               ("def_por_km", "{:.0f}", False),
    "% do travamento executado":     ("pct_exec", "{:.0f}%", True),
}


# region ── Controles ─────────────────────────────────────────────────────────

def _escala(q: pd.DataFrame, col: str, pct: bool) -> tuple[tuple, tuple]:
    preset = st.radio("Escala de cores", ["Slide", "Meta 20%", "Personalizada"], horizontal=True,
                      key="trv_preset", help="Slide = 10/20/30/40 %, verde → vinho.")
    if preset == "Slide" and pct:
        return cores.LIMIARES_SLIDE, cores.CORES_SLIDE
    if preset == "Meta 20%" and pct:
        return cores.LIMIARES_META20, cores.CORES_META20
    vmax = float(np.nanmax(q[col])) if q[col].notna().any() else 1.0
    padrao = cores.LIMIARES_SLIDE if pct else tuple(round(vmax * f, 1) for f in (0.2, 0.4, 0.6, 0.8))
    if preset != "Personalizada":
        return padrao, cores.CORES_SLIDE
    c = st.columns(5)
    lim = tuple(c[i].number_input(f"Limiar {i + 1}", value=float(padrao[i]), key=f"trv_lim{i}_{col}")
                for i in range(4))
    cs = tuple(c[i].color_picker(f"Faixa {i + 1}", cores.CORES_SLIDE[i], key=f"trv_cor{i}")
               for i in range(4)) + (c[4].color_picker("Faixa 5", cores.CORES_SLIDE[4], key="trv_cor4"),)
    return tuple(sorted(lim)), cs


def _filtros(q: pd.DataFrame) -> pd.DataFrame:
    c = st.columns([1.2, 1, 2, 1, 1.2, 1.6])
    tipo = c[0].selectbox("Tipo", ["Ambos", "Curva", "Tangente"], key="trv_tipo")
    linhas = c[1].multiselect("Linha", ["LP", "LD"], default=["LP", "LD"], key="trv_linha")
    sbs = c[2].multiselect("SB", list(dict.fromkeys(q.sort_values("km_inicio")["sb"].dropna())),
                           key="trv_sb", placeholder="Todas")
    raio = c[3].number_input("Raio máx. (m)", 0, 5000, 0, 50, key="trv_raio",
                             help="0 = sem filtro. Ex.: 400 para curvas apertadas.")
    taxa = c[4].slider("Taxa mín. (%)", 0, 60, 0, key="trv_taxa")
    restr = c[5].selectbox("Restrição A", ["Todos", "Só com restrição", "Só sem restrição"], key="trv_restr",
                           help="'Só sem restrição' = dormentação ruim rodando na VMA.")
    f = q[q["linha"].isin(linhas)]
    if tipo != "Ambos":
        f = f[f["tipo"] == tipo.lower()]
    if sbs:
        f = f[f["sb"].isin(sbs)]
    if raio:
        f = f[(f["tipo"] == "curva") & (f["raio"] <= raio)]
    f = f[f["taxa_pct"].fillna(0) >= taxa]
    n_restr = f["restr_via"] + f["restr_antt"]
    if restr == "Só com restrição":
        f = f[n_restr > 0]
    elif restr == "Só sem restrição":
        f = f[n_restr == 0]
    return f

# endregion


# region ── Gráficos ──────────────────────────────────────────────────────────

def fig_mapa(f: pd.DataFrame, col: str, fmt: str, lim, cs, pontos: pd.DataFrame | None,
             top: pd.DataFrame, km: tuple | None = None) -> go.Figure:
    fig = go.Figure()
    for linha, y in (("LP", 1), ("LD", 0)):
        g = f[f["linha"] == linha]
        if g.empty:
            continue
        fig.add_trace(go.Bar(
            x=g["ext_km"], base=g["km_inicio"], y=[y] * len(g), orientation="h", width=0.7,
            marker=dict(color=[cores.cor_por_faixa(v, lim, cs) for v in g[col]],
                        line=dict(color="#ffffff", width=0.5)),
            customdata=np.stack([g["equipamento_siv"], g["linha"]], axis=1),
            hovertext=[f"<b>{r.equipamento_siv}</b> · {r.linha} · {r.sb}<br>km {r.km_inicio:.3f}–{r.km_fim:.3f}"
                       f"{f' · R {r.raio:.0f} m' if r.tipo == 'curva' and pd.notna(r.raio) else ''}<br>"
                       f"{fmt.format(getattr(r, col)) if pd.notna(getattr(r, col)) else '—'}"
                       f" · travamento {r.dorm_travamento:.0f} · executado {r.pct_exec:.0f}%"
                       for r in g.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", name=linha, showlegend=False))
    if pontos is not None and len(pontos):
        for p in pontos.itertuples():
            if km and (p.km_fim < km[0] or p.km_inicio > km[1]):
                continue
            fig.add_vrect(x0=p.km_inicio, x1=p.km_fim, fillcolor="#1e3a5f", opacity=0.08, line_width=0,
                          annotation_text=f"<b>{p.ponto}</b>", annotation_position="top left",
                          annotation_textangle=-90, annotation_font_size=11)
    t = top[top["linha"] == "LP"]
    if len(t):
        mid = (t["km_inicio"] + t["km_fim"]) / 2
        txt = [("C#" if r.tipo == "curva" else "T#") + str(int(r.rank_calc)) for r in t.itertuples()]
        fig.add_trace(go.Scatter(x=mid, y=[1.55] * len(t), mode="markers+text", text=txt,
                                 textposition="top center", textfont=dict(size=9),
                                 marker=dict(symbol="triangle-down", size=9, color=cores.AZUL),
                                 hovertext=[f"{x} · {r.equipamento_siv} · km {r.km_inicio:.1f}"
                                            for x, r in zip(txt, t.itertuples())],
                                 hovertemplate="%{hovertext}<extra></extra>", showlegend=False))
    rng = list(km) if km else list(TRECHO_KM)
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=30), plot_bgcolor="#fff", bargap=0.1,
                      xaxis=dict(title="km", range=rng, showgrid=True, gridcolor="#f1f5f9"),
                      yaxis=dict(tickvals=[0, 1], ticktext=["LD", "LP"], range=[-0.6, 2.1]),
                      dragmode="zoom")
    return fig


def _legenda(lim, cs, fmt) -> None:
    rot = [f"≤ {fmt.format(lim[0])}"] + [f"{fmt.format(a)}–{fmt.format(b)}" for a, b in zip(lim, lim[1:])] \
        + [f"> {fmt.format(lim[-1])}"]
    st.markdown(" ".join(f"<span style='background:{c};color:#fff;padding:2px 8px;border-radius:4px;"
                         f"font-size:0.78rem;margin-right:4px'>{r}</span>" for c, r in zip(cs, rot)),
                unsafe_allow_html=True)

# endregion


# region ── Quadros e ficha ───────────────────────────────────────────────────

def _quadro_top(q: pd.DataFrame, top: pd.DataFrame) -> None:
    t = top.merge(q[["equipamento_siv", "linha", "executado", "pct_exec", "taxa_pct", "dias_equipe"]],
                  on=["equipamento_siv", "linha"], how="left")
    c1, c2 = st.columns(2)
    for c, tipo in ((c1, "curva"), (c2, "tangente")):
        g = t[t["tipo"] == tipo]
        c.markdown(f"**Top {len(g)} {'curvas' if tipo == 'curva' else 'tangentes'}**")
        cols = ["rank_calc", "equipamento_siv", "km_inicio", "taxa_pct", "dorm_travamento", "pct_exec",
                "dias_equipe"] + (["raio"] if tipo == "curva" else [])
        c.dataframe(g[cols], hide_index=True, use_container_width=True, column_config={
            "rank_calc": "#", "equipamento_siv": "Equipamento", "raio": st.column_config.NumberColumn(
                "Raio", format="%.0f m"),
            "km_inicio": st.column_config.NumberColumn("km", format="%.1f"),
            "taxa_pct": st.column_config.NumberColumn("Taxa", format="%.1f%%"),
            "dorm_travamento": "Travam.",
            "pct_exec": st.column_config.ProgressColumn("Executado", format="%.0f%%", min_value=0, max_value=100),
            "dias_equipe": st.column_config.NumberColumn("Dias equipe", help=f"falta ÷ {DORM_POR_DIA} dorm/dia")})


def _ficha(q: pd.DataFrame, chave: tuple, dados: dict) -> None:
    sel = q[(q["equipamento_siv"] == chave[0]) & (q["linha"] == chave[1])]
    if sel.empty:
        return
    r = sel.iloc[0]
    st.markdown(f"#### 📇 {r.equipamento_siv} · {r.linha}")
    geo = f"curva R {r.raio:.0f} m" if r.tipo == "curva" and pd.notna(r.raio) else "tangente"
    st.caption(f"km {r.km_inicio:.3f}–{r.km_fim:.3f} ({r.ext_km * 1000:.0f} m) · {geo} · SB {r.sb}"
               + (f" · ponto crítico **{r.ponto_critico}**" if pd.notna(r.ponto_critico) else "")
               + (f" · Top 10 #{int(r.rank_top10)}" if pd.notna(r.rank_top10) else ""))
    k = st.columns(5)
    k[0].metric("Taxa (marco zero → agora)", f"{r.taxa_pct:.1f}%",
                f"{r.taxa_pct - r.taxa_mz_pct:+.1f} p.p." if pd.notna(r.taxa_mz_pct) else None,
                delta_color="inverse")
    k[1].metric("Inservíveis", f"{r.inserv_atual:.0f}" if pd.notna(r.inserv_atual) else "—",
                f"malhas ≥3: {r.malhas_3:.0f}" if pd.notna(r.malhas_3) else None, delta_color="off")
    k[2].metric("Travamento", f"{r.dorm_travamento:.0f}", f"meta 20%: {r.dorm_meta20:.0f}", delta_color="off")
    k[3].metric("Executado", f"{r.executado:.0f} ({r.pct_exec:.0f}%)",
                f"{r.dias_equipe:.0f} dia(s) de equipe", delta_color="off")
    k[4].metric("Defeitos ativos", f"{r.defeitos:.0f}", f"{r.def_por_km:.0f}/km" if pd.notna(r.def_por_km)
                else None, delta_color="off")
    st.markdown(f"**Restrições A:** {r.restricoes or 'nenhuma'}")
    d = dados.get("defeitos")
    if d is not None and not d.empty:
        dd = d[d["equipamento_siv"] == r.equipamento_siv]
        if "status" in dd.columns:
            dd = dd[dd["status"].fillna("Ativo") == "Ativo"]
        if len(dd):
            st.markdown("**Defeitos por grupo:** " + " · ".join(
                f"{g} ({n})" for g, n in dd["grupo"].fillna("—").value_counts().items()))
            via = dd[dd["origem"] == "VIA"]
            if len(via):
                st.markdown(f"**Vagão de Via:** {len(via)} ponto(s)")
    for nome, cols in (("lastro", ("cont_severa", "bolsao_bombeando", "bolsao_nao_bombeando")),
                       ("trilho", ("junta_taco", "junta_tala_quebrada", "junta_desligada"))):
        t = dados.get(nome)
        if t is not None and not t.empty and "equipamento_siv" in t.columns:
            tt = t[(t["equipamento_siv"] == r.equipamento_siv) & (t["linha"] == r.linha)]
            vals = {c: pd.to_numeric(tt[c], errors="coerce").sum() for c in cols if c in tt.columns}
            if vals and any(v > 0 for v in vals.values()):
                st.markdown(f"**{nome.capitalize()}:** " + " · ".join(
                    f"{c.replace('_', ' ')} {v:.0f}" for c, v in vals.items() if v > 0))
    insp = dados.get("inspecao")
    if insp is not None and not insp.empty and "km" in insp.columns:
        n = int(((insp["km"] >= r.km_inicio - 0.05) & (insp["km"] <= r.km_fim + 0.05)).sum())
        if n:
            st.markdown(f"**Inspeções de campo:** {n} registro(s) — ver subaba 📷 Inspeção")
    if st.button("🛤️ Ver no unifilar", key="trv_ver_unifilar",
                 help="Ajusta a janela de km da aba para o equipamento ±0,5 km."):
        st.session_state["itp_km"] = (max(TRECHO_KM[0], round(r.km_inicio - 0.5, 1)),
                                      min(TRECHO_KM[1], round(r.km_fim + 0.5, 1)))
        st.toast("Janela de km ajustada — abra a subaba 🛤️ Unifilar.")

# endregion


def render_travamento(dados: dict, refs: dict) -> None:
    plano = refs.get("plano")
    if plano is None or plano.empty:
        st.warning(MSG_FASE2.format("plano"))
        return
    e, aviso = carregar_execucao()
    if aviso:
        st.caption(aviso)
    defe = dados.get("defeitos")
    if defe is not None and not defe.empty and "status" in defe.columns:
        defe = defe[defe["status"].fillna("Ativo") == "Ativo"]
    rel = dados.get("rel")
    rA = restricoes_trecho(rel) if rel is not None and not rel.empty else None
    q = quadro_equipamentos(plano, dados.get("dormentes"), defe, rA, e)

    c1, c2 = st.columns([2, 3])
    ind = c1.selectbox("Indicador da cor", list(INDICADORES), key="trv_ind")
    col, fmt, pct = INDICADORES[ind]
    with c2:
        lim, cs = _escala(q, col, pct)
    f = _filtros(q)
    n = st.slider("Top N", 5, 20, 10, key="trv_n")
    top = top_n(plano, n).merge(q[["equipamento_siv", "linha"]], on=["equipamento_siv", "linha"])

    pontos = refs.get("pontos")
    pontos = pontos[pontos["ponto"].astype(str).str.match(r"^[CT]\d+$")] if pontos is not None and len(pontos) \
        else pd.DataFrame()
    with st.expander("🎯 Pontos críticos — recalcular"):
        a, b, c, d = st.columns([1, 1, 1, 2])
        jan = a.number_input("Janela (km)", 1.0, 10.0, 3.0, 0.5, key="trv_jan")
        nc = b.number_input("Curvas", 1, 10, 3, key="trv_nc")
        nt = c.number_input("Tangentes", 1, 10, 4, key="trv_nt")
        usar = d.toggle("Usar os recalculados no mapa", key="trv_usar_calc",
                        help="Desligado = pontos oficiais do estudo (C1–C3 / T1–T4).")
        calc = pontos_criticos(plano, jan, int(nc), int(nt))
        st.dataframe(calc, hide_index=True, use_container_width=True)
        st.caption("Critério: janela com a maior soma de inservíveis (LP), sem reaproveitar equipamento, "
                   "curvas e tangentes separadas. Com o padrão reproduz C1, T1 e T2; os demais pontos do "
                   "estudo tiveram ajuste manual.")
        if usar:
            pontos = calc

    km = st.session_state.get("itp_km")
    st.markdown(f"##### 🔥 Mapa de calor — {ind} ({len(f)} equipamentos)")
    _legenda(lim, cs, "{:.0f}%" if pct else "{:.0f}")
    ev = st.plotly_chart(fig_mapa(f, col, fmt, lim, cs, pontos, top, km), use_container_width=True,
                         config=CFG, on_select="rerun", selection_mode="points", key="trv_mapa")
    st.caption("Clique numa barra para abrir a ficha · sombreado = ponto crítico · ▼ = Top N"
               + (" · janela de km da aba aplicada" if km else ""))

    st.markdown(f"##### 🏆 Top {n} — travamento previsto × executado")
    _quadro_top(q, top)

    st.markdown("##### 📇 Ficha do equipamento")
    pts = (ev or {}).get("selection", {}).get("points", []) if isinstance(ev, dict) else \
        getattr(getattr(ev, "selection", None), "points", []) or []
    opcoes = list(zip(f.sort_values("km_inicio")["equipamento_siv"], f.sort_values("km_inicio")["linha"]))
    if pts and pts[0].get("customdata"):
        st.session_state["trv_ficha"] = tuple(pts[0]["customdata"][:2])
    if not opcoes:
        st.info("Nenhum equipamento no filtro.")
        return
    if st.session_state.get("trv_ficha") not in opcoes:
        st.session_state["trv_ficha"] = opcoes[0]
    chave = st.selectbox("Equipamento", opcoes, format_func=lambda k: f"{k[0]} · {k[1]}", key="trv_ficha")
    _ficha(q, chave, dados)
