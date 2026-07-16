# database/queries_rasf.py
# Queries de acesso à tabela `rasf_ee` (export RASF de Eletroeletrônica).
# Sprint 6 — espelha o padrão anti-duplicação de database/queries.py.

import streamlit as st
import pandas as pd
from database.client import get_supabase

# Disciplina usada em uploads_historico para os uploads do RASF.
DISCIPLINA_RASF = "RASF"

_COLS_DATA = ["data_nota", "ultima_data_ativo", "ultima_data_sintoma", "criado_em"]
_COLS_NUM = [
    "ano", "mes", "numero_nota", "dias_ultima_falha_ativo",
    "dias_ultima_falha_sintoma", "thp_min", "thp_num_eventos", "thp_min_133",
]
_COLS_BOOL = [
    "reincidencia_ativo", "reincidencia_sintoma", "gerador_thp",
    "impacta_confiabilidade", "gatilho_analise", "rca_preenchida",
    "lacuna_rca", "pendente",
]


def _upload_ids_ativos_rasf(gerencia: str | None = None) -> list[str]:
    """IDs de uploads RASF com status 'ativo' (base da leitura anti-duplicação)."""
    try:
        supabase = get_supabase()
        q = (
            supabase.table("uploads_historico")
            .select("id")
            .eq("disciplina", DISCIPLINA_RASF)
            .eq("status", "ativo")
        )
        if gerencia:
            q = q.eq("gerencia", gerencia)
        resp = q.execute()
        return [r["id"] for r in (resp.data or [])]
    except Exception:
        return []


def get_rasf_gerencia(gerencia: str | None = None) -> pd.DataFrame:
    """
    Busca as linhas RASF ativas.

    Args:
        gerencia: 'SP', 'VP' ou None (ambas — Visão Global).

    Returns:
        DataFrame canônico (mesmas colunas do core.parser_rasf), ou vazio.
    """
    try:
        supabase = get_supabase()

        upload_ids = _upload_ids_ativos_rasf(gerencia)
        if not upload_ids:
            return pd.DataFrame()

        PAGE_SIZE = 1000
        registros: list[dict] = []
        offset = 0
        while True:
            query = (
                supabase.table("rasf_ee")
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
        st.error(f"❌ Erro ao buscar RASF ({gerencia}): {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_rasf_cached(gerencia: str | None = None) -> pd.DataFrame:
    """Versão cacheada (5 min) de get_rasf_gerencia para as telas."""
    return get_rasf_gerencia(gerencia)


@st.cache_data(ttl=300, show_spinner=False)
def carregar_gatilhos_analise() -> set[str]:
    """
    Lê de `configuracoes` (gerencia=NULL, chave='rasf_gatilhos_analise') os
    valores de "(Eng) Gatilho" que caracterizam Gatilho de Análise de Falhas
    (PG-ENG-0088, seção 6.4.1). O procedimento diz que essa regra muda por
    ciclo de metas da Coordenação — por isso fica em `configuracoes`
    (editável sem deploy) em vez de fixa no parser.

    Falha graciosa: sem config no banco (ou erro de conexão), cai no padrão
    `core.parser_rasf.GATILHOS_ANALISE_PADRAO`.
    """
    from core.parser_rasf import GATILHOS_ANALISE_PADRAO
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("configuracoes")
            .select("valor")
            .is_("gerencia", "null")
            .eq("chave", "rasf_gatilhos_analise")
            .execute()
        )
        if resp.data:
            valor = resp.data[0]["valor"]
            if isinstance(valor, list) and valor:
                return set(str(v) for v in valor)
    except Exception:
        pass
    return set(GATILHOS_ANALISE_PADRAO)


@st.cache_data(ttl=300, show_spinner=False)
def carregar_overrides_origem_categoria() -> dict[str, str]:
    """
    Lê de `configuracoes` (chave='rasf_origem_categoria_overrides') o mapa
    de reclassificação exata Obras/Manutenção para valores de "Descrição
    da Origem da Atividade" que a regra automática de substring (ver
    core.parser_rasf.classificar_origem_atividade) não classifica bem
    (ex.: "MECÂNICA", "TRILHO OXIDADO").

    Falha graciosa: sem config ou erro de conexão, retorna {} (só a regra
    automática se aplica).
    """
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("configuracoes")
            .select("valor")
            .is_("gerencia", "null")
            .eq("chave", "rasf_origem_categoria_overrides")
            .execute()
        )
        if resp.data:
            valor = resp.data[0]["valor"]
            if isinstance(valor, dict):
                return {str(k): str(v) for k, v in valor.items()}
    except Exception:
        pass
    return {}


def invalidar_cache_rasf() -> None:
    """
    Força limpeza do cache RASF (get_rasf_cached).
    Deve ser chamada após upload ou exclusão de dados RASF para garantir
    dados frescos nas telas — mesmo padrão de database.queries.invalidar_cache_notas.

    Uso:
        from database.queries_rasf import invalidar_cache_rasf
        invalidar_cache_rasf()
    """
    get_rasf_cached.clear()
    st.toast("🔄 Cache RASF atualizado.", icon="✅")
