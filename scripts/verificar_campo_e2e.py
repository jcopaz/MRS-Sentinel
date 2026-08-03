#!/usr/bin/env python3
# scripts/verificar_campo_e2e.py — Sprint 9 (Mobile First / Visão de Campo)
#
# Teste headless dos helpers PUROS de modules/visao_campo.py (ordenação das
# prioridades, dias em aberto, KPIs) sem Streamlit/Supabase.
#
# Uso:  PYTHONPATH=<raiz_do_app> python3 scripts/verificar_campo_e2e.py

import sys
import types
from contextlib import contextmanager


def _stub(nome, **attrs):
    m = types.ModuleType(nome)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[nome] = m
    return m


def _instalar_stubs():
    st = types.ModuleType("streamlit")

    def _noop(*a, **k):
        return None

    @contextmanager
    def _ctx(*a, **k):
        yield

    for nome in ("markdown", "caption", "info", "warning", "radio", "slider",
                 "dataframe"):
        setattr(st, nome, _noop)
    st.columns = lambda n, *a, **k: [_ctx() for _ in range(n if isinstance(n, int) else len(n))]
    st.spinner = _ctx
    st.session_state = {}
    sys.modules["streamlit"] = st

    _stub("auth", )
    _stub("auth.session", get_gerencia=lambda: "SP", get_perfil=lambda: "assistente")
    _stub("auth.permissions", can_see_gerencia=lambda g: True)


def main() -> int:
    print("=" * 64)
    print("MRS Sentinel — E2E Sprint 9 (Visão de Campo) — headless")
    print("=" * 64)
    _instalar_stubs()

    import pandas as pd
    import modules.visao_campo as vc

    falhas = []
    hoje = pd.Timestamp("2026-08-03")

    # Fixture: 5 notas (3 abertas, 2 encerradas) --------------------------------
    linhas = [
        {"ramal": "ACL", "trecho": "IPA-IPG", "km_real": 303.0,
         "prioridade": "1-Muito alta", "status_usuario": "ABER",
         "data_nota": hoje - pd.Timedelta(days=30), "score": 0.90,
         "familia_defeito": "Trilho"},
        {"ramal": "VBA", "trecho": "VBA-RGI", "km_real": 120.0,
         "prioridade": "2-Alta", "status_usuario": "ABER",
         "data_nota": hoje - pd.Timedelta(days=10), "score": 0.70,
         "familia_defeito": "AMV"},
        {"ramal": "ACL", "trecho": "IPA-IPG", "km_real": 305.0,
         "prioridade": "4-Baixa", "status_usuario": "ABER",
         "data_nota": hoje - pd.Timedelta(days=5), "score": 0.30,
         "familia_defeito": "Solda"},
        {"ramal": "VBA", "trecho": "VBA-RGI", "km_real": 121.0,
         "prioridade": "1-Muito alta", "status_usuario": "ENCE",
         "data_nota": hoje - pd.Timedelta(days=60), "score": 0.95,
         "familia_defeito": "Trilho"},
        {"ramal": "ACL", "trecho": "IPA-IPG", "km_real": 306.0,
         "prioridade": "3-Média", "status_usuario": "CONC",
         "data_nota": hoje - pd.Timedelta(days=40), "score": 0.50,
         "familia_defeito": "Solda"},
    ]
    df = pd.DataFrame(linhas)

    # [1] _is_aberta -----------------------------------------------------------
    n_ab = int(vc._is_aberta(df["status_usuario"]).sum())
    print(f"[1] abertas detectadas: {n_ab} (esperado 3)")
    if n_ab != 3:
        falhas.append(f"esperava 3 abertas, obtido {n_ab}")

    # [2] _dias_aberta ---------------------------------------------------------
    d = vc._dias_aberta(hoje - pd.Timedelta(days=30), hoje=hoje)
    print(f"[2] dias em aberto (nota de 30d): {d}")
    if d != 30:
        falhas.append(f"dias_aberta esperado 30, obtido {d}")
    if vc._dias_aberta(None) != 0:
        falhas.append("dias_aberta(None) deveria ser 0")

    # [3] _kpis_campo ----------------------------------------------------------
    k = vc._kpis_campo(df)
    print(f"[3] KPIs -> backlog={k['backlog']} criticas={k['criticas']} total={k['total']}")
    if k["backlog"] != 3:
        falhas.append(f"backlog esperado 3, obtido {k['backlog']}")
    # críticas = abertas prioridade 1/2 = ACL(1) + VBA(2) = 2
    if k["criticas"] != 2:
        falhas.append(f"criticas esperado 2, obtido {k['criticas']}")
    if k["total"] != 5:
        falhas.append(f"total esperado 5, obtido {k['total']}")

    # [4] _top_criticas: só abertas, ordenadas por score desc ------------------
    top = vc._top_criticas(df, n=10)
    print(f"[4] top prioridades: {len(top)} (só abertas) "
          f"1º={top.iloc[0]['ramal']}/{top.iloc[0]['score']}")
    if len(top) != 3:
        falhas.append(f"top deveria ter 3 (só abertas), obtido {len(top)}")
    if not top["status_usuario"].apply(lambda s: str(s).upper().startswith("AB")).all():
        falhas.append("top_criticas incluiu nota não-aberta")
    # 1ª deve ser ACL score 0.90 (maior score entre abertas)
    if not (top.iloc[0]["ramal"] == "ACL" and abs(top.iloc[0]["score"] - 0.90) < 1e-9):
        falhas.append(f"1ª prioridade errada: {top.iloc[0]['ramal']}/{top.iloc[0]['score']}")
    # score deve estar em ordem decrescente
    scores = top["score"].tolist()
    if scores != sorted(scores, reverse=True):
        falhas.append(f"top não está ordenado por score desc: {scores}")

    # [5] vazio / sem status ---------------------------------------------------
    k0 = vc._kpis_campo(pd.DataFrame())
    if k0 != {"backlog": 0, "criticas": 0, "total": 0}:
        falhas.append(f"KPIs de df vazio inesperado: {k0}")
    if not vc._top_criticas(pd.DataFrame()).empty:
        falhas.append("top_criticas de df vazio deveria ser vazio")
    print(f"[5] df vazio -> KPIs zerados e top vazio: OK")

    print("=" * 64)
    if falhas:
        print(f"❌ FALHOU ({len(falhas)}):")
        for f in falhas:
            print("   -", f)
        print("=" * 64)
        return 1
    print("✅ Sprint 9 (Visão de Campo) — e2e PASSOU.")
    print("=" * 64)
    print()
    print("CHECKLIST MANUAL no celular / Streamlit Cloud:")
    print("  [ ] Menu lateral mostra '📱 Visão de Campo'")
    print("  [ ] 3 KPIs grandes empilhados (Backlog / Críticas / Alertas)")
    print("  [ ] Lista de prioridades em cards (ramal · trecho · km · dias · score)")
    print("  [ ] Cards com barra colorida por prioridade; alertas ativos ao final")
    print("  [ ] Layout confortável em tela estreita (coluna única)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
