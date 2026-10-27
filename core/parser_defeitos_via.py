# =============================================================================
# core/parser_defeitos_via.py — Export de defeitos de via da Rumo
#
# Aceita os dois formatos (casamento por nome normalizado):
#   - "Defeitos SUB 78.xlsx"                (24 colunas, export curto)
#   - "Vgao Via-Defeitos Pederneiras.xlsx"  (60 colunas, aba Export; inclui
#     Vagão de Via = Origem 'VIA', com Número/Sentido da Viagem e lat/long)
# Colunas ausentes ficam NULL; o que não for mapeado vai para `extra` (JSONB).
#
# Filtro do trecho: Sub 78 e km ≤ 303,8 (depois disso é ZPD–ZFJ em diante,
# fora do Itirapina–Pederneiras) — descartado com aviso.
#
# Exporta:
#   ler_defeitos_via(arquivo, km_max=303.8) -> (DataFrame, avisos)
#   vel_classe(texto) -> float | None   ('Classe 2.3 | 35-40 Km/h' → 40)
# =============================================================================

import re

import numpy as np
import pandas as pd

from core.parser_prospeccao import _norm

KM_FIM_TRECHO = 303.8

MAPA = {
    "defeito id": "defeito_id", "status do defeito": "status", "subdivisao": "sub",
    "km": "km", "equipamento": "equipamento_siv", "linha": "linha", "sb": "sb",
    "nome do defeito": "nome_defeito", "defeito grupo": "grupo", "grupo grafico": "grupo_grafico",
    "classe de via (po novo)": "classe_via", "classificacao (po novo)": "classificacao",
    "limite de malha": "limite_malha", "tamanho": "tamanho", "extensao": "extensao", "peso": "peso",
    "data de entrada": "data_entrada", "data de baixa": "data_baixa", "tempo ativo": "dias_ativo",
    "origem": "origem", "tipo inspecao": "tipo_inspecao", "numero da viagem": "numero_viagem",
    "sentido da viagem": "sentido_viagem", "giro_via": "giro_via",
    "perimetro urbano": "perimetro_urbano", "obra de arte": "obra_de_arte", "amv": "amv",
    "area de risco antt ( s/n )": "area_risco_antt", "acidente": "acidente",
    "data do acidente": "data_acidente", "causa do acidente": "causa_acidente",
    "latitude": "latitude", "longitude": "longitude", "supervisor": "supervisor",
}
BOOLS = ("perimetro_urbano", "obra_de_arte", "area_risco_antt", "acidente")
DATAS = ("data_entrada", "data_baixa", "data_acidente")
INTS = ("dias_ativo", "numero_viagem")
NUMS = ("km", "tamanho", "extensao", "peso", "latitude", "longitude")


def vel_classe(texto):
    m = re.search(r"-\s*(\d+)\s*Km/h", str(texto or ""), flags=re.I)
    return float(m.group(1)) if m else None


def _bool(v):
    if pd.isna(v):
        return None
    t = _norm(v)
    return True if t in ("sim", "s") else False if t in ("nao", "n") else None


def _extra_safe(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v if isinstance(v, (int, float, bool)) else str(v)


def ler_defeitos_via(arquivo, km_max: float = KM_FIM_TRECHO) -> tuple[pd.DataFrame, list[str]]:
    xl = pd.ExcelFile(arquivo)
    aba = next((a for a in xl.sheet_names if _norm(a) == "export"), xl.sheet_names[0])
    bruto = pd.read_excel(xl, sheet_name=aba)
    avisos: list[str] = []

    mapeadas = {}
    for c in bruto.columns:
        d = MAPA.get(_norm(c))
        if d and d not in mapeadas.values():
            mapeadas[c] = d
    if "Defeito ID" not in mapeadas and not any(v == "defeito_id" for v in mapeadas.values()):
        raise ValueError("Coluna 'Defeito ID' não encontrada.")
    df = bruto[list(mapeadas)].rename(columns=mapeadas)
    for col in MAPA.values():
        if col not in df.columns:
            df[col] = None
    nao_mapeadas = [c for c in bruto.columns if c not in mapeadas]
    df["extra"] = [{k: _extra_safe(v) for k, v in zip(nao_mapeadas, row) if _extra_safe(v) is not None}
                   for row in bruto[nao_mapeadas].itertuples(index=False)]

    df["defeito_id"] = pd.to_numeric(df["defeito_id"], errors="coerce").astype("Int64")
    for c in NUMS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in INTS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in DATAS:
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    for c in BOOLS:
        df[c] = df[c].map(_bool)
    df["sub"] = df["sub"].map(lambda v: None if pd.isna(v) else str(v).split(".")[0])
    df["linha"] = df["linha"].astype(str).str.strip().str.upper().replace({"LPL": "LP", "NAN": None, "NONE": None})
    df["vel_max_classe_kmh"] = df["classe_via"].map(vel_classe)
    for c in ("limite_malha", "classe_via", "amv", "giro_via", "sentido_viagem"):
        df[c] = df[c].map(lambda v: None if pd.isna(v) else str(v))

    sem_id = df["defeito_id"].isna()
    if sem_id.any():
        avisos.append(f"{int(sem_id.sum())} linha(s) sem Defeito ID descartada(s).")
        df = df[~sem_id]
    if df["defeito_id"].duplicated().any():
        n = int(df["defeito_id"].duplicated().sum())
        avisos.append(f"{n} Defeito ID repetido(s) — mantida a 1ª ocorrência.")
        df = df.drop_duplicates("defeito_id")
    fora = df[(df["sub"] != "78") | (df["km"] > km_max + 1e-9)]
    if len(fora):
        avisos.append(f"{len(fora)} defeito(s) fora do trecho (Sub ≠ 78 ou km > {km_max}) descartado(s).")
    df = df.drop(fora.index)
    return df.reset_index(drop=True), avisos
