# =============================================================================
# modules/itirapina/exportar_onepage.py — Botões 🖼️ PNG · 📄 PDF · 📊 PPTX
#
# Geração sob demanda (o render matplotlib leva alguns segundos): o botão
# "Preparar" monta os 3 arquivos e guarda em session_state; os download
# buttons aparecem em seguida. Motor: core/onepage_render.py.
# =============================================================================

import streamlit as st

from core.onepage_render import nome_arquivo, para_pdf, para_png, para_pptx


def botoes_exportar(o: dict) -> None:
    chave = f"onepage_arq_{o['modo']}_{o['data_atual']}"
    c = st.columns([1.4, 1, 1, 1, 3])
    if c[0].button("📤 Preparar exportação", key="op_prep",
                   help="Gera PNG, PDF e PPTX da One Page (A4 paisagem)."):
        with st.spinner("Desenhando a One Page..."):
            png = para_png(o)
            st.session_state[chave] = {"png": png, "pdf": para_pdf(o), "pptx": para_pptx(o, png)}
    arq = st.session_state.get(chave)
    if not arq:
        c[4].caption("Exporta a mesma peça desta tela em um clique.")
        return
    c[1].download_button("🖼️ PNG", arq["png"], nome_arquivo(o, "png"), "image/png", key="op_png")
    c[2].download_button("📄 PDF", arq["pdf"], nome_arquivo(o, "pdf"), "application/pdf", key="op_pdf")
    c[3].download_button("📊 PPTX", arq["pptx"], nome_arquivo(o, "pptx"),
                         "application/vnd.openxmlformats-officedocument.presentationml.presentation", key="op_pptx")
