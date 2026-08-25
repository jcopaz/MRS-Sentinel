# modules/selecionar_gg.py — Pré-tela "Escolha a Gerência Geral" (Fase 1)
#
# Contexto: hoje só existe UMA Gerência Geral com dashboard ligado (São
# Paulo — SP/VP). A estrutura completa (São Paulo, Ferrovia do Aço, Rio de
# Janeiro, Linha do Centro) já está cadastrada em org_unidades (ver
# database/schema_organograma.sql), mas só SP tem telas de fato conectadas.
#
# Esta tela é mostrada só pro Admin (perfil global, sem 'gerencia' fixa —
# ver auth/login.py) como ponto de entrada opcional pra escolher qual
# Gerência Geral explorar. Assistente/Usuário de uma gerência específica
# continuam indo direto pro dashboard deles, sem esse passo a mais — não
# faz sentido adicionar fricção pra quem só enxerga uma gerência mesmo.

import streamlit as st

from auth.session import set_pagina
from core.glossarios import LISTA_GERENCIAS, GERENCIA_GERAL_DE, GERENCIAS_COM_DASHBOARD


def _agrupar_por_gg() -> dict[str, list[str]]:
    """Agrupa LISTA_GERENCIAS por Gerência Geral, preservando a ordem."""
    grupos: dict[str, list[str]] = {}
    for sigla in LISTA_GERENCIAS:
        gg = GERENCIA_GERAL_DE.get(sigla, sigla)
        grupos.setdefault(gg, []).append(sigla)
    return grupos


def render_selecionar_gg() -> None:
    st.markdown("### 🗺️ Escolha a Gerência Geral")
    st.caption(
        "Cada Gerência Geral tem o mesmo tipo de dashboard, com a visão das "
        "gerências que fazem parte dela."
    )

    grupos = _agrupar_por_gg()
    cols = st.columns(len(grupos))
    for col, (nome_gg, siglas) in zip(cols, grupos.items()):
        with col:
            tem_dashboard = any(s in GERENCIAS_COM_DASHBOARD for s in siglas)
            rotulo = f"🏭 Gerência Geral {nome_gg}" if tem_dashboard else f"🚧 Gerência Geral {nome_gg}"
            if st.button(rotulo, key=f"btn_gg_{nome_gg}", use_container_width=True):
                # "São Paulo" tem visão combinada (SP+VP) pronta em
                # gerencia_geral.py — as demais GGs ainda não têm essa
                # combinação, então cai na 1ª gerência dela (mostra o
                # dashboard, se pronto, ou o placeholder "em construção").
                if nome_gg == "São Paulo":
                    set_pagina("gerencia_geral")
                else:
                    set_pagina(f"gerencia_{siglas[0].lower()}")
                st.rerun()
            if not tem_dashboard:
                st.caption("Dashboard ainda não conectado.")
            else:
                st.caption(" · ".join(siglas))
