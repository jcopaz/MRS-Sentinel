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
# sessão).
#
# 2026-09-11: canal de aviso passa a ser SMS PRIMEIRO, e-mail depois
# (relato do Julio: e-mail parou de chegar; SMS via integracoes.brevo.
# enviar_sms — API HTTP do Brevo, não o SMTP usado em _enviar_email_senha).
# Isso também corrige uma limitação real: antes, conta só-matrícula
# (usuarios.email_gerado=True, sem e-mail corporativo real) NUNCA conseguia
# reset autoatendido, só pelo admin — agora, com telefone cadastrado
# (database/schema_telefone.sql), essas contas também se recuperam sozinhas.
#
# Freio contra abuso: além do cooldown client-side (60s, em session_state,
# em render_esqueci_senha), _cooldown_ativo() checa server-side pela mesma
# conta em logs_acesso — SMS custa por mensagem, o freio client-side sozinho
# (burlável recarregando a aba, mesmo gap do Fin360 docs/10 A1) não é
# suficiente aqui.

import secrets
import smtplib
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

from database.client import get_supabase, get_supabase_admin
from database.queries import (
    get_usuario_by_email,
    get_usuario_by_matricula,
    buscar_auth_user_id_por_email,
    atualizar_deve_trocar_senha,
    log_acesso,
)
from integracoes.brevo import enviar_sms

# Mesma mensagem de sucesso independente de a conta existir ou não — evita
# que alguém descubra quais matrículas/e-mails têm conta só tentando o reset.
_MSG_GENERICA = (
    "✅ Se existe uma conta ativa com celular ou e-mail corporativo "
    "cadastrado para essa matrícula/e-mail, uma nova senha temporária foi "
    "enviada por SMS ou e-mail. Confira as mensagens do celular e a caixa "
    "de entrada (e o spam) do e-mail."
)
_MSG_SEM_CONTATO = (
    "⚠️ Essa conta não tem celular nem e-mail corporativo cadastrado — o "
    "reset autoatendido não tem como avisar você em lugar nenhum. Peça a um "
    "administrador para resetar sua senha (Painel Admin > Usuários)."
)
_MSG_FALHA_ENVIO = (
    "❌ A senha foi trocada, mas não conseguimos avisar você agora (SMS e "
    "e-mail indisponíveis). Peça a um administrador para resetar sua senha "
    "de novo."
)

_COOLDOWN_SEGUNDOS = 60


def _cooldown_ativo(usuario_id: str, segundos: int = _COOLDOWN_SEGUNDOS) -> bool:
    """
    Freio server-side contra pedidos repetidos pra mesma conta — reaproveita
    logs_acesso (já grava SOLICITAR_RESET_SENHA) em vez de criar tabela nova.
    Falha-aberta: erro de consulta não deve travar um reset legítimo (mesmo
    critério do rate-limit de login do Fin360, docs/10 A1).
    """
    try:
        from datetime import datetime, timedelta, timezone

        desde = (datetime.now(timezone.utc) - timedelta(seconds=segundos)).isoformat()
        supabase = get_supabase()
        resp = (
            supabase.table("logs_acesso")
            .select("quando")
            .eq("usuario_id", usuario_id)
            .eq("acao", "SOLICITAR_RESET_SENHA")
            .gte("quando", desde)
            .limit(1)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        return False


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
    conta sem contato cadastrado, ou falha de envio).

    Ordem de canal: SMS primeiro (se tem telefone) -> e-mail (se tem e-mail
    corporativo real) -> nenhum dos dois = pede pro admin.
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

    auth_user_id = usuario.get("auth_user_id") or buscar_auth_user_id_por_email(usuario.get("email") or "")
    if not auth_user_id:
        return _MSG_GENERICA

    tem_telefone = bool(usuario.get("telefone"))
    tem_email_real = bool(usuario.get("email")) and not usuario.get("email_gerado")
    if not tem_telefone and not tem_email_real:
        return _MSG_SEM_CONTATO

    if _cooldown_ativo(usuario["id"]):
        # Mesma mensagem genérica — não revela que já tinha pedido antes.
        return _MSG_GENERICA

    senha_temp = _gerar_senha_temporaria()
    try:
        admin = get_supabase_admin()
        admin.auth.admin.update_user_by_id(auth_user_id, {"password": senha_temp})
    except Exception:
        return _MSG_GENERICA

    # Mesma regra do reset manual do admin (modules/admin_panel.py) e da
    # criação de usuário: conta que fica com senha provisória/temporária
    # tem que trocar no próximo login — reduz a janela de exposição da
    # senha que acabou de ser mandada por SMS/e-mail em texto puro (achado
    # de revisão de segurança, 2026-09-06).
    atualizar_deve_trocar_senha(usuario["id"], True)

    canal_usado = None
    if tem_telefone:
        texto_sms = f"MRS Sentinel: senha temporaria = {senha_temp}. Troque no proximo login."
        if enviar_sms(usuario["telefone"], texto_sms):
            canal_usado = "sms"
    if not canal_usado and tem_email_real:
        if _enviar_email_senha(usuario["email"], usuario.get("nome", ""), senha_temp):
            canal_usado = "email"

    if not canal_usado:
        return _MSG_FALHA_ENVIO

    log_acesso(usuario["id"], "SOLICITAR_RESET_SENHA", {"canal": canal_usado})
    return _MSG_GENERICA


def render_esqueci_senha() -> None:
    """Bloco 'Esqueci minha senha' — chamado pela tela de login."""
    with st.expander("🔑 Esqueci minha senha"):
        st.caption(
            "Funciona pra conta com celular ou e-mail corporativo cadastrado "
            "(prioridade: SMS). Sem nenhum dos dois, peça reset a um administrador."
        )
        with st.form("form_esqueci_senha"):
            identificador = st.text_input(
                "Matrícula ou e-mail", placeholder="Ex: 123456 ou seu.nome@mrs.com.br",
                key="esqueci_senha_id",
            )
            enviar = st.form_submit_button("Enviar nova senha")

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
