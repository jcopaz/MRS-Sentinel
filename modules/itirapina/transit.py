# =============================================================================
# modules/itirapina/transit.py — Subaba 🚆 Transit time (ZPD ↔ ZIQ)
#
# Série contínua (sem base). Mediana e P90 mensais por sentido, boxplot por
# mês, linha do marco zero (mediana jan–set/2026) e do programado
# (SUPRIMIDO = horário previsto), aderência (≤ programado + 1 h) e trens
# acima de 24 h. Outliers (> 72 h) ficam fora e são informados.
# =============================================================================

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.parser_transit_time import resumo_mensal

CFG = {"displaylogo": False}
MARCO_ZERO = ("2026-01-01", "2026-10-01")


def render_transit(transit: pd.DataFrame) -> None:
    if transit is None or transit.empty:
        st.info("📭 Nenhum transit time carregado — envie as consultas do SRM na subaba **📤 Upload**.")
        return
    sentidos = sorted(transit["sentido"].dropna().unique())
    c1, c2 = st.columns([1, 3])
    sentido = c1.radio("Sentido", sentidos, key="tt_sentido", horizontal=False)
    t = transit[transit["sentido"] == sentido]
    v = t[t["valido"] & ~t["outlier"]].copy()
    n_out = int((t["valido"] & t["outlier"]).sum())
    v["mes"] = v["partida"].dt.to_period("M").astype(str)
    mz = v[(v["partida"] >= MARCO_ZERO[0]) & (v["partida"] < MARCO_ZERO[1])]
    prog = t.loc[t["estado"] == "SUPRIMIDO", "horas"].median()
    mensal = resumo_mensal(t)

    ult = mensal.iloc[-1] if len(mensal) else None
    k = st.columns(5)
    k[0].metric("Mediana marco zero (jan–set/26)", f"{mz['horas'].median():.1f} h" if len(mz) else "—")
    k[1].metric("P90 marco zero", f"{mz['horas'].quantile(0.9):.1f} h" if len(mz) else "—")
    k[2].metric("Programado", f"{prog:.1f} h" if pd.notna(prog) else "—")
    k[3].metric("Aderência (≤ prog. + 1 h)",
                f"{(mz['horas'] <= mz['horas_programadas'] + 1).mean() * 100:.0f}%" if len(mz) else "—")
    k[4].metric("Último mês", f"{ult['mediana']:.1f} h" if ult is not None else "—",
                f"{ult['mes']} · {int(ult['trens'])} trens" if ult is not None else None, delta_color="off")
    c2.caption(f"{len(v):,} trens válidos (encerrados, partida e chegada realizadas). ".replace(",", ".")
               + (f"{n_out} outlier(s) acima de 72 h excluído(s)." if n_out else ""))

    st.markdown("##### Mediana e P90 mensais")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mensal["mes"], y=mensal["mediana"], mode="lines+markers", name="Mediana",
                             line=dict(color="#1e3a5f", width=3)))
    fig.add_trace(go.Scatter(x=mensal["mes"], y=mensal["p90"], mode="lines+markers", name="P90",
                             line=dict(color="#dc2626", dash="dot")))
    if pd.notna(prog):
        fig.add_hline(y=prog, line=dict(color="#16a34a", dash="dash"),
                      annotation_text=f"programado {prog:.1f} h", annotation_position="bottom right")
    if len(mz):
        fig.add_hline(y=mz["horas"].median(), line=dict(color="#94a3b8", dash="dash"),
                      annotation_text=f"marco zero {mz['horas'].median():.1f} h", annotation_position="top left")
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=10, b=30), yaxis_title="horas",
                      plot_bgcolor="#fff", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True, config=CFG)

    st.markdown("##### Distribuição por mês")
    fig = go.Figure(go.Box(x=v["mes"], y=v["horas"], marker_color="#1e3a5f", boxpoints="outliers"))
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=30), yaxis_title="horas",
                      plot_bgcolor="#fff")
    st.plotly_chart(fig, use_container_width=True, config=CFG)

    st.markdown("##### Trens acima de 24 h")
    acima = t[t["valido"] & (t["horas"] > 24)].sort_values("horas", ascending=False)
    st.dataframe(acima[["trem", "partida", "chegada", "horas", "horas_programadas", "outlier"]]
                 .rename(columns={"trem": "Trem", "partida": "Partida", "chegada": "Chegada",
                                  "horas": "Horas", "horas_programadas": "Programado", "outlier": "> 72 h"}),
                 hide_index=True, use_container_width=True, height=300)
    st.caption("O realizado é cerca de 2× o tempo de marcha: a melhoria de via aparece primeiro no "
               "P90 e na velocidade praticada.")
