# database/queries_prospeccao.py — Tabela `prospeccao_dormentes` + acesso à aba
#
# Schema: database/schema_itirapina.sql (rodar manualmente no Supabase).
# Todas as tabelas do trecho têm prefixo itp_ (PREFIXO) — isoladas das
# tabelas da malha MRS; os dados aqui são do formato Rumo (transição).
# Acesso à aba: lista de e-mails na config global
# `acesso_prospeccao_itirapina` (editada no Painel Admin → Configurações).

from datetime import date, datetime

import numpy as np
import pandas as pd
import streamlit as st

from database.client import get_supabase
from database.queries import get_config

PREFIXO = "itp_"  # tabelas do trecho Itirapina–Pederneiras: isoladas da malha MRS
TABELA = PREFIXO + "prospeccao_dormentes"
TRECHO_ITIRAPINA = "Itirapina-Triagem"
CHAVE_ACESSO_PROSPECCAO = "acesso_prospeccao_itirapina"


# region ====================== SESSÃO 1: Acesso =============================

@st.cache_data(ttl=120, show_spinner=False)
def get_emails_acesso_prospeccao() -> list[str]:
    """E-mails liberados pelo admin (sem o dono, que é fixo em permissions)."""
    valor = get_config(None, CHAVE_ACESSO_PROSPECCAO, [])
    if not isinstance(valor, list):
        return []
    return sorted({str(e).strip().lower() for e in valor if str(e).strip()})


def invalidar_cache_acesso():
    get_emails_acesso_prospeccao.clear()

# endregion


# region ====================== SESSÃO 2: Leitura / Escrita ===================

class TabelaAusente(Exception):
    """schema_itirapina.sql ainda não foi rodado no Supabase."""


def _tabela_ausente(e: Exception, tabela: str = TABELA) -> bool:
    msg = str(e).lower()
    return tabela in msg and ("does not exist" in msg or "not find" in msg or "42p01" in msg)


@st.cache_data(ttl=300, show_spinner=False)
def get_prospeccao(trecho: str, base_id: int | None = None) -> pd.DataFrame:
    """Segmentos do trecho; com base_id, só os daquela base (marco zero etc.)."""
    supabase = get_supabase()
    linhas, inicio, passo = [], 0, 1000
    try:
        while True:
            q = supabase.table(TABELA).select("*").eq("trecho", trecho)
            if base_id is not None:
                q = q.eq("base_id", base_id)
            resp = (q.order("km_inicio")
                    .range(inicio, inicio + passo - 1)
                    .execute())
            lote = resp.data or []
            linhas.extend(lote)
            if len(lote) < passo:
                break
            inicio += passo
    except Exception as e:
        if _tabela_ausente(e):
            raise TabelaAusente() from e
        raise
    return pd.DataFrame(linhas)


def _json_safe(v):
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        if np.isnan(v):
            return None
        # Coluna inteira com célula vazia vira float no pandas (96 → 96.0) e o
        # Postgres recusa "96.0" em INT/SMALLINT; valor inteiro vai como int.
        return int(v) if float(v).is_integer() else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (date, datetime, pd.Timestamp)):
        return None if pd.isna(v) else v.isoformat()[:10]
    return v


def substituir_prospeccao(trecho: str, df: pd.DataFrame, usuario_id: str | None,
                          base_id: int | None = None) -> int:
    """
    Apaga os segmentos do trecho (só dentro da base, se base_id vier) e insere
    os do arquivo. Retorna qtd inserida. Base congelada levanta BaseCongelada.
    Não é transacional (PostgREST); se o insert falhar, a base fica vazia
    até o próximo upload — aceitável para uma base de referência pequena.
    """
    if base_id is not None:
        from database.queries_trecho import exigir_base_aberta
        exigir_base_aberta(base_id)
    supabase = get_supabase()
    agora = datetime.utcnow().isoformat()
    registros = []
    for rec in df.to_dict(orient="records"):
        r = {k: _json_safe(v) for k, v in rec.items()}
        r["trecho"] = trecho
        r["enviado_por"] = usuario_id
        r["enviado_em"] = agora
        if base_id is not None:
            r["base_id"] = base_id
        registros.append(r)
    try:
        q = supabase.table(TABELA).delete().eq("trecho", trecho)
        (q.eq("base_id", base_id) if base_id is not None else q).execute()
        for i in range(0, len(registros), 500):
            supabase.table(TABELA).insert(registros[i:i + 500]).execute()
    except Exception as e:
        if _tabela_ausente(e):
            raise TabelaAusente() from e
        raise
    get_prospeccao.clear()
    return len(registros)

# endregion


# region ====================== SESSÃO 3: Relatório de Velocidade (SRM) =======

TABELA_VEL = PREFIXO + "relatorio_velocidade"


@st.cache_data(ttl=300, show_spinner=False)
def get_relatorio_velocidade(base_id: int | None = None) -> pd.DataFrame:
    """Rotas carregadas (poucos milhares de linhas); com base_id, só as da base."""
    supabase = get_supabase()
    linhas, inicio, passo = [], 0, 1000
    try:
        while True:
            q = supabase.table(TABELA_VEL).select("*")
            if base_id is not None:
                q = q.eq("base_id", base_id)
            resp = (q.order("id").range(inicio, inicio + passo - 1).execute())
            lote = resp.data or []
            linhas.extend(lote)
            if len(lote) < passo:
                break
            inicio += passo
    except Exception as e:
        if _tabela_ausente(e, TABELA_VEL):
            raise TabelaAusente() from e
        raise
    return pd.DataFrame(linhas)


def substituir_relatorio_velocidade(rota: str, exportado, df: pd.DataFrame,
                                    usuario_id: str | None, base_id: int | None = None) -> int:
    """Apaga a rota (dentro da base, se vier) e insere o relatório lido do PDF."""
    if base_id is not None:
        from database.queries_trecho import exigir_base_aberta
        exigir_base_aberta(base_id)
    supabase = get_supabase()
    agora = datetime.utcnow().isoformat()
    exp = exportado.isoformat() if exportado is not None else None
    registros = []
    for rec in df.to_dict(orient="records"):
        r = {}
        for k, v in rec.items():
            if isinstance(v, (datetime, pd.Timestamp)):
                r[k] = None if pd.isna(v) else v.isoformat()
            else:
                r[k] = _json_safe(v)
        r.update(rota=rota, data_exportacao=exp, enviado_por=usuario_id, enviado_em=agora)
        if base_id is not None:
            r["base_id"] = base_id
        registros.append(r)
    try:
        q = supabase.table(TABELA_VEL).delete().eq("rota", rota)
        (q.eq("base_id", base_id) if base_id is not None else q).execute()
        for i in range(0, len(registros), 500):
            supabase.table(TABELA_VEL).insert(registros[i:i + 500]).execute()
    except Exception as e:
        if _tabela_ausente(e, TABELA_VEL):
            raise TabelaAusente() from e
        raise
    get_relatorio_velocidade.clear()
    return len(registros)

# endregion
