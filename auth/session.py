# auth/session.py — Gerenciamento de estado de sessão do usuário
# Centraliza toda leitura/escrita do st.session_state relacionada ao usuário,
# evitando acesso direto e disperso ao session_state em todo o código.

import streamlit as st


# region ====================== SESSÃO 1: Verificação de Estado ======================

def is_logged_in() -> bool:
    """Retorna True se há um usuário autenticado na sessão atual."""
    return bool(st.session_state.get("usuario"))


def get_usuario() -> dict | None:
    """Retorna o dict completo do usuário logado, ou None."""
    return st.session_state.get("usuario")


def get_perfil() -> str | None:
    """Retorna o perfil do usuário: 'admin', 'assistente' ou 'usuario'."""
    u = get_usuario()
    return u.get("perfil") if u else None


def get_gerencia() -> str | None:
    """Retorna a gerência do usuário ('SP', 'VP') ou None para admin."""
    u = get_usuario()
    return u.get("gerencia") if u else None


def get_nome() -> str:
    """Retorna o nome do usuário ou 'Usuário' como fallback."""
    u = get_usuario()
    return u.get("nome", "Usuário") if u else "Usuário"


def get_id() -> str | None:
    """Retorna o UUID do usuário na tabela 'usuarios'."""
    u = get_usuario()
    return u.get("id") if u else None

# endregion


# region ====================== SESSÃO 2: Escrita de Estado ======================

def set_usuario(usuario_dict: dict):
    """Armazena o usuário autenticado na sessão."""
    st.session_state["usuario"] = usuario_dict
    st.session_state["logged_in"] = True


def clear_session():
    """
    Limpa todos os dados de sessão do usuário (logout).
    Preserva apenas chaves de UI que não são sensíveis.
    """
    keys_to_clear = ["usuario", "logged_in", "pagina", "gerencia_ativa"]
    for key in keys_to_clear:
        st.session_state.pop(key, None)


def set_pagina(pagina: str):
    """Navega para uma página sem disparar st.rerun (feito pelo caller)."""
    st.session_state["pagina"] = pagina


def get_pagina() -> str:
    """Retorna a página atual, com fallback para gerencia_sp."""
    return st.session_state.get("pagina", "gerencia_sp")

# endregion


# region ====================== SESSÃO 3: Inicialização ======================

def init_session():
    """
    Inicializa todas as variáveis de sessão com valores padrão.
    Deve ser chamado no início de app.py a cada rerun.
    Usa 'setdefault' para não sobrescrever valores já existentes na sessão.
    """
    defaults = {
        "usuario":         None,
        "logged_in":       False,
        "pagina":          "login",
        "gerencia_ativa":  None,
        "sp_disciplina":   "VP",
        "vp_disciplina":   "VP",
    }
    for key, val in defaults.items():
        st.session_state.setdefault(key, val)

# endregion
