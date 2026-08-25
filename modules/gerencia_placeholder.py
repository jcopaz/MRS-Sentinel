# modules/gerencia_placeholder.py — Tela "em construção" pra Gerências sem
# dashboard ligado ainda (Frente Norte, Frente Sul, Rio de Janeiro, Linha do
# Centro — ver database/schema_organograma.sql pra estrutura completa).
#
# Existe pra evitar que app.py caia no fallback de app.py::_rotear e mostre
# por engano o dashboard da Gerência SP pra um usuário de outra gerência —
# antes desta tela, uma rota "gerencia_fn" (por ex.) não reconhecida virava
# silenciosamente a tela de SP.

import streamlit as st

from core.glossarios import NOME_GERENCIA


def render_gerencia_placeholder(sigla: str) -> None:
    nome = NOME_GERENCIA.get(sigla, f"Gerência {sigla}")
    st.markdown(f"### 🏭 {nome}")
    st.info(
        f"⏳ O dashboard da **{nome}** ainda não foi conectado ao sistema. "
        "A estrutura organizacional já está cadastrada — falta ligar as telas "
        "de indicadores a ela. Fale com o administrador se precisar disso com urgência."
    )
