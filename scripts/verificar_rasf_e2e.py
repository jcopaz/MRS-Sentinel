#!/usr/bin/env python3
# =============================================================================
# scripts/verificar_rasf_e2e.py — Verificação e2e da ingestão RASF
# Sprint 6 — MRS Sentinel
#
# Roda LOCALMENTE (na sua máquina, com o venv do projeto e o secrets.toml
# preenchido). Valida, contra o Supabase real:
#   1. Conexão + credenciais
#   2. Existência da tabela rasf_ee (você já aplicou schema_rasf.sql?)
#   3. Parsing do export RASF (core.parser_rasf)
#   4. (opcional) Ingestão de verdade do arquivo, com --gravar
#
# USO:
#   python scripts/verificar_rasf_e2e.py <caminho_do_RASF.xlsx>
#   python scripts/verificar_rasf_e2e.py <RASF.xlsx> --gravar   # grava no banco
#
# Requer, no diretório raiz do projeto, .streamlit/secrets.toml com:
#   [supabase]
#   url = "..."; key = "..."; service_key = "..."
# =============================================================================

import sys
import os
import argparse
import tomllib
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _carregar_secrets() -> dict:
    for caminho in [".streamlit/secrets.toml",
                    os.path.expanduser("~/.streamlit/secrets.toml")]:
        if os.path.exists(caminho):
            with open(caminho, "rb") as f:
                return tomllib.load(f)
    raise SystemExit("❌ .streamlit/secrets.toml não encontrado.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", help="Caminho do export RASF (.xlsx)")
    ap.add_argument("--gravar", action="store_true",
                    help="Grava de verdade em rasf_ee (anti-duplicação).")
    args = ap.parse_args()

    print("── 1. Credenciais ──────────────────────────────")
    secrets = _carregar_secrets()
    url = secrets["supabase"]["url"]
    key = secrets["supabase"].get("service_key") or secrets["supabase"]["key"]
    print(f"   ✅ URL: {url}")

    print("── 2. Conexão + tabela rasf_ee ─────────────────")
    # Importa database.client só pelo efeito colateral: ele desliga a
    # verificação de certificado SSL (redes corporativas com proxy/MITM,
    # ex.: MRS) — sem isso, create_client() abaixo falha com
    # CERTIFICATE_VERIFY_FAILED antes mesmo de tentar autenticar.
    import database.client  # noqa: F401
    from supabase import create_client
    sb = create_client(url, key)
    try:
        r = sb.table("rasf_ee").select("id").limit(1).execute()
        print(f"   ✅ Tabela rasf_ee acessível (linhas de amostra: {len(r.data)})")
    except Exception as e:
        raise SystemExit(f"   ❌ rasf_ee inacessível — aplicou schema_rasf.sql? {e}")

    print("── 3. Parsing do RASF ──────────────────────────")
    from core.parser_rasf import carregar_rasf_xlsx, df_rasf_para_registros
    df = carregar_rasf_xlsx(args.xlsx)
    print(f"   ✅ {len(df)} linhas parseadas")
    print(f"      gerências: {df['gerencia'].value_counts().to_dict()}")
    print(f"      reincid. ativo: {int(df['reincidencia_ativo'].sum())}"
          f" | backlog RCA: {int(df['lacuna_rca'].sum())}"
          f" | THP: {df['thp_min'].sum()/60:.0f} h")

    if not args.gravar:
        print("\n✅ Verificação OK (modo leitura). "
              "Rode com --gravar para ingerir de verdade.")
        return

    print("── 4. Ingestão real (por gerência) ─────────────")
    for ger in sorted(df["gerencia"].dropna().unique()):
        sub = df[df["gerencia"] == ger].reset_index(drop=True)
        sb.table("uploads_historico").update({"status": "substituido"}).match(
            {"gerencia": ger, "disciplina": "RASF", "status": "ativo"}).execute()
        up = sb.table("uploads_historico").insert({
            "gerencia": ger, "disciplina": "RASF",
            "nome_arquivo": os.path.basename(args.xlsx),
            "total_notas": len(sub), "status": "ativo",
        }).execute()
        upload_id = up.data[0]["id"]
        regs = df_rasf_para_registros(sub, upload_id)
        for i in range(0, len(regs), 500):
            sb.table("rasf_ee").insert(regs[i:i + 500]).execute()
        print(f"   ✅ {ger}: {len(sub)} linhas gravadas (upload {upload_id})")

    print("\n🎉 Ingestão concluída. Abra a aba 🔌 Inteligência EE no app.")


if __name__ == "__main__":
    main()
