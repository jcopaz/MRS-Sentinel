# =============================================================================
# core/snapshots.py — Sprint 8 (Memória & Comparações)
#
# "Snapshot" = RECORTE de indicadores (não imagem, não cópia da base). A cada
# upload de notas (base VIVA VP/EE), grava-se/atualiza-se a foto SEMANAL:
# indicadores agregados por (semana ISO × gerência × disciplina × ramal × trecho).
#
# Duas naturezas de comparação no projeto:
#   • RASF/EE  → base CONGELADA por ano (YoY nativo, tabela rasf_baseline).
#   • Notas/VP → base VIVA; aqui o snapshot congela o ESTADO no tempo (score,
#     crônicos, backlog) que não dá pra recompor depois. Métricas de FLUXO
#     (aberturas/encerramentos) usam as datas das próprias notas.
#
# Sessão 1: Helpers de tempo (semana ISO)
# Sessão 2: Flags crônico/reincidente por nota (espelha core/alertas)
# Sessão 3: montar_snapshot() — DataFrame agregado pronto p/ persistir
# Sessão 4: gravar_snapshot() — monta + upsert (hook pós-upload)
# =============================================================================

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd


# region ====================== SESSÃO 1: Tempo (semana ISO) ===================

def semana_iso_de(d) -> dict:
    """
    Devolve os atributos de semana ISO de uma data:
      {semana_iso:'2026-W31', ano:2026, semana:31, data_ref: date(segunda)}
    data_ref = segunda-feira (ISO) da semana — âncora para agregação mensal.
    """
    if d is None:
        d = date.today()
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, pd.Timestamp):
        d = d.date()
    iso = d.isocalendar()  # (ano_iso, semana, dia_semana)
    ano, semana = int(iso[0]), int(iso[1])
    segunda = d - timedelta(days=d.weekday())
    return {
        "semana_iso": f"{ano}-W{semana:02d}",
        "ano": ano,
        "semana": semana,
        "data_ref": segunda,
    }

# endregion


# region ====================== SESSÃO 2: Flags crônico/reincidente ============

_STATUS_CONCLUIDA_TOKENS = ("conc", "encerr", "fecha", "resolv")


def _grupo_cols(df: pd.DataFrame) -> list[str]:
    """Mesma granularidade dos alertas: ramal + origem + família."""
    return [c for c in ("ramal", "origem", "familia_defeito") if c in df.columns]


def _is_concluida(row: pd.Series) -> bool:
    """Nota encerrada? Olha data_encerramento e campos de status textuais."""
    if pd.notna(row.get("data_encerramento")):
        return True
    for campo in ("status_usuario", "status_amigavel", "status_final",
                  "status_nota_ordem"):
        val = str(row.get(campo, "") or "").lower()
        if any(tok in val for tok in _STATUS_CONCLUIDA_TOKENS):
            return True
    return False


def _flags_cronico_reincidente(df: pd.DataFrame, n_min: int = 3,
                               janela_meses: int = 6,
                               reincidencia_dias: int = 90):
    """
    Retorna (serie_cronico, serie_reincidente) booleanas alinhadas ao índice
    de df — mesma lógica de core/alertas, porém marcada por NOTA (não por grupo)
    para permitir agregação por ramal/trecho no snapshot.
    """
    cronico = pd.Series(False, index=df.index)
    reincid = pd.Series(False, index=df.index)

    cols = _grupo_cols(df)
    if not cols or "data_nota" not in df.columns:
        return cronico, reincid

    d = df.copy()
    d["data_nota"] = pd.to_datetime(d["data_nota"], errors="coerce")
    if "data_encerramento" in d.columns:
        d["data_encerramento"] = pd.to_datetime(d["data_encerramento"], errors="coerce")
    else:
        d["data_encerramento"] = pd.NaT

    # Crônico: grupos com >= n_min notas na janela (últimos janela_meses)
    corte = pd.Timestamp.now() - pd.DateOffset(months=janela_meses)
    recentes = d[d["data_nota"] >= corte]
    for _, g in recentes.groupby(cols, dropna=False):
        if len(g) >= n_min:
            cronico.loc[g.index] = True

    # Reincidente: nota aberta até reincidencia_dias após o encerramento de
    # outra nota do mesmo grupo.
    dd = d.dropna(subset=["data_nota"])
    for _, g in dd.groupby(cols, dropna=False):
        if len(g) < 2:
            continue
        g = g.sort_values("data_nota")
        encerradas = g[g.apply(_is_concluida, axis=1)]
        for _, fechada in encerradas.iterrows():
            fim = fechada.get("data_encerramento")
            if pd.isna(fim):
                continue
            limite = fim + pd.Timedelta(days=reincidencia_dias)
            reab = g[(g["data_nota"] > fim) & (g["data_nota"] <= limite)]
            if not reab.empty:
                reincid.loc[reab.index] = True

    return cronico, reincid

# endregion


# region ====================== SESSÃO 3: montar_snapshot ======================

def _col_thp(df: pd.DataFrame) -> str:
    for c in ("thp", "thp_min", "thp_h", "thp_horas"):
        if c in df.columns:
            return c
    return ""


def montar_snapshot(gerencia: str, disciplina: str,
                    df: pd.DataFrame | None = None,
                    ref_date=None,
                    n_min: int = 3, janela_meses: int = 6,
                    reincidencia_dias: int = 90) -> pd.DataFrame:
    """
    Monta a foto SEMANAL agregada por (ramal, trecho) do recorte de notas.

    Args:
        gerencia: 'SP' | 'VP'.
        disciplina: 'VP' | 'EE' (base viva de notas — não RASF).
        df: notas já carregadas (para testes/e2e). Se None, carrega do Supabase
            via database.queries.get_notas_gerencia.
        ref_date: data de referência da semana (default = hoje).

    Returns:
        DataFrame com uma linha por (ramal, trecho) + colunas de métrica e a
        'chave' de deduplicação. Vazio se não houver notas.
    """
    if df is None:
        try:
            from database.queries import get_notas_gerencia
            df = get_notas_gerencia(gerencia, disciplina)
        except Exception:
            df = pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()

    # Score (pesos PADRÃO — congelado e reproduzível, independente da UI)
    if "score" not in d.columns:
        try:
            from core.score_engine import calcular_score_dataframe
            d = calcular_score_dataframe(d)
        except Exception:
            d["score"] = 0.0
    d["score"] = pd.to_numeric(d.get("score"), errors="coerce")

    # Datas e janela ISO da foto
    sem = semana_iso_de(ref_date)
    seg = pd.Timestamp(sem["data_ref"])
    dom = seg + pd.Timedelta(days=6)
    dn = pd.to_datetime(d.get("data_nota"), errors="coerce")
    de = (pd.to_datetime(d["data_encerramento"], errors="coerce")
          if "data_encerramento" in d.columns
          else pd.Series(pd.NaT, index=d.index))

    d["_aberta_semana"] = (dn >= seg) & (dn <= dom)
    d["_enc_semana"] = (de >= seg) & (de <= dom)
    d["_concluida"] = d.apply(_is_concluida, axis=1)
    d["_aberta"] = ~d["_concluida"]

    cronico, reincid = _flags_cronico_reincidente(
        d, n_min=n_min, janela_meses=janela_meses,
        reincidencia_dias=reincidencia_dias)
    d["_cronico"] = cronico
    d["_reincid"] = reincid

    col_thp = _col_thp(d)
    if col_thp:
        d["_thp"] = pd.to_numeric(d[col_thp], errors="coerce").fillna(0.0)
    else:
        d["_thp"] = 0.0

    if "ramal" not in d.columns:
        d["ramal"] = None
    if "trecho" not in d.columns:
        d["trecho"] = None

    linhas = []
    for (ramal, trecho), g in d.groupby(["ramal", "trecho"], dropna=False):
        total = int(len(g))
        n_cron = int(g["_cronico"].sum())
        ramal_s = None if pd.isna(ramal) else str(ramal)
        trecho_s = None if pd.isna(trecho) else str(trecho)
        chave = "|".join([
            sem["semana_iso"], gerencia, disciplina,
            ramal_s or "-", trecho_s or "-",
        ])
        score_med = g["score"].mean()
        linhas.append({
            "semana_iso": sem["semana_iso"],
            "ano": sem["ano"],
            "semana": sem["semana"],
            "data_ref": sem["data_ref"].isoformat(),
            "gerencia": gerencia,
            "disciplina": disciplina,
            "ramal": ramal_s,
            "trecho": trecho_s,
            "total_notas": total,
            "notas_abertas": int(g["_aberta"].sum()),
            "aberturas_periodo": int(g["_aberta_semana"].sum()),
            "encerramentos_periodo": int(g["_enc_semana"].sum()),
            "thp_acumulado": round(float(g["_thp"].sum()), 2),
            "score_medio": (None if pd.isna(score_med)
                            else round(float(score_med), 4)),
            "notas_cronicas": n_cron,
            "pct_cronico": (round(100.0 * n_cron / total, 1) if total else 0.0),
            "reincidentes": int(g["_reincid"].sum()),
            "chave": chave,
        })

    return pd.DataFrame(linhas)

# endregion


# region ====================== SESSÃO 4: gravar_snapshot ======================

def gravar_snapshot(gerencia: str, disciplina: str,
                    df: pd.DataFrame | None = None) -> int:
    """
    Monta a foto semanal e faz upsert na tabela `snapshots` (anti-duplicação
    por 'chave'). Retorna o nº de linhas gravadas/atualizadas. Falha
    graciosamente (retorna 0) — nunca deve invalidar o upload que a disparou.
    """
    try:
        snap = montar_snapshot(gerencia, disciplina, df=df)
        if snap.empty:
            return 0
        from database.queries_snapshots import upsert_snapshots
        return upsert_snapshots(snap)
    except Exception:
        return 0

# endregion
