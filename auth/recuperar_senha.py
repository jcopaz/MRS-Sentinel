# auth/recuperar_senha.py — Reset de senha autoatendido ("Esqueci minha senha")
#
# Por quê NÃO usa o "link mágico" do Supabase Auth: esse fluxo (
# reset_password_for_email + exchange_code_for_session) depende do client
# guardar uma sessão internamente entre a etapa de pedir o link e a etapa
# de trocar a senha. Mas database/client.get_supabase() é um único client
# (@st.cache_resource) compartilhado por TODOS os usuários simultâneos do
# servidor Streamlit — em produção, com mais de uma pessoa navegando ao
# mesmo tempo, isso arrisca uma sessão vazar pra thread errada. Por isso o
# reset aqui é mais simples e sem esse risco: gera uma senha temporária no
# servidor e troca direto via API admin do Supabase (mesmo mecanismo já
# usado e testado em modules/admin_panel._resetar_senha — sem estado de
# sessão), e manda a senha nova por e-mail via SMTP simples (Brevo ou
# outro provedor, configurado em st.secrets["smtp"]).
#
# Só funciona para contas com e-mail corporativo real cadastrado
# (usuarios.email_gerado=False) — quem loga só por matrícula (sem e-mail
# real) precisa pedir reset a um administrador (Painel Admin > Usuários).

import secrets
import smtplib
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

from database.client import get_supabase_admin
from database.queries import (
    get_usuario_by_email,
    get_usuario_by_matricula,
    buscar_auth_user_id_por_email,
    log_acesso,
)

# Mesma mensagem de sucesso independente de a conta existir ou não — evita
# que alguém descubra quais matrículas/e-mails têm conta só tentando o reset.
_MSG_GENERICA = (
    "✅ Se existe uma conta ativa com e-mail corporativo cadastrado para essa "
    "matrícula/e-mail, uma nova senha temporária foi enviada. Confira sua "
    "caixa de entrada (e o spam)."
)
_MSG_SEM_EMAIL = (
    "⚠️ Essa conta não tem e-mail corporativo cadastrado — o reset autoatendido "
    "não tem como avisar você em lugar nenhum. Peça a um administrador para "
    "resetar sua senha (Painel Admin > Usuários)."
)
_MSG_FALHA_ENVIO = (
    "❌ A senha foi trocada, mas não conseguimos enviar o e-mail agora "
    "(SMTP indisponível). Peça a um administrador para resetar sua senha de novo."
)

_COOLDOWN_SEGUNDOS = 60


def _gerar_senha_temporaria(tamanho: int = 10) -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def _enviar_email_senha(destinatario: str, nome: str, senha_temp: str) -> bool:
    """Envia a senha temporária por SMTP. Retorna True se enviou sem erro."""
    smtp_cfg = st.secrets.get("smtp", {})
    host = smtp_cfg.get("host")
    if not host:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "[MRS Sentinel] Sua nova senha temporária"
        msg["From"] = smtp_cfg.get("remetente", smtp_cfg.get("usuario", ""))
        msg["To"] = destinatario
        corpo = f"""
        <p>Olá, {nome},</p>
        <p>Recebemos um pedido de reset de senha para sua conta no MRS Sentinel.</p>
        <p>Sua nova senha temporária é: <b style="font-size:1.15em">{senha_temp}</b></p>
        <p>Use essa senha pra entrar. Se não foi você quem pediu, avise um administrador.</p>
        """
        msg.attach(MIMEText(corpo, "html"))

        porta = int(smtp_cfg.get("port", 587))
        with smtplib.SMTP(host, porta, timeout=20) as server:
            server.starttls()
            if smtp_cfg.get("usuario"):
                server.login(smtp_cfg["usuario"], smtp_cfg.get("senha", ""))
            server.sendmail(msg["From"], [destinatario], msg.as_string())
        return True
    except Exception:
        return False


def solicitar_reset_senha(identificador: str) -> str:
    """
    Ponto de entrada do "Esqueci minha senha" na tela de login.
    Retorna a mensagem a mostrar pro usuário (sucesso genérico, aviso de
    conta sem e-mail, ou falha de envio).
    """
    identificador = identificador.strip()
    if not identificador:
        return _MSG_GENERICA

    if "@" in identificador:
        usuario = get_usuario_by_email(identificador.lower())
    else:
        usuario = get_usuario_by_matricula(identificador)

    if not usuario:
        return _MSG_GENERICA

    auth_user_id = usuario.get("auth_user_id") or buscar_auth_user_id_por_email(usuario["email"])
    if usuario.get("email_gerado") or not auth_user_id:
        return _MSG_SEM_EMAIL

    senha_temp = _gerar_senha_temporaria()
    try:
        admin = get_supabase_admin()
        admin.auth.admin.update_user_by_id(auth_user_id, {"password": senha_temp})
    except Exception:
        return _MSG_GENERICA

    if not _enviar_email_senha(usuario["email"], usuario.get("nome", ""), senha_temp):
        return _MSG_FALHA_ENVIO

    log_acesso(usuario["id"], "SOLICITAR_RESET_SENHA", {"email": usuario["email"]})
    return _MSG_GENERICA


def render_esqueci_senha() -> None:
    """Bloco 'Esqueci minha senha' — chamado pela tela de login."""
    with st.expander("🔑 Esqueci minha senha"):
        st.caption(
            "Funciona só pra contas com e-mail corporativo cadastrado. "
            "Login só por matrícula precisa de reset pelo administrador."
        )
        with st.form("form_esqueci_senha"):
            identificador = st.text_input(
                "Matrícula ou e-mail", placeholder="Ex: 123456 ou seu.nome@mrs.com.br",
                key="esqueci_senha_id",
            )
            enviar = st.form_submit_button("Enviar nova senha por e-mail")

        if enviar:
            agora = st.session_state.get("_ultimo_reset_ts")
            import time
            ts = time.time()
            if agora and (ts - agora) < _COOLDOWN_SEGUNDOS:
                st.warning(f"⏳ Aguarde {int(_COOLDOWN_SEGUNDOS - (ts - agora))}s antes de tentar de novo.")
            elif not identificador.strip():
                st.error("⚠️ Informe a matrícula ou o e-mail.")
            else:
                st.session_state["_ultimo_reset_ts"] = ts
                with st.spinner("Processando..."):
                    msg = solicitar_reset_senha(identificador)
                if msg.startswith("✅"):
                    st.success(msg)
                elif msg.startswith("⚠️"):
                    st.warning(msg)
                else:
                    st.error(msg)
