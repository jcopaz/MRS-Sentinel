# =============================================================================
# modules/itirapina/onepage.py — Visão 🏁 One Page
#
# Uma figura Plotly única 16:9 (core/onepage_fig.py) que é a tela e a peça de
# apresentação: PNG em alta resolução pelo botão de câmera do gráfico (gerado
# no navegador) e HTML interativo por download (abre offline; imprime em PDF).
# Dados: core/onepage.montar_onepage — marco zero × base selecionada; só o
# marco zero → modo "Ponto de partida". Resultado em cache por (marco zero,
# base, execução) — a tela não recalcula a cada clique.
# =============================================================================

import pandas as pd
import streamlit as st

from core.onepage import montar_onepage
from core.onepage_fig import config_exportacao, fig_onepage, html_onepage
from modules.itirapina.dados import carregar_base
from modules.itirapina.evolucao import foto_da_base
from modules.itirapina.execucao import carregar_execucao


def _base_mz(bases: pd.DataFrame):
    mz = bases[bases["marco_zero"].fillna(False)]
    return (mz if len(mz) else bases.sort_values("data_base")).iloc[0]


@st.cache_data(ttl=600, show_spinner=False)
def _montar(mz_id: int, base_id: int, assinatura_exec: tuple, _mz, _base, _refs: dict) -> dict:
    d_mz = carregar_base(mz_id)
    evol = base_id != mz_id
    kw = {}
    if evol:
        d_b = carregar_base(base_id)
        kw = dict(foto_atual=foto_da_base(base_id, _base["data_base"], _refs),
                  rel_atual=d_b["rel"], dorm_atual=d_b["dormentes"], defeitos_atual=d_b["defeitos"])
    e, _ = carregar_execucao()
    return montar_onepage(
        data_mz=pd.to_datetime(_mz["data_base"]).date(),
        data_atual=pd.to_datetime((_base if evol else _mz)["data_base"]).date(),
        foto_mz=foto_da_base(mz_id, _mz["data_base"], _refs), rel_mz=d_mz["rel"], dorm_mz=d_mz["dormentes"],
        defeitos_mz=d_mz["defeitos"], transit=d_mz["transit"], plano=_refs.get("plano"), execucao=e,
        metas=_refs.get("metas"), estacoes=_refs.get("estacoes"), pontos=_refs.get("pontos"), **kw)


@st.cache_data(ttl=600, show_spinner=False, max_entries=4)
def _html(mz_id: int, base_id: int, assinatura_exec: tuple, _fig) -> bytes:
    return html_onepage(_fig)


def render_onepage(bases: pd.DataFrame, base_atual, refs: dict) -> None:
    if bases is None or bases.empty:
        st.info("A One Page usa as bases versionadas — carregue o marco zero.")
        return
    mz = _base_mz(bases)
    atual = base_atual if base_atual is not None else mz
    e, _ = carregar_execucao()
    assinatura = (len(e), str(e["data"].max()) if len(e) else "")
    with st.spinner("Montando a One Page..."):
        o = _montar(int(mz["id"]), int(atual["id"]), assinatura, mz, atual, refs)
    fig = fig_onepage(o)
    nome = f"OnePage_Itirapina_Pederneiras_{o['data_atual']:%Y-%m-%d}"
    st.plotly_chart(fig, use_container_width=False, config=config_exportacao(nome), key="op_fig")
    c1, c2 = st.columns([1, 3])
    c1.download_button("📥 HTML interativo", _html(int(mz["id"]), int(atual["id"]), assinatura, fig),
                       f"{nome}.html", "text/html", key="op_html")
    c2.caption("📷 PNG em alta resolução: botão de câmera no canto do gráfico. "
               "PDF: abra o HTML e imprima (Ctrl+P → Salvar como PDF).")
