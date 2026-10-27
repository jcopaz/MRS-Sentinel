# =============================================================================
# core/parser_execucao.py — Planilha-modelo "o que a Manutenção fez"
#
# Cabeçalho fixo (MODELO). ler_execucao(arquivo) → (df, avisos), pura.
#   - atividade aceita o código (troca_dormente) ou o rótulo ("Troca de dormente")
#   - km aceita 285,1 / 285.1 / 285+100 / metros (285100)
#   - linha vazia = LP; equipamento vazio é calculado pelo km na gravação
# gerar_modelo() devolve o .xlsx com o cabeçalho, 2 linhas de exemplo e uma
# aba "Atividades" com os códigos aceitos.
# =============================================================================

import io
import re

import pandas as pd

from core.parser_prospeccao import _norm

ATIVIDADES = {
    "troca_dormente":  ("Troca de dormente", "dorm"),
    "solda":           ("Solda", "und"),
    "retirada_tala":   ("Retirada de tala", "und"),
    "socaria":         ("Socaria", "km"),
    "nivelamento":     ("Nivelamento", "km"),
    "limpeza_lastro":  ("Limpeza de lastro", "m"),
    "descarga_lastro": ("Descarga de lastro", "m"),
    "troca_trilho":    ("Troca de trilho", "m"),
    "drenagem":        ("Drenagem", "m"),
    "outro":           ("Outro", "und"),
}
UNIDADES = ("dorm", "und", "m", "km")

# coluna do modelo → coluna do banco
MODELO = {
    "Data": "data",
    "Atividade": "atividade",
    "KM início": "km_inicio",
    "KM fim": "km_fim",
    "Linha": "linha",
    "Equipamento SIV": "equipamento_siv",
    "Quantidade": "quantidade",
    "Unidade": "unidade",
    "Equipe": "equipe",
    "Nota SAP": "nota_sap",
    "Observação": "observacao",
}
_POR_NORMA = {_norm(k): v for k, v in MODELO.items()}
_ATIV_NORMA = {**{_norm(k): k for k in ATIVIDADES},
               **{_norm(v[0]): k for k, v in ATIVIDADES.items()}}


def _km(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        k = float(v)
    else:
        s = str(v).strip().replace(" ", "")
        m = re.fullmatch(r"(\d+)\+(\d{1,3})", s)
        if m:
            return int(m.group(1)) + int(m.group(2)) / 1000
        try:
            k = float(s.replace(",", "."))
        except ValueError:
            return None
    return k / 1000 if k > 10_000 else k     # veio em metros


def ler_execucao(arquivo) -> tuple[pd.DataFrame, list[str]]:
    avisos: list[str] = []
    bruto = pd.read_excel(arquivo, sheet_name=0)
    mapa = {c: _POR_NORMA[_norm(c)] for c in bruto.columns if _norm(c) in _POR_NORMA}
    faltam = {"data", "atividade", "km_inicio", "quantidade"} - set(mapa.values())
    if faltam:
        return pd.DataFrame(), [f"Colunas obrigatórias ausentes: {', '.join(sorted(faltam))}. "
                                "Use o modelo (📥 Baixar modelo)."]
    d = bruto[list(mapa)].rename(columns=mapa).dropna(how="all")
    for c in MODELO.values():
        if c not in d.columns:
            d[c] = None
    d["data"] = pd.to_datetime(d["data"], errors="coerce", dayfirst=True).dt.date
    d["atividade"] = d["atividade"].map(lambda v: _ATIV_NORMA.get(_norm(v)) if pd.notna(v) else None)
    d["km_inicio"] = d["km_inicio"].map(_km)
    d["km_fim"] = d["km_fim"].map(_km)
    d["quantidade"] = pd.to_numeric(d["quantidade"], errors="coerce")
    d["linha"] = d["linha"].fillna("LP").astype(str).str.strip().str.upper().replace({"": "LP", "LPL": "LP"})
    sem_un = d["unidade"].isna() | (d["unidade"].astype(str).str.strip() == "")
    d.loc[sem_un, "unidade"] = d.loc[sem_un, "atividade"].map(lambda a: ATIVIDADES.get(a, (None, None))[1])
    d["unidade"] = d["unidade"].astype(str).str.strip().str.lower()
    for c in ("equipamento_siv", "equipe", "nota_sap", "observacao"):
        d[c] = d[c].map(lambda v: None if pd.isna(v) or str(v).strip() == "" else str(v).strip())

    invalida = d["data"].isna() | d["atividade"].isna() | d["km_inicio"].isna() | ~(d["quantidade"] > 0)
    if invalida.any():
        linhas = ", ".join(str(i + 2) for i in d.index[invalida][:10])
        avisos.append(f"{int(invalida.sum())} linha(s) ignorada(s) — data, atividade, km ou quantidade "
                      f"inválidos (linhas da planilha: {linhas}).")
        d = d[~invalida]
    un_ruim = ~d["unidade"].isin(UNIDADES)
    if un_ruim.any():
        avisos.append(f"{int(un_ruim.sum())} linha(s) com unidade fora de {', '.join(UNIDADES)} — ignoradas.")
        d = d[~un_ruim]
    dup = d.duplicated(["data", "atividade", "km_inicio", "linha", "quantidade"])
    if dup.any():
        avisos.append(f"{int(dup.sum())} linha(s) repetida(s) no arquivo — mantida 1.")
        d = d[~dup]
    return d[list(MODELO.values())].reset_index(drop=True), avisos


def gerar_modelo() -> bytes:
    exemplo = pd.DataFrame([
        {"Data": "15/01/2027", "Atividade": "Troca de dormente", "KM início": 285.1, "KM fim": 285.4,
         "Linha": "LP", "Equipamento SIV": "", "Quantidade": 70, "Unidade": "dorm",
         "Equipe": "Equipe Dois Córregos", "Nota SAP": "", "Observação": "T1"},
        {"Data": "16/01/2027", "Atividade": "Solda", "KM início": 285.25, "KM fim": None,
         "Linha": "LP", "Equipamento SIV": "", "Quantidade": 4, "Unidade": "und",
         "Equipe": "Equipe Dois Córregos", "Nota SAP": "", "Observação": ""},
    ], columns=list(MODELO))
    ativ = pd.DataFrame([{"Código": k, "Atividade": v[0], "Unidade padrão": v[1]}
                         for k, v in ATIVIDADES.items()])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        exemplo.to_excel(w, sheet_name="Execucao", index=False)
        ativ.to_excel(w, sheet_name="Atividades", index=False)
    return buf.getvalue()
