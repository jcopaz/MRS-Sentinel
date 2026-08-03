# components/mapa_geografico.py — Mapa geográfico real da malha (Sprint 6)
#
# Duas granularidades:
#   • 'nota'      → cada nota/falha é um PONTO EXATO (lat/lon por KM). Ideal p/
#                   notas VP, que carregam km_real. Igual ao Unifilar, porém no
#                   mapa real, com o TRAÇADO da via desenhado por baixo.
#   • 'segmento'  → pontos agregados por local (usado onde não há KM, ex.: EE).
#
# Linguagem visual (mesma do Unifilar):
#   Cor = score de prioridade · Tamanho = volume · Anel roxo = crônico.
#
# Fundo BRANCO (sem detalhamento do basemap) — só o traçado da via e os pontos.
# Renderização em cascata: Folium(+plugins) → Plotly(white-bg) → st.map.

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

try:
    import folium
    from folium.plugins import MarkerCluster
    from streamlit_folium import st_folium
    _HAS_FOLIUM = True
except Exception:
    _HAS_FOLIUM = False

try:
    import plotly.express as px
    _HAS_PLOTLY = True
except Exception:
    _HAS_PLOTLY = False

try:
    from core.geo import enriquecer_geo, cobertura_geo, carregar_tracado
except Exception:  # pragma: no cover
    def enriquecer_geo(df, **k):
        return df

    def cobertura_geo(df):
        return {"total": 0, "com_geo": 0, "pct": 0.0}

    def carregar_tracado():
        return []


# ── Paleta (verde → amarelo → vermelho), alinhada ao score do Unifilar ────────
def _cor_score(s: float) -> str:
    try:
        s = float(s)
    except Exception:
        return "#6b7280"
    s = min(max(s, 0.0), 1.0)
    if s < 0.5:
        r = int(0x22 + (0xF5 - 0x22) * (s / 0.5))
        g = int(0xC5 + (0xC0 - 0xC5) * (s / 0.5))
        b = int(0x5E + (0x43 - 0x5E) * (s / 0.5))
    else:
        t = (s - 0.5) / 0.5
        r = int(0xF5 + (0xDC - 0xF5) * t)
        g = int(0xC0 + (0x26 - 0xC0) * t)
        b = int(0x43 + (0x26 - 0x43) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Colunas usadas em popup/score, tolerante a notas (VP) e RASF (EE) ─────────
def _col_score(df: pd.DataFrame) -> str:
    for c in ("score_ee", "score"):
        if c in df.columns:
            return c
    return ""


def _col_defeito(df: pd.DataFrame) -> str:
    for c in ("familia_defeito", "defeito_legivel", "anomalia_sintoma",
              "codigo_defeito", "tipo_anomalia"):
        if c in df.columns:
            return c
    return ""


def _col_nota(df: pd.DataFrame) -> str:
    for c in ("numero_nota", "nota", "ordem"):
        if c in df.columns:
            return c
    return ""


def _agregar_pontos(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega por coordenada (modo 'segmento')."""
    d = df.dropna(subset=["lat", "lon"]).copy()
    if d.empty:
        return d
    sc = _col_score(d)
    d["_score"] = pd.to_numeric(d[sc], errors="coerce").fillna(0.5) if sc else 0.5
    if "thp_h" not in d.columns:
        d["thp_h"] = 0.0
    if "reincidencia_ativo" in d.columns:
        d["_cron"] = d["reincidencia_ativo"].astype("boolean").fillna(False)
    else:
        d["_cron"] = False

    def _moda(s):
        s = s.dropna()
        return s.mode().iloc[0] if not s.mode().empty else "—"

    g = (d.groupby(["lat", "lon"])
           .agg(volume=("lat", "size"),
                score=("_score", "mean"),
                thp_h=("thp_h", "sum"),
                ramal=("ramal", _moda) if "ramal" in d.columns else ("lat", "size"),
                patio=("patio", _moda) if "patio" in d.columns else ("lat", "size"),
                km=("km_real", "median") if "km_real" in d.columns else ("lat", "size"),
                cronico=("_cron", "any"))
           .reset_index())
    return g


# ── Mapa base BRANCO (sem detalhamento — só a ferrovia por cima) ──────────────
def _mapa_branco(location, zoom_start):
    """
    Cria um folium.Map SEM camada de tiles (sem ruas/cidades) e força o fundo
    do Leaflet para branco. Pedido do Julio: mapa limpo, só com o traçado da
    via e os pontos das notas — sem o detalhamento do basemap.
    """
    m = folium.Map(location=location, zoom_start=zoom_start, tiles=None,
                   control_scale=True)
    m.get_root().html.add_child(folium.Element(
        "<style>.leaflet-container{background:#ffffff !important;}</style>"
    ))
    return m


# ── Traçado da via: desenha as polilinhas dos ramais presentes no df ──────────
def _desenhar_tracado(m, df: pd.DataFrame):
    try:
        polis = carregar_tracado()
    except Exception:
        polis = []
    if not polis:
        return 0
    ramais_df = set()
    if "ramal" in df.columns:
        ramais_df = {str(x).strip().upper() for x in df["ramal"].dropna().unique()}
    desenhadas = 0
    for p in polis:
        # Só desenha o traçado dos ramais que aparecem no recorte atual
        # (evita poluir o mapa com a malha inteira).
        if ramais_df and p["ramal"] not in ramais_df:
            continue
        folium.PolyLine(
            p["coords"], color="#64748b", weight=3, opacity=0.55,
            tooltip=f"{p['ramal']} · {p['linha']}",
        ).add_to(m)
        desenhadas += 1
    return desenhadas


def _render_folium_notas(df: pd.DataFrame, escopo: str):
    """Modo 'nota': cada falha é um ponto exato (com cluster)."""
    d = df.dropna(subset=["lat", "lon"]).copy()
    centro = [d["lat"].median(), d["lon"].median()]
    m = _mapa_branco(centro, zoom_start=10)

    _desenhar_tracado(m, d)

    sc = _col_score(d)
    cdef = _col_defeito(d)
    cnota = _col_nota(d)
    cron_col = "reincidencia_ativo" if "reincidencia_ativo" in d.columns else None

    cluster = MarkerCluster(name="Notas", disableClusteringAtZoom=13).add_to(m)
    for _, r in d.iterrows():
        score = pd.to_numeric(r.get(sc), errors="coerce") if sc else np.nan
        score = 0.5 if pd.isna(score) else float(score)
        cor = _cor_score(score)
        cron = bool(r.get(cron_col)) if cron_col else False
        km_txt = f"{r['km_real']:.3f}" if ("km_real" in d.columns
                                           and pd.notna(r.get("km_real"))) else "—"
        linhas_popup = [
            f"<b>Ramal:</b> {r.get('ramal', '—')}",
            f"<b>KM:</b> {km_txt}",
        ]
        if cnota:
            linhas_popup.insert(0, f"<b>Nota:</b> {r.get(cnota, '—')}")
        if cdef:
            linhas_popup.append(f"<b>Defeito:</b> {r.get(cdef, '—')}")
        if sc:
            linhas_popup.append(f"<b>Score:</b> {score:.2f}")
        if cron:
            linhas_popup.append("🟣 <b>Reincidente/Crônico</b>")
        popup = folium.Popup("<br>".join(str(x) for x in linhas_popup),
                             max_width=260)

        if cron:
            folium.CircleMarker([r["lat"], r["lon"]], radius=9, color="#7c3aed",
                                weight=3, fill=False, opacity=0.9).add_to(cluster)
        folium.CircleMarker(
            [r["lat"], r["lon"]], radius=6, color=cor, weight=1,
            fill=True, fill_color=cor, fill_opacity=0.85, popup=popup,
        ).add_to(cluster)

    st_folium(m, use_container_width=True, height=560,
              returned_objects=[], key=f"mapa_geo_notas_{escopo}")


def _render_folium_segmento(g: pd.DataFrame, df_ctx: pd.DataFrame, escopo: str):
    """Modo 'segmento': bolhas agregadas por local."""
    centro = [g["lat"].median(), g["lon"].median()]
    m = _mapa_branco(centro, zoom_start=8)
    _desenhar_tracado(m, df_ctx)

    vmax = float(g["volume"].max()) or 1.0
    for _, r in g.iterrows():
        raio = 5 + 15 * (float(r["volume"]) / vmax) ** 0.5
        cor = _cor_score(r["score"])
        km_txt = f"{r['km']:.1f}" if pd.notna(r.get("km")) else "—"
        popup = folium.Popup(
            f"<b>Ramal:</b> {r.get('ramal', '—')}<br>"
            f"<b>Pátio:</b> {r.get('patio', '—')}<br>"
            f"<b>KM aprox.:</b> {km_txt}<br>"
            f"<b>Falhas:</b> {int(r['volume'])}<br>"
            f"<b>THP (h):</b> {r['thp_h']:.1f}<br>"
            f"<b>Score médio:</b> {r['score']:.2f}"
            + ("<br>🟣 <b>Reincidente/Crônico</b>" if r["cronico"] else ""),
            max_width=260,
        )
        if r["cronico"]:
            folium.CircleMarker([r["lat"], r["lon"]], radius=raio + 4,
                                color="#7c3aed", weight=3, fill=False,
                                opacity=0.9).add_to(m)
        folium.CircleMarker(
            [r["lat"], r["lon"]], radius=raio, color=cor, weight=1,
            fill=True, fill_color=cor, fill_opacity=0.75, popup=popup,
        ).add_to(m)

    st_folium(m, use_container_width=True, height=560,
              returned_objects=[], key=f"mapa_geo_seg_{escopo}")


def _render_plotly(df: pd.DataFrame, escopo: str, individual: bool):
    if individual:
        d = df.dropna(subset=["lat", "lon"]).copy()
        sc = _col_score(d)
        d["score"] = pd.to_numeric(d[sc], errors="coerce").fillna(0.5) if sc else 0.5
        d["volume"] = 1
        hover = {c: True for c in ("ramal", "km_real") if c in d.columns}
        hover["score"] = ":.2f"
    else:
        d = df.copy()
        hover = {"ramal": True, "km": ":.1f", "volume": True, "score": ":.2f"}
        hover = {k: v for k, v in hover.items() if k in d.columns}

    escala = [[0, "#22c55e"], [0.5, "#f5c043"], [1, "#dc2626"]]
    kwargs = dict(
        lat="lat", lon="lon",
        size="volume" if "volume" in d.columns else None,
        color="score", color_continuous_scale=escala,
        size_max=22, zoom=7, hover_data=hover,
    )

    # Plotly ≥ 5.24 depreciou os traces "mapbox" (scatter_mapbox / mapbox_style)
    # em favor do MapLibre (scatter_map / map_style). O mapbox antigo renderiza
    # em BRANCO no navegador no Plotly 6.x. Usa a API nova quando disponível.
    if hasattr(px, "scatter_map"):
        fig = px.scatter_map(d, **kwargs)
        fig.update_layout(map_style="white-bg")
    else:  # compat Plotly < 5.24
        fig = px.scatter_mapbox(d, **kwargs)
        fig.update_layout(mapbox_style="white-bg")

    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=560,
                      coloraxis_colorbar_title="Score")
    try:
        st.plotly_chart(fig, use_container_width=True,
                        key=f"mapa_geo_plotly_{escopo}")
    except TypeError:  # Streamlit sem suporte a key= em plotly_chart
        st.plotly_chart(fig, use_container_width=True)


def render_mapa_geografico(df: pd.DataFrame, escopo: str = "",
                           titulo: str = "🗺️ Mapa Geográfico da Malha",
                           granularidade: str = "auto",
                           ja_enriquecido: bool = False):
    """
    granularidade:
      'nota'     → um ponto exato por falha/nota (usa km_real; ideal p/ VP).
      'segmento' → pontos agregados por local (usado p/ EE, sem KM).
      'auto'     → 'nota' se a maioria dos pontos tem posição por KM; senão 'segmento'.
    """
    with st.expander(titulo, expanded=False):
        _render_mapa_corpo(df, escopo, granularidade, ja_enriquecido)


def _render_mapa_corpo(df: pd.DataFrame, escopo: str, granularidade: str,
                       ja_enriquecido: bool):
    if df is None or df.empty:
        st.info("Sem dados para o mapa neste escopo.")
        return

    if not ja_enriquecido or "lat" not in df.columns:
        df = enriquecer_geo(df)

    cob = cobertura_geo(df)
    d_geo = df.dropna(subset=["lat", "lon"]).copy()
    if d_geo.empty:
        st.info(
            "Nenhuma falha deste escopo pôde ser georreferenciada "
            f"(cobertura: {cob['com_geo']}/{cob['total']})."
        )
        return

    # Decide granularidade
    frac_km = 0.0
    if "geo_fonte" in d_geo.columns:
        frac_km = float((d_geo["geo_fonte"] == "km").mean())
    if granularidade == "auto":
        granularidade = "nota" if frac_km >= 0.5 else "segmento"

    if granularidade == "nota":
        n_exato = int((d_geo["geo_fonte"] == "km").sum()) if "geo_fonte" in d_geo.columns else 0
        st.caption(
            "Cada ponto = uma nota no **KM exato** (lat/long dos marcos do KMZ) · "
            "linha cinza = **traçado da via** · cor = score · 🟣 = crônico. "
            f"📍 {cob['com_geo']}/{cob['total']} georreferenciadas "
            f"({cob['pct']}%) · {n_exato} no KM exato."
        )
    else:
        st.caption(
            "Pontos **agregados por local** (sem KM na origem — ex.: RASF/EE) · "
            "linha cinza = traçado da via · tamanho = volume · cor = score. "
            f"📍 {cob['com_geo']}/{cob['total']} georreferenciadas ({cob['pct']}%)."
        )

    if _HAS_FOLIUM:
        try:
            if granularidade == "nota":
                _render_folium_notas(d_geo, escopo)
            else:
                g = _agregar_pontos(d_geo)
                _render_folium_segmento(g, d_geo, escopo)
            return
        except Exception as e:  # pragma: no cover
            st.caption(f"⚠️ Folium indisponível ({e}); usando Plotly.")

    if _HAS_PLOTLY:
        try:
            if granularidade == "nota":
                _render_plotly(d_geo, escopo, individual=True)
            else:
                _render_plotly(_agregar_pontos(d_geo), escopo, individual=False)
            return
        except Exception as e:  # pragma: no cover
            st.caption(f"⚠️ Plotly mapbox indisponível ({e}); usando st.map.")

    st.map(d_geo[["lat", "lon"]])
