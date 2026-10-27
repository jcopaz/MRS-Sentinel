"""
tests/test_trecho_marco_zero.py — Testes de aceitação do Marco Zero
Itirapina–Pederneiras (seção 6.2 do PROMPT v3.1).

Os parsers rodam sobre os arquivos reais copiados para
tests/fixtures/itirapina/ (fora do git — dados operacionais). Sem a pasta,
os testes são pulados.

Diferenças documentadas em relação à tabela 6.2:
  - Defeitos: o export curto (Defeitos SUB 78) dá 6.359; o export de 60
    colunas do Vagão (26/10, 2 dias depois) dá 6.360 (+1 CARRO CONTROLE).
  - Transit time: os dois exports fornecidos dão 2.540 trens válidos
    (2.541 antes de remover 1 trem repetido). Os 2.543 do Marco Zero v2
    incluem 2 trens de 30/09–01/10 que não estão nesses arquivos.
  - Programado ZPD→ZIQ: 8,14 h (a tabela arredonda para 8,1).
"""

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
FIX = RAIZ / "tests" / "fixtures" / "itirapina"

pytestmark = pytest.mark.skipif(not FIX.exists(), reason="fixtures do trecho ausentes")


# region ── Fixtures (carregam cada arquivo uma vez) ─────────────────────────

@pytest.fixture(scope="session")
def rev1():
    from core.parser_prospeccao_campo import ler_prospeccao_campo
    abas, avisos = ler_prospeccao_campo(FIX / "Prospecção - Sub 78 Rev (1).xlsx")
    return abas


@pytest.fixture(scope="session")
def r1():
    from core.parser_prospeccao import ler_prospeccao
    df, _ = ler_prospeccao(FIX / "Prospecção Itirapina Engenharia.xlsx")
    return df


@pytest.fixture(scope="session")
def trilho_eng():
    from core.parser_prospeccao import ler_trilho_engenharia
    df, _ = ler_trilho_engenharia(FIX / "Prospecção Itirapina Engenharia.xlsx")
    return df


@pytest.fixture(scope="session")
def defeitos_curto():
    from core.parser_defeitos_via import ler_defeitos_via
    return ler_defeitos_via(FIX / "Defeitos SUB 78.xlsx")[0]


@pytest.fixture(scope="session")
def defeitos_vagao():
    from core.parser_defeitos_via import ler_defeitos_via
    return ler_defeitos_via(FIX / "Vgao Via-Defeitos Pederneiras 2610.xlsx")[0]


@pytest.fixture(scope="session")
def rel():
    from core.parser_relatorio_velocidade import ler_relatorio_velocidade
    from core.analise_velocidade import normalizar_relatorio
    rota, exp, df = ler_relatorio_velocidade(FIX / "JUNDIAI-TRIAGEM PAULISTA.pdf")
    return normalizar_relatorio(df.assign(rota=rota))


@pytest.fixture(scope="session")
def transit():
    from core.parser_transit_time import ler_transit_time
    a, _ = ler_transit_time(FIX / "TransitTime ZPD-ZIQ.xlsx")
    b, _ = ler_transit_time(FIX / "TransitTime ZIQ-ZPD.xlsx")
    return pd.concat([a, b], ignore_index=True)


@pytest.fixture(scope="session")
def inspecao():
    from core.parser_inspecao import ler_inspecao
    return ler_inspecao(FIX / "marco_zero" / "MarcoZero_Itirapina_Pederneiras_v2.xlsx",
                        FIX / "marco_zero" / "midias_manifest_marco_zero.csv")

# endregion


# region ── Prospecção ───────────────────────────────────────────────────────

def test_rev1_equipamentos_e_totais(rev1):
    d = rev1["dormentes"]
    assert len(d) == 228
    assert d["linha"].value_counts().to_dict() == {"LP": 201, "LD": 27}
    assert d["total_prospectado"].sum() == 227_921
    assert d["qtd_inservivel"].sum() == 58_939
    assert d["qtd_inservivel"].sum() / d["total_prospectado"].sum() * 100 == pytest.approx(25.9, abs=0.1)
    assert d["qtd_acidentado"].sum() == 3
    assert d["km_inicio"].min() == pytest.approx(174.839)  # metros → km


def test_rev1_abas_brutas(rev1):
    assert len(rev1["lastro"]) == 228
    assert len(rev1["fixacao"]) == 228
    assert len(rev1["trilho"]) == 456
    assert {"TR57", "TR68"} <= set(rev1["trilho"]["perfil_predominante"].dropna())


def test_r1_engenharia(r1):
    assert len(r1) == 227
    assert r1["total_prospectado"].sum() == 226_408
    assert r1["qtd_inservivel"].sum() == 58_420
    assert r1["qtd_inservivel"].sum() / r1["total_prospectado"].sum() * 100 == pytest.approx(25.8, abs=0.1)


def test_rev1_vs_r1(rev1, r1):
    from core.parser_prospeccao_campo import comparar_rev1_r1
    c = comparar_rev1_r1(rev1["dormentes"], r1)
    assert c["so_rev1"] == [("78/302922-303800cv", "LP")]
    assert c["dormentes_novos"] == 1_513
    assert "78/300818-302202tg" in c["linha_repetida"]


def test_ciclo_2025_historico():
    from core.parser_prospeccao import ler_prospeccao, separar_ciclos
    df, _ = ler_prospeccao(FIX / "Relatório de Prospecção (1).xlsx")
    ciclos = separar_ciclos(df, km_max=303.8)
    c25 = ciclos[2025]
    assert len(c25) == 220
    assert c25["total_prospectado"].sum() == 226_732
    assert c25["qtd_inservivel"].sum() == 72_824
    assert c25["qtd_inservivel"].sum() / c25["total_prospectado"].sum() * 100 == pytest.approx(32.1, abs=0.1)
    assert ciclos[2026]["qtd_inservivel"].sum() == 58_420


def test_trilho_juntas_e_desgaste(trilho_eng):
    from core.parser_prospeccao import JUNTAS_PROBLEMA
    j = trilho_eng.groupby("linha")[list(JUNTAS_PROBLEMA)].sum().sum(axis=1)
    assert j["LP"] == 424 and j["LD"] == 72
    fora = trilho_eng["situacao_desgaste"] == "Fora"
    assert trilho_eng.loc[fora, "extensao_m"].sum() == 10_098

# endregion


# region ── Defeitos e Vagão de Via ──────────────────────────────────────────

def test_defeitos_export_curto(defeitos_curto):
    d = defeitos_curto
    assert len(d) == 6_359
    assert len(d) / (303.8 - 174.8) == pytest.approx(49.3, abs=0.1)
    assert (d["vel_max_classe_kmh"] <= 40).sum() == 240
    assert (d["dias_ativo"] > 365).sum() == 1_089


def test_defeitos_export_vagao(defeitos_vagao):
    d = defeitos_vagao
    assert len(d) == 6_360          # +1 em relação ao export curto (ver docstring)
    assert d["defeito_id"].is_unique
    via = d[d["origem"] == "VIA"]
    assert len(via) == 495
    assert via["numero_viagem"].value_counts().to_dict() == {180: 429, 168: 66}
    assert set(d["linha"].dropna()) <= {"LP", "LD"}   # LPL normalizado


def test_vagao_set26_sem_restricao(defeitos_vagao, rel):
    from core.analise_trecho import vagao_sem_restricao
    v = vagao_sem_restricao(defeitos_vagao, rel, viagem=180, vel_max=35)
    assert len(v) == 88
    assert int(v["coberto"].sum()) == 36
    sem = v[~v["coberto"]]
    assert len(sem) == 52
    esperado = pd.read_csv(FIX / "marco_zero" / "vagao_via_set26_sem_restricao.csv",
                           sep=None, engine="python", encoding="utf-8-sig")
    comuns = set(sem["km"].round(3)) & set(esperado["KM"].round(3))
    assert len(comuns) >= 51

# endregion


# region ── Velocidade e restrições ──────────────────────────────────────────

def test_restricoes_via_e_antt(rel):
    from core.analise_trecho import restricoes_trecho
    r = restricoes_trecho(rel)
    assert len(r) == 30
    assert (r["grupo"] == "Via").sum() == 14
    assert (r["grupo"] == "ANTT").sum() == 16


def test_vma_tempo_de_marcha(rel):
    from core.analise_trecho import resumo_velocidade
    r = resumo_velocidade(rel)
    assert r["vma_media"] == pytest.approx(37.9, abs=0.1)
    assert r["tempo_marcha_vma_min"] == pytest.approx(208, abs=1)
    assert r["min_perdidos"] == pytest.approx(14, abs=0.5)

# endregion


# region ── Transit time ─────────────────────────────────────────────────────

@pytest.mark.parametrize("sentido,mediana,p90,prog", [
    ("ZPD→ZIQ", 9.8, 15.9, 8.1),
    ("ZIQ→ZPD", 10.9, 20.0, 7.4),
])
def test_transit_2026(transit, sentido, mediana, p90, prog):
    t = transit[transit["sentido"] == sentido]
    v = t[t["valido"] & (t["partida"].dt.year == 2026) & ~t["outlier"]]
    assert v["horas"].median() == pytest.approx(mediana, abs=0.1)
    assert v["horas"].quantile(0.9) == pytest.approx(p90, abs=0.1)
    assert t.loc[t["estado"] == "SUPRIMIDO", "horas"].median() == pytest.approx(prog, abs=0.1)


def test_transit_trens_validos(transit):
    v = transit[transit["valido"]]
    janela = v[(v["partida"] >= "2024-12-01") & (v["partida"] < "2026-10-01")]
    assert len(janela) == 2_540     # 2.543 no Marco Zero v2 (ver docstring)


def test_tmpcirc_fracao_de_dia():
    from core.parser_transit_time import ler_transit_time
    bruto = pd.read_excel(FIX / "TransitTime ZPD-ZIQ.xlsx", sheet_name="Dados", dtype=str).iloc[3]
    t, _ = ler_transit_time(FIX / "TransitTime ZPD-ZIQ.xlsx")
    linha = t[(t["trem"] == bruto["TREM"]) &
              (t["partida"] == pd.to_datetime(bruto["PARTIDA"], format="%d/%m/%Y %H:%M:%S"))].iloc[0]
    assert float(bruto["TMPCIRC"].replace(",", ".")) * 24 == pytest.approx(linha["horas"], abs=1e-6)

# endregion


# region ── Inspeção de campo ────────────────────────────────────────────────

def test_inspecao_e_midias(inspecao):
    insp, midias, avisos = inspecao
    assert len(insp) == 83
    sem_ref = [a for a in avisos if "sem registro" in a]
    assert len(sem_ref) == 1 and "67" in sem_ref[0]
    assert midias["arquivo"].nunique() + len(sem_ref) == 106


def test_link_midia():
    from core.parser_inspecao import montar_link
    assert montar_link("https://x/sites/A/", "marco_zero/Mídia (59).jpg") == \
        "https://x/sites/A/marco_zero/M%C3%ADdia%20%2859%29.jpg"
    assert montar_link("https://x", "a.jpg", "https://direto/a.jpg") == "https://direto/a.jpg"
    assert montar_link(None, "a.jpg") is None

# endregion


# region ── Indicadores e base congelada ─────────────────────────────────────

def test_indicadores_trecho(r1, defeitos_curto, rel, transit, trilho_eng, rev1, inspecao):
    from core.indicadores_trecho import calcular
    from core.parser_prospeccao import enriquecer_prospeccao
    sys.path.insert(0, str(RAIZ / "scripts"))
    from seed_trecho_itirapina import carregar_referencias
    refs = carregar_referencias(FIX)
    foto = calcular({
        "dormentes": enriquecer_prospeccao(r1), "defeitos": defeitos_curto, "rel": rel,
        "transit": transit, "trilho": trilho_eng, "lastro": rev1["lastro"],
        "fixacao": rev1["fixacao"], "inspecao": inspecao[0], "pontos": refs["pontos"],
    }, date(2026, 10, 26))
    tot = foto[foto["escopo"] == "trecho"].set_index("indicador")["valor"]
    assert tot["taxa_inserviveis_pct"] == pytest.approx(25.8, abs=0.1)
    assert tot["defeitos_ativos"] == 6_359
    assert tot["restricoes_via"] == 14 and tot["restricoes_antt"] == 16
    assert tot["juntas_problema_lp"] == 424 and tot["juntas_problema_ld"] == 72
    assert tot["trilho_fora_m"] == 10_098
    assert tot["inspecao_registros"] == 83
    tt = foto[(foto["escopo"] == "transit") & (foto["indicador"] == "mediana")].set_index("chave")["valor"]
    assert tt["ZPD→ZIQ"] == pytest.approx(9.8, abs=0.1)
    sb = foto[(foto["escopo"] == "sb") & (foto["indicador"] == "defeitos_por_km")].set_index("chave")["valor"]
    assert sb.idxmax() == "ZBO-ZEP"                      # concentração 145/km (seção 6.3)
    assert sb["ZBO-ZEP"] == pytest.approx(145, abs=5)
    assert {"C1", "T1", "Top C1"} <= set(foto.loc[foto["escopo"] == "ponto_critico", "chave"])


def test_tabelas_isoladas_com_prefixo(monkeypatch):
    """Toda leitura/escrita do trecho vai para tabelas itp_ (nunca as da malha MRS)."""
    import database.queries_prospeccao as qp
    import database.queries_trecho as qt
    usadas = []

    class Q:
        def __init__(self, nome):
            usadas.append(nome)
        def __getattr__(self, _):
            return lambda *a, **k: self
        def execute(self):
            return type("R", (), {"data": [{"id": 1, "congelada": False, "msg_n": 1, "data_base": "2026-10-26"}]})()

    falso = type("C", (), {"table": lambda self, n: Q(n)})()
    for mod in (qp, qt):
        monkeypatch.setattr(mod, "get_supabase", lambda: falso)
    qt.limpar_caches()
    qp.get_prospeccao.clear()
    qp.get_relatorio_velocidade.clear()
    qt.get_bases("Itirapina-Triagem")
    qt.get_por_base("defeitos_via", 1)
    qt.substituir_por_base("prospeccao_lastro", 1, pd.DataFrame({"x": [1]}))
    qt.substituir_inspecao(1, pd.DataFrame({"msg_n": [1]}), pd.DataFrame({"msg_n": [1], "arquivo": ["a"]}))
    qt.upsert_transit_time(pd.DataFrame({"trem": ["X"]}))
    qt.get_referencia("limites_geometria")
    qt.get_indicadores((1,))
    qp.get_prospeccao("Itirapina-Triagem", 1)
    qp.get_relatorio_velocidade(1)
    qp.substituir_prospeccao("Itirapina-Triagem", pd.DataFrame({"x": [1]}), None, 1)
    assert usadas and all(n.startswith("itp_") for n in usadas), sorted(set(usadas))


def test_base_congelada_bloqueia_escrita(monkeypatch):
    import database.queries_trecho as qt
    monkeypatch.setattr(qt, "base_congelada", lambda base_id: True)
    with pytest.raises(qt.BaseCongelada):
        qt.substituir_por_base("defeitos_via", 1, pd.DataFrame({"defeito_id": [1]}))
    with pytest.raises(qt.BaseCongelada):
        qt.salvar_indicadores(1, pd.DataFrame())


def test_inteiro_com_vazio_vai_como_int():
    """vel_max_classe_kmh com célula vazia vira float; o Postgres recusa "96.0" em SMALLINT."""
    from database.queries_trecho import _registros
    df = pd.DataFrame({"vel_max_classe_kmh": [96, None], "km": [174.5, 175.0]})
    r = _registros(df)
    assert r[0]["vel_max_classe_kmh"] == 96 and isinstance(r[0]["vel_max_classe_kmh"], int)
    assert r[1]["vel_max_classe_kmh"] is None
    assert r[0]["km"] == 174.5

# endregion
