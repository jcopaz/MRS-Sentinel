# =============================================================================
# core/exportacao.py — Geração de Excel/CSV cacheada (fonte única)
# Perf 2026-08-30 — MRS Sentinel
#
# Antes, cada tela com um "Baixar Excel/CSV" gerava o arquivo do ZERO em
# TODO rerun da página, mesmo sem ninguém clicar em baixar (st.download_button
# exige os bytes prontos no momento da renderização — não tem geração
# preguiçosa nativa). Cacheado por CONTEÚDO do DataFrame: só reserializa
# quando o recorte de dados realmente muda.
#
# Usado por components/unifilar.py e components/visao_gerencial.py — evita
# duplicar a mesma lógica de ExcelWriter/to_csv em cada tela.
# =============================================================================

from io import BytesIO

import streamlit as st
import pandas as pd


@st.cache_data(ttl=300, show_spinner=False)
def gerar_excel_bytes(df: pd.DataFrame, sheet_name: str = "Dados") -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()


@st.cache_data(ttl=300, show_spinner=False)
def gerar_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")
