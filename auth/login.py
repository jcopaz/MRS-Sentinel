# auth/login.py — Tela de Login MRS Sentinel
# Design: tema claro com identidade visual MRS (azul-marinho + dourado)
# Auth: Supabase Auth (email + senha) → busca perfil na tabela 'usuarios'

from pathlib import Path

import streamlit as st
from database.client import get_supabase
from database.queries import get_usuario_by_email, atualizar_ultimo_login, log_acesso
from auth.session import set_usuario, set_pagina

# Logo animado — mp4 em vez de gif (mesmo conteúdo, muito mais leve: H.264
# comprime bem melhor que a paleta do GIF). Servido via static file serving
# do Streamlit (ver .streamlit/config.toml -> enableStaticServing) a partir
# de static/, pasta irmã de app.py na raiz do repo — por isso dois caminhos:
# um absoluto (checagem de existência em disco) e um relativo (URL do <video>).
LOGO_VIDEO_PATH = Path(__file__).resolve().parent.parent / "static" / "Sentinel_logo.mp4"
LOGO_VIDEO_URL = "app/static/Sentinel_logo.mp4"
LOGO_WIDTH = 240  # px — mesmo tamanho usado na sidebar (modules/home.py)


# region ====================== SESSÃO 1: CSS da Tela de Login ======================

def _inject_login_css():
    st.markdown("""
    <style>
    /* Remove sidebar na tela de login */
    [data-testid="stSidebar"] { display: none !important; }

    /* Fundo com gradiente suave */
    .stApp {
        background: linear-gradient(135deg, #f0f4f8 0%, #e8eef5 50%, #dde6f0 100%);
    }

    /* Remove padding padrão para centralizar melhor.
       ⚠️ ".main .block-container" é seletor de versões antigas do Streamlit
       — a partir do 1.5x o container principal usa data-testid
       "stMainBlockContainer" (sem a classe "main" como ancestral). Sem essa
       segunda regra, nada aqui era aplicado e a tela renderizava em largura
       total, "descentralizando" a logo (que fica alinhada à esquerda por
       padrão) em relação ao texto (centralizado via text-align próprio). */
    .main .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-top: 4rem !important;
        max-width: 460px !important;
        margin: 0 auto !important;
    }

    /* Inputs com estilo limpo */
    .stTextInput > div > div > input {
        border-radius: 8px !important;
        border: 1.5px solid #d1d5db !important;
        padding: 10px 14px !important;
        font-size: 15px !important;
        transition: border-color 0.2s ease;
    }
    .stTextInput > div > div > input:focus {
        border-color: #1e3a5f !important;
        box-shadow: 0 0 0 3px rgba(30,58,95,0.1) !important;
    }

    /* Botão entrar */
    div[data-testid="stForm"] .stButton > button {
        width: 100%;
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a8e 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 12px !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        letter-spacing: 0.5px;
        transition: all 0.2s ease;
        cursor: pointer;
    }
    div[data-testid="stForm"] .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(30,58,95,0.35) !important;
    }

    /* Logo em vídeo — centralizado direto no HTML (ver _render_header), não
       precisa de regra aqui: é um <div style="text-align:center"> escrito à
       mão, sem depender de testid interno do Streamlit (que muda de versão
       pra versão — foi o que quebrou a centralização do st.image antes). */

    /* Texto "SENTINEL" em dourado 3D reluzente — cor sólida + relevo nítido
       (sombras SEM blur, só deslocadas — nada de "0 0 Xpx", que é o que cria
       o halo/glow espalhado atrás da palavra). O brilho vem só de um pulso
       de brightness() no próprio texto, não de sombra difusa. */
    .sentinel-gold-3d {
        font-family: 'Arial Black', Arial, sans-serif;
        font-weight: 900;
        letter-spacing: 0.14em;
        text-align: center;
        line-height: 1.1;
        color: #e8a920;
        text-shadow:
            0 1px 0 #8a6314,
            0 2px 0 #7a5610,
            0 3px 2px rgba(0,0,0,.30);
        animation: sentinelShimmer 2.8s ease-in-out infinite;
    }
    .sentinel-gold-3d.lg { font-size: 2.6rem; margin-top: -0.4rem; }
    .sentinel-gold-3d.sm { font-size: 1.35rem; }
    @keyframes sentinelShimmer {
        0%, 100% { filter: brightness(1); }
        50%      { filter: brightness(1.22); }
    }
    </style>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Componentes Visuais ======================

def _render_header():
    if LOGO_VIDEO_PATH.exists():
        st.html(f"""
        <div style="text-align:center;">
            <video autoplay loop muted playsinline
                style="width:{LOGO_WIDTH}px;max-width:100%;display:inline-block;">
                <source src="{LOGO_VIDEO_URL}" type="video/mp4">
            </video>
        </div>
        """)
    else:
        st.markdown(
            "<div style='text-align:center;color:#dc2626;font-size:0.85rem;'>"
            "⚠️ Logo não encontrado (static/Sentinel_logo.mp4)</div>",
            unsafe_allow_html=True,
        )

    st.html("""
    <div style="text-align:center; margin-bottom: 2rem;">
        <div class="sentinel-gold-3d lg">SENTINEL</div>
        <p style="color:#6b7280;font-size:0.95rem;margin:0.4rem 0 0;">
            Plataforma de Inteligência de Manutenção da Malha</p>
        <div style="width:60px;height:3px;
            background:linear-gradient(90deg,#ffb000,#ffd04d);
            border-radius:2px;margin:1rem auto 0 auto;"></div>
    </div>
    """)

def _render_card_inicio():
    st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)

def _render_card_fim():
    pass

def _render_footer():
    try:
        versao = st.secrets.get("app", {}).get("versao", "1.0.0")
    except Exception:
        versao = "1.0.0"
    html = f"""<div style="text-align:center;margin-top:2rem;color:#9ca3af;font-size:0.8rem;">
        MRS Logística &nbsp;&bull;&nbsp; v{versao} &nbsp;&bull;&nbsp; Via Permanente
    </div>"""
    try:
        st.html(html)
    except AttributeError:
        st.markdown(html, unsafe_allow_html=True)


# endregion


# region ====================== SESSÃO 3: Lógica de Autenticação ======================

def _autenticar(email: str, senha: str) -> tuple[bool, str]:
    """
    Autentica o usuário via Supabase Auth, depois busca o perfil
    na tabela 'usuarios'. Retorna (sucesso, mensagem_erro).

    Fluxo:
    1. sign_in_with_password → valida credenciais no Supabase Auth
    2. get_usuario_by_email  → busca perfil (perfil, gerencia, ativo)
    3. Salva na session      → set_usuario()
    4. Registra log e atualiza último_login
    """
    # Passo 1: autenticar via Supabase Auth
    try:
        supabase = get_supabase()
        auth_resp = supabase.auth.sign_in_with_password({
            "email": email.strip().lower(),
            "password": senha,
        })
        if not auth_resp.user:
            return False, "Email ou senha incorretos."
    except Exception as e:
        err = str(e).lower()
        if "invalid" in err or "credentials" in err:
            return False, "Email ou senha incorretos."
        return False, f"Erro de conexão: verifique sua internet."

    # Passo 2: buscar perfil na tabela usuarios
    usuario = get_usuario_by_email(email.strip().lower())
    if not usuario:
        # Existe no Auth mas não tem perfil cadastrado (ou está inativo)
        supabase.auth.sign_out()
        return False, "Usuário sem perfil ativo. Contate o administrador."

    # Passo 3: salvar na sessão e navegar para home
    set_usuario(usuario)

    # Decide para qual gerência redirecionar por padrão
    gerencia = usuario.get("gerencia")
    if gerencia == "SP":
        set_pagina("gerencia_sp")
    elif gerencia == "VP":
        set_pagina("gerencia_vp")
    else:
        set_pagina("gerencia_sp")  # Admin começa pela SP

    # Passo 4: auditoria (falha silenciosa)
    atualizar_ultimo_login(usuario["id"])
    log_acesso(usuario["id"], "login", {"email": email})

    return True, ""

# endregion


# region ====================== SESSÃO 4: Renderização Principal ======================

def render_login():
    """Ponto de entrada: renderiza a tela de login completa."""
    _inject_login_css()
    _render_header()
    _render_card_inicio()

    with st.form("form_login", clear_on_submit=False):
        st.markdown(
            "<p style='color:#374151; font-weight:600; margin-bottom:0.3rem;'>E-mail corporativo</p>",
            unsafe_allow_html=True
        )
        email = st.text_input(
            "Email",
            placeholder="seu.nome@mrs.com.br",
            label_visibility="collapsed",
        )

        st.markdown(
            "<p style='color:#374151; font-weight:600; margin-bottom:0.3rem; margin-top:0.8rem;'>Senha</p>",
            unsafe_allow_html=True
        )
        senha = st.text_input(
            "Senha",
            type="password",
            placeholder="••••••••",
            label_visibility="collapsed",
        )

        st.markdown("<div style='margin-top:1.2rem;'></div>", unsafe_allow_html=True)
        entrar = st.form_submit_button("🔐  Entrar", use_container_width=True)

        if entrar:
            # Validação básica antes de chamar a API
            if not email or not email.strip():
                st.error("⚠️ Informe o e-mail.")
            elif "@" not in email:
                st.error("⚠️ E-mail inválido.")
            elif not senha:
                st.error("⚠️ Informe a senha.")
            else:
                with st.spinner("Autenticando..."):
                    sucesso, msg_erro = _autenticar(email, senha)

                if sucesso:
                    st.success("✅ Acesso autorizado!")
                    st.rerun()
                else:
                    st.error(f"❌ {msg_erro}")

    _render_card_fim()
    _render_footer()

# endregion
