# auth/login.py — Tela de Login MRS Sentinel
# Design: tema claro com identidade visual MRS (azul-marinho + dourado)
# Auth: Supabase Auth (email + senha) → busca perfil na tabela 'usuarios'

from pathlib import Path

import streamlit as st
from database.client import criar_cliente_auth_temporario
from database.queries import (
    get_usuario_by_email,
    get_usuario_by_matricula,
    atualizar_ultimo_login,
    log_acesso,
)
from auth.session import set_usuario, set_pagina
from core.versao import APP_VERSION

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

    /* Fundo escuro */
    .stApp {
        background: #1b2130;
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
        <p style="color:#ffffff;font-size:0.95rem;margin:0.4rem 0 0;">
            Plataforma de Inteligência de Manutenção da Malha</p>
        <div style="color:rgba(255,255,255,0.45);font-size:0.75rem;margin-top:0.35rem;letter-spacing:0.5px;">
            v""" + APP_VERSION + """</div>
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
    # Versão vem só de core/versao.py — sem fallback pra secrets.toml, pra
    # não correr o risco de mostrar um número desatualizado que ninguém
    # lembrou de sincronizar com o código de verdade.
    html = f"""<div style="text-align:center;margin-top:2rem;color:#9ca3af;font-size:0.8rem;">
        MRS Logística &nbsp;&bull;&nbsp; v{APP_VERSION} &nbsp;&bull;&nbsp; Via Permanente
    </div>"""
    try:
        st.html(html)
    except AttributeError:
        st.markdown(html, unsafe_allow_html=True)


# endregion


# region ====================== SESSÃO 3: Lógica de Autenticação ======================

def _autenticar(identificador: str, senha: str) -> tuple[bool, str]:
    """
    Autentica o usuário via Supabase Auth, depois busca o perfil
    na tabela 'usuarios'. Retorna (sucesso, mensagem_erro).

    Login aceita MATRÍCULA ou e-mail no mesmo campo (não há SMTP
    disponível pra recuperação de senha, então nem todo colaborador tem
    e-mail corporativo real — quem não tem loga pela matrícula, e o
    e-mail usado por baixo dos panos no Supabase Auth é sintético, gerado
    em modules/admin_panel.py na criação da conta).

    Fluxo:
    1. Resolve o perfil primeiro (por matrícula ou e-mail) — descobre qual
       e-mail está registrado no Supabase Auth para essa conta.
    2. sign_in_with_password → valida a senha no Supabase Auth.
    3. Salva na session      → set_usuario()
    4. Registra log e atualiza último_login
    """
    identificador = identificador.strip()

    # Passo 1: resolve o perfil (e o e-mail real do Auth) por matrícula ou e-mail
    if "@" in identificador:
        usuario = get_usuario_by_email(identificador.lower())
    else:
        usuario = get_usuario_by_matricula(identificador)

    if not usuario:
        return False, "Matrícula/e-mail ou senha incorretos."

    # Passo 2: autenticar via Supabase Auth com o e-mail (real ou sintético).
    # Client descartável (não o singleton compartilhado get_supabase()) —
    # ver docstring de criar_cliente_auth_temporario em database/client.py.
    try:
        auth_client = criar_cliente_auth_temporario()
        auth_resp = auth_client.auth.sign_in_with_password({
            "email": usuario["email"],
            "password": senha,
        })
        if not auth_resp.user:
            return False, "Matrícula/e-mail ou senha incorretos."
    except Exception as e:
        err = str(e).lower()
        if "invalid" in err or "credentials" in err:
            return False, "Matrícula/e-mail ou senha incorretos."
        return False, "Erro de conexão: verifique sua internet."

    # Passo 3: salvar na sessão e navegar para home
    set_usuario(usuario)

    # Decide para qual gerência redirecionar por padrão. Usuário com
    # gerência fixa vai direto pro dashboard dela (app.py::_rotear mostra
    # "em construção" se ainda não tiver tela ligada). Admin/global (sem
    # gerência) cai na tela de escolher a Gerência Geral.
    gerencia = usuario.get("gerencia")
    if gerencia:
        set_pagina(f"gerencia_{gerencia.lower()}")
    else:
        set_pagina("selecionar_gg")

    # Passo 4: auditoria (falha silenciosa — login não pode quebrar por causa disso)
    try:
        atualizar_ultimo_login(usuario["id"])
        log_acesso(usuario["id"], "login", {"email": usuario["email"]})
    except Exception:
        pass

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
            "<p style='color:#ffffff; font-weight:600; margin-bottom:0.3rem;'>Matrícula ou e-mail corporativo</p>",
            unsafe_allow_html=True
        )
        identificador = st.text_input(
            "Matrícula ou e-mail",
            placeholder="Ex: 123456 ou seu.nome@mrs.com.br",
            label_visibility="collapsed",
        )

        st.markdown(
            "<p style='color:#ffffff; font-weight:600; margin-bottom:0.3rem; margin-top:0.8rem;'>Senha</p>",
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
            if not identificador or not identificador.strip():
                st.error("⚠️ Informe a matrícula ou o e-mail.")
            elif not senha:
                st.error("⚠️ Informe a senha.")
            else:
                with st.spinner("Autenticando..."):
                    sucesso, msg_erro = _autenticar(identificador, senha)

                if sucesso:
                    st.success("✅ Acesso autorizado!")
                    st.rerun()
                else:
                    st.error(f"❌ {msg_erro}")

    from auth.recuperar_senha import render_esqueci_senha
    render_esqueci_senha()

    _render_card_fim()
    _render_footer()

# endregion
