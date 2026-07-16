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
# 7 blocos:
#   1. Painel de Prioridade  (KPIs + Pareto contagem × THP)
#   1B. Obras × Manutenção   (classificação via "Origem da Atividade")
#   2. Ranking de Reincidência por Ativo (TPLNR)
#   3. Unifilar EE           (ativo × posição seq. no trecho, cor=score, anel reincidência)
#   4. Backlog RCA / Gatilho (gatilho sem causa raiz)
#   5. Análise 6M            (Ishikawa consolidado)
#   6. Tendência mensal
#
# Filtros: Sistema, Origem Obras×Manutenção, Reincidência, Período (essenciais)
#   + Responsável, Ativo, Pátio, Tipo Solicitação, Origem Atividade, Grupo do
#   Ativo (expander "Mais filtros")
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

# Meses em português (idêntico ao padrão de components/heatmap.py e
# components/visao_gerencial.py) — todo gráfico com data usa isso, nunca
# formatação de data nativa do ECharts/navegador (que sai em inglês).
MESES_PT_ABREV = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
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
    Filtros da aba. Linha essencial sempre visível: Sistema, Categoria
    (Obras/Manutenção), Reincidência, Período. Os demais (Responsável,
    Ativo, Pátio, Tipo Solicitação, Origem da Atividade, Grupo do Ativo)
    ficam num expander pra não poluir o topo da tela.

    Aplicados sobre o df ANTES de _enriquecer() — assim o score_ee e todas as
    agregações dos 6 blocos já refletem só o recorte filtrado. Mesmo padrão
    defensivo de components/filtros.py: seleção vazia = sem filtro (volta a
    lista cheia), evita "aba em branco" por engano.
    """
    if df.empty:
        return df

    st.markdown("##### 🔍 Filtros")
    col_sist, col_cat, col_reinc, col_periodo = st.columns([1, 1, 1, 1.4])

    with col_sist:
        sistema_sel = _multiselect_coluna(df, "sistema", "Sistema", escopo)

    with col_cat:
        categoria_sel = _multiselect_coluna(
            df, "origem_categoria", "Origem: Obras × Manutenção", escopo,
            help="Derivado de 'Descrição da Origem da Atividade' — ver bloco "
                 "🏗️ Obras × Manutenção logo abaixo pra entender a classificação.",
        )

    with col_reinc:
        reincidencia_opt = st.radio(
            "Reincidência (90d, ativo)", ["Todas", "Só reincidentes", "Só não reincidentes"],
            index=0, key=f"ee_filtro_reincid_{escopo}",
            help="Usa o campo 'Reincidência 90 dias ativo' já pré-calculado pelo RASF.",
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

    with st.expander("🔎 Mais filtros — Responsável, Ativo, Pátio, Tipo, Origem, Grupo do Ativo"):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            resp_sel = _multiselect_coluna(df, "responsavel", "Responsável", escopo)
            tipo_sel = _multiselect_coluna(df, "desc_tipo_solicitacao", "Descrição Tipo Solicitação", escopo)
        with col_b:
            ativo_sel = _multiselect_coluna(
                df, "local_instalacao", "Ativo (TPLNR)", escopo,
                help="Local de Instalação — mesmo código usado no Ranking de Reincidência.",
            )
            origem_sel = _multiselect_coluna(df, "desc_origem_atividade", "Descrição da Origem da Atividade", escopo)
        with col_c:
            patio_sel = _multiselect_coluna(df, "local_patio", "Pátio", escopo)
            grupo_sel = _multiselect_coluna(df, "grupo_ativo", "Grupo do Ativo", escopo)

    d = df.copy()
    if sistema_sel is not None and "sistema" in d.columns:
        d = d[d["sistema"].isin(sistema_sel)]
    if categoria_sel is not None and "origem_categoria" in d.columns:
        d = d[d["origem_categoria"].isin(categoria_sel)]
    if "reincidencia_ativo" in d.columns:
        if reincidencia_opt == "Só reincidentes":
            d = d[d["reincidencia_ativo"]]
        elif reincidencia_opt == "Só não reincidentes":
            d = d[~d["reincidencia_ativo"]]
    if resp_sel is not None and "responsavel" in d.columns:
        d = d[d["responsavel"].isin(resp_sel)]
    if ativo_sel is not None and "local_instalacao" in d.columns:
        d = d[d["local_instalacao"].isin(ativo_sel)]
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


# region ====================== SESSÃO 3: BLOCO 1 — Painel de Prioridade ========

def _bloco_prioridade(df: pd.DataFrame, escopo: str = ""):
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


# region ====================== SESSÃO 3B: BLOCO 1B — Obras × Manutenção =======
# Pedido do Julio (16/07/2026): a malha está em obras de remodelação — falha
# originada de Obras pede estratégia de bloqueio diferente (comissionamento/
# padrão de entrega) de falha de Manutenção tradicional (RCA/plano). Achado
# nos dados reais: "Descrição da Origem da Atividade" já tem o valor
# "PROJETOS E OBRAS" isolado — não precisou inventar heurística nenhuma, só
# ler o que já existe (ver core.parser_rasf.classificar_origem_atividade).

_CORES_ORIGEM_CATEGORIA = {
    "Obras": "#7c3aed",
    "Manutenção": COR_PRIMARIA,
    "Não classificado": COR_WARN,
    "Não informado": "#9ca3af",
}


def _bloco_obras_manutencao(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 🏗️ Obras × Manutenção — como atacar")
    st.caption(
        "Classificação automática de 'Descrição da Origem da Atividade' "
        "(regra: contém \"OBRA\" → **Obras**, contém \"MANUTEN\" → "
        "**Manutenção**, resto → **Não classificado**). Falha de **Obras** "
        "geralmente pede bloqueio na frente de trabalho (padrão de "
        "comissionamento/entrega); falha de **Manutenção** pede RCA/plano "
        "de manutenção tradicional — duas estratégias diferentes. "
        "Categorização é ajustável sem deploy (`configuracoes`, chave "
        "`rasf_origem_categoria_overrides`) — expanda abaixo pra ver o "
        "detalhe e sugerir ajustes."
    )

    if "origem_categoria" not in df.columns:
        st.info("Coluna de origem da atividade indisponível.")
        return

    g = (
        df.groupby("origem_categoria")
          .agg(
              falhas=("origem_categoria", "size"),
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

    cols = st.columns(len(g))
    for col, (_, r) in zip(cols, g.iterrows()):
        cat = str(r["origem_categoria"])
        pct = 100 * r["falhas"] / total if total else 0
        _kpi(
            col, cat, f"{int(r['falhas']):,}".replace(",", "."),
            _CORES_ORIGEM_CATEGORIA.get(cat, COR_PRIMARIA),
            sub=f"{pct:.0f}% · {int(r['reincidencias'])} reincid. · {int(r['backlog'])} sem 6M",
        )

    if not ECHARTS_OK:
        st.dataframe(g, use_container_width=True, hide_index=True)
        return

    categorias = g["origem_categoria"].astype(str).tolist()
    falhas     = [int(v) for v in g["falhas"]]
    thp        = [round(float(v), 1) for v in g["thp_h"]]
    cores      = [_CORES_ORIGEM_CATEGORIA.get(c, COR_PRIMARIA) for c in categorias]

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
        "grid": {"left": "3%", "right": "6%", "top": "18%", "bottom": "10%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": categorias,
            "axisLabel": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
        },
        "yAxis": [
            {"type": "value", "name": "Falhas", "axisLabel": {"color": "#374151"},
             "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
            {"type": "value", "name": "THP (h)", "position": "right",
             "axisLabel": {"color": COR_THP}, "splitLine": {"show": False}},
        ],
        "series": [
            {"name": "Falhas", "type": "bar",
             "data": [{"value": v, "itemStyle": {"color": cores[i]}} for i, v in enumerate(falhas)],
             "label": {"show": True, "position": "top", "color": "#1f2937", "fontWeight": "bold"},
             "barWidth": "40%"},
            {"name": "THP (h)", "type": "line", "yAxisIndex": 1, "data": thp,
             "smooth": True, "lineStyle": {"color": COR_THP, "width": 3},
             "itemStyle": {"color": COR_THP}, "symbol": "circle", "symbolSize": 8},
        ],
    }
    st_echarts(opt, height="360px", key=f"ee_obras_manut_{escopo}")

    with st.expander("🔎 Ver quais valores de 'Origem da Atividade' caem em cada categoria"):
        tab = (
            df.groupby(["origem_categoria", "desc_origem_atividade"])
              .size().reset_index(name="qtd")
              .sort_values(["origem_categoria", "qtd"], ascending=[True, False])
        )
        st.dataframe(
            tab.rename(columns={
                "origem_categoria": "Categoria",
                "desc_origem_atividade": "Origem da Atividade (RASF)",
                "qtd": "Qtd falhas",
            }),
            use_container_width=True, hide_index=True,
        )

# endregion


# region ====================== SESSÃO 4: BLOCO 2 — Ranking Reincidência ========

def _bloco_reincidencia(df: pd.DataFrame, escopo: str = ""):
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
        top_n = st.selectbox("Top N", [10, 15, 20, 30], index=1, key=f"rank_reincid_n_{escopo}")
    with col_ord:
        ordem = st.selectbox(
            "Ordenar por",
            ["Reincidências (90d)", "Nº de falhas", "THP (h)"],
            index=0, key=f"rank_reincid_ord_{escopo}",
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

def _bloco_6m(df: pd.DataFrame, escopo: str = ""):
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

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        st.dataframe(g, use_container_width=True, hide_index=True)
        return

    categorias = g["m6_nivel1"].astype(str).tolist()
    valores    = [int(v) for v in g["qtd"]]

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA,
            "textStyle": {"color": "#1f2937"}, "formatter": "<b>{b}</b><br/>Falhas: <b>{c}</b>",
        },
        "grid": {"left": "3%", "right": "10%", "top": "5%", "bottom": "5%", "containLabel": True},
        "xAxis": {"type": "value", "name": "Nº de falhas", "axisLabel": {"color": "#374151"},
                  "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
        "yAxis": {
            "type": "category", "data": categorias,
            "axisLabel": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
        },
        "series": [{
            "type": "bar", "data": valores,
            "itemStyle": {"color": COR_PRIMARIA, "borderRadius": [0, 4, 4, 0]},
            "label": {"show": True, "position": "right", "color": "#1f2937",
                      "fontSize": 12, "fontWeight": "bold"},
            "barWidth": "55%",
        }],
    }
    altura = max(300, 40 * len(categorias) + 80)
    st_echarts(opt, height=f"{altura}px", key=f"ee_6m_{escopo}")

# endregion


# region ====================== SESSÃO 8: BLOCO 6 — Tendência YoY ===============

def _bloco_tendencia(df: pd.DataFrame, escopo: str = ""):
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

    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        st.dataframe(g, use_container_width=True, hide_index=True)
        return

    # Rótulos em PT-BR ("jan/25") — nunca formatação nativa (sai em inglês).
    rotulos = [f"{MESES_PT_ABREV[m.month]}/{str(m.year)[-2:]}" for m in g["mes"]]
    falhas  = [int(v) for v in g["falhas"]]
    thp     = [round(float(v), 1) for v in g["thp_h"]]

    opt = {
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA, "borderWidth": 2,
            "padding": [10, 14], "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            "axisPointer": {"type": "line", "lineStyle": {"color": COR_PRIMARIA, "type": "dashed"}},
        },
        "legend": {
            "data": ["Falhas", "THP (h)"], "top": 0,
            "textStyle": {"color": "#374151", "fontSize": 12, "fontWeight": "bold"},
        },
        "grid": {"left": "3%", "right": "6%", "top": "15%", "bottom": "18%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": rotulos,
            "axisLabel": {"color": "#374151", "fontSize": 11, "rotate": 35 if len(rotulos) > 10 else 0},
            "axisLine": {"lineStyle": {"color": "#9ca3af"}}, "boundaryGap": True,
        },
        "yAxis": [
            {"type": "value", "name": "Falhas", "axisLabel": {"color": "#374151"},
             "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
            {"type": "value", "name": "THP (h)", "position": "right",
             "axisLabel": {"color": COR_THP}, "splitLine": {"show": False}},
        ],
        "dataZoom": [
            {"type": "slider", "show": True, "bottom": 5, "height": 18,
             "borderColor": "#d1d5db", "fillerColor": "rgba(30,58,95,0.15)",
             "handleStyle": {"color": COR_PRIMARIA}},
            {"type": "inside"},
        ],
        "series": [
            {"name": "Falhas", "type": "bar", "data": falhas,
             "itemStyle": {"color": COR_PRIMARIA, "borderRadius": [3, 3, 0, 0]}},
            {"name": "THP (h)", "type": "line", "yAxisIndex": 1, "data": thp,
             "smooth": True, "lineStyle": {"color": COR_THP, "width": 3},
             "itemStyle": {"color": COR_THP}, "symbol": "circle", "symbolSize": 7},
        ],
    }
    st_echarts(opt, height="380px", key=f"ee_tendencia_{escopo}")

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

    rotulo = {"SP": "Gerência SP", "VP": "Gerência VP",
              "GLOBAL": "Visão Global (SP + VP)"}.get(escopo, escopo)
    st.markdown(
        f"<div style='color:#6b7280;font-size:0.85rem;margin-bottom:10px;'>"
        f"🔌 Inteligência de Falhas de Eletroeletrônica · <b>{rotulo}</b> · "
        f"base RASF (PG-ENG-0088)</div>",
        unsafe_allow_html=True,
    )

    # Filtros (Responsável, Ativo, Pátio, Período) — aplicados ANTES do
    # enriquecimento, pra score_ee e todas as agregações já refletirem o
    # recorte escolhido.
    df = _render_filtros(df, escopo)
    if df.empty:
        st.info("ℹ️ Nenhuma falha encontrada com os filtros aplicados.")
        return

    df = _enriquecer(df)
    st.markdown("---")

    _bloco_prioridade(df, escopo)
    st.markdown("---")
    _bloco_obras_manutencao(df, escopo)
    st.markdown("---")
    _bloco_reincidencia(df, escopo)
    st.markdown("---")
    _bloco_unifilar(df, escopo)
    st.markdown("---")
    _bloco_backlog(df)
    st.markdown("---")
    _bloco_6m(df, escopo)
    st.markdown("---")
    _bloco_tendencia(df, escopo)

# endregion
