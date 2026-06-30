# core/score_engine.py — Motor de cálculo de score composto
# Fórmula: Score = peso_prio × mult_status × mult_familia × mult_tipo × (1 + α × anos_aberta)
# Todos os multiplicadores são configuráveis via painel admin (Sprint 4).

import pandas as pd
from datetime import date


# region ====================== SESSÃO 1: Pesos e Multiplicadores Padrão ======================

PESO_PRIORIDADE: dict[str, int] = {
    "1-Muito alta": 4,
    "2-Alta":       3,
    "3-Média":      2,
    "4-Baixa":      1,
}

MULT_STATUS: dict[str, float] = {
    "ABER": 1.0,
    "DIFE": 0.5,   # Diferida — penalização menor por estar postergada
}

MULT_FAMILIA_VP: dict[str, float] = {
    "Trilho":           1.5,
    "Geometria":        1.5,
    "AMV":              1.5,
    "Dormente":         1.2,
    "Lastro":           1.2,
    "Junta":            1.0,
    "Solda":            1.0,
    "Cota Salvaguarda": 1.0,
    "Geral Manutenção": 0.8,
    "Outros":           1.0,
}

MULT_FAMILIA_EE: dict[str, float] = {
    "Wayside":               1.5,
    "Sinalização":           1.3,
    "Energia":               1.2,
    "Telecomunicações":      1.0,
    "Sinalização Específica":1.1,
    "Outros":                1.0,
}

MULT_TIPO: dict[str, float] = {
    "CT": 1.5,   # Corretiva — mais urgente
    "PV": 1.0,   # Preventiva
}

ALPHA_IDADE_PADRAO: float = 0.10  # 10% de penalização por ano em aberto

# endregion


# region ====================== SESSÃO 2: Função Principal ======================

def calcular_score_composto(
    row: pd.Series,
    disciplina: str = "VP",
    alpha: float = ALPHA_IDADE_PADRAO,
    mult_dife: float = 0.5,
) -> float:
    """
    Calcula o score composto de uma nota.

    Args:
        row:        Linha do DataFrame com colunas padronizadas
        disciplina: 'VP' ou 'EE' — define qual tabela de família usar
        alpha:      Fator de envelhecimento (padrão 0.10 = 10% ao ano)
        mult_dife:  Multiplicador para status DIFE (padrão 0.5)

    Returns:
        float: Score ponderado, arredondado a 2 casas decimais
    """
    # Peso base pela prioridade
    prio = str(row.get("prioridade", "4-Baixa") or "4-Baixa")
    score = float(PESO_PRIORIDADE.get(prio, 1))

    # Multiplicador de status
    status = str(row.get("status_usuario", "ABER") or "ABER").upper()
    mult_st = mult_dife if status == "DIFE" else MULT_STATUS.get(status, 1.0)
    score *= mult_st

    # Multiplicador de família
    familia = str(row.get("familia_defeito", "Outros") or "Outros")
    tabela_familia = MULT_FAMILIA_EE if disciplina == "EE" else MULT_FAMILIA_VP
    score *= tabela_familia.get(familia, 1.0)

    # Multiplicador por tipo de nota (CT/PV)
    tipo = str(row.get("tipo_nota", "") or "")
    for chave, mult in MULT_TIPO.items():
        if chave in tipo.upper():
            score *= mult
            break

    # Fator de envelhecimento: +α por ano em aberto
    data_nota = row.get("data_nota")
    if data_nota and pd.notna(data_nota):
        try:
            if isinstance(data_nota, str):
                data_nota = pd.to_datetime(data_nota).date()
            elif hasattr(data_nota, "date"):
                data_nota = data_nota.date()
            anos = max(0, (date.today() - data_nota).days / 365.25)
            score *= (1 + alpha * anos)
        except Exception:
            pass  # Falha silenciosa — não deve quebrar o pipeline

    return round(score, 2)


def aplicar_score_dataframe(
    df: pd.DataFrame,
    disciplina: str = "VP",
    alpha: float = ALPHA_IDADE_PADRAO,
    mult_dife: float = 0.5,
) -> pd.DataFrame:
    """
    Aplica calcular_score_composto em todo o DataFrame e salva em df['score'].
    ⭐ Sempre chamar após normalizar_coluna_ramal().

    Args:
        df:         DataFrame com notas padronizadas
        disciplina: 'VP' ou 'EE'
        alpha:      Fator de envelhecimento
        mult_dife:  Multiplicador DIFE

    Returns:
        DataFrame com coluna 'score' preenchida
    """
    df = df.copy()
    df["score"] = df.apply(
        lambda row: calcular_score_composto(row, disciplina, alpha, mult_dife),
        axis=1
    )
    return df

# endregion
