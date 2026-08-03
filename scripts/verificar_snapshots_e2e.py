#!/usr/bin/env python3
# scripts/verificar_snapshots_e2e.py — Sprint 8 (Memória & Comparações)
#
# Teste headless: valida core.snapshots (foto semanal agregada da base viva)
# sem depender de Streamlit rodando nem de Supabase.
#
# Uso:  PYTHONPATH=<raiz_do_app> python3 scripts/verificar_snapshots_e2e.py

import sys
import types
from contextlib import contextmanager
from datetime import date, timedelta


def _instalar_stub_streamlit():
    st = types.ModuleType("streamlit")

    def _ident(*a, **k):
        def deco(fn):
            try:
                fn.clear = lambda: None
            except Exception:
                pass
            return fn
        if a and callable(a[0]):
            return deco(a[0])
        return deco

    st.cache_data = _ident
    st.cache_resource = _ident
    st.fragment = _ident
    for nome in ("info", "warning", "caption", "markdown", "map", "dataframe",
                 "plotly_chart", "write", "error", "success", "spinner"):
        setattr(st, nome, lambda *a, **k: None)

    @contextmanager
    def _ctx(*a, **k):
        yield
    st.expander = _ctx
    st.container = _ctx
    st.spinner = _ctx
    st.secrets = {}
    sys.modules["streamlit"] = st


def main() -> int:
    print("=" * 64)
    print("MRS Sentinel — E2E Sprint 8 (Snapshots semanais) — headless")
    print("=" * 64)
    _instalar_stub_streamlit()

    import pandas as pd
    from core.snapshots import (semana_iso_de, montar_snapshot,
                                _flags_cronico_reincidente)

    falhas = []
    REF = date(2026, 8, 5)          # quarta-feira → semana ISO 2026-W32
    seg = REF - timedelta(days=REF.weekday())  # segunda 2026-08-03

    # [1] semana ISO -----------------------------------------------------------
    sem = semana_iso_de(REF)
    print(f"[1] semana_iso_de({REF}) -> {sem['semana_iso']} "
          f"(data_ref={sem['data_ref']})")
    if sem["semana_iso"] != "2026-W32":
        falhas.append(f"semana_iso esperado 2026-W32, obtido {sem['semana_iso']}")
    if sem["data_ref"] != seg:
        falhas.append("data_ref não é a segunda-feira da semana ISO")

    # [2] DataFrame sintético de notas ----------------------------------------
    # Ramal ACL, origem IPA, família 'Trilho': 4 notas na janela -> CRÔNICO.
    # Duas delas nesta semana (aberturas); uma encerrada nesta semana.
    # Reincidência: nota encerrada + reabertura <90d no mesmo grupo.
    hoje = pd.Timestamp(REF)
    linhas = [
        # crônico (>=3) no grupo ACL|IPA|Trilho, dentro da janela de 6 meses
        {"ramal": "ACL", "trecho": "IPA-IPG", "origem": "IPA",
         "familia_defeito": "Trilho", "prioridade": "Emergencial",
         "data_nota": hoje - pd.Timedelta(days=120), "data_encerramento": hoje - pd.Timedelta(days=100),
         "status_usuario": "Encerrada"},
        {"ramal": "ACL", "trecho": "IPA-IPG", "origem": "IPA",
         "familia_defeito": "Trilho", "prioridade": "Alta",
         "data_nota": hoje - pd.Timedelta(days=1),  # abriu ESTA semana
         "data_encerramento": pd.NaT, "status_usuario": "Aberta"},
        {"ramal": "ACL", "trecho": "IPA-IPG", "origem": "IPA",
         "familia_defeito": "Trilho", "prioridade": "Média",
         "data_nota": hoje,             # abriu ESTA semana; reabertura (<90d do enc acima)
         "data_encerramento": pd.NaT, "status_usuario": "Aberta"},
        {"ramal": "ACL", "trecho": "IPA-IPG", "origem": "IPA",
         "familia_defeito": "Trilho", "prioridade": "Baixa",
         "data_nota": hoje - pd.Timedelta(days=40),
         "data_encerramento": hoje - pd.Timedelta(days=2),  # ENCERROU esta semana
         "status_usuario": "Encerrada"},
        # grupo isolado (não crônico) em outro trecho
        {"ramal": "VBA", "trecho": "VBA-RGI", "origem": "VBA",
         "familia_defeito": "AMV", "prioridade": "Baixa",
         "data_nota": hoje - pd.Timedelta(days=10),
         "data_encerramento": pd.NaT, "status_usuario": "Aberta"},
    ]
    df = pd.DataFrame(linhas)
    print(f"[2] notas sintéticas: {len(df)} linhas / "
          f"{df['ramal'].nunique()} ramais")

    # [3] flags crônico/reincidente -------------------------------------------
    cron, reinc = _flags_cronico_reincidente(df)
    n_cron = int(cron.sum())
    n_reinc = int(reinc.sum())
    print(f"[3] flags -> crônicas={n_cron} · reincidentes={n_reinc}")
    if n_cron < 4:
        falhas.append(f"esperava 4 notas crônicas (ACL|IPA|Trilho), obtido {n_cron}")
    if n_reinc < 1:
        falhas.append(f"esperava >=1 reincidente (reabertura <90d), obtido {n_reinc}")

    # [4] montar_snapshot ------------------------------------------------------
    snap = montar_snapshot("SP", "VP", df=df, ref_date=REF)
    print(f"[4] snapshot: {len(snap)} recorte(s) de trecho")
    cols_esp = {"semana_iso", "ano", "semana", "data_ref", "gerencia",
                "disciplina", "ramal", "trecho", "total_notas", "notas_abertas",
                "aberturas_periodo", "encerramentos_periodo", "thp_acumulado",
                "score_medio", "notas_cronicas", "pct_cronico", "reincidentes",
                "chave"}
    faltando = cols_esp - set(snap.columns)
    if faltando:
        falhas.append(f"colunas ausentes no snapshot: {faltando}")
    if len(snap) != 2:
        falhas.append(f"esperava 2 recortes (ACL, VBA), obtido {len(snap)}")

    # Recorte ACL|IPA-IPG
    acl = snap[snap["ramal"] == "ACL"]
    if acl.empty:
        falhas.append("recorte ACL ausente no snapshot")
    else:
        r = acl.iloc[0]
        print(f"    ACL -> total={r['total_notas']} abertas={r['notas_abertas']} "
              f"aber_sem={r['aberturas_periodo']} enc_sem={r['encerramentos_periodo']} "
              f"cron={r['notas_cronicas']} pct_cron={r['pct_cronico']} "
              f"reinc={r['reincidentes']} score_medio={r['score_medio']}")
        if r["total_notas"] != 4:
            falhas.append(f"ACL total_notas esperado 4, obtido {r['total_notas']}")
        if r["aberturas_periodo"] != 2:
            falhas.append(f"ACL aberturas_periodo esperado 2, obtido {r['aberturas_periodo']}")
        if r["encerramentos_periodo"] != 1:
            falhas.append(f"ACL encerramentos_periodo esperado 1, obtido {r['encerramentos_periodo']}")
        if r["notas_cronicas"] != 4:
            falhas.append(f"ACL notas_cronicas esperado 4, obtido {r['notas_cronicas']}")
        if r["reincidentes"] < 1:
            falhas.append(f"ACL reincidentes esperado >=1, obtido {r['reincidentes']}")
        if r["score_medio"] is None:
            falhas.append("ACL score_medio não calculado")
        if r["chave"] != "2026-W32|SP|VP|ACL|IPA-IPG":
            falhas.append(f"ACL chave inesperada: {r['chave']}")

    # [5] JSON-safe + idempotência da chave -----------------------------------
    snap2 = montar_snapshot("SP", "VP", df=df, ref_date=REF)
    mesma_chave = set(snap["chave"]) == set(snap2["chave"])
    print(f"[5] idempotência de chave (mesma semana/escopo) -> {mesma_chave}")
    if not mesma_chave:
        falhas.append("chaves divergiram entre execuções idênticas (quebra o upsert)")

    # [6] df vazio -> snapshot vazio (graceful) --------------------------------
    vazio = montar_snapshot("SP", "VP", df=pd.DataFrame(), ref_date=REF)
    print(f"[6] df vazio -> snapshot vazio: {vazio.empty}")
    if not vazio.empty:
        falhas.append("df vazio deveria produzir snapshot vazio")

    print("=" * 64)
    if falhas:
        print(f"❌ FALHOU ({len(falhas)}):")
        for f in falhas:
            print("   -", f)
        print("=" * 64)
        return 1
    print("✅ Sprint 8 (Snapshots semanais) — e2e PASSOU.")
    print("=" * 64)
    print()
    print("CHECKLIST MANUAL no Streamlit Cloud (não coberto por este script):")
    print("  [ ] Rodar database/schema_snapshots.sql no Supabase (tabela + índices)")
    print("  [ ] Fazer um upload de notas VP/EE -> aparece '📸 Foto semanal atualizada'")
    print("  [ ] Reenviar no mesmo dia -> upsert atualiza a semana (não duplica)")
    print("  [ ] Conferir tabela snapshots: 1 linha por trecho da semana ISO corrente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
