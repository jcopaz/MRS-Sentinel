# auth/permissions.py — Verificação de permissões RBAC
# Matriz de permissões (fonte: 04_ARQUITETURA.md):
#
#   Ação                  | Admin | Assistente        | Usuário
#   Ver uma Gerência       | ✅    | Só a gerência dele | ✅
#   Ver Visão Geral       | ✅    | ✅                  | ✅
#   Upload de dados       | ✅    | Só da sua ger.     | ❌
#   Criar/editar usuários | ✅    | ❌                  | ❌
#   Ver logs de acesso    | ✅    | ❌                  | ❌

import streamlit as st
from auth.session import get_usuario, get_perfil, get_gerencia
from core.glossarios import LISTA_GERENCIAS


# region ====================== SESSÃO 1: Verificações Booleanas ======================

def is_admin() -> bool:
    """Retorna True se o usuário tem perfil admin."""
    return get_perfil() == "admin"


def is_assistente() -> bool:
    """Retorna True se o usuário tem perfil assistente."""
    return get_perfil() == "assistente"


def can_see_gerencia(gerencia_alvo: str) -> bool:
    """
    Verifica se o usuário pode visualizar uma gerência específica.
    - Admin: pode ver tudo
    - Usuário: pode ver tudo (somente leitura)
    - Assistente: só a gerência dele
    """
    perfil = get_perfil()
    if perfil in ("admin", "usuario"):
        return True
    if perfil == "assistente":
        return get_gerencia() == gerencia_alvo
    return False


def gerencias_visiveis() -> list[str]:
    """
    Lista de siglas de Gerência que o usuário logado pode ver, na ordem
    canônica de LISTA_GERENCIAS. Substitui a tupla fixa ("SP","VP") que
    estava duplicada em modules/alertas.py, evolucao_malha.py e
    visao_campo.py — agora escala pra qualquer gerência cadastrada.
    """
    return [g for g in LISTA_GERENCIAS if can_see_gerencia(g)]


def can_upload(gerencia_alvo: str) -> bool:
    """
    Verifica se o usuário pode fazer upload para uma gerência.
    - Admin: pode para qualquer gerência
    - Assistente: só para a gerência dele
    - Usuário: não pode
    """
    perfil = get_perfil()
    if perfil == "admin":
        return True
    if perfil == "assistente":
        return get_gerencia() == gerencia_alvo
    return False


def can_manage_alertas(gerencia_alvo: str) -> bool:
    """
    Verifica se o usuário pode GERIR alertas (recalcular / marcar visto/resolvido)
    de uma gerência. Mesma regra de escrita do upload:
    - Admin: qualquer gerência
    - Assistente: só a gerência dele
    - Usuário: não (somente leitura — vê a tela e exporta, mas não altera)
    """
    perfil = get_perfil()
    if perfil == "admin":
        return True
    if perfil == "assistente":
        return get_gerencia() == gerencia_alvo
    return False


def can_admin_panel() -> bool:
    """Somente admin acessa o painel de administração."""
    return is_admin()


def can_see_logs() -> bool:
    """Somente admin vê logs de acesso."""
    return is_admin()


def can_manage_users() -> bool:
    """Somente admin pode criar/editar/desativar usuários."""
    return is_admin()


def can_access_modo_tv() -> bool:
    """
    Verifica se o usuário pode acessar o Modo TV (painel de exibição em
    loop, pensado pra TV/monitor de uma coordenação — ex.: TV parada na
    coordenação de Jundiaí). Admin sempre pode; qualquer outro perfil só
    se tiver o campo 'acesso_tv' marcado explicitamente no Painel Admin
    (checkbox "📺 Acesso ao Modo TV") — pensado pra uma conta dedicada de
    kiosk, sem precisar dar admin completo pra ela. Por enquanto
    (2026-08-30) só admin de fato usa; o campo já existe pronto pra
    delegar no futuro.
    """
    if is_admin():
        return True
    usuario = get_usuario()
    return bool(usuario and usuario.get("acesso_tv"))

# endregion


# region ====================== SESSÃO 2: Guards de Tela ======================

def require_login():
    """
    Guard: se não estiver logado, para a execução e mostra mensagem.
    Usar no topo de módulos protegidos.
    """
    from auth.session import is_logged_in
    if not is_logged_in():
        st.error("🔒 Acesso restrito. Por favor, faça login.")
        st.stop()


def require_admin():
    """Guard: para a execução se não for admin."""
    require_login()
    if not is_admin():
        st.error("🚫 Esta área é restrita a administradores.")
        st.stop()


def require_upload_permission(gerencia_alvo: str):
    """Guard: para execução se não tiver permissão de upload para a gerência."""
    require_login()
    if not can_upload(gerencia_alvo):
        st.error(f"🚫 Você não tem permissão para fazer upload na Gerência {gerencia_alvo}.")
        st.stop()


def require_modo_tv():
    """Guard: para a execução se não tiver acesso ao Modo TV."""
    require_login()
    if not can_access_modo_tv():
        st.error("🚫 Você não tem acesso ao Modo TV.")
        st.stop()

# endregion
