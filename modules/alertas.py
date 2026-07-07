# modules/alertas.py — Tela de Alertas Automáticos (Sprint 5)
#
# Exibe os alertas persistidos na tabela `alertas`: hot-spots crônicos e
# reincidências, com severidade 🔴/🟡/🔵, filtros, recálculo manual, marcação
# de status (visto/resolvido) e exportação CSV/Excel.
#
# Granularidade: ramal + origem (pátio). Canal: app (badge + tela) com
# previsão de e-mail/export.
#
# Sessão 1: Imports & CSS
# Sessão 2: Cabeçalho & barra de ações
# Sessão 3: Cartões-resumo por severidade
# Sessão 4: Tabela / lista de alertas
# Sessão 5: Entrada da tela (render_alertas)

# region ====================== SESSÃO 1: Imports & CSS ========================
import streamlit as st
import pandas as pd

from auth.session import get_gerencia, get_perfil, get_id
from auth.permissions import can_see_gerencia
from database.queries import (
    get_alertas, marcar_alerta_status, contar_alertas_novos, log_acesso,
)

COR_CRIT = "#dc2626"
COR_WARN = "#f59e0b"
COR_INFO = "#2563eb"
COR_OK   = "#16a34a"

_SEV_META = {
    "critico": ("🔴", "Crítico",  COR_CRIT),
    "atencao": ("🟡", "Atenção",  COR_WARN),
    "info":    ("🔵", "Informativo", COR_INFO),
}
_TIPO_LABEL = {
    "cronico":      "Hot-spot crônico",
    "reincidencia": "Reincidência",
}


def _inject_css():
    st.markdown("""
    <style>
    .alert-card {
        border-left: 5px solid #ccc; border-radius: 10px;
        padding: 12px 16px; margin-bottom: 10px;
        background: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .alert-badge {
        display:inline-block; border-radius:20px; padding:1px 10px;
        font-size:0.72rem; font-weight:600; margin-right:6px;
    }
    </style>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Cabeçalho & Ações =====================

def _gerencia_ativa() -> str:
    """Gerência do usuário; admin/global usa seletor."""
    g = get_gerencia()
    if g:
        return g
    opcoes = [x for x in ("SP", "VP") if can_see_gerencia(x)] or ["SP"]
    return st.session_state.get("alertas_ger", opcoes[0])


def _barra_acoes(gerencia: str):
    """Filtros + botões de recálculo e exportação."""
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.4])

    with c1:
        if not get_gerencia():
            opcoes = [x for x in ("SP", "VP") if can_see_gerencia(x)] or ["SP"]
            st.session_state["alertas_ger"] = st.selectbox(
                "Gerência", opcoes,
                index=opcoes.index(gerencia) if gerencia in opcoes else 0,
                key="sel_alertas_ger",
            )
        else:
            st.markdown(f"**Gerência:** {gerencia}")

    with c2:
        disc = st.selectbox("Disciplina", ["Todas", "VP", "EE"], key="sel_alertas_disc")
    with c3:
        sev = st.selectbox("Severidade", ["Todas", "Crítico", "Atenção", "Informativo"],
                           key="sel_alertas_sev")
    with c4:
        status = st.selectbox("Status", ["Ativos", "Todos", "Novos", "Vistos", "Resolvidos"],
                              key="sel_alertas_status")

    b1, b2, b3 = st.columns([1.4, 1, 1])
    with b1:
        recalcular = st.button("🔄 Recalcular alertas", use_container_width=True,
                               key="btn_recalc_alertas")
    return {
        "disciplina": None if disc == "Todas" else disc,
        "severidade": {"Crítico": "critico", "Atenção": "atencao",
                       "Informativo": "info"}.get(sev),
        "status":     status,
        "recalcular": recalcular,
    }


def _executar_recalculo(gerencia: str):
    """Dispara o motor de detecção e persiste (botão manual)."""
    from core.alertas import gerar_alertas, persistir_alertas
    from core.notificacoes import enviar_email_alertas

    with st.spinner("Analisando notas e gerando alertas..."):
        df_alertas = gerar_alertas(gerencia)
        n = persistir_alertas(df_alertas)

    log_acesso(get_id(), "recalcular_alertas", {"gerencia": gerencia, "gerados": n})
    st.success(f"✅ {n} alerta(s) processado(s) para a Gerência {gerencia}.")

    # Previsão de e-mail: só dispara se ativado nas configurações
    if not df_alertas.empty:
        res = enviar_email_alertas(df_alertas, gerencia)
        if res.get("enviado"):
            st.info(f"📧 {res['motivo']}")

    get_alertas.clear()
    contar_alertas_novos.clear()

# endregion


# region ====================== SESSÃO 3: Cartões-resumo ========================

def _cartoes_resumo(df: pd.DataFrame):
    total   = len(df)
    n_crit  = int((df["severidade"] == "critico").sum()) if not df.empty else 0
    n_aten  = int((df["severidade"] == "atencao").sum()) if not df.empty else 0
    n_novos = int((df["status"] == "novo").sum()) if not df.empty else 0

    cols = st.columns(4)
    dados = [
        ("Total de alertas", total, "#1e3a5f"),
        ("🔴 Críticos",      n_crit, COR_CRIT),
        ("🟡 Atenção",       n_aten, COR_WARN),
        ("🆕 Novos",         n_novos, COR_OK),
    ]
    for col, (label, valor, cor) in zip(cols, dados):
        col.markdown(f"""
        <div style="background:#fff; border-radius:12px; padding:14px 16px;
                    border-top:4px solid {cor}; box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <div style="font-size:0.78rem; color:#6b7280;">{label}</div>
            <div style="font-size:1.7rem; font-weight:700; color:{cor};">{valor}</div>
        </div>
        """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 4: Lista de alertas ======================

def _filtrar(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    if f["severidade"]:
        d = d[d["severidade"] == f["severidade"]]
    status_map = {"Novos": "novo", "Vistos": "visto", "Resolvidos": "resolvido"}
    if f["status"] in status_map:
        d = d[d["status"] == status_map[f["status"]]]
    elif f["status"] == "Ativos":
        d = d[d["status"] != "resolvido"]
    ordem = {"critico": 0, "atencao": 1, "info": 2}
    d["_ord"] = d["severidade"].map(ordem).fillna(3)
    return d.sort_values(["_ord", "score_acumulado"], ascending=[True, False]).drop(columns="_ord")


def _render_lista(df: pd.DataFrame):
    if df.empty:
        st.info("✅ Nenhum alerta para os filtros selecionados.")
        return

    for _, r in df.iterrows():
        icone, sev_lbl, cor = _SEV_META.get(r.get("severidade"), ("🔵", "—", COR_INFO))
        tipo_lbl = _TIPO_LABEL.get(r.get("tipo"), r.get("tipo", ""))
        ramal  = r.get("ramal") or "—"
        origem = r.get("origem") or "—"
        familia = r.get("familia_defeito") or "—"
        n_oc   = int(r.get("n_ocorrencias", 0) or 0)
        score  = float(r.get("score_acumulado", 0) or 0)
        status = r.get("status", "novo")

        with st.container():
            st.markdown(f"""
            <div class="alert-card" style="border-left-color:{cor};">
                <span class="alert-badge" style="background:{cor}22; color:{cor};">
                    {icone} {sev_lbl}</span>
                <span class="alert-badge" style="background:#1e3a5f18; color:#1e3a5f;">
                    {tipo_lbl}</span>
                <span style="float:right; font-size:0.75rem; color:#9ca3af;">
                    status: <b>{status}</b></span>
                <div style="margin-top:6px; font-weight:600; color:#111827;">
                    {ramal} · {origem} — {familia}
                </div>
                <div style="font-size:0.85rem; color:#4b5563; margin-top:2px;">
                    {n_oc} ocorrência(s) · score acumulado {score:.1f}
                </div>
            </div>
            """, unsafe_allow_html=True)

            ca, cb, cc = st.columns([1, 1, 6])
            aid = r.get("id")
            if status != "visto" and status != "resolvido":
                if ca.button("👁 Visto", key=f"visto_{aid}"):
                    marcar_alerta_status(aid, "visto", get_id())
                    get_alertas.clear(); contar_alertas_novos.clear()
                    st.rerun()
            if status != "resolvido":
                if cb.button("✔ Resolver", key=f"resolv_{aid}"):
                    marcar_alerta_status(aid, "resolvido", get_id())
                    get_alertas.clear(); contar_alertas_novos.clear()
                    st.rerun()


def _botoes_export(df: pd.DataFrame):
    if df.empty:
        return
    from core.notificacoes import exportar_alertas_csv, exportar_alertas_xlsx
    st.markdown("##### 📥 Exportar")
    e1, e2, _ = st.columns([1, 1, 4])
    e1.download_button("CSV", exportar_alertas_csv(df),
                       file_name="alertas_mrs.csv", mime="text/csv",
                       use_container_width=True, key="dl_csv_alertas")
    e2.download_button("Excel", exportar_alertas_xlsx(df),
                       file_name="alertas_mrs.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True, key="dl_xlsx_alertas")

# endregion


# region ====================== SESSÃO 5: Entrada da tela =======================

def render_alertas():
    """Ponto de entrada da tela de Alertas (rota 'alertas')."""
    _inject_css()
    st.markdown("## 🚨 Alertas Automáticos")
    st.caption(
        "Hot-spots crônicos (≥3 notas da mesma família em 6 meses, mesmo ramal+origem) "
        "e reincidências (reabertura ≤90 dias). Recálculo automático no upload + manual."
    )

    gerencia = _gerencia_ativa()
    filtros = _barra_acoes(gerencia)
    gerencia = _gerencia_ativa()  # reavalia após seletor

    if filtros["recalcular"]:
        _executar_recalculo(gerencia)

    df = get_alertas(gerencia, filtros["disciplina"])

    st.divider()
    _cartoes_resumo(df)
    st.divider()

    df_view = _filtrar(df, filtros)
    _render_lista(df_view)
    st.divider()
    _botoes_export(df_view)

# endregion
