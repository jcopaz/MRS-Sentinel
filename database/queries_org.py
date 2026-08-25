# database/queries_org.py
# Leitura/escrita do organograma genérico (org_unidades / usuario_escopo).
#
# ⚠️ Fundação, ainda não usada por nenhuma tela do app — ver comentário no
# topo de database/schema_organograma.sql. Só existe pra já ter a base
# pronta quando o organograma for de fato ligado às telas/permissões numa
# sessão dedicada. usuarios.gerencia continua sendo a fonte de verdade
# até lá.

import streamlit as st

from database.client import get_supabase

# region ====================== SESSÃO 1: Leitura do organograma ==============

def listar_unidades(tipo: str | None = None, unidade_pai_id: str | None = None) -> list[dict]:
    """Lista nós do organograma, opcionalmente filtrando por tipo e/ou pai."""
    try:
        supabase = get_supabase()
        q = supabase.table("org_unidades").select("*").eq("ativo", True)
        if tipo:
            q = q.eq("tipo", tipo)
        if unidade_pai_id:
            q = q.eq("unidade_pai_id", unidade_pai_id)
        resp = q.order("nome").execute()
        return resp.data or []
    except Exception as e:
        st.error(f"❌ Erro ao buscar organograma: {e}")
        return []


def resolver_unidade_por_codigo_sap(disciplina: str, codigo_completo: str) -> dict | None:
    """
    Resolve um código SAP (ex.: 'V.RJ.FBJ', 'V.MG.FBV' legado, 'V.SP') pro
    nó do organograma dono dele HOJE — funciona tanto pro código vigente
    quanto pra qualquer código legado já registrado em org_codigo_sap
    (ver comentário da tabela em database/schema_organograma.sql: cobre
    coordenação que mudou de Gerência e/ou de código ao longo do tempo).
    """
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("org_codigo_sap")
            .select("*, org_unidades(*)")
            .eq("disciplina", disciplina)
            .eq("codigo_completo", codigo_completo)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        return resp.data[0]["org_unidades"]
    except Exception as e:
        st.error(f"❌ Erro ao resolver código SAP '{codigo_completo}': {e}")
        return None


def descendentes_ids(unidade_id: str) -> list[str]:
    """
    Retorna o próprio id + todos os ids descendentes na árvore (BFS).
    Usado pra resolver acesso em cascata: quem tem escopo num nó vê tudo
    que está abaixo dele.
    """
    try:
        supabase = get_supabase()
        resp = supabase.table("org_unidades").select("id, unidade_pai_id").eq("ativo", True).execute()
        todas = resp.data or []
    except Exception as e:
        st.error(f"❌ Erro ao resolver organograma: {e}")
        return [unidade_id]

    filhos_por_pai: dict[str, list[str]] = {}
    for u in todas:
        pai = u.get("unidade_pai_id")
        if pai:
            filhos_por_pai.setdefault(pai, []).append(u["id"])

    resultado = [unidade_id]
    fila = [unidade_id]
    while fila:
        atual = fila.pop(0)
        for filho_id in filhos_por_pai.get(atual, []):
            if filho_id not in resultado:
                resultado.append(filho_id)
                fila.append(filho_id)
    return resultado

# endregion


# region ====================== SESSÃO 2: Escrita do organograma ==============

def criar_unidade(tipo: str, sigla: str, nome: str, unidade_pai_id: str | None = None) -> bool:
    """Cria um nó no organograma (Gerência Geral / Gerência / Coordenação)."""
    try:
        supabase = get_supabase()
        supabase.table("org_unidades").insert({
            "tipo":           tipo,
            "sigla":          sigla.strip(),
            "nome":           nome.strip(),
            "unidade_pai_id": unidade_pai_id,
        }).execute()
        return True
    except Exception as e:
        st.error(f"❌ Erro ao criar unidade '{sigla}': {e}")
        return False

# endregion


# region ====================== SESSÃO 3: Escopo de acesso (cascata) ==========

def conceder_escopo(usuario_id: str, unidade_id: str) -> bool:
    """Concede a um usuário acesso a um nó do organograma (e tudo abaixo dele)."""
    try:
        supabase = get_supabase()
        supabase.table("usuario_escopo").upsert(
            {"usuario_id": usuario_id, "unidade_id": unidade_id},
            on_conflict="usuario_id,unidade_id",
        ).execute()
        return True
    except Exception as e:
        st.error(f"❌ Erro ao conceder escopo: {e}")
        return False


def revogar_escopo(usuario_id: str, unidade_id: str) -> bool:
    """Remove o acesso de um usuário a um nó do organograma."""
    try:
        supabase = get_supabase()
        supabase.table("usuario_escopo").delete().eq("usuario_id", usuario_id).eq("unidade_id", unidade_id).execute()
        return True
    except Exception as e:
        st.error(f"❌ Erro ao revogar escopo: {e}")
        return False


def listar_escopos_usuario(usuario_id: str) -> list[dict]:
    """Lista os nós do organograma que um usuário tem acesso direto (sem cascata)."""
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("usuario_escopo")
            .select("*, org_unidades(tipo, sigla, nome)")
            .eq("usuario_id", usuario_id)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        st.error(f"❌ Erro ao buscar escopos do usuário: {e}")
        return []

# endregion
