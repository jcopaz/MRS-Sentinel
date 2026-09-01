# =============================================================================
# modules/visao_campo.py — Sprint 9 (Mobile First)
#
# "Visão de Campo": tela ENXUTA para uso no celular (um toque). Em vez de tornar
# todo o dashboard (ECharts/Folium/AgGrid) responsivo de uma vez, entrega o
# essencial para quem está em campo:
#   • 3 KPIs grandes empilhados: Backlog, Críticas, Alertas novos
#   • Lista priorizada Top-N de notas ABERTAS (por score) em cards compactos
#   • Alertas ativos (crônico/reincidência) resumidos
#
# Layout coluna única + CSS de alvos de toque grandes. Respeita a gerência/
# permissões do usuário. Toda leitura falha graciosamente (offline/sem dados).
#
# Sessão 1: CSS mobile + helpers puros (ordenação/dias/kpis)
# Sessão 2: Blocos de UI (KPIs, lista de notas, alertas)
# Sessão 3: render_visao_campo()
# =============================================================================

import streamlit as st
import pandas as pd

from auth.permissions import gerencias_visiveis, require_admin

# region ====================== SESSÃO 1: CSS + helpers ========================

COR_PRIMARIA = "#1e3a5f"
COR_CRIT = "#dc2626"
COR_WARN = "#f59e0b"
COR_OK = "#16a34a"
COR_TEXTO = "#1f2937"
COR_SUAVE = "#6b7280"

CORES_PRIORIDADE = {
    "1-Muito alta": "#dc2626", "2-Alta": "#f59e0b",
    "3-Média": "#eab308", "4-Baixa": "#16a34a",
}
ORDEM_PRIORIDADE = {"1-Muito alta": 4, "2-Alta": 3, "3-Média": 2, "4-Baixa": 1}

_CSS = """
<style>
/* Visão de Campo — alvos de toque grandes, coluna única */
.vc-kpi{border-radius:14px;padding:16px 18px;margin:8px 0;color:#fff;
  box-shadow:0 2px 10px rgba(0,0,0,.12);}
.vc-kpi .n{font-size:2.2rem;font-weight:800;line-height:1;}
.vc-kpi .l{font-size:.85rem;opacity:.92;text-transform:uppercase;
  letter-spacing:.5px;margin-top:4px;}
.vc-card{border:1px solid #e5e7eb;border-left:5px solid var(--bar,#6b7280);
  border-radius:12px;padding:12px 14px;margin:8px 0;background:#fff;}
.vc-card .top{display:flex;justify-content:space-between;align-items:center;}
.vc-card .ramal{font-weight:800;color:#1e3a5f;font-size:1.05rem;}
.vc-card .prio{font-size:.72rem;font-weight:700;color:#fff;padding:2px 8px;
  border-radius:20px;}
.vc-card .meta{font-size:.82rem;color:#374151;margin-top:6px;}
.vc-card .sub{font-size:.75rem;color:#6b7280;margin-top:2px;}
@media (max-width:640px){
  .block-container{padding:0.6rem 0.7rem !important;}
  .vc-kpi .n{font-size:2rem;}
}
</style>
"""


def _is_aberta(serie_status: pd.Series) -> pd.Series:
    """Nota aberta = status começa com 'AB' (ABER...)."""
    return serie_status.astype(str).str.upper().str.startswith("AB")


def _dias_aberta(data_nota, hoje=None) -> int:
    """Dias corridos desde a abertura (0 se data inválida)."""
    dt = pd.to_datetime(data_nota, errors="coerce")
    if pd.isna(dt):
        return 0
    hoje = pd.Timestamp.now().normalize() if hoje is None else pd.Timestamp(hoje)
    return max(0, int((hoje.normalize() - dt.normalize()).days))


def _garantir_score(df: pd.DataFrame) -> pd.DataFrame:
    """Score padrão (congelado) se ainda não vier do banco."""
    if "score" in df.columns and pd.to_numeric(df["score"], errors="coerce").notna().any():
        df = df.copy()
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0.0)
        return df
    try:
        from core.score_engine import calcular_score_dataframe
        return calcular_score_dataframe(df)
    except Exception:
        d = df.copy()
        d["score"] = 0.0
        return d


def _kpis_campo(df: pd.DataFrame) -> dict:
    """Backlog (abertas), críticas (prioridade 1/2 abertas), total."""
    if df is None or df.empty:
        return {"backlog": 0, "criticas": 0, "total": 0}
    if "status_usuario" in df.columns:
        abertas = df[_is_aberta(df["status_usuario"])]
    else:
        abertas = df
    if "prioridade" in abertas.columns:
        criticas = int(abertas["prioridade"].isin(["1-Muito alta", "2-Alta"]).sum())
    else:
        criticas = 0
    return {"backlog": int(len(abertas)), "criticas": criticas,
            "total": int(len(df))}


def _top_criticas(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """
    Top-N notas ABERTAS ordenadas por (score desc, prioridade desc, dias desc).
    Devolve colunas prontas para o card.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    d = _garantir_score(df)
    if "status_usuario" in d.columns:
        d = d[_is_aberta(d["status_usuario"])].copy()
    if d.empty:
        return pd.DataFrame()
    d["_prio_ord"] = d.get("prioridade", pd.Series(index=d.index, dtype=object)) \
        .map(ORDEM_PRIORIDADE).fillna(0)
    d["_dias"] = d.get("data_nota").apply(_dias_aberta) if "data_nota" in d.columns \
        else 0
    d = d.sort_values(["score", "_prio_ord", "_dias"],
                      ascending=[False, False, False])
    return d.head(n).reset_index(drop=True)

# endregion


# region ====================== SESSÃO 2: Blocos de UI =========================

def _bloco_kpis(df: pd.DataFrame, n_alertas: int):
    k = _kpis_campo(df)
    cards = [
        ("Backlog aberto", k["backlog"], COR_PRIMARIA),
        ("Notas críticas", k["criticas"], COR_CRIT),
        ("Alertas novos", n_alertas, COR_WARN),
    ]
    for label, num, cor in cards:
        st.markdown(
            f"<div class='vc-kpi' style='background:{cor};'>"
            f"<div class='n'>{num}</div><div class='l'>{label}</div></div>",
            unsafe_allow_html=True,
        )


def _label_ramal(sigla) -> str:
    try:
        from core.glossarios import nome_ramal
        return nome_ramal(str(sigla), "completo") or str(sigla)
    except Exception:
        return str(sigla) if sigla is not None else "—"


def _bloco_lista(df: pd.DataFrame, n: int):
    st.markdown("#### 🚩 Prioridades de campo")
    top = _top_criticas(df, n)
    if top.empty:
        st.info("Sem notas abertas no escopo atual.")
        return

    for _, r in top.iterrows():
        prio = str(r.get("prioridade", "—"))
        cor_bar = CORES_PRIORIDADE.get(prio, COR_SUAVE)
        ramal = _label_ramal(r.get("ramal"))
        trecho = r.get("trecho") or "—"
        km = r.get("km_real")
        km_txt = f"km {float(km):.1f}" if pd.notna(km) else "km —"
        dias = _dias_aberta(r.get("data_nota"))
        score = r.get("score")
        score_txt = f"{float(score):.2f}" if pd.notna(score) else "—"
        fam = r.get("familia_defeito") or r.get("origem") or ""

        st.markdown(
            f"<div class='vc-card' style='--bar:{cor_bar};'>"
            f"<div class='top'>"
            f"<span class='ramal'>{ramal}</span>"
            f"<span class='prio' style='background:{cor_bar};'>{prio}</span>"
            f"</div>"
            f"<div class='meta'>📍 {trecho} · {km_txt} &nbsp;·&nbsp; ⏱️ {dias} dias</div>"
            f"<div class='sub'>score {score_txt}"
            + (f" · {fam}" if fam else "") + "</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _bloco_alertas(gerencia: str):
    st.markdown("#### 🚨 Alertas ativos")
    try:
        from database.queries import get_alertas
        al = get_alertas(gerencia)
    except Exception:
        al = pd.DataFrame()
    if al is None or al.empty:
        st.caption("Nenhum alerta ativo.")
        return
    if "status" in al.columns:
        al = al[al["status"].astype(str).str.lower() != "resolvido"]
    if al.empty:
        st.caption("Nenhum alerta ativo.")
        return

    col_tipo = "tipo" if "tipo" in al.columns else None
    for _, r in al.head(10).iterrows():
        tipo = str(r.get(col_tipo, "Alerta")) if col_tipo else "Alerta"
        sev = str(r.get("severidade", "")).lower()
        cor = COR_CRIT if "alt" in sev or "crit" in sev else COR_WARN
        ramal = _label_ramal(r.get("ramal"))
        origem = r.get("origem") or r.get("familia") or ""
        icone = "🔁" if "reinc" in tipo.lower() else "📌"
        st.markdown(
            f"<div class='vc-card' style='--bar:{cor};'>"
            f"<div class='top'><span class='ramal'>{icone} {ramal}</span>"
            f"<span class='prio' style='background:{cor};'>{tipo}</span></div>"
            f"<div class='sub'>{origem}</div></div>",
            unsafe_allow_html=True,
        )

# endregion


# region ====================== SESSÃO 3: render ===============================

def _carregar_notas(gerencia: str) -> pd.DataFrame:
    try:
        from database.queries import get_notas_cached
        return get_notas_cached(gerencia)
    except Exception:
        try:
            from database.queries import get_notas_gerencia
            return get_notas_gerencia(gerencia)
        except Exception:
            return pd.DataFrame()


def render_visao_campo():
    # Restrita a admin (pedido do Julio, 2026-09-01) — mesma lógica de
    # modules/alertas.py: bloqueio real, não só o link sumindo do menu.
    require_admin()
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("### 📱 Visão de Campo")

    gers = gerencias_visiveis()
    if not gers:
        st.warning("Sem gerências visíveis para o seu perfil.")
        return

    ger = (st.radio("Gerência", gers, horizontal=True, key="vc_ger")
           if len(gers) > 1 else gers[0])

    with st.spinner("Carregando…"):
        df = _carregar_notas(ger)
        try:
            from database.queries import contar_alertas_novos
            n_alertas = contar_alertas_novos(ger)
        except Exception:
            n_alertas = 0

    _bloco_kpis(df, n_alertas)
    st.markdown("---")

    n = st.slider("Quantas prioridades mostrar", 5, 30, 15, step=5, key="vc_n")
    _bloco_lista(df, n)
    st.markdown("---")
    _bloco_alertas(ger)

# endregion
