# =============================================================================
# modules/itirapina/onepage.py — Subaba 🏁 One Page
#
# Peça de comunicação para Operação, gerentes e executivos (leitura em 30 s):
# cards "antes → agora" (o que é mérito da Manutenção à esquerda, em
# destaque), ① esquemático das restrições, ② dormentação, ③ transit time,
# ④ travamento, ⑤ o que fizemos + frases. Dados: core/onepage.montar_onepage
# (o MESMO dict que a exportação PNG/PDF/PPTX usa).
# Marco zero × base selecionada; com só o marco zero → modo "Ponto de partida".
# =============================================================================

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import cores_itirapina as cores
from core.analise_trecho import TRECHO_KM
from core.onepage import montar_onepage
from core.onepage_textos import _n
from modules.itirapina.dados import carregar_base
from modules.itirapina.evolucao import foto_da_base
from modules.itirapina.execucao import carregar_execucao

CFG = {"displaylogo": False, "displayModeBar": False}
COR_CARD = {"bom": "#16a34a", "ruim": "#dc2626", "neutro": "#64748b"}


def _base_mz(bases: pd.DataFrame):
    mz = bases[bases["marco_zero"].fillna(False)]
    return (mz if len(mz) else bases.sort_values("data_base")).iloc[0]


@st.cache_data(ttl=300, show_spinner=False)
def _dados_base(base_id: int) -> dict:
    return carregar_base(base_id)


def dados_onepage(bases: pd.DataFrame, base_atual, refs: dict) -> dict:
    """Carrega marco zero + base atual do banco e monta o dict da One Page."""
    mz = _base_mz(bases)
    d_mz = _dados_base(int(mz["id"]))
    f_mz = foto_da_base(int(mz["id"]), mz["data_base"], refs)
    evol = base_atual is not None and int(base_atual["id"]) != int(mz["id"])
    kw = {}
    if evol:
        d_b = _dados_base(int(base_atual["id"]))
        kw = dict(foto_atual=foto_da_base(int(base_atual["id"]), base_atual["data_base"], refs),
                  rel_atual=d_b["rel"], dorm_atual=d_b["dormentes"], defeitos_atual=d_b["defeitos"])
    e, _ = carregar_execucao()
    return montar_onepage(
        data_mz=pd.to_datetime(mz["data_base"]).date(),
        data_atual=pd.to_datetime((base_atual if evol else mz)["data_base"]).date(),
        foto_mz=f_mz, rel_mz=d_mz["rel"], dorm_mz=d_mz["dormentes"], defeitos_mz=d_mz["defeitos"],
        transit=d_mz["transit"], plano=refs.get("plano"), execucao=e, metas=refs.get("metas"),
        estacoes=refs.get("estacoes"), pontos=refs.get("pontos"), **kw)


# region ── Blocos ────────────────────────────────────────────────────────────

def _cards(o: dict) -> None:
    cs = st.columns(len(o["cards"]))
    for c, k in zip(cs, o["cards"]):
        cor = COR_CARD[k["cor"]]
        antes = (f"<span style='color:#94a3b8;font-size:1.0rem'>{k['antes']} → </span>"
                 if k["antes"] else "")
        delta = f"<span style='color:{cor};font-size:0.85rem;margin-left:4px'>{k['delta']}</span>" \
            if k["delta"] else ""
        borda = f"border-top:4px solid {cores.AZUL if k['destaque'] else '#cbd5e1'}"
        c.markdown(
            f"<div title='{k['ajuda']}' style='background:#fff;{borda};border-radius:8px;padding:8px 10px;"
            f"box-shadow:0 1px 3px rgba(0,0,0,.08);min-height:118px'>"
            f"<div style='font-size:0.7rem;color:#475569;font-weight:700;letter-spacing:.03em'>{k['titulo']}</div>"
            f"<div style='font-size:1.45rem;font-weight:700;color:{cor if k['cor'] != 'neutro' else '#0f172a'};"
            f"line-height:1.6'>{antes}{k['valor']}{delta}</div>"
            f"<div style='font-size:0.72rem;color:#64748b'>{k['rodape']}</div></div>",
            unsafe_allow_html=True)


def fig_esquematico(o: dict, altura: int = 230) -> go.Figure:
    fig = go.Figure()
    fig.add_shape(type="line", x0=TRECHO_KM[0], x1=TRECHO_KM[1], y0=0, y1=0, line=dict(color="#334155", width=4))
    e = o["estacoes"]
    if len(e):
        e = e[(e["km_fim"] >= TRECHO_KM[0] - 6) & (e["km_inicio"] <= TRECHO_KM[1])]
        fig.add_trace(go.Scatter(x=e[["km_inicio", "km_fim"]].mean(axis=1).clip(*TRECHO_KM), y=[0] * len(e),
                                 mode="markers+text", text=e["codigo"], textposition="bottom center",
                                 marker=dict(symbol="line-ns", size=14, line=dict(width=2, color="#334155")),
                                 textfont=dict(size=10, color="#334155"), hoverinfo="skip", showlegend=False))
    r = o["restricoes"]
    if len(r):
        r = r.sort_values("a").reset_index(drop=True)
        fim = [-1e9] * 3
        larg = 9.0
        for x in r.itertuples():
            meio = (x.a + x.b) / 2
            t = next((i for i, f in enumerate(fim) if meio - larg / 2 > f), 2)
            fim[t] = meio + larg / 2
            cor = cores.RETIRADA if x.status == "retirada" else cores.VIA if x.grupo == "via" else cores.ANTT
            y = 0.35 + 0.33 * t
            fig.add_shape(type="rect", x0=x.a - 0.25, x1=max(x.b, x.a) + 0.25, y0=-0.12, y1=0.12,
                          fillcolor=cor, line_width=0)
            txt = f"{x.vel:.0f} · {x.motivo} · km {_n(x.a, 1)}"
            if x.status == "retirada":
                txt = f"<s>{txt}</s> ✔"
            fig.add_annotation(x=meio, y=y, text=txt, showarrow=True, ax=0, ay=0, axref="pixel",
                               font=dict(size=8.5, color=cor), bgcolor="rgba(255,255,255,0.85)")
            fig.add_shape(type="line", x0=meio, x1=meio, y0=0.12, y1=y - 0.08, line=dict(color=cor, width=0.6))
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="#fff",
                      xaxis=dict(range=[TRECHO_KM[0] - 1, TRECHO_KM[1] + 1], showgrid=False, title=None,
                                 tickformat=".0f"),
                      yaxis=dict(range=[-0.5, 1.3], visible=False), showlegend=False)
    return fig


def fig_dormentacao(o: dict, altura: int = 230) -> go.Figure:
    fig = go.Figure()
    d = o["dorm"]
    for linha, y in (("LP", 1.0), ("LD", 0.0)):
        g = d[d["linha"] == linha]
        if len(g):
            fig.add_trace(go.Bar(x=(g["km_fim"] - g["km_inicio"]).abs(), base=g["km_inicio"], y=[y] * len(g),
                                 orientation="h", width=0.5,
                                 marker=dict(color=[cores.cor_por_faixa(v, cores.LIMIARES_SLIDE, cores.CORES_SLIDE)
                                                    for v in g["taxa_pct"]], line_width=0),
                                 hovertext=[f"{r.equipamento_siv} · {r.taxa_pct:.1f}%" for r in g.itertuples()],
                                 hovertemplate="%{hovertext}<extra></extra>", showlegend=False))
        ref = o.get("dorm_ref")
        if ref is not None and len(ref):
            h = ref[ref["linha"] == linha]
            fig.add_trace(go.Bar(x=(h["km_fim"] - h["km_inicio"]).abs(), base=h["km_inicio"], y=[y + 0.38] * len(h),
                                 orientation="h", width=0.12,
                                 marker=dict(color=[cores.cor_por_faixa(v, cores.LIMIARES_SLIDE, cores.CORES_SLIDE)
                                                    for v in h["taxa_pct"]], line_width=0),
                                 hoverinfo="skip", showlegend=False))
    p = o["pontos"]
    if len(p):
        for x in p[p["ponto"].astype(str).str.match(r"^[CT]\d$")].itertuples():
            fig.add_vrect(x0=x.km_inicio, x1=x.km_fim, fillcolor=cores.AZUL, opacity=0.1, line_width=0,
                          annotation_text=x.ponto, annotation_position="top left", annotation_textangle=-90,
                          annotation_font_size=9)
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=18, b=20), plot_bgcolor="#fff", bargap=0,
                      xaxis=dict(range=list(TRECHO_KM), tickformat=".0f"),
                      yaxis=dict(tickvals=[0, 1], ticktext=["LD", "LP"], range=[-0.5, 1.7]))
    return fig


def fig_transit(o: dict, altura: int = 230) -> go.Figure:
    fig = go.Figure()
    t = o["transit"]
    paleta = {"ZIQ→ZPD": cores.AZUL, "ZPD→ZIQ": cores.LARANJA}
    for s, g in t.groupby("sentido"):
        g = g.sort_values("mes")
        cor = paleta.get(s, cores.NEUTRO)
        fig.add_trace(go.Scatter(x=g["mes"], y=g["mediana"], mode="lines+markers", name=f"{s} mediana",
                                 line=dict(color=cor, width=2.5)))
        fig.add_trace(go.Scatter(x=g["mes"], y=g["media"], mode="lines", name=f"{s} média",
                                 line=dict(color=cor, width=1, dash="dot")))
        ref = o["transit_ref"].get(s) or {}
        if ref.get("mediana") is not None:
            fig.add_hline(y=ref["mediana"], line=dict(color=cor, dash="dash", width=1),
                          annotation_text=f"marco zero {_n(ref['mediana'], 1)} h", annotation_font_size=8)
        if ref.get("programado") is not None:
            fig.add_hline(y=ref["programado"], line=dict(color="#94a3b8", dash="dashdot", width=1))
        u = g.iloc[-1]
        fig.add_annotation(x=u["mes"], y=u["mediana"], text=f"{_n(u['mediana'], 1)} h", showarrow=False,
                           yshift=10, font=dict(size=9, color=cor))
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=10, b=20), plot_bgcolor="#fff", yaxis_title="h",
                      xaxis=dict(type="date", tickformat="%m/%y"), legend=dict(orientation="h", y=-0.25, font_size=9))
    return fig


def fig_travamento(o: dict, altura: int = 230) -> go.Figure:
    p = o["travamento"]
    fig = go.Figure()
    if len(p):
        p = p.sort_values("ponto_critico", ascending=False)
        fig.add_trace(go.Bar(
            x=p["pct"] * 100, y=p["ponto_critico"], orientation="h",
            marker_color=[cores.SITUACAO[s] for s in p["situacao"]],
            text=[f"{r.ponto_critico} · km {_n(r.km_inicio, 1)}–{_n(r.km_fim, 1)} · {_n(r.travamento)} dorm. · "
                  f"{_n(r.pct * 100)}%" for r in p.itertuples()],
            textposition="outside", textfont_size=9, cliponaxis=False, showlegend=False))
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=10, b=20), plot_bgcolor="#fff",
                      xaxis=dict(range=[0, 140], title="% executado", tickvals=[0, 25, 50, 75, 100]))
    return fig


def _top10_bolinhas(o: dict) -> str:
    t = o["top"]
    if t is None or len(t) == 0:
        return ""
    linhas = []
    for tipo, rot in (("curva", "Top 10 curvas"), ("tangente", "Top 10 tangentes")):
        g = t[t["tipo"] == tipo].sort_values("rank_calc")
        bol = "".join(f"<span title='#{int(r.rank_calc)} {r.equipamento_siv}' style='display:inline-block;width:14px;"
                      f"height:14px;border-radius:50%;margin-right:3px;background:{cores.SITUACAO[r.situacao]}'></span>"
                      for r in g.itertuples())
        linhas.append(f"<div style='font-size:0.75rem;color:#475569'>{rot} &nbsp;{bol}</div>")
    leg = " · ".join(f"<span style='color:{c}'>●</span> {s}" for s, c in cores.SITUACAO.items())
    return "".join(linhas) + f"<div style='font-size:0.7rem;color:#94a3b8'>{leg}</div>"


def _bloco_feito(o: dict) -> None:
    if o["modo"] == "partida":
        st.markdown("**⑤ O PLANO**")
        p = o["plano"]
        st.markdown(f"- **{p['pontos']}** pontos críticos (C1–C3 / T1–T4)\n"
                    f"- **{_n(p['travamento'])}** dormentes de travamento\n"
                    f"- **{p['restricoes_via']}** restrições de via a retirar\n"
                    f"- **{p['vagao']}** pontos do Vagão a tratar")
    else:
        st.markdown("**⑤ O QUE FIZEMOS** (desde o marco zero)")
        f = o["feito"]
        if len(f):
            st.markdown("  \n".join(f"{r.icone} **{_n(r.total)}** {r.unidade} · {r.rotulo}" for r in f.itertuples()))
        else:
            st.caption("Nenhuma execução registrada (subaba 🔧 Execução).")
    for fr in o["frases"]:
        st.markdown(f"> {fr}")

# endregion


def render_onepage(bases: pd.DataFrame, base_atual, refs: dict) -> None:
    if bases is None or bases.empty:
        st.info("A One Page usa as bases versionadas — carregue o marco zero.")
        return
    with st.spinner("Montando a One Page..."):
        o = dados_onepage(bases, base_atual, refs)

    from modules.itirapina.exportar_onepage import botoes_exportar
    botoes_exportar(o)

    st.markdown(
        f"<div style='background:{cores.AZUL};color:#fff;padding:10px 16px;border-radius:8px'>"
        f"<div style='font-size:1.15rem;font-weight:700'>{o['titulo']} "
        f"<span style='font-weight:400;font-size:0.9rem'>({o['subtitulo']})</span></div>"
        f"<div style='font-size:0.85rem;opacity:.85'>{o['linha_datas']}</div></div>", unsafe_allow_html=True)
    st.write("")
    _cards(o)
    seg = o["seguranca"]
    txt = []
    if seg.get("dias_sem_acidente") is not None:
        txt.append(f"🦺 **{seg['dias_sem_acidente']} dias** sem acidente de via")
    if seg.get("defeitos_acidente"):
        txt.append(f"{_n(seg['defeitos_acidente'])} defeitos ligados a acidente")
    if txt:
        st.caption(" · ".join(txt))

    st.markdown("**① ESQUEMÁTICO DO TRECHO** — cada restrição no km real")
    st.plotly_chart(fig_esquematico(o), use_container_width=True, config=CFG)
    st.caption(f"<span style='color:{cores.VIA}'>■</span> restrição de via (Manutenção resolve) · "
               f"<span style='color:{cores.ANTT}'>■</span> ANTT/PN/perímetro urbano (terceiros) · "
               f"<span style='color:{cores.RETIRADA}'>■</span> retirada", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**② DORMENTAÇÃO INSERVÍVEL** por equipamento"
                    + (" (fino = marco zero)" if o.get("dorm_ref") is not None else ""))
        st.plotly_chart(fig_dormentacao(o), use_container_width=True, config=CFG)
    with c2:
        st.markdown("**③ TRANSIT TIME MÊS A MÊS** (tracejado = marco zero)")
        st.plotly_chart(fig_transit(o), use_container_width=True, config=CFG)
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**④ TRAVAMENTO – 7 PONTOS E TOP 10**")
        st.plotly_chart(fig_travamento(o), use_container_width=True, config=CFG)
        st.markdown(_top10_bolinhas(o), unsafe_allow_html=True)
    with c4:
        _bloco_feito(o)
        if o["proximos"]:
            st.caption("**Próximos passos:** " + " · ".join(o["proximos"]))
    st.caption(o["fontes"])
