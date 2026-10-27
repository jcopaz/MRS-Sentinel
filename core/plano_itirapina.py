# =============================================================================
# core/plano_itirapina.py — Plano de travamento do trecho e avanço da execução
#
# Funções puras (sem Streamlit/banco):
#   - ler_plano_engenharia: aba Dormente da "Prospecção Itirapina Engenharia"
#     → 1 linha por (equipamento_siv, linha) com os cenários (negativo → 0),
#     ponto crítico C/T e rank do Top 10. Totais de conferência: travamento
#     4.645 · Top 20 = 1.643 dormentes em 22,3 km. A meta 20% "oficial"
#     (16.580) é a do Resumo (inclui 982 encobertos + 1.188 TR45), não a
#     soma por equipamento (18.827) — por isso fica em TOTAIS_RESUMO.
#   - equipamento_pelo_km / avanco_travamento: cruzam itp_execucao com o plano.
#     Equipamento executado conta no máximo o travamento dele; ponto C/T ou
#     local do Top 20 é "concluído" com ≥ 90% do travamento executado.
# =============================================================================

import numpy as np
import pandas as pd

from core.parser_prospeccao import _norm

TOTAIS_RESUMO = {"travamento": 4645, "meta20": 16580, "meta16": 25636}
CONCLUIDO = 0.90
DORM_POR_DIA = 70     # produtividade da equipe (lição nº 1)

# cabeçalho normalizado (prefixo) → coluna
_COLUNAS = (
    ("equipamento siv", "equipamento_siv"),
    ("linha", "linha"),
    ("km inicio", "km_inicio"),
    ("km fim", "km_fim"),
    ("raio", "raio"),
    ("sb", "sb"),
    ("qtd inservivel", "inserviveis_mz"),
    ("total de dormentes prospectado", "prospectados_mz"),
    ("cenario travamento", "dorm_travamento"),
    ("2o cenario dorm. nec. 20", "dorm_meta20"),
    ("2 cenario dorm. nec. 20", "dorm_meta20"),
    ("3o cenario dorm. nec. 16", "dorm_meta16"),
    ("3 cenario dorm. nec. 16", "dorm_meta16"),
)


def _mapear(colunas) -> dict:
    out = {}
    for c in colunas:
        n = _norm(c).replace("º", "o")
        for prefixo, destino in _COLUNAS:
            if destino not in out.values() and (n == prefixo or (len(prefixo) > 6 and n.startswith(prefixo))):
                out[c] = destino
                break
    return out


def tipo_equipamento(eq) -> str | None:
    s = str(eq or "").strip().lower()
    return "curva" if s.endswith("cv") else "tangente" if s.endswith("tg") else None


def ler_plano_engenharia(arquivo, pontos: pd.DataFrame | None = None,
                         top10: pd.DataFrame | None = None, aba: str = "Dormente"
                         ) -> tuple[pd.DataFrame, list[str]]:
    """
    pontos: DataFrame com ponto, km_inicio/km_ini, km_fim (C1..T4).
    top10:  DataFrame com tipo, rank, equipamento_SIV/equipamento_siv.
    """
    avisos: list[str] = []
    bruto = pd.read_excel(arquivo, sheet_name=aba)
    mapa = _mapear(bruto.columns)
    faltam = {"equipamento_siv", "linha", "km_inicio", "km_fim", "dorm_travamento"} - set(mapa.values())
    if faltam:
        return pd.DataFrame(), [f"Colunas não encontradas na aba {aba}: {', '.join(sorted(faltam))}"]
    d = bruto[list(mapa)].rename(columns=mapa)
    d = d[d["equipamento_siv"].notna() & d["km_inicio"].notna()].copy()
    d["equipamento_siv"] = d["equipamento_siv"].astype(str).str.strip()
    d["linha"] = d["linha"].astype(str).str.strip().str.upper().replace({"LPL": "LP"})
    for c in ("km_inicio", "km_fim", "raio", "inserviveis_mz", "prospectados_mz",
              "dorm_travamento", "dorm_meta20", "dorm_meta16"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("dorm_travamento", "dorm_meta20", "dorm_meta16"):
        if c in d.columns:
            d[c] = d[c].clip(lower=0).fillna(0).round().astype(int)
    dup = d.duplicated(["equipamento_siv", "linha"])
    if dup.any():
        # ex.: 78/300818-302202tg aparece 2× na LP (158 + 14 de travamento) — soma
        avisos.append(f"{int(dup.sum())} equipamento(s) repetido(s) na mesma linha — quantidades somadas.")
        soma = [c for c in ("inserviveis_mz", "prospectados_mz", "dorm_travamento", "dorm_meta20",
                            "dorm_meta16") if c in d.columns]
        resto = {c: "first" for c in d.columns if c not in soma + ["equipamento_siv", "linha"]}
        d = d.groupby(["equipamento_siv", "linha"], as_index=False, sort=False).agg(
            {**resto, **{c: "sum" for c in soma}})
    d["tipo"] = d["equipamento_siv"].map(tipo_equipamento)
    if "prospectados_mz" in d.columns:
        d["taxa_mz"] = (d["inserviveis_mz"] / d["prospectados_mz"].replace(0, np.nan)).round(4)
        d = d.drop(columns="prospectados_mz")
    if "inserviveis_mz" in d.columns:
        d["inserviveis_mz"] = d["inserviveis_mz"].fillna(0).round().astype(int)
    d["ponto_critico"] = marcar_pontos(d, pontos)
    d["rank_top10"] = marcar_top10(d, top10)
    return d.reset_index(drop=True), avisos


def marcar_pontos(plano: pd.DataFrame, pontos: pd.DataFrame | None) -> pd.Series:
    """Equipamento da LP cujo meio cai no ponto C (curvas) / T (tangentes) — como no estudo."""
    out = pd.Series([None] * len(plano), index=plano.index, dtype=object)
    if pontos is None or len(pontos) == 0:
        return out
    p = pontos.rename(columns={"km_ini": "km_inicio"})
    p = p[p["ponto"].astype(str).str.match(r"^[CT]\d+$")]
    meio = (plano["km_inicio"] + plano["km_fim"]) / 2
    for r in p.itertuples():
        tipo = "curva" if str(r.ponto).startswith("C") else "tangente"
        m = (meio >= r.km_inicio) & (meio <= r.km_fim) & (plano["tipo"] == tipo) & (plano["linha"] == "LP")
        out[m] = r.ponto
    return out


def marcar_top10(plano: pd.DataFrame, top10: pd.DataFrame | None) -> pd.Series:
    out = pd.Series([pd.NA] * len(plano), index=plano.index, dtype="Int64")
    if top10 is None or len(top10) == 0:
        return out
    col = "equipamento_SIV" if "equipamento_SIV" in top10.columns else "equipamento_siv"
    rank = dict(zip(top10[col].astype(str).str.strip(), top10["rank"].astype(int)))
    # LP preferida: só a 1ª ocorrência do equipamento recebe o rank
    ordem = plano.assign(_o=(plano["linha"] != "LP").astype(int)).sort_values("_o")
    vistos = set()
    for i, eq in zip(ordem.index, ordem["equipamento_siv"]):
        if eq in rank and eq not in vistos:
            out[i] = rank[eq]
            vistos.add(eq)
    return out


def resumo_plano(plano: pd.DataFrame) -> dict:
    top = plano[plano["rank_top10"].notna()]
    return {
        "travamento": int(plano["dorm_travamento"].sum()),
        "top20_travamento": int(top["dorm_travamento"].sum()),
        "top20_km": float((top["km_fim"] - top["km_inicio"]).abs().sum()),
        "top20_locais": len(top),
        "pontos": sorted(plano["ponto_critico"].dropna().unique()),
    }

# region ====================== Execução × plano ================================

def equipamento_pelo_km(km, linha: str, plano: pd.DataFrame) -> str | None:
    if plano is None or plano.empty or km is None or pd.isna(km):
        return None
    m = plano[(plano["linha"] == (linha or "LP")) & (plano["km_inicio"] <= km) & (plano["km_fim"] >= km)]
    if m.empty:
        m = plano[(plano["km_inicio"] <= km) & (plano["km_fim"] >= km)]
    return m.iloc[0]["equipamento_siv"] if len(m) else None


def completar_equipamento(execucao: pd.DataFrame, plano: pd.DataFrame) -> pd.DataFrame:
    if execucao is None or execucao.empty:
        return execucao
    e = execucao.copy()
    if "equipamento_siv" not in e.columns:
        e["equipamento_siv"] = None
    vazio = e["equipamento_siv"].isna() | (e["equipamento_siv"].astype(str).str.strip() == "")
    e.loc[vazio, "equipamento_siv"] = [
        equipamento_pelo_km(k, l, plano) for k, l in zip(e.loc[vazio, "km_inicio"], e.loc[vazio, "linha"])]
    return e


def avanco_travamento(plano: pd.DataFrame, execucao: pd.DataFrame | None) -> dict:
    """
    Avanço por equipamento, ponto C/T e Top 20. Só troca de dormente conta.
    Retorna {'equip': df, 'pontos': df, 'pct': float, 'executado': int,
             'pontos_concluidos': int, 'top20_concluidos': int}.
    """
    eq = plano[plano["dorm_travamento"] > 0].copy()
    exe = pd.Series(dtype=float)
    if execucao is not None and not execucao.empty:
        e = completar_equipamento(execucao, plano)
        e = e[e["atividade"] == "troca_dormente"]
        if len(e):
            e = e.assign(linha=e["linha"].fillna("LP"))
            exe = e.groupby(["equipamento_siv", "linha"])["quantidade"].sum()
    chave = list(zip(eq["equipamento_siv"], eq["linha"]))
    eq["executado"] = [float(exe.get(k, 0.0)) for k in chave]
    eq["executado_lim"] = np.minimum(eq["executado"], eq["dorm_travamento"])
    eq["pct"] = eq["executado_lim"] / eq["dorm_travamento"]
    eq["dias_equipe"] = np.ceil((eq["dorm_travamento"] - eq["executado_lim"]) / DORM_POR_DIA)

    pts = (eq[eq["ponto_critico"].notna()]
           .groupby("ponto_critico")
           .agg(km_inicio=("km_inicio", "min"), km_fim=("km_fim", "max"),
                travamento=("dorm_travamento", "sum"), executado=("executado_lim", "sum"))
           .reset_index())
    pts["pct"] = pts["executado"] / pts["travamento"].replace(0, np.nan)
    pts["situacao"] = np.select([pts["pct"] >= CONCLUIDO, pts["pct"] > 0],
                                ["concluído", "em curso"], "a iniciar")
    top = eq[eq["rank_top10"].notna()]
    total = eq["dorm_travamento"].sum()
    return {
        "equip": eq, "pontos": pts,
        "executado": int(eq["executado_lim"].sum()),
        "travamento": int(total),
        "pct": float(eq["executado_lim"].sum() / total) if total else 0.0,
        "pontos_concluidos": int((pts["pct"] >= CONCLUIDO).sum()),
        "top20_concluidos": int((top["pct"] >= CONCLUIDO).sum()),
    }

# endregion
