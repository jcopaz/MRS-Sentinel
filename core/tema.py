# =============================================================================
# core/tema.py — Design System ÚNICO do MRS Sentinel (fonte única de estilo)
# Sprint UI (v3.6.0) — MRS Sentinel
#
# PROBLEMA QUE RESOLVE
# --------------------
# Antes deste arquivo, a constante COR_PRIMARIA (#1e3a5f) e suas irmãs
# (COR_CRIT, COR_WARN, COR_OK, COR_EE, COR_GOLD...) estavam COPIADAS E COLADAS
# em 7 arquivos diferentes:
#     components/kpi_card.py, components/heatmap.py, components/visao_gerencial.py,
#     components/unifilar.py, modules/alertas.py, auth/login.py, ...
# Trocar UMA cor exigia editar 7 lugares — e nada garantia que ficassem
# sincronizados (mesmo risco que motivou core/versao.py e core/glossarios.py
# a virarem "fonte única"). Aqui centralizamos TUDO: cores, sombras, raios de
# borda, espaçamentos e breakpoints de responsividade.
#
# COMO USAR
# ---------
#   from core.tema import CORES, SOMBRAS, RAIO, ESPACO, BP
#   cor = CORES["primaria"]
#   # ou, para manter compatibilidade com o código legado:
#   from core.tema import COR_PRIMARIA, COR_CRIT   # aliases exportados abaixo
#
# ⚠️ NÃO importa streamlit aqui de propósito — este módulo é PURO (só dados e
#    funções sem efeito colateral), então pode ser importado por qualquer
#    camada (core, components, modules) sem risco de dependência circular.
#
# Sessão 1: Paleta de cores (tokens semânticos)
# Sessão 2: Sombras, raios, espaçamentos, tipografia
# Sessão 3: Breakpoints de responsividade
# Sessão 4: Aliases de retrocompatibilidade (COR_PRIMARIA, ...)
# Sessão 5: Helpers (hex→rgba, cor por gerência/severidade)
# =============================================================================

from __future__ import annotations


# region ====================== SESSÃO 1: Paleta de cores ======================
# Tokens SEMÂNTICOS — nomeados pelo PAPEL, não pela cor. Assim, se um dia o
# "vermelho crítico" mudar de tom, quem consome "critico" não precisa saber.

CORES: dict[str, str] = {
    # Identidade MRS
    "primaria":   "#1e3a5f",   # azul-marinho MRS (cor-base do app)
    "primaria_2": "#2d5a8e",   # azul-marinho claro (fim de gradiente)
    "mrs_red":    "#E4002B",   # vermelho institucional MRS (uso pontual/marca)
    "gold":       "#ffb000",   # dourado Sentinel (destaques, capa, divisórias)
    "gold_2":     "#ffd04d",   # dourado claro (fim de gradiente)

    # Estados / severidade (mesma semântica de modules/alertas.py)
    "critico":    "#dc2626",   # 🔴 crítico
    "atencao":    "#f59e0b",   # 🟡 atenção
    "info":       "#2563eb",   # 🔵 informativo
    "ok":         "#16a34a",   # 🟢 concluído / saudável

    # Disciplinas (mesmo DNA da apresentação Sentinel — ver memória de design)
    "vp":         "#f59e0b",   # âmbar — Via Permanente
    "ee":         "#7c3aed",   # roxo/ciano-viés — Eletroeletrônica
    "rasf":       "#7c3aed",   # roxo — RASF/RCA
    "cronico":    "#7c3aed",   # roxo — anel de hot-spot crônico (Unifilar)

    # Neutros de interface
    "texto":       "#111827",  # texto principal
    "texto_2":     "#4b5563",  # texto secundário
    "texto_3":     "#6b7280",  # legendas/labels
    "texto_mute":  "#9ca3af",  # rodapés/hints
    "borda":       "#e5e7eb",  # bordas de card
    "borda_2":     "#d1d5db",  # bordas de input
    "fundo":       "#f8fafc",  # fundo de página claro
    "surface":     "#ffffff",  # superfície de card
    "surface_2":   "#f8fafc",  # superfície alternada (gradiente de card)
    "fundo_login": "#1b2130",  # fundo escuro da tela de login
}

# endregion


# region ============ SESSÃO 2: Sombras, raios, espaço, tipografia =============

# Elevação (sombras) — escala consistente (repouso → hover → destaque).
SOMBRAS: dict[str, str] = {
    "sm":    "0 1px 3px rgba(0,0,0,0.06)",
    "md":    "0 2px 12px rgba(0,0,0,0.06)",
    "lg":    "0 6px 20px rgba(0,0,0,0.10)",
    "hover": "0 8px 24px rgba(30,58,95,0.16)",   # card ao passar o mouse
    "focus": "0 0 0 3px rgba(30,58,95,0.12)",     # anel de foco de input
}

# Raio de borda — escala única (evita "cada card com um raio diferente").
RAIO: dict[str, str] = {
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "pill": "999px",   # badges/pílulas
}

# Espaçamento — escala de 4px (padrão de mercado; múltiplos previsíveis).
ESPACO: dict[str, str] = {
    "xs": "4px",
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "24px",
    "2xl": "32px",
}

# Tipografia — usa clamp() para escalar SOZINHA entre mobile e desktop.
# clamp(min, ideal, max): nunca menor que `min`, cresce com a viewport (vw)
# até `max`. É o coração da tipografia responsiva sem media query.
TIPO: dict[str, str] = {
    "kpi_valor":  "clamp(20px, 2.2vw, 30px)",  # número grande do KPI
    "kpi_label":  "clamp(10px, 1.0vw, 12px)",  # rótulo do KPI
    "titulo":     "clamp(18px, 2.0vw, 26px)",  # títulos de seção
    "corpo":      "clamp(13px, 1.1vw, 15px)",  # texto de corpo
    "legenda":    "clamp(11px, 0.9vw, 13px)",  # captions
}

# endregion


# region ============ SESSÃO 3: Breakpoints de responsividade ==================
# Pontos de quebra (px). Usados no CSS global (core/ui_global.py) e no helper
# de altura de gráfico. Alinhados com convenção de mercado (tablet ~768,
# desktop estreito ~1200).

BP: dict[str, int] = {
    "mobile": 768,    # <= 768px  → 1 coluna, densidade compacta
    "tablet": 1200,   # <= 1200px → 2 colunas, densidade média
    # > 1200px → layout pleno (desktop / projetor de sala de reunião)
}
BP_MOBILE = BP["mobile"]
BP_TABLET = BP["tablet"]

# endregion


# region ============ SESSÃO 4: Aliases de retrocompatibilidade ================
# Mantêm os nomes ANTIGOS funcionando, para a migração ser incremental: um
# arquivo legado pode continuar com `from core.tema import COR_PRIMARIA` sem
# reescrever nada. Ao migrar um arquivo, troque por CORES["primaria"].

COR_PRIMARIA = CORES["primaria"]
COR_PRIMARIA_2 = CORES["primaria_2"]
COR_GOLD = CORES["gold"]
COR_CRIT = CORES["critico"]
COR_WARN = CORES["atencao"]
COR_INFO = CORES["info"]
COR_OK = CORES["ok"]
COR_EE = CORES["ee"]
COR_CRONICO = CORES["cronico"]
COR_MRS_RED = CORES["mrs_red"]

# endregion


# region ====================== SESSÃO 5: Helpers ==============================

def hex_to_rgba(hex_cor: str, alpha: float = 1.0) -> str:
    """
    Converte '#1e3a5f' + alpha → 'rgba(30,58,95,0.5)'.

    Útil para Plotly (que NÃO aceita hex+alpha de 8 dígitos, ao contrário do
    ECharts). Falha graciosa: devolve a própria string se não for hex válido.
    """
    if not isinstance(hex_cor, str):
        return str(hex_cor)
    h = hex_cor.lstrip("#")
    if len(h) not in (6, 8):
        return hex_cor
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return hex_cor
    a = max(0.0, min(1.0, float(alpha)))
    return f"rgba({r},{g},{b},{a})"


def hex_alpha(hex_cor: str, alpha_byte: str = "50") -> str:
    """
    Devolve hex de 8 dígitos '#rrggbbaa' para ECharts (que aceita nativamente).
    `alpha_byte` é o par hexadecimal do canal alfa (ex.: '50'≈31%, '05'≈2%).
    """
    if not isinstance(hex_cor, str) or not hex_cor.startswith("#"):
        return str(hex_cor)
    return f"{hex_cor}{alpha_byte}"


# Cor de destaque (início, fim) de cada Gerência — ESPELHA COR_GERENCIA de
# core/glossarios.py. Fica aqui também para telas de UI que só querem o token
# de tema sem depender do glossário. Se divergir, glossarios.py é a verdade
# para lógica de negócio; tema.py é a verdade para estilo.
COR_GERENCIA: dict[str, tuple[str, str]] = {
    "SP": ("#1e3a5f", "#2d5a8e"),
    "VP": ("#0f4c35", "#1a6b4a"),
    "FN": ("#7c2d12", "#c2410c"),
    "FS": ("#713f12", "#b45309"),
    "RJ": ("#4c1d95", "#6d28d9"),
    "LC": ("#1e293b", "#475569"),
}

# Severidade → (cor, ícone, rótulo). Mesma semântica de modules/alertas.py,
# agora centralizada para reuso no componente radar_pulse e nos cards.
SEVERIDADE: dict[str, tuple[str, str, str]] = {
    "critico": (CORES["critico"], "🔴", "Crítico"),
    "atencao": (CORES["atencao"], "🟡", "Atenção"),
    "info":    (CORES["info"],    "🔵", "Informativo"),
}


def cor_severidade(sev: str) -> str:
    """Cor hex de uma severidade ('critico'/'atencao'/'info'). Fallback: info."""
    return SEVERIDADE.get(sev, SEVERIDADE["info"])[0]

# endregion
