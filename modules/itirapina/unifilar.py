# =============================================================================
# modules/itirapina/unifilar.py — Unifilar do trecho Itirapina–Pederneiras
#
# Faixas empilhadas no mesmo eixo de KM (make_subplots, shared_xaxes):
#   Pátios · Velocidade (VMA × praticada × restrições A) · Restrições B ·
#   Dormentes (taxa; opcional base A para comparar) · Defeitos/km por
#   equipamento · Vagão de Via (tamanho ÷ limite da classe da VMA; linha 1,0)
#   · Inspeção de campo (vazado = km estimado).
# Pátios: linhas verticais tracejadas atravessando todas as faixas.
# Pontos críticos C/T: rótulo a 90° com km exato + código SIV (lição nº 10).
# Faixas sem dado não aparecem.
# =============================================================================

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.analise_trecho import TRECHO_KM
from core.parser_inspecao import nivel_gravidade

CORES_CATEGORIA = {
    "Via permanente":           "#dc2626",
    "Externa (ANTT/PN/urbano)": "#f59e0b",
    "OAE":                      "#7c3aed",
    "Outras":                   "#64748b",
}
CORES_GRAVIDADE = {0: "#64748b", 1: "#f59e0b", 2: "#ea580c", 3: "#dc2626"}
SIMBOLO_TEMA = {"trilho": "line-ns", "lastro": "circle", "AMV": "diamond", "dormente": "square",
                "PN": "triangle-up", "junta": "x", "OAE": "star", "pátio": "hexagon", "drenagem": "cross"}


def _simbolo(tema) -> str:
    t = str(tema or "")
    for k, s in SIMBOLO_TEMA.items():
        if t.lower().startswith(k.lower()):
            return s
    return "circle"


def _degraus(p: pd.DataFrame, col: str) -> tuple[list, list]:
    xs, ys, fim = [], [], None
    for r in p.itertuples():
        v = getattr(r, col)
        if fim is not None and abs(r.km_de - fim) > 1e-6:
            xs.append(None)
            ys.append(None)
        xs += [r.km_de, r.km_ate]
        ys += [None if pd.isna(v) else v] * 2
        fim = r.km_ate
    return xs, ys


def fig_unifilar_trecho(p: pd.DataFrame, rB: pd.DataFrame, trem: str, *,
                        seg: pd.DataFrame | None = None, seg_a: pd.DataFrame | None = None,
                        rotulo_a: str = "Base A", estacoes: pd.DataFrame | None = None,
                        def_eq: pd.DataFrame | None = None, vagao: pd.DataFrame | None = None,
                        insp: pd.DataFrame | None = None, pontos: pd.DataFrame | None = None,
                        x_range=TRECHO_KM) -> go.Figure:
    def tem(df):
        return df is not None and not df.empty
    faixas = []
    if tem(estacoes):
        faixas.append(("patios", 0.05))
    faixas += [("vel", 0.34), ("rb", 0.06)]
    if tem(seg):
        faixas.append(("dorm", 0.12 if not tem(seg_a) else 0.16))
    if tem(def_eq):
        faixas.append(("def", 0.07))
    if tem(vagao):
        faixas.append(("vagao", 0.16))
    if tem(insp):
        faixas.append(("insp", 0.07))
    tot = sum(h for _, h in faixas)
    fig = make_subplots(rows=len(faixas), cols=1, shared_xaxes=True, vertical_spacing=0.018,
                        row_heights=[h / tot for _, h in faixas])
    linha_de = {nome: i + 1 for i, (nome, _) in enumerate(faixas)}

    # ── Pátios ───────────────────────────────────────────────────────────────
    if tem(estacoes):
        e = estacoes.sort_values("km_inicio")
        fig.add_trace(go.Bar(
            orientation="h", y=["Pátios"] * len(e), base=e["km_inicio"],
            x=(e["km_fim"] - e["km_inicio"]).clip(lower=0.25), text=e["codigo"],
            textposition="inside", insidetextanchor="middle", marker_color="#cbd5e1",
            hovertext=[f"<b>{r.codigo}</b> · {r.nome}<br>km {r.km_inicio:.3f}–{r.km_fim:.3f}"
                       for r in e.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", showlegend=False, width=0.8),
            row=linha_de["patios"], col=1)
        # Uma linha por pátio na altura da figura toda (yref=paper): os eixos X
        # são compartilhados, então o km vale para todas as faixas.
        for km in e["km_inicio"]:
            if x_range[0] <= km <= x_range[1]:
                fig.add_shape(type="line", xref="x", yref="paper", x0=km, x1=km, y0=0, y1=1,
                              line=dict(color="#94a3b8", width=1, dash="dot"), layer="below")

    # ── Velocidade ───────────────────────────────────────────────────────────
    rv = linha_de["vel"]
    x, y = _degraus(p, "vma")
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=f"VMA {trem}",
                             line=dict(color="#94a3b8", width=2, dash="dash"),
                             hovertemplate="km %{x:.1f}<br>VMA %{y:.0f} km/h<extra></extra>"),
                  row=rv, col=1)
    x, y = _degraus(p, "v_prat")
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Velocidade praticada",
                             line=dict(color="#1e3a5f", width=2), fill="tozeroy",
                             fillcolor="rgba(30,58,95,0.08)",
                             hovertemplate="km %{x:.1f}<br>Praticada %{y:.0f} km/h<extra></extra>"),
                  row=rv, col=1)
    restr = p[p["restrito"]] if "restrito" in p else p.iloc[0:0]
    for cat, cor in CORES_CATEGORIA.items():
        sub = restr[restr["categoria"] == cat]
        if sub.empty:
            continue
        xs, ys, txt = [], [], []
        for r in sub.itertuples():
            vma = f" (VMA {r.vma:.0f})" if pd.notna(r.vma) else ""
            h = f"<b>{r.motivo}</b><br>SB {r.sb} · km {r.km_de:.1f}–{r.km_ate:.1f}<br>{r.v_prat:.0f} km/h{vma}"
            xs += [r.km_de, r.km_ate, None]
            ys += [r.v_prat, r.v_prat, None]
            txt += [h, h, None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=f"Restrição · {cat}",
                                 line=dict(color=cor, width=7), hovertext=txt,
                                 hovertemplate="%{hovertext}<extra></extra>"), row=rv, col=1)
    fig.update_yaxes(title_text="km/h", rangemode="tozero", row=rv, col=1)
    if tem(pontos):
        for r in pontos[pontos["ponto"].str.match(r"^[CT]\d$", na=False)].itertuples():
            eq = getattr(r, "equipamento_siv", None)
            eq = f" · {eq}" if isinstance(eq, str) else ""
            fig.add_annotation(x=r.km_inicio, y=1.0, yref=f"y{rv if rv > 1 else ''} domain",
                               xref=f"x{rv if rv > 1 else ''}", text=f"{r.ponto} km {r.km_inicio:.3f}{eq}",
                               textangle=-90, showarrow=False, xanchor="left", yanchor="top",
                               font=dict(size=9, color="#7c3aed"))

    # ── Restrições B ─────────────────────────────────────────────────────────
    rr = linha_de["rb"]
    if tem(rB):
        pare = rB["condicao"].fillna("").str.contains("sim", case=False)
        fmt = lambda d: d.strftime("%d/%m %H:%M") if pd.notna(d) else "—"  # noqa: E731
        fig.add_trace(go.Bar(
            orientation="h", y=["Restr. B"] * len(rB), base=rB["a"], x=rB["b"] - rB["a"],
            marker=dict(color=np.where(pare, "#dc2626", "#f59e0b")),
            hovertext=[f"<b>{r.sb}</b> · {r.condicao}<br>km {r.a:.1f}–{r.b:.1f}<br>Resp. {r.responsavel}"
                       f"<br>{fmt(r.inicio)} → {fmt(r.fim)}" for r in rB.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", showlegend=False, width=0.6), row=rr, col=1)
    else:
        fig.add_trace(go.Bar(orientation="h", y=["Restr. B"], base=[x_range[0]], x=[0],
                             showlegend=False, hoverinfo="skip"), row=rr, col=1)

    # ── Dormentes ────────────────────────────────────────────────────────────
    if tem(seg):
        rd = linha_de["dorm"]
        def _barras(s, rotulo, contorno):
            return go.Bar(
                orientation="h", y=[rotulo] * len(s), base=s["km_inicio"], x=s["extensao_km"],
                marker=dict(color=s["taxa_pct"].clip(upper=50), colorscale="RdYlGn_r", cmin=0, cmax=50,
                            opacity=0.45 if contorno else 1,
                            line=dict(width=1.2 if contorno else 0.3,
                                      color="#1e3a5f" if contorno else "#fff"),
                            colorbar=None if contorno else dict(
                                title=dict(text="Inserv. %", side="right"), thickness=10, len=0.25)),
                hovertext=[f"<b>{r.equipamento_siv}</b> · {rotulo}<br>km {r.km_inicio:.3f}–{r.km_fim:.3f}"
                           f"<br>Inservíveis {r.taxa_pct:.1f}%" for r in s.itertuples()],
                hovertemplate="%{hovertext}<extra></extra>", showlegend=False, width=0.8)
        fig.add_trace(_barras(seg, "Dormentes", False), row=rd, col=1)
        if tem(seg_a):
            fig.add_trace(_barras(seg_a, rotulo_a, True), row=rd, col=1)

    # ── Defeitos por km ──────────────────────────────────────────────────────
    if tem(def_eq):
        d = def_eq.dropna(subset=["def_por_km"])
        fig.add_trace(go.Bar(
            orientation="h", y=["Defeitos/km"] * len(d), base=d["km_inicio"],
            x=(d["km_fim"] - d["km_inicio"]).abs(),
            marker=dict(color=d["def_por_km"].clip(upper=150), colorscale="Reds", cmin=0, cmax=150),
            hovertext=[f"<b>{r.equipamento_siv}</b><br>{r.defeitos:.0f} defeitos · {r.def_por_km:.0f}/km"
                       for r in d.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", showlegend=False, width=0.8),
            row=linha_de["def"], col=1)

    # ── Vagão de Via ─────────────────────────────────────────────────────────
    if tem(vagao):
        rg = linha_de["vagao"]
        v = vagao.copy()
        usa_razao = "razao_limite" in v and v["razao_limite"].notna().any()
        v["y"] = v["razao_limite"] if usa_razao else v["tamanho"]
        v = v.dropna(subset=["y"])
        vel = v["vel_max_classe_kmh"].fillna(130)
        fig.add_trace(go.Scatter(
            x=v["km"], y=v["y"], mode="markers", name="Vagão de Via",
            marker=dict(size=7, color=vel.clip(upper=80), colorscale="RdYlGn", cmin=15, cmax=80,
                        line=dict(width=0.5, color="#fff"), showscale=False),
            hovertext=[f"<b>{r.nome_defeito}</b> · viagem {int(r.numero_viagem) if pd.notna(r.numero_viagem) else '—'}"
                       f"<br>km {r.km:.3f} · tamanho {r.tamanho:.1f}<br>{r.classe_via}"
                       + (f"<br>limite {r.classe_vma} (VMA {r.vma:.0f}): {r.limite_mm:.0f} → {r.razao_limite:.2f}×"
                          if usa_razao and pd.notna(getattr(r, 'razao_limite', np.nan)) else "")
                       for r in v.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>"), row=rg, col=1)
        if usa_razao:
            fig.add_hline(y=1.0, line=dict(color="#dc2626", dash="dash", width=1), row=rg, col=1)
        fig.update_yaxes(title_text="÷ limite" if usa_razao else "tamanho", row=rg, col=1)

    # ── Inspeção de campo ────────────────────────────────────────────────────
    if tem(insp):
        i = insp.dropna(subset=["km"]).copy()
        i["nivel"] = i["gravidade"].map(nivel_gravidade)
        estimado = i["km_fonte"].astype(str).str.startswith("estim")
        fig.add_trace(go.Scatter(
            x=i["km"], y=["Inspeção"] * len(i), mode="markers", name="Inspeção de campo",
            marker=dict(size=11, symbol=[_simbolo(t) + ("-open" if e else "") for t, e in zip(i["tema"], estimado)],
                        color=i["nivel"].map(CORES_GRAVIDADE), line=dict(width=1.5, color=i["nivel"].map(CORES_GRAVIDADE))),
            hovertext=[f"<b>{r.tema or '—'}</b> · msg {r.msg_n}<br>{r.descricao or ''}<br>"
                       f"km {r.km:.3f} ({r.km_fonte}) · gravidade {r.gravidade or '—'}"
                       for r in i.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", showlegend=False), row=linha_de["insp"], col=1)

    n = len(faixas)
    fig.update_xaxes(range=list(x_range), row=n, col=1, title_text="KM", showgrid=True, gridcolor="#e5e7eb")
    for k in range(1, n + 1):
        fig.update_xaxes(range=list(x_range), row=k, col=1)
    fig.update_layout(
        height=int(260 + 600 * tot), margin=dict(l=10, r=10, t=40, b=40),
        plot_bgcolor="#ffffff", hovermode="closest", barmode="overlay",
        legend=dict(orientation="h", y=1.04, x=0, font=dict(size=11)),
    )
    return fig
