# integracoes/brevo.py — Envio de SMS via API HTTP do Brevo (2026-09-11)
#
# Por quê API HTTP: SMS não tem "SMTP equivalente" — é sempre por API. Usado
# por auth/recuperar_senha.py como canal PRIMÁRIO de reset quando a conta tem
# telefone cadastrado (ver database/schema_telefone.sql, auth/telefone.py);
# e-mail continua como canal secundário — mesma ordem decidida pro HubSP
# (relato de e-mail não estar chegando, 2026-09-10/11).
#
# Requer st.secrets["brevo"]["api_key"] (chave REST — Transactional SMS,
# DIFERENTE da chave SMTP usada em auth/recuperar_senha.py) e
# st.secrets["brevo"]["sms_sender"] (até 11 caracteres alfanuméricos, padrão
# GSM; nem toda operadora BR exibe sender alfanumérico, mas o Brevo aceita o
# envio de qualquer forma).

from __future__ import annotations

import requests
import streamlit as st

_BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/sms"
_TIMEOUT_SEGUNDOS = 15


def enviar_sms(telefone_e164: str, texto: str) -> bool:
    """
    Envia um SMS transacional via Brevo. Retorna True se o Brevo ACEITOU o
    envio (HTTP 200/201) — não garante entrega na operadora, só que a
    chamada em si deu certo. Qualquer falha (config ausente, erro de rede,
    rejeição do Brevo) -> False, silenciosa — quem chama decide o que fazer
    (ex.: cair pro e-mail como no auth/recuperar_senha.py).
    """
    cfg = st.secrets.get("brevo", {})
    api_key = cfg.get("api_key")
    sender = cfg.get("sms_sender")
    if not api_key or not sender or not telefone_e164:
        return False

    try:
        resp = requests.post(
            _BREVO_SMS_URL,
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "sender": sender,
                "recipient": telefone_e164.lstrip("+"),  # Brevo espera sem o "+"
                "content": texto,
                "type": "transactional",
            },
            timeout=_TIMEOUT_SEGUNDOS,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False
