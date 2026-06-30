# core/glossarios.py — Dicionários de referência MRS
# Fonte oficial: nomenclatura ANTT/SAP confirmada em 26/06/2026
# ⚠️ NUNCA usar "Matriz" — o termo correto é "Ramal"

import pandas as pd


# region ====================== SESSÃO 1: Mapa de Ramais (Sigla → Nome Completo) ======================

RAMAIS_MRS: dict[str, str] = {
    # ── Gerência SP ──────────────────────────────────────────────────────
    "SJU": "Santos - Jundiaí",
    "RCO": "Ramal de Conceiçãozinha",
    "RPQ": "Ligação Perequê - Cubatão",
    "RFA": "Ramal das Fábricas",
    "SLE": "Segregação Leste",
    "VSU": "Variante Suzano",          # ⭐ Canônico (ASP é alias legado → normalizar)
    # ── Gerência VP ──────────────────────────────────────────────────────
    "JIT": "Linha São Paulo",
    "FAC": "Ferrovia do Aço",
    "VPB": "Variante do Paraopeba",
    "RPS": "Ramal Porto Sudeste",
    "RIT": "Ramal de Itaguaí",
    "RMC": "Ramal de Mogi das Cruzes",
    "RHF": "Horto Florestal",
    "RAR": "Ligação à Arará",
    "RMB": "Posto km 452 - Miguel Burnier",
    "RAM": "Ramal Terminal Açominas",
    "RPM": "Ramal Terminal Paraibuna Metais",
    "RCB": "Ramal Terminal Cimento Barroso",
    "RMG": "Ramal de Mangaratiba",
}

# Aliases legados do SAP que devem ser normalizados para a sigla canônica
# Adicionar aqui se novos aliases forem descobertos nos uploads
ALIASES_RAMAL: dict[str, str] = {
    "ASP": "VSU",   # Variante Suzano — sigla legada do SAP
}

# endregion


# region ====================== SESSÃO 2: Funções de Consulta ======================

def nome_ramal(sigla: str, formato: str = "completo") -> str:
    """
    Retorna o nome legível de um ramal a partir da sigla canônica.

    Args:
        sigla:   Sigla do ramal (ex: 'SJU')
        formato: 'completo' → "Santos - Jundiaí"
                 'sigla'    → "SJU"
                 'ambos'    → "Santos - Jundiaí (SJU)"

    Returns:
        String formatada ou a própria sigla se não encontrada.
    """
    sigla = sigla.upper().strip() if sigla else ""
    # Normaliza alias antes de buscar
    sigla = ALIASES_RAMAL.get(sigla, sigla)
    nome = RAMAIS_MRS.get(sigla, sigla)

    if formato == "completo":
        return nome
    elif formato == "sigla":
        return sigla
    elif formato == "ambos":
        return f"{nome} ({sigla})"
    return nome


def normalizar_ramal(sigla: str) -> str:
    """
    Converte alias legado para sigla canônica.
    Ex: 'ASP' → 'VSU'  |  'SJU' → 'SJU'
    Sempre retorna maiúsculo.
    """
    if not sigla or not str(sigla).strip():
        return sigla
    s = str(sigla).upper().strip()
    return ALIASES_RAMAL.get(s, s)


def normalizar_coluna_ramal(df: pd.DataFrame, coluna: str = "ramal") -> pd.DataFrame:
    """
    Aplica normalização de aliases em toda a coluna 'ramal' do DataFrame.
    ⭐ SEMPRE chamar após carregar e decodificar o TPLNR.
    Garante que ASP→VSU e outros aliases não causem dupla contagem.

    Args:
        df:     DataFrame com coluna de ramal
        coluna: Nome da coluna (padrão 'ramal')

    Returns:
        DataFrame com a coluna normalizada (in-place seguro)
    """
    if coluna not in df.columns:
        return df
    df = df.copy()
    df[coluna] = df[coluna].apply(
        lambda x: normalizar_ramal(x) if pd.notna(x) else x
    )
    return df

# endregion


# region ====================== SESSÃO 3: Centros de Trabalho ======================

CENTROS_SP = ["CIPA", "CIPG", "CIJN"]
CENTROS_VP = ["CFAN", "CFTA", "CFPI"]

CENTROS_POR_GERENCIA: dict[str, list[str]] = {
    "SP": CENTROS_SP,
    "VP": CENTROS_VP,
}

# endregion


# region ====================== SESSÃO 4: Glossário VP (Famílias e Defeitos) ======================

FAMILIAS_VP: dict[str, str] = {
    "TR": "Trilho",
    "TJ": "Junta",
    "SD": "Solda",
    "AM": "AMV",
    "DM": "Dormente",
    "DO": "Dormente",
    "GE": "Geometria",
    "LA": "Lastro",
    "GM": "Geral Manutenção",
    "CS": "Cota Salvaguarda",
}

GLOSSARIO_VP: dict[str, str] = {
    "TR01": "Defeito superficial pista de rolamento",
    "TR02": "Patinado",
    "TR16": "Desgaste de trilho",
    "TR22": "Defeito superficial no canto de bitola",
    "TJ03": "Abertura excessiva de junção",
    "TJ04": "Falta parafuso tala de junção",
    "TJ07": "Junta arriada",
    "TJ09": "Junta batendo",
    "SD01": "Defeito em solda",
    "AM08": "Falta fixação no trinco (macaquinho)",
    "AM11": "Parafuso quebrado/faltante",
    "AM13": "Dormente podre — grade interm./jacaré",
    "AM15": "Desgaste do contra-trilho",
    "AM17": "Amassamento do trilho paralelo (encosto)",
    "AM19": "Agulha fora de esquadro",
    "AM23": "Def. superficial/perfil jacaré",
    "AM37": "Escora lateral desajustada/faltante",
    "AM40": "Bolsão na região do AMV",
    "AM42": "Dormente podre — grade agulha",
    "AM43": "AMV desnivelado",
    "DM01": "Dormente de madeira inservível",
    "DM02": "Dormente madeira inservível junta/solda",
    "DO01": "Vigota inservível",
    "GE01": "Bitola aberta (larga)",
    "GE03": "Defeito de nivelamento",
    "GE05": "Torção",
    "GE09": "Defeito de alinhamento",
    "GE13": "Cant irregular",
    "GE15": "Bitola — variação rápida",
    "LA01": "Bolsão",
    "LA04": "Ausência de ombro de lastro",
    "LA10": "Bolsão/lastro contaminado-solda entalada",
    "GM04": "Vegetação em alta tensão",
    "GM15": "Necessidade de ampara lastro",
    "CS01": "Cota LP fora dos parâmetros",
    "CS02": "Proteção ponta jacaré fora dos parâmetros",
    "CS04": "FLP fora dos parâmetros",
}

# endregion


# region ====================== SESSÃO 5: Glossário EE (Famílias e Defeitos) ======================

FAMILIAS_EE: dict[str, str] = {
    "SN": "Sinalização",
    "EN": "Energia",
    "TE": "Telecomunicações",
    "WS": "Wayside",
}

SUBSISTEMAS_EE = ["SINALIZ", "ENERGIA", "TELECOM", "WAYSIDE"]

GLOSSARIO_EE: dict[str, str] = {
    "SN01": "Abrigo/caixa danificado",
    "SN07": "Aterramento inadequado",
    "SN08": "Bateria danificada",
    "SN11": "Bondeamento inadequado",
    "SN12": "Cabos/conexão danificado/desorganizado",
    "SN18": "Conexão no trilho inadequada",
    "SN22": "Cordoalha/cabo transposição danificado",
    "SN23": "Corrosão",
    "SN46": "Máquina de chave desajustada",
    "SN55": "Relé danificado",
    "SN63": "Sujeira",
    "SN64": "Tensão irregular",
    "SN72": "Circuito de via irregular",
    "SN83": "Sinaleiro irregular/inadequado",
    "EN03": "Aterramento inadequado",
    "EN05": "Baixo nível óleo/líquido arrefecimento",
    "EN09": "Cabo aéreo irregular",
    "EN10": "Cabo defeituoso",
    "EN13": "Chave de manobra inadequada",
    "EN20": "Conexões irregulares",
    "EN25": "Defeito em inspeção visual",
    "EN26": "Disjuntor defeituoso",
    "EN33": "Falha em teste de operação/funcionamento",
    "EN37": "Fixação do componente deficiente",
    "EN64": "Resistência inadequada",
    "EN68": "Sujeira",
    "EN73": "Torres danificadas",
    "TE02": "Antena, cabo, conexão danif./desalinhado",
    "TE03": "Ar condicionado não funcional",
    "TE04": "Aterramento inadequado",
    "TE09": "Conexões irregulares",
    "TE10": "Corrosão",
    "TE23": "Potência de transmissão direta irregular",
    "WS02": "Antena, cabo, conexão danif./desalinhado",
    "WS04": "Aterramento inadequado",
    "WS08": "Condição de via inadequada",
    "WS13": "Espelho ou lente danificado",
    "WS28": "Scanner desalinhado",
    "WS31": "Sujeira",
    "WS33": "Tensão irregular",
    "WS38": "Abrigo/caixa danificado",
    "WS40": "Corrosão",
    "WS69": "Scanner danificado",
}

# endregion
