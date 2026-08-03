#!/usr/bin/env python3
# scripts/verificar_evolucao_e2e.py — Sprint 8 (Memória & Comparações)
#
# Teste headless do dashboard "Evolução da Malha" (modules/evolucao_malha.py):
# valida a lógica PURA de agregação (semana→mês, totais por período, setas Δ)
# sem depender de Streamlit/ECharts/Supabase rodando.
#
# Uso:  PYTHONPATH=<raiz_do_app> python3 scripts/verificar_evolucao_e2e.py

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
    # streamlit (só o necessário para importar o módulo)
    st = types.ModuleType("streamlit")

    def _noop(*a, **k):
        return None

    @contextmanager
    def _ctx(*a, **k):
        yield

    for nome in ("markdown", "caption", "info", "warning", "dataframe",
                 "line_chart", "selectbox", "multiselect", "radio",
                 "form_submit_button"):
        setattr(st, nome, _noop)
    st.columns = lambda n, *a, **k: [_ctx() for _ in range(n if isinstance(n, int) else len(n))]
    st.form = _ctx
    st.spinner = _ctx
    st.session_state = {}
    sys.modules["streamlit"] = st

    _stub("streamlit_echarts", st_echarts=lambda *a, **k: None)
    _stub("auth", )
    _stub("auth.session",
          get_gerencia=lambda: None,
          get_perfil=lambda: "admin")
    _stub("auth.permissions",
          can_see_gerencia=lambda g: True)
    # get_snapshots é substituído por fixture em cada teste
    _stub("database", )
    _stub("database.queries_snapshots",
          get_snapshots=lambda **k: None)


def main() -> int:
    print("=" * 64)
    print("MRS Sentinel — E2E Sprint 8 (Evolução da Malha) — headless")
    print("=" * 64)
    _instalar_stubs()

    import pandas as pd
    import modules.evolucao_malha as evo

    falhas = []

    # Fixture: 2 semanas (mesmo mês) × 2 trechos, gerência SP disciplina VP.
    # Semana W31 (data_ref 2026-08-03) e W32 (2026-08-10) — ambas de agosto/2026.
    linhas = [
        # W31
        {"semana_iso": "2026-W31", "data_ref": "2026-08-03", "gerencia": "SP",
         "disciplina": "VP", "ramal": "ACL", "trecho": "IPA-IPG",
         "total_notas": 10, "notas_abertas": 6, "aberturas_periodo": 3,
         "encerramentos_periodo": 2, "thp_acumulado": 120.0,
         "score_medio": 0.50, "notas_cronicas": 2, "pct_cronico": 20.0,
         "reincidentes": 1},
        {"semana_iso": "2026-W31", "data_ref": "2026-08-03", "gerencia": "SP",
         "disciplina": "VP", "ramal": "VBA", "trecho": "VBA-RGI",
         "total_notas": 4, "notas_abertas": 2, "aberturas_periodo": 1,
         "encerramentos_periodo": 1, "thp_acumulado": 30.0,
         "score_medio": 0.20, "notas_cronicas": 0, "pct_cronico": 0.0,
         "reincidentes": 0},
        # W32 (backlog do ACL sobe 6->8; encerramentos somam no mês)
        {"semana_iso": "2026-W32", "data_ref": "2026-08-10", "gerencia": "SP",
         "disciplina": "VP", "ramal": "ACL", "trecho": "IPA-IPG",
         "total_notas": 12, "notas_abertas": 8, "aberturas_periodo": 4,
         "encerramentos_periodo": 1, "thp_acumulado": 90.0,
         "score_medio": 0.60, "notas_cronicas": 3, "pct_cronico": 25.0,
         "reincidentes": 2},
        {"semana_iso": "2026-W32", "data_ref": "2026-08-10", "gerencia": "SP",
         "disciplina": "VP", "ramal": "VBA", "trecho": "VBA-RGI",
         "total_notas": 5, "notas_abertas": 3, "aberturas_periodo": 2,
         "encerramentos_periodo": 0, "thp_acumulado": 10.0,
         "score_medio": 0.25, "notas_cronicas": 1, "pct_cronico": 20.0,
         "reincidentes": 0},
    ]
    snap = pd.DataFrame(linhas)

    # Injeta a fixture no lugar do get_snapshots.
    evo.get_snapshots = lambda gerencia=None, disciplina=None, **k: (
        snap[snap["gerencia"] == gerencia] if gerencia else snap)

    # [1] SEMANAL: período = semana_iso; sem combinação -------------------------
    df_sem = evo._preparar(["SP"], ["VP"], "Semanal")
    periodos_sem = sorted(df_sem["periodo"].unique().tolist())
    print(f"[1] SEMANAL -> períodos={periodos_sem} linhas={len(df_sem)}")
    if periodos_sem != ["2026-W31", "2026-W32"]:
        falhas.append(f"semanal esperava W31/W32, obtido {periodos_sem}")
    if len(df_sem) != 4:
        falhas.append(f"semanal esperava 4 linhas (2 sem × 2 trechos), obtido {len(df_sem)}")

    # [2] MENSAL: combina semanas -> 1 período '2026-08', 2 trechos -------------
    df_mes = evo._preparar(["SP"], ["VP"], "Mensal")
    periodos_mes = sorted(df_mes["periodo"].unique().tolist())
    print(f"[2] MENSAL -> períodos={periodos_mes} linhas={len(df_mes)}")
    if periodos_mes != ["2026-08"]:
        falhas.append(f"mensal esperava ['2026-08'], obtido {periodos_mes}")
    if len(df_mes) != 2:
        falhas.append(f"mensal esperava 2 trechos combinados, obtido {len(df_mes)}")

    acl_mes = df_mes[df_mes["ramal"] == "ACL"]
    if acl_mes.empty:
        falhas.append("trecho ACL ausente na visão mensal")
    else:
        r = acl_mes.iloc[0]
        # fluxo soma: aberturas 3+4=7, encerr 2+1=3, thp 120+90=210
        # estoque = última foto (W32): backlog=8, cronicas=3
        print(f"    ACL mês -> aber={r['aberturas_periodo']} enc={r['encerramentos_periodo']} "
              f"thp={r['thp_acumulado']} backlog(ult)={r['notas_abertas']} cron(ult)={r['notas_cronicas']}")
        if r["aberturas_periodo"] != 7:
            falhas.append(f"ACL mensal aberturas esperado 7 (soma), obtido {r['aberturas_periodo']}")
        if r["encerramentos_periodo"] != 3:
            falhas.append(f"ACL mensal encerramentos esperado 3 (soma), obtido {r['encerramentos_periodo']}")
        if r["thp_acumulado"] != 210.0:
            falhas.append(f"ACL mensal thp esperado 210 (soma), obtido {r['thp_acumulado']}")
        if r["notas_abertas"] != 8:
            falhas.append(f"ACL mensal backlog esperado 8 (última foto), obtido {r['notas_abertas']}")
        if r["notas_cronicas"] != 3:
            falhas.append(f"ACL mensal crônicas esperado 3 (última foto), obtido {r['notas_cronicas']}")

    # [3] Totais por período (semanal): soma trechos + score ponderado ---------
    tot = evo._totais_por_periodo(df_sem)
    print(f"[3] totais/período -> {tot['periodo'].tolist()}")
    w31 = tot[tot["periodo"] == "2026-W31"].iloc[0]
    # backlog W31 = 6+2 = 8; score ponderado = (0.5*10 + 0.2*4)/14
    esperado_score = (0.5 * 10 + 0.2 * 4) / 14
    print(f"    W31 -> backlog={w31['notas_abertas']} score_pond={w31['score_medio']:.4f} "
          f"(esperado {esperado_score:.4f}) pct_cron={w31['pct_cronico']}")
    if int(w31["notas_abertas"]) != 8:
        falhas.append(f"W31 backlog total esperado 8, obtido {w31['notas_abertas']}")
    if abs(float(w31["score_medio"]) - esperado_score) > 1e-6:
        falhas.append(f"W31 score ponderado esperado {esperado_score:.4f}, obtido {w31['score_medio']}")
    # pct_cronico recomputado: (2+0)/(10+4)=14.3%
    if abs(float(w31["pct_cronico"]) - round(100 * 2 / 14, 1)) > 0.1:
        falhas.append(f"W31 pct_cronico recomputado inesperado: {w31['pct_cronico']}")

    # [4] Setas Δ: sentido bom/ruim -------------------------------------------
    # backlog subiu (menor_melhor) -> vermelho ▲
    up_ruim = evo._delta_html(8, 6, "menor_melhor", "int")
    # encerramentos subiu (maior_melhor) -> verde ▲
    up_bom = evo._delta_html(3, 1, "maior_melhor", "int")
    # backlog caiu (menor_melhor) -> verde ▼
    down_bom = evo._delta_html(4, 6, "menor_melhor", "int")
    print(f"[4] Δ backlog↑={'RUIM' if evo.COR_RUIM in up_ruim else '??'} "
          f"encerr↑={'BOM' if evo.COR_OK in up_bom else '??'} "
          f"backlog↓={'BOM' if evo.COR_OK in down_bom else '??'}")
    if evo.COR_RUIM not in up_ruim or "▲" not in up_ruim:
        falhas.append("backlog subindo deveria ser vermelho ▲")
    if evo.COR_OK not in up_bom or "▲" not in up_bom:
        falhas.append("encerramentos subindo deveria ser verde ▲")
    if evo.COR_OK not in down_bom or "▼" not in down_bom:
        falhas.append("backlog caindo deveria ser verde ▼")
    # sem período anterior -> traço neutro
    if "—" not in evo._delta_html(5, None, "menor_melhor", "int"):
        falhas.append("delta sem base deveria ser neutro (—)")

    # [5] vazio graceful -------------------------------------------------------
    evo.get_snapshots = lambda **k: pd.DataFrame()
    vazio = evo._preparar(["SP"], ["VP"], "Semanal")
    print(f"[5] sem fotos -> df vazio: {vazio.empty}")
    if not vazio.empty:
        falhas.append("sem snapshots deveria produzir df vazio")

    print("=" * 64)
    if falhas:
        print(f"❌ FALHOU ({len(falhas)}):")
        for f in falhas:
            print("   -", f)
        print("=" * 64)
        return 1
    print("✅ Sprint 8 (Evolução da Malha) — e2e PASSOU.")
    print("=" * 64)
    print()
    print("CHECKLIST MANUAL no Streamlit Cloud (não coberto por este script):")
    print("  [ ] Menu lateral mostra '📈 Evolução da Malha'")
    print("  [ ] Filtros (granularidade/disciplina/gerência) só rodam ao clicar Aplicar")
    print("  [ ] KPIs com setas ▲▼ (vermelho=piorou, verde=melhorou)")
    print("  [ ] Alternar Semanal/Mensal muda os períodos comparados")
    print("  [ ] Tabela por trecho ordena por Δ backlog (piores no topo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
