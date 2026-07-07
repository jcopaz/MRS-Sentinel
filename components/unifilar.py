# =============================================================================
# components/unifilar.py — Unifilar Dual VP + EE com ECharts
# Sprint 3 (rev.3) — MRS Sentinel
#
# Usa streamlit-echarts com:
#   • effectScatter  — bolhas pulsantes/irradiantes para hot-spots críticos
#   • scatter        — bolhas normais para demais pontos
#   • line           — trilhos VP (superior) e EE (inferior)
#   • dataZoom       — zoom deslizante (slider + scroll do mouse)
#   • tooltip rico   — nome completo, qtd, score, lead time, top defeitos
#
# Controles acima do gráfico:
#   • Nível de detalhe: Ramal | Pátio | Trecho
#   • Multiselect de ramais (nome completo)
#   • Checkbox "Só críticos"
#
# Sessão 1: Imports & constantes
# Sessão 2: Funções de agregação
# Sessão 3: Posicionamento x
# Sessão 4: Conversão para formato ECharts
# Sessão 5: Construção do option ECharts
# Sessão 6: Ponto de entrada render_unifilar_dual()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
import numpy as np

try:
    from streamlit_echarts import st_echarts
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

import plotly.graph_objects as go  # fallback se echarts ausente

from core.glossarios import nome_ramal, RAMAIS_MRS, normalizar_coluna_ramal

# Paleta MRS
COR_VP      = "#1e3a5f"   # azul-marinho — trilho Via Permanente
COR_EE      = "#7c3aed"   # roxo — trilho Eletroeletrônica
COR_GOLD    = "#ffb000"   # dourado MRS
COR_CRIT    = "#dc2626"   # vermelho — score crítico
COR_WARN    = "#f59e0b"   # amarelo — score atenção
COR_OK      = "#16a34a"   # verde — score normal
COR_BG      = "#f8fafc"   # fundo

# Posições Y das duas lanes
Y_VP    =  1.0   # trilho superior (Via Permanente)
Y_EE    = -1.0   # trilho inferior (Eletroeletrônica)
Y_GERAL =  0.0   # linha central (modo combinado)

# Limiar de criticidade: notas acima do percentil 75 do score
PERCENTIL_CRITICO = 0.75

# endregion


# region ====================== SESSÃO 2: Funções de agregação =================

def _top3_str(serie: pd.Series) -> str:
    """Retorna os 3 defeitos mais frequentes separados por quebra de linha."""
    vc = serie.dropna().value_counts().head(3)
    if vc.empty:
        return "—"
    return "\n".join(f"• {d}" for d in vc.index)


def _agregar(df: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """
    Agrega o DataFrame no nível escolhido.

    Colunas produzidas:
        chave, label, ramal_sigla, disciplina, qtd,
        score_med, lt_med, top_defeitos, y_pos, critico
    """
    if df.empty:
        return pd.DataFrame()

    # Define coluna de agrupamento
    if nivel == "Ramal":
        col_chave = "ramal"
    elif nivel == "Pátio":
        col_chave = "origem"
    else:
        # Trecho = par Origem→Destino
        if "origem" in df.columns and "destino" in df.columns:
            df = df.copy()
            df["_trecho"] = (
                df["origem"].fillna("?") + "→" + df["destino"].fillna("?")
            )
            col_chave = "_trecho"
        else:
            col_chave = "trecho" if "trecho" in df.columns else "origem"

    if col_chave not in df.columns:
        return pd.DataFrame()

    disc_col = "disciplina_label" if "disciplina_label" in df.columns else None
    group_cols = [col_chave] + ([disc_col] if disc_col else [])

    # Coluna de contagem
    cnt_col = "numero_nota" if "numero_nota" in df.columns else col_chave

    agg = (
        df.groupby(group_cols, dropna=False)
        .agg(
            qtd        =(cnt_col,           "count"),
            score_med  =("score",           "mean")         if "score"           in df.columns else (col_chave, lambda x: 0),
            lt_med     =("lead_time_dias",   "mean")        if "lead_time_dias"  in df.columns else (col_chave, lambda x: 0),
            ramal_sigla=("ramal",           "first")        if "ramal"           in df.columns else (col_chave, "first"),
            top_defeitos=("defeito_legivel", _top3_str)     if "defeito_legivel" in df.columns else (col_chave, lambda x: "—"),
        )
        .reset_index()
        .rename(columns={col_chave: "chave"})
    )

    # Label legível
    if nivel == "Ramal":
        agg["label"] = agg["chave"].apply(lambda s: nome_ramal(str(s), "completo_sigla"))
    else:
        agg["label"] = agg["chave"].fillna("?").astype(str)

    # Lane Y por disciplina
    if disc_col and disc_col in agg.columns:
        agg["y_pos"]     = agg[disc_col].map({"VP": Y_VP, "EE": Y_EE}).fillna(Y_GERAL)
        agg["disciplina"] = agg[disc_col]
    else:
        agg["y_pos"]     = Y_GERAL
        agg["disciplina"] = "VP+EE"

    # Limpa numéricos
    agg["score_med"] = pd.to_numeric(agg["score_med"], errors="coerce").fillna(0)
    agg["lt_med"]    = pd.to_numeric(agg["lt_med"],    errors="coerce").fillna(0)

    # Flag crítico: score acima do percentil 75
    limiar = agg["score_med"].quantile(PERCENTIL_CRITICO) if agg["score_med"].max() > 0 else 0
    agg["critico"] = agg["score_med"] >= limiar

    return agg

# endregion


# region ====================== SESSÃO 3: Posicionamento x ====================

def _posicionar_x(agg: pd.DataFrame, nivel: str) -> pd.DataFrame:
    """
    Atribui posição x sequencial respeitando a ordem canônica dos ramais.
    Adiciona gap de 1.5 entre ramais diferentes nos níveis Pátio/Trecho.
    """
    if agg.empty:
        return agg

    agg = agg.copy()
    ordem_ramais = list(RAMAIS_MRS.keys())

    def _rank(sigla):
        try:
            return ordem_ramais.index(str(sigla).strip().upper())
        except ValueError:
            return len(ordem_ramais)

    agg["_ord"] = agg["ramal_sigla"].apply(_rank)

    if nivel == "Ramal":
        agg = agg.sort_values(["_ord", "disciplina"]).reset_index(drop=True)
        # Mesma posição x para VP e EE do mesmo ramal (aparecem em lanes diferentes)
        ramais_unicos = list(dict.fromkeys(agg["chave"].tolist()))
        pos_x = {r: i * 2.5 for i, r in enumerate(ramais_unicos)}
        agg["x_pos"] = agg["chave"].map(pos_x)
    else:
        agg = agg.sort_values(["_ord", "chave", "disciplina"]).reset_index(drop=True)
        x, ramal_ant = 0.0, None
        posicoes = []
        for _, row in agg.iterrows():
            if ramal_ant is not None and row["ramal_sigla"] != ramal_ant:
                x += 1.5  # gap visual entre ramais
            posicoes.append(x)
            x += 1.0
            ramal_ant = row["ramal_sigla"]
        agg["x_pos"] = posicoes

    return agg

# endregion


# region ====================== SESSÃO 4: Formato ECharts =====================

def _score_para_cor(score: float, score_max: float) -> str:
    """Interpola cor hex entre verde e vermelho pelo score relativo."""
    if score_max == 0:
        return COR_OK
    t = min(score / score_max, 1.0)
    if t < 0.5:
        r = int(22  + (t * 2) * (245 - 22))
        g = int(163 + (t * 2) * (158 - 163))
        b = int(74  + (t * 2) * (11  - 74))
    else:
        t2 = (t - 0.5) * 2
        r = int(245 + t2 * (220 - 245))
        g = int(158 + t2 * (38  - 158))
        b = int(11  + t2 * (38  - 11))
    return f"#{r:02x}{g:02x}{b:02x}"


def _tamanho_bolha(qtd: int, qtd_max: int,
                   min_size: int = 14, max_size: int = 55) -> int:
    """Normaliza tamanho da bolha entre min_size e max_size."""
    if qtd_max == 0:
        return min_size
    return int(min_size + (qtd / qtd_max) * (max_size - min_size))


def _ponto_echarts(row: pd.Series, score_max: float, qtd_max: int) -> dict:
    """
    Converte uma linha do DataFrame agregado para o formato de ponto ECharts.
    Usado tanto em scatter quanto em effectScatter.
    """
    cor = _score_para_cor(row["score_med"], score_max)
    tam = _tamanho_bolha(int(row["qtd"]), qtd_max)

    tooltip_txt = (
        f"{row['label']}\n"
        f"Disciplina: {row['disciplina']}\n"
        f"📌 Notas: {int(row['qtd']):,}\n"
        f"⚡ Score médio: {row['score_med']:.1f}\n"
        f"⏱️ Lead time: {row['lt_med']:.0f} dias\n"
        f"─────────────\n"
        f"Top defeitos:\n{row['top_defeitos']}"
    )

    return {
        "value":  [float(row["x_pos"]), float(row["y_pos"]), float(row["score_med"])],
        "name":   row["label"],
        "symbol": "circle",
        "symbolSize": tam,
        "itemStyle": {"color": cor, "borderColor": "#ffffff", "borderWidth": 2},
        "label": {
            "show":     True,
            "position": "bottom",
            "formatter": row["label"][:18] + ("…" if len(row["label"]) > 18 else ""),
            "fontSize": 9,
            "color":   "#374151",
        },
        "_tooltip": tooltip_txt,  # campo auxiliar (não usado pelo ECharts diretamente)
    }

# endregion


# region ====================== SESSÃO 5: Construção do option ECharts =========

def _trilhos_echarts(agg: pd.DataFrame) -> list:
    """
    Gera as séries de linhas que representam os trilhos VP e EE.
    Conecta os pontos de cada lane em ordem de x_pos.
    """
    series = []
    for lane_disc, y_val, cor_linha, nome_lane in [
        ("VP",    Y_VP,    COR_VP, "Trilho VP"),
        ("EE",    Y_EE,    COR_EE, "Trilho EE"),
        ("VP+EE", Y_GERAL, "#94a3b8", "Trilho"),
    ]:
        sub = agg[agg["y_pos"] == y_val].sort_values("x_pos")
        if sub.empty:
            continue
        series.append({
            "type": "line",
            "name": nome_lane,
            "data": [[float(r["x_pos"]), float(r["y_pos"])] for _, r in sub.iterrows()],
            "symbol": "none",
            "lineStyle": {"color": cor_linha, "width": 3, "type": "solid"},
            "z": 1,
            "silent": True,
            "legend": {"show": False},
        })
    return series


def _construir_option(agg: pd.DataFrame, gerencia: str, nivel: str) -> dict:
    """
    Monta o dict completo do option ECharts.

    Lógica de separação:
    - Pontos críticos (flag critico=True)  → effectScatter (pulsante)
    - Pontos normais  (flag critico=False) → scatter (estático)
    - Trilhos VP e EE                      → line
    """
    if agg.empty:
        return {
            "graphic": [{
                "type": "text",
                "left": "center", "top": "middle",
                "style": {"text": "Sem dados para exibir", "fontSize": 16, "fill": "#6b7280"},
            }]
        }

    score_max = agg["score_med"].max() if agg["score_med"].max() > 0 else 1.0
    qtd_max   = int(agg["qtd"].max())  if agg["qtd"].max()   > 0 else 1

    criticos = agg[agg["critico"]].copy()
    normais  = agg[~agg["critico"]].copy()

    # Dados para as séries
    dados_criticos = [_ponto_echarts(r, score_max, qtd_max) for _, r in criticos.iterrows()]
    dados_normais  = [_ponto_echarts(r, score_max, qtd_max) for _, r in normais.iterrows()]

    # Limites do eixo X
    x_min = float(agg["x_pos"].min()) - 1.5
    x_max = float(agg["x_pos"].max()) + 1.5

    series = []

    # ── Trilhos (linhas) ──────────────────────────────────────────────────────
    series.extend(_trilhos_echarts(agg))

    # ── Scatter normal (pontos não críticos) ──────────────────────────────────
    if dados_normais:
        series.append({
            "type":      "scatter",
            "name":      "Normal",
            "data":      dados_normais,
            "z":         3,
            "emphasis":  {"scale": 1.3},
        })

    # ── effectScatter (hot-spots pulsantes) ───────────────────────────────────
    if dados_criticos:
        series.append({
            "type": "effectScatter",
            "name": "🔴 Hot-spot crítico",
            "data": dados_criticos,
            "z":    4,
            "showEffectOn": "render",       # pulsa sempre
            "rippleEffect": {
                "brushType": "stroke",      # anel irradiante
                "scale":     3.5,           # tamanho do pulso
                "period":    3,             # velocidade (segundos)
                "color":     COR_CRIT,
            },
            "emphasis": {"scale": 1.4},
        })

    titulo_nivel = {"Ramal": "por Ramal", "Pátio": "por Pátio", "Trecho": "por Trecho"}

    option = {
        "backgroundColor": COR_BG,
        "title": {
            "text":    f"Unifilar Dual VP+EE — {titulo_nivel.get(nivel, '')}",
            "subtext": f"Gerência {gerencia} · 🔴 Pulsante = hot-spot crítico (top 25% score)",
            "left":    "left",
            "textStyle":    {"color": "#1f2937", "fontSize": 14, "fontWeight": "bold"},
            "subtextStyle": {"color": "#6b7280", "fontSize": 11},
        },
        "tooltip": {
            "trigger":         "item",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor":     COR_VP,
            "borderWidth":     2,
            "padding":         [10, 14],
            "extraCssText":    "box-shadow:0 6px 20px rgba(0,0,0,0.15);border-radius:10px;",
            "textStyle":       {"color": "#1f2937", "fontSize": 12},
            # Formatter em JS — exibe o campo 'name' + values formatados
            "formatter": """function(p){
                if(!p.data || !p.value) return p.name || '';
                var d = p.data;
                var lines = [
                    '<b>' + (d.name||'') + '</b>',
                ];
                if(d._tooltip){
                    lines = lines.concat(d._tooltip.split('\\n'));
                }
                return lines.join('<br/>');
            }""",
        },
        "legend": {
            "data":   ["Normal", "🔴 Hot-spot crítico"],
            "bottom": 0,
            "textStyle": {"color": "#374151", "fontSize": 11},
        },
        "grid": {
            "left":         "8%",
            "right":        "5%",
            "top":          "15%",
            "bottom":       "18%",
            "containLabel": False,
        },
        "xAxis": {
            "type":        "value",
            "min":          x_min,
            "max":          x_max,
            "show":         False,
            "axisLine":     {"show": False},
            "splitLine":    {"show": False},
        },
        "yAxis": {
            "type":      "value",
            "min":       -2.2,
            "max":        2.2,
            "show":       False,
            "axisLine":  {"show": False},
            "splitLine": {"show": False},
        },
        # ── dataZoom: zoom horizontal (simula km quando há coordenadas reais) ──
        "dataZoom": [
            {
                "type":       "slider",          # barra deslizante abaixo do gráfico
                "xAxisIndex": 0,
                "start":      0,
                "end":        100,
                "height":     18,
                "bottom":     "8%",
                "borderColor": "#e5e7eb",
                "fillerColor": "rgba(30,58,95,0.15)",
                "handleStyle": {"color": COR_VP},
                "textStyle":   {"color": "#6b7280"},
                "labelFormatter": "",            # sem labels numéricos (eixo oculto)
            },
            {
                "type":       "inside",          # zoom com scroll do mouse
                "xAxisIndex": 0,
                "start":      0,
                "end":        100,
            },
        ],
        # Labels fixos de lane (VP / EE)
        "graphic": _labels_lane(agg, x_min),
        "series":  series,
        "animation": True,
        "animationDuration": 800,
    }

    return option


def _labels_lane(agg: pd.DataFrame, x_min: float) -> list:
    """
    Renderiza os labels fixos 'VP' e 'EE' no lado esquerdo do gráfico.
    Usa coordenadas de data (não de pixel) para alinhar com as lanes.
    """
    labels = []

    if agg["y_pos"].isin([Y_VP]).any():
        labels.append({
            "type": "text",
            "left": "2%", "top": "28%",
            "style": {
                "text":        "VP",
                "fontSize":    13,
                "fontWeight":  "bold",
                "fill":        COR_VP,
            },
        })

    if agg["y_pos"].isin([Y_EE]).any():
        labels.append({
            "type": "text",
            "left": "2%", "top": "62%",
            "style": {
                "text":       "EE",
                "fontSize":   13,
                "fontWeight": "bold",
                "fill":       COR_EE,
            },
        })

    return labels

# endregion


# region ====================== SESSÃO 6: Ponto de entrada ====================

def _fallback_plotly(agg: pd.DataFrame, gerencia: str, nivel: str):
    """
    Renderização alternativa em Plotly quando streamlit-echarts não está instalado.
    Mantém a mesma lógica de aggregação e cores, sem o efeito de pulso.
    """
    import plotly.graph_objects as go

    def _hex_rgba(h, a=0.15):
        h = h.lstrip("#")
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        return f"rgba({r},{g},{b},{a})"

    score_max = agg["score_med"].max() or 1.0
    qtd_max   = int(agg["qtd"].max()) or 1

    fig = go.Figure()

    # Trilhos
    for y_val, cor, nome in [(Y_VP, COR_VP, "VP"), (Y_EE, COR_EE, "EE")]:
        sub = agg[agg["y_pos"] == y_val].sort_values("x_pos")
        if not sub.empty:
            fig.add_trace(go.Scatter(
                x=sub["x_pos"], y=[y_val]*len(sub), mode="lines",
                line=dict(color=cor, width=3), name=f"Trilho {nome}", hoverinfo="skip",
            ))

    # Bolhas
    for is_crit, marker_sym in [(False, "circle"), (True, "circle-open")]:
        sub = agg[agg["critico"] == is_crit]
        if sub.empty:
            continue
        cores = [_score_para_cor(s, score_max) for s in sub["score_med"]]
        sizes = [_tamanho_bolha(int(q), qtd_max) for q in sub["qtd"]]
        fig.add_trace(go.Scatter(
            x=sub["x_pos"], y=sub["y_pos"], mode="markers+text",
            marker=dict(size=sizes, color=cores, symbol=marker_sym,
                        line=dict(color="white", width=2), opacity=0.9),
            text=sub["label"].apply(lambda s: s[:18]+"…" if len(s)>18 else s),
            textposition="bottom center", textfont=dict(size=9),
            name="🔴 Crítico" if is_crit else "Normal", hoverinfo="text",
            hovertext=[
                f"<b>{r['label']}</b><br>📌 {int(r['qtd']):,} notas<br>"
                f"⚡ Score: {r['score_med']:.1f}<br>⏱️ {r['lt_med']:.0f} dias"
                for _, r in sub.iterrows()
            ],
        ))

    fig.update_layout(
        height=420, plot_bgcolor=COR_BG, paper_bgcolor="white",
        xaxis=dict(visible=False), yaxis=dict(visible=False, range=[-2.2, 2.2]),
        margin=dict(l=60, r=20, t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("⚠️ streamlit-echarts não instalado — usando Plotly (sem animação)")


def render_unifilar_dual(df: pd.DataFrame, gerencia: str = "SP"):
    """
    Ponto de entrada do Unifilar Dual VP+EE.

    Exibe ECharts com effectScatter (pulsante) para hot-spots críticos.
    Fallback automático para Plotly se streamlit-echarts não estiver instalado.

    Controles:
        • Nível de detalhe — Ramal (padrão) | Pátio | Trecho
        • Multiselect de ramais — nome completo (ANTT/MRS)
        • Checkbox — Só críticos

    Args:
        df: DataFrame filtrado com score calculado
        gerencia: 'SP', 'VP' ou 'GERAL'
    """
    if df.empty:
        st.info("ℹ️ Sem dados para o unifilar. Faça upload de planilhas primeiro.")
        return

    # ── Controles acima do gráfico ───────────────────────────────────────────
    col_niv, col_ram, col_crit = st.columns([1, 3, 1])

    with col_niv:
        nivel = st.selectbox(
            "🔎 Detalhe",
            ["Ramal", "Pátio", "Trecho"],
            index=0,
            key=f"unif_nivel_{gerencia}",
            help="Ramal = visão ampla · Pátio = por estação · Trecho = máximo detalhe",
        )

    with col_ram:
        if "ramal" in df.columns:
            siglas_disp = sorted(df["ramal"].dropna().unique().tolist())
        else:
            siglas_disp = []

        opcoes_label = {nome_ramal(s, "completo_sigla"): s for s in siglas_disp}

        selecionados_nome = st.multiselect(
            "🚂 Ramais visíveis",
            options=list(opcoes_label.keys()),
            default=list(opcoes_label.keys()),
            key=f"unif_ramais_{gerencia}",
            help="Desmarque ramais para removê-los do unifilar",
        )
        ramais_sel = [opcoes_label[n] for n in selecionados_nome if n in opcoes_label]

    with col_crit:
        apenas_criticos = st.checkbox(
            "🔴 Só críticos",
            value=False,
            key=f"unif_crit_{gerencia}",
            help="Mostra apenas hot-spots (score top 25%)",
        )

    # ── Filtra DataFrame ─────────────────────────────────────────────────────
    df_plot = df.copy()
    if ramais_sel and "ramal" in df_plot.columns:
        df_plot = df_plot[df_plot["ramal"].isin(ramais_sel)]

    if df_plot.empty:
        st.warning("Nenhum dado com os ramais selecionados.")
        return

    if apenas_criticos and "score" in df_plot.columns:
        lim = df_plot["score"].quantile(PERCENTIL_CRITICO)
        df_plot = df_plot[df_plot["score"] >= lim]
        if df_plot.empty:
            st.info("Sem hot-spots críticos com os filtros aplicados.")
            return

    # ── Agrega e posiciona ───────────────────────────────────────────────────
    agg = _agregar(df_plot, nivel)
    if agg.empty:
        st.warning("Dados insuficientes para montar o unifilar.")
        return

    agg = _posicionar_x(agg, nivel)

    # ── Renderiza ─────────────────────────────────────────────────────────────
    if ECHARTS_OK:
        option = _construir_option(agg, gerencia, nivel)
        st_echarts(
            options=option,
            height="450px",
            key=f"unif_echarts_{gerencia}_{nivel}",
        )
    else:
        _fallback_plotly(agg, gerencia, nivel)

    # ── Resumo + tabela detalhada ─────────────────────────────────────────────
    n_crit = int(agg["critico"].sum())
    n_tot  = len(agg)
    st.caption(
        f"📍 {n_tot} pontos · 🔴 {n_crit} hot-spots críticos · "
        f"🚂 {agg['ramal_sigla'].nunique()} ramal(is) · "
        f"Nível: {nivel} · Scroll = zoom horizontal"
    )

    with st.expander("📋 Tabela detalhada dos pontos"):
        tab = agg[["label", "disciplina", "qtd", "score_med", "lt_med", "critico"]].copy()
        tab.columns = ["Ponto", "Disciplina", "Qtd. Notas", "Score Médio", "Lead Time (dias)", "Crítico?"]
        tab["Score Médio"]       = tab["Score Médio"].round(1)
        tab["Lead Time (dias)"]  = tab["Lead Time (dias)"].round(0).astype(int)
        tab["Crítico?"]          = tab["Crítico?"].map({True: "🔴 Sim", False: "🟢 Não"})
        tab = tab.sort_values("Score Médio", ascending=False)
        st.dataframe(tab, use_container_width=True, hide_index=True)

# endregion
