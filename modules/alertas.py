# modules/alertas.py — Tela de Alertas Automáticos (Sprint 5 · repaginação UI v3.6.0)
#
# Exibe os alertas persistidos na tabela `alertas`: hot-spots crônicos e
# reincidências, com severidade 🔴/🟡/🔵, filtros, recálculo manual, marcação
# de status (visto/resolvido) e exportação CSV/Excel.
#
# O QUE MUDOU NA REPAGINAÇÃO v3.6.0 (só ESTILO/UX — lógica de negócio intacta)
# ---------------------------------------------------------------------------
#   • Cores da FONTE ÚNICA core/tema.py (some COR_CRIT/COR_WARN/... duplicados).
#   • Cartões-resumo usam .mrs-card (hover) + .mrs-fade-up (entrada suave).
#   • Cartão de alerta CRÍTICO ganha barra de severidade com leve pulso —
#     mesmo "DNA radar" do Unifilar, aqui em CSS, sem tocar no unifilar.py.
#   • Layout responsivo: os cartões-resumo passam a usar a grid fluida global
#     (.mrs-kpi-grid) em vez de st.columns(4) fixo → empilham no mobile.
#   • RBAC, filtros, recálculo, export: SEM alteração de comportamento.
#
# Granularidade: ramal + origem (pátio). Canal: app (badge + tela).
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
from auth.permissions import can_see_gerencia, can_manage_alertas, require_login, gerencias_visiveis
from database.queries import (
    get_alertas, marcar_alerta_status, contar_alertas_novos, log_acesso,
)

# Cores da fonte única (core/tema.py). Import defensivo — mesmo padrão do projeto.
try:
    from core.tema import CORES
    COR_CRIT = CORES["critico"]
    COR_WARN = CORES["atencao"]
    COR_INFO = CORES["info"]
    COR_OK   = CORES["ok"]
    COR_PRIMARIA = CORES["primaria"]
except Exception:  # pragma: no cover - fallback defensivo
    COR_CRIT, COR_WARN, COR_INFO, COR_OK, COR_PRIMARIA = (
        "#dc2626", "#f59e0b", "#2563eb", "#16a34a", "#1e3a5f")

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
    """CSS específico da tela de Alertas.

    Depende do CSS GLOBAL (core/ui_global.injetar_css_global, chamado 1x em
    app.py) para as animações .mrs-fade-up/.mrs-pulse. Aqui só o que é
    exclusivo da lista de alertas. Idempotente via flag de sessão.
    """
    if st.session_state.get("_css_alertas_injetado"):
        return
    st.session_state["_css_alertas_injetado"] = True
    st.markdown("""
    <style>
    .alert-card {
        position: relative;
        border-left: 5px solid #ccc; border-radius: 12px;
        padding: 12px 16px 12px 18px; margin-bottom: 10px;
        background: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        transition: transform .15s ease, box-shadow .15s ease;
    }
    .alert-card:hover {
        transform: translateX(2px);
        box-shadow: 0 4px 14px rgba(0,0,0,0.10);
    }
    /* Barra de severidade animada no topo do card crítico — "respira"
       levemente, replicando o pulso do Unifilar em CSS (Unifilar intocado). */
    .alert-card.critico::before {
        content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
        border-radius: 12px 12px 0 0;
        background: linear-gradient(90deg, #dc2626, #f87171, #dc2626);
        background-size: 200% 100%;
        animation: mrsSweep 2.2s linear infinite;
    }
    .alert-badge {
        display:inline-block; border-radius:20px; padding:1px 10px;
        font-size:0.72rem; font-weight:600; margin-right:6px;
    }
    /* Grade fluida dos cartões-resumo (substitui st.columns(4) no mobile). */
    .alert-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px; margin-bottom: 4px;
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
    opcoes = gerencias_visiveis() or ["SP"]
    return st.session_state.get("alertas_ger", opcoes[0])


def _barra_acoes(gerencia: str, pode_gerir: bool = True):
    """Filtros + botões de recálculo e exportação.

    `pode_gerir` (RBAC): quando False (perfil Usuário), o botão de recálculo
    fica oculto e a tela opera em modo somente-leitura.
    """
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.4])

    with c1:
        if not get_gerencia():
            opcoes = gerencias_visiveis() or ["SP"]
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

    recalcular = False
    if pode_gerir:
        b1, _b2, _b3 = st.columns([1.4, 1, 1])
        with b1:
            recalcular = st.button("🔄 Recalcular alertas", use_container_width=True,
                                   key="btn_recalc_alertas")
    else:
        st.caption("🔒 Modo somente-leitura — seu perfil pode consultar e exportar, "
                   "mas não recalcular nem alterar status de alertas.")
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

    # Defesa em profundidade: revalida a permissão de escrita mesmo que o botão
    # tenha sido exibido indevidamente (ex.: sessão adulterada).
    if not can_manage_alertas(gerencia):
        st.error("🚫 Você não tem permissão para recalcular alertas desta gerência.")
        return

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
    """4 cartões-resumo. Agora em GRID FLUIDA (empilha no mobile) e com hover."""
    total   = len(df)
    n_crit  = int((df["severidade"] == "critico").sum()) if not df.empty else 0
    n_aten  = int((df["severidade"] == "atencao").sum()) if not df.empty else 0
    n_novos = int((df["status"] == "novo").sum()) if not df.empty else 0

    dados = [
        ("Total de alertas", total, COR_PRIMARIA, ""),
        ("🔴 Críticos",      n_crit, COR_CRIT, "mrs-pulse" if n_crit > 0 else ""),
        ("🟡 Atenção",       n_aten, COR_WARN, ""),
        ("🆕 Novos",         n_novos, COR_OK, ""),
    ]
    # Um único bloco HTML com grid fluida — reflui sozinho conforme a largura.
    cards = "".join(
        f"""<div class="mrs-card mrs-fade-up {extra}"
                 style="border-top:4px solid {cor};
                        --mrs-pulse-color:{cor}55;">
                <div style="font-size:0.78rem; color:#6b7280;">{label}</div>
                <div style="font-size:1.7rem; font-weight:700; color:{cor};">{valor}</div>
            </div>"""
        for (label, valor, cor, extra) in dados
    )
    st.markdown(f'<div class="alert-kpi-grid">{cards}</div>', unsafe_allow_html=True)

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


def _render_lista(df: pd.DataFrame, pode_gerir: bool = True):
    if df.empty:
        st.info("✅ Nenhum alerta para os filtros selecionados.")
        return

    for _, r in df.iterrows():
        sev = r.get("severidade")
        icone, sev_lbl, cor = _SEV_META.get(sev, ("🔵", "—", COR_INFO))
        tipo_lbl = _TIPO_LABEL.get(r.get("tipo"), r.get("tipo", ""))
        ramal  = r.get("ramal") or "—"
        origem = r.get("origem") or "—"
        familia = r.get("familia_defeito") or "—"
        n_oc   = int(r.get("n_ocorrencias", 0) or 0)
        score  = float(r.get("score_acumulado", 0) or 0)
        status = r.get("status", "novo")

        # Classe extra: 'critico' liga a barra animada do topo; fade-up = entrada.
        classe_sev = "critico" if sev == "critico" else ""

        with st.container():
            st.markdown(f"""
            <div class="alert-card mrs-fade-up {classe_sev}" style="border-left-color:{cor};">
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

            # Ações de escrita só para quem pode gerir (admin / assistente da ger.)
            if not pode_gerir:
                continue
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


def _botoes_export(df: pd.DataFrame, gerencia: str = ""):
    if df.empty:
        return
    from core.notificacoes import (
        exportar_alertas_csv, exportar_alertas_xlsx,
        exportar_alertas_pdf, exportar_alertas_relatorio_html,
    )
    st.markdown("##### 📥 Exportar")
    e1, e2, e3, _ = st.columns([1, 1, 1, 3])
    e1.download_button("CSV", exportar_alertas_csv(df),
                       file_name="alertas_mrs.csv", mime="text/csv",
                       use_container_width=True, key="dl_csv_alertas")
    e2.download_button("Excel", exportar_alertas_xlsx(df),
                       file_name="alertas_mrs.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True, key="dl_xlsx_alertas")

    # PDF via reportlab; se ausente, cai para relatório HTML imprimível (Ctrl+P)
    pdf_bytes = exportar_alertas_pdf(df, gerencia)
    if pdf_bytes:
        e3.download_button("PDF", pdf_bytes,
                           file_name="alertas_mrs.pdf", mime="application/pdf",
                           use_container_width=True, key="dl_pdf_alertas")
    else:
        e3.download_button("PDF (HTML)", exportar_alertas_relatorio_html(df, gerencia),
                           file_name="alertas_mrs.html", mime="text/html",
                           use_container_width=True, key="dl_html_alertas",
                           help="reportlab não instalado — baixa um HTML imprimível "
                                "(abra e use Ctrl+P → Salvar como PDF).")

# endregion


# region ====================== SESSÃO 5: Entrada da tela =======================

def render_alertas():
    """Ponto de entrada da tela de Alertas (rota 'alertas')."""
    require_login()  # RBAC: tela protegida — sem sessão, não renderiza
    _inject_css()
    st.markdown("## 🚨 Alertas Automáticos")
    st.caption(
        "Hot-spots crônicos (≥3 notas da mesma família em 6 meses, mesmo ramal+origem) "
        "e reincidências (reabertura ≤90 dias). Recálculo automático no upload + manual."
    )

    gerencia = _gerencia_ativa()
    pode_gerir = can_manage_alertas(gerencia)
    filtros = _barra_acoes(gerencia, pode_gerir)
    gerencia = _gerencia_ativa()          # reavalia após seletor
    pode_gerir = can_manage_alertas(gerencia)  # reavalia p/ a gerência escolhida

    if filtros["recalcular"]:
        _executar_recalculo(gerencia)

    df = get_alertas(gerencia, filtros["disciplina"])

    st.divider()
    _cartoes_resumo(df)
    st.divider()

    df_view = _filtrar(df, filtros)
    _render_lista(df_view, pode_gerir)
    st.divider()
    _botoes_export(df_view, gerencia)

# endregion
