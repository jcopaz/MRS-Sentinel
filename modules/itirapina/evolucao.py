# =============================================================================
# modules/itirapina/evolucao.py — Subaba 📈 Evolução (base A × base B)
#
# Lê a foto gravada em trecho_indicadores; se a base ainda não tiver foto
# (upload antigo, indicadores não recalculados), calcula na hora a partir dos
# dados da base (core/indicadores_trecho.calcular) sem gravar.
# Cards ▲▼ pelo sentido bom de cada indicador (core/ui_evolucao).
# =============================================================================

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.indicadores_trecho import CATALOGO, CATALOGO_TRANSIT, calcular
from core.ui_evolucao import bloco_cards, fmt_valor
from database.queries_prospeccao import TabelaAusente
from database.queries_trecho import get_indicadores
from modules.itirapina.dados import carregar_base

KPIS_PRINCIPAIS = [
    "taxa_inserviveis_pct", "dormentes_inserviveis", "defeitos_ativos", "defeitos_por_km",
    "defeitos_classe_ate40", "defeitos_mais_1ano", "vagao_sem_restricao", "restricoes_a",
    "restricoes_via", "restricoes_antt", "vma_media", "v_media_praticada",
    "minutos_perdidos", "km_restrito", "juntas_problema", "trilho_fora_m",
]


def _rotulo_base(b) -> str:
    selo = " 🔒" if b.congelada else ""
    mz = " · marco zero" if b.marco_zero else ""
    return f"{pd.to_datetime(b.data_base):%d/%m/%Y}{mz}{selo}"


def foto_da_base(base_id: int, data_base, refs: dict) -> pd.DataFrame:
    try:
        f = get_indicadores((int(base_id),))
    except TabelaAusente:
        f = pd.DataFrame()
    except Exception:
        f = pd.DataFrame()
    if not f.empty:
        f["valor"] = pd.to_numeric(f["valor"], errors="coerce")
        return f
    dados = carregar_base(int(base_id))
    dados["pontos"] = refs.get("pontos")
    return calcular(dados, pd.to_datetime(data_base).date())


def _valores(foto: pd.DataFrame, escopo: str, chave: str | None = None) -> pd.Series:
    if foto is None or foto.empty:
        return pd.Series(dtype=float)
    f = foto[foto["escopo"] == escopo]
    if chave is not None:
        f = f[f["chave"] == chave]
        return f.set_index("indicador")["valor"]
    return f


def _tabela_ab(fa, fb, escopo, indicadores, nome_a, nome_b) -> pd.DataFrame:
    a = _valores(fa, escopo)
    b = _valores(fb, escopo)
    linhas = []
    chaves = list(dict.fromkeys(list(b.get("chave", [])) + list(a.get("chave", []))))
    for ch in chaves:
        lin = {"chave": ch}
        for ind, rot in indicadores:
            va = a[(a["chave"] == ch) & (a["indicador"] == ind)]["valor"] if len(a) else pd.Series(dtype=float)
            vb = b[(b["chave"] == ch) & (b["indicador"] == ind)]["valor"] if len(b) else pd.Series(dtype=float)
            va = va.iloc[0] if len(va) else None
            vb = vb.iloc[0] if len(vb) else None
            lin[f"{rot} · {nome_a}"] = va
            lin[f"{rot} · {nome_b}"] = vb
            lin[f"{rot} · Δ"] = (vb - va) if va is not None and vb is not None else None
        linhas.append(lin)
    return pd.DataFrame(linhas)


def render_evolucao(bases: pd.DataFrame, refs: dict) -> None:
    if bases is None or bases.empty:
        st.info("A Evolução usa as bases versionadas — rode "
                "`database/schema_itirapina.sql` e carregue o marco zero.")
        return
    bases = bases.sort_values("data_base").reset_index(drop=True)
    rotulos = {int(b.id): _rotulo_base(b) for b in bases.itertuples()}
    ids = list(rotulos)
    mz = bases[bases["marco_zero"].fillna(False)]
    padrao_a = int(mz.iloc[0]["id"]) if len(mz) else ids[0]
    c1, c2 = st.columns(2)
    id_a = c1.selectbox("Base A (referência)", ids, index=ids.index(padrao_a),
                        format_func=rotulos.get, key="evo_a")
    id_b = c2.selectbox("Base B (comparada)", ids, index=len(ids) - 1,
                        format_func=rotulos.get, key="evo_b")
    ba = bases[bases["id"] == id_a].iloc[0]
    bb = bases[bases["id"] == id_b].iloc[0]
    with st.spinner("Calculando indicadores das bases..."):
        fa = foto_da_base(id_a, ba["data_base"], refs)
        fb = fa if id_b == id_a else foto_da_base(id_b, bb["data_base"], refs)

    if len(bases) == 1 or id_a == id_b:
        st.info("Evolução aparece a partir da 2ª base — abaixo, os valores da base selecionada.")

    ta, tb = _valores(fa, "trecho", "TOTAL"), _valores(fb, "trecho", "TOTAL")
    itens = []
    for ind in KPIS_PRINCIPAIS:
        if ind not in tb.index and ind not in ta.index:
            continue
        rot, sentido, fmt = CATALOGO[ind]
        itens.append((rot, tb.get(ind), ta.get(ind) if id_a != id_b else None, sentido, fmt))
    for sentido_tt in ("ZPD→ZIQ", "ZIQ→ZPD"):
        sa, sb = _valores(fa, "transit", sentido_tt), _valores(fb, "transit", sentido_tt)
        for ind in ("mediana", "p90"):
            if ind in sb.index:
                rot, sentido, fmt = CATALOGO_TRANSIT[ind]
                itens.append((f"{rot} {sentido_tt}", sb.get(ind),
                              sa.get(ind) if id_a != id_b else None, sentido, fmt))
    st.markdown(f"##### 📊 {rotulos[id_b]} × {rotulos[id_a]}")
    st.caption("Seta = variação de B em relação a A. Verde = melhorou pelo sentido do indicador "
               "(menos defeitos/restrições/inservíveis/transit time; mais VMA e velocidade).")
    if itens:
        bloco_cards(itens, colunas=4)
    else:
        st.info("Sem indicadores para as bases escolhidas.")

    nome_a, nome_b = "A", "B"
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("##### Por SB")
        t = _tabela_ab(fa, fb, "sb", [("taxa_inserviveis_pct", "Inserv. %"),
                                      ("defeitos_por_km", "Def/km")], nome_a, nome_b)
        if not t.empty:
            km = _valores(fb, "sb")
            ordem = km[km["indicador"] == "km_ini"].set_index("chave")["valor"]
            t = t.assign(_o=t["chave"].map(ordem)).sort_values("_o").drop(columns="_o")
        st.dataframe(t.rename(columns={"chave": "SB"}), hide_index=True, use_container_width=True)
    with c4:
        st.markdown("##### Pontos críticos e Top 10")
        t = _tabela_ab(fa, fb, "ponto_critico", [("taxa_inserviveis_pct", "Inserv. %"),
                                                 ("defeitos_por_km", "Def/km"),
                                                 ("restricoes_a", "Restr.")], nome_a, nome_b)
        st.dataframe(t.rename(columns={"chave": "Ponto"}), hide_index=True, use_container_width=True)

    _linha_do_tempo(bases, fb, refs, rotulos)


def _linha_do_tempo(bases, fb, refs, rotulos) -> None:
    st.markdown("##### 🕒 Linha do tempo")
    mes = _valores(fb, "mes")
    c1, c2 = st.columns(2)
    with c1:
        if mes is None or mes.empty:
            st.info("Sem transit time carregado.")
        else:
            m = mes.copy()
            m[["mes", "sentido"]] = m["chave"].str.split("|", expand=True)
            fig = go.Figure()
            for (sentido, ind), g in m[m["indicador"].isin(["mediana", "p90"])].groupby(["sentido", "indicador"]):
                g = g.sort_values("mes")
                fig.add_trace(go.Scatter(x=pd.to_datetime(g["mes"] + "-01"), y=g["valor"], mode="lines+markers",
                                         name=f"{sentido} · {ind}",
                                         line=dict(dash="solid" if ind == "mediana" else "dot")))
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=30), yaxis_title="horas",
                              xaxis=dict(type="date", tickformat="%m/%Y"),
                              plot_bgcolor="#fff", legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
            st.caption("Transit time mensal (mediana e P90, trens válidos sem outlier).")
    with c2:
        pontos = []
        for b in bases.itertuples():
            try:
                f = fb if b.id == bases.iloc[-1]["id"] else foto_da_base(b.id, b.data_base, refs)
            except Exception:
                continue
            t = _valores(f, "trecho", "TOTAL")
            pontos.append({"base": rotulos[int(b.id)], "data": b.data_base,
                           "Defeitos ativos": t.get("defeitos_ativos"),
                           "Taxa inservíveis %": t.get("taxa_inserviveis_pct"),
                           "Restrições A": t.get("restricoes_a")})
        p = pd.DataFrame(pontos)
        if p.empty:
            st.info("Sem bases.")
            return
        if len(p) < 2:
            # 1 ponto só: o Plotly escala o eixo em milissegundos — cards no lugar
            st.caption(f"Base única ({p.iloc[0]['base']}) — a linha do tempo aparece a partir da 2ª base.")
            k = st.columns(3)
            for c, (col, fmt) in zip(k, (("Defeitos ativos", "int"), ("Taxa inservíveis %", "pct"),
                                         ("Restrições A", "int"))):
                v = p.iloc[0][col]
                c.metric(col, fmt_valor(v, fmt) if v is not None and pd.notna(v) else "—")
            return
        p["data"] = pd.to_datetime(p["data"])
        fig = go.Figure()
        for col, eixo in (("Defeitos ativos", "y"), ("Taxa inservíveis %", "y2"), ("Restrições A", "y2")):
            fig.add_trace(go.Scatter(x=p["data"], y=p[col], mode="lines+markers+text", name=col,
                                     yaxis=eixo, text=[fmt_valor(v, "int" if col != "Taxa inservíveis %" else "pct")
                                                       if v is not None else "" for v in p[col]],
                                     textposition="top center"))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=30), plot_bgcolor="#fff",
                          yaxis=dict(title="defeitos"), legend=dict(orientation="h", y=1.15),
                          xaxis=dict(type="date", tickformat="%m/%Y"),
                          yaxis2=dict(title="% / qtd", overlaying="y", side="right"))
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        st.caption("Um ponto por base (marco zero, base histórica 2025, cargas de 2027+).")
