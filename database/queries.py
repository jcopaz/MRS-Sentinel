# database/queries.py — Queries reutilizáveis centralizadas
# Centralizar queries aqui facilita manutenção: se a estrutura do banco mudar,
# só este arquivo precisa ser atualizado.

import streamlit as st
import pandas as pd
from datetime import datetime
from database.client import get_supabase, get_supabase_admin


# region ====================== SESSÃO 1: Usuários ======================

def get_usuario_by_email(email: str) -> dict | None:
    """
    Busca perfil do usuário na tabela 'usuarios' pelo email.
    Retorna dict com dados ou None se não encontrado/inativo.
    """
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("usuarios")
            .select("*")
            .eq("email", email)
            .eq("ativo", True)
            .single()
            .execute()
        )
        return resp.data
    except Exception:
        # Usuário não encontrado ou inativo
        return None


def get_todos_usuarios() -> pd.DataFrame:
    """Retorna todos os usuários para o painel admin."""
    try:
        supabase = get_supabase()
        resp = supabase.table("usuarios").select("*").order("criado_em", desc=True).execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao buscar usuários: {e}")
        return pd.DataFrame()


def criar_usuario_perfil(email: str, nome: str, perfil: str, gerencia: str | None, criado_por_id: str) -> bool:
    """
    Insere linha na tabela 'usuarios' após o usuário já ter sido criado no Supabase Auth.
    Retorna True se sucesso, False se erro.
    """
    try:
        supabase = get_supabase()
        supabase.table("usuarios").insert({
            "email": email,
            "nome": nome,
            "perfil": perfil,
            "gerencia": gerencia,
            "ativo": True,
            "criado_por": criado_por_id,
        }).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao criar perfil: {e}")
        return False


def criar_usuario_auth(email: str, senha: str) -> bool:
    """
    Cria usuário no Supabase Auth via service_role.
    Chamado ANTES de criar o perfil na tabela 'usuarios'.
    """
    try:
        admin = get_supabase_admin()
        admin.auth.admin.create_user({
            "email": email,
            "password": senha,
            "email_confirm": True,  # confirma email automaticamente
        })
        return True
    except Exception as e:
        st.error(f"Erro ao criar usuário Auth: {e}")
        return False


def toggle_usuario_ativo(usuario_id: str, ativo: bool) -> bool:
    """Ativa ou desativa um usuário no sistema."""
    try:
        supabase = get_supabase()
        supabase.table("usuarios").update({"ativo": ativo}).eq("id", usuario_id).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar usuário: {e}")
        return False


def atualizar_ultimo_login(email: str):
    """Registra o timestamp do último login do usuário."""
    try:
        supabase = get_supabase()
        supabase.table("usuarios").update({
            "ultimo_login": datetime.now().isoformat()
        }).eq("email", email).execute()
    except Exception:
        pass  # Falha silenciosa — não deve bloquear o login

# endregion


# region ====================== SESSÃO 2: Uploads e Notas ======================

def get_ultima_atualizacao(gerencia: str | None = None) -> dict | None:
    """
    Retorna o upload mais recente (ativo) de uma gerência.
    Se gerencia=None, retorna o mais recente de todas.
    Usado pelo card 'Última Atualização' na sidebar.
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("uploads_historico")
            .select("gerencia, disciplina, enviado_em, total_notas, nome_arquivo")
            .eq("status", "ativo")
            .order("enviado_em", desc=True)
            .limit(1)
        )
        if gerencia:
            query = query.eq("gerencia", gerencia)
        resp = query.execute()
        return resp.data[0] if resp.data else None
    except Exception:
        return None


def get_contagem_notas_por_gerencia() -> dict:
    """
    Retorna contagem total de notas ativas por gerência.
    Usado para o dashboard de visão geral.
    """
    try:
        supabase = get_supabase()
        # Conta notas via uploads ativos
        resp = (
            supabase.table("uploads_historico")
            .select("gerencia, total_notas")
            .eq("status", "ativo")
            .execute()
        )
        contagem = {"SP": 0, "VP": 0}
        for row in (resp.data or []):
            g = row.get("gerencia")
            if g in contagem:
                contagem[g] += row.get("total_notas", 0)
        return contagem
    except Exception:
        return {"SP": 0, "VP": 0}

# endregion


# region ====================== SESSÃO 3: Notas e Uploads ======================

def get_notas_gerencia(gerencia: str, disciplina: str | None = None) -> pd.DataFrame:
    """
    Busca notas ativas de uma gerência do upload mais recente.
    Filtra pelo upload_id ativo para evitar pegar dados de uploads antigos.
    """
    try:
        supabase = get_supabase()

        # Primeiro busca o upload ativo da gerência
        query_upload = (
            supabase.table("uploads_historico")
            .select("id")
            .eq("gerencia", gerencia)
            .eq("status", "ativo")
        )
        if disciplina:
            query_upload = query_upload.eq("disciplina", disciplina)

        resp_uploads = query_upload.execute()
        if not resp_uploads.data:
            return pd.DataFrame()

        upload_ids = [r["id"] for r in resp_uploads.data]

        # Busca notas dos uploads ativos
        query = (
            supabase.table("notas")
            .select("*")
            .in_("upload_id", upload_ids)
        )
        resp = query.execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()

    except Exception as e:
        st.error(f"Erro ao buscar notas: {e}")
        return pd.DataFrame()


def get_historico_uploads(gerencia: str | None = None, usuario_id: str | None = None) -> pd.DataFrame:
    """
    Retorna histórico de uploads com join de usuário.
    Admin vê todos; assistente filtra por usuario_id.
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("uploads_historico")
            .select("*, usuarios(nome, email)")
            .order("enviado_em", desc=True)
            .limit(50)
        )
        if gerencia:
            query = query.eq("gerencia", gerencia)
        if usuario_id:
            query = query.eq("usuario_id", usuario_id)

        resp = query.execute()
        return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao buscar histórico: {e}")
        return pd.DataFrame()

# endregion


# region ====================== SESSÃO 4: Auditoria ======================

def log_acesso(usuario_id: str, acao: str, detalhes: dict | None = None):
    """
    Registra ação do usuário na tabela logs_acesso.
    Falha silenciosa para não atrapalhar a UX.
    Ações comuns: 'login', 'logout', 'view_sp', 'view_vp', 'upload_vp', etc.
    """
    try:
        supabase = get_supabase()
        supabase.table("logs_acesso").insert({
            "usuario_id": usuario_id,
            "acao": acao,
            "detalhes": detalhes or {},
        }).execute()
    except Exception:
        pass  # Log nunca deve quebrar o fluxo principal

# endregion
