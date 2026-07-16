# =============================================================================
# components/inteligencia_ee.py — Aba "Inteligência de Falhas EE"
# Sprint 6 — MRS Sentinel
#
# Recorte unifilar das falhas de Eletroeletrônica a partir do RASF, alinhado
# ao PG-ENG-0088 (metodologia RCA/RASF). Responde: onde atacar, qual ativo mais
# reincidente, quanto trem parou (THP) e onde a análise de causa raiz está em
# aberto (backlog do Gatilho).
#
# Entrada: DataFrame canônico produzido por core.parser_rasf / queries_rasf.
# Uso:     render_inteligencia_ee(df, escopo="SP"|"VP"|"GLOBAL")
#
# 6 blocos:
#   1. Painel de Prioridade  (KPIs + Pareto contagem × THP)
#   2. Ranking de Reincidência por Ativo (TPLNR)
#   3. Unifilar EE           (pátio × volume, cor=score, anel reincidência)
#   4. Backlog RCA / Gatilho (gatilho sem causa raiz)
#   5. Análise 6M            (Ishikawa consolidado)
#   6. Tendência YoY         (opcional — Base Congelada)
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

try:
    from streamlit_echarts import st_echarts, JsCode
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

try:
    from core.glossarios import decodificar_tplnr, nome_ramal
    GLOSS_OK = True
except Exception:
    GLOSS_OK = False

    def decodificar_tplnr(_):      # fallback defensivo
        return {}

    def nome_ramal(s, *a, **k):
        return s

COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_CRIT     = "#dc2626"
COR_OK       = "#16a34a"
COR_WARN     = "#f59e0b"
COR_CRONICO  = "#7c3aed"   # roxo — anel de ativo reincidente (mesma cor do Unifilar VP/EE,
                            # mas conceito diferente: aqui é reincidência de ativo 90d, não
                            # hot-spot ramal+pátio+família)
COR_THP      = "#0ea5e9"

RING_DELTA   = 12

# Peso de cada nível de "Tipo de falha" — usado no score de priorização EE.
_PESO_TIPO_FALHA = {
    "Crítica":       1.00,
    "Alto Impacto":  0.80,
    "Médio Impacto": 0.50,
    "Baixo Impacto": 0.25,
}
# endregion


# region ====================== SESSÃO 2: Preparação / enriquecimento ==========

@st.cache_data(ttl=300, show_spinner=False)
def _enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deriva ramal/pátio/subsistema a partir do TPLNR e calcula o score de
    priorização EE. Cacheado — o enriquecimento é puro em função do df.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Decodifica TPLNR -> ramal (trecho), pátio (origem), subsistema.
    if "local_instalacao" in df.columns:
        dec = df["local_instalacao"].apply(decodificar_tplnr)
        df["ramal"] = dec.apply(lambda d: (d or {}).get("trecho"))
        df["patio"] = dec.apply(lambda d: (d or {}).get("origem"))
        sub = dec.apply(lambda d: (d or {}).get("subsistema"))
        # Preferir 'Sistema' do RASF; cair para o subsistema do TPLNR.
        df["subsistema"] = df.get("sistema")
        df["subsistema"] = df["subsistema"].where(df["subsistema"].notna(), sub)

    # Pátio: usa local_patio do RASF quando o TPLNR não resolveu.
    if "local_patio" in df.columns:
        df["patio"] = df.get("patio").where(
            df.get("patio").notna() if "patio" in df.columns else False,
            df["local_patio"],
        ) if "patio" in df.columns else df["local_patio"]

    # THP em horas (mais legível que minutos nas telas).
    df["thp_h"] = pd.to_numeric(df.get("thp_min", 0), errors="coerce").fillna(0) / 60.0

    # Score de priorização EE (0-1): combina impacto, THP, reincidência,
    # confiabilidade e backlog de análise. Serve à cor do Unifilar e ao ranking.
    peso_tipo = df.get("tipo_falha", pd.Series(index=df.index, dtype=object)) \
        .map(_PESO_TIPO_FALHA).fillna(0.4)
    thp = df["thp_h"]
    thp_norm = (thp / thp.max()) if thp.max() and thp.max() > 0 else thp * 0
    reincid = df.get("reincidencia_ativo", False)
    reincid = reincid.astype(float) if hasattr(reincid, "astype") else 0.0
    confiab = df.get("impacta_confiabilidade", False)
    confiab = confiab.astype(float) if hasattr(confiab, "astype") else 0.0
    df["score_ee"] = (
        0.35 * peso_tipo
        + 0.30 * thp_norm
        + 0.20 * reincid
        + 0.15 * confiab
    ).clip(0, 1)

    return df


def _fmt_int(v) -> str:
    try:
        return f"{int(round(v)):,}".replace(",", ".")
    except Exception:
        return "0"


def _fmt_h(v) -> str:
    try:
        return f"{v:,.0f} h".replace(",", ".")
    except Exception:
        return "0 h"

# endregion


# region ====================== SESSÃO 3: BLOCO 1 — Painel de Prioridade ========

def _bloco_prioridade(df: pd.DataFrame):
    st.markdown("#### 🎯 Painel de Prioridade — onde atacar")

    total = len(df)
    thp_h = df["thp_h"].sum()
    reincid = int(df.get("reincidencia_ativo", pd.Series(dtype=bool)).sum())
    confiab = int(df.get("impacta_confiabilidade", pd.Series(dtype=bool)).sum())
    backlog = int(df.get("lacuna_rca", pd.Series(dtype=bool)).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    _kpi(c1, "Falhas EE", _fmt_int(total), COR_PRIMARIA)
    _kpi(c2, "Trem parado (THP)", _fmt_h(thp_h), COR_THP)
    _kpi(c3, "Reincid. 90d (ativo)",
         f"{_fmt_int(reincid)}",
         COR_CRIT, sub=f"{100*reincid/total:.0f}% do total" if total else "")
    _kpi(c4, "Impacta confiab.",
         f"{_fmt_int(confiab)}",
         COR_WARN, sub=f"{100*confiab/total:.0f}% do total" if total else "")
    _kpi(c5, "Backlog RCA", _fmt_int(backlog), COR_CRONICO,
         sub="gatilho sem causa raiz")

    st.markdown("---")
    st.markdown("##### 📊 Pareto de Sintomas — contagem × trem parado (THP)")
    st.caption(
        "O sintoma mais **frequente** nem sempre é o que mais **para trem**. "
        "As barras mostram volume; a linha, o THP acumulado (h)."
    )

    if "anomalia_sintoma" not in df.columns:
        st.info("Coluna de sintoma indisponível.")
        return

    g = (
        df.groupby("anomalia_sintoma")
          .agg(qtd=("anomalia_sintoma", "size"), thp_h=("thp_h", "sum"))
          .sort_values("qtd", ascending=False)
          .head(12)
          .reset_index()
    )
    if g.empty:
        st.info("Sem dados de sintoma no escopo atual.")
        return

    g["rotulo"] = g["anomalia_sintoma"].astype(str).str.slice(0, 42)

    fig = go.Figure()
    fig.add_bar(
        x=g["rotulo"], y=g["qtd"], name="Nº de falhas",
        marker_color=COR_PRIMARIA,
        hovertemplate="%{x}<br>Falhas: %{y}<extra></extra>",
    )
    fig.add_trace(go.Scatter(
        x=g["rotulo"], y=g["thp_h"], name="THP (h)",
        yaxis="y2", mode="lines+markers",
        line=dict(color=COR_THP, width=3),
        marker=dict(size=8, color=COR_THP),
        hovertemplate="%{x}<br>THP: %{y:.0f} h<extra></extra>",
    ))
    fig.update_layout(
        height=420, margin=dict(l=10, r=10, t=30, b=120),
        xaxis=dict(tickangle=-40),
        yaxis=dict(title="Nº de falhas"),
        yaxis2=dict(title="THP (h)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

# endregion


# region ====================== SESSÃO 4: BLOCO 2 — Ranking Reincidência ========

def _bloco_reincidencia(df: pd.DataFrame):
    st.markdown("#### ♻️ Ranking de Reincidência por Ativo")
    st.caption(
        "Ativos (TPLNR) que mais reincidem. A reincidência 90 dias vem do próprio "
        "RASF. Foque o topo: são os ativos que voltam a falhar."
    )

    if "local_instalacao" not in df.columns:
        st.info("Coluna de ativo (TPLNR) indisponível.")
        return

    col_n, col_ord = st.columns([1, 2])
    with col_n:
        top_n = st.selectbox("Top N", [10, 15, 20, 30], index=1, key="rank_reincid_n")
    with col_ord:
        ordem = st.selectbox(
            "Ordenar por",
            ["Reincidências (90d)", "Nº de falhas", "THP (h)"],
            index=0, key="rank_reincid_ord",
        )

    g = (
        df.groupby("local_instalacao")
          .agg(
              falhas=("local_instalacao", "size"),
              reincidencias=("reincidencia_ativo", "sum"),
              thp_h=("thp_h", "sum"),
              patio=("patio", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
              sistema=("sistema", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
              confiab=("impacta_confiabilidade", "sum"),
          )
          .reset_index()
    )
    g["reincidencias"] = g["reincidencias"].astype(int)
    g["confiab"] = g["confiab"].astype(int)

    col_ordem = {
        "Reincidências (90d)": "reincidencias",
        "Nº de falhas": "falhas",
        "THP (h)": "thp_h",
    }[ordem]
    g = g.sort_values(col_ordem, ascending=False).head(top_n)

    if g.empty:
        st.info("Sem dados de ativo no escopo atual.")
        return

    tabela = g.rename(columns={
        "local_instalacao": "Ativo (TPLNR)",
        "patio": "Pátio",
        "sistema": "Sistema",
        "falhas": "Falhas",
        "reincidencias": "Reincid. 90d",
        "thp_h": "THP (h)",
        "confiab": "Impacta confiab.",
    })
    tabela["THP (h)"] = tabela["THP (h)"].round(0).astype(int)

    st.dataframe(
        tabela[["Ativo (TPLNR)", "Pátio", "Sistema", "Falhas",
                "Reincid. 90d", "THP (h)", "Impacta confiab."]],
        use_container_width=True, hide_index=True,
        column_config={
            "Reincid. 90d": st.column_config.ProgressColumn(
                "Reincid. 90d", format="%d",
                min_value=0, max_value=int(g["reincidencias"].max() or 1),
            ),
        },
    )

# endregion


# region ====================== SESSÃO 5: BLOCO 3 — Unifilar EE =================

def _bloco_unifilar(df: pd.DataFrame):
    st.markdown("#### 🗺️ Unifilar EE — pátios da malha")
    st.caption(
        "Cada bolha é um pátio. Tamanho = volume de falhas · Cor = score de "
        "prioridade · 🟣 Anel roxo = pátio com **ativos reincidentes** "
        "(≥3 reincidências de 90 dias, ≥30% das falhas do pátio). "
        "⚠️ Conceito diferente do \"hot-spot crônico\" do Unifilar VP/EE "
        "(que é por ramal+pátio+família num período de 6 meses) — aqui é "
        "reincidência de ativo (TPLNR) em 90 dias, já pré-calculada pelo RASF."
    )

    if not ECHARTS_OK:
        st.info("Componente ECharts indisponível — exibindo ranking alternativo.")
        _unifilar_fallback(df)
        return

    if "patio" not in df.columns or df["patio"].dropna().empty:
        st.info("Não foi possível decodificar pátios do TPLNR neste escopo.")
        _unifilar_fallback(df)
        return

    g = (
        df.dropna(subset=["patio"])
          .groupby("patio")
          .agg(
              falhas=("patio", "size"),
              score=("score_ee", "mean"),
              reincidencias=("reincidencia_ativo", "sum"),
              thp_h=("thp_h", "sum"),
              ramal=("ramal", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
          )
          .reset_index()
          .sort_values("falhas", ascending=False)
          .head(30)
    )
    if g.empty:
        _unifilar_fallback(df)
        return

    g["reincidencias"] = g["reincidencias"].astype(int)
    # Crônico: pátio com reincidência relevante (>= 30% das falhas reincidem
    # e pelo menos 3 reincidências) — critério simples e transparente.
    g["cronico"] = (g["reincidencias"] >= 3) & \
                   (g["reincidencias"] >= 0.30 * g["falhas"])

    fmax = float(g["falhas"].max() or 1)

    def _bsize(n):
        return 18 + 42 * (n / fmax)

    pts, pts_cronico = [], []
    for _, r in g.iterrows():
        size = _bsize(r["falhas"])
        pts.append({
            "value": [str(r["patio"]), round(float(r["score"]), 3)],
            "symbolSize": size,
            "_falhas": int(r["falhas"]),
            "_reincid": int(r["reincidencias"]),
            "_thp": round(float(r["thp_h"]), 0),
            "_ramal": str(r["ramal"]),
        })
        if r["cronico"]:
            pts_cronico.append({
                "value": [str(r["patio"]), round(float(r["score"]), 3)],
                "symbolSize": size + RING_DELTA,
            })

    tooltip = JsCode("""
        function(p){
            var d = p.data || {};
            var badge = %s;
            return '<b>Pátio '+ (d.value ? d.value[0] : '') +'</b> '+badge+'<br/>'
                 + 'Ramal: '+ (d._ramal||'—') +'<br/>'
                 + 'Falhas: <b>'+ (d._falhas||0) +'</b><br/>'
                 + 'Reincidências: <b>'+ (d._reincid||0) +'</b><br/>'
                 + 'THP: <b>'+ (d._thp||0) +' h</b><br/>'
                 + 'Score: '+ (d.value ? d.value[1] : '');
        }
    """ % ("(d._reincid>=3 && d._reincid>=0.3*d._falhas)"
           " ? '<span style=\"color:#7c3aed\">♻️ ATIVOS REINCIDENTES</span>' : ''"))

    series = [
        {
            "name": "Pátios",
            "type": "scatter",
            "data": pts,
            "itemStyle": {"opacity": 0.85},
        },
        {  # pulso nos 20% de maior score
            "name": "Crítico",
            "type": "effectScatter",
            "rippleEffect": {"scale": 3, "brushType": "stroke"},
            "data": [p for p in pts if p["value"][1] >= _percentil_score(pts, 0.80)],
            "symbolSize": JsCode("function(v,p){return p.data.symbolSize;}"),
            "z": 3,
        },
    ]
    if pts_cronico:
        series.append({  # anel de ativo reincidente — camada decorativa, não rouba tooltip
            "name": "Reincidentes",
            "type": "scatter",
            "silent": True,
            "data": pts_cronico,
            "symbol": "circle",
            "itemStyle": {
                "color": "rgba(0,0,0,0)",
                "borderColor": COR_CRONICO,
                "borderWidth": 3,
                "shadowBlur": 6,
                "shadowColor": COR_CRONICO,
            },
            "z": 4,
        })

    option = {
        "tooltip": {"trigger": "item", "formatter": tooltip},
        "grid": {"left": 40, "right": 30, "top": 50, "bottom": 70},
        "xaxis": {"type": "category", "name": "Pátio",
                  "axisLabel": {"rotate": 40}},
        "yAxis": {"type": "value", "name": "Score", "max": 1},
        "visualMap": {
            "min": 0, "max": 1, "dimension": 1,
            "seriesIndex": [0, 1],
            "orient": "horizontal", "left": "center", "bottom": 0,
            "text": ["Crítico", "Normal"], "calculable": True,
            "inRange": {"color": [COR_OK, COR_WARN, COR_CRIT]},
        },
        "series": series,
    }
    # ECharts espera 'xAxis'/'yAxis' — corrige a chave.
    option["xAxis"] = option.pop("xaxis")
    st_echarts(options=option, height="460px")


def _percentil_score(pts, q):
    vals = sorted(p["value"][1] for p in pts)
    if not vals:
        return 1.0
    idx = int(q * (len(vals) - 1))
    return vals[idx]


def _unifilar_fallback(df: pd.DataFrame):
    col = "patio" if "patio" in df.columns else "local_patio"
    if col not in df.columns:
        return
    g = (df.dropna(subset=[col]).groupby(col)
           .agg(Falhas=(col, "size"),
                Reincidencias=("reincidencia_ativo", "sum"),
                THP_h=("thp_h", "sum"))
           .reset_index().sort_values("Falhas", ascending=False).head(20))
    g["Reincidencias"] = g["Reincidencias"].astype(int)
    g["THP_h"] = g["THP_h"].round(0).astype(int)
    st.dataframe(g.rename(columns={col: "Pátio", "THP_h": "THP (h)"}),
                 use_container_width=True, hide_index=True)

# endregion


# region ====================== SESSÃO 6: BLOCO 4 — Backlog RCA / Gatilho =======

def _bloco_backlog(df: pd.DataFrame):
    st.markdown("#### 🧭 Backlog de Classificação — Gatilhos sem 6M definido")
    st.caption(
        "Ocorrências que são **Gatilho de Análise** (PG-ENG-0088, §6.4.1) mas ainda "
        "não têm classificação 6M/Componente preenchida — é a fila de análise pendente. "
        "⚠️ Isso mede **classificação**, não **validação**: o procedimento ainda exige "
        "que o especialista da área valide a causa em até 5 dias úteis (fluxo formal, "
        "não rastreado neste export) — uma ocorrência pode estar aqui como \"coberta\" "
        "e ainda não ter passado por esse crivo."
    )

    if "lacuna_rca" not in df.columns:
        st.info("Campo de gatilho/causa raiz indisponível.")
        return

    gat = int(df.get("gatilho_analise", pd.Series(dtype=bool)).sum())
    back = int(df["lacuna_rca"].sum())
    feito = gat - back
    cobertura = (100 * feito / gat) if gat else 0

    c1, c2, c3 = st.columns(3)
    _kpi(c1, "Gatilhos de análise", _fmt_int(gat), COR_PRIMARIA)
    _kpi(c2, "Com 6M classificado", _fmt_int(feito), COR_OK,
         sub=f"{cobertura:.0f}% de cobertura")
    _kpi(c3, "Backlog (sem 6M)", _fmt_int(back), COR_CRONICO,
         sub="priorizar classificação")

    st.progress(min(cobertura / 100, 1.0),
                text=f"Cobertura de classificação 6M: {cobertura:.0f}%")

    bl = df[df["lacuna_rca"]].copy()
    if bl.empty:
        st.success("✅ Sem backlog: todos os gatilhos têm causa raiz. 🎉")
        return

    bl = bl.sort_values("thp_h", ascending=False)
    cols = [c for c in ["data_nota", "numero_nota", "local_patio",
                        "local_instalacao", "sistema", "anomalia_sintoma",
                        "gatilho_eng", "thp_h", "responsavel"] if c in bl.columns]
    tab = bl[cols].head(50).rename(columns={
        "data_nota": "Data", "numero_nota": "Nota", "local_patio": "Pátio",
        "local_instalacao": "Ativo (TPLNR)", "sistema": "Sistema",
        "anomalia_sintoma": "Sintoma", "gatilho_eng": "Gatilho",
        "thp_h": "THP (h)", "responsavel": "Responsável",
    })
    if "THP (h)" in tab.columns:
        tab["THP (h)"] = tab["THP (h)"].round(0).astype(int)
    if "Data" in tab.columns:
        tab["Data"] = pd.to_datetime(tab["Data"], errors="coerce").dt.strftime("%d/%m/%Y")
    st.dataframe(tab, use_container_width=True, hide_index=True)
    st.caption(f"Mostrando {min(len(bl),50)} de {len(bl)} pendências (ordenado por THP).")

# endregion


# region ====================== SESSÃO 7: BLOCO 5 — Análise 6M ==================

def _bloco_6m(df: pd.DataFrame):
    st.markdown("#### 🐟 Análise 6M — Ishikawa consolidado")
    st.caption(
        "Distribuição das causas raiz já classificadas (Eng > Manutenção). "
        "Responde: é gente, material, método ou máquina? — direciona o bloqueio."
    )

    if "m6_nivel1" not in df.columns:
        st.info("Campo 6M indisponível.")
        return

    classificados = df[df["m6_nivel1"].notna() & (df["m6_nivel1"].astype(str).str.strip() != "")]
    if classificados.empty:
        st.warning("Nenhuma falha com 6M classificado no escopo atual.")
        return

    total = len(df)
    cob = 100 * len(classificados) / total if total else 0
    st.markdown(
        f"<div style='color:#6b7280;font-size:0.85rem;margin-bottom:6px;'>"
        f"🔎 {len(classificados):,} de {total:,} falhas classificadas "
        f"({cob:.0f}%) — as demais aguardam análise.</div>".replace(",", "."),
        unsafe_allow_html=True,
    )

    g = (classificados.groupby("m6_nivel1")
         .agg(qtd=("m6_nivel1", "size"), thp_h=("thp_h", "sum"))
         .reset_index().sort_values("qtd", ascending=True))

    fig = go.Figure()
    fig.add_bar(
        y=g["m6_nivel1"], x=g["qtd"], orientation="h",
        marker_color=COR_PRIMARIA,
        text=g["qtd"], textposition="outside",
        hovertemplate="%{y}<br>Falhas: %{x}<extra></extra>",
    )
    fig.update_layout(
        height=380, margin=dict(l=10, r=30, t=20, b=20),
        xaxis_title="Nº de falhas", plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

# endregion


# region ====================== SESSÃO 8: BLOCO 6 — Tendência YoY ===============

def _bloco_tendencia(df: pd.DataFrame):
    st.markdown("#### 📈 Tendência mensal")
    st.caption("Evolução do volume de falhas e do THP ao longo do tempo.")

    if "data_nota" not in df.columns:
        st.info("Coluna de data indisponível.")
        return

    d = df.copy()
    d["data_nota"] = pd.to_datetime(d["data_nota"], errors="coerce")
    d = d.dropna(subset=["data_nota"])
    if d.empty:
        st.info("Sem datas válidas no escopo atual.")
        return

    d["mes"] = d["data_nota"].dt.to_period("M").dt.to_timestamp()
    g = (d.groupby("mes")
           .agg(falhas=("mes", "size"), thp_h=("thp_h", "sum"),
                reincid=("reincidencia_ativo", "sum"))
           .reset_index().sort_values("mes"))

    fig = go.Figure()
    fig.add_bar(x=g["mes"], y=g["falhas"], name="Falhas",
                marker_color=COR_PRIMARIA,
                hovertemplate="%{x|%b/%Y}<br>Falhas: %{y}<extra></extra>")
    fig.add_trace(go.Scatter(
        x=g["mes"], y=g["thp_h"], name="THP (h)", yaxis="y2",
        mode="lines+markers", line=dict(color=COR_THP, width=3),
        hovertemplate="%{x|%b/%Y}<br>THP: %{y:.0f} h<extra></extra>"))
    fig.update_layout(
        height=360, margin=dict(l=10, r=10, t=30, b=20),
        yaxis=dict(title="Falhas"),
        yaxis2=dict(title="THP (h)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

# endregion


# region ====================== SESSÃO 9: KPI helper ============================

def _kpi(col, label, valor, cor, sub=""):
    with col:
        st.markdown(
            f"""
            <div style="background:white;border:1px solid #e5e7eb;border-left:4px solid {cor};
                        border-radius:10px;padding:12px 14px;">
              <div style="font-size:0.72rem;color:#6b7280;text-transform:uppercase;
                          letter-spacing:.5px;font-weight:600;">{label}</div>
              <div style="font-size:1.5rem;font-weight:800;color:{cor};line-height:1.1;
                          margin-top:2px;">{valor}</div>
              <div style="font-size:0.72rem;color:#9ca3af;margin-top:2px;">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# endregion


# region ====================== SESSÃO 10: Entrada pública ======================

def render_inteligencia_ee(df: pd.DataFrame, escopo: str = "SP"):
    """
    Renderiza a aba de Inteligência de Falhas EE.

    Args:
        df:     DataFrame RASF canônico (já filtrado à gerência, se aplicável).
        escopo: "SP", "VP" ou "GLOBAL" — usado apenas para rótulos/contexto.
    """
    if df is None or df.empty:
        st.warning(
            "⚠️ Nenhum dado RASF disponível para este escopo. "
            "Solicite o upload do export RASF na tela de Alimentação de Dados.",
            icon="📋",
        )
        return

    df = _enriquecer(df)

    rotulo = {"SP": "Gerência SP", "VP": "Gerência VP",
              "GLOBAL": "Visão Global (SP + VP)"}.get(escopo, escopo)
    st.markdown(
        f"<div style='color:#6b7280;font-size:0.85rem;margin-bottom:10px;'>"
        f"🔌 Inteligência de Falhas de Eletroeletrônica · <b>{rotulo}</b> · "
        f"base RASF (PG-ENG-0088)</div>",
        unsafe_allow_html=True,
    )

    _bloco_prioridade(df)
    st.markdown("---")
    _bloco_reincidencia(df)
    st.markdown("---")
    _bloco_unifilar(df)
    st.markdown("---")
    _bloco_backlog(df)
    st.markdown("---")
    _bloco_6m(df)
    st.markdown("---")
    _bloco_tendencia(df)

# endregion
