# =============================================================================
# database/queries_snapshots.py — Sprint 8 (Memória & Comparações)
#
# Acesso à tabela `snapshots` (fotos semanais agregadas da base viva de notas).
#   • upsert_snapshots(df)  — grava/atualiza a semana corrente (anti-duplicação
#                             por 'chave' — regrava a mesma semana sem duplicar).
#   • get_snapshots(...)    — leitura paginada para os comparativos (período ×
#                             período) e o dashboard "Evolução da Malha".
# Espelha o padrão de database/queries_baseline.py.
# =============================================================================

import pandas as pd

try:
    import streamlit as st
except Exception:  # pragma: no cover — permite import fora do Streamlit (e2e)
    st = None

from database.client import get_supabase

_COLS_NUM = [
    "ano", "semana", "total_notas", "notas_abertas", "aberturas_periodo",
    "encerramentos_periodo", "thp_acumulado", "score_medio",
    "notas_cronicas", "pct_cronico", "reincidentes",
]


def upsert_snapshots(df: pd.DataFrame) -> int:
    """
    Upsert das linhas do snapshot semanal. Usa on_conflict='chave' — se a foto
    da semana já existe (regravação a cada upload), ATUALIZA em vez de duplicar.

    Returns:
        Número de linhas enviadas (0 se df vazio ou falha).
    """
    if df is None or df.empty:
        return 0

    registros = df.where(pd.notnull(df), None).to_dict(orient="records")
    if not registros:
        return 0

    try:
        supabase = get_supabase()
        LOTE = 500
        enviados = 0
        for i in range(0, len(registros), LOTE):
            bloco = registros[i:i + LOTE]
            supabase.table("snapshots").upsert(
                bloco, on_conflict="chave",
            ).execute()
            enviados += len(bloco)
        return enviados
    except Exception:
        return 0


def _get_snapshots_impl(gerencia: str | None = None,
                        disciplina: str | None = None,
                        semana_iso: str | None = None) -> pd.DataFrame:
    """Busca paginada de snapshots (sem cache — usada pelo wrapper cacheado)."""
    try:
        supabase = get_supabase()
        PAGE = 1000
        registros: list[dict] = []
        offset = 0
        while True:
            q = supabase.table("snapshots").select("*")
            if gerencia:
                q = q.eq("gerencia", gerencia)
            if disciplina:
                q = q.eq("disciplina", disciplina)
            if semana_iso:
                q = q.eq("semana_iso", semana_iso)
            resp = q.range(offset, offset + PAGE - 1).execute()
            dados = resp.data or []
            registros.extend(dados)
            if len(dados) < PAGE:
                break
            offset += PAGE

        df = pd.DataFrame(registros)
        for c in _COLS_NUM:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "data_ref" in df.columns:
            df["data_ref"] = pd.to_datetime(df["data_ref"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


if st is not None:
    @st.cache_data(ttl=300, show_spinner=False)
    def get_snapshots(gerencia: str | None = None,
                      disciplina: str | None = None,
                      semana_iso: str | None = None) -> pd.DataFrame:
        return _get_snapshots_impl(gerencia, disciplina, semana_iso)
else:  # pragma: no cover
    def get_snapshots(gerencia: str | None = None,
                      disciplina: str | None = None,
                      semana_iso: str | None = None) -> pd.DataFrame:
        return _get_snapshots_impl(gerencia, disciplina, semana_iso)
