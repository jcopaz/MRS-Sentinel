# =============================================================================
# core/parser_transit_time.py — Consulta SRM "Transit Time entre dois locais"
#
# Aba Dados: TREM, PATIO_A, PARTIDA, TIPO_PARTE, PATIO_B, CHEGADA,
# TIPO_CHEGA, TMPCIRC, ESTADO, DT_ENCER. Datas dd/mm/aaaa hh:mm:ss. TMPCIRC
# é FRAÇÃO DE DIA (pode vir como texto com vírgula) — usado só como
# conferência; horas = chegada − partida.
#
# valido = ENCERRADO e partida/chegada Realizadas (R/R).
# SUPRIMIDO (P/P) traz o horário PROGRAMADO: mediana por sentido e mês vira
# horas_programadas. outlier = horas > 72.
#
# Exporta:
#   ler_transit_time(arquivo) -> (DataFrame, avisos)
#   resumo_mensal(df) -> DataFrame mes × sentido (trens, mediana, p90, programado, aderência)
# =============================================================================

import pandas as pd

LIMITE_OUTLIER_H = 72
FMT = "%d/%m/%Y %H:%M:%S"


def _data(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, format=FMT, errors="coerce")
    falhou = d.isna() & s.notna()
    if falhou.any():
        d[falhou] = pd.to_datetime(s[falhou], dayfirst=True, errors="coerce")
    return d


def ler_transit_time(arquivo) -> tuple[pd.DataFrame, list[str]]:
    xl = pd.ExcelFile(arquivo)
    aba = next((a for a in xl.sheet_names if a.strip().lower() == "dados"), xl.sheet_names[0])
    bruto = pd.read_excel(xl, sheet_name=aba, dtype=str)
    bruto.columns = [c.strip().upper() for c in bruto.columns]
    faltam = {"TREM", "PATIO_A", "PARTIDA", "PATIO_B", "CHEGADA", "ESTADO"} - set(bruto.columns)
    if faltam:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(faltam))}")
    avisos: list[str] = []

    df = pd.DataFrame({
        "trem": bruto["TREM"].str.strip(),
        "patio_a": bruto["PATIO_A"].str.strip(),
        "patio_b": bruto["PATIO_B"].str.strip(),
        "partida": _data(bruto["PARTIDA"]),
        "tipo_parte": bruto.get("TIPO_PARTE", pd.Series(dtype=str)).str.strip(),
        "chegada": _data(bruto["CHEGADA"]),
        "tipo_chega": bruto.get("TIPO_CHEGA", pd.Series(dtype=str)).str.strip(),
        "estado": bruto["ESTADO"].str.strip(),
        "dt_encer": _data(bruto["DT_ENCER"]) if "DT_ENCER" in bruto else pd.NaT,
    })
    df["sentido"] = df["patio_a"] + "→" + df["patio_b"]
    df["horas"] = (df["chegada"] - df["partida"]).dt.total_seconds() / 3600
    df["valido"] = (df["estado"] == "ENCERRADO") & (df["tipo_parte"] == "R") & (df["tipo_chega"] == "R")
    df["outlier"] = df["horas"] > LIMITE_OUTLIER_H

    sem_data = df["partida"].isna().sum()
    if sem_data:
        avisos.append(f"{sem_data} linha(s) sem data de partida descartada(s).")
        df = df[df["partida"].notna()]
    # Mesma chave repetida: fica a linha válida (ENCERRADO R/R), se houver.
    df = df.sort_values("valido", ascending=False, kind="stable")
    dup = df.duplicated(["trem", "patio_a", "patio_b", "partida"])
    if dup.any():
        avisos.append(f"{int(dup.sum())} linha(s) repetida(s) (trem+partida) descartada(s).")
        df = df[~dup].sort_values("partida")

    df["mes"] = df["partida"].dt.to_period("M").astype(str)
    prog = (df[df["estado"] == "SUPRIMIDO"].groupby(["sentido", "mes"])["horas"].median()
            .rename("horas_programadas"))
    prog_sentido = df[df["estado"] == "SUPRIMIDO"].groupby("sentido")["horas"].median()
    df = df.join(prog, on=["sentido", "mes"])
    df["horas_programadas"] = df["horas_programadas"].fillna(df["sentido"].map(prog_sentido))
    if df["outlier"].any():
        avisos.append(f"{int((df['valido'] & df['outlier']).sum())} trem(ns) válido(s) acima de "
                      f"{LIMITE_OUTLIER_H} h marcado(s) como outlier.")
    return df.drop(columns="mes").reset_index(drop=True), avisos


def resumo_mensal(df: pd.DataFrame) -> pd.DataFrame:
    """Só trens válidos e sem outlier."""
    v = df[df["valido"].astype(bool) & ~df["outlier"].astype(bool)].copy()
    if v.empty:
        return pd.DataFrame(columns=["mes", "sentido", "trens", "mediana", "p90", "programado", "aderencia"])
    v["partida"] = pd.to_datetime(v["partida"])
    v["horas"] = pd.to_numeric(v["horas"])
    v["horas_programadas"] = pd.to_numeric(v["horas_programadas"])
    v["mes"] = v["partida"].dt.to_period("M").astype(str)
    v["no_prazo"] = v["horas"] <= v["horas_programadas"] + 1
    return (v.groupby(["mes", "sentido"])
            .agg(trens=("horas", "size"), mediana=("horas", "median"),
                 p90=("horas", lambda s: s.quantile(0.9)),
                 programado=("horas_programadas", "median"),
                 aderencia=("no_prazo", "mean"))
            .reset_index())
