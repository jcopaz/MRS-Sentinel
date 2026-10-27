# =============================================================================
# core/indicadores_trecho.py — Foto dos indicadores de uma base do trecho
#
# calcular(dados, data_base) é PURA: recebe os DataFrames da base e devolve
# a foto em formato longo (escopo, chave, indicador, valor) — escopos:
#   'trecho' (chave TOTAL) · 'sb' · 'equipamento' · 'ponto_critico' ·
#   'transit' (chave = sentido) · 'mes' (chave = 'AAAA-MM|sentido').
# calcular_indicadores(base_id) carrega do banco, calcula e faz upsert em
# trecho_indicadores (roda ao fim de cada upload e antes de congelar).
#
# CATALOGO define rótulo, sentido bom (para as setas ▲▼ da Evolução) e
# formato de cada indicador do escopo 'trecho'.
# =============================================================================

from datetime import date

import numpy as np
import pandas as pd

from core.analise_trecho import (
    TRECHO_KM, META_TAXA, GRUPO_ANTT, perfil_trecho, resumo_velocidade, restricoes_trecho, vagao_sem_restricao,
    defeitos_por_equipamento, sb_dos_defeitos, faixas_sb, preencher_sb,
)
from core.parser_prospeccao import JUNTAS_PROBLEMA

# indicador → (rótulo, sentido, formato)
CATALOGO = {
    "dormentes_prospectados":  ("Dormentes prospectados", "neutro", "int"),
    "dormentes_inserviveis":   ("Dormentes inservíveis", "menor_melhor", "int"),
    "taxa_inserviveis_pct":    ("Taxa de inservíveis", "menor_melhor", "pct"),
    "acima_meta20":            ("Dormentes acima da meta 20%", "menor_melhor", "int"),
    "dormentes_acidentados":   ("Dormentes acidentados", "menor_melhor", "int"),
    "defeitos_ativos":         ("Defeitos ativos", "menor_melhor", "int"),
    "defeitos_por_km":         ("Defeitos por km", "menor_melhor", "dec"),
    "defeitos_classe_ate40":   ("Defeitos classe ≤ 40 km/h", "menor_melhor", "int"),
    "defeitos_mais_1ano":      ("Defeitos ativos > 1 ano", "menor_melhor", "int"),
    "defeitos_criticos":       ("Defeitos críticos", "menor_melhor", "int"),
    "vagao_defeitos":          ("Defeitos do Vagão de Via", "menor_melhor", "int"),
    "vagao_sem_restricao":     ("Vagão < 35 km/h sem restrição", "menor_melhor", "int"),
    "restricoes_a":            ("Restrições A", "menor_melhor", "int"),
    "restricoes_via":          ("Restrições de via", "menor_melhor", "int"),
    "restricoes_antt":         ("Restrições ANTT", "menor_melhor", "int"),
    "km_restrito":             ("Km sob restrição A", "menor_melhor", "dec"),
    "km_restrito_via":         ("Km sob restrição de via", "menor_melhor", "dec"),
    "tempo_marcha_prat_min":   ("Tempo de marcha praticado", "menor_melhor", "min"),
    "vma_media":               ("VMA média TQ carregado", "maior_melhor", "kmh"),
    "v_media_praticada":       ("Velocidade praticada", "maior_melhor", "kmh"),
    "tempo_marcha_vma_min":    ("Tempo de marcha na VMA", "menor_melhor", "min"),
    "minutos_perdidos":        ("Perda por restrições", "menor_melhor", "min"),
    "juntas_problema":         ("Juntas com problema", "menor_melhor", "int"),
    "trilho_fora_m":           ("Trilho fora do limite", "menor_melhor", "m"),
    "bolsoes":                 ("Bolsões de lastro", "menor_melhor", "int"),
    "fixacao_faltantes":       ("Fixações faltantes", "menor_melhor", "int"),
    "inspecao_registros":      ("Registros de inspeção", "neutro", "int"),
}
CATALOGO_TRANSIT = {
    "mediana": ("Transit time mediana", "menor_melhor", "h"),
    "p90":     ("Transit time P90", "menor_melhor", "h"),
    "aderencia": ("Aderência ao programado (+1 h)", "maior_melhor", "pct"),
}


def _linhas(escopo, chave, valores: dict) -> list[dict]:
    return [{"escopo": escopo, "chave": str(chave), "indicador": k,
             "valor": None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)}
            for k, v in valores.items()]


def _ativos(defeitos: pd.DataFrame) -> pd.DataFrame:
    if defeitos is None or defeitos.empty:
        return pd.DataFrame()
    d = defeitos.copy()
    if "status" in d.columns:
        d = d[d["status"].fillna("Ativo") == "Ativo"]
    return d


def _bloco_dormentes(dorm: pd.DataFrame) -> dict:
    if dorm is None or dorm.empty:
        return {}
    tot = dorm["total_prospectado"].sum()
    ins = dorm["qtd_inservivel"].sum()
    acima = (dorm["qtd_inservivel"] - META_TAXA * dorm["total_prospectado"]).clip(lower=0).sum()
    out = {"equipamentos": len(dorm), "dormentes_prospectados": tot, "dormentes_inserviveis": ins,
           "taxa_inserviveis_pct": ins / tot * 100 if tot else np.nan, "acima_meta20": acima}
    if "qtd_acidentado" in dorm.columns:
        out["dormentes_acidentados"] = pd.to_numeric(dorm["qtd_acidentado"], errors="coerce").sum()
    return out


def _bloco_defeitos(defeitos: pd.DataFrame, rel) -> dict:
    d = _ativos(defeitos)
    if d.empty:
        return {}
    ext = TRECHO_KM[1] - TRECHO_KM[0]
    vel = pd.to_numeric(d["vel_max_classe_kmh"], errors="coerce")
    out = {
        "defeitos_ativos": len(d), "defeitos_por_km": len(d) / ext,
        "defeitos_classe_ate40": int((vel <= 40).sum()),
        "defeitos_mais_1ano": int((pd.to_numeric(d["dias_ativo"], errors="coerce") > 365).sum()),
        "defeitos_criticos": int((d.get("classificacao") == "Crítico").sum()),
        "defeitos_corretivos": int((d.get("classificacao") == "Corretivo").sum()),
        "defeitos_perimetro_urbano": int((d.get("perimetro_urbano") == True).sum()),  # noqa: E712
        "defeitos_acidente": int((d.get("acidente") == True).sum()),  # noqa: E712
        "vagao_defeitos": int((d["origem"] == "VIA").sum()),
    }
    if rel is not None and not rel.empty:
        v = vagao_sem_restricao(d, rel, viagem=None)
        if len(v):
            ultima = pd.to_numeric(v["numero_viagem"], errors="coerce").max()
            v = v[pd.to_numeric(v["numero_viagem"], errors="coerce") == ultima]
            out["vagao_classe_menor35"] = len(v)
            out["vagao_sem_restricao"] = int((~v["coberto"]).sum())
    return out


def _bloco_velocidade(rel) -> dict:
    if rel is None or rel.empty:
        return {}
    r = resumo_velocidade(rel)
    rA = restricoes_trecho(rel)
    out = {"restricoes_a": len(rA), "restricoes_via": int((rA["grupo"] == "Via").sum()),
           "restricoes_antt": int((rA["grupo"] == "ANTT").sum())}
    p = perfil_trecho(rel)
    if p is not None and not p.empty and "restrito" in p.columns:
        via = p[p["restrito"].fillna(False) & (p["categoria"] != GRUPO_ANTT)]
        out["km_restrito_via"] = float(via["ext"].sum())
    if r:
        out.update(vma_media=r["vma_media"], v_media_praticada=r["v_media"],
                   km_restrito=r["km_restrito"], minutos_perdidos=r["min_perdidos"],
                   tempo_marcha_vma_min=r["tempo_marcha_vma_min"],
                   tempo_marcha_prat_min=r["tempo_marcha_prat_min"])
    return out


def _bloco_campo(trilho, lastro, fixacao, insp) -> dict:
    out = {}
    if trilho is not None and not trilho.empty:
        cols = [c for c in JUNTAS_PROBLEMA if c in trilho.columns]
        j = trilho[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        out["juntas_problema"] = j.sum()
        out["juntas_problema_lp"] = j[trilho["linha"] == "LP"].sum()
        out["juntas_problema_ld"] = j[trilho["linha"] == "LD"].sum()
        if "situacao_desgaste" in trilho.columns:
            fora = trilho["situacao_desgaste"].astype(str).str.strip() == "Fora"
            out["trilho_fora_m"] = pd.to_numeric(trilho.loc[fora, "extensao_m"], errors="coerce").sum()
    if lastro is not None and not lastro.empty:
        out["bolsoes"] = (pd.to_numeric(lastro["bolsao_bombeando"], errors="coerce").sum()
                          + pd.to_numeric(lastro["bolsao_nao_bombeando"], errors="coerce").sum())
        out["lastro_cont_severa"] = pd.to_numeric(lastro["cont_severa"], errors="coerce").sum()
    if fixacao is not None and not fixacao.empty:
        out["fixacao_faltantes"] = pd.to_numeric(fixacao["total_faltantes"], errors="coerce").sum()
    if insp is not None and not insp.empty:
        out["inspecao_registros"] = len(insp)
    return out


def _bloco_transit(transit: pd.DataFrame, data_base: date) -> list[dict]:
    from core.parser_transit_time import resumo_mensal
    if transit is None or transit.empty:
        return []
    t = transit.copy()
    t["partida"] = pd.to_datetime(t["partida"])
    t = t[t["partida"] <= pd.Timestamp(data_base) + pd.Timedelta(days=1)]
    linhas = []
    mensal = resumo_mensal(t)
    for r in mensal.itertuples():
        linhas += _linhas("mes", f"{r.mes}|{r.sentido}",
                          {"trens": r.trens, "mediana": r.mediana, "p90": r.p90,
                           "programado": r.programado, "aderencia": r.aderencia * 100})
    # Janela: ano da base até a data da base (marco zero = jan–set/2026); sem
    # trens nesse ano (base no início do ano), os 12 meses anteriores.
    ano = t[t["partida"].dt.year == data_base.year]
    if not (ano["valido"].astype(bool)).any():
        ano = t[t["partida"] > pd.Timestamp(data_base) - pd.Timedelta(days=365)]
    v = ano[ano["valido"].astype(bool) & ~ano["outlier"].astype(bool)].copy()
    for sentido, g in v.groupby("sentido"):
        h = pd.to_numeric(g["horas"])
        prog = pd.to_numeric(g["horas_programadas"])
        linhas += _linhas("transit", sentido, {
            "trens": len(g), "mediana": h.median(), "p90": h.quantile(0.9),
            "programado": prog.median(), "aderencia": (h <= prog + 1).mean() * 100})
    return linhas


def calcular(dados: dict, data_base: date) -> pd.DataFrame:
    """
    dados: {'dormentes','defeitos','rel','transit','trilho','lastro','fixacao',
            'inspecao','pontos','sb_faixas'} — DataFrames (podem faltar).
    SB vazia (Rev 1) é completada pelo km (core/analise_trecho.sb_pelo_km).
    """
    g = dados.get
    dorm, defe, rel = g("dormentes"), g("defeitos"), g("rel")
    fx = g("sb_faixas")
    dorm = preencher_sb(dorm, "km_inicio", "km_fim", fx)
    linhas = []
    total = {}
    total.update(_bloco_dormentes(dorm))
    total.update(_bloco_defeitos(defe, rel))
    total.update(_bloco_velocidade(rel))
    total.update(_bloco_campo(g("trilho"), g("lastro"), g("fixacao"), g("inspecao")))
    linhas += _linhas("trecho", "TOTAL", total)
    linhas += _bloco_transit(g("transit"), data_base)

    if dorm is not None and not dorm.empty:
        ativos = _ativos(defe)
        if not ativos.empty:
            ativos = ativos.assign(sb_calc=sb_dos_defeitos(ativos, dorm, fx))
        rA = restricoes_trecho(rel) if rel is not None and not rel.empty else pd.DataFrame()
        for f in faixas_sb(dorm, fx).itertuples():
            s = dorm[dorm["sb"] == f.sb]
            ext = f.km_fim - f.km_ini
            n_def = int((ativos["sb_calc"] == f.sb).sum()) if not ativos.empty else 0
            r = rA[(rA["a"] < f.km_fim) & (rA["b"] > f.km_ini)] if not rA.empty else rA
            linhas += _linhas("sb", f.sb, {
                "km_ini": f.km_ini, "km_fim": f.km_fim,
                "dormentes_prospectados": s["total_prospectado"].sum(),
                "dormentes_inserviveis": s["qtd_inservivel"].sum(),
                "taxa_inserviveis_pct": s["qtd_inservivel"].sum() / s["total_prospectado"].sum() * 100
                if s["total_prospectado"].sum() else None,
                "defeitos_ativos": n_def, "defeitos_por_km": n_def / ext if ext else None,
                "restricoes_via": int((r["grupo"] == "Via").sum()) if len(r) else 0,
                "restricoes_antt": int((r["grupo"] == "ANTT").sum()) if len(r) else 0,
            })
        eq = defeitos_por_equipamento(ativos, dorm) if not ativos.empty else defeitos_por_equipamento(None, dorm)
        taxa = dorm.groupby("equipamento_siv").apply(
            lambda x: x["qtd_inservivel"].sum() / x["total_prospectado"].sum() * 100
            if x["total_prospectado"].sum() else np.nan)
        for e in eq.itertuples():
            linhas += _linhas("equipamento", e.equipamento_siv, {
                "taxa_inserviveis_pct": taxa.get(e.equipamento_siv), "defeitos_ativos": e.defeitos,
                "defeitos_por_km": e.def_por_km})

        pontos = g("pontos")
        if pontos is not None and not pontos.empty:
            for p in pontos.itertuples():
                s = dorm[(dorm["km_inicio"] < p.km_fim) & (dorm["km_fim"] > p.km_inicio)
                         & (dorm["linha"] == "LP")]
                ext = p.km_fim - p.km_inicio
                n_def = int(((ativos["km"] >= p.km_inicio) & (ativos["km"] <= p.km_fim)).sum()) \
                    if not ativos.empty else 0
                r = rA[(rA["a"] < p.km_fim) & (rA["b"] > p.km_inicio)] if not rA.empty else rA
                linhas += _linhas("ponto_critico", p.ponto, {
                    "taxa_inserviveis_pct": s["qtd_inservivel"].sum() / s["total_prospectado"].sum() * 100
                    if s["total_prospectado"].sum() else None,
                    "dormentes_inserviveis": s["qtd_inservivel"].sum(),
                    "defeitos_ativos": n_def, "defeitos_por_km": n_def / ext if ext else None,
                    "restricoes_a": len(r)})
    return pd.DataFrame(linhas)


def calcular_indicadores(base_id: int, trecho: str, data_base: date) -> int:
    """Carrega a base do banco, calcula e grava (upsert). Retorna nº de linhas."""
    from core.analise_velocidade import normalizar_relatorio
    from core.parser_prospeccao import enriquecer_prospeccao
    from database.queries_prospeccao import get_prospeccao, get_relatorio_velocidade
    from database.queries_trecho import (
        get_por_base, get_transit_time, get_referencia, salvar_indicadores,
    )
    from database.queries_prospeccao import TabelaAusente

    def _ler(f):
        try:
            return f()
        except TabelaAusente:
            return pd.DataFrame()
    dados = {
        "dormentes": _ler(lambda: get_prospeccao(trecho, base_id)),
        "rel": normalizar_relatorio(_ler(lambda: get_relatorio_velocidade(base_id))),
        "defeitos": _ler(lambda: get_por_base("defeitos_via", base_id)),
        "trilho": _ler(lambda: get_por_base("prospeccao_trilho", base_id)),
        "lastro": _ler(lambda: get_por_base("prospeccao_lastro", base_id)),
        "fixacao": _ler(lambda: get_por_base("prospeccao_fixacao", base_id)),
        "inspecao": _ler(lambda: get_por_base("inspecoes_campo", base_id)),
        "transit": _ler(get_transit_time),
        "pontos": _ler(lambda: get_referencia("trecho_pontos_criticos", trecho)),
        "sb_faixas": _ler(lambda: get_referencia("sb_faixas", trecho)),
    }
    if not dados["dormentes"].empty:
        dados["dormentes"] = enriquecer_prospeccao(dados["dormentes"])
    foto = calcular(dados, data_base)
    return salvar_indicadores(base_id, foto) if len(foto) else 0



# region ====================== Indicadores derivados (One Page) ================
# Ganho só faz sentido com 2 bases: com 1 base a One Page entra no modo
# "Ponto de partida" e estes valores não são mostrados.

def _total(foto: pd.DataFrame) -> pd.Series:
    if foto is None or foto.empty:
        return pd.Series(dtype=float)
    f = foto[(foto["escopo"] == "trecho") & (foto["chave"] == "TOTAL")]
    return pd.to_numeric(f.set_index("indicador")["valor"], errors="coerce")


def trens_por_mes(transit: pd.DataFrame | None, ate=None, meses: int = 3) -> float | None:
    """Média de trens válidos/mês (2 sentidos) nos `meses` últimos meses completos."""
    if transit is None or transit.empty:
        return None
    t = transit[transit["valido"].astype(bool)].copy()
    t["mes"] = pd.to_datetime(t["partida"]).dt.to_period("M")
    if ate is not None:
        t = t[t["mes"] <= pd.Period(pd.Timestamp(ate), "M")]
    por_mes = t.groupby("mes").size().sort_index()
    if por_mes.empty:
        return None
    return float(por_mes.tail(meses).mean())


def derivados(foto_a: pd.DataFrame, foto_b: pd.DataFrame, eventos: pd.DataFrame | None = None,
              transit: pd.DataFrame | None = None, defeitos_a: pd.DataFrame | None = None,
              defeitos_b: pd.DataFrame | None = None, avanco: dict | None = None,
              data_b=None) -> dict:
    """
    foto_a = marco zero (referência), foto_b = base atual. Valores positivos =
    ganho. Chaves ausentes quando falta dado.
    """
    from core.eventos_restricao import resumo_eventos
    a, b = _total(foto_a), _total(foto_b)
    out = {}
    if "tempo_marcha_prat_min" in a and "tempo_marcha_prat_min" in b:
        ganho = float(a["tempo_marcha_prat_min"] - b["tempo_marcha_prat_min"])
        out["minutos_ganhos"] = ganho
        tpm = trens_por_mes(transit, data_b)
        if tpm:
            out["trens_mes"] = tpm
            out["horas_mes"] = ganho * tpm / 60
    if "km_restrito_via" in a and "km_restrito_via" in b:
        out["km_liberados"] = float(a["km_restrito_via"] - b["km_restrito_via"])
    if "v_media_praticada" in a and "v_media_praticada" in b:
        out["delta_v_praticada"] = float(b["v_media_praticada"] - a["v_media_praticada"])
    if "taxa_inserviveis_pct" in a and "taxa_inserviveis_pct" in b:
        out["delta_taxa_pp"] = float(b["taxa_inserviveis_pct"] - a["taxa_inserviveis_pct"])
    if eventos is not None:
        out.update(resumo_eventos(eventos))
    if defeitos_a is not None and defeitos_b is not None and len(defeitos_a) and len(defeitos_b):
        ida = set(_ativos(defeitos_a)["defeito_id"].dropna().astype("int64"))
        idb = set(_ativos(defeitos_b)["defeito_id"].dropna().astype("int64"))
        out["defeitos_eliminados"] = len(ida - idb)
        out["defeitos_novos"] = len(idb - ida)
    if avanco:
        out["travamento_pct"] = avanco["pct"] * 100
        out["travamento_exec"] = avanco["executado"]
        out["pontos_concluidos"] = avanco["pontos_concluidos"]
        out["top20_concluidos"] = avanco["top20_concluidos"]
    return out

# endregion
