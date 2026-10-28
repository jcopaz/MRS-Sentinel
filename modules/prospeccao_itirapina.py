# =============================================================================
# modules/prospeccao_itirapina.py — Itirapina–Pederneiras
#
# Trecho Itirapina–Pederneiras (Sub 78, km 174,8–303,8) que entra na MRS em
# 2027. Aba restrita por e-mail (auth/permissions.py::can_ver_prospeccao —
# dono fixo + liberados no Painel Admin → Configurações).
#
# Desempenho: em vez de st.tabs (que desenha TODAS as subabas a cada clique),
# um seletor de visão desenha só a escolhida, e cada visão roda num
# st.fragment (interação dentro dela não reexecuta o resto). Cálculos
# pesados em cache por base (modules/itirapina/*).
#
# Visões:
#   🏁 One Page   — peça executiva 16:9 (modules/itirapina/onepage.py)
#   🛤️ Trecho     — unifilar navegável por km + restrições, defeitos, Vagão e
#                   equipamentos da janela (navegacao.py)
#   🎯 Travamento — avanço, mapa de calor, Top 10, ficha (travamento.py)
#   📈 Evolução   — base A × B, mudanças de restrição, transit time (evolucao.py)
#   📷 Inspeção   — galeria com mídias por link (inspecao.py)
#   ⚙️ Dados      — carregar arquivos, execução, metas, exportar (dados_view.py)
# Dados versionados por BASE (itp_trecho_bases); marco zero 26/10/2026.
# =============================================================================

import pandas as pd
import streamlit as st

from auth.permissions import can_upload_prospeccao, require_prospeccao
from modules.itirapina.dados import TRECHO_ROTULO, carregar_base, carregar_bases, carregar_referencias

VISOES = ["🏁 One Page", "🛤️ Trecho", "🎯 Travamento", "📈 Evolução", "📷 Inspeção", "⚙️ Dados"]


def _seletor_base(bases: pd.DataFrame, coluna):
    """Base mais recente por padrão."""
    b = bases.sort_values("data_base").reset_index(drop=True)
    rot = {int(r.id): f"{pd.to_datetime(r.data_base):%d/%m/%Y}" + (" · marco zero" if r.marco_zero else "")
           + (" 🔒" if r.congelada else "") for r in b.itertuples()}
    ids = list(rot)
    # Com a key já no session_state, o widget usa esse valor (não passar index).
    if st.session_state.get("base_sel") not in ids:
        st.session_state["base_sel"] = ids[-1]
    bid = coluna.selectbox("Base", ids, format_func=rot.get, key="base_sel", label_visibility="collapsed")
    return b[b["id"] == bid].iloc[0]


def _cabecalho(coluna) -> None:
    coluna.markdown(
        f"<div style='padding:2px 0 0 0'><span style='font-size:1.35rem;font-weight:700;color:#1e3a5f'>"
        f"🛤️ {TRECHO_ROTULO}</span><span style='color:#64748b;font-size:0.85rem;margin-left:10px'>"
        f"Sub 78 · km 174,8–303,8 · entra na MRS em 2027</span></div>", unsafe_allow_html=True)


@st.fragment
def _visao(visao: str, bases, base, base_id: int, pode_upload: bool) -> None:
    dados = carregar_base(base_id)
    refs = carregar_referencias()
    avisos = [a for a in dados["avisos"] + refs["avisos"] if "ausente" in a or "Erro" in a]
    if avisos:
        with st.expander(f"⚠️ {len(avisos)} aviso(s) de carga"):
            for a in dict.fromkeys(avisos):
                st.caption(a)
    from modules.itirapina import dados_view, evolucao, inspecao, navegacao, onepage, travamento
    if visao == "🏁 One Page":
        onepage.render_onepage(bases, base, refs)
    elif visao == "🛤️ Trecho":
        navegacao.render_unifilar(dados, refs, base_id)
    elif visao == "🎯 Travamento":
        travamento.render_travamento(dados, refs, base_id)
    elif visao == "📈 Evolução":
        evolucao.render_evolucao(bases, refs, dados)
    elif visao == "📷 Inspeção":
        inspecao.render_inspecao(dados, refs)
    else:
        dados_view.render_dados(bases, base, dados, refs, pode_upload)


def render_prospeccao_itirapina() -> None:
    require_prospeccao()
    bases, aviso = carregar_bases()
    c1, c2 = st.columns([3, 1])
    _cabecalho(c1)
    if bases is None or bases.empty:
        st.warning((aviso or "Nenhuma base criada.") + " Rode `database/schema_itirapina.sql` e "
                   "`database/schema_itirapina_fase2.sql` no Supabase.")
        return
    base = _seletor_base(bases, c2)
    pode_upload = can_upload_prospeccao()
    visao = st.segmented_control("Visão", VISOES, default=VISOES[0], key="itp_visao",
                                 label_visibility="collapsed") or VISOES[0]
    _visao(visao, bases, base, int(base["id"]), pode_upload)
