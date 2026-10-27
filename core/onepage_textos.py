# =============================================================================
# core/onepage_textos.py — Frases automáticas da One Page
#
# Modelos com placeholders. Regra: só entra a frase cujo número é FAVORÁVEL e
# passa do limiar mínimo (não "vender" ganho insignificante). Número que
# piorou NUNCA vira frase — aparece só no card, em vermelho (a transparência
# fica nos cards). Sem nenhuma frase favorável, entram as frases do plano
# (modo "Ponto de partida").
# =============================================================================


def _n(v, casas=0) -> str:
    """Número no formato brasileiro (1.234,5); ausente → '—'."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v != v:  # NaN
        return "—"
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def frases_evolucao(d: dict, base: dict) -> list[str]:
    """
    d: indicadores derivados (core/indicadores_trecho.derivados).
    base: valores de referência {'restricoes_via_mz', 'vma_atual', 'taxa_mz', 'taxa_atual',
          'vagao_mz', 'vagao_atual', 'pontos_total'}.
    """
    out = []
    n = d.get("via_retiradas", 0)
    km = d.get("km_liberados", 0) or 0
    if n >= 1:
        txt = f"Retiramos **{n}** das {base.get('restricoes_via_mz', 14)} restrições de via"
        if km >= 0.1 and base.get("vma_atual"):
            txt += f": **{_n(km, 1)} km** voltaram para {_n(base['vma_atual'])} km/h."
        out.append(txt + ("" if txt.endswith(".") else "."))
    m = d.get("minutos_ganhos", 0) or 0
    if m >= 1:
        txt = f"Cada trem ganha **{_n(m)} min** no trecho"
        h = d.get("horas_mes")
        out.append(txt + (f", o que soma **{_n(h)} h de trem por mês** devolvidas à circulação." if h and h >= 1
                          else "."))
    p = d.get("travamento_pct", 0) or 0
    if p >= 5:
        out.append(f"O trecho está **{_n(p)}% travado**: {d.get('pontos_concluidos', 0)} dos "
                   f"{base.get('pontos_total', 7)} pontos críticos concluídos.")
    a, b = base.get("taxa_mz"), base.get("taxa_atual")
    if a is not None and b is not None and a - b >= 1:
        out.append(f"A taxa de dormentes inservíveis caiu de **{_n(a, 1)}%** para **{_n(b, 1)}%**.")
    e = d.get("defeitos_eliminados", 0) or 0
    if e >= 50:
        out.append(f"**{_n(e)}** defeitos de via eliminados desde o marco zero.")
    va, vb = base.get("vagao_mz"), base.get("vagao_atual")
    if va is not None and vb is not None and va - vb >= 3:
        out.append(f"Pontos do Vagão de Via que pedem < 35 km/h sem restrição: **{_n(va)} → {_n(vb)}**.")
    return out[:3]


def frases_plano(plano: dict) -> list[str]:
    return [
        f"**{plano.get('pontos', 7)} pontos críticos** e **{_n(plano.get('travamento', 4645))} dormentes** "
        "de travamento definem o plano do 1º ano.",
        f"**{plano.get('restricoes_via', 14)} restrições de via** a retirar — as "
        f"{plano.get('restricoes_antt', 16)} de ANTT/PN/perímetro urbano dependem de terceiros.",
        f"**{plano.get('vagao', 52)} pontos** do Vagão de Via pedem < 35 km/h sem restrição: "
        "prioridade de segurança.",
    ]


def sem_markdown(txt: str) -> str:
    return txt.replace("**", "")
