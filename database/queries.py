# database/queries.py
# Queries reutilizáveis para acesso ao Supabase — Sprint 1 + Sprint 3
# Atualizado: Sprint 3 — Visualizações por Gerência
#
# Padrão: funções retornam pd.DataFrame ou None em caso de erro
# Sempre aplica normalizar_coluna_ramal() após o load (ASP→VSU etc.)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database.client import get_supabase
from core.glossarios import normalizar_coluna_ramal

# region ====================== SESSÃO 1: Queries base (Sprint 1) ==============

def get_notas_gerencia(gerencia: str, disciplina: str | None = None) -> pd.DataFrame:
    """
    Busca todas as notas ativas de uma gerência.

    Filtros: gerencia obrigatório, disciplina opcional ('VP' ou 'EE').
    Sempre normaliza a coluna 'ramal' (ASP→VSU, etc.) após o load.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None (ambas)

    Returns:
        pd.DataFrame com todas as notas, ou DataFrame vazio em caso de erro.
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("notas")
            .select("*, uploads_historico(enviado_em, usuario_id, nome_arquivo)")
            .eq("gerencia", gerencia)
        )
        if disciplina:
            query = query.eq("disciplina", disciplina)

        response = query.execute()

        if not response.data:
            return pd.DataFrame()

        df = pd.DataFrame(response.data)

        # ⭐ ESSENCIAL: normaliza siglas de ramal logo após o load
        df = normalizar_coluna_ramal(df, "ramal")

        # Converte colunas de data
        for col in ["data_nota", "data_encerramento", "data_planejada", "criado_em"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        # Garante numérico em colunas sensíveis
        for col in ["score", "km_real", "km_fim_real", "lead_time_dias", "peso_prio"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    except Exception as e:
        st.error(f"❌ Erro ao buscar notas ({gerencia}/{disciplina}): {e}")
        return pd.DataFrame()


def get_uploads_historico(gerencia: str | None = None) -> pd.DataFrame:
    """
    Retorna o histórico de uploads de uma gerência (ou todos, se gerencia=None).
    Usado no card de 'última atualização' e na auditoria.

    Args:
        gerencia: 'SP', 'VP' ou None

    Returns:
        pd.DataFrame com histórico de uploads
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("uploads_historico")
            .select("*, usuarios(nome, email)")
            .order("enviado_em", desc=True)
        )
        if gerencia:
            query = query.eq("gerencia", gerencia)

        response = query.execute()
        df = pd.DataFrame(response.data or [])

        if not df.empty and "enviado_em" in df.columns:
            df["enviado_em"] = pd.to_datetime(df["enviado_em"], errors="coerce")

        return df

    except Exception as e:
        st.error(f"❌ Erro ao buscar histórico de uploads: {e}")
        return pd.DataFrame()


def get_ultima_atualizacao(gerencia: str, disciplina: str | None = None) -> str:
    """
    Retorna a data/hora do último upload ativo para o card de 'última atualização'.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None

    Returns:
        String formatada (ex: '05/07/2026 às 14:32') ou 'Sem dados'
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("uploads_historico")
            .select("enviado_em")
            .eq("gerencia", gerencia)
            .eq("status", "ativo")
            .order("enviado_em", desc=True)
            .limit(1)
        )
        if disciplina:
            query = query.eq("disciplina", disciplina)

        response = query.execute()

        if response.data:
            dt = pd.to_datetime(response.data[0]["enviado_em"])
            return dt.strftime("%d/%m/%Y às %H:%M")

        return "Sem dados"

    except Exception:
        return "Sem dados"

# endregion


# region ====================== SESSÃO 2: Queries Sprint 3 =====================

@st.cache_data(ttl=300)  # Cache de 5 minutos — dados não mudam frequentemente
def get_notas_cached(gerencia: str, disciplina: str | None = None) -> pd.DataFrame:
    """
    Versão cacheada de get_notas_gerencia para uso nas telas de visualização.
    TTL de 5 minutos evita múltiplos round-trips ao banco em recargas normais.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None

    Returns:
        pd.DataFrame com as notas (cacheado)
    """
    return get_notas_gerencia(gerencia, disciplina)


def get_kpis_gerencia(gerencia: str, disciplina: str | None = None) -> dict:
    """
    Retorna KPIs aggregados diretamente do banco (query leve).

    KPIs calculados:
      - total_notas
      - notas_abertas
      - score_medio
      - lead_time_medio
      - ramal_mais_critico (sigla)
      - notas_muito_alta

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None

    Returns:
        dict com os KPIs, ou dict vazio em caso de erro
    """
    try:
        df = get_notas_cached(gerencia, disciplina)

        if df.empty:
            return {}

        kpis = {
            "total_notas":     len(df),
            "notas_abertas":   int((df.get("status_usuario", pd.Series()).str.upper() == "ABER").sum()),
            "score_medio":     round(df["score"].dropna().mean(), 2) if "score" in df.columns else 0.0,
            "lead_time_medio": round(df["lead_time_dias"].dropna().mean(), 1) if "lead_time_dias" in df.columns else 0.0,
            "notas_muito_alta": int(
                df["prioridade"].str.contains("1-Muito alta", na=False).sum()
            ) if "prioridade" in df.columns else 0,
        }

        # Ramal mais crítico — maior score total
        if "ramal" in df.columns and "score" in df.columns:
            por_ramal = df.groupby("ramal")["score"].sum().dropna()
            if not por_ramal.empty:
                kpis["ramal_mais_critico"] = por_ramal.idxmax()

        return kpis

    except Exception as e:
        st.error(f"❌ Erro ao calcular KPIs ({gerencia}/{disciplina}): {e}")
        return {}


def get_notas_por_periodo(
    gerencia: str,
    disciplina: str | None = None,
    dias: int = 90,
) -> pd.DataFrame:
    """
    Retorna notas criadas nos últimos N dias — otimiza a série temporal
    para não trazer o histórico completo.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None
        dias:       janela de tempo em dias (padrão 90)

    Returns:
        pd.DataFrame filtrado por data_nota >= (hoje - dias)
    """
    df = get_notas_cached(gerencia, disciplina)

    if df.empty or "data_nota" not in df.columns:
        return df

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=dias)
    df_periodo = df[df["data_nota"] >= cutoff].copy()

    return df_periodo


def get_ranking_hotspots(
    gerencia: str,
    disciplina: str | None = None,
    top_n: int = 20,
) -> pd.DataFrame:
    """
    Retorna os top N trechos mais críticos por score total.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None
        top_n:      número de registros a retornar

    Returns:
        pd.DataFrame com colunas: ramal, origem, score_total, n_notas, lead_medio
    """
    df = get_notas_cached(gerencia, disciplina)

    if df.empty:
        return pd.DataFrame()

    group_cols = [c for c in ["ramal", "origem"] if c in df.columns]

    if not group_cols:
        return pd.DataFrame()

    agg_dict = {}
    if "score" in df.columns:
        agg_dict["score"] = "sum"
    if "lead_time_dias" in df.columns:
        agg_dict["lead_time_dias"] = "mean"
    agg_dict["numero_nota"] = "count"

    ranking = (
        df.groupby(group_cols)
        .agg(agg_dict)
        .reset_index()
        .rename(columns={
            "score":          "score_total",
            "lead_time_dias": "lead_medio",
            "numero_nota":    "n_notas",
        })
        .sort_values("score_total", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    return ranking

# endregion


# region ====================== SESSÃO 3: Invalidação de cache =================

def invalidar_cache_notas() -> None:
    """
    Força limpeza do cache de notas.
    Deve ser chamada após um novo upload para garantir dados frescos.

    Uso:
        from database.queries import invalidar_cache_notas
        invalidar_cache_notas()  # chamado em data_uploader.py após upload
    """
    get_notas_cached.clear()
    st.toast("🔄 Cache de notas atualizado.", icon="✅")

# endregion
