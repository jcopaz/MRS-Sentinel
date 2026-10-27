# =============================================================================
# core/analise_trecho.py — Regras de negócio do trecho Itirapina–Pederneiras
#
# Funções puras (sem Streamlit/banco), usadas pela tela, pelos indicadores
# (core/indicadores_trecho.py) e pelos testes de aceitação.
#
#   - Trecho = Sub 78, km 174,8–303,8 (TRECHO_KM).
#   - Chave de cruzamento: equipamento_siv; equipamento com LP e LD → LP
#     (sem isso os defeitos inflam de 6.359 para 7.267).
#   - Restrições por SB: contadas direto pela faixa de km, sem somar
#     sobreposições.
#   - Vagão de Via: defeito com classe abaixo da VMA é "coberto" quando há
#     restrição A a até 50 m com velocidade ≤ à da classe do defeito.
# =============================================================================

import numpy as np
import pandas as pd

from core.analise_velocidade import perfil_velocidade, resumo_perfil

SUB = "78"
TRECHO_KM = (174.8, 303.8)
TOL_COBERTURA_KM = 0.05
META_TAXA = 0.20
GRUPO_ANTT = "Externa (ANTT/PN/urbano)"


# region ====================== SESSÃO 1: Velocidade / restrições ==============

def recortar(p: pd.DataFrame, a: float = TRECHO_KM[0], b: float = TRECHO_KM[1]) -> pd.DataFrame:
    if p is None or p.empty:
        return p
    p = p.copy()
    p["km_de"] = p["km_de"].clip(a, b)
    p["km_ate"] = p["km_ate"].clip(a, b)
    p["ext"] = p["km_ate"] - p["km_de"]
    return p[p["ext"] > 0].reset_index(drop=True)


def perfil_trecho(rel: pd.DataFrame, linha: str = "LP", bitola: str = "Larga",
                  trem: str = "TQ Carreg") -> pd.DataFrame:
    return recortar(perfil_velocidade(rel, SUB, linha, bitola, trem))


def resumo_velocidade(rel: pd.DataFrame, trem: str = "TQ Carreg") -> dict:
    p = perfil_trecho(rel, "LP", "Larga", trem)
    if p is None or p.empty:
        return {}
    r = resumo_perfil(p)
    com_vma = p.dropna(subset=["vma"])
    r["tempo_marcha_vma_min"] = float((com_vma["ext"] / com_vma["vma"] * 60).sum())
    r["tempo_marcha_prat_min"] = float((p["ext"] / p["v_prat"] * 60).sum())
    return r


def restricoes_trecho(rel: pd.DataFrame) -> pd.DataFrame:
    """
    Restrições A da Sub 78 dentro do trecho (LP + LD, todas as bitolas), com
    grupo Via/ANTT. ÚNICA fonte da contagem no app (Evolução, Dashboard, One
    Page): marco zero = 30 (14 via · 16 ANTT).
    """
    if rel is None or rel.empty:
        return pd.DataFrame()
    r = rel[(rel["tipo"] == "restricao_a") & (rel["sub"] == SUB)].copy()
    a = r[["km_de", "km_ate"]].min(axis=1)
    b = r[["km_de", "km_ate"]].max(axis=1)
    r = r[(a <= TRECHO_KM[1] + 1e-9) & (b >= TRECHO_KM[0] - 1e-9)].copy()
    r["a"], r["b"] = a.loc[r.index], b.loc[r.index]
    r["grupo"] = np.where(r["categoria"] == GRUPO_ANTT, "ANTT", "Via")
    return r.reset_index(drop=True)


def rotulo_restricoes(rA: pd.DataFrame) -> str:
    """'30 (14 via · 16 ANTT)' — formato único das telas."""
    if rA is None or rA.empty:
        return "0"
    via = int((rA["grupo"] == "Via").sum())
    return f"{len(rA)} ({via} via · {len(rA) - via} ANTT)"


def vma_no_km(perfil: pd.DataFrame, kms) -> np.ndarray:
    """VMA vigente em cada km (NaN fora do perfil)."""
    if perfil is None or perfil.empty:
        return np.full(len(kms), np.nan)
    out = []
    for k in kms:
        m = perfil[(perfil["km_de"] <= k) & (perfil["km_ate"] >= k)]
        out.append(m["vma"].min() if len(m) else np.nan)
    return np.array(out, dtype=float)

# endregion


# region ====================== SESSÃO 2: Vagão de Via × restrições ============

def cobertura_restricao(defeitos: pd.DataFrame, rel: pd.DataFrame,
                        tol: float = TOL_COBERTURA_KM) -> pd.DataFrame:
    """
    Para cada defeito com vel_max_classe_kmh: VMA no km, restrição A que o
    cobre (±tol, vel ≤ classe) e se a classe pede velocidade abaixo da VMA.
    """
    d = defeitos[defeitos["vel_max_classe_kmh"].notna()].copy()
    if d.empty:
        return d.assign(vma=np.nan, coberto=False, abaixo_vma=False, restricao=None)
    rA = restricoes_trecho(rel) if rel is not None and not rel.empty else pd.DataFrame()
    perfil = perfil_trecho(rel) if rel is not None and not rel.empty else None
    d["vma"] = vma_no_km(perfil, d["km"].values)
    cob, motivo = [], []
    for k, v in zip(d["km"], d["vel_max_classe_kmh"]):
        if rA.empty:
            cob.append(False)
            motivo.append(None)
            continue
        m = rA[(rA["a"] - tol <= k) & (rA["b"] + tol >= k) & (rA["vel"] <= v)]
        cob.append(len(m) > 0)
        motivo.append(m.iloc[0]["motivo"] if len(m) else None)
    d["coberto"] = cob
    d["restricao"] = motivo
    d["abaixo_vma"] = d["vma"].isna() | (d["vel_max_classe_kmh"] < d["vma"])
    return d


def vagao_sem_restricao(defeitos: pd.DataFrame, rel: pd.DataFrame, viagem: int | None = 180,
                        vel_max: float = 35) -> pd.DataFrame:
    """Defeitos do Vagão de Via (Origem VIA) com classe < vel_max e cobertura."""
    v = defeitos[(defeitos["origem"] == "VIA") & (defeitos["vel_max_classe_kmh"] < vel_max)]
    if viagem is not None:
        v = v[v["numero_viagem"] == viagem]
    return cobertura_restricao(v, rel)

# endregion


# region ====================== SESSÃO 3: Cruzamentos por equipamento / SB =====

def mapa_equipamentos(dorm: pd.DataFrame) -> pd.DataFrame:
    """1 linha por código SIV (LP preferida) com SB, km e taxa."""
    if dorm is None or dorm.empty:
        return pd.DataFrame(columns=["equipamento_siv", "sb", "km_inicio", "km_fim", "linha"])
    d = dorm.copy()
    d["_ord"] = (d["linha"] != "LP").astype(int)
    return (d.sort_values(["_ord", "km_inicio"]).drop_duplicates("equipamento_siv")
            .drop(columns="_ord").reset_index(drop=True))


def defeitos_por_equipamento(defeitos: pd.DataFrame, dorm: pd.DataFrame) -> pd.DataFrame:
    eq = mapa_equipamentos(dorm)
    if defeitos is None or defeitos.empty or eq.empty:
        return eq.assign(defeitos=0, def_por_km=0.0)
    n = defeitos.groupby("equipamento_siv").size().rename("defeitos")
    eq = eq.join(n, on="equipamento_siv").fillna({"defeitos": 0})
    ext = (eq["km_fim"] - eq["km_inicio"]).abs().replace(0, np.nan)
    eq["def_por_km"] = eq["defeitos"] / ext
    return eq


def _sb_vazia(s: pd.Series) -> pd.Series:
    return s.isna() | s.astype(str).str.strip().str.lower().isin(["", "none", "nan", "<na>"])


def sb_dos_defeitos(defeitos: pd.DataFrame, dorm: pd.DataFrame,
                    faixas: pd.DataFrame | None = None) -> pd.Series:
    """SB pelo equipamento (prospecção); na falta, a do export; por último, pelo km."""
    eq = mapa_equipamentos(dorm).set_index("equipamento_siv")["sb"] if dorm is not None and not dorm.empty \
        else pd.Series(dtype=object)
    sb = defeitos["equipamento_siv"].map(eq)
    sb = sb.where(~_sb_vazia(sb), None)
    if "sb" in defeitos.columns:
        sb = sb.fillna(defeitos["sb"].where(~_sb_vazia(defeitos["sb"]), None))
    vazia = _sb_vazia(sb)
    if vazia.any() and "km" in defeitos.columns:
        sb = sb.copy()
        sb[vazia] = [sb_pelo_km(k, faixas) for k in defeitos.loc[vazia, "km"]]
    return sb


# SBs da Rumo no trecho (marco_zero/seed_sb_faixas_itirapina_pederneiras.csv,
# limites tirados do export de defeitos 26/10/2026). NÃO derivar dos pátios do
# layout: a SB ZWY-ZPD vai até 302,2 e passa por Porto Pederneiras (ZPW).
# A tabela itp_sb_faixas (seed) tem os mesmos valores e prevalece quando lida.
SB_FAIXAS = pd.DataFrame([
    ("ZIQ-ZQY", 174.8, 181.715), ("ZQY-ZFH", 181.715, 190.16), ("ZFH-ZWF", 190.16, 196.112),
    ("ZWF-ZBO", 196.112, 206.808), ("ZBO-ZEP", 206.808, 209.936), ("ZEP-ZFG", 209.936, 218.7),
    ("ZFG-ZTR", 218.7, 225.828), ("ZTR-ZTE", 225.828, 233.545), ("ZTE-ZVT", 233.545, 240.013),
    ("ZVT-ZDK", 240.013, 251.29), ("ZDK-ZLF", 251.29, 258.66), ("ZLF-ZJU", 258.66, 275.6),
    ("ZJU-ZWM", 275.6, 282.42), ("ZWM-ZWY", 282.42, 290.435), ("ZWY-ZPD", 290.435, 302.206),
    ("ZPD-ZFJ", 302.206, 303.8),
], columns=["sb", "km_inicio", "km_fim"]).assign(ordem=lambda d: range(1, len(d) + 1))


def _faixas(faixas: pd.DataFrame | None) -> pd.DataFrame:
    if faixas is None or len(faixas) == 0:
        return SB_FAIXAS
    f = faixas.copy()
    f["km_inicio"] = pd.to_numeric(f["km_inicio"], errors="coerce")
    f["km_fim"] = pd.to_numeric(f["km_fim"], errors="coerce")
    return f.sort_values("km_inicio").reset_index(drop=True)


def sb_pelo_km(km, faixas: pd.DataFrame | None = None) -> str | None:
    """SB que contém o km (limite inferior fechado; o último km fecha a última SB)."""
    try:
        k = float(km)
    except (TypeError, ValueError):
        return None
    if np.isnan(k):
        return None
    f = _faixas(faixas)
    m = f[(f["km_inicio"] <= k) & (f["km_fim"] > k)]
    if len(m):
        return m.iloc[0]["sb"]
    if abs(k - f["km_fim"].max()) < 1e-6:
        return f.iloc[-1]["sb"]
    return None


def preencher_sb(df: pd.DataFrame, km_ini: str = "km", km_fim: str | None = None,
                 faixas: pd.DataFrame | None = None, col: str = "sb") -> pd.DataFrame:
    """Completa a coluna SB vazia pelo km (meio do segmento quando houver km_fim)."""
    if df is None or df.empty or km_ini not in df.columns:
        return df
    d = df.copy()
    if col not in d.columns:
        d[col] = None
    vazia = _sb_vazia(d[col])
    if not vazia.any():
        return d
    k = pd.to_numeric(d.loc[vazia, km_ini], errors="coerce")
    if km_fim and km_fim in d.columns:
        k2 = pd.to_numeric(d.loc[vazia, km_fim], errors="coerce")
        k = ((k + k2) / 2).fillna(k)
    d[col] = d[col].astype(object)
    d.loc[vazia, col] = [sb_pelo_km(x, faixas) for x in k]
    return d


def faixas_sb(dorm: pd.DataFrame | None = None, faixas: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    km início/fim de cada SB da Rumo (referência fixa, não mais pela prospecção:
    a Rev 1 não tem SB e equipamento só em LD distorcia a faixa). `dorm` fica
    na assinatura por compatibilidade.
    """
    f = _faixas(faixas)
    return f.rename(columns={"km_inicio": "km_ini"})[["sb", "km_ini", "km_fim"]].reset_index(drop=True)

# endregion


# region ====================== SESSÃO 4: Vagão × limites de geometria ========

# nome do defeito (prefixo) → parâmetro de limites_geometria. Tamanho do
# Vagão vem em mm, mesma unidade dos limites (conferido: empeno 65,9 mm cai
# em C.1, 49,8 mm em C.2-3 — igual à classe da Rumo). VIA DESBITOLADA
# (bitola absoluta) e NIVELAMENTO (sem parâmetro) ficam de fora.
PARAMETRO_DEFEITO = (
    ("EMPENO", "empeno_20m"),
    ("CONJUGADO EMPENO", "empeno_20m"),
    ("DEFEITO CONJUGADO EMP", "empeno_20m"),
    ("TORÇÃO", "torcao_10m"),
    ("VARIAÇÃO RÁPIDA DE BITOLA", "variacao_rapida_bitola_5m"),
    ("ALINHAMENTO DIREITO 10", "desalinhamento_curva_corda_10m"),
    ("ALINHAMENTO ESQUERDO 10", "desalinhamento_curva_corda_10m"),
    ("ALINHAMENTO DIREITO 20", "desalinhamento_tangente_corda_20m"),
    ("ALINHAMENTO ESQUERDO 20", "desalinhamento_tangente_corda_20m"),
    ("SUPERELEVAÇÃO", "superelevacao_max_linha_tronco"),
)


def parametro_do_defeito(nome) -> str | None:
    n = str(nome or "").upper()
    for prefixo, par in PARAMETRO_DEFEITO:
        if n.startswith(prefixo):
            return par
    return None


def limite_pela_vma(defeitos: pd.DataFrame, limites: pd.DataFrame,
                    perfil: pd.DataFrame, bitola: str = "Larga") -> pd.DataFrame:
    """
    Acrescenta parametro, classe_vma, limite_mm e razao_limite (tamanho ÷
    limite da classe da VMA vigente no km). razão > 1 = o defeito passa do
    que a VMA atual admite.
    """
    d = defeitos.copy()
    d["parametro"] = d["nome_defeito"].map(parametro_do_defeito)
    d["vma"] = vma_no_km(perfil, d["km"].values)
    lim = limites[limites["bitola"] == bitola] if limites is not None and len(limites) else pd.DataFrame()
    classes, valores = [], []
    for par, vma in zip(d["parametro"], d["vma"]):
        if lim.empty or par is None or np.isnan(vma):
            classes.append(None)
            valores.append(np.nan)
            continue
        m = lim[(lim["parametro"] == par) & (lim["vel_min_kmh"] <= vma) & (lim["vel_max_kmh"] >= vma)]
        classes.append(m.iloc[0]["classe"] if len(m) else None)
        valores.append(float(m.iloc[0]["limite_mm"]) if len(m) and pd.notna(m.iloc[0]["limite_mm"]) else np.nan)
    d["classe_vma"] = classes
    d["limite_mm"] = valores
    d["razao_limite"] = pd.to_numeric(d["tamanho"], errors="coerce").abs() / d["limite_mm"]
    return d

# endregion
