# app.py — Ponto de entrada principal do MRS Sentinel
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
from core.versao import APP_VERSION  # módulo sem nenhuma chamada st.* — seguro importar antes do set_page_config
from core.ui_global import injetar_css_global  # CSS global responsivo (v3.6.0)

# region ====================== SESSÃO 1: Configuração da Página ======================
# ⚠️ st.set_page_config DEVE ser a PRIMEIRA chamada Streamlit — antes de qualquer OUTRA chamada st.*
st.set_page_config(
    page_title="MRS Sentinel",
    page_icon="🚂",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help":     None,
        "Report a bug": None,
        "About": (
            "**MRS Sentinel** — Plataforma de Inteligência de Manutenção da Malha\n\n"
            "MRS Logística · Gerência de Via Permanente e Obras\n\n"
            f"v{APP_VERSION}"
        ),
    }
)

# CSS global responsivo (core/ui_global.py) — idempotente, precisa rodar
# antes de qualquer tela para o CSS já valer no primeiro paint (v3.6.0).
injetar_css_global()
# endregion


# region ====================== SESSÃO 2: Imports (após set_page_config) ======================
from auth.session    import is_logged_in, init_session
from auth.login      import render_login
from modules.home    import render_sidebar
from modules.gerencia_dashboard import render_gerencia
from modules.gerencia_geral import render_gerencia_geral
from modules.admin_panel    import render_admin_panel
from modules.data_uploader  import render_upload
from modules.alertas        import render_alertas
from modules.evolucao_malha import render_evolucao_malha
from modules.visao_campo   import render_visao_campo
from modules.selecionar_gg  import render_selecionar_gg
from modules.gerencia_placeholder import render_gerencia_placeholder
from modules.modo_tv import render_modo_tv
from core.glossarios import LISTA_GERENCIAS
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

    /* ── Área de conteúdo principal (só o que a v3.6.0 não cobre) ──── */
    /* padding-top/left/right e max-width agora vêm de
       core/ui_global.py::injetar_css_global() (fonte única de
       responsividade, chamada 1x logo após set_page_config). Aqui só o
       padding inferior, que aquele CSS não define. Mantém os dois
       seletores (".main .block-container" = Streamlit antigo;
       "stMainBlockContainer" = 1.5x+) pra funcionar em qualquer versão. */
    .main .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-bottom: 3rem;
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

    /* ── Tabelas sempre com rolagem horizontal (não estouram a tela) ── */
    [data-testid="stDataFrame"], [data-testid="stTable"] { overflow-x: auto; }

    /* ═══════════════ RESPONSIVIDADE GLOBAL (Mobile First) ═══════════ */
    /* padding/max-width do container e empilhamento de st.columns() já
       ficam a cargo de core/ui_global.py::injetar_css_global() (breakpoints
       tablet<=1200px / mobile<=768px). Aqui só o que aquele CSS não cobre:
       tabs roláveis e o ajuste fino de métricas/títulos/botões/inputs. */
    /* Tablets e telas médias */
    @media (max-width: 992px) {
        /* Tabs roláveis em vez de espremidas */
        .stTabs [data-baseweb="tab-list"] {
            overflow-x: auto; flex-wrap: nowrap; -webkit-overflow-scrolling: touch;
        }
    }
    /* Celulares: ajuste fino de tipografia e alvos de toque */
    @media (max-width: 640px) {
        /* Métricas e títulos mais compactos */
        [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.25rem !important; }
        h3 { font-size: 1.1rem !important; }
        /* Alvos de toque: botões ocupam a largura e ganham altura */
        .stButton > button { width: 100% !important; min-height: 44px !important; }
        /* Inputs com altura confortável para o dedo */
        .stSelectbox, .stMultiSelect, .stNumberInput, .stTextInput { min-height: 44px; }
    }
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
        "gerencia_geral": render_gerencia_geral,
        "selecionar_gg":  render_selecionar_gg,
        "evolucao":       render_evolucao_malha,
        "campo":          render_visao_campo,
        "alertas":        render_alertas,
        "upload":         render_upload,
        "admin":          render_admin_panel,
        "modo_tv":        render_modo_tv,
    }

    if pagina in rotas:
        rotas[pagina]()
        return

    # "gerencia_<sigla>" — dashboard genérico se a sigla for conhecida
    # (modules/gerencia_dashboard.py); senão "em construção" em vez de
    # cair por engano no dashboard de outra gerência.
    if pagina.startswith("gerencia_"):
        sigla = pagina.removeprefix("gerencia_").upper()
        if sigla in LISTA_GERENCIAS:
            render_gerencia(sigla)
        else:
            render_gerencia_placeholder(sigla)
        return

    render_gerencia("SP")


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
