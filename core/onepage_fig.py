# =============================================================================
# core/onepage_fig.py — One Page como UMA figura Plotly 16:9
#
# A figura é a tela e a exportação ao mesmo tempo (mesma biblioteca do resto
# do Sentinel): PNG em alta resolução pelo botão de câmera do Plotly
# (CONFIG_EXPORTACAO, gerado no navegador — sem kaleido/Chrome no servidor) e
# HTML interativo por download. Entrada: o dict de core/onepage.montar_onepage.
#
# Composição (coordenadas "paper", 1280 × 720):
#   faixa do título · 5 indicadores · O TRECHO (restrições + dormentação no
#   mesmo eixo de km) · TRAVAMENTO (7 pontos) · DESTAQUES (3 frases) · fonte.
# =============================================================================

import re
import textwrap

import plotly.graph_objects as go

from core import cores_itirapina as cores
from core.analise_trecho import TRECHO_KM
from core.onepage_textos import _n

LARGURA, ALTURA = 1280, 720
FONTE = "Inter, 'Segoe UI', Arial, sans-serif"
TINTA, CINZA, CLARO, FUNDO = "#0f172a", "#64748b", "#e2e8f0", "#f8fafc"
COR_VALOR = {"bom": "#15803d", "ruim": "#b91c1c", "neutro": TINTA}


def config_exportacao(nome: str) -> dict:
    """config do st.plotly_chart: só o botão de câmera, PNG 2× (2560 × 1440)."""
    return {"displaylogo": False, "modeBarButtons": [["toImage"]], "displayModeBar": True,
            "toImageButtonOptions": {"format": "png", "filename": nome, "width": LARGURA,
                                     "height": ALTURA, "scale": 2}}


def _html(txt: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)


def _rect(fig, x0, y0, x1, y1, cor, linha=None, larg=0, camada="below"):
    fig.add_shape(type="rect", xref="paper", yref="paper", x0=x0, y0=y0, x1=x1, y1=y1, fillcolor=cor,
                  line=dict(color=linha or cor, width=larg), layer=camada)


def _txt(fig, x, y, t, tam=11, cor=TINTA, xa="left", ya="middle", negrito=False):
    fig.add_annotation(xref="paper", yref="paper", x=x, y=y, text=f"<b>{t}</b>" if negrito else t,
                       showarrow=False, xanchor=xa, yanchor=ya, align=xa if xa != "center" else "center",
                       font=dict(size=tam, color=cor, family=FONTE))


def _cabecalho(fig, o):
    _rect(fig, 0, 0.885, 1, 1, cores.AZUL)
    _rect(fig, 0, 0.885, 1, 0.892, cores.LARANJA)
    _txt(fig, 0.025, 0.955, "MANUTENÇÃO DE VIA · ITIRAPINA–PEDERNEIRAS", 22, "white", negrito=True)
    _txt(fig, 0.025, 0.912, o["subtitulo"], 12, "#cbd5e1")
    if o["modo"] == "evolucao":
        selo, data = "SITUAÇÃO EM", f"{o['data_atual']:%d/%m/%Y}"
        sub = f"marco zero {o['data_mz']:%d/%m/%Y}"
    else:
        selo, data, sub = "PONTO DE PARTIDA", f"{o['data_mz']:%d/%m/%Y}", "onde a Manutenção começa"
    _txt(fig, 0.975, 0.965, selo, 10, "#cbd5e1", xa="right")
    _txt(fig, 0.975, 0.935, data, 20, "white", xa="right", negrito=True)
    _txt(fig, 0.975, 0.905, sub, 10, "#cbd5e1", xa="right")


def _indicadores(fig, o):
    cs = o["cards"]
    n, gap, x0, x1 = len(cs), 0.012, 0.025, 0.975
    larg = (x1 - x0 - gap * (n - 1)) / n
    y0, y1 = 0.665, 0.855
    for i, c in enumerate(cs):
        a = x0 + i * (larg + gap)
        _rect(fig, a, y0, a + larg, y1, "white", CLARO, 1)
        _rect(fig, a, y1 - 0.008, a + larg, y1, cores.AZUL if c["destaque"] else "#94a3b8")
        _txt(fig, a + 0.012, y1 - 0.03, c["titulo"], 10.5, CINZA, negrito=True)
        cor = COR_VALOR[c["cor"]]
        if c.get("antes"):
            _txt(fig, a + 0.012, y0 + 0.098, f"{c['antes']}  →", 15, "#94a3b8", ya="bottom")
            _txt(fig, a + 0.012 + 0.0075 * (len(str(c["antes"])) + 3.4), y0 + 0.092, c["valor"], 30, cor,
                 ya="bottom", negrito=True)
        else:
            _txt(fig, a + 0.012, y0 + 0.092, c["valor"], 30, cor, ya="bottom", negrito=True)
        if c.get("delta"):
            _txt(fig, a + larg - 0.01, y1 - 0.03, c["delta"], 11, cor, xa="right", negrito=True)
        if c.get("progresso") is not None:
            p = max(0.0, min(1.0, float(c["progresso"])))
            _rect(fig, a + 0.012, y0 + 0.058, a + larg - 0.012, y0 + 0.07, CLARO)
            _rect(fig, a + 0.012, y0 + 0.058, a + 0.012 + (larg - 0.024) * p, y0 + 0.07, "#15803d")
        _txt(fig, a + 0.012, y0 + 0.028, c["rodape"], 10, CINZA)


def _trecho(fig, o):
    _txt(fig, 0.025, 0.625, "O TRECHO", 12, cores.AZUL, negrito=True)
    _txt(fig, 0.105, 0.625, "cada restrição no km real · faixa de baixo = dormentes inservíveis por equipamento",
         10, CINZA)
    # legenda
    leg = [(cores.VIA, "via (Manutenção)"), (cores.ANTT, "ANTT/PN/urbano"), (cores.RETIRADA, "retirada")]
    x = 0.68
    for cor, t in leg:
        _rect(fig, x, 0.618, x + 0.012, 0.632, cor)
        _txt(fig, x + 0.016, 0.625, t, 10, CINZA)
        x += 0.016 + 0.0062 * len(t) + 0.02
    # eixo 1: restrições
    fig.add_shape(type="line", xref="x", yref="y", x0=TRECHO_KM[0], x1=TRECHO_KM[1], y0=0, y1=0,
                  line=dict(color="#334155", width=4))
    e = o["estacoes"]
    if len(e):
        e = e[(e["km_fim"] >= TRECHO_KM[0] - 6) & (e["km_inicio"] <= TRECHO_KM[1])]
        km = e[["km_inicio", "km_fim"]].mean(axis=1).clip(*TRECHO_KM)
        fig.add_trace(go.Scatter(x=km, y=[-0.42] * len(e), mode="text", text=e["codigo"], xaxis="x", yaxis="y",
                                 textfont=dict(size=9, color=CINZA, family=FONTE), hoverinfo="skip"))
        for k in km:
            fig.add_shape(type="line", xref="x", yref="y", x0=k, x1=k, y0=-0.2, y1=0.2,
                          line=dict(color="#334155", width=1.5))
    r = o["restricoes"]
    if len(r):
        niveis, meia = 4, 7.0
        fim = [-1e9] * niveis
        for x in r.sort_values("a").itertuples():
            via = x.grupo == "via" or x.status == "retirada"
            cor = cores.RETIRADA if x.status == "retirada" else cores.VIA if x.grupo == "via" else cores.ANTT
            h = 0.22 if via else 0.13
            fig.add_shape(type="rect", xref="x", yref="y", x0=x.a - 0.3, x1=max(x.b, x.a) + 0.3, y0=-h, y1=h,
                          fillcolor=cor, line_width=0, opacity=1 if via else 0.75)
            if not via:
                continue          # só as de via ganham rótulo (as de terceiros ficam no hover)
            meio = (x.a + x.b) / 2
            t = next((i for i, f in enumerate(fim) if meio - meia > f), None)
            t = t if t is not None else min(range(niveis), key=lambda i: fim[i])
            fim[t] = meio + meia
            y = 0.5 + 0.27 * t
            rot = f"{x.vel:.0f} km/h · {x.motivo}"
            if x.status == "retirada":
                rot = "✔ " + rot
            fig.add_shape(type="line", xref="x", yref="y", x0=meio, x1=meio, y0=h, y1=y - 0.1,
                          line=dict(color=cor, width=1))
            fig.add_annotation(x=meio, y=y, xref="x", yref="y", text=rot, showarrow=False,
                               font=dict(size=9.5, color=cor, family=FONTE), bgcolor="white")
        fig.add_trace(go.Scatter(
            x=(r["a"] + r["b"]) / 2, y=[0] * len(r), mode="markers", marker=dict(size=12, opacity=0),
            xaxis="x", yaxis="y", hovertemplate="%{text}<extra></extra>",
            text=[f"{x.vel:.0f} km/h · {x.motivo} · km {_n(x.a, 1)} · {x.grupo} · {x.status}" for x in r.itertuples()]))
    # eixo 2: dormentação (LP)
    d = o["dorm"]
    lp = d[d["linha"] == "LP"] if len(d) else d
    if len(lp):
        fig.add_trace(go.Bar(
            x=(lp["km_fim"] - lp["km_inicio"]).abs(), base=lp["km_inicio"], y=[0] * len(lp), orientation="h",
            width=1, xaxis="x2", yaxis="y2",
            marker=dict(color=[cores.cor_por_faixa(v, cores.LIMIARES_SLIDE, cores.CORES_SLIDE)
                               for v in lp["taxa_pct"]], line_width=0),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=[f"{r.equipamento_siv} · {_n(r.taxa_pct, 1)}% inservíveis" for r in lp.itertuples()]))
    p = o["pontos"]
    if len(p):
        for x in p[p["ponto"].astype(str).str.match(r"^[CT]\d$")].itertuples():
            fig.add_annotation(x=(x.km_inicio + x.km_fim) / 2, y=0.5, xref="x2", yref="y2", text=f"<b>{x.ponto}</b>",
                               showarrow=False, yanchor="bottom", yshift=2,
                               font=dict(size=9, color=cores.AZUL, family=FONTE))
    x = 0.68
    for c, t in zip(cores.CORES_SLIDE, ("≤10%", "10–20", "20–30", "30–40", ">40%")):
        _rect(fig, x, 0.312, x + 0.012, 0.324, c)
        _txt(fig, x + 0.015, 0.318, t, 9, CINZA)
        x += 0.058


def _travamento(fig, o):
    _txt(fig, 0.025, 0.29, "TRAVAMENTO DOS PONTOS CRÍTICOS", 12, cores.AZUL, negrito=True)
    p = o["travamento"]
    if len(p) == 0:
        return
    p = p.sort_values("ponto_critico", ascending=False)
    rot = [f"{r.ponto_critico}  km {_n(r.km_inicio, 1)}" for r in p.itertuples()]
    fig.add_trace(go.Bar(x=[100] * len(p), y=rot, orientation="h", xaxis="x3", yaxis="y3",
                         marker=dict(color=CLARO), hoverinfo="skip", width=0.62))
    fig.add_trace(go.Bar(x=p["pct"] * 100, y=rot, orientation="h", xaxis="x3", yaxis="y3", width=0.62,
                         marker=dict(color=[cores.SITUACAO[s] if s != "a iniciar" else "#94a3b8"
                                            for s in p["situacao"]]),
                         text=[f"{_n(r.pct * 100)}% de {_n(r.travamento)} dorm." for r in p.itertuples()],
                         textposition="outside", textfont=dict(size=9.5, color=CINZA, family=FONTE),
                         cliponaxis=False, hovertemplate="%{y}: %{x:.0f}%<extra></extra>"))


def _destaques(fig, o):
    titulo = "O PLANO" if o["modo"] == "partida" else "DESTAQUES"
    _txt(fig, 0.53, 0.29, titulo, 12, cores.AZUL, negrito=True)
    y = 0.262
    for f in o["frases"][:3]:
        linhas = textwrap.wrap(f, 70)
        h = 0.016 + 0.027 * len(linhas)
        _rect(fig, 0.53, y - h, 0.975, y, FUNDO, CLARO, 1)
        _rect(fig, 0.53, y - h, 0.535, y, cores.LARANJA)
        _txt(fig, 0.545, y - h / 2, "<br>".join(_html(l) for l in linhas), 11.5, TINTA)
        y -= h + 0.012


def fig_onepage(o: dict) -> go.Figure:
    fig = go.Figure()
    _cabecalho(fig, o)
    _indicadores(fig, o)
    _trecho(fig, o)
    _travamento(fig, o)
    _destaques(fig, o)
    _txt(fig, 0.025, 0.012, o["fontes"], 8.5, "#94a3b8", ya="bottom")
    rng = [TRECHO_KM[0] - 1, TRECHO_KM[1] + 1]
    fig.update_layout(
        width=LARGURA, height=ALTURA, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="white",
        plot_bgcolor="white", showlegend=False, barmode="overlay", font=dict(family=FONTE),
        hoverlabel=dict(font=dict(family=FONTE, size=11)),
        xaxis=dict(domain=[0.025, 0.975], range=rng, visible=False, fixedrange=True),
        yaxis=dict(domain=[0.415, 0.605], range=[-0.6, 1.4], visible=False, fixedrange=True),
        xaxis2=dict(domain=[0.025, 0.975], range=rng, matches="x", fixedrange=True, ticks="outside", anchor="y2",
                    tickfont=dict(size=9, color=CINZA), showgrid=False, ticksuffix=" km", dtick=10,
                    showline=False, zeroline=False),
        yaxis2=dict(domain=[0.37, 0.395], range=[-0.5, 0.5], visible=False, fixedrange=True, anchor="x2"),
        xaxis3=dict(domain=[0.12, 0.40], range=[0, 100], visible=False, fixedrange=True),
        yaxis3=dict(domain=[0.045, 0.265], anchor="x3", tickfont=dict(size=10, color=TINTA, family=FONTE),
                    fixedrange=True, ticklabelstandoff=6),
    )
    fig.update_layout(yaxis3=dict(anchor="x3"), xaxis3=dict(anchor="y3"))
    return fig


def html_onepage(fig: go.Figure) -> bytes:
    """HTML autocontido (plotly.js embutido): abre offline e imprime em PDF pelo navegador."""
    return fig.to_html(full_html=True, include_plotlyjs=True, config={"displaylogo": False}).encode("utf-8")
