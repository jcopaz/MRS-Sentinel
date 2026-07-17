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
# Blocos (recorte pedido pelo Julio — 16/07/2026, cards+heatmap em 16/07/2026):
#   -1. Exportar Relatório   (HTML autônomo do recorte filtrado — ver
#                             components/relatorio_ee.py)
#   0. Cards Resumo          (ativo c/ mais falhas, ativo c/ maior THP, ativo
#                             mais reincidente, sintoma mais crítico por THP,
#                             origem de atividade mais frequente)
#   1. Unifilar EE           (ativo × posição seq. no trecho, cor=score, anel
#                             reincidência, tamanho=qtd de falhas)
#   2. Pareto de Sintomas    (contagem × THP, barras com % de representatividade)
#   3. Obras × Manutenção    (qtd de falhas / THP por "Descrição da Origem da
#                             Atividade" RASF, sem agrupar em categoria; barras
#                             com % de representatividade)
#   3B. Heatmap Pátio×Origem  (Pátio × Descrição da Origem da Atividade ×
#                             quantidade de falhas)
#   4. Ranking de Reincidência por Ativo (agrupado pela coluna K do RASF —
#                             "Local de instalação", não o código TPLNR)
#
# Filtros (essenciais): Sistema, Reincidência, Gerador THP (coluna Z do
#   RASF — marcada com "X"), Período (Data da nota), Descrição Tipo
#   Solicitação, Origem da Atividade (efetiva), Consenso Origem de
#   Atividade, Pátio, Grupo do Ativo.
#
# Regra de causa raiz/responsabilidade (Julio, 16/07/2026): "Descrição da
# Origem da Atividade" é a referência, MAS "Origem de Atividade Correta"
# sobrepõe quando preenchida em reunião com valor diferente (responsabilidade
# corrigida). Ver core.parser_rasf.origem_efetiva() e _preparar_origem()
# abaixo — toda classificação/ranking/heatmap por origem usa o resultado
# disso ('origem_efetiva'), nunca a coluna bruta.
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
from datetime import date
import json

import numpy as np
import pandas as pd
import streamlit as st

try:
    from streamlit_echarts import st_echarts, JsCode
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

try:
    from core.glossarios import decodificar_tplnr, nome_ramal, ativo_curto
    GLOSS_OK = True
except Exception:
    GLOSS_OK = False

    def decodificar_tplnr(_):      # fallback defensivo
        return {}

    def nome_ramal(s, *a, **k):
        return s

    def ativo_curto(s):
        return str(s or "")

try:
    from core.parser_rasf import origem_efetiva as _calc_origem_efetiva, status_consenso_origem
    PARSER_OK = True
except Exception:
    PARSER_OK = False

    def _calc_origem_efetiva(desc_origem, correta):  # fallback defensivo
        return desc_origem

    def status_consenso_origem(_):
        return "Pendente"

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


def _trunc_palavra(s, limite: int = 40) -> str:
    """Trunca preservando palavras inteiras (nunca corta no meio de uma
    palavra, ex.: 'CIRCUITO DE VIA COM O' virando algo sem sentido) e
    sinaliza com '…' quando corta de verdade. Usado em texto livre do RASF
    (sintoma, origem da atividade) que vai para cards/rótulos."""
    s = str(s)
    if len(s) <= limite:
        return s
    cortado = s[:limite].rsplit(" ", 1)[0]
    return (cortado or s[:limite]) + "…"


def _preparar_origem(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica a regra de causa raiz/responsabilidade do RASF (Julio, 16/07/2026):
    'Descrição da Origem da Atividade' é a referência, mas 'Origem de
    Atividade Correta' sobrepõe quando foi preenchida em reunião com valor
    diferente (responsabilidade corrigida). Resultado vai em 'origem_efetiva'
    — TODA classificação/ranking/heatmap por origem deve usar essa coluna,
    não a bruta.

    Roda ANTES de _render_filtros() (sessão 2B) — o filtro de origem já
    precisa dessa coluna calculada. Recalcula sempre client-side (em vez de
    só confiar na coluna já persistida pelo parser) pra funcionar mesmo com
    bases antigas, subidas antes desta regra existir.

    Também deriva 'consenso_origem_status' (Sim/Não/Pendente) a partir do
    bruto 'consenso_origem', com fallback 'Pendente' se a coluna não existir
    (base antiga).
    """
    if df.empty:
        return df
    d = df.copy()

    if "origem_atividade_correta" in d.columns and "desc_origem_atividade" in d.columns:
        d["origem_efetiva"] = [
            _calc_origem_efetiva(p, c)
            for p, c in zip(d["desc_origem_atividade"], d["origem_atividade_correta"])
        ]
    else:
        d["origem_efetiva"] = d.get("desc_origem_atividade")

    if "consenso_origem" in d.columns:
        d["consenso_origem_status"] = d["consenso_origem"].apply(status_consenso_origem)
    elif "consenso_origem_status" in d.columns:
        d["consenso_origem_status"] = d["consenso_origem_status"].fillna("Pendente")
    else:
        d["consenso_origem_status"] = "Pendente"

    return d

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
    Filtros da aba — recorte pedido pelo Julio (16/07/2026), todos dentro de
    um único expander recolhível pra não poluir o topo da tela: Sistema,
    Reincidência, Gerador THP, Período, Descrição Tipo Solicitação, Origem
    da Atividade (efetiva — já com a correção de responsabilidade aplicada),
    Consenso, Pátio e Grupo do Ativo.

    Recebe o df já passado por _preparar_origem() (chamada no início de
    render_inteligencia_ee) — precisa das colunas 'origem_efetiva' e
    'consenso_origem_status' calculadas ANTES de filtrar.

    Aplicados sobre o df ANTES de _enriquecer() — assim o score_ee e todas as
    agregações dos blocos já refletem só o recorte filtrado. Mesmo padrão
    defensivo de components/filtros.py: seleção vazia = sem filtro (volta a
    lista cheia), evita "aba em branco" por engano.
    """
    if df.empty:
        return df

    with st.expander("🔍 Filtros", expanded=False):
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

        st.markdown("---")
        col_a, col_b = st.columns(2)
        with col_a:
            tipo_sel = _multiselect_coluna(df, "desc_tipo_solicitacao", "Descrição Tipo Solicitação", escopo)
            origem_sel = _multiselect_coluna(
                df, "origem_efetiva", "Origem da Atividade (efetiva)", escopo,
                help="Já com a correção aplicada: usa 'Origem de Atividade Correta' "
                     "quando ela diverge de 'Descrição da Origem da Atividade' — "
                     "é a referência de causa raiz/responsabilidade após a reunião do RASF.",
            )
            consenso_sel = _multiselect_coluna(
                df, "consenso_origem_status", "Consenso Origem de Atividade", escopo,
                help="Sim = processo encerrado · Não = pode caber revisão · "
                     "Pendente = campo em branco (reunião ainda não decidiu).",
            )
        with col_b:
            centro_sel = _multiselect_coluna(
                df, "centro_trab", "Coordenação (Centro de Trabalho)", escopo,
                help="Filtra por centro de coordenação regional (ex.: CIPA, CIPG, "
                     "CIJN, CFAN...) — escolha aqui primeiro pra encurtar a lista "
                     "de Pátio logo abaixo.",
            )
            # Cascata: as opções de Pátio já vêm restritas à Coordenação
            # escolhida acima — mesmo padrão de components/filtros.py
            # (Centro de Trabalho → Ramal).
            df_para_patio = (
                df[df["centro_trab"].isin(centro_sel)]
                if centro_sel is not None and "centro_trab" in df.columns
                else df
            )
            patio_sel = _multiselect_coluna(df_para_patio, "local_patio", "Pátio", escopo)
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
    if centro_sel is not None and "centro_trab" in d.columns:
        d = d[d["centro_trab"].isin(centro_sel)]
    if patio_sel is not None and "local_patio" in d.columns:
        d = d[d["local_patio"].isin(patio_sel)]
    if tipo_sel is not None and "desc_tipo_solicitacao" in d.columns:
        d = d[d["desc_tipo_solicitacao"].isin(tipo_sel)]
    if origem_sel is not None and "origem_efetiva" in d.columns:
        d = d[d["origem_efetiva"].isin(origem_sel)]
    if consenso_sel is not None and "consenso_origem_status" in d.columns:
        d = d[d["consenso_origem_status"].isin(consenso_sel)]
    if grupo_sel is not None and "grupo_ativo" in d.columns:
        d = d[d["grupo_ativo"].isin(grupo_sel)]
    if "data_nota" in d.columns and isinstance(periodo, (tuple, list)) and len(periodo) == 2:
        col_data = pd.to_datetime(d["data_nota"], errors="coerce")
        d = d[(col_data.dt.date >= periodo[0]) & (col_data.dt.date <= periodo[1])]

    return d

# endregion


# region ====================== SESSÃO 2C: BLOCO 0 — Cards Resumo ==============

def _bloco_cards_resumo(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 📌 Resumo Executivo")
    st.caption(
        "Panorama rápido do recorte filtrado — pra achar de cara qual ativo "
        "mais falha, qual mais para trem, qual sintoma mais crítico e qual "
        "origem de atividade predomina."
    )

    if df.empty or "local_instalacao" not in df.columns:
        st.info("Sem dados suficientes pra montar o resumo.")
        return

    col_ativo = "local_instalacao"
    c1, c2, c3, c4, c5 = st.columns(5)

    # 1) Ativo com mais falhas + tipo de falha predominante nele
    grp_falhas = df.groupby(col_ativo).size()
    if not grp_falhas.empty:
        ativo_top = grp_falhas.idxmax()
        falhas_top = int(grp_falhas.max())
        sub_df = df[df[col_ativo] == ativo_top]
        tipo_moda = (
            sub_df["tipo_falha"].dropna().mode()
            if "tipo_falha" in sub_df.columns else pd.Series(dtype=object)
        )
        tipo_txt = str(tipo_moda.iloc[0]) if not tipo_moda.empty else "—"
        _kpi(c1, "Ativo com mais falhas", ativo_curto(ativo_top), COR_PRIMARIA,
             sub=f"{_fmt_int(falhas_top)} falhas · tipo mais comum: {tipo_txt}")
    else:
        _kpi(c1, "Ativo com mais falhas", "—", COR_PRIMARIA)

    # 2) Ativo com maior THP
    grp_thp = df.groupby(col_ativo)["thp_h"].sum()
    if not grp_thp.empty and grp_thp.max() > 0:
        ativo_thp_top = grp_thp.idxmax()
        thp_top = float(grp_thp.max())
        falhas_desse = int(grp_falhas.get(ativo_thp_top, 0))
        _kpi(c2, "Ativo com maior THP", ativo_curto(ativo_thp_top), COR_THP,
             sub=f"{_fmt_h(thp_top)} · {_fmt_int(falhas_desse)} falhas")
    else:
        _kpi(c2, "Ativo com maior THP", "—", COR_THP)

    # 3) Ativo mais reincidente
    if "reincidencia_ativo" in df.columns:
        grp_reincid = df.groupby(col_ativo)["reincidencia_ativo"].sum()
        if not grp_reincid.empty and grp_reincid.max() > 0:
            ativo_reincid_top = grp_reincid.idxmax()
            reincid_top = int(grp_reincid.max())
            _kpi(c3, "Ativo mais reincidente", ativo_curto(ativo_reincid_top), COR_CRONICO,
                 sub=f"{_fmt_int(reincid_top)} reincidências (90d)")
        else:
            _kpi(c3, "Ativo mais reincidente", "—", COR_CRONICO)
    else:
        _kpi(c3, "Ativo mais reincidente", "—", COR_CRONICO)

    # 4) Sintoma mais crítico por THP (complementa o Pareto, que ordena por contagem)
    if "anomalia_sintoma" in df.columns:
        grp_sint_thp = df.groupby("anomalia_sintoma")["thp_h"].sum()
        if not grp_sint_thp.empty and grp_sint_thp.max() > 0:
            sintoma_top = grp_sint_thp.idxmax()
            thp_sint_top = float(grp_sint_thp.max())
            _kpi(c4, "Sintoma mais crítico (THP)", _trunc_palavra(sintoma_top), COR_CRIT,
                 sub=f"{_fmt_h(thp_sint_top)} de trem parado")
        else:
            _kpi(c4, "Sintoma mais crítico (THP)", "—", COR_CRIT)
    else:
        _kpi(c4, "Sintoma mais crítico (THP)", "—", COR_CRIT)

    # 5) Origem de atividade mais frequente (efetiva — já com a correção de
    # responsabilidade aplicada, ver _preparar_origem)
    if "origem_efetiva" in df.columns:
        grp_origem = df["origem_efetiva"].value_counts()
        if not grp_origem.empty:
            origem_top = grp_origem.idxmax()
            qtd_origem_top = int(grp_origem.max())
            pct_origem = 100 * qtd_origem_top / len(df) if len(df) else 0
            _kpi(c5, "Origem mais frequente", _trunc_palavra(origem_top), COR_WARN,
                 sub=f"{_fmt_int(qtd_origem_top)} falhas · {pct_origem:.0f}% do total")
        else:
            _kpi(c5, "Origem mais frequente", "—", COR_WARN)
    else:
        _kpi(c5, "Origem mais frequente", "—", COR_WARN)

# endregion


# region ====================== SESSÃO 3: BLOCO 2 — Pareto de Sintomas x THP ====

def _bloco_pareto_sintomas(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 📊 Pareto de Sintomas — Falhas × THP por Sintoma")

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
    total_falhas = len(df) or 1  # denominador do % — total do escopo filtrado, não só o top 12

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
             "itemStyle": {"color": COR_PRIMARIA, "borderRadius": [3, 3, 0, 0]}, "barWidth": "55%",
             "label": {
                 "show": True, "position": "top", "color": "#1f2937",
                 "fontSize": 10, "fontWeight": "bold",
                 "formatter": JsCode(
                     f"function(p){{return p.value + ' (' + (p.value/{total_falhas}*100).toFixed(0) + '%)';}}"
                 ),
             }},
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
    st.markdown("#### 🏗️ Obras × Manutenção — Falhas × THP por Origem da Atividade")

    if "origem_efetiva" not in df.columns:
        st.info("Coluna de origem da atividade indisponível.")
        return

    g = (
        df.groupby("origem_efetiva")
          .agg(
              falhas=("origem_efetiva", "size"),
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
    _kpi(c3, "Origem principal", _trunc_palavra(top1["origem_efetiva"]),
         COR_CRIT, sub=f"{_fmt_int(top1['falhas'])} falhas · {pct_top1:.0f}% do total")

    g_chart = g.head(_TOP_ORIGENS_ATIVIDADE)

    if not ECHARTS_OK:
        st.dataframe(g, use_container_width=True, hide_index=True)
        return

    rotulos = g_chart["origem_efetiva"].astype(str).str.slice(0, 32).tolist()
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
             "itemStyle": {"color": COR_PRIMARIA, "borderRadius": [3, 3, 0, 0]}, "barWidth": "55%",
             "label": {
                 "show": True, "position": "top", "color": "#1f2937",
                 "fontSize": 10, "fontWeight": "bold",
                 "formatter": JsCode(
                     f"function(p){{return p.value + ' (' + (p.value/{total or 1}*100).toFixed(0) + '%)';}}"
                 ),
             }},
            {"name": "THP (h)", "type": "line", "yAxisIndex": 1, "data": thp,
             "smooth": True, "lineStyle": {"color": COR_THP, "width": 3},
             "itemStyle": {"color": COR_THP}, "symbol": "circle", "symbolSize": 8},
        ],
    }
    st_echarts(opt, height="420px", key=f"ee_obras_manut_{escopo}")

    with st.expander("🔎 Ver tabela completa por Origem da Atividade"):
        tab = g.rename(columns={
            "origem_efetiva": "Origem da Atividade (efetiva)",
            "falhas": "Falhas",
            "thp_h": "THP (h)",
            "reincidencias": "Reincid. 90d",
            "backlog": "Backlog RCA",
        })
        tab["THP (h)"] = tab["THP (h)"].round(0).astype(int)
        st.dataframe(tab, use_container_width=True, hide_index=True)

# endregion


# region ====================== SESSÃO 4B: Heatmap Pátio × Origem ==============

_TOP_ORIGENS_HEATMAP = 12  # linhas do heatmap (eixo Y) — evita poluir com origens raras


def _bloco_heatmap_patio_origem(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 🔥 Mapa de Calor — Pátio × Origem da Atividade (qtd de falhas)")

    if "patio" not in df.columns or "origem_efetiva" not in df.columns:
        st.info("Colunas de pátio/origem da atividade indisponíveis.")
        return

    d = df.dropna(subset=["patio", "origem_efetiva"]).copy()
    if d.empty:
        st.info("Sem dados de pátio/origem no escopo atual.")
        return

    patios = sorted(d["patio"].unique())
    top_origens = d["origem_efetiva"].value_counts().head(_TOP_ORIGENS_HEATMAP).index.tolist()
    d = d[d["origem_efetiva"].isin(top_origens)]
    if d.empty:
        st.info("Sem dados suficientes pra montar o mapa de calor.")
        return

    pivot = (
        d.groupby(["patio", "origem_efetiva"])
         .size().reset_index(name="falhas")
    )

    patio_labels = [str(p) for p in patios]
    origem_labels = [_trunc_palavra(o, 32) for o in top_origens]
    patio_idx = {p: i for i, p in enumerate(patios)}
    origem_idx = {o: i for i, o in enumerate(top_origens)}

    dados_heatmap = [
        [patio_idx[row["patio"]], origem_idx[row["origem_efetiva"]], int(row["falhas"])]
        for _, row in pivot.iterrows()
    ]
    max_val = max((v[2] for v in dados_heatmap), default=1)

    if not ECHARTS_OK:
        st.dataframe(
            pivot.rename(columns={
                "patio": "Pátio", "origem_efetiva": "Origem da Atividade (efetiva)", "falhas": "Falhas",
            }),
            use_container_width=True, hide_index=True,
        )
        return

    tooltip_fmt = JsCode(f"""
        function(p){{
            var patios = {json.dumps(patio_labels, ensure_ascii=False)};
            var origens = {json.dumps(origem_labels, ensure_ascii=False)};
            return '<b>'+ patios[p.value[0]] +'</b><br/>'
                 + origens[p.value[1]] +'<br/>'
                 + 'Falhas: <b>'+ p.value[2] +'</b>';
        }}
    """)

    opt = {
        "tooltip": {
            "position": "top",
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA, "borderWidth": 2,
            "padding": [10, 14], "extraCssText": "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            "formatter": tooltip_fmt,
        },
        "grid": {"left": "3%", "right": "4%", "top": "5%", "bottom": "26%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": patio_labels,
            "axisLabel": {"color": "#374151", "fontSize": 10, "rotate": 40, "interval": 0},
            "splitArea": {"show": True},
        },
        "yAxis": {
            "type": "category", "data": origem_labels,
            "axisLabel": {"color": "#374151", "fontSize": 10},
            "splitArea": {"show": True},
        },
        "visualMap": {
            "min": 0, "max": max_val, "calculable": True, "orient": "horizontal",
            "left": "center", "bottom": 0,
            "inRange": {"color": ["#eef2ff", COR_PRIMARIA, COR_CRIT]},
            "textStyle": {"color": "#1f2937"},
        },
        "series": [{
            "type": "heatmap", "data": dados_heatmap,
            "label": {"show": True, "color": "#1f2937", "fontSize": 10},
            "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,0.3)"}},
        }],
    }
    altura = max(360, 34 * len(origem_labels) + 160)
    st_echarts(opt, height=f"{altura}px", key=f"ee_heatmap_patio_origem_{escopo}")

# endregion


# region ====================== SESSÃO 5: BLOCO 4 — Ranking Reincidência ========

def _bloco_reincidencia(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### ♻️ Ranking de Reincidência por Ativo")
    st.caption(
        "Ativos que mais reincidem, identificados pelo TPLNR (chave única do "
        "RASF) e rotulados com a coluna K ('Local de instalação'). A "
        "reincidência 90 dias vem do próprio RASF. Foque o topo: são os "
        "ativos que voltam a falhar."
    )

    # ⚠️ Agrupa por TPLNR (local_instalacao), não pela coluna K
    # (local_instalacao_desc) — a coluna K é só um rótulo textual e NÃO é
    # garantidamente única por ativo físico (dois TPLNR diferentes podem
    # compartilhar a mesma descrição). Agrupar direto pela coluna K juntava
    # ativos diferentes num só total, inflando falhas/reincidências e
    # divergindo do Unifilar (que já usa TPLNR corretamente). A coluna K
    # continua exibida — só não é mais a CHAVE de agrupamento.
    if "local_instalacao" not in df.columns:
        st.info("Coluna de ativo (TPLNR) indisponível.")
        return
    tem_desc = "local_instalacao_desc" in df.columns

    col_n, col_ord = st.columns([1, 2])
    with col_n:
        top_n = st.selectbox("Top N", [10, 15, 20, 30], index=1, key=f"rank_reincid_n_{escopo}")
    with col_ord:
        ordem = st.selectbox(
            "Ordenar por",
            ["Reincidências (90d)", "Nº de falhas", "THP (h)"],
            index=0, key=f"rank_reincid_ord_{escopo}",
        )

    agg_kwargs = dict(
        falhas=("local_instalacao", "size"),
        reincidencias=("reincidencia_ativo", "sum"),
        thp_h=("thp_h", "sum"),
        patio=("patio", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
        sistema=("sistema", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
        confiab=("impacta_confiabilidade", "sum"),
        classificacao=(
            "origem_efetiva",
            lambda s: s.dropna().mode().iloc[0] if not s.dropna().mode().empty else "—",
        ),
    )
    if tem_desc:
        agg_kwargs["local_desc"] = (
            "local_instalacao_desc",
            lambda s: s.dropna().iloc[0] if s.notna().any() else "—",
        )

    g = df.groupby("local_instalacao").agg(**agg_kwargs).reset_index()
    if not tem_desc:
        g["local_desc"] = g["local_instalacao"]

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
        "local_desc": "Local de Instalação",
        "patio": "Pátio",
        "sistema": "Sistema",
        "falhas": "Falhas",
        "reincidencias": "Reincid. 90d",
        "thp_h": "THP (h)",
        "confiab": "Impacta confiab.",
        "classificacao": "Classificação",
    })
    tabela["THP (h)"] = tabela["THP (h)"].round(0).astype(int)

    st.dataframe(
        tabela[["Local de Instalação", "Pátio", "Sistema", "Classificação", "Falhas",
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

def _resumo_sintomas(sub: pd.DataFrame, k: int = 5) -> str:
    """Lista até k sintomas mais comuns do grupo, com contagem e a data da
    última ocorrência de CADA sintoma (não a última do ativo em geral) —
    mesmo padrão de _top5_defeitos do Unifilar VP/EE (components/unifilar.py),
    acrescido da data pra saber se aquele sintoma específico está "quente"."""
    if "anomalia_sintoma" not in sub.columns:
        return "—"
    s = sub.dropna(subset=["anomalia_sintoma"])
    if s.empty:
        return "—"
    contagem = s["anomalia_sintoma"].value_counts().head(k)
    linhas = []
    for sintoma, n in contagem.items():
        datas = pd.to_datetime(s.loc[s["anomalia_sintoma"] == sintoma, "data_nota"], errors="coerce").dropna()
        ultima = datas.max().strftime("%d/%m/%Y") if not datas.empty else "—"
        linhas.append(
            f"&nbsp;&nbsp;• {sintoma} "
            f"<span style='color:#9ca3af;'>({n} · últ. {ultima})</span>"
        )
    return "<br/>".join(linhas)


_GAP_TRECHOS = 3  # espaço (em posições) entre um trecho e o próximo no modo "Todos"
_OPCAO_TODOS = "🌐 Todos os trechos (visão geral)"


def _bloco_unifilar(df: pd.DataFrame, escopo: str = ""):
    st.markdown("#### 🗺️ Unifilar EE — ativos por trecho")
    st.caption(
        "⚠️ Eixo X = posição sequencial no trecho (não é KM real) · "
        "Tamanho = qtd de falhas · Cor = score de prioridade · "
        "🟣 Anel roxo = ativo reincidente (≥3 em 90d). "
        f"Selecione **\"{_OPCAO_TODOS}\"** pra ver a malha inteira de uma vez."
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

    modo_todos = False
    ramal_view = ramais_disp[0] if ramais_disp else None

    if len(ramais_disp) == 1:
        st.markdown(
            f"<div style='padding:8px 12px;background:{COR_PRIMARIA};color:#fff;"
            f"border-radius:8px;text-align:center;margin-bottom:10px;'>"
            f"🚂 Visualizando: <b>{nome_ramal(ramal_view, 'completo')}</b></div>",
            unsafe_allow_html=True,
        )
    else:
        opcoes_label = [_OPCAO_TODOS] + [
            f"{nome_ramal(r, 'completo')} ({len(df_u[df_u['ramal'] == r]):,})".replace(",", ".")
            for r in ramais_disp
        ]
        escolha = st.radio(
            "🚂 Trecho:", opcoes_label, horizontal=True, key=f"ee_unif_ramal_{escopo}",
            help="\"Todos os trechos\" concatena tudo num único gráfico — "
                 "ótimo pra comparar criticidade entre trechos.",
        )
        if escolha == _OPCAO_TODOS:
            modo_todos = True
        else:
            ramal_view = ramais_disp[opcoes_label.index(escolha) - 1]

    # Posição sequencial por ativo, ordenada por pátio → TPLNR (mesmo espírito
    # de _criar_km_sequencial() do Unifilar VP/EE, só que granularidade por
    # ativo em vez de pátio, já que a análise aqui é por TPLNR).
    # No modo "Todos", cada trecho ganha sua própria faixa de posições,
    # separadas por um espaço fixo (_GAP_TRECHOS) — mantém a leitura de
    # "sequência dentro do trecho" e ainda permite comparar tudo de uma vez.
    fronteiras = []
    if modo_todos:
        d = df_u.copy()
        pos_map = {}
        offset = 0
        for r in ramais_disp:
            sub = d[d["ramal"] == r]
            ordem = (
                sub.sort_values(["patio", "local_instalacao"])["local_instalacao"]
                   .drop_duplicates().tolist()
            )
            if not ordem:
                continue
            for i, a in enumerate(ordem):
                pos_map[(r, a)] = offset + i
            fronteiras.append({
                "ramal": r, "inicio": offset, "fim": offset + len(ordem) - 1,
                "label": nome_ramal(r, "completo"),
            })
            offset += len(ordem) + _GAP_TRECHOS
        d["posicao"] = [pos_map.get((rr, aa)) for rr, aa in zip(d["ramal"], d["local_instalacao"])]
        d = d.dropna(subset=["posicao"])
    else:
        d = df_u[df_u["ramal"] == ramal_view].copy()
        ordem_ativos = (
            d.sort_values(["patio", "local_instalacao"])["local_instalacao"]
             .drop_duplicates().tolist()
        )
        pos_map = {a: i for i, a in enumerate(ordem_ativos)}
        d["posicao"] = d["local_instalacao"].map(pos_map)

    g = (
        d.groupby(["ramal", "local_instalacao"])
         .agg(
             posicao=("posicao", "first"),
             patio=("patio", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
             sistema=("sistema", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
             falhas=("local_instalacao", "size"),
             score=("score_ee", "mean"),
             reincidencias=("reincidencia_ativo", "sum"),
             thp_h=("thp_h", "sum"),
         )
         .reset_index()
         .sort_values("posicao")
    )
    if g.empty:
        _unifilar_fallback(df)
        return

    # Sintomas + última data de cada um — precisa de duas colunas (sintoma e
    # data), por isso não dá pra fazer via .agg() de coluna única acima.
    sintomas_por_ativo = (
        d.groupby(["ramal", "local_instalacao"])
         .apply(_resumo_sintomas, include_groups=False)
         .rename("sintomas")
         .reset_index()
    )
    g = g.merge(sintomas_por_ativo, on=["ramal", "local_instalacao"], how="left")

    g["reincidencias"] = g["reincidencias"].astype(int)
    g["cronico"] = g["reincidencias"] >= 3  # já é por ativo — sinal direto do RASF

    # Leitura rápida ANTES do gráfico — pedido do Julio (16/07/2026): quem
    # abre a aba já vê o resumo sem precisar rolar a tela pra baixo do Unifilar.
    if modo_todos:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🚂 Ativos (todos os trechos)", f"{len(g):,}".replace(",", "."))
        densidade = len(d) / max(len(g), 1)
        c2.metric("📊 Densidade", f"{densidade:.1f} falhas/ativo")
        top_row = g.sort_values("score", ascending=False).iloc[0]
        c3.metric("🎯 Ativo mais crítico", ativo_curto(top_row["local_instalacao"]))
        c4.metric("🚂 Trecho do ativo crítico", nome_ramal(top_row["ramal"], "completo"))
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("🚂 Ativos no trecho", f"{len(g):,}".replace(",", "."))
        densidade = len(d) / max(len(g), 1)
        c2.metric("📊 Densidade", f"{densidade:.1f} falhas/ativo")
        top_ativo = ativo_curto(g.sort_values("score", ascending=False).iloc[0]["local_instalacao"]) if len(g) else "—"
        c3.metric("🎯 Ativo mais crítico", top_ativo)

    fmax = float(g["falhas"].max() or 1)

    def _bsize(n):
        return 14 + 36 * (n / fmax)

    pts, pts_cronico = [], []
    for _, r in g.iterrows():
        size = _bsize(r["falhas"])
        pts.append({
            "value": [float(r["posicao"]), round(float(r["score"]), 3)],
            "symbolSize": size,
            "_ativo": ativo_curto(r["local_instalacao"]),
            "_ramal": nome_ramal(r["ramal"], "completo") if modo_todos else None,
            "_patio": str(r["patio"]),
            "_sistema": str(r["sistema"]),
            "_falhas": int(r["falhas"]),
            "_reincid": int(r["reincidencias"]),
            "_thp": round(float(r["thp_h"]), 0),
            "_sintomas": r["sintomas"],
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
            var ramalLinha = d._ramal
                ? ('Trecho: <b>'+ d._ramal +'</b><br/>') : '';
            return '<div style="min-width:230px;">'
                 + '<b>'+ (d._ativo||'') +'</b> '+ badge +'<br/>'
                 + ramalLinha
                 + 'Pátio: <b>'+ (d._patio||'—') +'</b> · Sistema: <b>'+ (d._sistema||'—') +'</b><br/>'
                 + 'Falhas: <b>'+ (d._falhas||0) +'</b> · THP: <b>'+ (d._thp||0) +' h</b><br/>'
                 + 'Reincidências (90d): <b>'+ (d._reincid||0) +'</b><br/>'
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

    if modo_todos and len(fronteiras) > 1:
        # Linha tracejada + rótulo no início de cada trecho (menos o primeiro,
        # que já começa no eixo) — separa visualmente cada trecho concatenado.
        series[0]["markLine"] = {
            "symbol": "none",
            "silent": True,
            "animation": False,
            "lineStyle": {"color": "#9ca3af", "type": "dashed", "width": 1},
            "label": {
                "formatter": "{b}", "position": "insideEndTop",
                "color": "#374151", "fontSize": 10, "fontWeight": "bold",
                "rotate": 90, "distance": [4, 4],
            },
            "data": [
                {"xAxis": f["inicio"] - _GAP_TRECHOS / 2, "name": f["label"]}
                for f in fronteiras[1:]
            ],
        }

    eixo_nome = ("Trechos concatenados (linhas tracejadas separam cada trecho — não é KM real)"
                 if modo_todos else "Posição sequencial no trecho (não é KM real)")

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
            "type": "value", "name": eixo_nome,
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
            "text": ["🔴 Crítico (1,0)", "🟢 Normal (0,0)"],
            "calculable": True, "precision": 2, "showLabel": True,
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
    chart_key = f"ee_unifilar_{escopo}_{'TODOS' if modo_todos else ramal_view}"
    st_echarts(options=option, height="460px", key=chart_key)


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
    # Texto longo (nome de ativo, sintoma, origem...) quebra em várias linhas
    # em vez de estourar/vazar do card — fonte menor pra caber mais sem
    # cortar. Limiar baixo (12) de propósito: strings tipo "IBA_IBA-SINALIZ"
    # (16 chars) já vazavam a largura estreita do card em 1.5rem por não
    # terem espaço pra quebrar — overflow-wrap:anywhere força a quebra
    # mesmo sem espaço (em "_"/"-"), então cabe inteiro em 2-3 linhas.
    tamanho_fonte = "1.05rem" if len(str(valor)) > 12 else "1.4rem"
    with col:
        st.markdown(
            f"""
            <div style="background:white;border:1px solid #e5e7eb;border-left:4px solid {cor};
                        border-radius:10px;padding:12px 14px;height:100%;">
              <div style="font-size:0.72rem;color:#6b7280;text-transform:uppercase;
                          letter-spacing:.5px;font-weight:600;">{label}</div>
              <div style="font-size:{tamanho_fonte};font-weight:800;color:{cor};line-height:1.25;
                          margin-top:2px;word-break:normal;overflow-wrap:anywhere;">{valor}</div>
              <div style="font-size:0.72rem;color:#9ca3af;margin-top:4px;">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# endregion


# region ====================== SESSÃO 7B: Exportar Relatório ==================

def _bloco_exportar_relatorio(df: pd.DataFrame, escopo: str):
    """
    Gera um HTML autônomo (components/relatorio_ee.py) com o resumo do
    recorte JÁ FILTRADO na tela — mesmos números que o usuário está vendo.
    Fica em session_state pra o botão de download sobreviver ao rerun do
    Streamlit sem precisar gerar de novo a cada interação.
    """
    st.markdown("#### 📄 Exportar Relatório")
    st.caption(
        "Gera um .html autônomo com o resumo do recorte filtrado acima "
        "(Resumo Executivo, Pareto, Obras × Manutenção, Mapa de Calor e "
        "Ranking) — abre em qualquer navegador, sem precisar do sistema."
    )

    key_html = f"ee_relatorio_html_{escopo}"
    col_gerar, col_baixar = st.columns([1, 2])

    with col_gerar:
        if st.button("🧾 Gerar relatório", key=f"ee_gerar_relatorio_{escopo}", use_container_width=True):
            from components.relatorio_ee import gerar_relatorio_html
            st.session_state[key_html] = gerar_relatorio_html(df, escopo)

    with col_baixar:
        if key_html in st.session_state:
            st.download_button(
                "⬇️ Baixar relatório (.html)",
                data=st.session_state[key_html].encode("utf-8"),
                file_name=f"relatorio_ee_{escopo}_{date.today().isoformat()}.html",
                mime="text/html",
                key=f"ee_download_relatorio_{escopo}",
                use_container_width=True,
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

    # Origem efetiva + status de consenso ANTES dos filtros — o filtro de
    # origem/consenso já precisa dessas colunas calculadas.
    df = _preparar_origem(df)

    # Filtros (Sistema, Reincidência, Período + expander) — aplicados ANTES
    # do enriquecimento, pra score_ee e todas as agregações já refletirem o
    # recorte escolhido.
    df = _render_filtros(df, escopo)
    if df.empty:
        st.info("ℹ️ Nenhuma falha encontrada com os filtros aplicados.")
        return

    df = _enriquecer(df)
    st.markdown("---")

    _bloco_exportar_relatorio(df, escopo)
    st.markdown("---")
    _bloco_cards_resumo(df, escopo)
    st.markdown("---")
    _bloco_unifilar(df, escopo)
    st.markdown("---")
    _bloco_pareto_sintomas(df, escopo)
    st.markdown("---")
    _bloco_obras_manutencao(df, escopo)
    st.markdown("---")
    _bloco_heatmap_patio_origem(df, escopo)
    st.markdown("---")
    _bloco_reincidencia(df, escopo)

# endregion
