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
# 4 blocos (recorte pedido pelo Julio — 16/07/2026):
#   1. Unifilar EE           (ativo × posição seq. no trecho, cor=score, anel
#                             reincidência, tamanho=qtd de falhas)
#   2. Pareto de Sintomas    (contagem × THP)
#   3. Obras × Manutenção    (qtd de falhas / THP por "Descrição da Origem da
#                             Atividade" RASF, sem agrupar em categoria)
#   4. Ranking de Reincidência por Ativo (agrupado pela coluna K do RASF —
#                             "Local de instalação", não o código TPLNR)
#
# Filtros (essenciais): Sistema, Reincidência, Gerador THP (coluna Z do
#   RASF — marcada com "X"), Período (Data da nota), Descrição Tipo
#   Solicitação, Descrição da Origem da Atividade, Pátio, Grupo do Ativo.
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

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


# region ====================== SESSÃO 2B: Filtros ==============================

def _multiselect_coluna(df: pd.DataFrame, coluna: str, label: str, escopo: str, **kwargs) -> list | None:
    """
    Helper: multiselect padrão sobre uma coluna de texto do df.

    Retorna None quando o filtro está no estado "sem filtro" (seleção vazia
    OU igual à lista cheia de opções) — o chamador NÃO deve aplicar isin()
    nesse caso. Isso é importante porque a lista de opções vem de
    dropna().unique(): se aplicássemos isin() mesmo com "tudo selecionado",
    linhas com o campo em branco seriam excluídas por padrão (ex.:
    'responsavel' está vazio em 60% das falhas do RASF) — com 6+ filtros
    desse tipo empilhados, o efeito composto derruba o total mesmo sem o
    usuário tocar em nada. Só filtra de verdade quando o usuário restringe
    ativamente a seleção.
    """
    opcoes = sorted(
        v for v in df.get(coluna, pd.Series(dtype=object)).dropna().unique()
        if str(v).strip()
    )
    sel = st.multiselect(label, opcoes, default=opcoes, key=f"ee_filtro_{coluna}_{escopo}", **kwargs)
    if not sel or set(sel) == set(opcoes):
        return None
    return sel


def _render_filtros(df: pd.DataFrame, escopo: str) -> pd.DataFrame:
    """
    Filtros da aba — recorte pedido pelo Julio (16/07/2026): Sistema,
    Reincidência, Gerador THP, Período sempre visíveis; Descrição Tipo
    Solicitação, Descrição da Origem da Atividade, Pátio e Grupo do Ativo
    num expander pra não poluir o topo da tela.

    Aplicados sobre o df ANTES de _enriquecer() — assim o score_ee e todas as
    agregações dos blocos já refletem só o recorte filtrado. Mesmo padrão
    defensivo de components/filtros.py: seleção vazia = sem filtro (volta a
    lista cheia), evita "aba em branco" por engano.
    """
    if df.empty:
        return df

    st.markdown("##### 🔍 Filtros")
    col_sist, col_reinc, col_thp, col_periodo = st.columns([1, 1, 1, 1.4])

    with col_sist:
        sistema_sel = _multiselect_coluna(df, "sistema", "Sistema", escopo)

    with col_reinc:
        reincidencia_opt = st.radio(
            "Reincidência (90d, ativo)", ["Todas", "Só reincidentes", "Só não reincidentes"],
            index=0, key=f"ee_filtro_reincid_{escopo}",
            help="Usa o campo 'Reincidência 90 dias ativo' já pré-calculado pelo RASF.",
        )

    with col_thp:
        gerador_thp_opt = st.radio(
            "Gerador THP (300)", ["Todas", "Só com THP", "Só sem THP"],
            index=0, key=f"ee_filtro_thp_{escopo}",
            help="Coluna Z do RASF ('Gerador THP (300)') — sinalizada com "
                 "'X' nas notas que geraram trem parado.",
        )

    with col_periodo:
        data_max = date.today()  # SEMPRE hoje — nunca derivar dos dados
        datas_validas = pd.to_datetime(df.get("data_nota"), errors="coerce").dropna()
        data_min_disp = datas_validas.min().date() if not datas_validas.empty else date(2018, 1, 1)
        periodo = st.date_input(
            "Período (data da nota)",
            value=(data_min_disp, data_max),
            min_value=date(2018, 1, 1),
            max_value=data_max,
            format="DD/MM/YYYY",
            key=f"ee_filtro_periodo_{escopo}",
        )

    with st.expander("🔎 Mais filtros — Tipo Solicitação, Origem da Atividade, Pátio, Grupo do Ativo"):
        col_a, col_b = st.columns(2)
        with col_a:
            tipo_sel = _multiselect_coluna(df, "desc_tipo_solicitacao", "Descrição Tipo Solicitação", escopo)
            origem_sel = _multiselect_coluna(df, "desc_origem_atividade", "Descrição da Origem da Atividade", escopo)
        with col_b:
            patio_sel = _multiselect_coluna(df, "local_patio", "Pátio", escopo)
            grupo_sel = _multiselect_coluna(df, "grupo_ativo", "Grupo do Ativo", escopo)

    d = df.copy()
    if sistema_sel is not None and "sistema" in d.columns:
        d = d[d["sistema"].isin(sistema_sel)]
    if "reincidencia_ativo" in d.columns:
        if reincidencia_opt == "Só reincidentes":
            d = d[d["reincidencia_ativo"]]
        elif reincidencia_opt == "Só não reincidentes":
            d = d[~d["reincidencia_ativo"]]
    if "gerador_thp" in d.columns:
        if gerador_thp_opt == "Só com THP":
            d = d[d["gerador_thp"]]
        elif gerador_thp_opt == "Só sem THP":
            d = d[~d["gerador_thp"]]
    if patio_sel is not None and "local_patio" in d.columns:
        d = d[d["local_patio"].isin(patio_sel)]
    if tipo_sel is not None and "desc_tipo_solicitacao" in d.columns:
        d = d[d["desc_tipo_solicitacao"].isin(tipo_sel)]
    if origem_sel is not None and "desc_origem_atividade" in d.columns:
        d = d[d["desc_origem_atividade"].isin(origem_sel)]
    if grupo_sel is not None and "grupo_ativo" in d.columns:
        d = d[d["grupo_ativo"].isin(grupo_sel)]
    if "data_nota" in d.columns and isinstance(periodo, (tuple, list)) and len(periodo) == 2:
        col_data = pd.to_datetime(d["data_nota"], errors="coerce")
        d = d[(col_data.dt.date >= periodo[0]) & (col_data.dt.date <= periodo[1])]

    return d

# endregion


# region ====================== SESSÃO 3: BLOCO 2 — Pareto de Sintomas x THP ====

def _bloco_pareto_sintomas(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 📊 Pareto de Sintomas × THP")
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

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        st.dataframe(g[["anomalia_sintoma", "qtd", "thp_h"]], use_container_width=True, hide_index=True)
        return

    labels = g["rotulo"].tolist()
    qtd    = [int(v) for v in g["qtd"]]
    thp    = [round(float(v), 1) for v in g["thp_h"]]

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA, "borderWidth": 2,
            "padding": [10, 14], "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
            "textStyle": {"color": "#1f2937", "fontSize": 12},
        },
        "legend": {
            "data": ["Nº de falhas", "THP (h)"], "top": 0,
            "textStyle": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
        },
        "grid": {"left": "3%", "right": "6%", "top": "15%", "bottom": "24%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": labels,
            "axisLabel": {"color": "#374151", "fontSize": 10, "rotate": 40, "interval": 0},
            "axisLine": {"lineStyle": {"color": "#9ca3af"}},
        },
        "yAxis": [
            {"type": "value", "name": "Nº de falhas", "axisLabel": {"color": "#374151"},
             "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
            {"type": "value", "name": "THP (h)", "position": "right",
             "axisLabel": {"color": COR_THP}, "splitLine": {"show": False}},
        ],
        "series": [
            {"name": "Nº de falhas", "type": "bar", "data": qtd,
             "itemStyle": {"color": COR_PRIMARIA, "borderRadius": [3, 3, 0, 0]}, "barWidth": "55%"},
            {"name": "THP (h)", "type": "line", "yAxisIndex": 1, "data": thp,
             "smooth": True, "lineStyle": {"color": COR_THP, "width": 3},
             "itemStyle": {"color": COR_THP}, "symbol": "circle", "symbolSize": 8},
        ],
    }
    st_echarts(opt, height="420px", key=f"ee_pareto_{escopo}")

# endregion


# region ====================== SESSÃO 4: BLOCO 3 — Obras × Manutenção =========
# Pedido do Julio (16/07/2026): a malha está em obras de remodelação — falha
# originada de Obras pede estratégia de bloqueio diferente (comissionamento/
# padrão de entrega) de falha de Manutenção tradicional (RCA/plano). Em vez
# de agrupar num rótulo Obras/Manutenção derivado, o bloco mostra a
# quantidade de falhas e o THP por cada valor bruto de "Descrição da Origem
# da Atividade" (RASF) — dá pra ver exatamente qual origem pesa mais, sem a
# perda de granularidade da categorização (ajuste 16/07/2026).

_TOP_ORIGENS_ATIVIDADE = 15


def _bloco_obras_manutencao(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 🏗️ Obras × Manutenção — como atacar")
    st.caption(
        "Quantidade de falhas e THP por 'Descrição da Origem da Atividade' "
        "(RASF) — cada origem pede uma estratégia diferente: falha originada "
        "de obra costuma pedir bloqueio na frente de trabalho (padrão de "
        "comissionamento/entrega); falha de manutenção tradicional pede "
        "RCA/plano de manutenção."
    )

    if "desc_origem_atividade" not in df.columns:
        st.info("Coluna de origem da atividade indisponível.")
        return

    g = (
        df.groupby("desc_origem_atividade")
          .agg(
              falhas=("desc_origem_atividade", "size"),
              thp_h=("thp_h", "sum"),
              reincidencias=("reincidencia_ativo", "sum"),
              backlog=("lacuna_rca", "sum"),
          )
          .reset_index()
          .sort_values("falhas", ascending=False)
    )
    if g.empty:
        st.info("Sem dados de origem no escopo atual.")
        return

    total = int(g["falhas"].sum())
    top1 = g.iloc[0]
    pct_top1 = 100 * top1["falhas"] / total if total else 0

    c1, c2, c3 = st.columns(3)
    _kpi(c1, "Falhas no recorte", _fmt_int(total), COR_PRIMARIA)
    _kpi(c2, "Trem parado (THP)", _fmt_h(g["thp_h"].sum()), COR_THP)
    _kpi(c3, "Origem principal", str(top1["desc_origem_atividade"])[:28],
         COR_CRIT, sub=f"{_fmt_int(top1['falhas'])} falhas · {pct_top1:.0f}% do total")

    g_chart = g.head(_TOP_ORIGENS_ATIVIDADE)

    if not ECHARTS_OK:
        st.dataframe(g, use_container_width=True, hide_index=True)
        return

    rotulos = g_chart["desc_origem_atividade"].astype(str).str.slice(0, 32).tolist()
    falhas  = [int(v) for v in g_chart["falhas"]]
    thp     = [round(float(v), 1) for v in g_chart["thp_h"]]

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA,
            "textStyle": {"color": "#1f2937"},
        },
        "legend": {
            "data": ["Falhas", "THP (h)"], "top": 0,
            "textStyle": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
        },
        "grid": {"left": "3%", "right": "6%", "top": "15%", "bottom": "26%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": rotulos,
            "axisLabel": {"color": "#374151", "fontSize": 10, "rotate": 40, "interval": 0},
            "axisLine": {"lineStyle": {"color": "#9ca3af"}},
        },
        "yAxis": [
            {"type": "value", "name": "Falhas", "axisLabel": {"color": "#374151"},
             "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
            {"type": "value", "name": "THP (h)", "position": "right",
             "axisLabel": {"color": COR_THP}, "splitLine": {"show": False}},
        ],
        "series": [
            {"name": "Falhas", "type": "bar", "data": falhas,
             "itemStyle": {"color": COR_PRIMARIA, "borderRadius": [3, 3, 0, 0]}, "barWidth": "55%"},
            {"name": "THP (h)", "type": "line", "yAxisIndex": 1, "data": thp,
             "smooth": True, "lineStyle": {"color": COR_THP, "width": 3},
             "itemStyle": {"color": COR_THP}, "symbol": "circle", "symbolSize": 8},
        ],
    }
    st_echarts(opt, height="420px", key=f"ee_obras_manut_{escopo}")

    with st.expander("🔎 Ver tabela completa por Origem da Atividade"):
        tab = g.rename(columns={
            "desc_origem_atividade": "Origem da Atividade (RASF)",
            "falhas": "Falhas",
            "thp_h": "THP (h)",
            "reincidencias": "Reincid. 90d",
            "backlog": "Backlog RCA",
        })
        tab["THP (h)"] = tab["THP (h)"].round(0).astype(int)
        st.dataframe(tab, use_container_width=True, hide_index=True)

# endregion


# region ====================== SESSÃO 5: BLOCO 4 — Ranking Reincidência ========

def _bloco_reincidencia(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### ♻️ Ranking de Reincidência por Ativo")
    st.caption(
        "Ativos (coluna K do RASF — 'Local de instalação') que mais "
        "reincidem. A reincidência 90 dias vem do próprio RASF. Foque o "
        "topo: são os ativos que voltam a falhar."
    )

    # Coluna K do export RASF ("Local de instalação") — descrição do ativo,
    # não o código TPLNR (coluna J). Pedido do Julio (16/07/2026): o ranking
    # deve agrupar por essa coluna, não pelo código.
    col_ativo = "local_instalacao_desc" if "local_instalacao_desc" in df.columns else "local_instalacao"
    if col_ativo not in df.columns:
        st.info("Coluna de ativo (Local de instalação) indisponível.")
        return

    col_n, col_ord = st.columns([1, 2])
    with col_n:
        top_n = st.selectbox("Top N", [10, 15, 20, 30], index=1, key=f"rank_reincid_n_{escopo}")
    with col_ord:
        ordem = st.selectbox(
            "Ordenar por",
            ["Reincidências (90d)", "Nº de falhas", "THP (h)"],
            index=0, key=f"rank_reincid_ord_{escopo}",
        )

    g = (
        df.groupby(col_ativo)
          .agg(
              falhas=(col_ativo, "size"),
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
        col_ativo: "Local de Instalação",
        "patio": "Pátio",
        "sistema": "Sistema",
        "falhas": "Falhas",
        "reincidencias": "Reincid. 90d",
        "thp_h": "THP (h)",
        "confiab": "Impacta confiab.",
    })
    tabela["THP (h)"] = tabela["THP (h)"].round(0).astype(int)

    st.dataframe(
        tabela[["Local de Instalação", "Pátio", "Sistema", "Falhas",
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


# region ====================== SESSÃO 6: BLOCO 1 — Unifilar EE =================

def _top_sintomas(x, k: int = 5):
    """Lista até k sintomas mais comuns — mesmo padrão de _top5_defeitos do
    Unifilar VP/EE (components/unifilar.py)."""
    vc = x.dropna().value_counts().head(k)
    if len(vc) == 0:
        return "—"
    return "<br/>".join(
        f"&nbsp;&nbsp;• {s} <span style='color:#9ca3af;'>({n})</span>"
        for s, n in vc.items()
    )


def _bloco_unifilar(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 🗺️ Unifilar EE — ativos por trecho")
    st.caption(
        "Mesmo estilo visual do Unifilar VP/EE (bolhas, pulso, zoom). "
        "⚠️ O eixo horizontal é **posição sequencial dos ativos dentro do "
        "trecho** (ordenados por pátio → TPLNR) — não é KM real, o RASF não "
        "traz medição de distância. Tamanho = volume de falhas · Cor = score "
        "de prioridade · 🟣 Anel roxo = ativo **reincidente** (≥3 "
        "reincidências de 90 dias — conceito diferente do hot-spot crônico "
        "do Unifilar VP/EE, que é por ramal+pátio+família em 6 meses)."
    )

    if not ECHARTS_OK:
        st.info("Componente ECharts indisponível — exibindo ranking alternativo.")
        _unifilar_fallback(df)
        return

    if ("ramal" not in df.columns or df["ramal"].dropna().empty
            or "local_instalacao" not in df.columns or df["local_instalacao"].dropna().empty):
        st.info("Não foi possível decodificar ramal/ativo do TPLNR neste escopo.")
        _unifilar_fallback(df)
        return

    df_u = df.dropna(subset=["ramal", "local_instalacao"]).copy()
    ramais_disp = sorted(df_u["ramal"].unique())

    if len(ramais_disp) == 1:
        ramal_view = ramais_disp[0]
        st.markdown(
            f"<div style='padding:8px 12px;background:{COR_PRIMARIA};color:#fff;"
            f"border-radius:8px;text-align:center;margin-bottom:10px;'>"
            f"🚂 Visualizando: <b>{nome_ramal(ramal_view, 'completo')}</b></div>",
            unsafe_allow_html=True,
        )
    else:
        opcoes_label = [
            f"{nome_ramal(r, 'completo')} ({len(df_u[df_u['ramal'] == r]):,})".replace(",", ".")
            for r in ramais_disp
        ]
        escolha = st.radio(
            "🚂 Trecho:", opcoes_label, horizontal=True, key=f"ee_unif_ramal_{escopo}",
            help="Cada trecho tem sua própria escala de posição sequencial.",
        )
        ramal_view = ramais_disp[opcoes_label.index(escolha)]

    d = df_u[df_u["ramal"] == ramal_view].copy()

    # Posição sequencial por ativo, ordenada por pátio → TPLNR (mesmo espírito
    # de _criar_km_sequencial() do Unifilar VP/EE, só que granularidade por
    # ativo em vez de pátio, já que a análise aqui é por TPLNR).
    ordem_ativos = (
        d.sort_values(["patio", "local_instalacao"])["local_instalacao"]
         .drop_duplicates().tolist()
    )
    pos_map = {a: i for i, a in enumerate(ordem_ativos)}
    d["posicao"] = d["local_instalacao"].map(pos_map)

    g = (
        d.groupby("local_instalacao")
         .agg(
             posicao=("posicao", "first"),
             patio=("patio", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
             sistema=("sistema", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
             falhas=("local_instalacao", "size"),
             score=("score_ee", "mean"),
             reincidencias=("reincidencia_ativo", "sum"),
             thp_h=("thp_h", "sum"),
             sintomas=("anomalia_sintoma", _top_sintomas),
             responsavel=("responsavel", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
         )
         .reset_index()
         .sort_values("posicao")
    )
    if g.empty:
        _unifilar_fallback(df)
        return

    g["reincidencias"] = g["reincidencias"].astype(int)
    g["cronico"] = g["reincidencias"] >= 3  # já é por ativo — sinal direto do RASF

    fmax = float(g["falhas"].max() or 1)

    def _bsize(n):
        return 14 + 36 * (n / fmax)

    pts, pts_cronico = [], []
    for _, r in g.iterrows():
        size = _bsize(r["falhas"])
        pts.append({
            "value": [float(r["posicao"]), round(float(r["score"]), 3)],
            "symbolSize": size,
            "_ativo": str(r["local_instalacao"]),
            "_patio": str(r["patio"]),
            "_sistema": str(r["sistema"]),
            "_falhas": int(r["falhas"]),
            "_reincid": int(r["reincidencias"]),
            "_thp": round(float(r["thp_h"]), 0),
            "_sintomas": r["sintomas"],
            "_resp": str(r["responsavel"]),
        })
        if r["cronico"]:
            pts_cronico.append({
                "value": [float(r["posicao"]), round(float(r["score"]), 3)],
                "symbolSize": size + RING_DELTA,
            })

    tooltip = JsCode("""
        function(p){
            var d = p.data || {};
            var badge = (d._reincid>=3)
                ? '<span style="color:#7c3aed">♻️ REINCIDENTE</span>' : '';
            return '<div style="min-width:230px;">'
                 + '<b>'+ (d._ativo||'') +'</b> '+ badge +'<br/>'
                 + 'Pátio: <b>'+ (d._patio||'—') +'</b> · Sistema: <b>'+ (d._sistema||'—') +'</b><br/>'
                 + 'Falhas: <b>'+ (d._falhas||0) +'</b> · THP: <b>'+ (d._thp||0) +' h</b><br/>'
                 + 'Reincidências (90d): <b>'+ (d._reincid||0) +'</b><br/>'
                 + 'Responsável: '+ (d._resp||'—') +'<br/>'
                 + '<div style="margin-top:6px;font-size:12px;color:#6b7280;"><b>Sintomas:</b></div>'
                 + '<div style="font-size:12px;">'+ (d._sintomas||'—') +'</div>'
                 + '</div>';
        }
    """)

    series = [
        {
            "name": "Ativos", "type": "scatter", "data": pts,
            "itemStyle": {"opacity": 0.85, "borderColor": "#fff", "borderWidth": 1.5},
        },
        {  # pulso nos 10% de maior score — fiel ao Unifilar VP/EE
            "name": "Crítico", "type": "effectScatter",
            "rippleEffect": {"period": 3, "scale": 2.8, "brushType": "stroke"},
            "showEffectOn": "render",
            "data": [p for p in pts if p["value"][1] >= _percentil_score(pts, 0.90)],
            "symbolSize": JsCode("function(v,p){return p.data.symbolSize;}"),
            "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
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
        "tooltip": {
            "trigger": "item",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": COR_PRIMARIA, "borderWidth": 2, "padding": [10, 14],
            "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;max-width:320px;",
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            "formatter": tooltip,
        },
        "grid": {"left": 50, "right": 90, "top": 20, "bottom": 75, "containLabel": True},
        "xAxis": {
            "type": "value", "name": "Posição sequencial no trecho (não é KM real)",
            "nameLocation": "middle", "nameGap": 32,
            "nameTextStyle": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
            "axisLine": {"lineStyle": {"color": "#9ca3af"}},
            "axisLabel": {"color": "#374151", "fontSize": 11},
            "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}},
        },
        "yAxis": {"type": "value", "name": "Score", "min": 0, "max": 1, "show": False},
        "visualMap": {
            "min": 0, "max": 1, "dimension": 1,
            "seriesIndex": [0, 1],
            "orient": "horizontal", "left": "center", "bottom": 0,
            "text": ["Crítico", "Normal"], "calculable": True,
            "textStyle": {"color": "#1f2937", "fontSize": 11},
            "inRange": {"color": [COR_OK, COR_WARN, COR_CRIT]},
        },
        "dataZoom": [
            {"type": "slider", "show": True, "xAxisIndex": [0], "bottom": 40, "height": 20,
             "borderColor": "#d1d5db", "fillerColor": "rgba(30,58,95,0.15)",
             "handleStyle": {"color": COR_PRIMARIA}},
            {"type": "inside", "xAxisIndex": [0]},
        ],
        "series": series,
    }
    st_echarts(options=option, height="460px", key=f"ee_unifilar_{escopo}_{ramal_view}")

    c1, c2, c3 = st.columns(3)
    c1.metric("🚂 Ativos no trecho", f"{len(g):,}".replace(",", "."))
    densidade = len(d) / max(len(g), 1)
    c2.metric("📊 Densidade", f"{densidade:.1f} falhas/ativo")
    top_ativo = str(g.sort_values("score", ascending=False).iloc[0]["local_instalacao"]) if len(g) else "—"
    c3.metric("🎯 Ativo mais crítico", top_ativo)


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


# region ====================== SESSÃO 7: KPI helper ============================

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


# region ====================== SESSÃO 8: Entrada pública ======================

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

    rotulo = {"SP": "Gerência SP", "VP": "Gerência VP",
              "GLOBAL": "Visão Global (SP + VP)"}.get(escopo, escopo)
    st.markdown(
        f"<div style='color:#6b7280;font-size:0.85rem;margin-bottom:10px;'>"
        f"🔌 Inteligência de Falhas de Eletroeletrônica · <b>{rotulo}</b> · "
        f"base RASF (PG-ENG-0088)</div>",
        unsafe_allow_html=True,
    )

    # Filtros (Sistema, Reincidência, Período + expander) — aplicados ANTES
    # do enriquecimento, pra score_ee e todas as agregações já refletirem o
    # recorte escolhido.
    df = _render_filtros(df, escopo)
    if df.empty:
        st.info("ℹ️ Nenhuma falha encontrada com os filtros aplicados.")
        return

    df = _enriquecer(df)
    st.markdown("---")

    _bloco_unifilar(df, escopo)
    st.markdown("---")
    _bloco_pareto_sintomas(df, escopo)
    st.markdown("---")
    _bloco_obras_manutencao(df, escopo)
    st.markdown("---")
    _bloco_reincidencia(df, escopo)

# endregion
