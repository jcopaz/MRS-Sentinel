"""
scripts/seed_trecho_itirapina.py — Gera o SQL das referências estáticas do
trecho Itirapina–Pederneiras a partir dos CSVs da base de conhecimento:

  marco_zero/seed_estacoes_itirapina_pederneiras.csv   → trecho_estacoes
  marco_zero/seed_limites_geometria_bitola_larga.csv   → limites_geometria (bitola 'Larga')
  dados/pontos_criticos_C_T.csv                        → trecho_pontos_criticos (C1–C3, T1–T4)
  dados/top10_curvas_tangentes.csv                     → trecho_pontos_criticos (Top 10)

Uso (depois de rodar database/schema_itirapina.sql):
    python scripts/seed_trecho_itirapina.py [pasta_base_conhecimento] > seed.sql
e colar o resultado no SQL Editor do Supabase. Idempotente (ON CONFLICT).
Sem argumento, usa ../Base_Conhecimento_Itirapina_Pederneiras ao lado do repo.
"""

import sys
from pathlib import Path

import pandas as pd

TRECHO = "Itirapina-Triagem"
PADRAO = Path(__file__).resolve().parents[2] / "Base_Conhecimento_Itirapina_Pederneiras"


def _csv(caminho: Path) -> pd.DataFrame:
    return pd.read_csv(caminho, sep=None, engine="python", encoding="utf-8-sig")


def _sql(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) else str(v)
    return "'" + str(v).replace("'", "''") + "'"


def gerar(pasta: Path) -> str:
    out = ["-- Gerado por scripts/seed_trecho_itirapina.py", "BEGIN;"]

    est = _csv(pasta / "marco_zero" / "seed_estacoes_itirapina_pederneiras.csv")
    for r in est.itertuples():
        out.append(
            "INSERT INTO itp_trecho_estacoes (trecho, codigo, nome, km_inicio, km_fim, ordem, observacao) "
            f"VALUES ({_sql(TRECHO)}, {_sql(r.codigo)}, {_sql(r.nome)}, {_sql(float(r.km_inicio))}, "
            f"{_sql(float(r.km_fim))}, {int(r.ordem)}, {_sql(r.observacao)}) "
            "ON CONFLICT (trecho, codigo) DO UPDATE SET nome=EXCLUDED.nome, km_inicio=EXCLUDED.km_inicio, "
            "km_fim=EXCLUDED.km_fim, ordem=EXCLUDED.ordem, observacao=EXCLUDED.observacao;")

    lim = _csv(pasta / "marco_zero" / "seed_limites_geometria_bitola_larga.csv")
    for r in lim.itertuples():
        out.append(
            "INSERT INTO itp_limites_geometria (bitola, classe, vel_min_kmh, vel_max_kmh, parametro, limite_mm) "
            f"VALUES ('Larga', {_sql(r.classe)}, {int(r.vel_min_kmh)}, {int(r.vel_max_kmh)}, "
            f"{_sql(r.parametro)}, {_sql(None if pd.isna(r.limite_mm) else float(r.limite_mm))}) "
            "ON CONFLICT (bitola, classe, parametro) DO UPDATE SET vel_min_kmh=EXCLUDED.vel_min_kmh, "
            "vel_max_kmh=EXCLUDED.vel_max_kmh, limite_mm=EXCLUDED.limite_mm;")

    pts = _csv(pasta / "dados" / "pontos_criticos_C_T.csv")
    linhas = [(r.ponto, "curva" if str(r.ponto).startswith("C") else "tangente", None, None,
               r.secao, r.km_ini, r.km_fim) for r in pts.itertuples()]
    top = _csv(pasta / "dados" / "top10_curvas_tangentes.csv")
    for r in top.itertuples():
        prefixo = "Top C" if r.tipo == "curva" else "Top T"
        linhas.append((f"{prefixo}{int(r.rank)}", f"top10_{r.tipo}", int(r.rank),
                       r.equipamento_SIV, r.secao, r.km_ini, r.km_fim))
    for ponto, tipo, rank, eq, secao, a, b in linhas:
        out.append(
            "INSERT INTO itp_trecho_pontos_criticos (trecho, ponto, tipo, rank, equipamento_siv, secao, "
            f"km_inicio, km_fim) VALUES ({_sql(TRECHO)}, {_sql(ponto)}, {_sql(tipo)}, "
            f"{_sql(rank)}, {_sql(eq)}, {_sql(secao)}, {_sql(float(a))}, {_sql(float(b))}) "
            "ON CONFLICT (trecho, ponto) DO UPDATE SET tipo=EXCLUDED.tipo, rank=EXCLUDED.rank, "
            "equipamento_siv=EXCLUDED.equipamento_siv, secao=EXCLUDED.secao, "
            "km_inicio=EXCLUDED.km_inicio, km_fim=EXCLUDED.km_fim;")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def carregar_referencias(pasta: Path) -> dict:
    """Mesmas referências como DataFrames (usado pelos testes e pela tela offline)."""
    est = _csv(pasta / "marco_zero" / "seed_estacoes_itirapina_pederneiras.csv")
    lim = _csv(pasta / "marco_zero" / "seed_limites_geometria_bitola_larga.csv").assign(bitola="Larga")
    pts = _csv(pasta / "dados" / "pontos_criticos_C_T.csv")
    pts = pd.DataFrame({"ponto": pts["ponto"], "tipo": pts["ponto"].str[0].map({"C": "curva", "T": "tangente"}),
                        "secao": pts["secao"], "km_inicio": pts["km_ini"], "km_fim": pts["km_fim"]})
    top = _csv(pasta / "dados" / "top10_curvas_tangentes.csv")
    top = pd.DataFrame({
        "ponto": [("Top C" if t == "curva" else "Top T") + str(int(r)) for t, r in zip(top["tipo"], top["rank"])],
        "tipo": "top10_" + top["tipo"], "rank": top["rank"], "equipamento_siv": top["equipamento_SIV"],
        "secao": top["secao"], "km_inicio": top["km_ini"], "km_fim": top["km_fim"]})
    return {"estacoes": est.assign(trecho=TRECHO), "limites": lim,
            "pontos": pd.concat([pts, top], ignore_index=True).assign(trecho=TRECHO)}


if __name__ == "__main__":
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else PADRAO
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(gerar(pasta))
