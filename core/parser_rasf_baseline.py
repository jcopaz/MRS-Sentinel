# core/parser_rasf_baseline.py — Parser da Base de Falhas EE CONGELADA 2025
# Sprint 7 — MRS Sentinel · camada YoY da aba "🔌 Inteligência de Falhas EE"
#
# O congelado 2025 (Base_de_Falhas_Congelado_2025_EE.xlsx, aba "Export") é
# mais enxuto que o RASF vivo (~16 col vs 77) e já traz o campo "Causa"
# classificado. Este parser converte esse arquivo no DataFrame canônico
# gravado em `rasf_baseline` (ver database/schema_rasf_baseline.sql).
#
# Robustez: o cabeçalho do congelado varia um pouco entre exports (acento,
# caixa, espaços, sufixos). Por isso o mapa de colunas é resolvido por um
# nome NORMALIZADO (sem acento, minúsculo, sem espaço/pontuação) + lista de
# aliases — em vez de casar o texto exato. Assim o mesmo parser aceita
# "Tempo THP", "Tempo THP (min)", "Tempo THP 300", etc.
#
# Fluxo: upload xlsx → carregar_baseline_xlsx() → processar_baseline() →
#        df canônico → df_baseline_para_registros() → insert em rasf_baseline.

from __future__ import annotations

import io
import unicodedata

import pandas as pd

# Reaproveita a decodificação de gerência e o Sim/Não do parser do RASF vivo,
# com fallback defensivo caso o import falhe (ambiente parcial/teste).
try:
    from core.parser_rasf import _mapear_gerencia, _sim_nao
except Exception:  # pragma: no cover - fallback defensivo
    def _mapear_gerencia(valor, centro_trab=None):
        from core.glossarios import GERENCIAS_CONHECIDAS, GERENCIA_CODIGO_LEGADO, COORDENACAO_REALOCADA
        if centro_trab:
            coord_sigla = str(centro_trab).strip().upper().split(".")[-1]
            if coord_sigla in COORDENACAO_REALOCADA:
                return COORDENACAO_REALOCADA[coord_sigla]
        if valor is None:
            return None
        sigla = str(valor).strip().upper().split(".")[-1]
        if sigla in GERENCIAS_CONHECIDAS:
            return sigla
        return GERENCIA_CODIGO_LEGADO.get(sigla)

    def _sim_nao(valor) -> bool:
        if valor is None:
            return False
        return str(valor).strip().casefold() in {"sim", "s", "x", "true", "1", "yes"}


# region ====================== SESSÃO 1: Mapa de colunas =======================

def _norm(txt) -> str:
    """Normaliza um cabeçalho: sem acento, minúsculo, só alfanumérico."""
    if txt is None:
        return ""
    s = unicodedata.normalize("NFKD", str(txt))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


# canônica → lista de aliases (cada alias já será _norm()-alizado na resolução).
# A ordem importa: o primeiro alias encontrado no arquivo vence.
_ALIASES: dict[str, list[str]] = {
    "_gerencia_raw":         ["Gerência", "Gerencia", "Departamento", "Depto", "Depart."],
    "numero_nota":           ["Número nota", "Numero nota", "Número da nota", "Nota", "Nº nota", "No nota"],
    "data_nota":             ["Data", "Data nota", "Data da nota", "Data da Notificação", "Data notificação"],
    "desc_tipo_solicitacao": ["Tipo Solicitação", "Tipo de Solicitação", "Descrição Tipo Solicitação",
                              "Tipo Solicitacao"],
    "anomalia_sintoma":      ["Codificação", "Codificacao", "Sintoma", "Anomalia", "Código Anomalia",
                              "Codigo Anomalia"],
    "causa":                 ["Causa", "Causa Raiz", "Causa raiz", "Classificação Causa", "Causa classificada"],
    "local_instalacao":      ["Local Instalação", "Local de instalação", "Local de Instalacao",
                              "Local Instalacao", "TPLNR", "Tplnr"],
    "grupo_ativo":           ["Grupo Ativo", "Grupo do Ativo", "Grupo de Ativo"],
    "sistema":               ["Sistema", "Sistema do Ativo"],
    "status_sistema":        ["Status", "Status Sistema", "Status do Sistema", "Situação", "Situacao"],
    "novo_indicador":        ["Novo Indicador", "Indicador", "Novo indicador"],
    "gerador_thp":           ["Gerador THP", "Gerador THP (300)", "Gerador THP 300", "Gera THP"],
    "thp_min":               ["Tempo THP", "Tempo THP (min)", "Tempo THP 300", "Tempo THP 300 (min)",
                              "THP", "THP (min)", "Minutos THP"],
}

# Colunas do DataFrame canônico gravadas em rasf_baseline
COLUNAS_BASELINE = [
    "gerencia", "disciplina", "ano", "mes", "numero_nota", "data_nota",
    "desc_tipo_solicitacao", "anomalia_sintoma", "causa",
    "local_instalacao", "grupo_ativo", "sistema", "status_sistema",
    "novo_indicador", "gerador_thp", "thp_min",
]

# endregion


# region ====================== SESSÃO 2: Parsing ==============================

def _resolver_colunas(df: pd.DataFrame) -> dict[str, str]:
    """
    Casa cada coluna canônica com a coluna REAL do arquivo pelo nome
    normalizado. Retorna {canonica: nome_real_no_df}. Colunas ausentes
    simplesmente não entram no mapa (tratadas como None depois).
    """
    norm_para_real = {}
    for real in df.columns:
        norm_para_real.setdefault(_norm(real), real)

    resolvido: dict[str, str] = {}
    for canonica, aliases in _ALIASES.items():
        for alias in aliases:
            real = norm_para_real.get(_norm(alias))
            if real is not None:
                resolvido[canonica] = real
                break
    return resolvido


def processar_baseline(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Converte o DataFrame bruto do congelado 2025 no DataFrame canônico.

    - Deriva `gerencia` (SP/VP) de Departamento/Gerência (GEE.xx). Linhas sem
      gerência reconhecida ficam com None (o uploader avisa e descarta).
    - Deriva ano/mes de `data_nota`.
    - `gerador_thp` -> bool; `thp_min` -> numérico (0 em vazio).
    - Preserva `_gerencia_raw` para a mensagem de aviso do uploader.
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=COLUNAS_BASELINE + ["_gerencia_raw"])

    mapa = _resolver_colunas(df_raw)
    out = pd.DataFrame(index=df_raw.index)

    for canonica, real in mapa.items():
        out[canonica] = df_raw[real]

    # Garante presença de todas as colunas canônicas (as ausentes viram NaN)
    for c in COLUNAS_BASELINE:
        if c not in out.columns and c not in ("gerencia", "disciplina", "ano", "mes"):
            out[c] = pd.NA

    # Gerência (mantém bruto para o aviso do uploader)
    if "_gerencia_raw" in out.columns:
        out["gerencia"] = out["_gerencia_raw"].map(_mapear_gerencia)
    else:
        out["_gerencia_raw"] = pd.NA
        out["gerencia"] = None

    out["disciplina"] = "EE"

    # Datas → ano/mes
    if "data_nota" in out.columns:
        out["data_nota"] = pd.to_datetime(out["data_nota"], errors="coerce", dayfirst=True)
    else:
        out["data_nota"] = pd.NaT
    out["ano"] = out["data_nota"].dt.year
    out["mes"] = out["data_nota"].dt.month

    # THP
    if "thp_min" in out.columns:
        out["thp_min"] = pd.to_numeric(out["thp_min"], errors="coerce").fillna(0)
    else:
        out["thp_min"] = 0
    out["gerador_thp"] = (out["gerador_thp"].map(_sim_nao)
                          if "gerador_thp" in out.columns else False)

    # numero_nota numérico quando possível (mantém NaN se não for)
    if "numero_nota" in out.columns:
        out["numero_nota"] = pd.to_numeric(out["numero_nota"], errors="coerce")

    # Remove linhas totalmente vazias (sem data e sem número de nota)
    validade = out["data_nota"].notna() | out.get("numero_nota", pd.Series(index=out.index)).notna()
    out = out[validade].reset_index(drop=True)

    return out


def carregar_baseline_xlsx(arquivo, aba: str | None = None) -> pd.DataFrame:
    """
    Lê o xlsx do congelado 2025 e devolve o DataFrame canônico.

    Tenta a aba "Export" (padrão do congelado); se não existir, usa a primeira.
    """
    if isinstance(arquivo, (bytes, bytearray)):
        arquivo = io.BytesIO(arquivo)

    xls = pd.ExcelFile(arquivo)
    if aba is None:
        aba = "Export" if "Export" in xls.sheet_names else xls.sheet_names[0]
    df_raw = xls.parse(aba)
    return processar_baseline(df_raw)

# endregion


# region ====================== SESSÃO 3: Registros p/ Supabase =================

def _limpar(v):
    """NaN/NaT → None; numpy → tipos nativos (JSON-safe para o insert)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def df_baseline_para_registros(df: pd.DataFrame, upload_id: str) -> list[dict]:
    """Converte o DataFrame canônico em registros prontos para rasf_baseline."""
    if df is None or df.empty:
        return []

    registros: list[dict] = []
    for _, row in df.iterrows():
        reg = {"upload_id": upload_id}
        for col in COLUNAS_BASELINE:
            valor = row.get(col) if col in df.columns else None
            if col == "data_nota" and valor is not None and not pd.isna(valor):
                # DATE em ISO (YYYY-MM-DD) para o Postgres
                try:
                    reg[col] = pd.Timestamp(valor).date().isoformat()
                    continue
                except Exception:
                    reg[col] = None
                    continue
            reg[col] = _limpar(valor)
        registros.append(reg)
    return registros

# endregion
