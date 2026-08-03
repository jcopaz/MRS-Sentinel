# core/geo.py — Geografia real da malha MRS (Sprint 6)
#
# Fonte: Marcos_KM_Malha_MRS.kmz (2.298 marcos de KM georreferenciados). O KMZ
# foi pré-processado em data/geo_marcos.csv, agregado no nível
# (trecho, origem, destino) — a chave mais fina que o decodificador de TPLNR
# (core.glossarios.decodificar_tplnr) consegue extrair tanto das notas quanto
# do RASF. Cada linha traz lat/lon (mediana dos marcos do segmento) e km real.
#
# Uso:
#   from core.geo import enriquecer_geo
#   df = enriquecer_geo(df)          # adiciona colunas lat, lon, km_real, geo_fonte
#
# Retrocompatível: onde não há marco (ramal fora do KMZ), lat/lon ficam NaN e o
# consumidor cai no comportamento antigo (ex.: _criar_km_sequencial no unifilar).

from __future__ import annotations

import os

import numpy as np
import pandas as pd

try:
    import streamlit as st
    _HAS_ST = True
except Exception:  # pragma: no cover
    _HAS_ST = False

try:
    from core.glossarios import decodificar_tplnr, normalizar_ramal
except Exception:  # pragma: no cover - fallback defensivo p/ testes isolados
    import re

    _PAD = re.compile(
        r"MF-(?P<trecho>[A-Z0-9]+)-"
        r"(?P<origem>[A-Z0-9]+)_(?P<destino>[A-Z0-9]+)"
    )

    def decodificar_tplnr(s):
        if not s:
            return {}
        m = _PAD.match(str(s))
        return m.groupdict() if m else {}

    def normalizar_ramal(s):
        return str(s).strip().upper() if s else s


_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CSV_PATH = os.path.join(_DATA_DIR, "geo_marcos.csv")
_CSV_KM_PATH = os.path.join(_DATA_DIR, "geo_km.csv")
_CSV_TRACADO_PATH = os.path.join(_DATA_DIR, "geo_tracado.csv")


# region ====================== SESSÃO 1: Carregamento da referência ===========

def _carregar_ref_raw() -> pd.DataFrame:
    """Lê data/geo_marcos.csv. Retorna DataFrame vazio (com colunas) se ausente."""
    cols = ["trecho", "origem", "destino", "lat", "lon", "km", "n_marcos"]
    try:
        df = pd.read_csv(_CSV_PATH)
    except Exception:
        return pd.DataFrame(columns=cols)
    for c in ("lat", "lon", "km", "n_marcos"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("trecho", "origem", "destino"):
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip().str.upper()
    return df


if _HAS_ST:
    @st.cache_data(ttl=3600, show_spinner=False)
    def carregar_ref_geo() -> dict:
        """Versão cacheada — devolve os mapas de lookup prontos."""
        return _montar_lookups(_carregar_ref_raw())
else:  # pragma: no cover
    def carregar_ref_geo() -> dict:
        return _montar_lookups(_carregar_ref_raw())


def _montar_lookups(ref: pd.DataFrame) -> dict:
    """
    Constrói dois níveis de lookup a partir da referência:
      • fino:    (trecho, origem, destino) -> (lat, lon, km)
      • pátio:   (trecho, origem)          -> (lat, lon, km)  [mediana dos destinos]
    O consumidor tenta o fino primeiro e cai no de pátio.
    """
    fino: dict[tuple, tuple] = {}
    patio: dict[tuple, tuple] = {}
    if ref is None or ref.empty:
        return {"fino": fino, "patio": patio, "n": 0}

    for _, r in ref.iterrows():
        t, o, d = r.get("trecho"), r.get("origem"), r.get("destino")
        lat, lon, km = r.get("lat"), r.get("lon"), r.get("km")
        if pd.notna(lat) and pd.notna(lon):
            fino[(t, o, d)] = (float(lat), float(lon),
                               float(km) if pd.notna(km) else np.nan)

    ag = (ref.dropna(subset=["lat", "lon"])
             .groupby(["trecho", "origem"])
             .agg(lat=("lat", "median"), lon=("lon", "median"), km=("km", "median")))
    for (t, o), r in ag.iterrows():
        patio[(t, o)] = (float(r["lat"]), float(r["lon"]),
                         float(r["km"]) if pd.notna(r["km"]) else np.nan)

    return {"fino": fino, "patio": patio, "n": len(fino)}

# endregion


# region ============ SESSÃO 1B: Referência por KM + Traçado da via =============
# Fonte fina: cada marco de KM do KMZ (~1/1 km). Permite posicionar a nota no
# ponto EXATO por (ramal, km) — usada para notas VP, que carregam km_real.

def _carregar_ref_km_raw() -> pd.DataFrame:
    cols = ["ramal", "km", "lat", "lon", "n"]
    try:
        df = pd.read_csv(_CSV_KM_PATH)
    except Exception:
        return pd.DataFrame(columns=cols)
    for c in ("km", "lat", "lon", "n"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "ramal" in df.columns:
        df["ramal"] = df["ramal"].astype(str).str.strip().str.upper()
    return df.dropna(subset=["ramal", "km", "lat", "lon"])


def _montar_km(ref: pd.DataFrame) -> dict:
    """
    {ramal: {'km': np.array ordenado, 'lat': np.array, 'lon': np.array}}
    para interpolação linear rápida por KM.
    """
    out: dict[str, dict] = {}
    if ref is None or ref.empty:
        return out
    for ramal, sub in ref.sort_values("km").groupby("ramal"):
        out[ramal] = {
            "km": sub["km"].to_numpy(dtype=float),
            "lat": sub["lat"].to_numpy(dtype=float),
            "lon": sub["lon"].to_numpy(dtype=float),
        }
    return out


def _carregar_tracado_raw() -> pd.DataFrame:
    cols = ["ramal", "linha", "km", "lat", "lon"]
    try:
        df = pd.read_csv(_CSV_TRACADO_PATH)
    except Exception:
        return pd.DataFrame(columns=cols)
    for c in ("km", "lat", "lon"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("ramal", "linha"):
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip().str.upper()
    return df.dropna(subset=["ramal", "linha", "km", "lat", "lon"])


if _HAS_ST:
    @st.cache_data(ttl=3600, show_spinner=False)
    def carregar_ref_km() -> dict:
        return _montar_km(_carregar_ref_km_raw())

    @st.cache_data(ttl=3600, show_spinner=False)
    def carregar_tracado() -> list:
        return _montar_tracado(_carregar_tracado_raw())
else:  # pragma: no cover
    def carregar_ref_km() -> dict:
        return _montar_km(_carregar_ref_km_raw())

    def carregar_tracado() -> list:
        return _montar_tracado(_carregar_tracado_raw())


def _montar_tracado(df: pd.DataFrame) -> list:
    """
    Lista de polilinhas: [{'ramal','linha','coords':[(lat,lon),...]}, ...],
    ordenadas por KM. Só linhas com >= 2 vértices.
    """
    polis = []
    if df is None or df.empty:
        return polis
    for (ramal, linha), sub in df.sort_values("km").groupby(["ramal", "linha"]):
        coords = list(zip(sub["lat"].astype(float), sub["lon"].astype(float)))
        if len(coords) >= 2:
            polis.append({"ramal": ramal, "linha": linha, "coords": coords})
    return polis


def geo_por_km(ramal, km, ref_km: dict | None = None) -> tuple:
    """
    Posição EXATA por interpolação linear entre marcos de KM do ramal.

    Retorna (lat, lon, 'km') ou (nan, nan, None) se o ramal não tiver marcos
    ou o KM cair fora da faixa coberta (sem extrapolar).
    """
    rk = ref_km if ref_km is not None else carregar_ref_km()
    r = normalizar_ramal(ramal) if ramal else ramal
    r = r.upper() if isinstance(r, str) else r
    dados = rk.get(r)
    try:
        km = float(km)
    except Exception:
        return np.nan, np.nan, None
    if not dados or pd.isna(km):
        return np.nan, np.nan, None
    kms = dados["km"]
    if km < kms.min() or km > kms.max():
        # Fora da faixa coberta — não extrapola (evita ponto fantasma).
        return np.nan, np.nan, None
    lat = float(np.interp(km, kms, dados["lat"]))
    lon = float(np.interp(km, kms, dados["lon"]))
    return lat, lon, "km"

# endregion


# region ====================== SESSÃO 2: Enriquecimento ========================

def _chaves_do_tplnr(tplnr) -> tuple:
    """(trecho, origem, destino) a partir de um TPLNR (via decodificar_tplnr)."""
    d = decodificar_tplnr(tplnr) or {}
    t = d.get("trecho")
    t = normalizar_ramal(t) if t else t
    return (t.upper() if isinstance(t, str) else t,
            (d.get("origem") or "").upper() or None,
            (d.get("destino") or "").upper() or None)


def _chaves_de_colunas(ramal, origem) -> tuple:
    """(trecho, origem) a partir das colunas já normalizadas ramal/origem."""
    t = normalizar_ramal(ramal) if ramal else ramal
    return (t.upper() if isinstance(t, str) else t,
            (str(origem).upper() if origem is not None and str(origem) != "nan" else None))


def _up(v):
    """Uppercase seguro, tratando None/NaN."""
    if v is None:
        return None
    s = str(v).strip()
    return s.upper() if s and s.lower() != "nan" else None


def geo_lookup_cols(trecho=None, origem=None, destino=None,
                    lookups: dict | None = None) -> tuple:
    """
    Resolve (lat, lon, km, fonte) usando as colunas NATIVAS da nota
    (trecho / origem / destino) — que já vêm decodificadas do parser e
    compartilham o mesmo vocabulário da referência geo (ACL, ADP, ...).

    É a via preferencial quando a nota não traz o TPLNR no formato MF- e o
    `ramal` está na sigla canônica (SJU, JIT...), diferente do código de trecho.
    """
    lk = lookups or carregar_ref_geo()
    fino, patio = lk["fino"], lk["patio"]
    t, o, d = _up(trecho), _up(origem), _up(destino)
    if t is not None:
        if (t, o, d) in fino:
            lat, lon, km = fino[(t, o, d)]
            return lat, lon, km, "segmento"
        if (t, o) in patio:
            lat, lon, km = patio[(t, o)]
            return lat, lon, km, "patio"
    return np.nan, np.nan, np.nan, None


def geo_lookup(tplnr=None, ramal=None, origem=None, lookups: dict | None = None) -> tuple:
    """
    Resolve (lat, lon, km, fonte) para uma falha/nota.

    Estratégia em cascata:
      1. TPLNR -> (trecho, origem, destino)  [mais preciso]
      2. TPLNR -> (trecho, origem)           [nível pátio]
      3. colunas ramal+origem -> (trecho, origem)
    Retorna (nan, nan, nan, None) se nada casar.
    """
    lk = lookups or carregar_ref_geo()
    fino, patio = lk["fino"], lk["patio"]

    if tplnr:
        t, o, d = _chaves_do_tplnr(tplnr)
        if (t, o, d) in fino:
            lat, lon, km = fino[(t, o, d)]
            return lat, lon, km, "segmento"
        if (t, o) in patio:
            lat, lon, km = patio[(t, o)]
            return lat, lon, km, "patio"

    if ramal is not None:
        t, o = _chaves_de_colunas(ramal, origem)
        if (t, o) in patio:
            lat, lon, km = patio[(t, o)]
            return lat, lon, km, "patio"

    return np.nan, np.nan, np.nan, None


def enriquecer_geo(df: pd.DataFrame,
                   col_tplnr: str = "local_instalacao",
                   col_ramal: str = "ramal",
                   col_origem: str = "origem",
                   col_km: str = "km_real",
                   col_trecho: str = "trecho",
                   col_destino: str = "destino") -> pd.DataFrame:
    """
    Adiciona colunas lat, lon, km_real, geo_fonte ao DataFrame.

    Estratégia de posicionamento, por linha, na ordem de precisão:
      1. **Exato por KM** — quando a linha tem `km_real` (notas VP) e o ramal
         tem marcos: interpola lat/lon no marco exato. geo_fonte='km'.
      2. **Segmento** (trecho,origem,destino via TPLNR). geo_fonte='segmento'.
      3. **Pátio** (trecho,origem). geo_fonte='patio'.

    - Não sobrescreve km_real já existente e válido (respeita dados do banco).
    - Falha graciosa: sem referência, devolve colunas geo em NaN (consumidores
      mantêm o fallback antigo).
    """
    if df is None or df.empty:
        return df

    lk = carregar_ref_geo()
    rk = carregar_ref_km()
    if lk.get("n", 0) == 0 and not rk:
        for c in ("lat", "lon", "geo_fonte"):
            if c not in df.columns:
                df = df.copy()
                df[c] = np.nan if c != "geo_fonte" else None
        return df

    df = df.copy()
    tplnr_col = col_tplnr if col_tplnr in df.columns else None
    ramal_col = col_ramal if col_ramal in df.columns else None
    origem_col = col_origem if col_origem in df.columns else None
    trecho_col = col_trecho if col_trecho in df.columns else None
    destino_col = col_destino if col_destino in df.columns else None
    km_col = col_km if col_km in df.columns else None
    km_atual = pd.to_numeric(df[km_col], errors="coerce") if km_col else None

    lats, lons, kms, fontes = [], [], [], []
    for i, r in df.iterrows():
        lat = lon = km = np.nan
        fonte = None

        km_lin = km_atual.loc[i] if km_atual is not None else np.nan
        ramal_lin = r.get(ramal_col) if ramal_col else None
        trecho_lin = r.get(trecho_col) if trecho_col else None

        # 1) Posição EXATA por KM (notas VP com km_real). A referência de KM é
        #    chaveada por CÓDIGO DE TRECHO (ACL, ADP...); o `ramal` da nota pode
        #    estar na sigla canônica (SJU, JIT...). Tenta ambos.
        if rk and pd.notna(km_lin):
            for chave in (trecho_lin, ramal_lin):
                if chave is None or (isinstance(chave, float) and pd.isna(chave)):
                    continue
                lat, lon, fonte = geo_por_km(chave, km_lin, ref_km=rk)
                if fonte:
                    km = float(km_lin)
                    break

        # 2) Colunas NATIVAS da nota (trecho/origem/destino) — mesmo vocabulário
        #    da referência. Preferencial ao TPLNR quando ele não vem em MF-.
        if fonte is None and trecho_lin is not None:
            lat, lon, km, fonte = geo_lookup_cols(
                trecho=trecho_lin,
                origem=r.get(origem_col) if origem_col else None,
                destino=r.get(destino_col) if destino_col else None,
                lookups=lk,
            )

        # 3) Fallback por TPLNR (segmento) / ramal+origem (pátio).
        if fonte is None:
            lat, lon, km, fonte = geo_lookup(
                tplnr=r.get(tplnr_col) if tplnr_col else None,
                ramal=ramal_lin,
                origem=r.get(origem_col) if origem_col else None,
                lookups=lk,
            )

        lats.append(lat); lons.append(lon); kms.append(km); fontes.append(fonte)

    df["lat"] = lats
    df["lon"] = lons
    df["geo_fonte"] = fontes

    km_novo = pd.Series(kms, index=df.index, dtype="float64")
    if "km_real" in df.columns:
        atual = pd.to_numeric(df["km_real"], errors="coerce")
        df["km_real"] = atual.where(atual.notna(), km_novo)
    else:
        df["km_real"] = km_novo

    return df


def cobertura_geo(df: pd.DataFrame) -> dict:
    """Resumo de cobertura geográfica (para captions/telemetria na UI)."""
    if df is None or df.empty or "lat" not in df.columns:
        return {"total": 0, "com_geo": 0, "pct": 0.0}
    total = len(df)
    com = int(df["lat"].notna().sum())
    return {"total": total, "com_geo": com,
            "pct": round(com / total * 100, 1) if total else 0.0}

# endregion
