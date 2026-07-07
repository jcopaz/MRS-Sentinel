# core/alertas.py — Motor de detecção de alertas (Sprint 5)
#
# Detecta dois tipos de alerta sobre as notas de uma gerência/disciplina:
#   • cronico       → mesmo ramal+origem+familia_defeito com >= N notas na
#                     janela de M meses.
#   • reincidencia  → nova nota abre no mesmo ramal+origem+familia até X dias
#                     após o encerramento de outra nota igual.
#
# Granularidade do local: ramal + origem (pátio). KM bin fica para o Sprint 6.
#
# Pipeline:
#   gerar_alertas(gerencia, disciplina)
#     → carrega notas (get_notas_gerencia)
#     → detectar_hotspots_cronicos() + detectar_reincidencia()
#     → classificar_severidade()
#     → retorna DataFrame padronizado
#   persistir_alertas(df_alertas) → upsert em `alertas` por chave_alerta
#
# Sessão 1: Imports & configuração
# Sessão 2: Helpers
# Sessão 3: Detecção — hot-spots crônicos
# Sessão 4: Detecção — reincidência
# Sessão 5: Classificação de severidade
# Sessão 6: Orquestração (gerar_alertas)
# Sessão 7: Persistência (persistir_alertas)

# region ====================== SESSÃO 1: Imports & Configuração ================
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

# Valores canônicos de status (ver core/parser.py _mapear_status_amigavel)
_STATUS_CONCLUIDA_TOKENS = ("conc", "encerr", "fecha", "resolv")

# Limites de severidade (score acumulado do grupo)
_SEV_SCORE_CRITICO = 40.0
_SEV_SCORE_ATENCAO = 15.0

# Limite de lead time que promove severidade (dias)
_SEV_LEAD_CRITICO = 60


@dataclass
class AlertaConfig:
    """Parâmetros do motor de alertas (lidos de `configuracoes` no Supabase)."""
    n_min: int = 3               # nº mínimo de notas para crônico
    janela_meses: int = 6        # janela de análise do crônico
    reincidencia_dias: int = 90  # janela de reabertura da reincidência

# endregion


# region ====================== SESSÃO 2: Helpers ==============================

def carregar_config_alertas() -> AlertaConfig:
    """
    Lê os parâmetros globais de alerta da tabela `configuracoes`.
    Falha graciosamente para os defaults se o banco não responder.
    """
    cfg = AlertaConfig()
    try:
        from database.client import get_supabase
        supabase = get_supabase()
        resp = (
            supabase.table("configuracoes")
            .select("chave, valor")
            .is_("gerencia", "null")
            .in_("chave", ["alerta_n_min", "alerta_janela_meses",
                           "alerta_reincidencia_dias"])
            .execute()
        )
        mapa = {r["chave"]: r["valor"] for r in (resp.data or [])}
        cfg.n_min             = int(_num(mapa.get("alerta_n_min"), cfg.n_min))
        cfg.janela_meses      = int(_num(mapa.get("alerta_janela_meses"), cfg.janela_meses))
        cfg.reincidencia_dias = int(_num(mapa.get("alerta_reincidencia_dias"), cfg.reincidencia_dias))
    except Exception:
        pass
    return cfg


def _num(valor, default):
    """Converte valor JSONB (pode vir como '3', 3, '"3"') para número."""
    if valor is None:
        return default
    try:
        return float(str(valor).strip().strip('"'))
    except (TypeError, ValueError):
        return default


def _is_concluida(row: pd.Series) -> bool:
    """True se a nota está encerrada (por status amigável, usuario ou data)."""
    for campo in ("status_amigavel", "status_usuario", "status_final"):
        v = str(row.get(campo, "")).strip().lower()
        if any(tok in v for tok in _STATUS_CONCLUIDA_TOKENS):
            return True
    return bool(pd.notna(row.get("data_encerramento")))


def _chave_alerta(gerencia, disciplina, tipo, ramal, origem, familia) -> str:
    """Chave de deduplicação estável (usada no UNIQUE do banco)."""
    base = "|".join(str(x) for x in
                    [gerencia, disciplina, tipo, ramal, origem, familia])
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _grupo_local_familia(df: pd.DataFrame) -> list[str]:
    """Colunas de agrupamento disponíveis: ramal, origem, familia_defeito."""
    return [c for c in ("ramal", "origem", "familia_defeito") if c in df.columns]

# endregion


# region ====================== SESSÃO 3: Hot-spots crônicos ===================

def detectar_hotspots_cronicos(df: pd.DataFrame, cfg: AlertaConfig) -> pd.DataFrame:
    """
    Detecta grupos ramal+origem+familia com >= n_min notas nos últimos
    janela_meses. Retorna um DataFrame (uma linha por hot-spot).
    """
    if df.empty:
        return pd.DataFrame()

    cols = _grupo_local_familia(df)
    if not cols or "data_nota" not in df.columns:
        return pd.DataFrame()

    d = df.copy()
    d["data_nota"] = pd.to_datetime(d["data_nota"], errors="coerce")
    corte = pd.Timestamp.now() - pd.DateOffset(months=cfg.janela_meses)
    d = d[d["data_nota"] >= corte]
    if d.empty:
        return pd.DataFrame()

    registros = []
    for chave_vals, g in d.groupby(cols, dropna=False):
        if len(g) < cfg.n_min:
            continue
        vals = chave_vals if isinstance(chave_vals, tuple) else (chave_vals,)
        info = dict(zip(cols, vals))
        notas = _lista_notas(g)
        registros.append({
            "tipo":            "cronico",
            "ramal":           info.get("ramal"),
            "origem":          info.get("origem"),
            "familia_defeito": info.get("familia_defeito"),
            "n_ocorrencias":   int(len(g)),
            "score_acumulado": _score_soma(g),
            "lead_medio":      _lead_medio(g),
            "detalhes": {
                "notas":            notas,
                "janela_meses":     cfg.janela_meses,
                "primeira_nota":    _data_min(g),
                "ultima_nota":      _data_max(g),
                "n_prioridade_alta": _n_prio_alta(g),
            },
        })

    return pd.DataFrame(registros)

# endregion


# region ====================== SESSÃO 4: Reincidência =========================

def detectar_reincidencia(df: pd.DataFrame, cfg: AlertaConfig) -> pd.DataFrame:
    """
    Detecta reabertura: nova nota no mesmo ramal+origem+familia até
    reincidencia_dias após o encerramento de uma nota anterior igual.
    """
    if df.empty or "data_nota" not in df.columns:
        return pd.DataFrame()

    cols = _grupo_local_familia(df)
    if not cols:
        return pd.DataFrame()

    d = df.copy()
    d["data_nota"] = pd.to_datetime(d["data_nota"], errors="coerce")
    if "data_encerramento" in d.columns:
        d["data_encerramento"] = pd.to_datetime(d["data_encerramento"], errors="coerce")
    else:
        d["data_encerramento"] = pd.NaT
    d = d.dropna(subset=["data_nota"])

    registros = []
    for chave_vals, g in d.groupby(cols, dropna=False):
        if len(g) < 2:
            continue
        g = g.sort_values("data_nota")
        encerradas = g[g.apply(_is_concluida, axis=1)]
        if encerradas.empty:
            continue

        pares = []
        for _, fechada in encerradas.iterrows():
            fim = fechada.get("data_encerramento")
            if pd.isna(fim):
                continue
            limite = fim + pd.Timedelta(days=cfg.reincidencia_dias)
            reaberturas = g[(g["data_nota"] > fim) & (g["data_nota"] <= limite)]
            for _, nova in reaberturas.iterrows():
                dias = int((nova["data_nota"] - fim).days)
                pares.append({
                    "nota_fechada":  _nota_id(fechada),
                    "nota_reaberta": _nota_id(nova),
                    "dias_entre":    dias,
                })

        if not pares:
            continue

        vals = chave_vals if isinstance(chave_vals, tuple) else (chave_vals,)
        info = dict(zip(cols, vals))
        registros.append({
            "tipo":            "reincidencia",
            "ramal":           info.get("ramal"),
            "origem":          info.get("origem"),
            "familia_defeito": info.get("familia_defeito"),
            "n_ocorrencias":   int(len(pares)),
            "score_acumulado": _score_soma(g),
            "lead_medio":      _lead_medio(g),
            "detalhes": {
                "pares":              pares,
                "reincidencia_dias":  cfg.reincidencia_dias,
                "menor_intervalo":    min(p["dias_entre"] for p in pares),
            },
        })

    return pd.DataFrame(registros)

# endregion


# region ====================== SESSÃO 5: Severidade ===========================

def classificar_severidade(row: pd.Series) -> str:
    """
    Deriva 'critico' / 'atencao' / 'info' a partir do score acumulado,
    da presença de prioridade alta e do lead time médio.
    """
    score = float(row.get("score_acumulado", 0) or 0)
    lead  = row.get("lead_medio")
    lead  = float(lead) if lead is not None and pd.notna(lead) else 0.0
    detalhes = row.get("detalhes") or {}
    n_prio_alta = int(detalhes.get("n_prioridade_alta", 0) or 0)

    if score >= _SEV_SCORE_CRITICO or lead >= _SEV_LEAD_CRITICO or n_prio_alta >= 2:
        return "critico"
    if score >= _SEV_SCORE_ATENCAO or n_prio_alta >= 1:
        return "atencao"
    return "info"

# endregion


# region ====================== SESSÃO 6: Orquestração =========================

def gerar_alertas(gerencia: str, disciplina: str | None = None,
                  cfg: AlertaConfig | None = None) -> pd.DataFrame:
    """
    Pipeline completo: carrega notas, detecta crônicos + reincidência,
    classifica severidade e devolve um DataFrame pronto para persistir.

    Se disciplina for None, roda para VP e EE separadamente e concatena.
    """
    cfg = cfg or carregar_config_alertas()

    from database.queries import get_notas_gerencia

    discs = [disciplina] if disciplina else ["VP", "EE"]
    frames = []

    for disc in discs:
        df = get_notas_gerencia(gerencia, disc)
        if df.empty:
            continue

        cronicos = detectar_hotspots_cronicos(df, cfg)
        reincid  = detectar_reincidencia(df, cfg)
        parcial  = pd.concat([cronicos, reincid], ignore_index=True)
        if parcial.empty:
            continue

        parcial["gerencia"]   = gerencia
        parcial["disciplina"] = disc
        frames.append(parcial)

    if not frames:
        return pd.DataFrame()

    alertas = pd.concat(frames, ignore_index=True)
    alertas["severidade"] = alertas.apply(classificar_severidade, axis=1)
    alertas["chave_alerta"] = alertas.apply(
        lambda r: _chave_alerta(r["gerencia"], r["disciplina"], r["tipo"],
                                r.get("ramal"), r.get("origem"),
                                r.get("familia_defeito")),
        axis=1,
    )
    return alertas

# endregion


# region ====================== SESSÃO 7: Persistência =========================

def persistir_alertas(df_alertas: pd.DataFrame) -> int:
    """
    Faz upsert dos alertas em `alertas` (por chave_alerta).
    Preserva o `status` de alertas já resolvidos/vistos: o upsert atualiza
    métricas mas NÃO rebaixa o status manualmente definido pelo usuário.

    Retorna o nº de alertas gravados.
    """
    if df_alertas is None or df_alertas.empty:
        return 0

    from database.client import get_supabase
    supabase = get_supabase()

    # Status já definidos manualmente (não sobrescrever para 'novo')
    status_existente = _status_por_chave(supabase,
                                         df_alertas["chave_alerta"].tolist())

    payload = []
    agora = datetime.utcnow().isoformat()
    for _, r in df_alertas.iterrows():
        chave = r["chave_alerta"]
        status = status_existente.get(chave, "novo")
        payload.append({
            "gerencia":        r["gerencia"],
            "disciplina":      r["disciplina"],
            "tipo":            r["tipo"],
            "severidade":      r["severidade"],
            "ramal":           _s(r.get("ramal")),
            "origem":          _s(r.get("origem")),
            "familia_defeito": _s(r.get("familia_defeito")),
            "n_ocorrencias":   int(r.get("n_ocorrencias", 0) or 0),
            "score_acumulado": float(r.get("score_acumulado", 0) or 0),
            "chave_alerta":    chave,
            "detalhes":        _json_safe(r.get("detalhes")),
            "status":          status,
            "atualizado_em":   agora,
        })

    supabase.table("alertas").upsert(payload, on_conflict="chave_alerta").execute()
    return len(payload)


def _status_por_chave(supabase, chaves: list[str]) -> dict:
    """Retorna {chave_alerta: status} dos alertas já existentes no banco."""
    if not chaves:
        return {}
    try:
        resp = (
            supabase.table("alertas")
            .select("chave_alerta, status")
            .in_("chave_alerta", chaves)
            .execute()
        )
        return {r["chave_alerta"]: r["status"] for r in (resp.data or [])}
    except Exception:
        return {}

# endregion


# region ====================== SESSÃO 8: Utilitários de agregação =============

def _lista_notas(g: pd.DataFrame) -> list:
    col = "numero_nota" if "numero_nota" in g.columns else None
    if not col:
        return []
    vals = pd.to_numeric(g[col], errors="coerce").dropna().astype(int).tolist()
    return vals[:50]  # limita o payload


def _nota_id(row: pd.Series):
    v = row.get("numero_nota")
    try:
        return int(v) if pd.notna(v) else None
    except (TypeError, ValueError):
        return None


def _score_soma(g: pd.DataFrame) -> float:
    if "score" not in g.columns:
        return 0.0
    return round(float(pd.to_numeric(g["score"], errors="coerce").fillna(0).sum()), 2)


def _lead_medio(g: pd.DataFrame):
    if "lead_time_dias" not in g.columns:
        return None
    s = pd.to_numeric(g["lead_time_dias"], errors="coerce").dropna()
    return round(float(s.mean()), 1) if not s.empty else None


def _n_prio_alta(g: pd.DataFrame) -> int:
    if "prioridade" not in g.columns:
        return 0
    p = g["prioridade"].astype(str)
    return int(p.str.contains("1-|2-|Muito alta|Alta", na=False).sum())


def _data_min(g: pd.DataFrame):
    if "data_nota" not in g.columns:
        return None
    s = pd.to_datetime(g["data_nota"], errors="coerce").dropna()
    return s.min().date().isoformat() if not s.empty else None


def _data_max(g: pd.DataFrame):
    if "data_nota" not in g.columns:
        return None
    s = pd.to_datetime(g["data_nota"], errors="coerce").dropna()
    return s.max().date().isoformat() if not s.empty else None


def _s(v):
    """Normaliza valor para string ou None (evita NaN no JSON/DB)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return str(v)


def _json_safe(obj):
    """Garante que o dict de detalhes é serializável (sem NaN/np types)."""
    import math
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if hasattr(obj, "item"):
        return obj.item()
    return obj

# endregion
