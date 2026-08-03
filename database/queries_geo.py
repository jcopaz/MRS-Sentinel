# database/queries_geo.py
# Leitura da tabela de referência `geo_marcos` (marcos de KM da malha, KMZ).
# Sprint 6 — geografia real.
#
# É a FONTE ALTERNATIVA à data/geo_marcos.csv embarcado. `core.geo` usa o CSV
# por padrão (funciona offline e sem seed); quem preferir servir a referência
# pelo Supabase pode chamar `get_geo_marcos_cached()` e alimentar
# `core.geo._montar_lookups`.

import pandas as pd
import streamlit as st

try:
    from database.client import get_supabase
except Exception:  # pragma: no cover
    def get_supabase():
        raise RuntimeError("Supabase client indisponível")


@st.cache_data(ttl=3600, show_spinner=False)
def get_geo_marcos_cached() -> pd.DataFrame:
    """
    Devolve a referência geográfica da tabela `geo_marcos`.

    Returns:
        DataFrame [trecho, origem, destino, lat, lon, km, n_marcos] — ou vazio
        se a tabela não existir / Supabase indisponível (o app cai no CSV).
    """
    try:
        supabase = get_supabase()
        PAGE = 1000
        regs: list[dict] = []
        ini = 0
        while True:
            resp = (supabase.table("geo_marcos")
                    .select("trecho,origem,destino,lat,lon,km,n_marcos")
                    .range(ini, ini + PAGE - 1)
                    .execute())
            lote = resp.data or []
            regs.extend(lote)
            if len(lote) < PAGE:
                break
            ini += PAGE
        if not regs:
            return pd.DataFrame(
                columns=["trecho", "origem", "destino", "lat", "lon", "km", "n_marcos"])
        df = pd.DataFrame(regs)
        for c in ("lat", "lon", "km", "n_marcos"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame(
            columns=["trecho", "origem", "destino", "lat", "lon", "km", "n_marcos"])


def invalidar_cache_geo():
    """Limpa o cache da referência geográfica (após reseed)."""
    try:
        get_geo_marcos_cached.clear()
    except Exception:
        pass
