# modules/gerencia_sp.py — Tela da Gerência SP
# Sprint 1: placeholder com identidade visual completa.
# Sprint 3: substituir _render_placeholder() pelo conteúdo real (VP + EE).

import streamlit as st
from auth.permissions import require_login, can_see_gerencia, can_upload
from auth.session import get_perfil


# region ====================== SESSÃO 1: Header da Gerência ======================

def _render_header():
    """Cabeçalho da gerência com título e badges de status."""
    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown("""
        <div style="margin-bottom: 0.5rem;">
            <span style="font-size:0.8rem; color:#6b7280; font-weight:500;
                         text-transform:uppercase; letter-spacing:1px;">
                GERÊNCIA DE VIA PERMANENTE E OBRAS
            </span>
            <h1 style="font-size:1.9rem; font-weight:700; color:#1e3a5f;
                        margin:4px 0 0 0; line-height:1.2;">
                🏭 Gerência SP
            </h1>
            <p style="color:#6b7280; font-size:0.92rem; margin:6px 0 0 0;">
                São Paulo · Centros: CIPA · CIPG · CIJN
            </p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        # Badge de status da sprint
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, #fef9c3, #fef08a);
            border: 1px solid #f59e0b;
            border-radius: 10px; padding: 10px 14px; text-align:center;
            margin-top: 10px;
        ">
            <div style="font-size:0.7rem; color:#92400e; font-weight:600;
                         text-transform:uppercase; letter-spacing:0.5px;">
                STATUS
            </div>
            <div style="font-size:1rem; font-weight:700; color:#b45309; margin-top:2px;">
                🚧 Sprint 3
            </div>
            <div style="font-size:0.72rem; color:#92400e;">Em desenvolvimento</div>
        </div>
        """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Toggle VP / EE ======================

def _render_toggle_disciplina() -> str:
    """Seletor de disciplina VP / EE / Ambas. Retorna a seleção."""
    st.markdown("<div style='margin: 1rem 0 0.5rem 0;'></div>", unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([1, 1, 1, 4])

    with col1:
        vp = st.button("🛤️ Via Permanente", key="sp_disc_vp", use_container_width=True)
    with col2:
        ee = st.button("⚡ Eletroeletrônica", key="sp_disc_ee", use_container_width=True)
    with col3:
        amb = st.button("🔗 VP + EE", key="sp_disc_amb", use_container_width=True)

    # Mantém estado da seleção
    if vp:
        st.session_state["sp_disciplina"] = "VP"
    elif ee:
        st.session_state["sp_disciplina"] = "EE"
    elif amb:
        st.session_state["sp_disciplina"] = "AMBAS"

    return st.session_state.get("sp_disciplina", "VP")

# endregion


# region ====================== SESSÃO 3: Placeholder (Sprint 1) ======================

def _render_placeholder(disciplina: str):
    """
    Placeholder visual para Sprint 1.
    Substituir pelo conteúdo real na Sprint 3.
    """
    disc_nome = {"VP": "Via Permanente", "EE": "Eletroeletrônica", "AMBAS": "VP + EE"}
    disc_cor  = {"VP": "#1e3a5f",        "EE": "#7c3aed",          "AMBAS": "#0891b2"}
    disc_ico  = {"VP": "🛤️",             "EE": "⚡",               "AMBAS": "🔗"}

    nome = disc_nome.get(disciplina, disciplina)
    cor  = disc_cor.get(disciplina, "#1e3a5f")
    ico  = disc_ico.get(disciplina, "📊")

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

    # KPIs mockados (4 cards)
    st.markdown("""
    <p style='font-size:0.8rem; color:#9ca3af; text-transform:uppercase;
               letter-spacing:1px; font-weight:600; margin-bottom:0.8rem;'>
        KPIs — Aguardando dados (Sprint 2)
    </p>
    """, unsafe_allow_html=True)

    kpis = [
        ("📋", "Total de Notas",      "—",     "Será carregado via upload"),
        ("🚨", "Prioridade 1+2",      "—",     "Críticos + Muito Altos"),
        ("⏱️", "Lead Time Médio",     "— dias", "Notas abertas"),
        ("📍", "Hot-spot Principal",   "—",     "Ramal mais crítico"),
    ]

    cols = st.columns(4)
    for i, (ico_k, titulo, valor, subtitulo) in enumerate(kpis):
        with cols[i]:
            st.markdown(f"""
            <div style="
                background: white; border: 1px solid #e5e7eb;
                border-top: 3px solid {cor};
                border-radius: 12px; padding: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.04);
                text-align: center; min-height: 110px;
                display: flex; flex-direction: column; justify-content: center;
            ">
                <div style="font-size:1.6rem; margin-bottom:4px;">{ico_k}</div>
                <div style="font-size:0.75rem; color:#6b7280; font-weight:500;
                             text-transform:uppercase; letter-spacing:0.5px;">
                    {titulo}
                </div>
                <div style="font-size:1.6rem; font-weight:700; color:{cor}; margin:4px 0 2px 0;">
                    {valor}
                </div>
                <div style="font-size:0.72rem; color:#9ca3af;">{subtitulo}</div>
            </div>
            """, unsafe_allow_html=True)

        # Bloco central "em construção"
    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
    checklist_html = "".join([
        f'<div style="font-size:0.83rem; color:#6b7280; padding:2px 0;">&#9744; {el}</div>'
        for el in [
            "Unifilar Dual (ECharts effectScatter)",
            "Heatmap Pátio x Familia",
            "KPIs Premium com Sparklines",
            "Score Composto (4 fatores)",
            "Ranking Hot-spots",
            "Serie Temporal (6 dimensoes)",
            "Planejado x Realizado",
            "Aba Gerencial (9 elementos)",
            "Filtros em cascata hierarquica",
        ]
    ])
    st.html(f"""
    <div style="background:linear-gradient(135deg,{cor}08 0%,{cor}04 100%);
        border:2px dashed {cor}30; border-radius:16px;
        padding:3rem 2rem; text-align:center;">
        <div style="font-size:3rem; margin-bottom:1rem;">{ico}</div>
        <h2 style="font-size:1.4rem; font-weight:700; color:{cor}; margin:0 0 0.5rem 0;">
            {nome} - Gerencia SP
        </h2>
        <p style="color:#6b7280; font-size:0.95rem; max-width:500px; margin:0 auto 1.5rem auto;">
            Este modulo sera ativado na Sprint 3, com todos os 9 elementos gerenciais:
            Unifilar Dual, Heatmap, KPIs, Score, Ranking e Serie Temporal.
        </p>
        <div style="display:inline-block; text-align:left; background:white;
            border-radius:12px; padding:16px 20px; border:1px solid #e5e7eb;">
            <div style="font-size:0.82rem; color:#374151; font-weight:600;
                margin-bottom:8px; text-transform:uppercase; letter-spacing:0.5px;">
                Elementos previstos
            </div>
            {checklist_html}
        </div>
    </div>
    """)


    # Box de upload (se tiver permissão) — já prepara o usuário para Sprint 2
    if can_upload("SP"):
        st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
        st.info(
            "📤 **Upload de dados** estará disponível na **Sprint 2**. "
            "Você tem permissão para alimentar a Gerência SP.",
            icon="ℹ️"
        )

# endregion


# region ====================== SESSÃO 4: Renderização Principal ======================

def render_gerencia_sp():
    """Ponto de entrada: renderiza a tela da Gerência SP."""
    require_login()

    # Proteção: assistente VP não pode ver SP
    if not can_see_gerencia("SP"):
        st.error("🚫 Você não tem acesso à Gerência SP.")
        st.stop()

    _render_header()
    st.divider()

    disciplina = _render_toggle_disciplina()
    _render_placeholder(disciplina)

# endregion
