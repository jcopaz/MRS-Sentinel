# =============================================================================
# core/glossarios.py — Glossário oficial de Ramais e Códigos MRS Logística
# Sprint 1 (rev.3) — MRS Sentinel
#
# ⚠️  DICIONÁRIO DE NOMES OFICIAIS — não alterar sem validação com Julio
#     Fonte: 08_GLOSSARIOS.md + padrão ANTT
#
# Sessão 1: Ramais (SIGLA → Nome Completo oficial)
# Sessão 2: Aliases (siglas legadas → sigla canônica)
# Sessão 3: Funções utilitárias
# Sessão 4: Centros de Trabalho por Gerência
# Sessão 5: Pátios típicos por Centro
# =============================================================================

# region ====================== SESSÃO 1: Ramais MRS ===========================

# Dicionário SIGLA → NOME COMPLETO (uso na UI)
# ⭐ Nomes validados com 08_GLOSSARIOS.md — não usar nomes informais
RAMAIS_MRS = {
    # Ramais principais (prefixo MF-{SIGLA})
    "ADP": "Alça Dupla",
    "BPD": "Boa Vista - Pederneiras",
    "JIT": "Jundiaí - Itirapina",
    "RAM": "Aço Minas",
    "RAR": "Perequê - Areais",           # ⚠️ Não é "Ligação à Arara"
    "RCB": "Cimento Barroso",
    "RCF": "Córrego do Feijão",
    "RCO": "Conceiçãozinha",
    "RCS": "César de Souza (VCP/FIBRIA)",
    "RFA": "Fábricas",
    "RIT": "Itaguaí",
    "RMB": "Miguel Burnier",
    "RPB": "Paraibuna",
    "RPQ": "Cubatão - Perequê",
    "RPS": "Porto Sudeste",
    "RTP": "Tiplan",
    "SJU": "Santos - Jundiaí",
    "TOD": "Olhos D'Água",
    "RWL": "Wilson Lobato",
    "LSP": "Linha de São Paulo",
    "SLE": "Segregação Leste",
    "VSU": "Variante Suzano",            # ⭐ canônico (alias: ASP)
}

# endregion


# region ====================== SESSÃO 2: Aliases ==============================

# Siglas legadas ou duplicadas → sigla canônica
# ⚠️ Sempre normalizar ANTES de qualquer agrupamento/filtro/exibição
RAMAIS_ALIASES = {
    "ASP": "VSU",   # ASP = alias antigo de Variante Suzano → canônico VSU
    # Adicionar novos aliases aqui conforme forem descobertos no SAP
}

# Dicionário reverso: Nome Completo → Sigla (busca reversa, quando necessário)
RAMAIS_REVERSO = {v: k for k, v in RAMAIS_MRS.items()}

# endregion


# region ====================== SESSÃO 3: Funções Utilitárias ==================

def normalizar_ramal(sigla: str) -> str:
    """
    Normaliza a sigla do ramal, aplicando aliases conhecidos.

    Sempre chame ANTES de qualquer agrupamento, filtro ou exibição
    para garantir consistência nos dados.

    Args:
        sigla: ex: 'ASP', 'VSU', 'SJU'

    Returns:
        str: sigla canônica (ex: 'ASP' → 'VSU')
    """
    if not sigla or not isinstance(sigla, str):
        return sigla
    sigla_clean = sigla.strip().upper()
    return RAMAIS_ALIASES.get(sigla_clean, sigla_clean)


def nome_ramal(sigla: str, formato: str = "completo") -> str:
    """
    Retorna o nome do ramal conforme o formato escolhido.
    Aplica normalização de aliases automaticamente.

    Args:
        sigla:   ex: 'SJU', 'JIT', 'ASP', 'RAR'
        formato: 'completo'       → apenas o nome
                 'sigla'          → apenas a sigla canônica
                 'completo_sigla' → Nome (SIGLA)

    Returns:
        str: nome formatado

    Exemplos:
        nome_ramal('SJU')                    → 'Santos - Jundiaí'
        nome_ramal('ASP')                    → 'Variante Suzano'
        nome_ramal('RAR')                    → 'Perequê - Areais'
        nome_ramal('VSU', 'completo_sigla') → 'Variante Suzano (VSU)'
    """
    sigla_canonica = normalizar_ramal(sigla)
    nome = RAMAIS_MRS.get(sigla_canonica, sigla_canonica)

    if formato == "sigla":
        return sigla_canonica
    elif formato == "completo_sigla":
        if sigla_canonica == nome:   # sigla não cadastrada → retorna como está
            return sigla_canonica
        return f"{nome} ({sigla_canonica})"
    else:  # completo (padrão)
        return nome


def normalizar_coluna_ramal(df, coluna: str = "ramal"):
    """
    Normaliza uma coluna inteira do DataFrame, convertendo aliases
    para a sigla canônica.

    Args:
        df:     DataFrame pandas
        coluna: nome da coluna com siglas de ramal

    Returns:
        DataFrame com coluna normalizada (modifica in-place e retorna)

    Exemplo:
        df = normalizar_coluna_ramal(df, "ramal")
        # notas com ramal='ASP' → ramal='VSU'
    """
    if coluna in df.columns:
        df[coluna] = df[coluna].apply(normalizar_ramal)
    return df

# endregion


# region ====================== SESSÃO 4: Centros de Trabalho ==================

# Centros de trabalho por gerência
# Fonte: estrutura organizacional MRS Logística
CENTROS_POR_GERENCIA = {
    "SP": ["CIPA", "CIPG", "CIJN"],
    "VP": ["CFAN", "CFTA", "CFPI"],
}

# Gerência de cada centro (busca reversa)
GERENCIA_POR_CENTRO = {
    centro: ger
    for ger, centros in CENTROS_POR_GERENCIA.items()
    for centro in centros
}

# endregion


# region ====================== SESSÃO 5: Pátios típicos =======================

# Pátios típicos por centro (para validação e sugestão)
PATIOS_POR_CENTRO = {
    # Gerência SP
    "CIPA": ["IPA", "IRS", "ICG", "IRG", "IBA", "ICZ",
             "IJU", "IQA", "ISN", "IUF", "IVP", "ZPG"],
    "CIPG": ["IPG", "IQB", "IQA", "ICB"],
    "CIJN": ["IJN", "ILA", "IAB"],
    # Gerência VP
    "CFAN": ["FAN", "FFL", "FVQ", "FCZ", "FEP", "FQU", "FIA", "FPB"],
    "CFTA": ["FTA", "FCT", "FAD", "FLR", "FPB", "FUI"],
    "CFPI": ["FPI"],
}

# endregion
