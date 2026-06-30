# modules/gerencia_geral.py — Tela de Visão Geral (multi-gerencial)
# Sprint 1: placeholder com roadmap visual.
# Sprint 4: conteúdo real cruzando SP + VP (IMT, DI, Unifilar Tridisciplinar).

import streamlit as st
from auth.permissions import require_login
from database.queries import get_contagem_notas_por_gerencia


# region ====================== SESSÃO 1: Header ======================

def _render_header():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("""
        <div style="margin-bottom: 0.5rem;">
            <span style="font-size:0.8rem; color:#6b7280; font-weight:500;
                         text-transform:uppercase; letter-spacing:1px;">
                CONSOLIDADO MULTI-GERENCIAL
            </span>
            <h1 style="font-size:1.9rem; font-weight:700; color:#1e3a5f;
                        margin:4px 0 0 0; line-height:1.2;">
                🌐 Visão Geral da Malha
            </h1>
            <p style="color:#6b7280; font-size:0.92rem; margin:6px 0 0 0;">
                Gerência SP + VP · Via Permanente e Eletroeletrônica
            </p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, #fce7f3, #fbcfe8);
            border: 1px solid #ec4899;
            border-radius: 10px; padding: 10px 14px; text-align:center;
            margin-top: 10px;
        ">
            <div style="font-size:0.7rem; color:#9d174d; font-weight:600;
                         text-transform:uppercase;">STATUS</div>
            <div style="font-size:1rem; font-weight:700; color:#be185d; margin-top:2px;">
                🚧 Sprint 4
            </div>
            <div style="font-size:0.72rem; color:#9d174d;">Pós MVP</div>
        </div>
        """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Cards de Contagem por Gerência ======================

def _render_cards_contagem():
    """
    Mostra contagem de notas por gerência consultando o banco.
    Sprint 2+: números reais aparecem aqui automaticamente.
    """
    contagem = get_contagem_notas_por_gerencia()

    st.markdown("""
    <p style='font-size:0.8rem; color:#9ca3af; text-transform:uppercase;
               letter-spacing:1px; font-weight:600; margin: 1.5rem 0 0.8rem 0;'>
        Consolidado da Plataforma
    </p>
    """, unsafe_allow_html=True)

    cols = st.columns(4)
    total = contagem["SP"] + contagem["VP"]

    cards = [
        ("🏭", "Gerência SP",    f"{contagem['SP']:,}".replace(",", "."), "#1e3a5f", "notas carregadas"),
        ("🏭", "Gerência VP",    f"{contagem['VP']:,}".replace(",", "."), "#0891b2", "notas carregadas"),
        ("🌐", "Total Plataforma", f"{total:,}".replace(",", "."),        "#16a34a", "notas consolidadas"),
        ("⏰", "Atualização",    "—",                                     "#f59e0b", "Em tempo real"),
    ]

    for i, (ico, titulo, valor, cor, sub) in enumerate(cards):
        with cols[i]:
            st.markdown(f"""
            <div style="
                background:white; border:1px solid #e5e7eb;
                border-top:3px solid {cor}; border-radius:12px;
                padding:16px; box-shadow:0 2px 8px rgba(0,0,0,0.04);
                text-align:center; min-height:110px;
                display:flex; flex-direction:column; justify-content:center;
            ">
                <div style="font-size:1.6rem; margin-bottom:4px;">{ico}</div>
                <div style="font-size:0.75rem; color:#6b7280; font-weight:500;
                             text-transform:uppercase; letter-spacing:0.5px;">{titulo}</div>
                <div style="font-size:1.6rem; font-weight:700; color:{cor}; margin:4px 0 2px 0;">
                    {valor if valor != "0" else "—"}
                </div>
                <div style="font-size:0.72rem; color:#9ca3af;">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 3: Roadmap Visual ======================

def _render_roadmap_visao_geral():
    """Mostra o que será construído nesta tela na Sprint 4."""
        # Bloco roadmap
    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
    grid_html = "".join([
        f"""<div style="background:white; border-radius:10px; padding:12px 14px;
            border:1px solid #bbf7d0;">
            <div style="font-size:0.75rem; font-weight:600; color:#15803d;
                text-transform:uppercase; margin-bottom:4px;">{titulo}</div>
            <div style="font-size:0.82rem; color:#4b5563;">{desc}</div>
        </div>"""
        for titulo, desc in [
            ("IMT Consolidado",       "Indice de Manutencao Total cruzando SP e VP"),
            ("DI Integrado",          "Desempenho Integrado das disciplinas VP+EE"),
            ("Unifilar Tridisciplinar","VP + EE + Sinalizacao no mesmo mapa"),
            ("Mapa Geografico",       "Bolhas KMZ sobre tracado real da malha"),
            ("Alertas Criticos",      "Hot-spots cronicos das duas gerencias"),
            ("Comparativo Mensal",    "SP x VP lado a lado por periodo"),
        ]
    ])
    st.html(f"""
    <div style="background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);
        border:2px dashed #16a34a44; border-radius:16px; padding:2.5rem; text-align:center;">
        <div style="font-size:3rem; margin-bottom:1rem;">&#127760;</div>
        <h2 style="font-size:1.4rem; font-weight:700; color:#15803d; margin:0 0 0.5rem 0;">
            Visao Geral - Em construcao (Sprint 4)
        </h2>
        <p style="color:#6b7280; font-size:0.95rem; max-width:560px; margin:0 auto 1.5rem auto;">
            A Visao Geral cruzara dados das duas gerencias para dar ao Gerente Geral
            uma perspectiva unificada de toda a malha MRS.
        </p>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;
            max-width:480px; margin:0 auto; text-align:left;">
            {grid_html}
        </div>
    </div>
    """)
    
# endregion


# region ====================== SESSÃO 4: Renderização Principal ======================

def render_gerencia_geral():
    """Ponto de entrada: renderiza a tela de Visão Geral."""
    require_login()

    _render_header()
    st.divider()
    _render_cards_contagem()
    _render_roadmap_visao_geral()

# endregion
