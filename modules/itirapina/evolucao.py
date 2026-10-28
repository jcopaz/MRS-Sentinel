# =============================================================================
# modules/itirapina/evolucao.py — Visão 📈 Evolução (base A × base B)
#
# Enxuta: 8 indicadores com seta pelo sentido bom · mudanças nas restrições
# (eventos da base) · transit time mês a mês por sentido (absorve a antiga
# subaba Transit) · linha do tempo das bases (só com ≥ 2 bases).
# Foto de indicadores: lê itp_trecho_indicadores; sem foto, calcula na hora
# (core/indicadores_trecho.calcular) sem gravar — em cache por base.
# =============================================================================

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import cores_itirapina as cores
from core.indicadores_trecho import CATALOGO, CATALOGO_TRANSIT, calcular
from core.parser_transit_time import resumo_mensal
from core.ui_evolucao import bloco_cards
from database.queries_prospeccao import TabelaAusente
from database.queries_trecho import get_indicadores
from modules.itirapina.dados import carregar_base

CFG = {"displaylogo": False, "displayModeBar": False}
KPIS = ["restricoes_via", "restricoes_antt", "v_media_praticada", "minutos_perdidos",
        "taxa_inserviveis_pct", "defeitos_ativos", "vagao_sem_restricao"]


def _rotulo_base(b) -> str:
    return f"{pd.to_datetime(b.data_base):%d/%m/%Y}" + (" · marco zero" if b.marco_zero else "") \
        + (" 🔒" if b.congelada else "")


@st.cache_data(ttl=600, show_spinner=False)
def _foto(base_id: int, data_base: str, _refs: dict) -> pd.DataFrame:
    try:
        f = get_indicadores((int(base_id),))
    except (TabelaAusente, Exception):
        f = pd.DataFrame()
    if not f.empty:
        f["valor"] = pd.to_numeric(f["valor"], errors="coerce")
        return f
    dados = carregar_base(int(base_id))
    dados["pontos"] = _refs.get("pontos")
    return calcular(dados, pd.to_datetime(data_base).date())


def foto_da_base(base_id: int, data_base, refs: dict) -> pd.DataFrame:
    return _foto(int(base_id), str(pd.to_datetime(data_base).date()), refs)


def _total(foto: pd.DataFrame) -> pd.Series:
    if foto is None or foto.empty:
        return pd.Series(dtype=float)
    f = foto[(foto["escopo"] == "trecho") & (foto["chave"] == "TOTAL")]
    return f.set_index("indicador")["valor"]


def _transit(foto: pd.DataFrame, sentido: str) -> pd.Series:
    if foto is None or foto.empty:
        return pd.Series(dtype=float)
    f = foto[(foto["escopo"] == "transit") & (foto["chave"] == sentido)]
    return f.set_index("indicador")["valor"]


def _eventos(ev: pd.DataFrame | None) -> None:
    if ev is None or ev.empty:
        return
    from core.eventos_restricao import motivo_legivel
    st.markdown("##### 🔁 Restrições em relação à base anterior")
    e = ev.assign(motivo_txt=ev["motivo"].map(motivo_legivel)).sort_values(["evento", "km_de"])
    st.dataframe(e[["evento", "grupo", "linha", "km_de", "vel_antes", "vel_depois", "motivo_txt"]],
                 hide_index=True, use_container_width=True, column_config={
                     "evento": "Evento", "grupo": "Grupo", "linha": "Linha",
                     "km_de": st.column_config.NumberColumn("km", format="%.2f"),
                     "vel_antes": st.column_config.NumberColumn("Antes", format="%.0f km/h"),
                     "vel_depois": st.column_config.NumberColumn("Depois", format="%.0f km/h"),
                     "motivo_txt": "Motivo"})


def _fig_transit(transit: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    paleta = {"ZIQ→ZPD": cores.AZUL, "ZPD→ZIQ": cores.LARANJA}
    for s, g in transit.groupby("sentido"):
        m = resumo_mensal(g)
        if m.empty:
            continue
        x = pd.to_datetime(m["mes"] + "-01")
        fig.add_trace(go.Scatter(x=x, y=m["mediana"], mode="lines+markers", name=f"{s} · mediana",
                                 line=dict(color=paleta.get(s, cores.NEUTRO), width=2.5)))
        fig.add_trace(go.Scatter(x=x, y=m["p90"], mode="lines", name=f"{s} · P90",
                                 line=dict(color=paleta.get(s, cores.NEUTRO), width=1, dash="dot")))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=30), plot_bgcolor="#fff", yaxis_title="horas",
                      xaxis=dict(type="date", tickformat="%m/%Y"), legend=dict(orientation="h", y=1.15))
    return fig


def _linha_do_tempo(bases: pd.DataFrame, refs: dict) -> None:
    pts = []
    for b in bases.itertuples():
        t = _total(foto_da_base(b.id, b.data_base, refs))
        pts.append({"data": pd.to_datetime(b.data_base), "Restrições de via": t.get("restricoes_via"),
                    "Inservíveis %": t.get("taxa_inserviveis_pct"), "Defeitos ativos": t.get("defeitos_ativos")})
    p = pd.DataFrame(pts)
    fig = go.Figure()
    for col, eixo, cor in (("Defeitos ativos", "y", "#94a3b8"), ("Restrições de via", "y2", cores.VIA),
                           ("Inservíveis %", "y2", cores.LARANJA)):
        fig.add_trace(go.Scatter(x=p["data"], y=p[col], mode="lines+markers", name=col, yaxis=eixo,
                                 line=dict(color=cor, width=2.5)))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=30), plot_bgcolor="#fff",
                      xaxis=dict(type="date", tickformat="%m/%Y"), yaxis=dict(title="defeitos"),
                      yaxis2=dict(title="restrições / %", overlaying="y", side="right"),
                      legend=dict(orientation="h", y=1.15))
    st.plotly_chart(fig, use_container_width=True, config=CFG)


def render_evolucao(bases: pd.DataFrame, refs: dict, dados: dict) -> None:
    if bases is None or bases.empty:
        st.info("A Evolução usa as bases versionadas — carregue o marco zero.")
        return
    bases = bases.sort_values("data_base").reset_index(drop=True)
    rot = {int(b.id): _rotulo_base(b) for b in bases.itertuples()}
    ids = list(rot)
    mz = bases[bases["marco_zero"].fillna(False)]
    c1, c2 = st.columns(2)
    id_a = c1.selectbox("Comparar com", ids, index=ids.index(int(mz.iloc[0]["id"])) if len(mz) else 0,
                        format_func=rot.get, key="evo_a")
    id_b = c2.selectbox("Base", ids, index=len(ids) - 1, format_func=rot.get, key="evo_b")
    with st.spinner("Calculando indicadores..."):
        fa = foto_da_base(id_a, bases.loc[bases["id"] == id_a, "data_base"].iloc[0], refs)
        fb = fa if id_b == id_a else foto_da_base(id_b, bases.loc[bases["id"] == id_b, "data_base"].iloc[0], refs)
    ta, tb = _total(fa), _total(fb)
    mesmo = id_a == id_b
    itens = [(CATALOGO[k][0], tb.get(k), None if mesmo else ta.get(k), CATALOGO[k][1], CATALOGO[k][2])
             for k in KPIS if k in tb.index or k in ta.index]
    sa, sb = _transit(fa, "ZIQ→ZPD"), _transit(fb, "ZIQ→ZPD")
    if "mediana" in sb.index:
        rotulo, sentido, fmt = CATALOGO_TRANSIT["mediana"]
        itens.append((f"{rotulo} ZIQ→ZPD", sb.get("mediana"), None if mesmo else sa.get("mediana"), sentido, fmt))
    if mesmo:
        st.caption("Uma base só — as setas aparecem quando há outra base para comparar.")
    bloco_cards(itens, colunas=4)

    _eventos(dados.get("eventos"))
    transit = dados.get("transit")
    if transit is not None and not transit.empty:
        st.markdown("##### 🚆 Transit time mês a mês")
        v = transit[transit["valido"] & ~transit["outlier"]]
        st.plotly_chart(_fig_transit(v), use_container_width=True, config=CFG)
        st.caption("Trens encerrados, sem outliers (> 72 h). Inclui circulação, cruzamentos e pátio — "
                   "a melhoria de via aparece antes na velocidade praticada.")
    if len(bases) >= 2:
        st.markdown("##### 🕒 Linha do tempo das bases")
        _linha_do_tempo(bases, refs)
