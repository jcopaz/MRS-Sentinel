# core/ui_evolucao.py — Cartões de KPI com seta ▲▼ (A × B)
#
# Extraído de modules/evolucao_malha.py para ser compartilhado com a aba
# Itirapina–Pederneiras (subaba Evolução). A cor da seta segue o SENTIDO BOM
# de cada indicador: "menor_melhor" (subir = vermelho), "maior_melhor"
# (subir = verde) ou "neutro" (sempre cinza).

import pandas as pd
import streamlit as st

COR_PRIMARIA = "#1e3a5f"
COR_OK = "#16a34a"
COR_RUIM = "#dc2626"
COR_NEUTRO = "#6b7280"


def fmt_valor(valor, formato) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "—"
    if formato == "int":
        return f"{int(round(valor)):,}".replace(",", ".")
    if formato == "pct":
        return f"{valor:.1f}%"
    if formato == "h":
        return f"{valor:.1f} h"
    if formato == "kmh":
        return f"{valor:.1f} km/h"
    if formato == "min":
        return f"{valor:.0f} min"
    if formato == "m":
        return f"{valor:,.0f} m".replace(",", ".")
    if formato == "dec":
        return f"{valor:.1f}"
    return f"{valor:.2f}"


def delta_html(atual, anterior, sentido, formato) -> str:
    """Seta ▲▼ colorida conforme melhora/piora."""
    if atual is None or anterior is None or pd.isna(atual) or pd.isna(anterior):
        return f"<span style='color:{COR_NEUTRO};font-size:0.8rem;'>—</span>"
    diff = atual - anterior
    if abs(diff) < 1e-9:
        return f"<span style='color:{COR_NEUTRO};font-size:0.8rem;'>▬ 0</span>"
    subiu = diff > 0
    if sentido == "neutro":
        cor = COR_NEUTRO
    else:
        bom = (subiu and sentido == "maior_melhor") or (not subiu and sentido == "menor_melhor")
        cor = COR_OK if bom else COR_RUIM
    seta = "▲" if subiu else "▼"
    val = fmt_valor(abs(diff), formato)
    return (f"<span style='color:{cor};font-size:0.8rem;font-weight:700;'>"
            f"{seta} {val}</span>")


def card_kpi(rotulo, atual, anterior, sentido, formato, legenda: str | None = None) -> str:
    extra = (f"<div style='font-size:0.7rem;color:{COR_NEUTRO};margin-top:2px;'>{legenda}</div>"
             if legenda else "")
    return (f"<div style='border:1px solid #e5e7eb;border-radius:10px;"
            f"padding:10px 12px;margin-bottom:8px;background:#fff;'>"
            f"<div style='font-size:0.72rem;color:{COR_NEUTRO};"
            f"text-transform:uppercase;letter-spacing:.5px;'>{rotulo}</div>"
            f"<div style='font-size:1.5rem;font-weight:800;"
            f"color:{COR_PRIMARIA};line-height:1.2;'>{fmt_valor(atual, formato)}</div>"
            f"{delta_html(atual, anterior, sentido, formato)}{extra}"
            f"</div>")


def bloco_cards(itens: list[tuple], colunas: int = 4) -> None:
    """itens = [(rótulo, atual, anterior, sentido, formato[, legenda]), ...]"""
    cols = st.columns(colunas)
    for i, item in enumerate(itens):
        with cols[i % colunas]:
            st.markdown(card_kpi(*item), unsafe_allow_html=True)
