# database/queries_baseline.py
# Queries de acesso à tabela `rasf_baseline` (Base de Falhas EE congelada 2025).
# Sprint 7 — espelha o padrão anti-duplicação de database/queries_rasf.py.

import streamlit as st
import pandas as pd
from database.client import get_supabase

# Disciplina usada em uploads_historico para os uploads do congelado.
DISCIPLINA_BASELINE = "RASF_BASE"

_COLS_DATA = ["data_nota", "criado_em"]
_COLS_NUM = ["ano", "mes", "numero_nota", "thp_min"]
_COLS_BOOL = ["gerador_thp"]


def _upload_ids_ativos_baseline(gerencia: str | None = None) -> list[str]:
    """IDs de uploads do congelado com status 'ativo' (anti-duplicação)."""
    try:
        supabase = get_supabase()
        q = (
            supabase.table("uploads_historico")
            .select("id")
            .eq("disciplina", DISCIPLINA_BASELINE)
            .eq("status", "ativo")
        )
        if gerencia:
            q = q.eq("gerencia", gerencia)
        resp = q.execute()
        return [r["id"] for r in (resp.data or [])]
    except Exception:
        return []


def get_baseline_gerencia(gerencia: str | None = None) -> pd.DataFrame:
    """
    Busca as linhas do congelado 2025 ativas.

    Args:
        gerencia: 'SP', 'VP' ou None (ambas — Visão Global).

    Returns:
        DataFrame canônico (colunas do core.parser_rasf_baseline), ou vazio.
    """
    try:
        supabase = get_supabase()

        upload_ids = _upload_ids_ativos_baseline(gerencia)
        if not upload_ids:
            return pd.DataFrame()

        PAGE_SIZE = 1000
        registros: list[dict] = []
        offset = 0
        while True:
            query = (
                supabase.table("rasf_baseline")
                .select("*")
                .in_("upload_id", upload_ids)
                .range(offset, offset + PAGE_SIZE - 1)
            )
            if gerencia:
                query = query.eq("gerencia", gerencia)

            resp = query.execute()
            pagina = resp.data or []
            registros.extend(pagina)
            if len(pagina) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        if not registros:
            return pd.DataFrame()

        df = pd.DataFrame(registros)
        for col in _COLS_DATA:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        for col in _COLS_NUM:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "thp_min" in df.columns:
            df["thp_min"] = df["thp_min"].fillna(0)
        for col in _COLS_BOOL:
            if col in df.columns:
                df[col] = df[col].fillna(False).astype(bool)
        return df

    except Exception as e:
        st.error(f"❌ Erro ao buscar base congelada 2025 ({gerencia}): {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_baseline_cached(gerencia: str | None = None) -> pd.DataFrame:
    """Versão cacheada (5 min) de get_baseline_gerencia para as telas."""
    return get_baseline_gerencia(gerencia)


def invalidar_cache_baseline() -> None:
    """Limpa o cache do congelado após upload/exclusão (mesmo padrão do RASF)."""
    get_baseline_cached.clear()
    st.toast("🔄 Cache da base congelada 2025 atualizado.", icon="✅")
