# =============================================================================
# core/parser_rasf.py — Parser do export RASF de Eletroeletrônica
# Sprint 6 — MRS Sentinel · Aba "Inteligência de Falhas EE"
#
# O RASF (Reunião de Análise Sistêmica de Falha) é um export DIFERENTE da nota
# SAP clássica: além dos campos operacionais, traz a camada de análise de causa
# raiz (RCA) que o PG-ENG-0088 exige — Gatilho, THP, 6M (Ishikawa), Componente
# Causador, reincidência pré-calculada e impacto em confiabilidade.
#
# Estas colunas NÃO existem na tabela `notas`; por isso o RASF vai para uma
# tabela dedicada `rasf_ee` (opção B — não mexe no pipeline VP/EE existente).
#
# Fluxo: upload xlsx RASF → processar_rasf() → df canônico →
#        df_rasf_para_registros() → grava em rasf_ee no Supabase.
#
# Layout canônico confirmado por Julio (77 colunas, aba "Export").
# =============================================================================

from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime


# region ====================== SESSÃO 1: Mapeamento de Colunas =================
# RASF (cabeçalho original) -> nome canônico interno (snake_case).
# Colunas de ciclo preventivo (C30..C3600, 24 colunas) são intencionalmente
# omitidas da v1 — não alimentam nenhum dos 6 blocos de inteligência e só
# inflariam a tabela. Podem ser reincorporadas se surgir análise preventiva.

COLUNAS_RASF: dict[str, str] = {
    "Ano":                                         "ano",
    "Mês":                                         "mes",
    "Número da nota":                              "numero_nota",
    "Data da nota":                                "data_nota",
    "Nº ordem":                                    "ordem",
    "Centro de trabalho responsável":              "centro_trab",
    "Gerência":                                    "_gerencia_raw",
    "Local Pátio":                                 "local_patio",
    "Descrição Tipo Solicitação":                  "desc_tipo_solicitacao",
    "Local de instalação TPLNR":                   "local_instalacao",
    "Local de instalação":                         "local_instalacao_desc",
    "Nº equipamento":                              "num_equipamento",
    "Grupo do ativo":                              "grupo_ativo",
    "Sistema":                                     "sistema",
    "Anomalia/Sintoma":                            "anomalia_sintoma",
    "Descrição da Origem da Atividade":            "desc_origem_atividade",
    "Texto breve para o código Parte de Objeto":   "texto_parte_objeto",
    "Texto breve para o código Problemas Erro":    "texto_problema_erro",
    "Texto Longo Nota":                            "texto_longo",
    "Última data ativo":                           "ultima_data_ativo",
    "Dias desde última falha ativo":               "dias_ultima_falha_ativo",
    "Reincidência 90 dias ativo":                  "_reincidencia_ativo_raw",
    "Última data sintoma":                         "ultima_data_sintoma",
    "Dias desde última falha sintoma":             "dias_ultima_falha_sintoma",
    "Reincidência 90 dias sintoma":                "_reincidencia_sintoma_raw",
    "Gerador THP (300)":                           "_gerador_thp_raw",
    "Descricao Justificativa Transporte":          "just_transporte",
    "Tempo THP 300 (min)":                         "thp_min",
    "Número de Eventos (300)":                     "thp_num_eventos",
    "Tempo THP 133 (min)":                         "thp_min_133",
    "Número de Eventos (133)":                     "thp_num_eventos_133",
    "Status Sistema":                              "status_sistema",
    "Impacta no indicador de confiabilidade?":     "_confiabilidade_raw",
    "(Campo) Gatilho":                             "gatilho_campo",
    "6M Nível 1 - MF":                             "m6n1_mf",
    "6M Nível 2 - MF":                             "m6n2_mf",
    "6M Nível 3 - MF":                             "m6n3_mf",
    "Árvore de Falhas - MF":                       "arvore_falhas_mf",
    "(Eng) Gatilho":                               "gatilho_eng",
    "Tipo de falha":                               "tipo_falha",
    "6M Nível 1 - Eng":                            "m6n1_eng",
    "6M Nível 2 - Eng":                            "m6n2_eng",
    "6M Nível 3 - Eng":                            "m6n3_eng",
    "Componente Causador":                         "componente_causador",
    "Pendente?":                                   "_pendente_raw",
    "Disposições Reunião":                         "disposicoes_reuniao",
    "Responsável":                                 "responsavel",
    "Consenso Origem de Atividade?":               "consenso_origem",
    "Origem de Atividade Correta":                 "origem_atividade_correta",
    "Item SAC":                                    "item_sac",
    "Justificativa":                               "justificativa",
    "Divergência THP":                             "divergencia_thp",
    "Data SAC":                                    "data_sac",
}

# Gerência do RASF (GEE.SP / GEE.VP / GEV.SP) -> gerência canônica do app (SP/VP)
MAPA_GERENCIA: dict[str, str] = {
    "GEE.SP": "SP",
    "GEV.SP": "SP",
    "GEE.VP": "VP",
    "GEV.VP": "VP",
}

# Valores de "(Eng) Gatilho" que caracterizam ocorrência que DEVE ter causa raiz
# (Gatilho de Análise de Falhas — PG-ENG-0088, seção 6.4.1).
#
# ⚠️ O próprio procedimento diz que essa regra NÃO é fixa: "As regras do
# gatilho estarão sujeitas a alteração de acordo com o indicador de
# confiabilidade vigente [...] definidos e validados durante o processo de
# revisão e definição de metas da coordenação." Por isso este valor é só o
# PADRÃO — quem chama processar_rasf()/carregar_rasf_xlsx() pode sobrescrever
# via o parâmetro gatilhos_analise (ver database.queries_rasf.carregar_gatilhos_analise,
# que lê de `configuracoes` e cai neste padrão se não houver override).
GATILHOS_ANALISE_PADRAO = {"Falha THP", "Falha Segurança", "Defeito THP"}

# Categorização Obras × Manutenção a partir de "Descrição da Origem da
# Atividade" — pedido do Julio (10/07/2026): a malha está em obras de
# remodelação, então falha originada de Obras pede estratégia de bloqueio
# diferente (padrão de comissionamento/entrega) de falha originada de
# Manutenção tradicional (RCA/plano de manutenção).
#
# Regra por SUBSTRING (não lista fechada) — generaliza sozinha a valores
# novos que apareçam em exports futuros, sem precisar de deploy:
#   contém "OBRA"     → "Obras"
#   contém "MANUTEN"   → "Manutenção"
#   NaN/vazio          → "Não informado"
#   qualquer outro     → "Não classificado" (ex.: Vandalismo, TI, Acidente,
#                         Ação de Terceiros — causas externas/operacionais,
#                         não é nem Obras nem Manutenção MRS)
#
# Casos ambíguos que a regra de substring não pega bem (ex.: "MECÂNICA",
# "TRILHO OXIDADO") ficam em "Não classificado" por padrão — dá pra
# refinar via overrides exatos em `configuracoes`
# (chave='rasf_origem_categoria_overrides', ver database.queries_rasf).
def classificar_origem_atividade(valor, overrides: dict[str, str] | None = None) -> str:
    """Classifica 'Descrição da Origem da Atividade' em Obras/Manutenção/
    Não classificado/Não informado. Overrides exatos (case-insensitive)
    têm prioridade sobre a regra de substring."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "Não informado"
    v = str(valor).strip()
    if not v or v == "-":
        return "Não informado"
    if overrides:
        for chave, categoria in overrides.items():
            if str(chave).strip().upper() == v.upper():
                return categoria
    vu = v.upper()
    if "OBRA" in vu:
        return "Obras"
    if "MANUTEN" in vu:
        return "Manutenção"
    return "Não classificado"

# 6M Nível 1 preenchido válido (exclui vazios e "sem análise")
_M6_NAO_PREENCHIDO = {None, "", "-", "nan"}

COLUNAS_DATA_RASF = [
    "data_nota", "ultima_data_ativo", "ultima_data_sintoma", "data_sac",
]
COLUNAS_NUM_RASF = [
    "ano", "mes", "numero_nota", "dias_ultima_falha_ativo",
    "dias_ultima_falha_sintoma", "thp_min", "thp_num_eventos",
    "thp_min_133", "thp_num_eventos_133",
]

# endregion


# region ====================== SESSÃO 2: Helpers de normalização ==============

def _sim_nao(valor) -> bool:
    """Converte 'Sim'/'Não' (e variações, incl. marcação por 'X' — padrão do
    RASF na coluna Z 'Gerador THP (300)') em bool. Vazio/None -> False."""
    if valor is None:
        return False
    return str(valor).strip().casefold() in {"sim", "s", "x", "true", "1", "yes"}


def _texto_valido(v) -> str:
    """Normaliza pra string vazia quando NaN/None/'-' — usado nas regras de
    origem efetiva/consenso abaixo (evita 'nan' virando texto de verdade)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    v = str(v).strip()
    return "" if v in {"-", "nan"} else v


# Regra de causa raiz/responsabilidade do RASF — pedido do Julio (16/07/2026):
# "Descrição da Origem da Atividade" (coluna P) é a REFERÊNCIA de causa raiz/
# responsabilidade. Mas se "Origem de Atividade Correta" (coluna AW) foi
# preenchida em reunião com um valor DIFERENTE de P, a responsabilidade foi
# corrigida — ela prevalece. Se P == correta (ou correta vazia), P já está
# certo, mantém P.
def origem_efetiva(desc_origem_atividade, origem_atividade_correta):
    """Aplica a regra acima e devolve o valor efetivo de origem/responsabilidade."""
    p = _texto_valido(desc_origem_atividade)
    correta = _texto_valido(origem_atividade_correta)
    if correta and correta.upper() != p.upper():
        return origem_atividade_correta  # preserva a grafia original da correção
    return desc_origem_atividade


# "Consenso Origem de Atividade?" (coluna AV) — Sim: processo encerrado
# (consenso fechado); Não: pode caber revisão; em branco: ainda Pendente
# (reunião não discutiu/decidiu esse item).
def status_consenso_origem(valor) -> str:
    """
    Classifica o status de consenso em 'Sim' | 'Não' | 'Pendente'.

    Usa startswith (não igualdade exata) porque o RASF às vezes traz o valor
    com complemento (ex.: 'Sim - Fechado', 'Não - aguardando validação') —
    mesmo padrão já usado pelo campo 'Pendente?' do RASF (ver 'pendente' em
    processar_rasf()), que também é um 'SIM'/'NÃO' com sufixo variável.
    """
    v = _texto_valido(valor)
    if not v:
        return "Pendente"
    vu = v.upper()
    if vu.startswith("SIM") or vu in {"S", "TRUE", "1", "YES", "X"}:
        return "Sim"
    if vu.startswith(("NÃO", "NAO")) or vu in {"N", "FALSE", "0", "NO"}:
        return "Não"
    return "Pendente"


def _mapear_gerencia(valor) -> str | None:
    """GEE.SP -> SP, GEE.VP -> VP. Desconhecido/None -> None."""
    if valor is None:
        return None
    return MAPA_GERENCIA.get(str(valor).strip().upper())


def _m6_preenchido(valor) -> bool:
    """True se o 6M Nível 1 tem classificação real (qualquer valor não vazio)."""
    if valor is None:
        return False
    return str(valor).strip().casefold() not in {c.casefold() for c in _M6_NAO_PREENCHIDO if c is not None} \
        and str(valor).strip() != ""


def _consolidar_6m(row: pd.Series) -> str | None:
    """
    Fonte da verdade do 6M: prioriza a análise da Engenharia (m6n1_eng);
    se ausente, cai para a análise da Manutenção/Field (m6n1_mf).
    """
    eng = row.get("m6n1_eng")
    if _m6_preenchido(eng):
        return str(eng).strip()
    mf = row.get("m6n1_mf")
    if _m6_preenchido(mf):
        return str(mf).strip()
    return None

# endregion


# region ====================== SESSÃO 3: Pipeline principal ===================

def processar_rasf(
    df_raw: pd.DataFrame,
    gatilhos_analise: set[str] | None = None,
    overrides_origem: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Recebe o DataFrame bruto do export RASF (aba 'Export') e devolve um
    DataFrame canônico, pronto para gravação e para os componentes.

    Deriva:
      - gerencia          : SP/VP (a partir de 'Gerência' GEE.xx) — None se
        não reconhecida (chamador decide o que fazer; ver aviso no uploader)
      - disciplina        : sempre 'EE'
      - reincidencia_ativo / reincidencia_sintoma : bool
      - impacta_confiabilidade / gerador_thp / pendente : bool
      - gatilho_analise   : bool (Gatilho de Análise de Falhas do PG-ENG-0088)
      - m6_nivel1         : 6M consolidado (Eng > MF)
      - rca_preenchida    : bool (tem 6M/Componente classificado — NÃO é o
        mesmo que "validado" pelo fluxo formal do procedimento, que este
        export não carrega)
      - lacuna_rca        : bool (é gatilho MAS sem classificação) -> backlog
      - origem_categoria  : "Obras" | "Manutenção" | "Não classificado" |
        "Não informado" — ver classificar_origem_atividade()

    Args:
        gatilhos_analise: conjunto de valores de "(Eng) Gatilho" que
            caracterizam gatilho de análise. Se None, usa
            GATILHOS_ANALISE_PADRAO. Passe um valor vindo de
            `configuracoes` (via database.queries_rasf) para refletir
            mudanças de regra sem precisar deploy — o PG-ENG-0088 prevê
            que essa regra muda por ciclo de metas.
        overrides_origem: mapa exato {valor_origem: categoria} que tem
            prioridade sobre a regra automática de substring em
            classificar_origem_atividade(). Vem de `configuracoes`
            (chave='rasf_origem_categoria_overrides').
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    gatilhos = gatilhos_analise if gatilhos_analise is not None else GATILHOS_ANALISE_PADRAO

    # Renomeia apenas as colunas conhecidas; ignora extras silenciosamente.
    rename = {k: v for k, v in COLUNAS_RASF.items() if k in df_raw.columns}
    df = df_raw.rename(columns=rename).copy()

    # Datas e numéricos
    for col in COLUNAS_DATA_RASF:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in COLUNAS_NUM_RASF:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # THP sempre numérico e não-negativo (vazio -> 0 para somas)
    if "thp_min" in df.columns:
        df["thp_min"] = pd.to_numeric(df["thp_min"], errors="coerce").fillna(0).clip(lower=0)
    else:
        df["thp_min"] = 0.0

    # Gerência canônica + disciplina
    df["gerencia"] = df.get("_gerencia_raw").map(_mapear_gerencia) \
        if "_gerencia_raw" in df.columns else None
    df["disciplina"] = "EE"

    # Flags booleanas
    df["reincidencia_ativo"] = df.get("_reincidencia_ativo_raw").map(_sim_nao) \
        if "_reincidencia_ativo_raw" in df.columns else False
    df["reincidencia_sintoma"] = df.get("_reincidencia_sintoma_raw").map(_sim_nao) \
        if "_reincidencia_sintoma_raw" in df.columns else False
    df["impacta_confiabilidade"] = df.get("_confiabilidade_raw").map(_sim_nao) \
        if "_confiabilidade_raw" in df.columns else False
    df["gerador_thp"] = df.get("_gerador_thp_raw").map(_sim_nao) \
        if "_gerador_thp_raw" in df.columns else False

    # Pendente: '-' = não; 'SIM'/'SIM - xxx' = sim
    if "_pendente_raw" in df.columns:
        df["pendente"] = df["_pendente_raw"].apply(
            lambda v: bool(v) and str(v).strip().upper().startswith("SIM")
        )
    else:
        df["pendente"] = False

    # Gatilho de Análise (Eng)
    if "gatilho_eng" in df.columns:
        df["gatilho_analise"] = df["gatilho_eng"].apply(
            lambda v: str(v).strip() in gatilhos if v is not None else False
        )
    else:
        df["gatilho_analise"] = False

    # Origem efetiva de responsabilidade — "Descrição da Origem da Atividade"
    # é a referência, mas "Origem de Atividade Correta" sobrepõe quando a
    # responsabilidade foi corrigida em reunião (ver origem_efetiva() acima).
    if "desc_origem_atividade" in df.columns:
        df["origem_atividade_efetiva"] = df.apply(
            lambda r: origem_efetiva(
                r.get("desc_origem_atividade"), r.get("origem_atividade_correta")
            ),
            axis=1,
        )
    else:
        df["origem_atividade_efetiva"] = None

    # Status de consenso da origem ('Sim'/'Não' normalizados, vazio=Pendente)
    df["consenso_origem_status"] = df.get("consenso_origem").apply(status_consenso_origem) \
        if "consenso_origem" in df.columns else "Pendente"

    # Categoria Obras × Manutenção — a partir da origem EFETIVA (não da bruta),
    # já que é ela que reflete a responsabilidade real após a reunião do RASF.
    if "origem_atividade_efetiva" in df.columns:
        df["origem_categoria"] = df["origem_atividade_efetiva"].apply(
            lambda v: classificar_origem_atividade(v, overrides_origem)
        )
    else:
        df["origem_categoria"] = "Não informado"

    # 6M consolidado + preenchimento de causa raiz
    df["m6_nivel1"] = df.apply(_consolidar_6m, axis=1)
    tem_6m = df["m6_nivel1"].apply(lambda v: pd.notna(v) and str(v).strip() != "")
    comp = df.get("componente_causador", pd.Series([None] * len(df), index=df.index))
    tem_componente = comp.apply(
        lambda v: pd.notna(v) and str(v).strip() not in {"", "-"}
    )
    df["rca_preenchida"] = tem_6m | tem_componente

    # Lacuna RCA = precisa de análise (gatilho) mas NÃO tem causa raiz.
    df["lacuna_rca"] = df["gatilho_analise"] & (~df["rca_preenchida"])

    # Descarta linhas sem número de nota (rodapés/linhas em branco do export)
    if "numero_nota" in df.columns:
        df = df[df["numero_nota"].notna()].reset_index(drop=True)

    return df


def carregar_rasf_xlsx(
    fonte,
    sheet_name: str = "Export",
    gatilhos_analise: set[str] | None = None,
    overrides_origem: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Lê o arquivo/buffer xlsx do RASF e devolve o DataFrame canônico.
    Aceita caminho (str), file-like (upload do Streamlit) ou BytesIO.
    """
    df_raw = pd.read_excel(fonte, sheet_name=sheet_name, engine="openpyxl")
    return processar_rasf(
        df_raw, gatilhos_analise=gatilhos_analise, overrides_origem=overrides_origem,
    )

# endregion


# region ====================== SESSÃO 4: Serialização Supabase =================

# Colunas efetivamente persistidas em rasf_ee (bate 1:1 com schema_rasf.sql).
COLUNAS_RASF_EE = [
    "ano", "mes", "numero_nota", "data_nota", "ordem",
    "gerencia", "disciplina", "centro_trab", "local_patio",
    "desc_tipo_solicitacao", "local_instalacao", "local_instalacao_desc",
    "num_equipamento", "grupo_ativo", "sistema", "anomalia_sintoma",
    "desc_origem_atividade", "origem_atividade_correta", "origem_atividade_efetiva",
    "consenso_origem", "consenso_origem_status", "texto_longo",
    "ultima_data_ativo", "dias_ultima_falha_ativo", "reincidencia_ativo",
    "ultima_data_sintoma", "dias_ultima_falha_sintoma", "reincidencia_sintoma",
    "gerador_thp", "thp_min", "thp_num_eventos", "thp_min_133",
    "status_sistema", "impacta_confiabilidade",
    "gatilho_campo", "gatilho_eng", "gatilho_analise", "tipo_falha",
    "m6n1_mf", "m6n1_eng", "m6_nivel1", "arvore_falhas_mf",
    "componente_causador", "rca_preenchida", "lacuna_rca",
    "pendente", "disposicoes_reuniao", "responsavel", "item_sac",
    "origem_categoria",
]


def df_rasf_para_registros(df: pd.DataFrame, upload_id: str) -> list[dict]:
    """
    Converte o DataFrame RASF canônico em registros prontos para o Supabase.
    Trata NaN/NaT, floats inteiros e datas — mesmo padrão de
    core.parser.df_para_registros_supabase.
    """
    registros: list[dict] = []
    for _, row in df.iterrows():
        rec: dict = {"upload_id": upload_id}
        for col in COLUNAS_RASF_EE:
            val = row.get(col)
            try:
                if val is None or (not isinstance(val, (list, dict)) and pd.isnull(val)):
                    rec[col] = None
                    continue
            except (TypeError, ValueError):
                pass

            if isinstance(val, (bool, np.bool_)):
                rec[col] = bool(val)
            elif isinstance(val, float):
                if np.isnan(val) or np.isinf(val):
                    rec[col] = None
                elif val == int(val):
                    rec[col] = int(val)
                else:
                    rec[col] = val
            elif isinstance(val, (pd.Timestamp, datetime)):
                rec[col] = val.date().isoformat()
            elif hasattr(val, "item"):
                rec[col] = val.item()
            else:
                rec[col] = val
        registros.append(rec)
    return registros

# endregion
