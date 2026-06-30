# app.py — Ponto de entrada principal do MRS Nexus
# 🚂 Plataforma de Inteligência de Manutenção da Malha MRS
# Sprint 1 — Fundação: login, RBAC, roteamento, sidebar
#
# ESTRUTURA DE ROTEAMENTO:
#   Não logado  → render_login()
#   Logado      → render_sidebar() + rota para módulo conforme st.session_state.pagina
#
# Para adicionar nova tela:
#   1. Crie o módulo em modules/nova_tela.py
#   2. Adicione o elif abaixo em _rotear()
#   3. Adicione o botão em modules/home.py → _render_nav_buttons()

import streamlit as st

# region ====================== SESSÃO 1: Configuração da Página ======================
# ⚠️ st.set_page_config DEVE ser a PRIMEIRA chamada Streamlit — antes de qualquer import
st.set_page_config(
    page_title="MRS Nexus",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help":     None,
        "Report a bug": None,
        "About": (
            "**MRS Nexus** — Plataforma de Inteligência de Manutenção da Malha\n\n"
            "MRS Logística · Gerência de Via Permanente e Obras\n\n"
            "v1.0.0 · Sprint 1 — Fundação"
        ),
    }
)
# endregion


# region ====================== SESSÃO 2: Imports (após set_page_config) ======================
from auth.session    import is_logged_in, init_session
from auth.login      import render_login
from modules.home    import render_sidebar
from modules.gerencia_sp    import render_gerencia_sp
from modules.gerencia_vp    import render_gerencia_vp
from modules.gerencia_geral import render_gerencia_geral
from modules.admin_panel    import render_admin_panel
from modules.data_uploader  import render_upload
# endregion


# region ====================== SESSÃO 3: CSS Global ======================

def _inject_global_css():
    """
    Estilos globais da aplicação.
    Separado do CSS específico de cada módulo para facilitar manutenção.
    """
    st.markdown("""
    <style>
    /* ── Fonte Inter (moderna e legível) ────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* ── Fundo da aplicação (área principal) ─────────────────────── */
    .stApp {
        background-color: #f8fafc;
    }

    /* ── Área de conteúdo principal ──────────────────────────────── */
    .main .block-container {
        padding-top:    1.5rem;
        padding-bottom: 3rem;
        max-width:      1400px;
    }

    /* ── Header nativo do Streamlit (ocultar o vermelho padrão) ─── */
    [data-testid="stHeader"] {
        background: transparent;
        border-bottom: none;
    }

    /* ── Botões primários ────────────────────────────────────────── */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 15px rgba(30,58,95,0.35) !important;
    }

    /* ── Tabs ────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab"] {
        font-weight: 500;
        font-size: 0.9rem;
        color: #6b7280;
    }
    .stTabs [aria-selected="true"] {
        color: #1e3a5f !important;
        font-weight: 600 !important;
    }

    /* ── Expanders ───────────────────────────────────────────────── */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: #374151;
    }

    /* ── Scrollbar customizada ───────────────────────────────────── */
    ::-webkit-scrollbar       { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #f1f5f9; }
    ::-webkit-scrollbar-thumb { background: #1e3a5f66; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #1e3a5f; }

    /* ── Âncoras dos headers (ocultar o ícone 🔗 nativo) ─────────── */
    h1 a, h2 a, h3 a, h4 a { display: none !important; }

    /* ── DataFrames ──────────────────────────────────────────────── */
    [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

    /* ── Alertas arredondados ────────────────────────────────────── */
    .stAlert { border-radius: 10px !important; }

    /* ── Divisor ─────────────────────────────────────────────────── */
    hr { border-color: #e5e7eb !important; margin: 0.8rem 0 !important; }
    </style>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 4: Roteador Principal ======================

def _rotear():
    """
    Determina qual módulo renderizar com base em st.session_state.pagina.
    Chamado APÓS render_sidebar() para garantir que a sidebar sempre apareça.
    """
    pagina = st.session_state.get("pagina", "gerencia_sp")

    rotas = {
        "gerencia_sp":    render_gerencia_sp,
        "gerencia_vp":    render_gerencia_vp,
        "gerencia_geral": render_gerencia_geral,
        "upload":         render_upload,
        "admin":          render_admin_panel,
    }

    render_fn = rotas.get(pagina, render_gerencia_sp)
    render_fn()


def main():
    """
    Ponto de entrada principal.
    Ordem: CSS → init estado → auth check → sidebar (se logado) → roteamento
    """
    _inject_global_css()
    init_session()

    if not is_logged_in():
        render_login()
    else:
        render_sidebar()
        _rotear()


# endregion


# region ====================== SESSÃO 5: Execução ======================
if __name__ == "__main__":
    main()
# endregion
