# core/parser.py — Parser universal de planilhas SAP (VP e EE)
#
# Detecta automaticamente o formato da planilha:
#   Formato A — Unificada:        possui coluna 'Status_Final_ok' (sem 'Número_da_nota')
#   Formato B — Notas Abertas:    possui coluna 'Marcador inic.'
#   Formato C — Notas Concluídas: possui coluna 'Ponto de partida'
#   Formato D — SAP Fiori/BW:     possui coluna 'Número_da_nota' (novo export)
#
# Pipeline de processamento:
#   1. Detectar formato
#   2. Renomear colunas para padrão interno
#   3. Converter datas (serial Excel e string)
#   4. Decodificar TPLNR → ramal, trecho, origem, destino
#   5. Calcular KM real (Formato D: KM{N} + offset decimal | outros: TPLNR)
#   6. Mapear família de defeito
#   7. Normalizar aliases de ramal (ASP → VSU)
#   8. Calcular score composto
#   9. Retornar DataFrame padronizado

import re
import pandas as pd
import numpy as np
from datetime import datetime

from core.glossarios import (
    FAMILIAS_VP, FAMILIAS_EE, GLOSSARIO_VP, GLOSSARIO_EE,
    normalizar_coluna_ramal, RAMAIS_MRS,
)
from core.score_engine import aplicar_score_dataframe


# region ====================== SESSÃO 1: Mapeamento de Colunas =================

# Formato A — Unificada (export SAP GUI clássico)
COLUNAS_FORMATO_A: dict[str, str] = {
    "Nota":                 "numero_nota",
    "Ordem":                "ordem",
    "Dt.vig.início":        "data_nota",
    "Data de encerramento": "data_encerramento",
    "Data planejada":       "data_planejada",
    "Local de instalação":  "local_instalacao",
    "Prioridade":           "prioridade",
    "CódCodificação":       "code_codificacao",
    "Texto breve nota":     "descricao",
    "Texto longo":          "texto_longo",
    "Tipo de atividade":    "tipo_atividade",
    "Tipo de nota":         "tipo_nota",
    "Ctr.trab.responsável": "centro_trab",
    "Centro de planej.":    "centro_planejamento",
    "Status do usuário":    "status_usuario",
    "Status_Final_ok":      "status_final",
    "Gerência Origem":      "gerencia_origem",
    "Modificado por":       "modificado_por",
    "Subsistema":           "subsistema",
}

# Formato B — Notas Abertas
COLUNAS_FORMATO_B: dict[str, str] = {
    "Nota":               "numero_nota",
    "Ordem":              "ordem",
    "Marcador inic.":     "data_nota",
    "Dt término real":    "data_encerramento",
    "Data bás. início":   "data_planejada",
    "Objeto técnico":     "local_instalacao",
    "Prioridade":         "prioridade",
    "CódCodificação":     "code_codificacao",
    "Descrição":          "descricao",
    "Tipo de atividade":  "tipo_atividade",
    "Tipo de nota":       "tipo_nota",
    "Centro de trabalho": "centro_trab",
    "Status de sistema":  "status_usuario",
    "Subsistema":         "subsistema",
}

# Formato C — Notas Concluídas
COLUNAS_FORMATO_C: dict[str, str] = {
    "Nota":               "numero_nota",
    "Ordem":              "ordem",
    "Ponto de partida":   "data_nota",
    "Data de término":    "data_encerramento",
    "Data planejada":     "data_planejada",
    "Local técnico":      "local_instalacao",
    "Prioridade":         "prioridade",
    "CódigoCodificação":  "code_codificacao",
    "Descrição":          "descricao",
    "Tipo de nota":       "tipo_nota",
    "Ctr trab resp":      "centro_trab",
    "Status usuário":     "status_usuario",
    "Subsistema":         "subsistema",
}

# Formato D — SAP Fiori/BW (export com cabeçalho snake_case, KM em colunas separadas)
# Identificado pela presença de "Número_da_nota"
COLUNAS_FORMATO_D: dict[str, str] = {
    "Número_da_nota":                       "numero_nota",
    "Nº_ordem":                             "ordem",
    "Data_da_nota":                         "data_nota",
    "Data_de_encerramento_da_nota":         "data_encerramento",
    "Data_de_conclusão_desejada":           "data_planejada",
    "Local_de_instalação_TPLNR":            "local_instalacao",
    "Texto_referente_à_prioridade":         "prioridade",
    "Codificação_1":                        "code_codificacao",
    "Texto_breve":                          "descricao",
    "Texto_Longo_Nota":                     "texto_longo",
    "Tipo_atividade_conc":                  "tipo_atividade",
    "Tipo_de_nota":                         "tipo_nota",
    "Centro_de_trabalho_responsável":       "centro_trab",
    "Centro_de_planejamento_de_manutenção": "centro_planejamento",
    "Status_Breve_Usuario":                 "status_usuario",
    "Status_Final_ok":                      "status_final",
    "Status_Breve_Sistema":                 "status_sistema",
    "Gerencia":                             "gerencia_origem",
    "Tipo_anomalia_conc":                   "_anomalia_raw",
    "Linhas":                               "linha",
    # KM: tratadas separadamente em _aplicar_km_formato_d()
    # "Km início" + "Market_Dist_Start_2" → km_real
    # "Km Fim"    + "Maker_Dist_End_1"    → km_fim
}

# endregion


# region ====================== SESSÃO 2: Detecção de Formato ==================

def detectar_formato(df_raw: pd.DataFrame) -> str:
    """
    Detecta qual formato de planilha SAP foi carregado.

    Returns:
        'A' = Unificada clássica
        'B' = Notas Abertas
        'C' = Notas Concluídas
        'D' = SAP Fiori/BW (Número_da_nota em snake_case)
    Raises:
        ValueError se não conseguir detectar.
    """
    colunas = set(df_raw.columns.astype(str))

    # Formato D tem prioridade: identificado por colunas snake_case do Fiori
    if "Número_da_nota" in colunas or any("Número_da" in c for c in colunas):
        return "D"
    if "Status_Final_ok" in colunas:
        return "A"
    if "Marcador inic." in colunas:
        return "B"
    if "Ponto de partida" in colunas:
        return "C"

    # Heurística por colunas parciais
    if any("Status_Final" in c for c in colunas):
        return "A"
    if any("Marcador" in c for c in colunas):
        return "B"
    if any("Ponto" in c for c in colunas):
        return "C"
    if any("mero" in c and "nota" in c.lower() for c in colunas):
        return "D"

    raise ValueError(
        "Formato de planilha não reconhecido. "
        "Certifique-se de enviar um arquivo exportado do SAP (VP ou EE)."
    )


def detectar_disciplina(df_raw: pd.DataFrame, nome_arquivo: str = "") -> str:
    """
    Detecta se a planilha é de VP (Via Permanente) ou EE (Eletroeletrônica).

    Returns:
        'VP' ou 'EE'
    """
    colunas = set(df_raw.columns.astype(str))

    if "Subsistema" in colunas:
        sub_vals = df_raw["Subsistema"].dropna().astype(str).str.upper()
        if any(v in sub_vals.values for v in ["SINALIZ", "ENERGIA", "TELECOM", "WAYSIDE"]):
            return "EE"

    nome_upper = nome_arquivo.upper()
    if "EE" in nome_upper or "ELETR" in nome_upper or "ELETRO" in nome_upper:
        return "EE"
    if "VP" in nome_upper or "VIA" in nome_upper or "PERM" in nome_upper:
        return "VP"

    centros_ee = {"CSPA", "CSPG", "CSVP"}
    centros_vp = {"CIPA", "CIPG", "CIJN", "CFAN", "CFTA", "CFPI"}
    col_centro = next(
        (c for c in colunas if "trab" in c.lower() or "centro" in c.lower()), None
    )
    if col_centro:
        centros_raw = set(df_raw[col_centro].dropna().astype(str).str.upper().unique())
        if centros_raw & centros_ee:
            return "EE"
        if centros_raw & centros_vp:
            return "VP"

    return "VP"

# endregion


# region ====================== SESSÃO 3: Conversão de Datas ===================

_EXCEL_ORIGIN = pd.Timestamp("1899-12-30")


def _converter_data(valor) -> pd.Timestamp | None:
    """
    Converte qualquer representação de data do SAP para pd.Timestamp.
    Aceita: serial numérico Excel, string DD.MM.YYYY, string YYYY-MM-DD, datetime.
    """
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    try:
        if isinstance(valor, (int, float)) and 30000 < valor < 60000:
            return _EXCEL_ORIGIN + pd.Timedelta(days=int(valor))
        if isinstance(valor, pd.Timestamp):
            return valor
        if isinstance(valor, datetime):
            return pd.Timestamp(valor)
        s = str(valor).strip()
        if not s or s in ("nan", "NaT", "None", "0"):
            return None
        if re.match(r"^\d{2}\.\d{2}\.\d{4}$", s):
            return pd.to_datetime(s, format="%d.%m.%Y")
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return pd.to_datetime(s)
        return pd.to_datetime(s, dayfirst=True)
    except Exception:
        return None


def _converter_colunas_data(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    for col in colunas:
        if col in df.columns:
            df[col] = df[col].apply(_converter_data)
    return df

# endregion


# region ====================== SESSÃO 4: Decodificador TPLNR ==================

_RE_TPLNR = re.compile(
    r"MF[-_]"
    r"(?P<ramal>[A-Z0-9]{2,6})"
    r"[-_]"
    r"(?P<origem>[A-Z0-9]{2,6})"
    r"[_\-]"
    r"(?P<destino>[A-Z0-9]{2,6})"
    r"(?:[-_](?P<linha>[^-_\s]*))?"
    r"(?:[-_](?P<ativo>[^-_\s]*))?"
    r"(?:[-_](?P<km_marc>\d+(?:[.,]\d+)?)(?:\+(?P<offset>\d+))?)?",
    re.IGNORECASE,
)


def decodificar_tplnr(tplnr: str) -> dict:
    """
    Extrai ramal, origem, destino (e km quando embutido no TPLNR).

    Exemplos:
      "MF-SJU-IPA_IPA-L000001-AMV258N" → ramal=SJU, origem=IPA, destino=IPA
      "MF-RCO-IPG_IBA"                 → ramal=RCO, origem=IPG, destino=IBA
    """
    resultado = {
        "ramal": None, "trecho": None, "origem": None,
        "destino": None, "linha": None, "ativo": None, "km_real": None,
    }
    if not tplnr or not str(tplnr).strip():
        return resultado

    m = _RE_TPLNR.search(str(tplnr).upper())
    if not m:
        return resultado

    ramal   = m.group("ramal")
    origem  = m.group("origem")
    destino = m.group("destino")

    resultado["ramal"]   = ramal
    resultado["origem"]  = origem
    resultado["destino"] = destino
    resultado["linha"]   = m.group("linha")
    resultado["ativo"]   = m.group("ativo")

    if origem and destino:
        resultado["trecho"] = f"{origem}-{destino}"

    # KM embutido no TPLNR (formatos A/B/C)
    km_marc_str = m.group("km_marc")
    offset_str  = m.group("offset")
    if km_marc_str:
        try:
            km = float(km_marc_str.replace(",", "."))
            km += float(offset_str) / 1000 if offset_str else 0.0
            resultado["km_real"] = round(km, 3)
        except Exception:
            pass

    return resultado


def _aplicar_tplnr_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if "local_instalacao" not in df.columns:
        return df
    decoded = df["local_instalacao"].apply(decodificar_tplnr)
    decoded_df = pd.DataFrame(decoded.tolist(), index=df.index)
    for col in decoded_df.columns:
        if col not in df.columns or df[col].isna().all():
            df[col] = decoded_df[col]
        else:
            mask = df[col].isna()
            df.loc[mask, col] = decoded_df.loc[mask, col]
    return df

# endregion


# region ====================== SESSÃO 5: KM — Formato D =======================

# Limites plausíveis de km para a malha MRS
_KM_MIN = 0.0
_KM_MAX = 800.0


def _extrair_km_formato_d(txt_km, decimal) -> float | None:
    """
    Formato D: "KM30" + 0.089 → 30.089 km.
    Rejeita valores fora de [0, 800] km (sanidade da malha MRS).
    """
    s = str(txt_km).strip().upper() if pd.notna(txt_km) else ""
    m = re.match(r"^KM(\d+(?:\.\d+)?)$", s)
    if not m:
        return None
    base = float(m.group(1))
    dec  = float(decimal) if pd.notna(decimal) else 0.0
    km   = base + dec
    return round(km, 3) if _KM_MIN <= km <= _KM_MAX else None


def _aplicar_km_formato_d(df: pd.DataFrame, df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica extração de km_real e km_fim a partir das colunas brutas do Formato D.

    IMPORTANTE: chamado ANTES de reset_index para que df.index ainda aponte
    para as mesmas linhas de df_raw (o dropna(how='all') pode ter removido
    linhas — reindex alinha corretamente sem quebrar por tamanho).
    """
    idx = df.index  # índices originais (antes do reset_index)

    def _col(nome: str) -> pd.Series:
        if nome in df_raw.columns:
            return df_raw[nome].reindex(idx)
        return pd.Series([None] * len(idx), index=idx)

    s_inicio  = _col("Km início")
    s_offset  = _col("Market_Dist_Start_2")
    s_fim     = _col("Km Fim")
    s_fim_off = _col("Maker_Dist_End_1")

    df["km_real"] = [_extrair_km_formato_d(a, b) for a, b in zip(s_inicio, s_offset)]
    df["km_fim"]  = [_extrair_km_formato_d(a, b) for a, b in zip(s_fim, s_fim_off)]
    return df

# endregion


# region ====================== SESSÃO 6: Família, Defeito e Status =============

def _mapear_familia(code: str, disciplina: str) -> tuple[str, str]:
    if not code or not str(code).strip():
        return ("??", "Outros")
    code = str(code).strip().upper()
    prefixo = re.match(r"^([A-Z]+)", code)
    if not prefixo:
        return ("??", "Outros")
    pref = prefixo.group(1)
    tabela = FAMILIAS_EE if disciplina == "EE" else FAMILIAS_VP
    return (pref, tabela.get(pref, "Outros"))


def _mapear_defeito_legivel(code: str, disciplina: str) -> str:
    if not code:
        return "—"
    code = str(code).strip().upper()
    tabela = GLOSSARIO_EE if disciplina == "EE" else GLOSSARIO_VP
    return tabela.get(code, code)


def _calcular_lead_time(row: pd.Series) -> int | None:
    try:
        inicio = row.get("data_nota")
        fim    = row.get("data_encerramento")
        if pd.isna(inicio) or inicio is None:
            return None
        fim = fim if (fim is not None and not pd.isna(fim)) else pd.Timestamp.now()
        inicio = pd.Timestamp(inicio)
        fim    = pd.Timestamp(fim)
        return max(0, (fim - inicio).days)
    except Exception:
        return None


def _mapear_status_amigavel(status: str) -> str:
    mapa = {
        "ABER": "Aberta",
        "DIFE": "Diferida",
        "CONC": "Concluída",
        "CANC": "Cancelada",
        "PLAN": "Planejada",
        "EXEC": "Em Execução",
        "REWM": "Em Revisão",
        "PRLS": "Liberada",
    }
    if not status:
        return "—"
    s = str(status).upper().strip()
    for chave, val in mapa.items():
        if chave in s:
            return val
    return status

_PESO_PRIORIDADE: dict[str, int] = {
    "1-Muito alta":  5,
    "2-Alta":        4,
    "3-Média":       3,
    "4-Baixa":       2,
    "5-Muito baixa": 1,
    "1": 5,
    "2": 4,
    "3": 3,
    "4": 2,
    "5": 1,
}


def _mapear_peso_prioridade(prio: str) -> int:
    p = str(prio).strip() if prio else ""
    if p in _PESO_PRIORIDADE:
        return _PESO_PRIORIDADE[p]
    return _PESO_PRIORIDADE.get(p[:1], 1)

# endregion


# region ====================== SESSÃO 7: Pipeline Principal ===================

def carregar_planilha(arquivo_bytes, nome_arquivo: str = "") -> pd.DataFrame:
    """Carrega o arquivo Excel bruto sem processamento."""
    try:
        df = pd.read_excel(arquivo_bytes, engine="openpyxl", dtype=str)
        if df.empty or len(df.columns) < 3:
            df = pd.read_excel(arquivo_bytes, engine="openpyxl", header=1, dtype=str)
        return df
    except Exception as e:
        raise ValueError(f"Erro ao ler arquivo Excel: {e}")


def processar_planilha(
    arquivo_bytes,
    nome_arquivo: str,
    gerencia: str,
    disciplina_override: str | None = None,
) -> tuple[pd.DataFrame, str, str]:
    """
    Pipeline completo de processamento de planilha SAP.

    Args:
        arquivo_bytes:       BytesIO do arquivo enviado
        nome_arquivo:        Nome original do arquivo
        gerencia:            'SP' ou 'VP'
        disciplina_override: Força 'VP' ou 'EE' (None = detecta automaticamente)

    Returns:
        tuple (df_processado, formato_detectado, disciplina_detectada)
    """
    # Passo 1: Carregar bruto
    df_raw = carregar_planilha(arquivo_bytes, nome_arquivo)

    # Passo 2: Detectar formato e disciplina
    formato    = detectar_formato(df_raw)
    disciplina = disciplina_override or detectar_disciplina(df_raw, nome_arquivo)

    # Passo 3: Selecionar mapeamento de colunas
    mapa = {
        "A": COLUNAS_FORMATO_A,
        "B": COLUNAS_FORMATO_B,
        "C": COLUNAS_FORMATO_C,
        "D": COLUNAS_FORMATO_D,
    }[formato]

    # Renomeia colunas que existem no DataFrame
    colunas_rename = {k: v for k, v in mapa.items() if k in df_raw.columns}
    df = df_raw.rename(columns=colunas_rename).copy()

    # Remove linhas completamente vazias — SEM reset_index ainda
    # (o índice precisa continuar apontando para df_raw até o passo 6)
    df = df.dropna(how="all")

    # Passo 4: Converter datas
    df = _converter_colunas_data(df, ["data_nota", "data_encerramento", "data_planejada"])

    # Passo 5: Decodificar TPLNR → ramal, origem, destino, trecho
    df = _aplicar_tplnr_dataframe(df)

    # Passo 6: KM real — ANTES do reset_index para manter alinhamento com df_raw
    if formato == "D":
        df = _aplicar_km_formato_d(df, df_raw)
    # Para A/B/C: km já foi extraído do TPLNR em _aplicar_tplnr_dataframe

    # Apenas agora o reset_index é seguro
    df = df.reset_index(drop=True)

    # Passo 7: Normalizar ramal (ASP → VSU, etc.)
    df = normalizar_coluna_ramal(df, "ramal")

    # Passo 8: Defeito legível
    if formato == "D" and "_anomalia_raw" in df.columns:
        # "DM01Dormente de madeira inservível" → "Dormente de madeira inservível"
        df["defeito_legivel"] = df["_anomalia_raw"].str.replace(
            r"^[A-Z]{2}\d{2}", "", regex=True
        ).str.strip()
        df = df.drop(columns=["_anomalia_raw"], errors="ignore")

    # Passo 9: Família a partir do code_codificacao
    if "code_codificacao" in df.columns:
        familia_info = df["code_codificacao"].apply(
            lambda x: _mapear_familia(x, disciplina)
        )
        df["familia_cod"]    = [f[0] for f in familia_info]
        df["familia_defeito"] = [f[1] for f in familia_info]
        if "defeito_legivel" not in df.columns:
            df["defeito_legivel"] = df["code_codificacao"].apply(
                lambda x: _mapear_defeito_legivel(x, disciplina)
            )
    else:
        df["familia_cod"]    = "??"
        df["familia_defeito"] = "Outros"
        df.setdefault("defeito_legivel", pd.Series("—", index=df.index))

    # Passo 10: Status amigável + alias status_nota
    if "status_usuario" in df.columns:
        df["status_amigavel"] = df["status_usuario"].apply(_mapear_status_amigavel)
        df["status_nota"]     = df["status_usuario"]  # alias para compatibilidade

    # Passo 11: Peso prioridade
    if "prioridade" in df.columns:
        df["peso_prio"] = df["prioridade"].apply(_mapear_peso_prioridade)

    # Passo 12: Lead time
    df["lead_time_dias"] = df.apply(_calcular_lead_time, axis=1)

    # Passo 13: Score composto
    df = aplicar_score_dataframe(df, disciplina)

    # Passo 14: Metadados de origem
    df["gerencia"]   = gerencia
    df["disciplina"] = disciplina

    # Passo 15: numero_nota numérico + filtro linhas inválidas
    if "numero_nota" in df.columns:
        df["numero_nota"] = pd.to_numeric(df["numero_nota"], errors="coerce")
        df = df[df["numero_nota"].notna()].reset_index(drop=True)

    return df, formato, disciplina


def df_para_registros_supabase(df: pd.DataFrame, upload_id: str) -> list[dict]:
    """
    Converte o DataFrame processado para lista de dicts prontos para o Supabase.
    """
    colunas_notas = [
        "numero_nota", "ordem", "data_nota", "data_encerramento", "data_planejada",
        "local_instalacao", "ramal", "trecho", "origem", "destino", "linha",
        "ativo", "km_real", "km_fim", "subsistema",
        "prioridade", "peso_prio", "score",
        "code_codificacao", "defeito_legivel", "familia_cod", "familia_defeito",
        "tipo_nota", "tipo_atividade",
        "status_usuario", "status_nota", "status_amigavel", "status_final",
        "status_sistema",
        "centro_trab", "centro_planejamento", "gerencia_origem", "modificado_por",
        "lead_time_dias", "descricao", "texto_longo",
        "gerencia", "disciplina",
    ]

    registros = []
    for _, row in df.iterrows():
        rec = {"upload_id": upload_id}
        for col in colunas_notas:
            val = row.get(col)
            # Captura None, NaT e NaN em uma única verificação
            try:
                if val is None or pd.isnull(val):
                    rec[col] = None
                    continue
            except (TypeError, ValueError):
                pass

            if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                rec[col] = None
            elif isinstance(val, (pd.Timestamp, datetime)):
                rec[col] = val.date().isoformat()
            elif hasattr(val, "item"):
                rec[col] = val.item()
            else:
                rec[col] = val
        registros.append(rec)

    return registros

# endregion
