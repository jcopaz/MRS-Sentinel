# =============================================================================
# modules/evolucao_malha.py — Sprint 8 (Memória & Comparações)
#
# Dashboard "Evolução da Malha": compara indicadores da base VIVA de notas entre
# dois períodos (SEMANAL ou MENSAL), consumindo as fotos semanais gravadas em
# `snapshots` (ver core/snapshots.py + database/queries_snapshots.py).
#
#   • Granularidade SEMANAL  → período = semana ISO (2026-W31).
#   • Granularidade MENSAL   → agrega as semanas do mês (fluxo soma; estoque =
#     última foto do mês).
#
# Métricas de FLUXO (somam entre semanas):  aberturas, encerramentos, THP.
# Métricas de ESTOQUE (estado no tempo):    backlog, crônicas, reincidentes,
#                                            score médio, % crônico.
#
# Sessão 1: Config + helpers de agregação
# Sessão 2: KPIs com setas ▲▼ (sentido bom/ruim por métrica)
# Sessão 3: Gráfico de tendência (ECharts, com fallback)
# Sessão 4: Tabela comparativa por trecho (Período A × B × Δ)
# Sessão 5: render_evolucao_malha() — orquestra filtros + blocos
# =============================================================================

import streamlit as st
import pandas as pd

try:
    from streamlit_echarts import st_echarts
    ECHARTS_OK = True
except Exception:  # pragma: no cover
    ECHARTS_OK = False

from auth.permissions import gerencias_visiveis
from database.queries_snapshots import get_snapshots

# region ====================== SESSÃO 1: Config + agregação ===================

COR_PRIMARIA = "#1e3a5f"
COR_OK = "#16a34a"
COR_RUIM = "#dc2626"
COR_NEUTRO = "#6b7280"

# Colunas de FLUXO (somam ao juntar semanas num mês).
_FLUXO = ["aberturas_periodo", "encerramentos_periodo", "thp_acumulado"]
# Colunas de ESTOQUE contáveis (estado; no mês = última foto).
_ESTOQUE_CONT = ["total_notas", "notas_abertas", "notas_cronicas", "reincidentes"]

# Métricas expostas nos KPIs/tabela: (coluna, rótulo, sentido, formato).
# sentido: "menor_melhor" (subir = ruim/vermelho) ou "maior_melhor".
METRICAS = [
    ("notas_abertas",         "Backlog (abertas)",   "menor_melhor", "int"),
    ("aberturas_periodo",     "Aberturas",           "menor_melhor", "int"),
    ("encerramentos_periodo", "Encerramentos",       "maior_melhor", "int"),
    ("notas_cronicas",        "Crônicas",            "menor_melhor", "int"),
    ("reincidentes",          "Reincidentes",        "menor_melhor", "int"),
    ("score_medio",           "Score médio",         "menor_melhor", "float"),
    ("pct_cronico",           "% Crônico",           "menor_melhor", "pct"),
    ("thp_acumulado",         "THP acumulado",       "menor_melhor", "float"),
]


def _col_periodo(df: pd.DataFrame, granularidade: str) -> pd.Series:
    """Chave de período conforme a granularidade escolhida."""
    if granularidade == "Mensal":
        dref = pd.to_datetime(df.get("data_ref"), errors="coerce")
        return dref.dt.strftime("%Y-%m")
    return df["semana_iso"].astype(str)


def _combinar_semanas_no_mes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Para a visão MENSAL, junta as semanas de cada (periodo × ramal × trecho):
    fluxo = soma; estoque = última foto (maior data_ref) do mês.
    """
    if df.empty:
        return df
    d = df.copy()
    d["_ord"] = pd.to_datetime(d.get("data_ref"), errors="coerce")
    chaves = ["periodo", "gerencia", "disciplina", "ramal", "trecho"]
    chaves = [c for c in chaves if c in d.columns]

    linhas = []
    for chave_vals, g in d.groupby(chaves, dropna=False):
        g = g.sort_values("_ord")
        ult = g.iloc[-1]
        if not isinstance(chave_vals, tuple):
            chave_vals = (chave_vals,)
        reg = {c: chave_vals[i] for i, c in enumerate(chaves)}
        for c in _FLUXO:
            if c in g.columns:
                reg[c] = float(pd.to_numeric(g[c], errors="coerce").fillna(0).sum())
        for c in _ESTOQUE_CONT:
            if c in g.columns:
                reg[c] = float(pd.to_numeric(ult.get(c), errors="coerce") or 0)
        if "score_medio" in g.columns:
            reg["score_medio"] = ult.get("score_medio")
        reg["data_ref"] = ult.get("data_ref")
        linhas.append(reg)
    return pd.DataFrame(linhas)


def _totais_por_periodo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Consolida a malha por período: soma contagens/fluxo, score = média ponderada
    por total_notas, %crônico recomputado. Uma linha por período.
    """
    if df.empty:
        return df
    d = df.copy()
    for c in _FLUXO + _ESTOQUE_CONT:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["score_medio"] = pd.to_numeric(d.get("score_medio"), errors="coerce")

    linhas = []
    for periodo, g in d.groupby("periodo", dropna=False):
        total = float(g["total_notas"].sum()) if "total_notas" in g else 0.0
        n_cron = float(g["notas_cronicas"].sum()) if "notas_cronicas" in g else 0.0
        peso = g["total_notas"] if "total_notas" in g else pd.Series(1.0, index=g.index)
        sc = g["score_medio"]
        mask = sc.notna() & (peso > 0)
        score_pond = (float((sc[mask] * peso[mask]).sum() / peso[mask].sum())
                      if mask.any() and peso[mask].sum() > 0 else None)
        reg = {"periodo": periodo}
        for c in _FLUXO + _ESTOQUE_CONT:
            if c in g.columns:
                reg[c] = float(g[c].sum())
        reg["score_medio"] = score_pond
        reg["pct_cronico"] = round(100.0 * n_cron / total, 1) if total else 0.0
        linhas.append(reg)
    out = pd.DataFrame(linhas).sort_values("periodo").reset_index(drop=True)
    return out


def _preparar(gerencias, disciplinas, granularidade) -> pd.DataFrame:
    """Lê snapshots das gerências/disciplinas visíveis e anexa coluna periodo."""
    frames = []
    for g in gerencias:
        for disc in disciplinas:
            snap = get_snapshots(gerencia=g, disciplina=disc)
            if snap is not None and not snap.empty:
                frames.append(snap)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["periodo"] = _col_periodo(df, granularidade)
    df = df[df["periodo"].notna()]
    if granularidade == "Mensal":
        df = _combinar_semanas_no_mes(df)
    return df

# endregion


# region ====================== SESSÃO 2: KPIs com setas =======================

def _fmt(valor, formato) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "—"
    if formato == "int":
        return f"{int(round(valor))}"
    if formato == "pct":
        return f"{valor:.1f}%"
    return f"{valor:.2f}"


def _delta_html(atual, anterior, sentido, formato) -> str:
    """Seta ▲▼ colorida conforme melhora/piora."""
    if atual is None or anterior is None or pd.isna(atual) or pd.isna(anterior):
        return f"<span style='color:{COR_NEUTRO};font-size:0.8rem;'>—</span>"
    diff = atual - anterior
    if abs(diff) < 1e-9:
        return f"<span style='color:{COR_NEUTRO};font-size:0.8rem;'>▬ 0</span>"
    subiu = diff > 0
    bom = (subiu and sentido == "maior_melhor") or (not subiu and sentido == "menor_melhor")
    cor = COR_OK if bom else COR_RUIM
    seta = "▲" if subiu else "▼"
    val = _fmt(abs(diff), formato)
    return (f"<span style='color:{cor};font-size:0.8rem;font-weight:700;'>"
            f"{seta} {val}</span>")


def _bloco_kpis(tot: pd.DataFrame, pa: str, pb: str):
    st.markdown("##### 📊 Indicadores — Período atual vs. anterior")
    linha_b = tot[tot["periodo"] == pb]
    linha_a = tot[tot["periodo"] == pa]
    if linha_b.empty:
        st.info("Sem dados no período selecionado.")
        return
    rb = linha_b.iloc[0]
    ra = linha_a.iloc[0] if not linha_a.empty else None

    cols = st.columns(4)
    for i, (col, rot, sentido, fmt) in enumerate(METRICAS):
        atual = rb.get(col)
        ant = ra.get(col) if ra is not None else None
        with cols[i % 4]:
            st.markdown(
                f"<div style='border:1px solid #e5e7eb;border-radius:10px;"
                f"padding:10px 12px;margin-bottom:8px;background:#fff;'>"
                f"<div style='font-size:0.72rem;color:{COR_NEUTRO};"
                f"text-transform:uppercase;letter-spacing:.5px;'>{rot}</div>"
                f"<div style='font-size:1.5rem;font-weight:800;"
                f"color:{COR_PRIMARIA};line-height:1.2;'>{_fmt(atual, fmt)}</div>"
                f"{_delta_html(atual, ant, sentido, fmt)}"
                f"</div>",
                unsafe_allow_html=True,
            )

# endregion


# region ====================== SESSÃO 3: Tendência ============================

def _bloco_tendencia(tot: pd.DataFrame):
    st.markdown("##### 📈 Tendência ao longo do tempo")
    if tot.empty:
        st.info("Sem série histórica.")
        return
    opcoes = {rot: col for col, rot, _, _ in METRICAS if col in tot.columns}
    rot_sel = st.selectbox("Métrica", list(opcoes.keys()), key="evo_metrica_trend")
    col = opcoes[rot_sel]

    periodos = tot["periodo"].tolist()
    valores = [None if pd.isna(v) else round(float(v), 3)
               for v in tot[col].tolist()]

    if not ECHARTS_OK:
        st.line_chart(tot.set_index("periodo")[[col]])
        return

    opt = {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "5%", "top": "10%", "bottom": "12%",
                 "containLabel": True},
        "xAxis": {"type": "category", "data": periodos,
                  "axisLabel": {"color": "#374151", "rotate": 30}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#374151"},
                  "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}}},
        "series": [{
            "type": "line", "data": valores, "smooth": True,
            "symbolSize": 8, "lineStyle": {"width": 3, "color": COR_PRIMARIA},
            "itemStyle": {"color": COR_PRIMARIA},
            "areaStyle": {"color": "rgba(30,58,95,0.08)"},
            "label": {"show": True, "position": "top", "fontSize": 11,
                      "color": "#374151"},
        }],
    }
    st_echarts(opt, height="340px", key="evo_trend")

# endregion


# region ====================== SESSÃO 4: Tabela por trecho ====================

def _bloco_tabela_trecho(df: pd.DataFrame, pa: str, pb: str):
    st.markdown("##### 🧭 Comparativo por trecho (atual vs. anterior)")
    if df.empty:
        st.info("Sem dados por trecho.")
        return
    d = df.copy()
    d["ramal"] = d["ramal"].fillna("—")
    d["trecho"] = d["trecho"].fillna("—")

    def _agg(periodo):
        sub = d[d["periodo"] == periodo]
        if sub.empty:
            return pd.DataFrame(columns=["ramal", "trecho"])
        g = sub.groupby(["ramal", "trecho"], dropna=False).agg(
            backlog=("notas_abertas", "sum"),
            cronicas=("notas_cronicas", "sum"),
            encerr=("encerramentos_periodo", "sum"),
        ).reset_index()
        return g

    gb = _agg(pb)
    ga = _agg(pa)
    if gb.empty:
        st.info("Sem dados no período atual.")
        return
    m = gb.merge(ga, on=["ramal", "trecho"], how="outer",
                 suffixes=("_atual", "_ant")).fillna(0)
    m["Δ backlog"] = (m["backlog_atual"] - m["backlog_ant"]).astype(int)
    tabela = pd.DataFrame({
        "Ramal": m["ramal"],
        "Trecho": m["trecho"],
        "Backlog (atual)": m["backlog_atual"].astype(int),
        "Backlog (ant.)": m["backlog_ant"].astype(int),
        "Δ backlog": m["Δ backlog"],
        "Crônicas": m["cronicas_atual"].astype(int),
        "Encerr. período": m["encerr_atual"].astype(int),
    }).sort_values("Δ backlog", ascending=False).reset_index(drop=True)

    def _cor_delta(v):
        if isinstance(v, (int, float)) and v > 0:
            return f"color:{COR_RUIM};font-weight:700"
        if isinstance(v, (int, float)) and v < 0:
            return f"color:{COR_OK};font-weight:700"
        return ""

    try:
        estilo = tabela.style.map(_cor_delta, subset=["Δ backlog"])
    except AttributeError:  # pandas < 2.1 usa applymap
        estilo = tabela.style.applymap(_cor_delta, subset=["Δ backlog"])

    st.dataframe(estilo, use_container_width=True, hide_index=True)

# endregion


# region ====================== SESSÃO 5: render ===============================

def render_evolucao_malha():
    st.markdown("### 📈 Evolução da Malha")
    st.caption("Comparação período a período das notas (base viva), a partir das "
               "fotos semanais automáticas. RASF/EE congelado usa o comparativo "
               "anual (YoY) na aba de Inteligência.")

    gers = gerencias_visiveis()
    if not gers:
        st.warning("Sem gerências visíveis para o seu perfil.")
        return

    with st.form("evo_filtros"):
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            granularidade = st.radio("Granularidade", ["Semanal", "Mensal"],
                                     horizontal=True, key="evo_gran")
        with c2:
            disc_sel = st.multiselect("Disciplina", ["VP", "EE"],
                                      default=["VP", "EE"], key="evo_disc")
        with c3:
            ger_sel = st.multiselect("Gerência", gers, default=gers, key="evo_ger")
        aplicar = st.form_submit_button("✅ Aplicar", use_container_width=True)

    # Estado inicial: aplica com defaults na 1ª carga.
    if not aplicar and not st.session_state.get("evo_carregado"):
        st.session_state["evo_carregado"] = True
        aplicar = True
    if not aplicar:
        st.info("Ajuste os filtros e clique em **Aplicar**.")
        return

    with st.spinner("Carregando fotos semanais…"):
        df = _preparar(ger_sel or gers, disc_sel or ["VP", "EE"], granularidade)

    if df.empty:
        st.info("Ainda não há fotos gravadas. As fotos semanais são criadas "
                "automaticamente a cada upload de notas (VP/EE).")
        return

    tot = _totais_por_periodo(df)
    periodos = tot["periodo"].tolist()
    if len(periodos) < 1:
        st.info("Sem períodos disponíveis.")
        return

    st.markdown("---")
    cpa, cpb = st.columns(2)
    with cpb:
        pb = st.selectbox("Período atual", periodos, index=len(periodos) - 1,
                          key="evo_pb")
    with cpa:
        idx_a = max(0, periodos.index(pb) - 1)
        pa = st.selectbox("Período anterior (base)", periodos, index=idx_a,
                          key="evo_pa")

    _bloco_kpis(tot, pa, pb)
    st.markdown("---")
    _bloco_tendencia(tot)
    st.markdown("---")
    _bloco_tabela_trecho(df, pa, pb)

# endregion
