"""Monta os insumos da One Page a partir das fixtures (usado pelos testes da F5/F6)."""
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "tests" / "fixtures" / "itirapina"


def insumos(evolucao: bool) -> dict:
    sys.path.insert(0, str(RAIZ / "scripts"))
    from seed_trecho_itirapina import carregar_referencias
    from core.parser_prospeccao import ler_prospeccao, enriquecer_prospeccao
    from core.parser_defeitos_via import ler_defeitos_via
    from core.parser_relatorio_velocidade import ler_relatorio_velocidade
    from core.parser_transit_time import ler_transit_time
    from core.analise_velocidade import normalizar_relatorio
    from core.indicadores_trecho import calcular
    from core.plano_itirapina import ler_plano_engenharia
    from core.analise_trecho import TRECHO_KM, GRUPO_ANTT

    csv = lambda n: pd.read_csv(FIX / "dados" / n, sep=";", encoding="utf-8-sig")  # noqa: E731
    plano, _ = ler_plano_engenharia(FIX / "Prospecção Itirapina Engenharia.xlsx",
                                    csv("pontos_criticos_C_T.csv"), csv("top10_curvas_tangentes.csv"))
    dorm = enriquecer_prospeccao(ler_prospeccao(FIX / "Prospecção Itirapina Engenharia.xlsx")[0])
    defe = ler_defeitos_via(FIX / "Vgao Via-Defeitos Pederneiras 2610.xlsx")[0]
    rota, _, df = ler_relatorio_velocidade(FIX / "JUNDIAI-TRIAGEM PAULISTA.pdf")
    rel = normalizar_relatorio(df.assign(rota=rota))
    t = pd.concat([ler_transit_time(FIX / f"TransitTime {s}.xlsx")[0] for s in ("ZPD-ZIQ", "ZIQ-ZPD")])
    refs = carregar_referencias(FIX)
    mz = date(2026, 10, 26)
    foto_mz = calcular({"dormentes": dorm, "defeitos": defe, "rel": rel, "transit": t}, mz)
    kw = dict(data_mz=mz, data_atual=mz, foto_mz=foto_mz, rel_mz=rel, dorm_mz=dorm, defeitos_mz=defe,
              transit=t, plano=plano, estacoes=refs["estacoes"], pontos=refs["pontos"],
              metas=pd.DataFrame([{"indicador": "restricoes_via", "valor_meta": 0, "prazo": "2027-12-31"},
                                  {"indicador": "vma_media", "valor_meta": 40, "prazo": "2027-12-31"}]),
              gerado_em=datetime(2026, 10, 27, 10, 0))
    if not evolucao:
        return kw
    # 2ª base fictícia: 2 restrições de via retiradas, 1 velocidade +5, 300 dormentes trocados no T1,
    # 10% dos inservíveis recuperados
    r = rel.copy()
    m = ((r["tipo"] == "restricao_a") & (r["sub"] == "78") & (r["categoria"] != GRUPO_ANTT)
         & (r["linha"] == "LP") & (r[["km_de", "km_ate"]].min(axis=1) <= TRECHO_KM[1]))
    idx = r[m].sort_values("km_de").index
    r = r.drop(index=idx[:2])
    r.loc[idx[2], "vel"] += 5
    d2 = dorm.copy()
    d2["qtd_inservivel"] = (d2["qtd_inservivel"] * 0.9).round()
    d2 = enriquecer_prospeccao(d2)
    b = date(2027, 3, 31)
    defe2 = defe.iloc[200:]
    foto_b = calcular({"dormentes": d2, "defeitos": defe2, "rel": r, "transit": t}, b)
    t1 = plano[(plano["ponto_critico"] == "T1")].iloc[0]
    exe = pd.DataFrame([{"data": "2027-02-10", "atividade": "troca_dormente", "km_inicio": t1.km_inicio + 0.1,
                         "km_fim": None, "linha": "LP", "equipamento_siv": None, "quantidade": 300,
                         "unidade": "dorm"},
                        {"data": "2027-02-11", "atividade": "solda", "km_inicio": 285.2, "km_fim": None,
                         "linha": "LP", "equipamento_siv": None, "quantidade": 12, "unidade": "und"}])
    kw.update(data_atual=b, foto_atual=foto_b, rel_atual=r, dorm_atual=d2, defeitos_atual=defe2, execucao=exe)
    return kw
