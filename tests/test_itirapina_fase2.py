"""
tests/test_itirapina_fase2.py — Testes de aceitação da Fase 2 do trecho
Itirapina–Pederneiras (PROMPT_VSCode_Sentinel_Itirapina_OnePage_v1, seção 9).

Fixtures reais em tests/fixtures/itirapina/ (fora do git); sem a pasta, os
testes que dependem delas são pulados.

Diferença documentada:
  - Top 20 do plano = 1.657 dormentes (e não 1.643): 78/300818-302202tg
    aparece 2× na LP da Engenharia (158 + 14); o estudo rankeou só a 1ª
    linha. O travamento total (4.645) só fecha somando as duas.
  - Vagão: 153 corretivos · 1.680 perímetro urbano · 869 com lat/long são da
    planilha inteira (Sub 78 toda); no trecho são 105 · 1.557 · 664.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
FIX = RAIZ / "tests" / "fixtures" / "itirapina"
com_fixtures = pytest.mark.skipif(not FIX.exists(), reason="fixtures do trecho ausentes")


def _csv(nome):
    return pd.read_csv(FIX / "dados" / nome, sep=";", encoding="utf-8-sig")


@pytest.fixture(scope="module")
def rel():
    from core.parser_relatorio_velocidade import ler_relatorio_velocidade
    from core.analise_velocidade import normalizar_relatorio
    rota, exp, df = ler_relatorio_velocidade(FIX / "JUNDIAI-TRIAGEM PAULISTA.pdf")
    return normalizar_relatorio(df.assign(rota=rota))


@pytest.fixture(scope="module")
def defeitos_vagao():
    from core.parser_defeitos_via import ler_defeitos_via
    return ler_defeitos_via(FIX / "Vgao Via-Defeitos Pederneiras 2610.xlsx")[0]


@pytest.fixture(scope="module")
def plano():
    from core.plano_itirapina import ler_plano_engenharia
    p, _ = ler_plano_engenharia(FIX / "Prospecção Itirapina Engenharia.xlsx",
                                _csv("pontos_criticos_C_T.csv"), _csv("top10_curvas_tangentes.csv"))
    return p


# region ── F0 ───────────────────────────────────────────────────────────────

def test_sb_pelo_km():
    from core.analise_trecho import sb_pelo_km, SB_FAIXAS
    assert sb_pelo_km(206.0) == "ZWF-ZBO"
    assert sb_pelo_km(290.0) == "ZWM-ZWY"
    assert sb_pelo_km(300.0) == "ZWY-ZPD"
    assert sb_pelo_km(303.0) == "ZPD-ZFJ"
    assert sb_pelo_km(303.8) == "ZPD-ZFJ"
    assert sb_pelo_km(174.8) == "ZIQ-ZQY"
    assert sb_pelo_km(150.0) is None and sb_pelo_km(None) is None
    assert len(SB_FAIXAS) == 16


def test_preencher_sb_so_onde_vazia():
    from core.analise_trecho import preencher_sb
    d = pd.DataFrame({"km_inicio": [206.0, 300.0, 290.0], "km_fim": [206.2, 300.4, 290.1],
                      "sb": [None, "None", "XPTO"]})
    f = preencher_sb(d, "km_inicio", "km_fim")
    assert f["sb"].tolist() == ["ZWF-ZBO", "ZWY-ZPD", "XPTO"]


@com_fixtures
def test_matriz_sb_16_com_rev1_sem_sb():
    """Rev 1 não tem SB: os indicadores por SB vêm pelo km → 16 SBs."""
    from core.parser_prospeccao_campo import ler_prospeccao_campo
    from core.parser_prospeccao import enriquecer_prospeccao
    from core.indicadores_trecho import calcular
    abas, _ = ler_prospeccao_campo(FIX / "Prospecção - Sub 78 Rev (1).xlsx")
    dorm = enriquecer_prospeccao(abas["dormentes"])
    foto = calcular({"dormentes": dorm}, date(2026, 10, 26))
    sb = foto[(foto["escopo"] == "sb") & (foto["indicador"] == "dormentes_prospectados")]
    assert sb["chave"].nunique() == 16
    assert (sb["valor"] > 0).sum() == 16


@com_fixtures
def test_restricoes_unica_fonte(rel):
    from core.analise_trecho import restricoes_trecho, rotulo_restricoes
    rA = restricoes_trecho(rel)
    assert rotulo_restricoes(rA) == "30 (14 via · 16 ANTT)"


@com_fixtures
def test_vagao_recarregado(defeitos_vagao, rel):
    from core.analise_trecho import vagao_sem_restricao
    v = vagao_sem_restricao(defeitos_vagao, rel, viagem=180)
    assert int((~v["coberto"]).sum()) == 52
    # O prompt cita 153 corretivos · 1.680 PU · 869 lat/long: são da planilha
    # inteira (7.928 linhas, Sub 78 toda). No trecho (km ≤ 303,8, 6.360):
    assert int(defeitos_vagao[["latitude", "longitude"]].notna().all(axis=1).sum()) == 664
    assert int((defeitos_vagao["classificacao"] == "Corretivo").sum()) == 105
    assert int((defeitos_vagao["classificacao"] == "Crítico").sum()) == 2
    assert int((defeitos_vagao["perimetro_urbano"] == True).sum()) == 1557  # noqa: E712
    assert int((defeitos_vagao["acidente"] == True).sum()) == 151  # noqa: E712

# endregion


# region ── F1 ───────────────────────────────────────────────────────────────

@com_fixtures
def test_plano_totais(plano):
    from core.plano_itirapina import resumo_plano
    r = resumo_plano(plano)
    assert r["travamento"] == 4645
    assert r["top20_locais"] == 20
    assert r["top20_travamento"] == 1643 + 14      # ver docstring
    assert abs(r["top20_km"] - 22.3) < 0.06
    assert r["pontos"] == ["C1", "C2", "C3", "T1", "T2", "T3", "T4"]
    pts = _csv("pontos_criticos_C_T.csv").set_index("ponto")["travamento"].to_dict()
    assert plano.groupby("ponto_critico")["dorm_travamento"].sum().to_dict() == pts


@com_fixtures
def test_execucao_sobe_avanco_t1(plano):
    from core.plano_itirapina import avanco_travamento
    antes = avanco_travamento(plano, None)
    t1 = plano[(plano["ponto_critico"] == "T1") & (plano["dorm_travamento"] > 0)].iloc[0]
    exe = pd.DataFrame([{"data": "2027-01-10", "atividade": "troca_dormente",
                         "km_inicio": (t1.km_inicio + t1.km_fim) / 2, "linha": "LP",
                         "equipamento_siv": None, "quantidade": 100, "unidade": "dorm"}])
    depois = avanco_travamento(plano, exe)
    assert antes["executado"] == 0 and depois["executado"] == min(100, int(t1.dorm_travamento))
    assert depois["pct"] > antes["pct"]
    p = depois["pontos"].set_index("ponto_critico")
    assert p.loc["T1", "pct"] > 0 and p.loc["T1", "situacao"] in ("em curso", "concluído")

# endregion
