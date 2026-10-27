# =============================================================================
# core/analise_velocidade.py — Velocidade praticada × restrições × dormentes
#
# Entrada: DataFrame da tabela relatorio_velocidade (todas as rotas) e o da
# prospeccao_dormentes (já enriquecido). Tudo por Sub + linha + KM — é a
# chave comum entre o Relatório de Velocidade do SRM e a prospecção.
#
# Velocidade praticada (por trem-tipo) = min(VMA do trem-tipo, restrições A
# que cobrem o ponto). Restrições B (programadas do dia) ficam à parte: são
# janelas de horas, não mudam o perfil permanente.
#
# Exporta:
#   normalizar_relatorio(rel)                 -> rel deduplicado entre rotas
#   rotulos_sub(rel)                          -> {sub: "78 · ITIRAPINA - BAURU"}
#   perfil_velocidade(rel, sub, linha, bitola, trem_tipo) -> trechos contínuos
#   resumo_perfil(perfil)                     -> dict de KPIs
#   cruzar_prospeccao(prosp, rel, perfil_lp_ld) -> segmentos + restrições
# =============================================================================

import numpy as np
import pandas as pd

from core.parser_relatorio_velocidade import categoria_motivo

EXT_MIN_PONTUAL = 0.1  # km — restrição "de == até" (PN, junta) vira 100 m

CHAVE_CONTEUDO = ["tipo", "sub", "sb", "linha", "bitola", "trem_tipo", "km_de", "km_ate",
                  "vel", "motivo", "condicao", "responsavel", "inicio", "fim",
                  "estacao", "trecho_desc", "observacao"]


# region ====================== SESSÃO 1: Preparação ===========================

def _sub_txt(v) -> str | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    t = str(v).strip()
    return t[:-2] if t.endswith(".0") else t


def normalizar_relatorio(rel: pd.DataFrame) -> pd.DataFrame:
    """Subs que aparecem em mais de uma rota (ex.: 70, 71) viriam duplicadas."""
    if rel is None or rel.empty:
        return pd.DataFrame(columns=CHAVE_CONTEUDO + ["rota"])
    rel = rel.copy()
    for c in CHAVE_CONTEUDO:
        if c not in rel.columns:
            rel[c] = None
    rel["sub"] = rel["sub"].map(_sub_txt)
    for c in ("km_de", "km_ate", "vel"):
        rel[c] = pd.to_numeric(rel[c], errors="coerce")
    for c in ("inicio", "fim"):
        rel[c] = pd.to_datetime(rel[c], errors="coerce")
    chave = [c for c in CHAVE_CONTEUDO if c in rel.columns]
    rel = rel.drop_duplicates(subset=chave).reset_index(drop=True)
    rel["categoria"] = np.where(rel["tipo"] == "restricao_a",
                                rel["motivo"].fillna("").map(categoria_motivo), None)
    return rel


def rotulos_sub(rel: pd.DataFrame) -> dict:
    nomes = (rel[rel["tipo"] == "obs_trecho"].dropna(subset=["sub"])
             .groupby("sub")["trecho_desc"].first().to_dict())
    subs = sorted(rel["sub"].dropna().unique(), key=lambda s: (len(s), s))
    return {s: f"{s} · {nomes[s]}" if s in nomes else f"Sub {s}" for s in subs}

# endregion


# region ====================== SESSÃO 2: Perfil de velocidade =================

def _intervalos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["km_de", "km_ate"]).copy()
    a = df[["km_de", "km_ate"]].min(axis=1)
    b = df[["km_de", "km_ate"]].max(axis=1)
    b = np.where(b - a < EXT_MIN_PONTUAL, a + EXT_MIN_PONTUAL, b)
    df["a"], df["b"] = a, b
    return df


def restricoes_da_sub(rel, sub, linha=None, bitola=None, tipo="restricao_a") -> pd.DataFrame:
    r = rel[(rel["tipo"] == tipo) & (rel["sub"] == sub)]
    if linha:
        r = r[r["linha"] == linha]
    if bitola and tipo == "restricao_a":
        r = r[r["bitola"].isna() | (r["bitola"] == bitola)]
    return _intervalos(r)


def perfil_velocidade(rel: pd.DataFrame, sub: str, linha: str,
                      bitola: str, trem_tipo: str) -> pd.DataFrame:
    """
    Trechos contínuos [km_de, km_ate) com vma, v_restr, v_prat e o motivo
    limitante. LD sem VMA própria herda a da LP (o SRM só publica LP na
    maior parte das Subs).
    """
    vma = rel[(rel["tipo"] == "vma") & (rel["sub"] == sub) &
              (rel["bitola"] == bitola) & (rel["trem_tipo"] == trem_tipo)]
    vma_l = vma[vma["linha"] == linha]
    vma = _intervalos(vma_l if len(vma_l) else vma[vma["linha"] == "LP"])
    rA = restricoes_da_sub(rel, sub, linha, bitola)
    if vma.empty and rA.empty:
        return pd.DataFrame()

    pontos = np.unique(np.concatenate([vma["a"], vma["b"], rA["a"], rA["b"]]))
    linhas = []
    for a, b in zip(pontos[:-1], pontos[1:]):
        meio = (a + b) / 2
        cv = vma[(vma["a"] <= meio) & (vma["b"] > meio)]
        cr = rA[(rA["a"] <= meio) & (rA["b"] > meio)]
        v_vma = cv["vel"].min() if len(cv) else np.nan
        if len(cr):
            lim = cr.loc[cr["vel"].idxmin()]
            v_r, motivo, cat, sb = lim["vel"], lim["motivo"], lim["categoria"], lim["sb"]
        else:
            v_r, motivo, cat, sb = np.nan, None, None, None
        if np.isnan(v_vma) and np.isnan(v_r):
            continue
        v_p = np.nanmin([v_vma, v_r])
        restrito = not np.isnan(v_r) and (np.isnan(v_vma) or v_r < v_vma)
        linhas.append(dict(km_de=a, km_ate=b, vma=v_vma, v_restr=v_r, v_prat=v_p,
                           restrito=restrito, motivo=motivo if restrito else None,
                           categoria=cat if restrito else None, sb=sb))
    p = pd.DataFrame(linhas)
    if p.empty:
        return p
    # Junta trechos vizinhos idênticos (menos pontos no gráfico).
    chave = p["vma"].map(str) + "|" + p["v_prat"].map(str) + "|" + p["motivo"].map(str)
    grupo = ((chave != chave.shift()) | (p["km_de"] != p["km_ate"].shift())).cumsum()
    p = (p.groupby(grupo).agg(km_de=("km_de", "first"), km_ate=("km_ate", "last"),
                              vma=("vma", "first"), v_restr=("v_restr", "first"),
                              v_prat=("v_prat", "first"), restrito=("restrito", "first"),
                              motivo=("motivo", "first"), categoria=("categoria", "first"),
                              sb=("sb", "first"))
         .reset_index(drop=True))
    p["ext"] = p["km_ate"] - p["km_de"]
    return p


def resumo_perfil(p: pd.DataFrame) -> dict:
    if p is None or p.empty:
        return {}
    ext = p["ext"].sum()
    com_vma = p.dropna(subset=["vma"])
    vma_media = (com_vma["vma"] * com_vma["ext"]).sum() / com_vma["ext"].sum() if len(com_vma) else np.nan
    # Média harmônica ponderada = velocidade média real de percurso.
    prat = p[p["v_prat"] > 0]
    v_media = prat["ext"].sum() / (prat["ext"] / prat["v_prat"]).sum() if len(prat) else np.nan
    perda = com_vma[(com_vma["v_prat"] > 0) & (com_vma["vma"] > 0)]
    min_perdidos = ((perda["ext"] / perda["v_prat"] - perda["ext"] / perda["vma"]) * 60).sum()
    return dict(
        ext_km=ext, vma_media=vma_media, v_media=v_media,
        km_restrito=p.loc[p["restrito"], "ext"].sum(),
        pct_restrito=p.loc[p["restrito"], "ext"].sum() / ext * 100 if ext else 0,
        min_perdidos=min_perdidos,
        km_ini=p["km_de"].min(), km_fim=p["km_ate"].max(),
    )

# endregion


# region ====================== SESSÃO 3: Cruzamento com a prospecção ==========

def cruzar_prospeccao(prosp: pd.DataFrame, rel: pd.DataFrame,
                      perfis: dict, sub: str) -> pd.DataFrame:
    """
    Para cada segmento prospectado da Sub: restrições A/B sobrepostas,
    velocidade praticada mínima e motivos. `perfis` = {linha: perfil}.
    """
    if prosp is None or prosp.empty:
        return pd.DataFrame()
    seg = prosp[prosp["sub"].map(_sub_txt) == sub].copy()
    if seg.empty:
        return seg
    rA = restricoes_da_sub(rel, sub, tipo="restricao_a")
    rB = restricoes_da_sub(rel, sub, tipo="restricao_b")

    n_a, motivos, cats, v_min_r, n_b, v_prat, vma = [], [], [], [], [], [], []
    for s in seg.itertuples():
        a, b = min(s.km_inicio, s.km_fim), max(s.km_inicio, s.km_fim)
        ra = rA[(rA["linha"] == s.linha) & (rA["a"] < b) & (rA["b"] > a)]
        rb = rB[(rB["linha"] == s.linha) & (rB["a"] < b) & (rB["b"] > a)]
        n_a.append(len(ra))
        motivos.append("; ".join(sorted(ra["motivo"].dropna().unique())) or None)
        cats.append(", ".join(sorted(ra["categoria"].dropna().unique())) or None)
        v_min_r.append(ra["vel"].min() if len(ra) else np.nan)
        n_b.append(len(rb))
        p = perfis.get(s.linha)
        if p is not None and not p.empty:
            pp = p[(p["km_de"] < b) & (p["km_ate"] > a)]
            v_prat.append(pp["v_prat"].min() if len(pp) else np.nan)
            vma.append(pp["vma"].min() if len(pp) else np.nan)
        else:
            v_prat.append(np.nan)
            vma.append(np.nan)
    seg["n_restr_a"] = n_a
    seg["motivos_restr"] = motivos
    seg["categorias_restr"] = cats
    seg["v_restr_min"] = v_min_r
    seg["n_restr_b"] = n_b
    seg["v_prat_min"] = v_prat
    seg["vma_min"] = vma
    seg["restr_via"] = seg["categorias_restr"].fillna("").str.contains("Via permanente")
    return seg

# endregion
