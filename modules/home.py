# modules/home.py — Sidebar de navegação (renderizado após login)
# A sidebar é a "espinha dorsal" da navegação. Persiste em todas as telas.
# Contém: logo, usuário ativo, botões de gerência, card última atualização, logout.

from pathlib import Path

import streamlit as st
from auth.session import get_nome, get_perfil, get_gerencia, set_pagina, get_pagina, clear_session, get_id
from auth.permissions import can_see_gerencia, can_admin_panel, can_upload
from database.queries import log_acesso, contar_alertas_novos

# Logo animado — mp4 em vez de gif (mesmo conteúdo, muito mais leve: H.264
# comprime bem melhor que a paleta do GIF). Servido via static file serving
# do Streamlit (ver .streamlit/config.toml -> enableStaticServing) a partir
# de static/, pasta irmã de app.py na raiz do repo — por isso dois caminhos:
# um absoluto (checagem de existência em disco) e um relativo (URL do <video>).
LOGO_VIDEO_PATH = Path(__file__).resolve().parent.parent / "static" / "Sentinel_logo.mp4"
LOGO_VIDEO_URL = "app/static/Sentinel_logo.mp4"
LOGO_WIDTH = 240  # px — mesmo tamanho usado na tela de Login (auth/login.py)


# region ====================== SESSÃO 1: CSS da Sidebar ======================

def _inject_sidebar_css():
    """CSS para estilizar a sidebar com identidade MRS."""
    st.markdown("""
    <style>
    /* Fundo navy da sidebar */
    [data-testid="stSidebar"] > div:first-child {
        background: linear-gradient(180deg, #1e3a5f 0%, #16304f 60%, #0f2338 100%);
        padding: 0;
    }

    /* Logo em vídeo — centralizado direto no HTML (ver _render_logo), não
       precisa de regra aqui: é um <div style="text-align:center"> escrito à
       mão, sem depender de testid interno do Streamlit (que muda de versão
       pra versão — foi o que quebrou a centralização do st.image antes).
       Só o respiro em relação à borda da sidebar continua aqui. */
    [data-testid="stSidebar"] .sentinel-logo-wrap {
        padding: 1.2rem 0 0 0;
    }

    /* Todos os textos na sidebar ficam brancos */
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div {
        color: #ffffff !important;
    }

    /* Botões da sidebar — estilo ghost */
    [data-testid="stSidebar"] .stButton > button {
        background: transparent !important;
        color: #d1d5db !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 10px !important;
        text-align: left !important;
        padding: 10px 16px !important;
        font-size: 14px !important;
        width: 100% !important;
        transition: all 0.2s ease !important;
        margin-bottom: 4px;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(255,255,255,0.12) !important;
        border-color: rgba(255,255,255,0.35) !important;
        color: #ffffff !important;
        transform: translateX(3px);
    }

    /* Divisor */
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.12) !important;
        margin: 12px 0 !important;
    }

    /* Texto "SENTINEL" em dourado 3D reluzente — cor sólida + relevo nítido
       (sombras SEM blur, só deslocadas — nada de "0 0 Xpx", que é o que cria
       o halo/glow espalhado atrás da palavra). O brilho vem só de um pulso
       de brightness() no próprio texto, não de sombra difusa. Seletor com
       prefixo [data-testid="stSidebar"] pra vencer em especificidade a
       regra genérica "div{color:#fff!important}" acima. */
    [data-testid="stSidebar"] .sentinel-gold-3d {
        font-family: 'Arial Black', Arial, sans-serif;
        font-weight: 900 !important;
        letter-spacing: 0.14em;
        text-align: center;
        line-height: 1.1;
        color: #e8a920 !important;
        text-shadow:
            0 1px 0 #8a6314,
            0 2px 0 #7a5610,
            0 3px 2px rgba(0,0,0,.30);
        animation: sentinelShimmer 2.8s ease-in-out infinite;
    }
    [data-testid="stSidebar"] .sentinel-gold-3d.sm { font-size: 1.35rem; }
    @keyframes sentinelShimmer {
        0%, 100% { filter: brightness(1); }
        50%      { filter: brightness(1.22); }
    }
    </style>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Componentes da Sidebar ======================

def _render_logo():
    """Logo animado + nome do app no topo da sidebar."""
    if LOGO_VIDEO_PATH.exists():
        st.sidebar.html(f"""
        <div class="sentinel-logo-wrap" style="text-align:center;">
            <video autoplay loop muted playsinline
                style="width:{LOGO_WIDTH}px;max-width:100%;display:inline-block;">
                <source src="{LOGO_VIDEO_URL}" type="video/mp4">
            </video>
        </div>
        """)
    else:
        st.sidebar.markdown(
            "<div style='text-align:center;color:#f87171;font-size:0.75rem;padding-top:1rem;'>"
            "⚠️ Logo não encontrado (static/Sentinel_logo.mp4)</div>",
            unsafe_allow_html=True,
        )

    st.sidebar.markdown("""
    <div style="padding: 0.3rem 1rem 1rem 1rem; text-align: center;">
        <div class="sentinel-gold-3d sm">SENTINEL</div>
        <div style="font-size:0.72rem; color:rgba(255,255,255,0.5); margin-top:4px; letter-spacing:0.3px;">
            INTELIGÊNCIA DE MANUTENÇÃO
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_usuario_badge():
    """Card do usuário logado com perfil e gerência."""
    nome    = get_nome()
    perfil  = get_perfil()
    gerencia = get_gerencia()

    # Ícone e cor por perfil
    perfil_cfg = {
        "admin":      ("👑", "#fbbf24", "Admin"),
        "assistente": ("🔧", "#60a5fa", "Assistente"),
        "usuario":    ("👤", "#a3e635", "Usuário"),
    }
    icone, cor, label = perfil_cfg.get(perfil, ("👤", "#a3e635", perfil or "?"))
    ger_txt = f" · Ger. {gerencia}" if gerencia else " · Global"

    st.sidebar.markdown(f"""
    <div style="
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 10px;
        padding: 10px 12px;
        margin: 0 1rem 1rem 1rem;
    ">
        <div style="font-size:0.8rem; color:rgba(255,255,255,0.6); margin-bottom:3px;">
            {icone} {label}{ger_txt}
        </div>
        <div style="font-size:0.92rem; font-weight:600; color:#ffffff;
                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            {nome}
        </div>
        <div style="
            display:inline-block;
            background:{cor}22; border:1px solid {cor}55;
            border-radius:20px; padding:1px 8px;
            font-size:0.7rem; color:{cor}; margin-top:4px;
        ">● Online</div>
    </div>
    """, unsafe_allow_html=True)


def _render_nav_buttons():
    """Botões de navegação entre gerências."""
    pagina_atual = get_pagina()

    st.sidebar.markdown(
        "<div style='padding:0 1rem; margin-bottom:6px;'>"
        "<span style='font-size:0.7rem; color:rgba(255,255,255,0.4); "
        "letter-spacing:1px; text-transform:uppercase;'>NAVEGAÇÃO</span></div>",
        unsafe_allow_html=True
    )

    # Define os botões disponíveis com base nas permissões
    nav_items = []

    if can_see_gerencia("SP"):
        ativo_sp = "🔵 " if pagina_atual == "gerencia_sp" else ""
        nav_items.append(("SP", f"{ativo_sp}🏭  Gerência SP", "gerencia_sp"))

    if can_see_gerencia("VP"):
        ativo_vp = "🔵 " if pagina_atual == "gerencia_vp" else ""
        nav_items.append(("VP", f"{ativo_vp}🏭  Gerência VP", "gerencia_vp"))

    # Visão Geral: todos podem ver
    ativo_geral = "🔵 " if pagina_atual == "gerencia_geral" else ""
    nav_items.append(("GERAL", f"{ativo_geral}🌐  Visão Geral", "gerencia_geral"))

    # Alertas: todos podem ver — badge com contagem de novos
    ativo_alertas = "🔵 " if pagina_atual == "alertas" else ""
    try:
        n_novos = contar_alertas_novos(get_gerencia())
    except Exception:
        n_novos = 0
    badge = f"  ({n_novos})" if n_novos else ""
    nav_items.append(("ALERTAS", f"{ativo_alertas}🚨  Alertas{badge}", "alertas"))

    # Upload: admin e assistente
    gerencia_usr = get_gerencia()
    gerencia_upload = gerencia_usr or "SP"
    if can_upload(gerencia_upload) or get_perfil() == "admin":
        ativo_upload = "🔵 " if pagina_atual == "upload" else ""
        nav_items.append(("UPLOAD", f"{ativo_upload}📤  Upload de Dados", "upload"))

    # Admin Panel: somente admin
    if can_admin_panel():
        ativo_admin = "🔵 " if pagina_atual == "admin" else ""
        nav_items.append(("ADMIN", f"{ativo_admin}⚙️  Administração", "admin"))

    # Renderiza os botões
    with st.sidebar:
        for _, label, pagina_destino in nav_items:
            if st.button(label, key=f"nav_{pagina_destino}", use_container_width=True):
                set_pagina(pagina_destino)
                uid = get_id()
                if uid:
                    log_acesso(uid, f"view_{pagina_destino}")
                st.rerun()


def _render_ultima_atualizacao():
    """Card de 'última atualização' consultando o banco."""
    from datetime import datetime

    st.sidebar.markdown("<br>", unsafe_allow_html=True)
    st.sidebar.markdown(
        "<div style='padding:0 1rem; margin-bottom:6px;'>"
        "<span style='font-size:0.7rem; color:rgba(255,255,255,0.4); "
        "letter-spacing:1px; text-transform:uppercase;'>ÚLTIMA ATUALIZAÇÃO</span></div>",
        unsafe_allow_html=True
    )

    from database.queries import get_ultima_atualizacao_info
    ultimo = get_ultima_atualizacao_info()


    if not ultimo:
        st.sidebar.markdown("""
        <div style="
            background: rgba(255,255,255,0.05);
            border: 1px dashed rgba(255,255,255,0.2);
            border-radius: 10px; padding: 12px 14px; margin: 0 1rem;
            font-size:0.82rem; color:rgba(255,255,255,0.45); text-align:center;
        ">
            📭 Sem dados carregados ainda
        </div>
        """, unsafe_allow_html=True)
        return

    # Formata a data de envio
    try:
        dt = datetime.fromisoformat(ultimo["enviado_em"].replace("Z", "+00:00"))
        data_fmt = dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        data_fmt = "—"

    gerencia  = ultimo.get("gerencia", "?")
    disciplina = ultimo.get("disciplina", "?")
    total     = f"{ultimo.get('total_notas', 0):,}".replace(",", ".")

    st.sidebar.markdown(f"""
    <div style="
        background: rgba(255,176,0,0.08);
        border: 1px solid rgba(255,176,0,0.25);
        border-radius: 10px; padding: 12px 14px; margin: 0 1rem;
    ">
        <div style="font-size:0.78rem; color:#ffb000; font-weight:600; margin-bottom:4px;">
            Ger. {gerencia} — {disciplina}
        </div>
        <div style="font-size:0.82rem; color:rgba(255,255,255,0.7);">
            {data_fmt}
        </div>
        <div style="font-size:0.78rem; color:rgba(255,255,255,0.5); margin-top:2px;">
            {total} notas carregadas
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_logout():
    """Botão de logout no fundo da sidebar."""
    st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
    st.sidebar.divider()

    with st.sidebar:
        if st.button("🚪  Sair", key="btn_logout", use_container_width=True):
            uid = get_id()
            if uid:
                log_acesso(uid, "logout")
            # Faz signout no Supabase Auth
            try:
                from database.client import get_supabase
                get_supabase().auth.sign_out()
            except Exception:
                pass
            clear_session()
            st.rerun()

    # Versão no rodapé
    versao = st.secrets.get("app", {}).get("versao", "1.0.0")
    st.sidebar.markdown(
        f"<div style='text-align:center; padding:0.5rem; "
        f"font-size:0.7rem; color:rgba(255,255,255,0.25);'>v{versao}</div>",
        unsafe_allow_html=True
    )

# endregion


# region ====================== SESSÃO 3: Renderização Principal ======================

def render_sidebar():
    """
    Ponto de entrada: renderiza a sidebar completa.
    Deve ser chamado ANTES de renderizar o conteúdo da página.
    """
    _inject_sidebar_css()
    _render_logo()
    _render_usuario_badge()
    _render_nav_buttons()
    _render_ultima_atualizacao()
    _render_logout()

# endregion
