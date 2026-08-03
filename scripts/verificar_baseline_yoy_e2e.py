#!/usr/bin/env python3
# scripts/verificar_baseline_yoy_e2e.py — Verificação E2E do Sprint 7 (YoY 2025).
# Headless, SEM Supabase e SEM Streamlit real (usa stubs). Roda da raiz do repo:
#     python scripts/verificar_baseline_yoy_e2e.py
# Sai 0 se tudo passar, 1 caso contrário.
#
# Cobre:
#   1. Parser do congelado: raw (~16 col) -> canônico (gerência/ano/mes/thp/bool)
#   2. df_baseline_para_registros: JSON-safe (sem NaN, data ISO)
#   3. Bloco YoY (_bloco_yoy) roda sem exceção com stubs e compara 2025 × 2026

from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timedelta

import pandas as pd

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

FALHAS: list[str] = []


def _check(cond: bool, msg: str):
    print(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        FALHAS.append(msg)


# ---------------------------------------------------------------- stubs Streamlit
def _instalar_stubs():
    """Injeta stubs mínimos de streamlit + streamlit_echarts em sys.modules."""
    captura = {"echarts": []}

    st = types.ModuleType("streamlit")

    def _noop(*a, **k):
        return None

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Col(_Ctx):
        def metric(self, *a, **k): return None
        def markdown(self, *a, **k): return None
        def dataframe(self, *a, **k): return None

    for nome in ("markdown", "caption", "info", "warning", "error", "success",
                 "dataframe", "write", "divider", "metric", "toast", "balloons"):
        setattr(st, nome, _noop)
    st.columns = lambda spec, *a, **k: [_Col() for _ in (range(spec) if isinstance(spec, int) else spec)]
    st.expander = lambda *a, **k: _Ctx()
    st.container = lambda *a, **k: _Ctx()
    st.spinner = lambda *a, **k: _Ctx()

    # cache_data como decorador identidade (com .clear())
    def cache_data(*dargs, **dkw):
        def deco(fn):
            fn.clear = lambda: None
            return fn
        if dargs and callable(dargs[0]):
            return deco(dargs[0])
        return deco
    st.cache_data = cache_data

    # fragment / cache_resource — decoradores identidade
    def _passthrough_deco(*dargs, **dkw):
        def deco(fn):
            return fn
        if dargs and callable(dargs[0]):
            return dargs[0]
        return deco
    st.fragment = _passthrough_deco
    st.cache_resource = cache_data
    st.session_state = {}

    ech = types.ModuleType("streamlit_echarts")
    def st_echarts(options=None, **k):
        captura["echarts"].append(options)
        return None
    ech.st_echarts = st_echarts
    ech.JsCode = lambda s: s

    sys.modules["streamlit"] = st
    sys.modules["streamlit_echarts"] = ech
    return captura


# ---------------------------------------------------------------- dados sintéticos
def _raw_congelado() -> pd.DataFrame:
    """Simula o arquivo bruto do congelado 2025 (cabeçalhos com acento/espaço)."""
    linhas = []
    base = datetime(2025, 1, 5)
    sistemas = ["SINALIZAÇÃO", "ENERGIA", "TELECOM"]
    causas = ["Componente eletrônico", "Infiltração", "Vandalismo", "Desgaste"]
    for i in range(60):
        d = base + timedelta(days=i * 5)
        linhas.append({
            "Número nota": 5000 + i,
            "Data": d.strftime("%d/%m/%Y"),
            "Departamento": "GEE.SP" if i % 3 else "GEE.VP",
            "Tipo Solicitação": "Corretiva",
            "Codificação": f"3{i % 6}-Sintoma exemplo",
            "Causa": causas[i % len(causas)],
            "Local Instalação": "MF-LSP-FPA_FPA-SINALIZ-PN010B",
            "Grupo Ativo": "Circuito de Via",
            "Sistema": sistemas[i % len(sistemas)],
            "Status": "Encerrada",
            "Novo Indicador": "Sim" if i % 4 == 0 else "",
            "Gerador THP": "X" if i % 5 == 0 else "",
            "Tempo THP": (i % 5) * 30,
        })
    return pd.DataFrame(linhas)


def _rasf_vivo_2026() -> pd.DataFrame:
    """Base viva canônica com registros de 2025 e 2026 (SP)."""
    linhas = []
    for ano in (2025, 2026):
        for m in range(1, 8):  # jan..jul
            for _ in range(3 if ano == 2026 else 2):  # 2026 com mais falhas
                linhas.append({
                    "data_nota": datetime(ano, m, 10),
                    "gerencia": "SP", "disciplina": "EE",
                    "sistema": "SINALIZAÇÃO" if m % 2 else "ENERGIA",
                    "thp_min": 45, "anomalia_sintoma": "33-Circuito",
                })
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------- cenários
def cenario_parser():
    print("\n[1] Parser do congelado 2025 (raw -> canônico)")
    from core.parser_rasf_baseline import processar_baseline, COLUNAS_BASELINE

    raw = _raw_congelado()
    df = processar_baseline(raw)

    _check(not df.empty, f"parser retornou {len(df)} linhas")
    _check(set(["gerencia", "ano", "mes", "thp_min", "causa"]).issubset(df.columns),
           "colunas canônicas presentes (gerencia/ano/mes/thp_min/causa)")
    _check(set(df["gerencia"].dropna().unique()).issubset({"SP", "VP"}),
           f"gerência mapeada de Departamento GEE.xx -> {sorted(df['gerencia'].dropna().unique())}")
    _check(df["ano"].dropna().eq(2025).all(), "ano derivado da Data = 2025")
    _check(df["gerador_thp"].dtype == bool, "gerador_thp convertido para bool")
    _check(df["thp_min"].sum() > 0, f"THP somado = {df['thp_min'].sum():.0f} min")
    return df


def cenario_registros(df):
    print("\n[2] df_baseline_para_registros -> JSON-safe")
    from core.parser_rasf_baseline import df_baseline_para_registros
    regs = df_baseline_para_registros(df, upload_id="fake-uuid-0001")
    _check(len(regs) == len(df), f"{len(regs)} registros gerados")
    # nenhum float NaN nos valores
    import math
    tem_nan = any(isinstance(v, float) and math.isnan(v)
                  for r in regs for v in r.values())
    _check(not tem_nan, "nenhum NaN nos registros (JSON-safe)")
    datas_ok = all(("data_nota" not in r) or (r["data_nota"] is None)
                   or (isinstance(r["data_nota"], str) and r["data_nota"][:4].isdigit())
                   for r in regs)
    _check(datas_ok, "data_nota em ISO (YYYY-MM-DD) ou None")
    _check(all(r.get("upload_id") == "fake-uuid-0001" for r in regs), "upload_id propagado")


def cenario_yoy(df_baseline):
    print("\n[3] Bloco YoY (_bloco_yoy) com stubs")
    captura = _instalar_stubs()
    # (re)importa o componente já com o stub de streamlit ativo
    for m in list(sys.modules):
        if m.startswith("components.inteligencia_ee"):
            del sys.modules[m]
    from components.inteligencia_ee import _bloco_yoy, _yoy_prep

    df_atual = _rasf_vivo_2026()

    # sanidade das helpers
    prep = _yoy_prep(df_atual)
    _check("thp_h" in prep.columns and "ano" in prep.columns, "_yoy_prep deriva thp_h/ano/mes")

    try:
        _bloco_yoy(df_atual, df_baseline, escopo="SP")
        _check(True, "_bloco_yoy executou sem exceção")
    except Exception as e:
        _check(False, f"_bloco_yoy lançou exceção: {e}")

    _check(len(captura["echarts"]) >= 1,
           f"gerou {len(captura['echarts'])} gráfico(s) ECharts (mensal/causa)")

    # baseline vazio -> não deve quebrar (mostra orientação de upload)
    try:
        _bloco_yoy(df_atual, pd.DataFrame(), escopo="SP")
        _check(True, "baseline vazio tratado graciosamente (sem exceção)")
    except Exception as e:
        _check(False, f"baseline vazio quebrou: {e}")


def main():
    print("=" * 64)
    print("MRS Sentinel — E2E Sprint 7 (Base Congelada 2025 / YoY) — headless")
    print("=" * 64)

    df = cenario_parser()
    if df is not None and not df.empty:
        cenario_registros(df)
        cenario_yoy(df)

    print("\n" + "=" * 64)
    if FALHAS:
        print(f"❌ {len(FALHAS)} verificação(ões) falharam:")
        for f in FALHAS:
            print(f"   - {f}")
        print("=" * 64)
        return 1
    print("✅ Todos os cenários passaram.")
    print("=" * 64)
    print("""
CHECKLIST MANUAL no Streamlit Cloud (não coberto por este script):
  [ ] Rodar database/schema_rasf_baseline.sql no Supabase (tabela + CHECK)
  [ ] Upload disciplina "RASF — Base Congelada 2025" (SP e VP)
  [ ] Aba 🔌 Inteligência EE -> expander "📅 Comparativo Anual (YoY)"
      mostra KPIs YTD, barras 2025×vigente, YoY por Sistema e Causa 2025
  [ ] Visão Global consolida SP+VP respeitando gerências visíveis
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
