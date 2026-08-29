# =============================================================================
# core/ui_global.py — Camada de UI global do MRS Sentinel (CSS + helpers)
# Sprint UI (v3.6.0) — MRS Sentinel
#
# O QUE É
# -------
# Um único ponto de injeção de:
#   1. CSS GLOBAL RESPONSIVO   → injetar_css_global()  (chamar 1x em app.py)
#   2. Helper de altura de gráfico responsiva → altura_responsiva()
#   3. Componente reutilizável "radar pulse" (pulso + anel concêntrico) →
#      radar_pulse_option() / render_radar_pulse()  — o "DNA do Unifilar"
#      levado para KPIs e Alertas SEM tocar em components/unifilar.py.
#
# POR QUE EXISTE
# --------------
# Auditoria do código legado (v3.5.0) encontrou:
#   • @media  = 0 ocorrências  → aplicação NÃO era responsiva;
#   • 34 alturas de gráfico HARDCODED em px  → não respiravam entre monitores;
#   • 7 blocos <style> soltos e duplicados  → sem identidade única.
# Este módulo resolve os três de uma vez, mantendo o Unifilar intocado.
#
# COMO INTEGRAR (app.py)
# ----------------------
#   from core.ui_global import injetar_css_global
#   st.set_page_config(..., layout="wide")
#   injetar_css_global()          # ← LOGO APÓS set_page_config, antes de tudo
#
# Sessão 1: CSS global responsivo
# Sessão 2: Helper de altura responsiva
# Sessão 3: Componente radar-pulse (pulso + anel)
# =============================================================================

from __future__ import annotations

import streamlit as st

# Import defensivo do tema — se por algum motivo tema.py não estiver no path
# (ambiente parcial/teste), caímos em cores mínimas para NÃO derrubar o app.
try:
    from core.tema import CORES, SOMBRAS, RAIO, BP, TIPO, hex_alpha
except Exception:  # pragma: no cover - fallback defensivo
    CORES = {"primaria": "#1e3a5f", "critico": "#dc2626", "atencao": "#f59e0b",
             "ok": "#16a34a", "ee": "#7c3aed", "cronico": "#7c3aed",
             "gold": "#ffb000", "borda": "#e5e7eb", "surface": "#ffffff",
             "surface_2": "#f8fafc", "texto": "#111827", "texto_3": "#6b7280"}
    SOMBRAS = {"md": "0 2px 12px rgba(0,0,0,0.06)",
               "hover": "0 8px 24px rgba(30,58,95,0.16)"}
    RAIO = {"md": "12px", "pill": "999px"}
    BP = {"mobile": 768, "tablet": 1200}
    TIPO = {"kpi_valor": "clamp(20px,2.2vw,30px)"}

    def hex_alpha(c, a="50"):
        return f"{c}{a}"


# region ====================== SESSÃO 1: CSS global responsivo =================

def injetar_css_global() -> None:
    """
    Injeta o CSS global do app UMA vez. Idempotente: usa uma flag em
    session_state para não reinjetar a cada rerun (evita <style> duplicado no
    DOM, que pesa e pode piscar).

    Cobre:
      • Tipografia responsiva (clamp) e suavização de fonte;
      • Cards padronizados (.mrs-card) com hover elevado;
      • GRID FLUIDO de KPIs (.mrs-kpi-grid): 4 → 2 → 1 colunas conforme a tela;
      • Media queries em BP['tablet'] e BP['mobile'];
      • Ajuste do container principal do Streamlit para telas largas (projetor)
        e estreitas (tablet), reduzindo padding lateral no mobile;
      • Animações reutilizáveis (pulse/ripple) para cards de destaque.
    """
    if st.session_state.get("_css_global_injetado"):
        return
    st.session_state["_css_global_injetado"] = True

    css = f"""
    <style>
    /* ===================== BASE / TIPOGRAFIA ===================== */
    html, body, [class*="css"] {{
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
    }}

    /* Container principal: em telas MUITO largas (projetor de reunião), limita
       a largura para o conteúdo não "esticar" e perder legibilidade; em telas
       estreitas, reduz o padding lateral para ganhar área útil. */
    [data-testid="stMainBlockContainer"] {{
        padding-top: 2.2rem !important;
        padding-left: clamp(0.8rem, 3vw, 3rem) !important;
        padding-right: clamp(0.8rem, 3vw, 3rem) !important;
        max-width: 1600px;
        margin: 0 auto;
    }}

    /* ===================== CARD PADRÃO ===================== */
    .mrs-card {{
        background: linear-gradient(145deg, {CORES.get('surface','#fff')} 0%,
                    {CORES.get('surface_2','#f8fafc')} 100%);
        border: 1px solid {CORES.get('borda','#e5e7eb')};
        border-radius: {RAIO['md']};
        box-shadow: {SOMBRAS['md']};
        padding: 16px 18px;
        transition: transform .18s ease, box-shadow .18s ease;
    }}
    .mrs-card:hover {{
        transform: translateY(-2px);
        box-shadow: {SOMBRAS['hover']};
    }}

    /* ===================== GRID FLUIDO DE KPIs ===================== */
    /* auto-fit + minmax = o navegador decide QUANTAS colunas cabem. Some a
       necessidade de st.columns(4) fixo, que espremia tudo no mobile. */
    .mrs-kpi-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 14px;
        margin: 6px 0 10px 0;
    }}

    /* ===================== BADGES / PÍLULAS ===================== */
    .mrs-badge {{
        display: inline-block;
        border-radius: {RAIO['pill']};
        padding: 2px 10px;
        font-size: 0.72rem;
        font-weight: 600;
        margin-right: 6px;
        letter-spacing: .2px;
    }}

    /* ===================== ANIMAÇÕES REUTILIZÁVEIS ===================== */
    /* Pulso suave (para KPI/alert de destaque) — mesmo espírito do
       effectScatter do Unifilar, aqui em CSS puro para cards HTML. */
    @keyframes mrsPulse {{
        0%   {{ box-shadow: 0 0 0 0 var(--mrs-pulse-color, rgba(220,38,38,.45)); }}
        70%  {{ box-shadow: 0 0 0 12px rgba(220,38,38,0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(220,38,38,0); }}
    }}
    .mrs-pulse {{ animation: mrsPulse 2.4s ease-out infinite; }}

    /* Entrada suave de card (fade + subida) — dá polish sem distrair. */
    @keyframes mrsFadeUp {{
        from {{ opacity: 0; transform: translateY(6px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}
    .mrs-fade-up {{ animation: mrsFadeUp .35s ease both; }}

    /* Barra de severidade animada (usada na tela de Alertas). */
    @keyframes mrsSweep {{
        0%   {{ background-position: 0% 50%; }}
        100% {{ background-position: 100% 50%; }}
    }}

    /* ===================== RESPONSIVIDADE ===================== */
    /* Tablet / desktop estreito */
    @media (max-width: {BP['tablet']}px) {{
        .mrs-kpi-grid {{
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
        }}
        .mrs-card {{ padding: 14px 15px; }}
    }}
    /* Mobile / tela muito estreita */
    @media (max-width: {BP['mobile']}px) {{
        [data-testid="stMainBlockContainer"] {{
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
        }}
        .mrs-kpi-grid {{ grid-template-columns: 1fr; }}
        /* Colunas do Streamlit deixam de ficar lado a lado e empilham,
           evitando o "esmagamento" de st.columns([1.2,1.2,1.2,1.4]). */
        [data-testid="stHorizontalBlock"] {{
            flex-wrap: wrap !important;
        }}
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
            min-width: 100% !important;
        }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Altura responsiva =====================

def altura_responsiva(base: int = 400, min_px: int = 260,
                      max_px: int = 640) -> str:
    """
    Devolve uma string de altura para `st_echarts(height=...)` que ESCALA com
    a viewport — substitui os `height="320px"` fixos espalhados pelo código.

    Estratégia: usa CSS clamp() em vez de px cru. O ECharts aceita qualquer
    string CSS de comprimento válida, então passamos 'clamp(min, ideal, max)':
      • em telas baixas (notebook), o gráfico não estoura a dobra;
      • em telas altas (monitor 4K / projetor), ele aproveita o espaço.

    `base` vira o "ideal" proporcional à altura da viewport (vh). Regra prática:
      base 400 → ~48vh;  base 560 → ~62vh.  Ajuste fino com min_px/max_px.

    Ex.: st_echarts(opt, height=altura_responsiva(320))  # antes: height="320px"
    """
    # Converte a altura-base em fração de vh de forma suave e limitada.
    vh = max(30, min(80, round(base / 8.3)))   # 320→39vh, 400→48vh, 560→67vh
    return f"clamp({min_px}px, {vh}vh, {max_px}px)"

# endregion


# region ============ SESSÃO 3: Componente radar-pulse (reutilizável) ==========
# Leva o "DNA visual do Unifilar" (pulso + anel concêntrico) para QUALQUER tela
# — KPIs, Alertas — sem importar nem alterar components/unifilar.py. É uma
# reimplementação independente e enxuta do mesmo effectScatter + aro vazado.

def radar_pulse_option(cor: str | None = None,
                       com_anel_cronico: bool = False,
                       label: str = "") -> dict:
    """
    Monta um `option` mínimo de ECharts com um ÚNICO ponto central que pulsa
    (effectScatter, rippleEffect) — um "radar" decorativo para usar dentro de
    um card de KPI ou de alerta crítico.

    Args:
        cor: cor do pulso (default: crítico). Aceita hex '#rrggbb'.
        com_anel_cronico: se True, adiciona um aro vazado roxo ao redor
            (mesma linguagem do anel crônico do Unifilar).
        label: texto opcional exibido no tooltip.

    Retorna um dict pronto para `st_echarts(option, ...)`.

    ⚠️ Este componente NÃO substitui o Unifilar — é uma peça decorativa/indicadora
       independente. O Unifilar (components/unifilar.py) permanece intocado.
    """
    cor = cor or CORES.get("critico", "#dc2626")
    series = []

    # Anel concêntrico crônico (aro vazado) — desenhado ATRÁS do pulso.
    if com_anel_cronico:
        series.append({
            "type": "scatter", "silent": True, "z": 1,
            "data": [{"value": [0, 0], "symbolSize": 46}],
            "itemStyle": {
                "color": "rgba(0,0,0,0)",
                "borderColor": CORES.get("cronico", "#7c3aed"),
                "borderWidth": 3,
                "shadowBlur": 6,
                "shadowColor": "rgba(124,58,237,0.5)",
            },
            "tooltip": {"show": False},
        })

    # Pulso central — effectScatter com o MESMO ritmo do Unifilar (period=3,
    # scale=2.8, brushType=stroke) para manter coerência de linguagem.
    series.append({
        "type": "effectScatter", "z": 2,
        "data": [{"value": [0, 0], "symbolSize": 26}],
        "rippleEffect": {"period": 3, "scale": 2.8, "brushType": "stroke"},
        "showEffectOn": "render",
        "itemStyle": {"color": cor, "borderColor": "#fff", "borderWidth": 2},
        "tooltip": {"show": bool(label), "formatter": label} if label
                   else {"show": False},
    })

    return {
        "animation": True,
        "grid": {"left": 0, "right": 0, "top": 0, "bottom": 0},
        "xAxis": {"show": False, "min": -1, "max": 1},
        "yAxis": {"show": False, "min": -1, "max": 1},
        "series": series,
    }


def render_radar_pulse(cor: str | None = None, com_anel_cronico: bool = False,
                       altura: int = 70, key: str = "radar") -> None:
    """
    Renderiza o radar-pulse. Falha graciosa: se streamlit-echarts não estiver
    instalado, não quebra a tela (só não desenha o pulso).
    """
    try:
        from streamlit_echarts import st_echarts
    except Exception:
        return
    st_echarts(radar_pulse_option(cor, com_anel_cronico),
               height=f"{altura}px", key=key)

# endregion
