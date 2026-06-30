# core/parser.py — Parser universal de planilhas SAP (VP e EE)
#
# Detecta automaticamente o formato da planilha:
#   Formato A — Unificada:        possui coluna 'Status_Final_ok'
#   Formato B — Notas Abertas:    possui coluna 'Marcador inic.'
#   Formato C — Notas Concluídas: possui coluna 'Ponto de partida'
#
# Pipeline de processamento:
#   1. Detectar formato
#   2. Renomear colunas para padrão interno
#   3. Converter datas (serial Excel e string)
#   4. Decodificar TPLNR → ramal, trecho, origem, destino
#   5. Calcular KM real (KM_marc + offset/1000)
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


# region ====================== SESSÃO 1: Mapeamento de Colunas ======================

# Mapeamento: nome SAP → nome interno padrão
# Formato A — Unificada
COLUNAS_FORMATO_A: dict[str, str] = {
    "Nota":                "numero_nota",
    "Ordem":               "ordem",
    "Dt.vig.início":       "data_nota",
    "Data de encerramento":"data_encerramento",
    "Data planejada":      "data_planejada",
    "Local de instalação": "local_instalacao",
    "Prioridade":          "prioridade",
    "CódCodificação":      "code_codificacao",
    "Texto breve nota":    "descricao",
    "Texto longo":         "texto_longo",
    "Tipo de atividade":   "tipo_atividade",
    "Tipo de nota":        "tipo_nota",
    "Ctr.trab.responsável":"centro_trab",
    "Centro de planej.":   "centro_planejamento",
    "Status do usuário":   "status_usuario",
    "Status_Final_ok":     "status_final",
    "Gerência Origem":     "gerencia_origem",
    "Modificado por":      "modificado_por",
    "Subsistema":          "subsistema",
}

# Formato B — Notas Abertas
COLUNAS_FORMATO_B: dict[str, str] = {
    "Nota":                "numero_nota",
    "Ordem":               "ordem",
    "Marcador inic.":      "data_nota",
    "Dt término real":     "data_encerramento",
    "Data bás. início":    "data_planejada",
    "Objeto técnico":      "local_instalacao",
    "Prioridade":          "prioridade",
    "CódCodificação":      "code_codificacao",
    "Descrição":           "descricao",
    "Tipo de atividade":   "tipo_atividade",
    "Tipo de nota":        "tipo_nota",
    "Centro de trabalho":  "centro_trab",
    "Status de sistema":   "status_usuario",
    "Subsistema":          "subsistema",
}

# Formato C — Notas Concluídas
COLUNAS_FORMATO_C: dict[str, str] = {
    "Nota":                "numero_nota",
    "Ordem":               "ordem",
    "Ponto de partida":    "data_nota",
    "Data de término":     "data_encerramento",
    "Data planejada":      "data_planejada",
    "Local técnico":       "local_instalacao",
    "Prioridade":          "prioridade",
    "CódigoCodificação":   "code_codificacao",
    "Descrição":           "descricao",
    "Tipo de nota":        "tipo_nota",
    "Ctr trab resp":       "centro_trab",
    "Status usuário":      "status_usuario",
    "Subsistema":          "subsistema",
}

# endregion


# region ====================== SESSÃO 2: Detecção de Formato ======================

def detectar_formato(df_raw: pd.DataFrame) -> str:
    """
    Detecta qual dos 3 formatos de planilha SAP foi carregado.

    Returns:
        'A' = Unificada | 'B' = Notas Abertas | 'C' = Notas Concluídas
    Raises:
        ValueError se não conseguir detectar.
    """
    colunas = set(df_raw.columns.astype(str))

    if "Status_Final_ok" in colunas:
        return "A"
    elif "Marcador inic." in colunas:
        return "B"
    elif "Ponto de partida" in colunas:
        return "C"
    else:
        # Tenta heurística por colunas parciais
        if any("Status_Final" in c for c in colunas):
            return "A"
        if any("Marcador" in c for c in colunas):
            return "B"
        if any("Ponto" in c for c in colunas):
            return "C"
        raise ValueError(
            "Formato de planilha não reconhecido. "
            "Certifique-se de enviar um arquivo exportado do SAP (VP ou EE)."
        )


def detectar_disciplina(df_raw: pd.DataFrame, nome_arquivo: str = "") -> str:
    """
    Detecta se a planilha é de VP (Via Permanente) ou EE (Eletroeletrônica).
    Usa presença da coluna Subsistema e centros de trabalho como heurística.

    Returns:
        'VP' ou 'EE'
    """
    colunas = set(df_raw.columns.astype(str))

    # EE tem sempre a coluna Subsistema
    if "Subsistema" in colunas:
        # Confere se tem valores típicos de EE
        sub_vals = df_raw["Subsistema"].dropna().astype(str).str.upper()
        if any(v in sub_vals.values for v in ["SINALIZ", "ENERGIA", "TELECOM", "WAYSIDE"]):
            return "EE"

    # Verifica nome do arquivo
    nome_upper = nome_arquivo.upper()
    if "EE" in nome_upper or "ELETR" in nome_upper or "ELETRO" in nome_upper:
        return "EE"
    if "VP" in nome_upper or "VIA" in nome_upper or "PERM" in nome_upper:
        return "VP"

    # Verifica centros de trabalho
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

    return "VP"  # fallback seguro

# endregion


# region ====================== SESSÃO 3: Conversão de Datas ======================

_EXCEL_ORIGIN = pd.Timestamp("1899-12-30")

def _converter_data(valor) -> pd.Timestamp | None:
    """
    Converte qualquer representação de data do SAP para pd.Timestamp.
    Aceita: serial numérico Excel, string DD.MM.YYYY, string YYYY-MM-DD, datetime.
    Retorna None se inválido.
    """
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    try:
        # Serial numérico Excel (ex: 45123)
        if isinstance(valor, (int, float)) and 30000 < valor < 60000:
            return _EXCEL_ORIGIN + pd.Timedelta(days=int(valor))

        # Já é Timestamp
        if isinstance(valor, pd.Timestamp):
            return valor

        # datetime nativo
        if isinstance(valor, datetime):
            return pd.Timestamp(valor)

        # String
        s = str(valor).strip()
        if not s or s in ("nan", "NaT", "None", "0"):
            return None

        # Formato DD.MM.YYYY (padrão SAP)
        if re.match(r"^\d{2}\.\d{2}\.\d{4}$", s):
            return pd.to_datetime(s, format="%d.%m.%Y")

        # Formato YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return pd.to_datetime(s)

        # Tentativa genérica
        return pd.to_datetime(s, dayfirst=True)

    except Exception:
        return None


def _converter_colunas_data(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    """Aplica _converter_data em múltiplas colunas do DataFrame."""
    for col in colunas:
        if col in df.columns:
            df[col] = df[col].apply(_converter_data)
    return df

# endregion


# region ====================== SESSÃO 4: Decodificador TPLNR ======================

# Padrão: MF-{RAMAL}-{ORIGEM}_{DESTINO}-{LINHA}-{ATIVO}-{KM_MARC}+{OFFSET}
_RE_TPLNR = re.compile(
    r"MF[-_]"
    r"(?P<ramal>[A-Z0-9]{2,6})"
    r"[-_]"
    r"(?P<origem>[A-Z0-9]{2,6})"
    r"[_\-]"
    r"(?P<destino>[A-Z0-9]{2,6})"
    r"[-_]"
    r"(?P<linha>[^-_\s]*)"
    r"(?:[-_](?P<ativo>[^-_\s]*))?"
    r"(?:[-_](?P<km_marc>\d+(?:[.,]\d+)?)(?:\+(?P<offset>\d+))?)?",
    re.IGNORECASE,
)


def decodificar_tplnr(tplnr: str) -> dict:
    """
    Extrai campos geográficos do Local de Instalação (TPLNR).

    Args:
        tplnr: String no formato MF-SJU-IPA_IPA-L000001-AMV258N

    Returns:
        dict com: ramal, trecho, origem, destino, linha, ativo, km_real
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
    linha   = m.group("linha")
    ativo   = m.group("ativo")
    km_marc_str = m.group("km_marc")
    offset_str  = m.group("offset")

    resultado["ramal"]   = ramal
    resultado["origem"]  = origem
    resultado["destino"] = destino
    resultado["linha"]   = linha
    resultado["ativo"]   = ativo

    if origem and destino:
        resultado["trecho"] = f"{origem}-{destino}"

    # KM real = KM_marc + offset/1000
    if km_marc_str:
        try:
            km_marc = float(km_marc_str.replace(",", "."))
            offset  = float(offset_str) / 1000 if offset_str else 0.0
            resultado["km_real"] = round(km_marc + offset, 3)
        except Exception:
            pass

    return resultado


def _aplicar_tplnr_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica decodificar_tplnr em toda a coluna 'local_instalacao'
    e adiciona as colunas geográficas ao DataFrame.
    """
    if "local_instalacao" not in df.columns:
        return df

    decoded = df["local_instalacao"].apply(decodificar_tplnr)
    decoded_df = pd.DataFrame(decoded.tolist(), index=df.index)

    # Preenche só se a coluna ainda não foi populada por outra fonte
    for col in decoded_df.columns:
        if col not in df.columns or df[col].isna().all():
            df[col] = decoded_df[col]
        else:
            # Complementa NaN
            mask = df[col].isna()
            df.loc[mask, col] = decoded_df.loc[mask, col]

    return df

# endregion


# region ====================== SESSÃO 5: Mapeamento de Família e Defeito ======================

def _mapear_familia(code: str, disciplina: str) -> tuple[str, str]:
    """
    Mapeia código de defeito para (familia_cod, familia_defeito) e (defeito_legivel).

    Args:
        code:       Código do defeito (ex: 'AM15', 'SN07')
        disciplina: 'VP' ou 'EE'

    Returns:
        tuple (familia_cod, familia_defeito)
    """
    if not code or not str(code).strip():
        return ("??", "Outros")

    code = str(code).strip().upper()
    # Extrai prefixo alfabético (ex: 'AM' de 'AM15', 'SN' de 'SN07')
    prefixo = re.match(r"^([A-Z]+)", code)
    if not prefixo:
        return ("??", "Outros")

    pref = prefixo.group(1)
    tabela = FAMILIAS_EE if disciplina == "EE" else FAMILIAS_VP
    familia = tabela.get(pref, "Outros")
    return (pref, familia)


def _mapear_defeito_legivel(code: str, disciplina: str) -> str:
    """Retorna descrição legível do código de defeito."""
    if not code:
        return "—"
    code = str(code).strip().upper()
    tabela = GLOSSARIO_EE if disciplina == "EE" else GLOSSARIO_VP
    return tabela.get(code, code)  # Fallback: mostra o próprio código


def _calcular_lead_time(row: pd.Series) -> int | None:
    """Calcula lead time em dias entre data_nota e data_encerramento (ou hoje)."""
    try:
        inicio = row.get("data_nota")
        fim    = row.get("data_encerramento")

        if pd.isna(inicio) or inicio is None:
            return None

        fim = fim if (fim is not None and not pd.isna(fim)) else pd.Timestamp.now()

        if hasattr(inicio, "date"):
            inicio = pd.Timestamp(inicio)
        if hasattr(fim, "date"):
            fim = pd.Timestamp(fim)

        delta = (fim - inicio).days
        return max(0, delta)
    except Exception:
        return None


def _mapear_status_amigavel(status: str) -> str:
    """Converte status técnico SAP para texto amigável."""
    mapa = {
        "ABER": "Aberta",
        "DIFE": "Diferida",
        "CONC": "Concluída",
        "CANC": "Cancelada",
        "PLAN": "Planejada",
        "EXEC": "Em Execução",
    }
    if not status:
        return "—"
    s = str(status).upper().strip()
    for chave, val in mapa.items():
        if chave in s:
            return val
    return status


def _mapear_peso_prioridade(prio: str) -> int:
    """Retorna peso numérico da prioridade."""
    from core.score_engine import PESO_PRIORIDADE
    return PESO_PRIORIDADE.get(str(prio).strip(), 1)

# endregion


# region ====================== SESSÃO 6: Pipeline Principal ======================

def carregar_planilha(arquivo_bytes, nome_arquivo: str = "") -> pd.DataFrame:
    """
    Etapa 1: Carrega o arquivo Excel bruto sem processamento.
    Tenta múltiplas abas comuns do SAP.
    """
    try:
        # Tenta aba padrão
        df = pd.read_excel(arquivo_bytes, engine="openpyxl", dtype=str)
        if df.empty or len(df.columns) < 3:
            # Tenta com header na linha 1
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
        nome_arquivo:        Nome original do arquivo (para detecção)
        gerencia:            'SP' ou 'VP'
        disciplina_override: Força 'VP' ou 'EE' (None = detecta automaticamente)

    Returns:
        tuple (df_processado, formato_detectado, disciplina_detectada)

    Raises:
        ValueError em caso de formato não reconhecido ou dados insuficientes.
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
    }[formato]

    # Renomeia colunas que existem
    colunas_rename = {k: v for k, v in mapa.items() if k in df_raw.columns}
    df = df_raw.rename(columns=colunas_rename).copy()

    # Remove linhas completamente vazias
    df = df.dropna(how="all").reset_index(drop=True)

    # Passo 4: Converter datas
    colunas_data = ["data_nota", "data_encerramento", "data_planejada"]
    df = _converter_colunas_data(df, colunas_data)

    # Passo 5: Decodificar TPLNR
    df = _aplicar_tplnr_dataframe(df)

    # Passo 6: Normalizar ramal (ASP → VSU, etc.)
    df = normalizar_coluna_ramal(df, "ramal")

    # Passo 7: Mapear família e defeito legível
    if "code_codificacao" in df.columns:
        familia_info = df["code_codificacao"].apply(
            lambda x: _mapear_familia(x, disciplina)
        )
        df["familia_cod"]    = [f[0] for f in familia_info]
        df["familia_defeito"] = [f[1] for f in familia_info]
        df["defeito_legivel"] = df["code_codificacao"].apply(
            lambda x: _mapear_defeito_legivel(x, disciplina)
        )
    else:
        df["familia_cod"]    = "??"
        df["familia_defeito"] = "Outros"
        df["defeito_legivel"] = "—"

    # Passo 8: Status amigável e peso prioridade
    if "status_usuario" in df.columns:
        df["status_amigavel"] = df["status_usuario"].apply(_mapear_status_amigavel)
    if "prioridade" in df.columns:
        df["peso_prio"] = df["prioridade"].apply(_mapear_peso_prioridade)

    # Passo 9: Lead time
    df["lead_time_dias"] = df.apply(_calcular_lead_time, axis=1)

    # Passo 10: Score composto
    df = aplicar_score_dataframe(df, disciplina)

    # Passo 11: Adicionar metadados de origem
    df["gerencia"]    = gerencia
    df["disciplina"]  = disciplina

    # Passo 12: Converter numero_nota para numérico
    if "numero_nota" in df.columns:
        df["numero_nota"] = pd.to_numeric(df["numero_nota"], errors="coerce")

    # Filtra notas sem número (cabeçalhos extras, totais, etc.)
    if "numero_nota" in df.columns:
        df = df[df["numero_nota"].notna()].reset_index(drop=True)

    return df, formato, disciplina


def df_para_registros_supabase(df: pd.DataFrame, upload_id: str) -> list[dict]:
    """
    Converte o DataFrame processado para lista de dicts prontos para inserção no Supabase.
    Trata NaN, NaT e Infinity para garantir JSON válido.

    Args:
        df:        DataFrame processado por processar_planilha()
        upload_id: UUID do registro em uploads_historico

    Returns:
        Lista de dicts para inserção em lote no Supabase
    """
    # Colunas que mapeiam para a tabela 'notas'
    colunas_notas = [
        "numero_nota", "ordem", "data_nota", "data_encerramento", "data_planejada",
        "local_instalacao", "ramal", "trecho", "origem", "destino", "linha",
        "ativo", "km_real", "km_fim_real", "subsistema",
        "prioridade", "peso_prio", "score",
        "code_codificacao", "defeito_legivel", "familia_cod", "familia_defeito",
        "tipo_nota", "tipo_atividade",
        "status_usuario", "status_amigavel", "status_final", "status_nota_ordem",
        "centro_trab", "centro_planejamento", "gerencia_origem", "modificado_por",
        "lead_time_dias", "descricao", "texto_longo", "texto_code",
        "gerencia", "disciplina",
    ]

    registros = []
    for _, row in df.iterrows():
        rec = {"upload_id": upload_id}
        for col in colunas_notas:
            val = row.get(col)
            # Sanitização: converte NaN/NaT/Inf para None
            if val is None:
                rec[col] = None
            elif isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                rec[col] = None
            elif isinstance(val, pd.Timestamp):
                rec[col] = val.date().isoformat() if not pd.isna(val) else None
            elif hasattr(val, "item"):
                rec[col] = val.item()  # numpy scalar → Python nativo
            else:
                rec[col] = val
        registros.append(rec)

    return registros

# endregion
