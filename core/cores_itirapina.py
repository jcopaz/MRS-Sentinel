# =============================================================================
# core/cores_itirapina.py — Paleta única do trecho Itirapina–Pederneiras
#
# Usada pelo app (Plotly) e pela exportação (matplotlib) para que tela e
# One Page tenham as mesmas cores.
# =============================================================================

# Faixas do slide "Mapa de calor" (taxa de inservíveis): até 10 / 10–20 /
# 20–30 / 30–40 / > 40 %, verde → vinho.
LIMIARES_SLIDE = (10.0, 20.0, 30.0, 40.0)
CORES_SLIDE = ("#16a34a", "#a3e635", "#facc15", "#f97316", "#7f1d1d")
LIMIARES_META20 = (20.0,)
CORES_META20 = ("#16a34a", "#dc2626")

# Grupos de restrição (regra de ouro: mérito da Manutenção × terceiros)
VIA = "#dc2626"           # restrição de via — a Manutenção resolve
ANTT = "#f59e0b"          # ANTT / PN / perímetro urbano — depende de terceiros
RETIRADA = "#16a34a"      # retirada desde o marco zero
NEUTRO = "#64748b"

SITUACAO = {"concluído": "#16a34a", "em curso": "#f59e0b", "a iniciar": "#cbd5e1"}
AZUL = "#1e3a5f"
LARANJA = "#b45309"


def cor_por_faixa(valor, limiares, cores) -> str:
    """len(cores) == len(limiares) + 1; valor ≤ limiar[i] → cores[i]."""
    if valor is None or valor != valor:  # NaN
        return "#e5e7eb"
    for lim, cor in zip(limiares, cores):
        if valor <= lim:
            return cor
    return cores[-1]
