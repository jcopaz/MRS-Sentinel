# auth/telefone.py — Validação/normalização de telefone (E.164, Brasil)
#
# DORMENTE desde 2026-09-11 (não é chamado por nenhuma tela agora): a
# captura de telefone existia pra viabilizar reset de senha por SMS
# (v11.0.0), revertida no mesmo dia por falta de orçamento pra SMS (não
# existe gateway gratuito — ver core/versao.py 13.0.0). Fica pronto pra
# retomar (aqui, em integracoes/brevo.py e em auth/confirmar_telefone.py)
# se um dia fizer sentido — WhatsApp, provedor mais barato, ou orçamento
# aprovado. Função PURA, sem Streamlit/banco — testável isolada (ver
# PADRAO-DE-ENGENHARIA.md secao 7: "função pura primeiro").

from __future__ import annotations

import re


def validar_e_formatar_telefone(bruto: str) -> str | None:
    """
    Aceita celular/fixo brasileiro em qualquer grafia comum
    ("(11) 91234-5678", "11912345678", "+55 11 91234-5678") e devolve
    normalizado em E.164 (+55DDDNNNNNNNNN), ou None se não parecer válido.

    Regra: DDD (2 dígitos, 11-99 — não existe DDD 00-10 no Brasil) + 8 dígitos
    (fixo) ou 9 dígitos (celular, sempre iniciando em 9) = 10 ou 11 dígitos
    no total, sem o +55.
    """
    if not bruto:
        return None
    digitos = re.sub(r"\D", "", bruto)

    # Aceita com ou sem o "55" de país na frente.
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]

    if len(digitos) not in (10, 11):
        return None

    ddd = digitos[:2]
    if not (11 <= int(ddd) <= 99):
        return None

    if len(digitos) == 11 and digitos[2] != "9":
        return None  # 11 dígitos só é válido se o 3º for o "9" do celular

    return f"+55{digitos}"
