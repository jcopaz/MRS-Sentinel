# =============================================================================
# core/glossarios.py — Glossário oficial MRS Logística
# Sprint 1 (rev.4) — MRS Sentinel
#
# ⚠️  CORREÇÕES v4:
#   • RAR = "Perequê - Areais" (não "Ligação à Arara")
#   • RIP não existe no glossário oficial (mantido como sigla bruta)
#   • Mantidos TODOS os símbolos do parser.py: PADRAO_TPLNR, decodificar_tplnr,
#     GLOSSARIO_DEFEITOS, FAMILIAS_VP, GLOSSARIO_EE, FAMILIAS_EE,
#     PESO_PRIORIDADE, MULT_STATUS, MULT_TIPO, ALPHA_IDADE_PADRAO
# =============================================================================

import re

# region ====================== SESSÃO 1: Ramais MRS ===========================

RAMAIS_MRS = {
    "ADP": "Alça Dupla",
    "BPD": "Boa Vista - Pederneiras",
    "JIT": "Jundiaí - Itirapina",
    "RAM": "Aço Minas",
    "RAR": "Perequê - Areais",           # ⚠️ CORRETO — não é "Ligação à Arara"
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

RAMAIS_ALIASES = {
    "ASP": "VSU",   # ASP = alias legado → canônico VSU
    "RIP": "JIT",   # RIP faz parte do mesmo trecho Jundiaí - Itirapina
}

RAMAIS_REVERSO = {v: k for k, v in RAMAIS_MRS.items()}

# endregion


# region ====================== SESSÃO 2: Funções de Ramal =====================

def normalizar_ramal(sigla: str) -> str:
    if not sigla or not isinstance(sigla, str):
        return sigla
    sigla_clean = sigla.strip().upper()
    return RAMAIS_ALIASES.get(sigla_clean, sigla_clean)


def nome_ramal(sigla: str, formato: str = "completo") -> str:
    sigla_canonica = normalizar_ramal(sigla)
    nome = RAMAIS_MRS.get(sigla_canonica, sigla_canonica)
    if formato == "sigla":
        return sigla_canonica
    elif formato == "completo_sigla":
        if sigla_canonica == nome:
            return sigla_canonica
        return f"{nome} ({sigla_canonica})"
    return nome


def normalizar_coluna_ramal(df, coluna: str = "ramal"):
    if coluna in df.columns:
        df[coluna] = df[coluna].apply(normalizar_ramal)
    return df

# endregion


# region ====================== SESSÃO 3: Centros e Pátios =====================

CENTROS_POR_GERENCIA = {
    "SP": ["CIPA", "CIPG", "CIJN"],
    "VP": ["CFAN", "CFTA", "CFPI"],
}

GERENCIA_POR_CENTRO = {
    centro: ger
    for ger, centros in CENTROS_POR_GERENCIA.items()
    for centro in centros
}

PATIOS_POR_CENTRO = {
    "CIPA": ["IPA", "IRS", "ICG", "IRG", "IBA", "ICZ",
             "IJU", "IQA", "ISN", "IUF", "IVP", "ZPG"],
    "CIPG": ["IPG", "IQB", "IQA", "ICB"],
    "CIJN": ["IJN", "ILA", "IAB"],
    "CFAN": ["FAN", "FFL", "FVQ", "FCZ", "FEP", "FQU", "FIA", "FPB"],
    "CFTA": ["FTA", "FCT", "FAD", "FLR", "FPB", "FUI"],
    "CFPI": ["FPI"],
}

# endregion


# region ====================== SESSÃO 4: Glossário VP =========================

GLOSSARIO_DEFEITOS = {
    # Trilho (TR)
    "TR01": "Defeito superficial pista de rolamento",
    "TR02": "Patinado",
    "TR16": "Desgaste de trilho",
    "TR22": "Defeito superficial no canto de bitola",
    # Junta (TJ)
    "TJ03": "Abertura excessiva de junção",
    "TJ04": "Falta parafuso tala de junção",
    "TJ07": "Junta arriada",
    "TJ09": "Junta batendo",
    # Solda (SD)
    "SD01": "Defeito em solda",
    # AMV (AM)
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
    # Dormente (DM/DO)
    "DM01": "Dormente de madeira inservível",
    "DM02": "Dormente madeira inservível junta/solda",
    "DO01": "Vigota inservível",
    # Geometria (GE)
    "GE01": "Bitola aberta (larga)",
    "GE03": "Defeito de nivelamento",
    "GE05": "Torção",
    "GE09": "Defeito de alinhamento",
    "GE13": "Cant irregular",
    "GE15": "Bitola — variação rápida",
    # Lastro (LA)
    "LA01": "Bolsão",
    "LA04": "Ausência de ombro de lastro",
    "LA10": "Bolsão/lastro contaminado-solda entalada",
    # Geral Manutenção (GM)
    "GM04": "Vegetação em alta tensão",
    "GM15": "Necessidade de ampara lastro",
    # Cota Salvaguarda (CS)
    "CS01": "Cota LP fora dos parâmetros",
    "CS02": "Proteção ponta jacaré fora dos parâmetros",
    "CS04": "FLP fora dos parâmetros",
}

# Alias para compatibilidade com código legado que usa GLOSSARIO_VP
GLOSSARIO_VP = GLOSSARIO_DEFEITOS

FAMILIAS_VP = {
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

# endregion


# region ====================== SESSÃO 5: Glossário EE =========================

GLOSSARIO_EE = {
    # SN — Sinalização
    "SN01": "Abrigo/caixa danificado",
    "SN07": "Aterramento inadequado",
    "SN08": "Bateria danificada",
    "SN09": "Bateria inadequada",
    "SN11": "Bondeamento inadequado",
    "SN12": "Cabos/conexão danificado/desorganizado",
    "SN13": "Cadeados danificados",
    "SN18": "Conexão no trilho inadequada",
    "SN19": "Conexões irregulares",
    "SN22": "Cordoalha/cabo transposição danificado",
    "SN23": "Corrosão",
    "SN25": "Documentação técnica inadequada",
    "SN34": "Fiação/terminais/conexões inadequados",
    "SN46": "Máquina de chave desajustada",
    "SN55": "Relé danificado",
    "SN56": "Relé rachado/quebrado",
    "SN63": "Sujeira",
    "SN64": "Tensão irregular",
    "SN72": "Circuito de via irregular",
    "SN83": "Sinaleiro irregular/inadequado",
    "SN86": "Suporte/barra irregular/danificado",
    # EN — Energia
    "EN03": "Aterramento inadequado",
    "EN05": "Baixo nível óleo/líquido arrefecimento",
    "EN09": "Cabo aéreo irregular",
    "EN10": "Cabo defeituoso",
    "EN11": "Cabo, alimentações ou garras danificados",
    "EN13": "Chave de manobra inadequada",
    "EN16": "Climatização inadequada",
    "EN20": "Conexões irregulares",
    "EN21": "Contatos/fiação inadequados",
    "EN25": "Defeito em inspeção visual",
    "EN26": "Disjuntor defeituoso",
    "EN27": "Dobradiça/tranca danificada ou fresta",
    "EN33": "Falha em teste de operação/funcionamento",
    "EN37": "Fixação do componente deficiente",
    "EN42": "Instalações inadequadas",
    "EN64": "Resistência inadequada",
    "EN68": "Sujeira",
    "EN73": "Torres danificadas",
    "EN77": "Vazamento de combustível",
    # TE — Telecomunicações
    "TE02": "Antena, cabo, conexão danif./desalinhado",
    "TE03": "Ar condicionado não funcional",
    "TE04": "Aterramento inadequado",
    "TE06": "Baixa autonomia da bateria",
    "TE09": "Conexões irregulares",
    "TE10": "Corrosão",
    "TE23": "Potência de transmissão direta irregular",
    # WS — Wayside
    "WS02": "Antena, cabo, conexão danif./desalinhado",
    "WS04": "Aterramento inadequado",
    "WS05": "Baixa autonomia da bateria",
    "WS08": "Condição de via inadequada",
    "WS13": "Espelho ou lente danificado",
    "WS26": "Protetor de surto inadequado",
    "WS28": "Scanner desalinhado",
    "WS31": "Sujeira",
    "WS33": "Tensão irregular",
    "WS38": "Abrigo/caixa danificado",
    "WS40": "Corrosão",
    "WS47": "Documentação técnica inadequada",
    "WS66": "Bondeamento inadequado",
    "WS69": "Scanner danificado",
    # S1xx — Sinalização específica
    "S103": "Invólucro do relé trincado",
    "S104": "Invólucro do relé quebrado",
    "S131": "Tirantes desalinhados",
    "S138": "Máquina de chave sem identificação",
    # Numéricos — Eventos operacionais
    "33":  "Circuito de via com ocupação indevida",
    "35":  "Máquina de chave inoperante",
    "36":  "Máquina de chave perdendo indicação",
    "40":  "Sinal inoperante",
    "50":  "Sinal com foco fraco",
    "999": "Outros problemas de EE",
}

FAMILIAS_EE = {
    "SN": "Sinalização",
    "EN": "Energia",
    "TE": "Telecomunicações",
    "WS": "Wayside",
    "S1": "Sinalização Específica",
}

SUBSISTEMAS_EE = ["SINALIZ", "ENERGIA", "TELECOM", "WAYSIDE"]

# endregion


# region ====================== SESSÃO 6: Pesos e Multiplicadores ==============

PESO_PRIORIDADE = {
    "1-Muito alta": 4,
    "2-Alta":       3,
    "3-Média":      2,
    "4-Baixa":      1,
}

MULT_STATUS = {"ABER": 1.0, "DIFE": 0.5}

MULT_TIPO = {"CT": 1.5, "PV": 1.0}

ALPHA_IDADE_PADRAO = 0.10   # 10% por ano aberto

# endregion


# region ====================== SESSÃO 7: Parser TPLNR =========================

# Padrão unificado VP + EE
# VP:  MF-{TRECHO}-{ORIGEM}_{DESTINO}-L{LINHA}-{ATIVO}
# EE:  MF-{TRECHO}-{ORIGEM}_{DESTINO}-{SUBSISTEMA}-{ATIVO}
PADRAO_TPLNR = re.compile(
    r"MF-(?P<trecho>[A-Z0-9]+)-"
    r"(?P<origem>[A-Z0-9]+)_(?P<destino>[A-Z0-9]+)"
    r"(?:-(?:L(?P<linha>[A-Z0-9]+)|(?P<subsistema>SINALIZ|ENERGIA|TELECOM|WAYSIDE)))?"
    r"(?:-(?P<ativo>.+))?"
)


def decodificar_tplnr(local_instalacao: str) -> dict:
    """
    Decodifica o Local de Instalação em campos estruturados.

    Args:
        local_instalacao: string TPLNR (ex: "MF-SJU-IPA_IPA-L000001-AMV258N")

    Returns:
        dict com chaves: trecho, origem, destino, linha, subsistema, ativo
    """
    if not local_instalacao:
        return {}
    match = PADRAO_TPLNR.match(str(local_instalacao))
    if not match:
        return {}
    return match.groupdict()

# endregion
