# auth/login.py — Tela de Login MRS Sentinel
# Design: tema claro com identidade visual MRS (azul-marinho + dourado)
# Auth: Supabase Auth (email + senha) → busca perfil na tabela 'usuarios'

import streamlit as st
from database.client import get_supabase
from database.queries import get_usuario_by_email, atualizar_ultimo_login, log_acesso
from auth.session import set_usuario, set_pagina


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

    /* Remove padding padrão para centralizar melhor */
    .main .block-container {
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
    </style>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Componentes Visuais ======================

def _render_header():
    st.html("""
    <div style="text-align:center; margin-bottom: 2rem;">
        <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2d5a8e 100%);
            width:80px;height:80px;border-radius:20px;display:flex;
            align-items:center;justify-content:center;
            margin:0 auto 1.2rem auto;">
            <span style="font-size:42px;">🚂</span>
        </div>
        <h1 style="font-size:2rem;font-weight:700;color:#1e3a5f;
            margin:0 0 0.3rem 0;">MRS Sentinel</h1>
        <p style="color:#6b7280;font-size:0.95rem;margin:0;">
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
