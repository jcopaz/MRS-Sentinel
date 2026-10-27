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


# region ====================== Top N e pontos críticos (recalculáveis) =========

def top_n(plano: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """
    Top N curvas e Top N tangentes da LP por dormentes de travamento (desempate:
    taxa). Com n=10 reproduz dados/top10_curvas_tangentes.csv do estudo.
    """
    d = plano[(plano["linha"] == "LP") & plano["tipo"].isin(["curva", "tangente"])]
    out = []
    for tipo in ("curva", "tangente"):
        t = (d[d["tipo"] == tipo].sort_values(["dorm_travamento", "taxa_mz"], ascending=False)
             .head(n).copy())
        t["rank_calc"] = range(1, len(t) + 1)
        out.append(t)
    return pd.concat(out, ignore_index=True)


def pontos_criticos(plano: pd.DataFrame, janela_km: float = 3.0, n_curvas: int = 3,
                    n_tangentes: int = 4, metrica: str = "inserviveis_mz") -> pd.DataFrame:
    """
    Janela de `janela_km` (equipamentos da LP do mesmo tipo que COMEÇAM dentro
    dela) com a maior soma de inservíveis, sem reaproveitar equipamento; curvas
    e tangentes separadas. Sugestão do algoritmo: reproduz C1, T1 e T2 do
    estudo. Os demais pontos do estudo tiveram escolha manual (ex.: a janela
    do km 251,5 tem mais inservíveis que C3 e ficou de fora) — por isso a tela
    mostra os pontos oficiais por padrão e esta função só no "Recalcular".
    """
    linhas = []
    for tipo, n, prefixo in (("curva", n_curvas, "C"), ("tangente", n_tangentes, "T")):
        d = (plano[(plano["linha"] == "LP") & (plano["tipo"] == tipo)]
             .sort_values("km_inicio").reset_index(drop=True))
        usados = np.zeros(len(d), bool)
        for k in range(1, n + 1):
            melhor = None
            for a in d["km_inicio"]:
                m = ((d["km_inicio"] >= a - 1e-9) & (d["km_inicio"] <= a + janela_km + 1e-9)).values
                if (m & usados).any():
                    continue
                s = d.loc[m, metrica].sum()
                if melhor is None or s > melhor[0]:
                    melhor = (s, m)
            if melhor is None:
                break
            s, m = melhor
            usados |= m
            g = d[m]
            linhas.append({"ponto": f"{prefixo}{k}", "tipo": tipo, "km_inicio": g["km_inicio"].min(),
                           "km_fim": g["km_fim"].max(), "n_equip": len(g), "inserviveis": int(s),
                           "travamento": int(g["dorm_travamento"].sum()),
                           "equipamentos": ", ".join(g["equipamento_siv"])})
    return pd.DataFrame(linhas)

# endregion


# region ====================== Quadro por equipamento (tela 🎯 Travamento) =====

def quadro_equipamentos(plano: pd.DataFrame, dorm: pd.DataFrame | None = None,
                        defeitos: pd.DataFrame | None = None, rA: pd.DataFrame | None = None,
                        execucao: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    1 linha por (equipamento, linha) do plano com a situação atual: taxa e
    inservíveis da base (prospecção), malhas ≥ 3, defeitos ativos/km,
    restrições A sobrepostas (via/ANTT), executado e % do travamento.
    """
    q = plano.copy()
    q["ext_km"] = (q["km_fim"] - q["km_inicio"]).abs()
    q["taxa_mz_pct"] = q["taxa_mz"] * 100
    if dorm is not None and not dorm.empty:
        malhas = [c for c in (f"malha_{i}" for i in range(3, 11)) if c in dorm.columns]
        g = dorm.assign(_m3=dorm[malhas].apply(pd.to_numeric, errors="coerce").sum(axis=1) if malhas else 0)
        g = g.groupby(["equipamento_siv", "linha"]).agg(
            inserv_atual=("qtd_inservivel", "sum"), prosp_atual=("total_prospectado", "sum"),
            malhas_3=("_m3", "sum"))
        q = q.join(g, on=["equipamento_siv", "linha"])
        q["taxa_pct"] = q["inserv_atual"] / q["prosp_atual"].replace(0, np.nan) * 100
    else:
        q["inserv_atual"], q["taxa_pct"], q["malhas_3"] = q["inserviveis_mz"], q["taxa_mz_pct"], np.nan
    q["taxa_pct"] = q["taxa_pct"].fillna(q["taxa_mz_pct"])
    if defeitos is not None and not defeitos.empty:
        n = defeitos.groupby("equipamento_siv").size()
        q["defeitos"] = q["equipamento_siv"].map(n).fillna(0)
        # equipamento com LP e LD: defeitos ficam na LP (mesma regra de mapa_equipamentos)
        q.loc[q.duplicated("equipamento_siv") & (q["linha"] != "LP"), "defeitos"] = 0
    else:
        q["defeitos"] = 0
    q["def_por_km"] = q["defeitos"] / q["ext_km"].replace(0, np.nan)
    q["restr_via"], q["restr_antt"], q["restricoes"] = 0, 0, ""
    if rA is not None and not rA.empty:
        for i, r in q.iterrows():
            s = rA[(rA["a"] < r["km_fim"]) & (rA["b"] > r["km_inicio"])]
            if len(s):
                q.at[i, "restr_via"] = int((s["grupo"] == "Via").sum())
                q.at[i, "restr_antt"] = int((s["grupo"] == "ANTT").sum())
                q.at[i, "restricoes"] = " · ".join(f"{v:.0f} km/h {m}" for v, m in zip(s["vel"], s["motivo"]))
    av = avanco_travamento(plano, execucao)["equip"][["equipamento_siv", "linha", "executado_lim", "pct"]]
    q = q.merge(av, on=["equipamento_siv", "linha"], how="left")
    q["executado"] = q["executado_lim"].fillna(0)
    q["pct_exec"] = q["pct"].fillna(0) * 100
    q["dias_equipe"] = np.ceil((q["dorm_travamento"] - q["executado"]).clip(lower=0) / DORM_POR_DIA)
    return q.drop(columns=["executado_lim", "pct"])

# endregion
