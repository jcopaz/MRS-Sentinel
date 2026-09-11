# scripts/importar_usuarios_planilha.py — Importa em lote os colaboradores
# de "Usuarios Sentinel.xlsx" pra tabela usuarios + Supabase Auth.
#
# Reaproveita a MESMA sequência de modules/admin_panel.py::_criar_usuario
# (Auth admin.create_user + insert em usuarios, senha provisória
# SENHA_PADRAO, deve_trocar_senha=True) — sem duplicar a lógica, só sem o
# acoplamento a Streamlit UI (st.success/st.error/st.rerun), pra poder
# rodar como script de linha de comando.
#
# Uso:
#   python scripts/importar_usuarios_planilha.py                # dry-run (não grava nada)
#   python scripts/importar_usuarios_planilha.py --commit        # cria de verdade
#   python scripts/importar_usuarios_planilha.py --arquivo "outra.xlsx" --commit
#
# Pré-requisito: .streamlit/secrets.toml com [supabase] url/key/service_key
# válidos (o mesmo arquivo que o app usa) — precisa rodar de um lugar que
# alcance o Supabase (mesma rede/proxy do app).

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.client import get_supabase, get_supabase_admin  # noqa: E402
from modules.admin_panel import SENHA_PADRAO  # noqa: E402

# usuarios_gerencia_check (database/schema_gerencias_expandidas.sql) — só
# essas 6 passam no banco hoje. GC/AU (core/glossarios.py::LISTA_GERENCIAS)
# NÃO estão nesse CHECK — achado à parte, registrado na revisão do app.
GERENCIAS_VALIDAS = {"SP", "VP", "FN", "FS", "RJ", "LC"}

# "GG" na planilha = Gerência Geral São Paulo (SP+VP combinadas — mesma
# agregação de modules/gerencia_geral.py "Visão Geral"). Confirmado pelo
# Julio (2026-09-11): pessoa com esse valor deve ver SP e VP como Usuario.
# O banco não tem coluna pra "lista de gerências" hoje (só uma sigla ou
# NULL) — gerencia=NULL é o mecanismo mais próximo disponível (dá acesso a
# Visão Geral SP+VP), mas TAMBÉM libera ver as outras 6 gerências
# individualmente (auth/permissions.py::can_see_gerencia devolve True pra
# qualquer alvo quando não há gerência delegada) — mais amplo do que "só
# SP e VP". Registrado como limitação conhecida; usar só enquanto não
# houver escopo de N-gerências de verdade (tabela usuario_escopo já existe,
# sem UI/lógica ligada ainda).
_GERENCIA_GERAL_SP_VP = "GG"


def ler_planilha(caminho: str) -> list[dict]:
    wb = openpyxl.load_workbook(caminho, data_only=True)
    ws = wb.active
    registros = []
    for i, (matricula, nome, gerencia, email, cargo) in enumerate(
        ws.iter_rows(min_row=2, values_only=True), start=2
    ):
        registros.append({
            "linha": i,
            "matricula": str(matricula).strip() if matricula else None,
            "nome": (nome or "").strip(),
            "gerencia": (gerencia or "").strip().upper() or None,
            "email": (email or "").strip().lower() or None,
            "cargo": (cargo or "").strip(),
        })
    return registros


def validar(registros: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separa em (válidos, com_problema) — só forma, não consulta o banco
    (duplicata contra conta JÁ existente só aparece na hora de criar, via
    exceção do Supabase — mesmo comportamento de _criar_usuario)."""
    validos: list[dict] = []
    problemas: list[dict] = []
    vistos: set[str] = set()

    for r in registros:
        motivos = []
        if not r["matricula"]:
            motivos.append("sem matrícula")
        if not r["nome"]:
            motivos.append("sem nome")
        if not r["email"] or "@" not in r["email"]:
            motivos.append("e-mail ausente/inválido")
        if r["gerencia"] not in GERENCIAS_VALIDAS and r["gerencia"] != _GERENCIA_GERAL_SP_VP:
            motivos.append(f"gerência {r['gerencia']!r} fora do CHECK do banco {sorted(GERENCIAS_VALIDAS)}")
        if r["matricula"] and r["matricula"] in vistos:
            motivos.append("matrícula duplicada na própria planilha")
        if r["matricula"]:
            vistos.add(r["matricula"])

        if motivos:
            problemas.append({**r, "motivos": motivos})
        else:
            validos.append(r)

    return validos, problemas


def gerencia_para_gravar(gerencia_planilha: str) -> str | None:
    """"GG" (Gerência Geral SP+VP) não passa no usuarios_gerencia_check ->
    grava NULL (mecanismo mais próximo hoje: dá Visão Geral SP+VP, mas
    também amplia pras outras 6 gerências — ver comentário no topo do
    arquivo). Qualquer outra sigla válida grava como está."""
    return None if gerencia_planilha == _GERENCIA_GERAL_SP_VP else gerencia_planilha


def criar_usuario(registro: dict, criado_por: str | None) -> tuple[bool, str]:
    """Mesma sequência de modules/admin_panel.py::_criar_usuario, sem UI."""
    admin = get_supabase_admin()
    supabase = get_supabase()
    try:
        resp_auth = admin.auth.admin.create_user({
            "email": registro["email"],
            "password": SENHA_PADRAO,
            "email_confirm": True,
        })
        auth_user_id = resp_auth.user.id if resp_auth and resp_auth.user else None

        supabase.table("usuarios").insert({
            "nome": registro["nome"],
            "matricula": registro["matricula"],
            "email": registro["email"],
            "email_gerado": False,
            "auth_user_id": auth_user_id,
            "perfil": "usuario",
            "gerencia": gerencia_para_gravar(registro["gerencia"]),
            "acesso_tv": False,
            "ativo": True,
            "criado_por": criado_por,
            "deve_trocar_senha": True,
        }).execute()
        return True, ""
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "already been registered" in msg or "already registered" in msg:
            return False, "já cadastrado (matrícula ou e-mail já existem)"
        return False, str(e)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arquivo", default="Usuarios Sentinel.xlsx")
    ap.add_argument("--commit", action="store_true", help="sem essa flag, só mostra o que faria (dry-run)")
    ap.add_argument("--criado-por", default=None, help="user_id (uuid) do admin, pro log de auditoria")
    args = ap.parse_args()

    registros = ler_planilha(args.arquivo)
    validos, problemas = validar(registros)

    print(f"Planilha: {args.arquivo}")
    print(f"Total de linhas: {len(registros)} | válidas: {len(validos)} | com problema: {len(problemas)}\n")

    if problemas:
        print("=== LINHAS COM PROBLEMA (não serão criadas) ===")
        for p in problemas:
            print(f"  linha {p['linha']}: {p['nome']} (matrícula {p['matricula']}) -> {', '.join(p['motivos'])}")
        print()

    print("=== SERIAM CRIADAS (dry-run) ===" if not args.commit else "=== CRIANDO ===")
    for r in validos:
        if not args.commit:
            gerencia_gravada = gerencia_para_gravar(r["gerencia"])
            nota = " -> grava gerencia=NULL (Visão Geral SP+VP)" if gerencia_gravada is None else ""
            print(
                f"  [dry-run] {r['matricula']} | {r['nome']} | {r['gerencia']}{nota} | "
                f"{r['email']} | perfil=usuario | senha provisória={SENHA_PADRAO}"
            )
        else:
            ok, erro = criar_usuario(r, args.criado_por)
            status = "OK" if ok else f"PULADO ({erro})"
            print(f"  {r['matricula']} | {r['nome']} -> {status}")

    if not args.commit:
        print("\nNenhuma conta foi criada (dry-run). Rode de novo com --commit pra criar de verdade.")


if __name__ == "__main__":
    main()
