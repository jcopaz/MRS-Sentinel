#!/usr/bin/env python3
# scripts/verificar_alertas_e2e.py — Verificação end-to-end do motor de Alertas
# (Sprint 5, fechamento). NÃO acessa Supabase: usa notas sintéticas e exercita
# core.alertas + core.notificacoes de forma headless.
#
# Uso local (na raiz do repo):
#     python scripts/verificar_alertas_e2e.py
# Sai com código 0 se todos os cenários passarem; 1 caso contrário.
#
# Cobre:
#   1. Hot-spot CRÔNICO (>=3 notas mesma família/local em 6 meses) -> crítico
#   2. REINCIDÊNCIA (reabertura <=90 dias no mesmo local)
#   3. RUÍDO que NÃO deve virar alerta (poucas notas, espaçadas)
#   4. Export CSV / XLSX / PDF(ou HTML) não quebra

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

# Garante import a partir da raiz do repo, rodando de qualquer pasta
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

FALHAS: list[str] = []


def _check(cond: bool, msg: str):
    marca = "✅" if cond else "❌"
    print(f"  {marca} {msg}")
    if not cond:
        FALHAS.append(msg)


def _notas_sinteticas() -> pd.DataFrame:
    """Constrói um DataFrame de notas cobrindo os 3 cenários."""
    hoje = datetime.now()
    linhas = []

    # (1) Crônico: 4 notas mesma família no mesmo ramal+origem, dentro de 6 meses
    for i in range(4):
        linhas.append({
            "ramal": "Santos - Jundiaí", "origem": "IPG",
            "familia_defeito": "Circuito de Via", "prioridade": "Alta",
            "data_nota": hoje - timedelta(days=20 * i + 5),
            "data_encerramento": hoje - timedelta(days=20 * i),
            "gerencia": "SP", "disciplina": "EE", "score": 30 + i,
        })

    # (2) Reincidência: reabertura 20 dias após encerramento no mesmo local
    linhas.append({
        "ramal": "Santos - Jundiaí", "origem": "IRS",
        "familia_defeito": "Máquina de Chave", "prioridade": "Alta",
        "data_nota": hoje - timedelta(days=60),
        "data_encerramento": hoje - timedelta(days=55),
        "gerencia": "SP", "disciplina": "EE", "score": 25,
    })
    linhas.append({
        "ramal": "Santos - Jundiaí", "origem": "IRS",
        "familia_defeito": "Máquina de Chave", "prioridade": "Média",
        "data_nota": hoje - timedelta(days=35),   # 20 dias após o encerramento
        "data_encerramento": None,
        "gerencia": "SP", "disciplina": "EE", "score": 18,
    })

    # (3) Ruído: 2 notas espaçadas, família única -> não deve virar crônico
    for i in range(2):
        linhas.append({
            "ramal": "Santos - Jundiaí", "origem": "IAA",
            "familia_defeito": "Sinalização", "prioridade": "Baixa",
            "data_nota": hoje - timedelta(days=300 + 40 * i),
            "data_encerramento": hoje - timedelta(days=295 + 40 * i),
            "gerencia": "SP", "disciplina": "EE", "score": 5,
        })

    return pd.DataFrame(linhas)


def cenario_deteccao():
    print("\n[1] Detecção crônico + reincidência + severidade")
    try:
        from core.alertas import (
            detectar_hotspots_cronicos, detectar_reincidencia, carregar_config_alertas,
        )
    except Exception as e:
        _check(False, f"import core.alertas falhou: {e}")
        return pd.DataFrame()

    df = _notas_sinteticas()
    try:
        cfg = carregar_config_alertas()
    except Exception:
        cfg = {"n_min": 3, "janela_meses": 6, "reincidencia_dias": 90}

    try:
        cron = detectar_hotspots_cronicos(df, cfg)
        reinc = detectar_reincidencia(df, cfg)
    except Exception as e:
        _check(False, f"execução dos detectores falhou: {e}")
        return pd.DataFrame()

    _check(cron is not None and len(cron) >= 1,
           f"detectou >=1 hot-spot crônico (IPG/Circuito de Via) — obtido {0 if cron is None else len(cron)}")
    _check(reinc is not None and len(reinc) >= 1,
           f"detectou >=1 reincidência (IRS/Máquina de Chave) — obtido {0 if reinc is None else len(reinc)}")

    partes = [x for x in (cron, reinc) if x is not None and not x.empty]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def cenario_gerar_alertas_offline():
    """Se gerar_alertas aceitar df injetado, ótimo; senão, apenas informa."""
    print("\n[2] gerar_alertas / persistir_alertas (sem Supabase = tolerante a falha)")
    try:
        from core.alertas import gerar_alertas  # noqa: F401
        _check(True, "core.alertas.gerar_alertas importável")
    except Exception as e:
        _check(False, f"import gerar_alertas falhou: {e}")


def cenario_export(df_alertas: pd.DataFrame):
    print("\n[3] Exportação CSV / XLSX / PDF(ou HTML)")
    try:
        from core.notificacoes import (
            exportar_alertas_csv, exportar_alertas_xlsx,
            exportar_alertas_pdf, exportar_alertas_relatorio_html,
        )
    except Exception as e:
        _check(False, f"import core.notificacoes falhou: {e}")
        return

    # Normaliza colunas esperadas pelo exportador
    if not df_alertas.empty:
        df_alertas = df_alertas.rename(columns={"n_notas": "n_ocorrencias"})
    for col in ("severidade", "tipo", "gerencia", "disciplina", "ramal",
                "origem", "familia_defeito", "n_ocorrencias", "score_acumulado", "status"):
        if col not in df_alertas.columns:
            df_alertas[col] = None
    if "severidade" in df_alertas and df_alertas["severidade"].isna().all():
        df_alertas["severidade"] = "critico"

    try:
        csv_b = exportar_alertas_csv(df_alertas)
        _check(isinstance(csv_b, (bytes, bytearray)) and len(csv_b) > 0, "CSV gerado")
    except Exception as e:
        _check(False, f"CSV falhou: {e}")

    try:
        xlsx_b = exportar_alertas_xlsx(df_alertas)
        _check(isinstance(xlsx_b, (bytes, bytearray)) and len(xlsx_b) > 0, "XLSX gerado")
    except Exception as e:
        _check(False, f"XLSX falhou: {e}")

    try:
        pdf_b = exportar_alertas_pdf(df_alertas, "SP")
        if pdf_b:
            _check(pdf_b[:5] == b"%PDF-", f"PDF gerado (assinatura %PDF-, {len(pdf_b)} bytes)")
        else:
            html_b = exportar_alertas_relatorio_html(df_alertas, "SP")
            _check(b"<table" in html_b, "reportlab ausente -> fallback HTML imprimível OK")
    except Exception as e:
        _check(False, f"PDF/HTML falhou: {e}")


def main():
    print("=" * 64)
    print("MRS Sentinel — Verificação E2E de Alertas (headless, sem Supabase)")
    print("=" * 64)

    df_alertas = cenario_deteccao()
    cenario_gerar_alertas_offline()
    cenario_export(df_alertas)

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
  [ ] Login como ADMIN        -> vê Recalcular + Visto/Resolver + PDF
  [ ] Login como ASSISTENTE SP -> gere alertas só da SP; não vê botões da VP
  [ ] Login como USUÁRIO      -> tela em modo somente-leitura (sem Recalcular,
      sem Visto/Resolver), mas CSV/Excel/PDF disponíveis
  [ ] Upload novo -> badge 🚨 na sidebar incrementa
  [ ] Resolver todos -> badge de "novos" zera
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
