# =============================================================================
# components/unifilar.py — Unifilar ECharts (KM Real + effectScatter)
# Sprint 3 (rev.3) — MRS Sentinel
#
# FIEL AO app1.py:
#   • KM real no eixo X (fallback sequencial quando km_real ausente)
#   • effectScatter pulsante nos top 10% por score
#   • visualMap score → cor (verde → vermelho)
#   • dataZoom slider + scroll do mouse
#   • Tooltip HTML rico: KM, notas, score, pátio, defeitos
#   • Modo Dual (Abertas × Concluídas) quando coluna origem_base disponível
#
# Exporta:
#   construir_serie_unifilar(df, bin_km, y_offset, label)
#   render_unifilar(df, bin_km, gerencia)
#
# Sessão 1: Imports & constantes
# Sessão 2: construir_serie_unifilar()
# Sessão 3: render_unifilar()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import math
import streamlit as st
import pandas as pd
import numpy as np

try:
    from streamlit_echarts import st_echarts, JsCode
    ECHARTS_OK = True
except ImportError:
    ECHARTS_OK = False

import plotly.graph_objects as go

from core.glossarios import nome_ramal, ativo_curto

# Motor de alertas — usado só para marcar hot-spots CRÔNICOS (anel extra).
# Import resiliente: se o módulo/dep falhar, o unifilar segue funcionando
# normalmente, apenas sem o anel crônico.
try:
    from core.alertas import detectar_hotspots_cronicos, carregar_config_alertas
    ALERTAS_OK = True
except Exception:
    ALERTAS_OK = False

COR_PRIMARIA = "#1e3a5f"
COR_GOLD     = "#ffb000"
COR_CRIT     = "#dc2626"
COR_OK       = "#16a34a"
COR_WARN     = "#f59e0b"
COR_CRONICO  = "#7c3aed"   # roxo — anel de hot-spot crônico (distinto do pulso)

# Folga (px) do anel crônico em relação ao diâmetro da bolha que ele circunda.
RING_DELTA   = 12
# endregion


# region ====================== SESSÃO 2: construir_serie_unifilar() ============

@st.cache_data(ttl=300, show_spinner=False)
def _cfg_alertas_cached():
    """Config de alertas (n_min / janela_meses) — cacheada 5 min p/ não bater
    no Supabase a cada rerun do unifilar. Falha graciosa para defaults."""
    return carregar_config_alertas()


def _marcar_cronicos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marca cada nota com `is_cronico=True` se pertence a um hot-spot crônico
    (ramal+origem+familia_defeito com >= n_min notas na janela) — MESMA
    granularidade e regra do motor de alertas (core/alertas.py).

    Não altera nada da série existente: apenas adiciona a coluna auxiliar
    usada para desenhar o anel crônico. Falha graciosa (coluna toda False).
    """
    df = df.copy()
    df["is_cronico"] = False
    if not ALERTAS_OK or df.empty or "data_nota" not in df.columns:
        return df

    present = [c for c in ("ramal", "origem", "familia_defeito")
               if c in df.columns]
    if not present:
        return df

    try:
        cfg = _cfg_alertas_cached()
        hs = detectar_hotspots_cronicos(df, cfg)
    except Exception:
        return df

    if hs is None or hs.empty:
        return df

    def _norm(vals):
        return tuple("" if pd.isna(v) else str(v) for v in vals)

    chaves = {_norm(t) for t in zip(*[hs[c] for c in present])}
    if not chaves:
        return df

    df["is_cronico"] = [_norm(t) in chaves
                        for t in zip(*[df[c] for c in present])]
    return df


def _top5_defeitos(x):
    vc = x.dropna().value_counts().head(5)
    if len(vc) == 0:
        return "—"
    return "<br/>".join(
        [f"&nbsp;&nbsp;• {d} <span style='color:#9ca3af;'>({n})</span>"
         for d, n in vc.items()]
    )


def _patios_unicos(x):
    valores = [v for v in x.dropna().unique() if str(v).strip()]
    return ", ".join(sorted(valores)) if valores else "—"


def _top3_inspecoes(x):
    vc = x.dropna().value_counts().head(3)
    vc = vc[vc.index.astype(str).str.strip() != ""]
    return ", ".join([str(t) for t in vc.index]) if len(vc) > 0 else "—"


def construir_serie_unifilar(df_base: pd.DataFrame, bin_km: float,
                              y_offset: float = 0, label: str = "") -> tuple:
    """
    Agrega notas em bins de KM e retorna pontos normais e pulsantes.
    FIEL AO app1.py — mesma lógica de agregação, tamanho e limiar pulsante.

    Returns:
        (pontos_normais, pontos_pulsantes, pontos_cronicos, agreg_df,
         km_min, km_max)
    """
    if len(df_base) == 0:
        return [], [], [], pd.DataFrame(), None, None

    df_t = df_base.copy()

    # Detecta colunas (suporta naming do app1 e do Sentinel)
    col_nota   = "nota"       if "nota"       in df_t.columns else (
                 "numero_nota" if "numero_nota" in df_t.columns else None)
    col_origem = "origem"      if "origem"      in df_t.columns else None
    col_sub    = "sub_trecho"  if "sub_trecho"  in df_t.columns else (
                 "trecho"      if "trecho"      in df_t.columns else None)
    col_def    = "defeito_legivel" if "defeito_legivel" in df_t.columns else (
                 "familia_defeito" if "familia_defeito" in df_t.columns else None)
    col_tipo   = "tipo_atividade" if "tipo_atividade" in df_t.columns else None
    col_lt     = "lead_time_dias" if "lead_time_dias" in df_t.columns else None

    if "score"      not in df_t.columns: df_t["score"]      = 1.0
    if "prioridade" not in df_t.columns: df_t["prioridade"] = "3-Média"

    df_t["bin_km"] = (df_t["km_real"] // bin_km) * bin_km

    # Dicionário de agregação
    agg_dict = {}
    if col_nota: agg_dict["qtd_notas"] = (col_nota, "count")
    else:        agg_dict["qtd_notas"] = ("score",  "count")
    agg_dict["score_total"] = ("score", "sum")
    agg_dict["score_medio"] = ("score", "mean")
    agg_dict["prio_1"] = ("prioridade", lambda x: (x == "1-Muito alta").sum())
    agg_dict["prio_2"] = ("prioridade", lambda x: (x == "2-Alta").sum())
    if col_origem: agg_dict["patios"]      = (col_origem, _patios_unicos)
    if col_sub:    agg_dict["sub_trechos"] = (col_sub,    _patios_unicos)
    if col_def:    agg_dict["defeitos"]    = (col_def,    _top5_defeitos)
    if col_tipo:   agg_dict["tipos_insp"] = (col_tipo,   _top3_inspecoes)
    if col_lt:     agg_dict["lt_medio"]   = (col_lt,
                                             lambda x: x.dropna().mean()
                                             if x.dropna().any() else None)
    tem_cronico = "is_cronico" in df_t.columns
    if tem_cronico:
        agg_dict["n_cronicos"] = ("is_cronico", "sum")

    agreg = df_t.groupby("bin_km").agg(**agg_dict).reset_index()
    if len(agreg) == 0:
        return [], [], [], pd.DataFrame(), None, None

    qtd_max   = agreg["qtd_notas"].max()
    score_max = agreg["score_total"].max()

    # Top 10% → pulsante (igual app1)
    limiar = agreg["score_total"].quantile(0.90) if len(agreg) >= 10 else score_max

    def calc_tamanho(qtd):
        return 12 + (qtd / qtd_max) * 43   # 12–55 px (igual app1)

    pontos_normais   = []
    pontos_pulsantes = []
    pontos_cronicos  = []

    for _, row in agreg.iterrows():
        tamanho = calc_tamanho(row["qtd_notas"])

        n_cron = int(row["n_cronicos"]) if (tem_cronico
                 and pd.notna(row.get("n_cronicos"))) else 0
        cron_txt = (
            f"<div style='margin-top:6px;padding:4px 8px;"
            f"background:rgba(124,58,237,0.08);border-left:3px solid "
            f"{COR_CRONICO};border-radius:4px;font-size:12px;color:#5b21b6;'>"
            f"♻️ <b>Hot-spot CRÔNICO</b> — {n_cron} nota(s) recorrente(s) "
            f"neste local</div>"
            if n_cron > 0 else ""
        )

        lt_txt = (
            f"⏱️ Lead time médio: <b>{row['lt_medio']:.0f} dias</b><br/>"
            if "lt_medio" in row.index and pd.notna(row.get("lt_medio")) else ""
        )
        patios_txt  = row.get("patios",      "—")
        subtrc_txt  = row.get("sub_trechos", "—")
        def_txt     = row.get("defeitos",    "—")
        tipo_txt    = row.get("tipos_insp",  "—")

        # Tooltip HTML idêntico ao app1
        hover = (
            f"<div style='min-width:220px;'>"
            f"<div style='font-size:13px;color:#9ca3af;margin-bottom:4px;'>{label}</div>"
            f"<div style='font-size:15px;font-weight:700;color:#1e3a5f;margin-bottom:6px;'>"
            f"KM {row['bin_km']:.1f} → {row['bin_km']+bin_km:.1f}</div>"
            f"<hr style='border:0;border-top:1px solid #e5e7eb;margin:6px 0;'/>"
            f"📋 <b>{row['qtd_notas']}</b> notas<br/>"
            f"⚡ Score: <b>{row['score_total']:.0f}</b><br/>"
            f"🔴 Muito alta: <b>{row['prio_1']}</b> &nbsp;|&nbsp; "
            f"🟠 Alta: <b>{row['prio_2']}</b><br/>"
            f"{lt_txt}"
            f"📍 Pátio(s): <b>{patios_txt}</b><br/>"
            f"🚂 Trecho(s): <b>{subtrc_txt}</b><br/>"
            f"🔍 Inspeção(ões): <b>{tipo_txt}</b><br/>"
            f"<div style='margin-top:6px;font-size:12px;color:#6b7280;'>"
            f"<b>Top defeitos:</b></div>"
            f"<div style='font-size:12px;'>{def_txt}</div>"
            f"{cron_txt}"
            f"</div>"
        )

        valor = [
            float(row["bin_km"] + bin_km / 2),
            y_offset,
            float(row["score_total"]),
            int(row["qtd_notas"]),
        ]
        ponto = {
            "value": valor,
            "symbolSize": tamanho,
            "tooltipHTML": hover,
        }

        if row["score_total"] >= limiar:
            pontos_pulsantes.append(ponto)
        else:
            pontos_normais.append(ponto)

        # Anel crônico (camada extra, NÃO substitui o pulso): mesmo ponto,
        # símbolo um pouco maior que a bolha, desenhado como aro vazado.
        if n_cron > 0:
            pontos_cronicos.append({
                "value": valor,
                "symbolSize": tamanho + RING_DELTA,
            })

    km_min = float(agreg["bin_km"].min()) if len(agreg) else None
    km_max = float(agreg["bin_km"].max() + bin_km) if len(agreg) else None
    return (pontos_normais, pontos_pulsantes, pontos_cronicos,
            agreg, km_min, km_max)

# endregion


# region ====================== SESSÃO 3: render_unifilar() ====================

def _sanitize(obj):
    """Remove Infinity/NaN do option dict — idêntico ao app1."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return 0
    return obj


def _criar_km_sequencial(df: pd.DataFrame, col_ramal: str,
                          bin_km: float = 0.5) -> pd.DataFrame:
    """
    KM fictício quando não há coluna km_real.
    Cada pátio único = posição sequencial × (bin_km × 4).
    Sprint 6 substituirá pelo KM real do Supabase.
    """
    df = df.copy()
    if "origem" in df.columns:
        df["km_real"] = df.groupby(col_ramal)["origem"].transform(
            lambda x: pd.Categorical(x, categories=x.unique()).codes.astype(float)
            * bin_km * 4
        )
    else:
        df["km_real"] = pd.Series(range(len(df)), dtype=float) * bin_km
    return df


def render_unifilar(df: pd.DataFrame, bin_km: float = None,
                    gerencia: str = "SP"):
    """
    Renderiza o Unifilar ECharts — fiel ao app1.py.

    Adapta nomes de colunas do Sentinel para o padrão do app1:
      numero_nota  → nota
      ramal        → trecho (agrupador de Matriz)
      trecho       → sub_trecho (par Origem-Destino)
      familia_defeito → defeito_legivel

    Args:
        df:      DataFrame filtrado (todas as notas da gerência)
        bin_km:  janela de agrupamento (km) — se None, mostra slider interno
        gerencia: 'SP', 'VP' ou 'GERAL'
    """
    if df.empty:
        st.info("Sem dados para o unifilar.")
        return

    # ── Slider de resolução (idêntico ao app1: 100–2000 m) ───────────────────
    col_res, _ = st.columns([1, 2])
    with col_res:
        bin_km_m = st.slider(
            "🔬 Janela de agrupamento (m):",
            min_value=100, max_value=2000, value=500, step=100,
            key=f"bin_km_{gerencia}",
            help="Menor = mais detalhe por KM | Maior = visão macro do ramal.",
        )
    bin_km = bin_km_m / 1000  # converte para km

    df_u = df.copy()

    # ── Normaliza colunas ────────────────────────────────────────────────────
    if "nota" not in df_u.columns and "numero_nota" in df_u.columns:
        df_u["nota"] = df_u["numero_nota"]

    # Ramal = agrupador de Matriz (trecho no app1)
    col_matriz = "ramal" if "ramal" in df_u.columns else (
                 "trecho" if "trecho" in df_u.columns else None)

    # sub_trecho = par Origem-Destino
    if "sub_trecho" not in df_u.columns and "trecho" in df_u.columns:
        df_u["sub_trecho"] = df_u["trecho"]

    # defeito_legivel
    if "defeito_legivel" not in df_u.columns:
        for c in ["familia_defeito", "codigo_defeito", "tipo_anomalia"]:
            if c in df_u.columns:
                df_u["defeito_legivel"] = df_u[c]
                break
        else:
            df_u["defeito_legivel"] = "—"

    if "score" not in df_u.columns:
        df_u["score"] = 1.0

    # ── KM real (ou sequencial) ───────────────────────────────────────────────
    if "km_real" not in df_u.columns or df_u["km_real"].isna().all():
        df_u = _criar_km_sequencial(df_u, col_matriz or "ramal", bin_km)
        km_ficticio = True
    else:
        km_ficticio = False

    # ── Origem base (para Modo Dual) ──────────────────────────────────────────
    # Mapeamento robusto: tenta várias colunas e padrões de valores do banco.
    # Qualquer variação de "aberto/abertas/pendente" → "Abertas"
    # Qualquer variação de "encerrado/concluido/fechado" → "Concluídas"
    def _detectar_origem_base(row_df: pd.DataFrame) -> pd.Series:
        # Colunas candidatas em ordem de prioridade
        candidatas = ["origem_base", "status_amigavel", "status", "situacao",
                      "status_nota", "situacao_nota"]
        for col in candidatas:
            if col in row_df.columns:
                # fillna ANTES do astype(str): em colunas com dtype nullable
                # (string[pyarrow], comum no pandas atual), valores ausentes
                # viram pd.NA mesmo depois de astype(str) — e "x in pd.NA"
                # explode com TypeError dentro do map abaixo.
                return row_df[col].fillna("").astype(str).str.lower().map(
                    lambda v: (
                        "Concluídas" if any(p in v for p in
                            ["encerr", "conclui", "fecha", "resolv", "conclu"])
                        else "Abertas"
                    )
                )
        # Fallback: tudo como Abertas
        return pd.Series(["Abertas"] * len(row_df), index=row_df.index)

    if "origem_base" not in df_u.columns:
        df_u["origem_base"] = _detectar_origem_base(df_u)
    else:
        # Normaliza valores já existentes (pode vir como "Aberto" ou "Abertas")
        # fillna antes do astype(str) pelo mesmo motivo do bloco acima.
        df_u["origem_base"] = df_u["origem_base"].fillna("").astype(str).str.lower().map(
            lambda v: (
                "Concluídas" if any(p in v for p in
                    ["encerr", "conclui", "fecha", "resolv", "conclu"])
                else "Abertas"
            )
        )

    # ── Filtra notas com KM e matriz ──────────────────────────────────────────
    df_unifilar = df_u.dropna(subset=["km_real"]).copy()
    if col_matriz:
        df_unifilar = df_unifilar.dropna(subset=[col_matriz])

    if len(df_unifilar) == 0:
        st.warning(
            "⚠️ Nenhuma nota com KM identificado. "
            "Tente liberar mais filtros ou aguardar Sprint 6 (KM real)."
        )
        return

    if km_ficticio:
        st.caption(
            "ℹ️ **KM real não disponível** — posição sequencial por pátio. "
            "Sprint 6 substituirá por KM real."
        )

    # ── Seleciona Matriz (Ramal) ──────────────────────────────────────────────
    bases_disponiveis  = sorted(df_unifilar["origem_base"].unique())
    # Dual possível sempre que houver ao menos 1 base — o outro lado fica vazio
    # mas o modo visual já é o principal (fiel ao app1)
    modo_dual_possivel = True
    matrizes = sorted(df_unifilar[col_matriz].dropna().unique()) \
               if col_matriz else ["Geral"]

    col_modo, col_ramal_sel = st.columns([1, 3])

    with col_modo:
        modo_raw = st.radio(
            "🎬 Modo:",
            ["🎯 Dual", "📊 Empilhado"],
            horizontal=False,
            index=0,   # Dual é o padrão
            help="Dual = Abertas (topo) × Concluídas (base). "
                 "Empilhado = todas na mesma linha.",
            key=f"modo_unif_{gerencia}",
        )
        modo_view = "Dual" if "Dual" in modo_raw else "Empilhado"

    with col_ramal_sel:
        if len(matrizes) == 1:
            ramal_view = matrizes[0]
            label_m = nome_ramal(ramal_view, "completo")                       if col_matriz == "ramal" else str(ramal_view)
            st.markdown(
                f"<div style='padding:8px 12px;background:#1e3a5f;color:#fff;"
                f"border-radius:8px;text-align:center;margin-top:28px;'>"
                f"🚂 Visualizando: <b>{label_m}</b></div>",
                unsafe_allow_html=True,
            )
        else:
            opcoes = [f"🌐 Todos ({len(df_unifilar):,})"]
            for m in matrizes:
                qtd = len(df_unifilar[df_unifilar[col_matriz] == m])                       if col_matriz else len(df_unifilar)
                lbl = nome_ramal(m, "completo")                       if col_matriz == "ramal" else str(m)
                opcoes.append(f"{lbl} ({qtd:,})")

            escolha = st.radio(
                "🚂 Ramal:",
                opcoes,
                horizontal=True,
                key=f"ramal_unif_{gerencia}",
                help="Cada ramal gera seu próprio unifilar. 'Todos' combina todos "
                     "os ramais na mesma visão (visão total unifilar).",
            )
            idx_escolha = opcoes.index(escolha)
            ramal_view = "__TODOS__" if idx_escolha == 0 else matrizes[idx_escolha - 1]

    # Filtra pelo ramal
    if ramal_view == "__TODOS__":
        df_t_completo = df_unifilar.copy()
    elif col_matriz and len(matrizes) > 1:
        df_t_completo = df_unifilar[df_unifilar[col_matriz] == ramal_view].copy()
    else:
        df_t_completo = df_unifilar.copy()

    if ramal_view == "__TODOS__":
        label_ramal_final = "Todos"
    else:
        label_ramal_final = nome_ramal(ramal_view, "completo") \
                            if col_matriz == "ramal" else str(ramal_view)

    # ── Multi-trecho (idêntico ao app1: Sessão 6) ─────────────────────────────
    # Permite selecionar múltiplos trechos (par Origem-Destino) para fechar
    # o KM completo do ramal ou focar em um trecho específico.
    col_sub = "sub_trecho" if "sub_trecho" in df_t_completo.columns else (
              "trecho"     if "trecho"     in df_t_completo.columns else None)

    if col_sub:
        trechos_disp = sorted(
            [t for t in df_t_completo[col_sub].dropna().unique() if str(t).strip()]
        )
        if len(trechos_disp) > 1:
            trechos_sel = st.multiselect(
                "🚂 Trecho (Origem-Destino):",
                trechos_disp,
                default=trechos_disp,
                key=f"trecho_unif_{gerencia}",
                help=(
                    f"{len(trechos_disp)} trechos disponíveis. "
                    "Selecione múltiplos para fechar o KM completo do ramal "
                    "ou foque em um trecho específico."
                ),
            )
            if trechos_sel:
                df_t_completo = df_t_completo[
                    df_t_completo[col_sub].isin(trechos_sel)
                ].copy()

    if df_t_completo.empty:
        st.warning("⚠️ Nenhuma nota com os filtros de trecho aplicados.")
        return

    # ── Marca hot-spots crônicos (para o anel extra) ──────────────────────────
    # Feito ANTES do split Abertas/Concluídas para que o anel crônico apareça
    # em ambos os eixos do modo Dual. Não altera a lógica do pulso (top 10%).
    df_t_completo = _marcar_cronicos(df_t_completo)
    ha_cronicos = bool(df_t_completo["is_cronico"].any())

    st.caption(
        f"Cada bolha = agrupamento de notas em **{bin_km*1000:.0f} m**. "
        f"**Tamanho** = qtd de notas | **Cor** = score de criticidade | "
        f"**Bolhas pulsantes** = top 10% mais críticos"
        + (f" | <span style='color:{COR_CRONICO};font-weight:600;'>"
           f"⭕ anel roxo = hot-spot crônico</span> (defeito recorrente no "
           f"mesmo local)" if ha_cronicos else "")
        + ". Use a barra inferior para **zoom** no KM.",
        unsafe_allow_html=True,
    )

    # ── Monta séries ──────────────────────────────────────────────────────────
    series           = []
    indices_score    = []   # séries coloridas pelo score (escopo do visualMap)
    km_min_global    = float("inf")
    km_max_global    = float("-inf")
    score_max_global = 0

    def _add_score_series(s):
        """Adiciona série cuja cor vem do visualMap (score)."""
        indices_score.append(len(series))
        series.append(s)

    def _serie_anel_cronico(pontos, nome):
        """Aro vazado roxo ao redor das bolhas crônicas — camada decorativa
        (silent) que NÃO interfere no pulso nem no tooltip da bolha."""
        return {
            "name": nome, "type": "scatter", "data": pontos,
            "symbol": "circle", "silent": True,
            "itemStyle": {
                "color": "rgba(0,0,0,0)",          # aro vazado
                "borderColor": COR_CRONICO,
                "borderWidth": 3,
                "shadowBlur": 6,
                "shadowColor": "rgba(124,58,237,0.5)",
            },
            "emphasis": {"disabled": True},
            "tooltip": {"show": False},
            "z": 3,
        }

    if modo_view == "Dual":
        df_a = df_t_completo[df_t_completo["origem_base"] == "Abertas"].copy()
        df_c = df_t_completo[df_t_completo["origem_base"] == "Concluídas"].copy()
        # Se não houver concluídas, avisa mas mantém o modo dual (eixo vazio)
        if df_c.empty:
            st.info("ℹ️ Nenhuma nota **Concluída** nos filtros atuais — "
                    "eixo inferior ficará vazio.")
        if df_a.empty:
            st.info("ℹ️ Nenhuma nota **Aberta** nos filtros atuais — "
                    "eixo superior ficará vazio.")

        pn_a, pp_a, pc_a, agreg_a, kma_min, kma_max = construir_serie_unifilar(
            df_a, bin_km, y_offset=1, label="📋 Abertas (Diagnóstico)"
        )
        pn_c, pp_c, pc_c, agreg_c, kmc_min, kmc_max = construir_serie_unifilar(
            df_c, bin_km, y_offset=-1, label="✅ Concluídas (Realizado)"
        )

        for v in [kma_min, kmc_min]:
            if v is not None and pd.notna(v):
                km_min_global = min(km_min_global, v)
        for v in [kma_max, kmc_max]:
            if v is not None and pd.notna(v):
                km_max_global = max(km_max_global, v)
        if len(agreg_a):
            score_max_global = max(score_max_global,
                                   float(agreg_a["score_total"].max()))
        if len(agreg_c):
            score_max_global = max(score_max_global,
                                   float(agreg_c["score_total"].max()))

        # Linhas da via (Abertas = y+1, Concluídas = y-1)
        series += [
            {"name": "Via (Abertas)", "type": "line",
             "data": [[km_min_global, 1], [km_max_global, 1]],
             "lineStyle": {"color": "#374151", "width": 3},
             "symbol": "none", "silent": True, "tooltip": {"show": False}},
            {"name": "Via (Concluídas)", "type": "line",
             "data": [[km_min_global, -1], [km_max_global, -1]],
             "lineStyle": {"color": "#374151", "width": 3},
             "symbol": "none", "silent": True, "tooltip": {"show": False}},
        ]
        if pn_a:
            _add_score_series({
                "name": "📋 Abertas", "type": "scatter", "data": pn_a,
                "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5,
                              "opacity": 0.85}})
        if pn_c:
            _add_score_series({
                "name": "✅ Concluídas", "type": "scatter", "data": pn_c,
                "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5,
                              "opacity": 0.85}})
        # Anel crônico (aro roxo) — camada extra, não colorida pelo score
        if pc_a:
            series.append(_serie_anel_cronico(pc_a, "♻️ Abertas Crônicas"))
        if pc_c:
            series.append(_serie_anel_cronico(pc_c, "♻️ Concluídas Crônicas"))
        # effectScatter — pulsante (fiel ao app1: period=3, scale=2.8)
        if pp_a:
            _add_score_series({
                "name": "🔥 Abertas Críticos", "type": "effectScatter",
                "data": pp_a,
                "rippleEffect": {"period": 3, "scale": 2.8,
                                 "brushType": "stroke"},
                "showEffectOn": "render",
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})
        if pp_c:
            _add_score_series({
                "name": "🔥 Concluídas Críticos", "type": "effectScatter",
                "data": pp_c,
                "rippleEffect": {"period": 3, "scale": 2.8,
                                 "brushType": "stroke"},
                "showEffectOn": "render",
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})

        qtd_a = len(df_a); qtd_c = len(df_c)
        st.markdown(
            f"<div style='text-align:center;font-size:17px;"
            f"margin-bottom:8px;color:#1f2937;'>"
            f"<b>Ramal {label_ramal_final}</b> — "
            f"<span style='color:#dc2626;font-weight:600;'>"
            f"📋 {qtd_a:,} abertas</span>"
            f" &nbsp;×&nbsp; "
            f"<span style='color:#16a34a;font-weight:600;'>"
            f"✅ {qtd_c:,} concluídas</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        # Empilhado / base única
        pn, pp, pc, agreg, kmm, kmx = construir_serie_unifilar(
            df_t_completo, bin_km, y_offset=0, label=f"📊 {label_ramal_final}"
        )
        if kmm is not None and pd.notna(kmm): km_min_global = kmm
        if kmx is not None and pd.notna(kmx): km_max_global = kmx
        if km_min_global == float("inf"):  km_min_global = 0.0
        if km_max_global == float("-inf"): km_max_global = 100.0
        if len(agreg):
            score_max_global = float(agreg["score_total"].max())

        series.append({
            "name": "Via", "type": "line",
            "data": [[km_min_global, 0], [km_max_global, 0]],
            "lineStyle": {"color": "#374151", "width": 3},
            "symbol": "none", "silent": True, "tooltip": {"show": False},
        })
        if pn:
            _add_score_series({
                "name": "Notas", "type": "scatter", "data": pn,
                "itemStyle": {"borderColor": "#fff", "borderWidth": 1.5,
                              "opacity": 0.85}})
        # Anel crônico (aro roxo) — camada extra, não colorida pelo score
        if pc:
            series.append(_serie_anel_cronico(pc, "♻️ Crônicos"))
        # effectScatter pulsante — fiel ao app1
        if pp:
            _add_score_series({
                "name": "🔥 Hot-spots críticos", "type": "effectScatter",
                "data": pp,
                "rippleEffect": {"period": 3, "scale": 2.8,
                                 "brushType": "stroke"},
                "showEffectOn": "render",
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2}})

        st.markdown(
            f"<div style='text-align:center;font-size:17px;"
            f"margin-bottom:8px;color:#1f2937;'>"
            f"<b>Ramal {label_ramal_final}</b> — "
            f"{len(df_t_completo):,} notas distribuídas</div>",
            unsafe_allow_html=True,
        )

    if km_min_global == float("inf"):  km_min_global = 0.0
    if km_max_global == float("-inf"): km_max_global = 100.0

    # ── Fallback Plotly ───────────────────────────────────────────────────────
    if not ECHARTS_OK:
        fig = go.Figure()
        for s in series:
            if s["type"] in ("scatter", "effectScatter"):
                xs = [p["value"][0] for p in s["data"]]
                ys = [p["value"][1] for p in s["data"]]
                ss = [p["symbolSize"] for p in s["data"]]
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="markers", name=s["name"],
                    marker=dict(size=[sz / 3 for sz in ss]),
                ))
            elif s["type"] == "line":
                fig.add_trace(go.Scatter(
                    x=[p[0] for p in s["data"]],
                    y=[p[1] for p in s["data"]],
                    mode="lines", name=s["name"],
                    line=dict(color="#374151", width=2),
                ))
        fig.update_layout(
            height=380, plot_bgcolor="white", paper_bgcolor="white",
            xaxis_title="KM", margin=dict(l=50, r=20, t=20, b=60),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("streamlit-echarts não instalado — usando Plotly")
        return

    # ── Opção ECharts (fiel ao app1) ──────────────────────────────────────────
    option = {
        "tooltip": {
            "trigger": "item",
            "backgroundColor": "rgba(255,255,255,0.98)",
            "borderColor": COR_PRIMARIA, "borderWidth": 2,
            "padding": [10, 14],
            "extraCssText": (
                "box-shadow:0 6px 20px rgba(0,0,0,0.15);"
                "border-radius:10px;max-width:320px;"
            ),
            "textStyle": {"color": "#1f2937", "fontSize": 12},
            # Tooltip usa a prop tooltipHTML de cada ponto — idêntico ao app1
            "formatter": JsCode(
                "function(params){ return params.data.tooltipHTML || ''; }"
            ).js_code,
        },
        # visualMap: score → cor (verde → vermelho) — idêntico ao app1.
        # seriesIndex restringe a coloração às bolhas/pulsos; o anel crônico
        # (roxo, cor fixa) fica de fora para não ser recolorido pelo score.
        "visualMap": {
            "min": 0,
            "max": float(score_max_global) if score_max_global > 0 else 100,
            "dimension": 2,
            "seriesIndex": indices_score,
            "show": True, "orient": "vertical",
            "right": 10, "top": "middle",
            "itemHeight": 120, "itemWidth": 14,
            "calculable": True,
            "text": ["Crítico", "OK"],
            "textStyle": {"color": "#1f2937", "fontSize": 11},
            "inRange": {
                "color": ["#16a34a", "#84cc16", "#eab308",
                          "#f59e0b", "#dc2626"]
            },
        },
        "grid": {
            "left": 50, "right": 90, "top": 20, "bottom": 80,
            "containLabel": True,
        },
        "xAxis": {
            "type": "value",
            "name": "Quilometragem (KM)" if not km_ficticio
                    else "Posição sequencial",
            "nameLocation": "middle", "nameGap": 32,
            "nameTextStyle": {
                "color": "#374151", "fontSize": 12, "fontWeight": "bold"
            },
            "axisLine":  {"lineStyle": {"color": "#9ca3af"}},
            "axisLabel": {"color": "#374151", "fontSize": 11},
            "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}},
        },
        "yAxis": {
            "type": "value",
            "min": -2.5 if modo_view == "Dual" else -1.2,
            "max":  2.5 if modo_view == "Dual" else  1.2,
            "show": False,
            "axisLine": {"show": False}, "splitLine": {"show": False},
        },
        # dataZoom: slider + scroll do mouse — idêntico ao app1
        "dataZoom": [
            {
                "type": "slider", "show": True, "xAxisIndex": [0],
                "bottom": 15, "height": 22,
                "borderColor": "#d1d5db",
                "fillerColor": "rgba(30,58,95,0.15)",
                "handleStyle": {"color": COR_PRIMARIA},
                "moveHandleStyle": {"color": COR_PRIMARIA},
                "textStyle": {"color": "#374151", "fontSize": 10},
            },
            {"type": "inside", "xAxisIndex": [0]},
        ],
        "series": series,
    }

    option_safe = _sanitize(option)
    altura = 460 if modo_view == "Dual" else 380
    st_echarts(
        options=option_safe,
        height=f"{altura}px",
        key=f"unif_{gerencia}_{str(ramal_view)}",
    )

    # ── Rankings complementares (Tipo de Inspeção / Família Defeito / Ativo) ──
    render_rankings_unifilar(df_t_completo, gerencia=f"{gerencia}_{str(ramal_view)}")

# endregion

# Alias de compatibilidade — gerencia_sp/vp/geral importam render_unifilar_dual
render_unifilar_dual = render_unifilar


# region ====================== SESSÃO 4: Rankings da aba Unifilar =============
#
# Três rankings em barras (verticais), sempre respeitando o recorte de
# Ramal + Trecho já selecionado acima no Unifilar:
#   1. Tipo de Inspeção (X) × Qtd. de Notas (Y)
#        empilhar por: Total | Prioridade
#   2. Família Defeito (X) × Qtd. de Notas (Y)
#        empilhar por: Total | Prioridade | Tipo de Inspeção
#   3. Ativo (X) × Qtd. de Notas (Y)
#        empilhar por: Família Defeito | Prioridade | Tipo de Inspeção

_CORES_PRIORIDADE = {
    "1-Muito alta": COR_CRIT,
    "2-Alta":       COR_WARN,
    "3-Média":      "#eab308",
    "4-Baixa":      COR_OK,
}


def _gradiente_stack(idx: int, total: int) -> str:
    """Paleta cíclica (azul MRS → dourado) p/ segmentos de empilhamento
    sem mapeamento fixo de cor (ex.: Tipo de Inspeção, Família Defeito)."""
    if total <= 1:
        return COR_PRIMARIA
    ratio = idx / (total - 1)
    r = int(30 + (245 - 30) * ratio)
    g = int(58 + (158 - 58) * ratio)
    b = int(95 + (11 - 95) * ratio)
    return f"rgb({r},{g},{b})"


def _bar_empilhado_ranking(df: pd.DataFrame, col_cat: str, col_stack: str | None,
                            chart_key: str, top_n: int = 15,
                            max_segmentos: int = 8):
    """
    Barras verticais: Eixo X = ranking de col_cat (top_n por qtd. de notas),
    Eixo Y = qtd. de notas. Se col_stack for informado, empilha por essa
    coluna (limitado a max_segmentos + 'Outros').
    """
    if not ECHARTS_OK:
        st.warning("streamlit-echarts não instalado.")
        return
    if col_cat not in df.columns or df.empty:
        st.info(f"Coluna '{col_cat}' não disponível nos dados.")
        return

    d = df.copy()
    d[col_cat] = d[col_cat].fillna("(Sem informação)").replace("", "(Sem informação)")

    contagem_cat = d[col_cat].value_counts()
    if contagem_cat.empty:
        st.info("Sem dados no filtro atual.")
        return
    ordem_cat = contagem_cat.head(top_n).index.tolist()
    d = d[d[col_cat].isin(ordem_cat)]

    if not col_stack or col_stack not in d.columns:
        contagem = d[col_cat].value_counts().reindex(ordem_cat).fillna(0).astype(int)
        series = [{
            "name": "Notas",
            "type": "bar",
            "data": [int(contagem[c]) for c in ordem_cat],
            "itemStyle": {"color": COR_PRIMARIA},
            "label": {"show": True, "position": "top", "color": "#1f2937",
                      "fontSize": 10, "fontWeight": "bold"},
        }]
        legenda = None
    else:
        d[col_stack] = d[col_stack].fillna("(Sem informação)").replace("", "(Sem informação)")
        pivot = d.groupby([col_cat, col_stack]).size().unstack(fill_value=0)
        pivot = pivot.reindex(ordem_cat).fillna(0)

        totais_stack = pivot.sum(axis=0).sort_values(ascending=False)
        cols_stack = totais_stack.index.tolist()[:max_segmentos]
        outros = [c for c in pivot.columns if c not in cols_stack]
        if outros:
            pivot["Outros"] = pivot[outros].sum(axis=1)
            cols_stack = cols_stack + ["Outros"]

        series = []
        for i, cs in enumerate(cols_stack):
            cor = _CORES_PRIORIDADE.get(cs) or _gradiente_stack(i, len(cols_stack))
            series.append({
                "name": str(cs), "type": "bar", "stack": "total",
                "data": [int(pivot.loc[c, cs]) for c in ordem_cat],
                "itemStyle": {"color": cor},
            })
        legenda = [str(c) for c in cols_stack]

    opt = {
        "tooltip": {
            "trigger": "axis", "axisPointer": {"type": "shadow"},
            "backgroundColor": "rgba(255,255,255,0.98)", "borderColor": COR_PRIMARIA,
            "textStyle": {"color": "#1f2937"},
        },
        "legend": ({"data": legenda, "top": 0, "textStyle": {"fontSize": 10}}
                   if legenda else None),
        "grid": {"left": "3%", "right": "3%",
                 "top": "18%" if legenda else "10%",
                 "bottom": "18%", "containLabel": True},
        "xAxis": {
            "type": "category", "data": ordem_cat,
            "axisLabel": {"rotate": 30, "fontSize": 10, "color": "#374151",
                          "width": 110, "overflow": "truncate"},
        },
        "yAxis": {
            "type": "value", "axisLabel": {"color": "#374151"},
            "splitLine": {"lineStyle": {"color": "#e5e7eb", "type": "dashed"}},
        },
        "series": series,
    }
    opt = _sanitize(opt)
    st_echarts(opt, height="380px", key=chart_key)

    total_dist = int(contagem_cat.shape[0])
    if total_dist > top_n:
        st.caption(
            f"⚠️ Mostrando os **{top_n} com mais notas**. "
            f"Total distintos no filtro: **{total_dist:,}**."
        )


def render_rankings_unifilar(df: pd.DataFrame, gerencia: str):
    """
    Três rankings empilháveis, abaixo do gráfico de KM do Unifilar,
    usando o mesmo recorte de Ramal + Trecho já aplicado na aba.
    """
    if df.empty or not ECHARTS_OK:
        return

    col_insp  = "tipo_atividade"    if "tipo_atividade"    in df.columns else None
    col_fam   = "familia_defeito"   if "familia_defeito"   in df.columns else (
                "defeito_legivel"   if "defeito_legivel"   in df.columns else None)
    col_ativo = "local_instalacao"  if "local_instalacao"  in df.columns else None
    col_prio  = "prioridade"        if "prioridade"        in df.columns else None

    if not any([col_insp, col_fam, col_ativo]):
        return

    st.markdown("---")
    st.markdown("#### 🏆 Rankings — Tipo de Inspeção, Família de Defeito e Ativo")
    st.caption(
        "Rankings calculados sobre o mesmo recorte de Ramal e Trecho "
        "selecionado no Unifilar acima."
    )

    # ── Ranking 1: Tipo de Inspeção ────────────────────────────────────────
    if col_insp:
        st.markdown("##### 🔍 Ranking — Tipo de Inspeção × Ativos")
        opcoes1 = ["Quantidade Total de Notas"]
        if col_prio: opcoes1.append("Quantidade por Prioridade")
        modo1 = (
            st.radio("Empilhar por:", opcoes1, horizontal=True,
                      key=f"rk_insp_modo_{gerencia}")
            if len(opcoes1) > 1 else opcoes1[0]
        )
        stack1 = col_prio if modo1 == "Quantidade por Prioridade" else None
        _bar_empilhado_ranking(df, col_insp, stack1, f"rk_insp_{gerencia}")

    # ── Ranking 2: Família Defeito ──────────────────────────────────────────
    if col_fam:
        st.markdown("##### 🧩 Ranking — Família Defeito × Ativos")
        opcoes2 = ["Quantidade Total de Notas"]
        if col_prio: opcoes2.append("Quantidade por Prioridade")
        if col_insp: opcoes2.append("Quantidade por Tipo de Inspeção")
        modo2 = (
            st.radio("Empilhar por:", opcoes2, horizontal=True,
                      key=f"rk_fam_modo_{gerencia}")
            if len(opcoes2) > 1 else opcoes2[0]
        )
        stack2 = (
            col_prio if modo2 == "Quantidade por Prioridade" else
            col_insp if modo2 == "Quantidade por Tipo de Inspeção" else None
        )
        _bar_empilhado_ranking(df, col_fam, stack2, f"rk_fam_{gerencia}")

    # ── Ranking 3: Ativo ─────────────────────────────────────────────────────
    if col_ativo:
        st.markdown("##### 🚂 Ranking — Ativo × Quantidade Total de Notas")
        opcoes3 = ["Quantidade Total de Notas"]
        if col_fam:  opcoes3.append("Quantidade por Família Defeito")
        if col_prio: opcoes3.append("Quantidade por Prioridade")
        if col_insp: opcoes3.append("Quantidade por Tipo de Inspeção")
        modo3 = (
            st.radio("Empilhar por:", opcoes3, horizontal=True,
                      key=f"rk_ativo_modo_{gerencia}")
            if len(opcoes3) > 1 else opcoes3[0]
        )
        stack3 = (
            col_fam  if modo3 == "Quantidade por Família Defeito" else
            col_prio if modo3 == "Quantidade por Prioridade" else
            col_insp if modo3 == "Quantidade por Tipo de Inspeção" else None
        )

        d_ativo = df.copy()
        d_ativo[col_ativo] = d_ativo[col_ativo].apply(
            lambda v: ativo_curto(v) if pd.notna(v) and str(v).strip() else v
        )
        _bar_empilhado_ranking(d_ativo, col_ativo, stack3, f"rk_ativo_{gerencia}",
                               top_n=20)

# endregion
