# database/queries_trecho.py — Bases versionadas do trecho Itirapina–Pederneiras
#
# Schema: database/schema_itirapina.sql (rodar manualmente no Supabase).
# Nomes lógicos no código ('defeitos_via', 'trecho_bases'...); a tabela
# física leva o PREFIXO itp_ (isolamento do trecho).
#
# Regras:
#   - Toda carga pertence a uma BASE (trecho_bases.data_base). Os
#     substituir_* apagam e regravam só dentro do base_id.
#   - Base congelada = somente leitura: qualquer escrita levanta
#     BaseCongelada. Corrigir dado = criar base nova. Não há descongelar.
#   - transit_time é série contínua (sem base): upsert pela chave única.

from datetime import date, datetime

import pandas as pd
import streamlit as st

from database.client import get_supabase
from database.queries_prospeccao import PREFIXO, TabelaAusente, _tabela_ausente, _json_safe

TABELAS_POR_BASE = (
    "prospeccao_dormentes", "relatorio_velocidade", "prospeccao_lastro",
    "prospeccao_fixacao", "prospeccao_trilho", "defeitos_via",
    "inspecoes_campo", "inspecao_midias",
)


class BaseCongelada(Exception):
    """Tentativa de escrita numa base congelada (somente leitura)."""


# region ====================== SESSÃO 1: Helpers ==============================

def _paginar(montar_query, tabela: str) -> pd.DataFrame:
    """Lê tudo em páginas de 1000 (limite do PostgREST)."""
    linhas, inicio, passo = [], 0, 1000
    try:
        while True:
            lote = montar_query().range(inicio, inicio + passo - 1).execute().data or []
            linhas.extend(lote)
            if len(lote) < passo:
                break
            inicio += passo
    except Exception as e:
        if _tabela_ausente(e, tabela):
            raise TabelaAusente(tabela) from e
        raise
    return pd.DataFrame(linhas)


def _registros(df: pd.DataFrame, extras: dict | None = None) -> list[dict]:
    """DataFrame → lista de dicts JSON-safe (datas ISO, NaN → None, bytes → bytea)."""
    out = []
    for rec in df.to_dict(orient="records"):
        r = {}
        for k, v in rec.items():
            if v is None or v is pd.NA or v is pd.NaT:
                r[k] = None
            elif isinstance(v, (dict, list)):
                r[k] = v
            elif isinstance(v, (bytes, bytearray)):
                r[k] = "\\x" + bytes(v).hex()
            elif isinstance(v, (datetime, pd.Timestamp)):
                r[k] = None if pd.isna(v) else v.isoformat()
            else:
                r[k] = _json_safe(v)
        if extras:
            r.update(extras)
        out.append(r)
    return out


def _inserir(tabela: str, registros: list[dict], lote: int = 500) -> None:
    supabase = get_supabase()
    for i in range(0, len(registros), lote):
        supabase.table(PREFIXO + tabela).insert(registros[i:i + lote]).execute()


def limpar_caches() -> None:
    for f in (get_bases, get_por_base, get_transit_time, get_referencia,
              get_indicadores, get_repositorios_midia):
        f.clear()

# endregion


# region ====================== SESSÃO 2: Bases ================================

@st.cache_data(ttl=120, show_spinner=False)
def get_bases(trecho: str) -> pd.DataFrame:
    """Bases do trecho, mais antiga → mais recente."""
    supabase = get_supabase()
    df = _paginar(lambda: supabase.table(PREFIXO + "trecho_bases").select("*")
                  .eq("trecho", trecho).order("data_base"), "trecho_bases")
    if not df.empty:
        df["data_base"] = pd.to_datetime(df["data_base"]).dt.date
    return df


def base_congelada(base_id: int) -> bool:
    """Consulta direta (sem cache) — usada antes de qualquer escrita."""
    resp = (get_supabase().table(PREFIXO + "trecho_bases").select("congelada")
            .eq("id", base_id).limit(1).execute())
    return bool(resp.data and resp.data[0].get("congelada"))


def exigir_base_aberta(base_id: int | None) -> None:
    if base_id is not None and base_congelada(base_id):
        raise BaseCongelada(f"Base {base_id} está congelada (somente leitura).")


def criar_base(trecho: str, data_base: date, descricao: str | None,
               usuario_id: str | None, marco_zero: bool = False) -> int:
    """Cria a base (ou devolve a existente com a mesma data)."""
    supabase = get_supabase()
    existente = (supabase.table(PREFIXO + "trecho_bases").select("id").eq("trecho", trecho)
                 .eq("data_base", data_base.isoformat()).limit(1).execute())
    if existente.data:
        return int(existente.data[0]["id"])
    resp = supabase.table(PREFIXO + "trecho_bases").insert({
        "trecho": trecho, "data_base": data_base.isoformat(), "descricao": descricao,
        "marco_zero": marco_zero, "congelada": False, "criado_por": usuario_id,
    }).execute()
    get_bases.clear()
    return int(resp.data[0]["id"])


def congelar_base(base_id: int) -> bool:
    get_supabase().table(PREFIXO + "trecho_bases").update({"congelada": True}).eq("id", base_id).execute()
    get_bases.clear()
    return True

# endregion


# region ====================== SESSÃO 3: Dados por base =======================

@st.cache_data(ttl=300, show_spinner=False)
def get_por_base(tabela: str, base_id: int, colunas: str = "*") -> pd.DataFrame:
    if tabela not in TABELAS_POR_BASE:
        raise ValueError(f"Tabela sem base: {tabela}")
    supabase = get_supabase()
    return _paginar(lambda: supabase.table(PREFIXO + tabela).select(colunas)
                    .eq("base_id", base_id).order("id"), tabela)


def substituir_por_base(tabela: str, base_id: int, df: pd.DataFrame,
                        extras: dict | None = None) -> int:
    """Apaga a tabela dentro da base e insere o df. Bloqueia base congelada."""
    if tabela not in TABELAS_POR_BASE:
        raise ValueError(f"Tabela sem base: {tabela}")
    exigir_base_aberta(base_id)
    registros = _registros(df, {"base_id": base_id, **(extras or {})})
    try:
        get_supabase().table(PREFIXO + tabela).delete().eq("base_id", base_id).execute()
        _inserir(tabela, registros)
    except Exception as e:
        if _tabela_ausente(e, tabela):
            raise TabelaAusente(tabela) from e
        raise
    get_por_base.clear()
    return len(registros)


def substituir_inspecao(base_id: int, insp: pd.DataFrame, midias: pd.DataFrame) -> tuple[int, int]:
    """
    Grava inspeções e mídias da base. As mídias são ligadas pelo msg_n (o id
    da inspeção só existe depois do insert).
    """
    exigir_base_aberta(base_id)
    supabase = get_supabase()
    try:
        supabase.table(PREFIXO + "inspecao_midias").delete().eq("base_id", base_id).execute()
        supabase.table(PREFIXO + "inspecoes_campo").delete().eq("base_id", base_id).execute()
        _inserir("inspecoes_campo", _registros(insp, {"base_id": base_id}))
        ids = _paginar(lambda: supabase.table(PREFIXO + "inspecoes_campo").select("id,msg_n")
                       .eq("base_id", base_id).order("id"), "inspecoes_campo")
        mapa = dict(zip(ids["msg_n"], ids["id"])) if not ids.empty else {}
        m = midias.copy()
        if not m.empty:
            m["inspecao_id"] = m["msg_n"].map(mapa)
        _inserir("inspecao_midias", _registros(m, {"base_id": base_id}))
    except Exception as e:
        for t in ("inspecoes_campo", "inspecao_midias"):
            if _tabela_ausente(e, t):
                raise TabelaAusente(t) from e
        raise
    get_por_base.clear()
    return len(insp), len(midias)

# endregion


# region ====================== SESSÃO 4: Transit time (sem base) ==============

@st.cache_data(ttl=300, show_spinner=False)
def get_transit_time() -> pd.DataFrame:
    supabase = get_supabase()
    return _paginar(lambda: supabase.table(PREFIXO + "transit_time").select("*").order("partida"),
                    "transit_time")


def upsert_transit_time(df: pd.DataFrame) -> int:
    registros = _registros(df)
    try:
        supabase = get_supabase()
        for i in range(0, len(registros), 500):
            supabase.table(PREFIXO + "transit_time").upsert(
                registros[i:i + 500], on_conflict="trem,patio_a,patio_b,partida").execute()
    except Exception as e:
        if _tabela_ausente(e, "transit_time"):
            raise TabelaAusente("transit_time") from e
        raise
    get_transit_time.clear()
    return len(registros)

# endregion


# region ====================== SESSÃO 5: Referências e indicadores ============

@st.cache_data(ttl=3600, show_spinner=False)
def get_referencia(tabela: str, trecho: str | None = None) -> pd.DataFrame:
    """trecho_estacoes / limites_geometria / trecho_pontos_criticos."""
    if tabela not in ("trecho_estacoes", "limites_geometria", "trecho_pontos_criticos"):
        raise ValueError(tabela)
    supabase = get_supabase()

    def q():
        b = supabase.table(PREFIXO + tabela).select("*")
        return b.eq("trecho", trecho) if trecho and tabela != "limites_geometria" else b
    return _paginar(q, tabela)


@st.cache_data(ttl=300, show_spinner=False)
def get_indicadores(base_ids: tuple) -> pd.DataFrame:
    supabase = get_supabase()
    return _paginar(lambda: supabase.table(PREFIXO + "trecho_indicadores").select("*")
                    .in_("base_id", list(base_ids)).order("id"), "trecho_indicadores")


def salvar_indicadores(base_id: int, df: pd.DataFrame) -> int:
    """Upsert da foto de indicadores. Base congelada não muda."""
    exigir_base_aberta(base_id)
    registros = _registros(df, {"base_id": base_id,
                                "calculado_em": datetime.utcnow().isoformat()})
    supabase = get_supabase()
    for i in range(0, len(registros), 500):
        supabase.table(PREFIXO + "trecho_indicadores").upsert(
            registros[i:i + 500], on_conflict="base_id,escopo,chave,indicador").execute()
    get_indicadores.clear()
    return len(registros)


@st.cache_data(ttl=300, show_spinner=False)
def get_repositorios_midia(trecho: str) -> pd.DataFrame:
    supabase = get_supabase()
    return _paginar(lambda: supabase.table(PREFIXO + "midias_repositorio").select("*")
                    .eq("trecho", trecho).order("id"), "midias_repositorio")


def salvar_repositorio_midia(trecho: str, nome: str, base_url: str, tipo: str) -> None:
    get_supabase().table(PREFIXO + "midias_repositorio").upsert(
        {"trecho": trecho, "nome": nome, "base_url": base_url, "tipo": tipo, "ativo": True},
        on_conflict="trecho,nome").execute()
    get_repositorios_midia.clear()

# endregion
