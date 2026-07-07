# core/notificacoes.py — Canais de notificação de alertas (Sprint 5)
#
# Previsão de e-mail/export conforme decisão do Julio. Por padrão o e-mail
# fica DESLIGADO (email_alertas_ativo=false) — o canal primário é o app
# (badge + tela de alertas). Este módulo apenas prepara a infraestrutura:
#   • exportar_alertas_csv/xlsx  → download na tela de alertas (já funcional)
#   • enviar_email_alertas       → stub SMTP, só dispara se ativado nas configs
#
# Sessão 1: Imports & configuração
# Sessão 2: Exportação (CSV / Excel)
# Sessão 3: E-mail (stub, desligado por padrão)

# region ====================== SESSÃO 1: Imports & Configuração ================
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd

COR_CRIT = "#dc2626"
COR_WARN = "#f59e0b"
COR_OK   = "#16a34a"

# Colunas exportadas e seus rótulos amigáveis
_COLUNAS_EXPORT = {
    "severidade":      "Severidade",
    "tipo":            "Tipo",
    "gerencia":        "Gerência",
    "disciplina":      "Disciplina",
    "ramal":           "Ramal",
    "origem":          "Origem (Pátio)",
    "familia_defeito": "Família",
    "n_ocorrencias":   "Ocorrências",
    "score_acumulado": "Score Acumulado",
    "status":          "Status",
}


def _config_email() -> dict:
    """
    Lê a configuração de e-mail da tabela `configuracoes`.
    Retorna {ativo: bool, destinatarios: list[str]}.
    """
    cfg = {"ativo": False, "destinatarios": []}
    try:
        from database.client import get_supabase
        supabase = get_supabase()
        resp = (
            supabase.table("configuracoes")
            .select("chave, valor")
            .is_("gerencia", "null")
            .in_("chave", ["email_alertas_ativo", "email_destinatarios"])
            .execute()
        )
        mapa = {r["chave"]: r["valor"] for r in (resp.data or [])}
        cfg["ativo"] = str(mapa.get("email_alertas_ativo", "false")).strip().lower() in ("true", "1", "sim")
        dest = mapa.get("email_destinatarios", [])
        if isinstance(dest, str):
            import json
            try:
                dest = json.loads(dest)
            except Exception:
                dest = [e.strip() for e in dest.split(",") if e.strip()]
        cfg["destinatarios"] = list(dest or [])
    except Exception:
        pass
    return cfg

# endregion


# region ====================== SESSÃO 2: Exportação ===========================

def _preparar_export(df: pd.DataFrame) -> pd.DataFrame:
    """Seleciona e renomeia colunas para exportação legível."""
    if df is None or df.empty:
        return pd.DataFrame(columns=list(_COLUNAS_EXPORT.values()))
    cols = [c for c in _COLUNAS_EXPORT if c in df.columns]
    out = df[cols].rename(columns=_COLUNAS_EXPORT)
    return out


def exportar_alertas_csv(df: pd.DataFrame) -> bytes:
    """Gera CSV (UTF-8 BOM p/ Excel PT-BR) dos alertas para download."""
    out = _preparar_export(df)
    return out.to_csv(index=False, sep=";").encode("utf-8-sig")


def exportar_alertas_xlsx(df: pd.DataFrame) -> bytes:
    """Gera XLSX dos alertas. Cai para CSV-bytes se o engine não existir."""
    out = _preparar_export(df)
    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            out.to_excel(writer, index=False, sheet_name="Alertas")
        return buffer.getvalue()
    except Exception:
        return out.to_csv(index=False, sep=";").encode("utf-8-sig")

# endregion


# region ====================== SESSÃO 3: E-mail (stub) ========================

def _montar_corpo_email(df: pd.DataFrame, gerencia: str) -> str:
    """Monta um corpo HTML simples com o resumo dos alertas críticos."""
    if df is None or df.empty:
        return "<p>Sem alertas ativos.</p>"

    criticos = df[df["severidade"] == "critico"] if "severidade" in df.columns else df
    linhas = []
    for _, r in criticos.head(20).iterrows():
        linhas.append(
            f"<tr>"
            f"<td>{r.get('tipo','')}</td>"
            f"<td>{r.get('ramal','')}</td>"
            f"<td>{r.get('origem','')}</td>"
            f"<td>{r.get('familia_defeito','')}</td>"
            f"<td style='text-align:center'>{r.get('n_ocorrencias','')}</td>"
            f"</tr>"
        )
    tabela = "".join(linhas) or "<tr><td colspan=5>Sem críticos</td></tr>"
    return (
        f"<h2 style='color:{COR_CRIT}'>MRS Sentinel — Alertas · Ger. {gerencia}</h2>"
        f"<p>{len(criticos)} alerta(s) crítico(s) em {datetime.now():%d/%m/%Y %H:%M}.</p>"
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<tr><th>Tipo</th><th>Ramal</th><th>Origem</th><th>Família</th><th>Ocorr.</th></tr>"
        f"{tabela}</table>"
    )


def enviar_email_alertas(df: pd.DataFrame, gerencia: str) -> dict:
    """
    Envia e-mail com os alertas — SOMENTE se email_alertas_ativo=true e houver
    destinatários e credenciais SMTP nos secrets. Caso contrário, no-op seguro.

    Retorna {enviado: bool, motivo: str}.

    Secrets esperados (st.secrets["smtp"]):
        host, port, usuario, senha, remetente
    """
    cfg = _config_email()
    if not cfg["ativo"]:
        return {"enviado": False, "motivo": "E-mail desativado nas configurações."}
    if not cfg["destinatarios"]:
        return {"enviado": False, "motivo": "Nenhum destinatário configurado."}

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import streamlit as st

        smtp_cfg = st.secrets.get("smtp", {})
        host = smtp_cfg.get("host")
        if not host:
            return {"enviado": False, "motivo": "SMTP não configurado nos secrets."}

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[MRS Sentinel] Alertas — Ger. {gerencia}"
        msg["From"]    = smtp_cfg.get("remetente", smtp_cfg.get("usuario", ""))
        msg["To"]      = ", ".join(cfg["destinatarios"])
        msg.attach(MIMEText(_montar_corpo_email(df, gerencia), "html"))

        porta = int(smtp_cfg.get("port", 587))
        with smtplib.SMTP(host, porta, timeout=20) as server:
            server.starttls()
            if smtp_cfg.get("usuario"):
                server.login(smtp_cfg["usuario"], smtp_cfg.get("senha", ""))
            server.sendmail(msg["From"], cfg["destinatarios"], msg.as_string())

        return {"enviado": True, "motivo": f"E-mail enviado a {len(cfg['destinatarios'])} destinatário(s)."}
    except Exception as e:
        return {"enviado": False, "motivo": f"Falha SMTP: {e}"}

# endregion
