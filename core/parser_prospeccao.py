# =============================================================================
# core/parser_prospeccao.py — Leitura da planilha de Prospecção de Dormentes
#
# Fonte: "Prospecção Itirapina Engenharia.xlsx" (GeVia, jun/2026) — 1 linha
# por segmento (Equipamento SIV) com km início/fim, malhas de inservíveis
# consecutivos (Malha 1..10), inservíveis em junta/guarda/solda e taxa.
#
# Cabeçalhos casados por nome NORMALIZADO (sem acento, minúsculo, espaços
# colapsados) — a planilha tem "Extensão (Km)" duplicada (a 2ª é em metros)
# e uma coluna sem nome; ambas são ignoradas. As colunas de cenário (20% /
# 16% / 30%) são cálculo da planilha e NÃO são importadas.
#
# Também lê o export "Relatório de Prospecção" do GeVia (mesmo layout, com
# Kmi/Kmf/Cv/Tg/Total de Dormentes/Taxa Inservível e a coluna Ciclo — ciclo
# 2025 = base histórica Rumo, ciclo 2026 = R1) e a aba Trilho da Engenharia
# (Dentro/Fora + juntas).
#
# Exporta:
#   ler_prospeccao(arquivo, aba=0) -> (DataFrame, list[str] avisos)
#   separar_ciclos(df, km_max) -> {ciclo: DataFrame}
#   ler_trilho_engenharia(arquivo) -> (DataFrame, list[str] avisos)
#   enriquecer_prospeccao(df) -> DataFrame com colunas derivadas
# =============================================================================

import re
import unicodedata

import numpy as np
import pandas as pd


# region ====================== SESSÃO 1: Mapeamento de colunas ================

def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


# cabeçalho normalizado → coluna do banco (tabela prospeccao_dormentes)
MAPA_COLUNAS = {
    "gerencia":                        "gerencia",
    "coordenador":                     "coordenador",
    "trecho":                          "trecho",
    "sb":                              "sb",
    "sub":                             "sub",
    "equipamento siv":                 "equipamento_siv",
    "linha":                           "linha",
    "km inicio":                       "km_inicio",
    "km fim":                          "km_fim",
    "kmi":                             "km_inicio",
    "kmf":                             "km_fim",
    "equipament.":                     "geometria",
    "cv/tg":                           "geometria",
    "ciclo":                           "ciclo",
    "raio":                            "raio",
    "oae":                             "oae",
    "pu":                              "pu",
    "fonte":                           "fonte",
    "data prospeccao":                 "data_prospeccao",
    "espacamento medio (cm)":          "espacamento_cm",
    "tipo dormente":                   "tipo_dormente",
    "tipo fixacao":                    "tipo_fixacao",
    **{f"malha {n}": f"malha_{n}" for n in range(1, 11)},
    "dormente inservivel junta":       "inserv_junta",
    "dormente inservivel guarda":      "inserv_guarda",
    "dormente inservivel solda":       "inserv_solda",
    "total de dormentes prospectado":  "total_prospectado",
    "total de dormentes":              "total_prospectado",
    "dormentes proj. p/ extensao":     "dormentes_projetados",
    "qtd inservivel":                  "qtd_inservivel",
    "taxa inservivel atual":           "taxa_inservivel",
    "taxa inservivel":                 "taxa_inservivel",
    "qtd ruina":                       "qtd_ruina",
    "ext. s/ leitura (m)":             "ext_sem_leitura_m",
    "extensao sem leitura (m)":        "ext_sem_leitura_m",
    "observacao":                      "observacao",
    "trem de pasageiro":               "trem_passageiro",
    "trem de passageiro":              "trem_passageiro",
    "aderencia":                       "aderencia",
}

OBRIGATORIAS = ("trecho", "linha", "km_inicio", "km_fim")

COLS_INT = (
    [f"malha_{n}" for n in range(1, 11)]
    + ["inserv_junta", "inserv_guarda", "inserv_solda",
       "total_prospectado", "qtd_inservivel", "qtd_ruina"]
)
COLS_FLOAT = ("km_inicio", "km_fim", "raio", "espacamento_cm",
              "dormentes_projetados", "taxa_inservivel", "ext_sem_leitura_m")
COLS_TEXTO = ("gerencia", "coordenador", "trecho", "sb", "sub", "equipamento_siv",
              "linha", "geometria", "fonte", "tipo_dormente", "tipo_fixacao",
              "observacao", "trem_passageiro", "aderencia")

# endregion


# region ====================== SESSÃO 2: Leitura ==============================

def _sim_nao(v):
    if pd.isna(v):
        return None
    t = _norm(v)
    if t in ("sim", "s", "1", "true"):
        return True
    if t in ("nao", "n", "0", "false"):
        return False
    return None


def ler_prospeccao(arquivo, aba=0) -> tuple[pd.DataFrame, list[str]]:
    """
    Lê a aba de dormentes (1ª por padrão) e devolve (df no formato da
    tabela, avisos). Lança ValueError se faltar coluna obrigatória.
    """
    bruto = pd.read_excel(arquivo, sheet_name=aba)
    avisos: list[str] = []

    # 1ª ocorrência de cada cabeçalho normalizado vence (a 2ª "Extensão
    # (Km)" e outras duplicadas ficam de fora).
    escolhidas: dict[str, str] = {}
    for col in bruto.columns:
        destino = MAPA_COLUNAS.get(_norm(col))
        if destino and destino not in escolhidas.values():
            escolhidas[col] = destino
    df = bruto[list(escolhidas)].rename(columns=escolhidas)

    faltando = [c for c in OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(faltando)}")

    for c in COLS_FLOAT:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in COLS_INT:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round().astype(int)
    for c in COLS_TEXTO:
        if c in df.columns:
            df[c] = df[c].where(df[c].notna(), None)
            df[c] = df[c].map(lambda v: str(v).strip() if v is not None else None)
            df[c] = df[c].replace({"": None})
    for c in ("oae", "pu"):
        if c in df.columns:
            df[c] = df[c].map(_sim_nao)
    if "data_prospeccao" in df.columns:
        df["data_prospeccao"] = pd.to_datetime(df["data_prospeccao"], errors="coerce").dt.date
    if "ciclo" in df.columns:
        df["ciclo"] = pd.to_numeric(df["ciclo"], errors="coerce").astype("Int64")
    if "sub" in df.columns:
        df["sub"] = df["sub"].map(lambda v: v[:-2] if isinstance(v, str) and v.endswith(".0") else v)
    if "linha" in df.columns:
        df["linha"] = df["linha"].str.upper()
    if "geometria" in df.columns:
        df["geometria"] = df["geometria"].str.lower()

    antes = len(df)
    df = df.dropna(subset=["trecho", "km_inicio", "km_fim"])
    if len(df) < antes:
        avisos.append(f"{antes - len(df)} linha(s) sem trecho/km ignorada(s).")

    # Taxa em % (0–100) → 0–1; ausente → recalcula de qtd/total.
    if "taxa_inservivel" in df.columns and df["taxa_inservivel"].max(skipna=True) > 1.5:
        df["taxa_inservivel"] = df["taxa_inservivel"] / 100
    if "taxa_inservivel" in df.columns and {"qtd_inservivel", "total_prospectado"} <= set(df.columns):
        sem_taxa = df["taxa_inservivel"].isna() & (df["total_prospectado"] > 0)
        df.loc[sem_taxa, "taxa_inservivel"] = (
            df.loc[sem_taxa, "qtd_inservivel"] / df.loc[sem_taxa, "total_prospectado"])

    invertidos = (df["km_fim"] < df["km_inicio"]).sum()
    if invertidos:
        avisos.append(f"{invertidos} segmento(s) com km fim < km início.")

    return df.reset_index(drop=True), avisos

def separar_ciclos(df: pd.DataFrame, km_max: float | None = None) -> dict:
    """{ciclo: df} — recorta km_fim <= km_max (ex.: 303,8 = fim do trecho)."""
    if "ciclo" not in df.columns:
        return {None: df}
    if km_max is not None:
        df = df[df["km_fim"] <= km_max + 1e-9]
    return {int(c): g.reset_index(drop=True) for c, g in df.groupby("ciclo")}


# Aba Trilho da Engenharia: 2 linhas de cabeçalho; "Fora" fica dentro do
# bloco "Medida Trilho 1" (critério de desgaste da Engenharia).
JUNTAS_PROBLEMA = ("junta_taco", "junta_tala_quebrada", "junta_desligada",
                   "junta_deformada", "junta_tala_emergencia")


def ler_trilho_engenharia(arquivo, aba="Trilho") -> tuple[pd.DataFrame, list[str]]:
    from core.parser_prospeccao_campo import ler_aba_multicabecalho, montar_trilho
    bruto = ler_aba_multicabecalho(arquivo, aba)
    return montar_trilho(bruto)

# endregion


# region ====================== SESSÃO 3: Colunas derivadas ====================

def enriquecer_prospeccao(df: pd.DataFrame) -> pd.DataFrame:
    """Colunas usadas pelo mapa de calor (não persistidas)."""
    if df.empty:
        return df
    df = df.copy()
    for c in COLS_INT:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["extensao_km"] = (df["km_fim"] - df["km_inicio"]).abs()
    ext = df["extensao_km"].replace(0, np.nan)

    # Malha crítica = 3 ou mais inservíveis consecutivos.
    df["malhas_criticas"] = sum(df[f"malha_{n}"] for n in range(3, 11))
    df["dorm_malha_critica"] = sum(n * df[f"malha_{n}"] for n in range(3, 11))
    df["inserv_jgs"] = df["inserv_junta"] + df["inserv_guarda"] + df["inserv_solda"]

    df["taxa_pct"] = pd.to_numeric(df.get("taxa_inservivel"), errors="coerce") * 100
    df["inserv_por_km"] = df["qtd_inservivel"] / ext
    df["malhas_criticas_por_km"] = df["malhas_criticas"] / ext
    df["jgs_por_km"] = df["inserv_jgs"] / ext

    geo = df.get("geometria", pd.Series(index=df.index, dtype=object)).fillna("")
    df["geometria_txt"] = np.where(geo.str.startswith("cv"), "Curva",
                                   np.where(geo.str.startswith("tg"), "Tangente", "—"))
    return df

# endregion
