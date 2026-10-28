# =============================================================================
# modules/itirapina/dados_view.py — Visão ⚙️ Dados
#
# Tudo o que é operação de dados fica aqui, fora das telas de leitura:
#   Carregar arquivos (cards por base) · Execução (planilha-modelo e registros)
#   · Metas · Exportar (Excel da base).
# =============================================================================

import pandas as pd
import streamlit as st

from core.analise_trecho import restricoes_trecho
from core.exportacao import gerar_excel_bytes
from modules.itirapina import execucao, upload


def _exportar(dados: dict, refs: dict, base) -> None:
    data = f"{pd.to_datetime(base['data_base']):%Y-%m-%d}" if base is not None else "base"
    itens = []
    d = dados.get("dormentes")
    if d is not None and not d.empty:
        cols = [c for c in ("sb", "linha", "equipamento_siv", "km_inicio", "km_fim", "total_prospectado",
                            "qtd_inservivel", "taxa_pct", "malhas_criticas") if c in d.columns]
        itens.append(("🪵 Prospecção de dormentes", d[cols], "Dormentes"))
    f = dados.get("defeitos")
    if f is not None and not f.empty:
        itens.append(("🛠️ Defeitos de via", f.drop(columns=[c for c in ("extra",) if c in f.columns]), "Defeitos"))
    rel = dados.get("rel")
    if rel is not None and not rel.empty:
        r = restricoes_trecho(rel)
        itens.append(("🚧 Restrições A do trecho", r[[c for c in ("a", "b", "linha", "vel", "motivo", "grupo")
                                                      if c in r.columns]], "Restricoes"))
    p = refs.get("plano")
    if p is not None and not p.empty:
        itens.append(("🎯 Plano de travamento", p, "Plano"))
    if not itens:
        st.info("Nada carregado nesta base.")
        return
    for rot, df, aba in itens:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"{rot} · {len(df):,} linhas".replace(",", "."))
        c2.download_button("📥 Excel", gerar_excel_bytes(df, aba), f"itirapina_{aba.lower()}_{data}.xlsx",
                           key=f"exp_{aba}", use_container_width=True)


def render_dados(bases: pd.DataFrame, base, dados: dict, refs: dict, pode_editar: bool) -> None:
    opcoes = (["Carregar arquivos"] if pode_editar else []) + ["Execução"] + \
        (["Metas"] if pode_editar else []) + ["Exportar"]
    sec = st.segmented_control("Seção", opcoes, default=opcoes[0], key="dados_sec",
                               label_visibility="collapsed") or opcoes[0]
    if sec == "Carregar arquivos":
        upload.render_upload(bases)
    elif sec == "Execução":
        execucao.render_execucao(refs, pode_editar)
    elif sec == "Metas":
        execucao.render_metas(refs.get("metas"))
    else:
        _exportar(dados, refs, base)
