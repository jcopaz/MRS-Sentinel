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
    """Restrições A da Sub 78 dentro do trecho, com grupo Via/ANTT."""
    if rel is None or rel.empty:
        return pd.DataFrame()
    r = rel[(rel["tipo"] == "restricao_a") & (rel["sub"] == SUB)].copy()
    a = r[["km_de", "km_ate"]].min(axis=1)
    b = r[["km_de", "km_ate"]].max(axis=1)
    r = r[(a <= TRECHO_KM[1] + 1e-9) & (b >= TRECHO_KM[0] - 1e-9)].copy()
    r["a"], r["b"] = a.loc[r.index], b.loc[r.index]
    r["grupo"] = np.where(r["categoria"] == GRUPO_ANTT, "ANTT", "Via")
    return r.reset_index(drop=True)


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


def sb_dos_defeitos(defeitos: pd.DataFrame, dorm: pd.DataFrame) -> pd.Series:
    """SB pelo equipamento (prospecção); na falta, a SB do próprio export."""
    eq = mapa_equipamentos(dorm).set_index("equipamento_siv")["sb"] if dorm is not None and not dorm.empty \
        else pd.Series(dtype=object)
    sb = defeitos["equipamento_siv"].map(eq)
    if "sb" in defeitos.columns:
        sb = sb.fillna(defeitos["sb"])
    return sb


def faixas_sb(dorm: pd.DataFrame) -> pd.DataFrame:
    """
    km início/fim de cada SB, pelas duas linhas — equipamento só em LD (ex.:
    78/302922-303800cv em ZPD-ZFJ) também estende a faixa; senão a densidade
    de defeitos da SB infla (os defeitos dele caem numa faixa só de LP).
    """
    return (dorm.groupby("sb").agg(km_ini=("km_inicio", "min"), km_fim=("km_fim", "max"))
            .sort_values("km_ini").reset_index())

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
