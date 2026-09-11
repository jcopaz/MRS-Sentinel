# auth/trocar_senha_obrigatoria.py — Troca de senha obrigatória
#
# Por quê existe: toda conta nova nasce com a MESMA senha provisória
# (SENHA_PADRAO, ver modules/admin_panel.py) e todo reset de senha volta
# pra ela também — sem esta tela, quem não trocasse manualmente ficava
# com a senha provisória pra sempre (achado real do Julio, 2026-09-02:
# criou um usuário de teste e não foi pedido pra trocar a senha).
#
# Como funciona: usuarios.deve_trocar_senha (ver
# database/schema_deve_trocar_senha.sql) é setado TRUE tanto na criação de
# usuário quanto em todo reset de senha (modules/admin_panel.py). Enquanto
# estiver TRUE, app.py::main() renderiza SÓ esta tela — sidebar e rotas
# normais ficam bloqueadas até a troca (ou logout).
#
# Mesmo mecanismo de troca já usado em auth/recuperar_senha.py e
# modules/admin_panel._resetar_senha: API admin do Supabase
# (update_user_by_id), sem depender de SMTP — a rede corporativa da MRS
# bloqueia porta de saída SMTP mesmo (ver auth/recuperar_senha.py).
#
# 2026-09-11: ganha a captura do TELEFONE de recuperação (relato de e-mail
# não chegando — SMS vira o canal prioritário). Pedido explícito do Julio:
# capturar no exato momento da troca de senha, enquanto a pessoa já está
# na tela. Quem já tinha conta e não passa mais por aqui (deve_trocar_senha
# já False) recebe um prompt único equivalente — ver
# auth/confirmar_telefone.py, acionado por app.py::main().
#
# Sessão 1: Lógica de troca
# Sessão 2: Renderização

import streamlit as st

from database.client import get_supabase_admin
from database.queries import (
    buscar_auth_user_id_por_email,
    atualizar_deve_trocar_senha,
    atualizar_telefone,
    log_acesso,
)
from auth.session import get_usuario, clear_session
from auth.telefone import validar_e_formatar_telefone


# region ====================== SESSÃO 1: Lógica de troca ======================

def _trocar_senha(nova_senha: str, telefone_e164: str) -> tuple[bool, str]:
    """
    Troca a senha da conta logada via API admin do Supabase, grava o
    telefone de recuperação e desmarca deve_trocar_senha (banco + sessão em
    memória — sem atualizar a sessão aqui, o gate continuaria pedindo troca/
    telefone até o próximo login).
    """
    usuario = get_usuario()
    if not usuario:
        return False, "Sessão inválida — faça login novamente."

    auth_user_id = usuario.get("auth_user_id") or buscar_auth_user_id_por_email(usuario.get("email", ""))
    if not auth_user_id:
        return False, "Conta não encontrada no Supabase Auth — peça a um administrador para resetar sua senha."

    try:
        admin = get_supabase_admin()
        admin.auth.admin.update_user_by_id(auth_user_id, {"password": nova_senha})
    except Exception as e:
        return False, f"Erro ao trocar a senha: {e}"

    atualizar_deve_trocar_senha(usuario["id"], False)
    atualizar_telefone(usuario["id"], telefone_e164)
    usuario["deve_trocar_senha"] = False
    usuario["telefone"] = telefone_e164
    st.session_state["usuario"] = usuario

    try:
        log_acesso(usuario["id"], "TROCAR_SENHA_OBRIGATORIA", {"email": usuario.get("email")})
    except Exception:
        pass

    return True, ""

# endregion


# region ====================== SESSÃO 2: Renderização =========================

def render_trocar_senha_obrigatoria() -> None:
    """
    Tela que intercepta o app inteiro enquanto usuarios.deve_trocar_senha
    for True. Chamada por app.py::main() ANTES de render_sidebar()/rotas —
    não há como navegar pro resto do app sem passar por aqui primeiro.
    """
    st.markdown("## 🔑 Troque sua senha")
    st.info(
        "Este é seu primeiro acesso, ou sua senha foi resetada por um "
        "administrador. Por segurança, defina uma senha nova antes de "
        "continuar — não é possível manter a senha provisória."
    )

    with st.form("form_trocar_senha_obrigatoria"):
        nova = st.text_input(
            "Nova senha", type="password",
            help="Mínimo 8 caracteres.",
            key="tso_nova_senha",
        )
        confirma = st.text_input(
            "Confirme a nova senha", type="password",
            key="tso_confirma_senha",
        )
        telefone_bruto = st.text_input(
            "Celular com DDD (para recuperação por SMS)",
            placeholder="(11) 91234-5678",
            key="tso_telefone",
        )
        st.caption("Usamos seu celular só para recuperar seu acesso caso você esqueça a senha.")
        enviar = st.form_submit_button(
            "✅ Trocar senha e continuar", type="primary", key="tso_btn_enviar",
        )

    if enviar:
        telefone = validar_e_formatar_telefone(telefone_bruto)
        if len(nova) < 8:
            st.error("⚠️ A senha deve ter no mínimo 8 caracteres.")
        elif nova != confirma:
            st.error("⚠️ As senhas não conferem.")
        elif not telefone:
            st.error("⚠️ Informe um celular válido, com DDD.")
        else:
            with st.spinner("Trocando senha..."):
                ok, erro = _trocar_senha(nova, telefone)
            if ok:
                st.success("✅ Senha alterada! Redirecionando...")
                st.rerun()
            else:
                st.error(f"❌ {erro}")

    st.markdown("---")
    st.caption("Não é você quem deveria estar trocando esta senha agora?")
    if st.button("🚪 Cancelar e sair", key="tso_btn_cancelar"):
        clear_session()
        st.rerun()

# endregion
