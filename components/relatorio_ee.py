# =============================================================================
# components/relatorio_ee.py — Relatório HTML autônomo da Inteligência EE
#
# Gera um único arquivo .html (sem dependências externas além de uma fonte
# via Google Fonts, com fallback de sistema) a partir do recorte JÁ FILTRADO
# na tela de Inteligência de Falhas EE — mesmos números que o usuário está
# vendo, prontos pra abrir em qualquer navegador ou anexar num e-mail.
#
# Estética inspirada no pitch SGO Eletroeletrônica (fundo escuro navy, texto
# em gradiente dourado/ciano, cards com blur, barras em cascata) — só que
# estática (sem slides/animação contínua), pensada pra rolagem/impressão.
#
# Uso: gerar_relatorio_html(df, escopo) -> str (HTML completo)
#   df já deve estar filtrado + enriquecido (mesmo df que alimenta os blocos
#   de components/inteligencia_ee.py — chamar DEPOIS de _enriquecer()).
# =============================================================================

import html as _html
from datetime import date, datetime

import pandas as pd

try:
    from core.glossarios import ativo_curto, nome_ramal
except Exception:
    def ativo_curto(s):
        return str(s or "")

    def nome_ramal(s, *a, **k):
        return s


# region ====================== SESSÃO 1: Helpers de formatação ================

def _e(v) -> str:
    """Escapa texto livre do RASF antes de embutir no HTML (evita quebrar o
    documento ou injetar markup a partir de um valor da planilha)."""
    return _html.escape(str(v)) if v is not None else ""


def _fmt_int(v) -> str:
    try:
        return f"{int(round(v)):,}".replace(",", ".")
    except Exception:
        return "0"


def _fmt_h(v) -> str:
    try:
        return f"{v:,.0f} h".replace(",", ".")
    except Exception:
        return "0 h"


def _trunc(s, limite: int = 46) -> str:
    s = str(s)
    if len(s) <= limite:
        return s
    cortado = s[:limite].rsplit(" ", 1)[0]
    return (cortado or s[:limite]) + "…"


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


_HEAT_STOPS = [
    (0.00, (13, 23, 42)),
    (0.35, (30, 90, 140)),
    (0.65, (57, 180, 190)),
    (0.85, (243, 177, 60)),
    (1.00, (255, 90, 126)),
]


def _heat_color(intensidade: float) -> str:
    """Interpola entre os _HEAT_STOPS pra dar a cor de uma célula do
    mapa de calor estático (0=frio/escuro, 1=quente)."""
    t = max(0.0, min(1.0, intensidade))
    for i in range(len(_HEAT_STOPS) - 1):
        t0, c0 = _HEAT_STOPS[i]
        t1, c1 = _HEAT_STOPS[i + 1]
        if t0 <= t <= t1:
            local_t = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            r = _lerp(c0[0], c1[0], local_t)
            g = _lerp(c0[1], c1[1], local_t)
            b = _lerp(c0[2], c1[2], local_t)
            return f"rgb({r},{g},{b})"
    return "rgb(13,23,42)"

# endregion


# region ====================== SESSÃO 2: Componentes HTML ======================

_PALETA_BARRAS = ["#39d6e8", "#f3b13c", "#9b7bff", "#37e07e", "#ff5a7e"]


def _kpi_tile(label: str, valor: str, sub: str, cor: str) -> str:
    return (
        f'<div class="kpi" style="--c:{cor}">'
        f'<div class="kpi-lbl">{_e(label)}</div>'
        f'<div class="kpi-val">{_e(valor)}</div>'
        f'<div class="kpi-sub">{_e(sub)}</div>'
        f'</div>'
    )


def _casc_bar(rank: int, label: str, valor_fmt: str, pct_largura: float, meta: str) -> str:
    cor = _PALETA_BARRAS[(rank - 1) % len(_PALETA_BARRAS)]
    largura = max(6, round(pct_largura))
    return (
        f'<div class="prow">'
        f'<div class="rk" style="color:{cor};border-color:{cor}">{rank}</div>'
        f'<div class="bar" style="width:{largura}%;background:linear-gradient(90deg,{cor},{cor}99)">'
        f'{_e(label)} <b>{_e(valor_fmt)}</b></div>'
        f'<div class="meta">{_e(meta)}</div>'
        f'</div>'
    )


def _secao_cascata(titulo: str, kicker: str, linhas: list, vazio_msg: str) -> str:
    if not linhas:
        corpo = f'<p class="vazio">{_e(vazio_msg)}</p>'
    else:
        corpo = '<div class="casc">' + "".join(linhas) + "</div>"
    return (
        f'<section class="sec">'
        f'<div class="sec-head"><span class="kicker">{_e(kicker)}</span><h2>{titulo}</h2></div>'
        f'{corpo}'
        f'</section>'
    )

# endregion


# region ====================== SESSÃO 3: Cálculos (mesma lógica da tela) =======

def _calc_resumo(df: pd.DataFrame) -> list:
    cards = []
    col_ativo = "local_instalacao"

    grp_falhas = df.groupby(col_ativo).size()
    if not grp_falhas.empty:
        ativo_top = grp_falhas.idxmax()
        falhas_top = int(grp_falhas.max())
        sub_df = df[df[col_ativo] == ativo_top]
        moda = sub_df["tipo_falha"].dropna().mode() if "tipo_falha" in sub_df.columns else pd.Series(dtype=object)
        tipo_txt = str(moda.iloc[0]) if not moda.empty else "—"
        cards.append(_kpi_tile(
            "Ativo com mais falhas", ativo_curto(ativo_top),
            f"{_fmt_int(falhas_top)} falhas · tipo mais comum: {tipo_txt}", "#1e3a5f",
        ))
    else:
        cards.append(_kpi_tile("Ativo com mais falhas", "—", "", "#1e3a5f"))

    grp_thp = df.groupby(col_ativo)["thp_h"].sum()
    if not grp_thp.empty and grp_thp.max() > 0:
        ativo_thp_top = grp_thp.idxmax()
        cards.append(_kpi_tile(
            "Ativo com maior THP", ativo_curto(ativo_thp_top),
            f"{_fmt_h(float(grp_thp.max()))} · {_fmt_int(int(grp_falhas.get(ativo_thp_top, 0)))} falhas",
            "#0ea5e9",
        ))
    else:
        cards.append(_kpi_tile("Ativo com maior THP", "—", "", "#0ea5e9"))

    if "reincidencia_ativo" in df.columns:
        grp_reincid = df.groupby(col_ativo)["reincidencia_ativo"].sum()
        if not grp_reincid.empty and grp_reincid.max() > 0:
            ativo_reincid_top = grp_reincid.idxmax()
            cards.append(_kpi_tile(
                "Ativo mais reincidente", ativo_curto(ativo_reincid_top),
                f"{_fmt_int(int(grp_reincid.max()))} reincidências (90d)", "#7c3aed",
            ))
        else:
            cards.append(_kpi_tile("Ativo mais reincidente", "—", "", "#7c3aed"))

    if "anomalia_sintoma" in df.columns:
        grp_sint_thp = df.groupby("anomalia_sintoma")["thp_h"].sum()
        if not grp_sint_thp.empty and grp_sint_thp.max() > 0:
            sintoma_top = grp_sint_thp.idxmax()
            cards.append(_kpi_tile(
                "Sintoma mais crítico (THP)", _trunc(sintoma_top, 34),
                f"{_fmt_h(float(grp_sint_thp.max()))} de trem parado", "#dc2626",
            ))
        else:
            cards.append(_kpi_tile("Sintoma mais crítico (THP)", "—", "", "#dc2626"))

    if "origem_efetiva" in df.columns:
        grp_origem = df["origem_efetiva"].value_counts()
        if not grp_origem.empty:
            origem_top = grp_origem.idxmax()
            qtd_top = int(grp_origem.max())
            pct = 100 * qtd_top / len(df) if len(df) else 0
            cards.append(_kpi_tile(
                "Origem mais frequente", _trunc(origem_top, 34),
                f"{_fmt_int(qtd_top)} falhas · {pct:.0f}% do total", "#f59e0b",
            ))
        else:
            cards.append(_kpi_tile("Origem mais frequente", "—", "", "#f59e0b"))

    return cards


def _calc_pareto_sintomas(df: pd.DataFrame, top_n: int = 10) -> list:
    if "anomalia_sintoma" not in df.columns:
        return []
    g = (
        df.groupby("anomalia_sintoma")
          .agg(qtd=("anomalia_sintoma", "size"), thp_h=("thp_h", "sum"))
          .sort_values("qtd", ascending=False)
          .head(top_n)
          .reset_index()
    )
    if g.empty:
        return []
    maxv = g["qtd"].max()
    linhas = []
    for i, r in enumerate(g.itertuples(), start=1):
        linhas.append(_casc_bar(
            i, _trunc(r.anomalia_sintoma, 52), f"{_fmt_int(r.qtd)}",
            100 * r.qtd / maxv, f"THP {_fmt_h(r.thp_h)}",
        ))
    return linhas


def _calc_obras_manutencao(df: pd.DataFrame, top_n: int = 10) -> list:
    if "origem_efetiva" not in df.columns:
        return []
    g = (
        df.groupby("origem_efetiva")
          .agg(falhas=("origem_efetiva", "size"), thp_h=("thp_h", "sum"))
          .sort_values("falhas", ascending=False)
          .head(top_n)
          .reset_index()
    )
    if g.empty:
        return []
    maxv = g["falhas"].max()
    linhas = []
    for i, r in enumerate(g.itertuples(), start=1):
        linhas.append(_casc_bar(
            i, _trunc(r.origem_efetiva, 52), f"{_fmt_int(r.falhas)}",
            100 * r.falhas / maxv, f"THP {_fmt_h(r.thp_h)}",
        ))
    return linhas


def _calc_heatmap(df: pd.DataFrame, top_patios: int = 8, top_origens: int = 8) -> str:
    if "patio" not in df.columns or "origem_efetiva" not in df.columns:
        return '<p class="vazio">Colunas de pátio/origem indisponíveis.</p>'
    d = df.dropna(subset=["patio", "origem_efetiva"])
    if d.empty:
        return '<p class="vazio">Sem dados de pátio/origem no recorte.</p>'

    patios = d["patio"].value_counts().head(top_patios).index.tolist()
    origens = d["origem_efetiva"].value_counts().head(top_origens).index.tolist()
    d = d[d["patio"].isin(patios) & d["origem_efetiva"].isin(origens)]
    if d.empty:
        return '<p class="vazio">Sem dados suficientes pra montar o mapa de calor.</p>'

    pivot = d.groupby(["origem_efetiva", "patio"]).size().unstack(fill_value=0)
    pivot = pivot.reindex(index=origens, columns=patios, fill_value=0)
    max_val = int(pivot.values.max()) or 1

    head = "<th></th>" + "".join(f"<th>{_e(p)}</th>" for p in patios)
    linhas = []
    for origem in origens:
        celulas = ""
        for p in patios:
            v = int(pivot.loc[origem, p])
            cor = _heat_color(v / max_val)
            celulas += f'<td style="background:{cor}">{v if v else ""}</td>'
        linhas.append(f'<tr><th class="rowlbl">{_e(_trunc(origem, 30))}</th>{celulas}</tr>')

    return (
        '<div class="tblwrap"><table class="heat">'
        f'<thead><tr>{head}</tr></thead><tbody>{"".join(linhas)}</tbody>'
        '</table></div>'
    )


def _calc_ranking(df: pd.DataFrame, top_n: int = 15) -> str:
    col_ativo = "local_instalacao_desc" if "local_instalacao_desc" in df.columns else "local_instalacao"
    if col_ativo not in df.columns:
        return '<p class="vazio">Coluna de ativo indisponível.</p>'

    g = (
        df.groupby(col_ativo)
          .agg(
              falhas=(col_ativo, "size"),
              reincidencias=("reincidencia_ativo", "sum"),
              thp_h=("thp_h", "sum"),
              patio=("patio", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
              sistema=("sistema", lambda s: s.dropna().iloc[0] if s.notna().any() else "—"),
              classificacao=(
                  "origem_efetiva",
                  lambda s: s.dropna().mode().iloc[0] if not s.dropna().mode().empty else "—",
              ),
          )
          .reset_index()
          .sort_values("reincidencias", ascending=False)
          .head(top_n)
    )
    if g.empty:
        return '<p class="vazio">Sem dados de ranking no recorte.</p>'

    linhas = "".join(
        f"<tr><td>{_e(_trunc(getattr(r, col_ativo), 40))}</td>"
        f"<td>{_e(r.patio)}</td><td>{_e(r.sistema)}</td><td>{_e(_trunc(r.classificacao, 28))}</td>"
        f"<td>{_fmt_int(r.falhas)}</td><td>{_fmt_int(r.reincidencias)}</td><td>{_fmt_int(r.thp_h)} h</td></tr>"
        for r in g.itertuples()
    )
    return (
        '<div class="tblwrap"><table class="rank">'
        "<thead><tr><th>Local de Instalação</th><th>Pátio</th><th>Sistema</th>"
        "<th>Classificação</th><th>Falhas</th><th>Reincid. 90d</th><th>THP</th></tr></thead>"
        f"<tbody>{linhas}</tbody></table></div>"
    )

# endregion


# region ====================== SESSÃO 4: Documento HTML ========================

_CSS = """
:root{
  --bg:#040a16; --ink:#eef4ff; --mut:#aebfda; --dim:#6f83a6;
  --gold:#f3b13c; --gold2:#ffd479; --cyan:#39d6e8; --green:#37e07e;
  --red:#ff465e; --violet:#9b7bff;
  --line:rgba(120,160,220,.16); --panel:rgba(15,32,58,.5);
  --card:linear-gradient(155deg, rgba(15,32,58,.72), rgba(6,15,30,.5));
  --shadow:0 20px 50px rgba(0,0,0,.45);
  --font:'Manrope',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  --mono:'Space Mono','SF Mono',ui-monospace,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:var(--font);color:var(--ink);
  background:
    radial-gradient(1100px 700px at 12% -10%, rgba(57,214,232,.10), transparent),
    radial-gradient(900px 650px at 100% 0%, rgba(155,123,255,.10), transparent),
    var(--bg);
  -webkit-font-smoothing:antialiased;line-height:1.4;
}
.wrap{max-width:1180px;margin:0 auto;padding:64px 40px 100px}
.eyebrow{font-family:var(--mono);letter-spacing:.32em;text-transform:uppercase;font-size:13px;
  color:var(--gold);display:flex;align-items:center;gap:12px;margin-bottom:18px}
.eyebrow::before{content:"";width:36px;height:2px;background:linear-gradient(90deg,var(--gold),transparent)}
h1{font-size:56px;line-height:1.05;font-weight:800;letter-spacing:-.02em}
.grad{background:linear-gradient(100deg,var(--gold) 0%,var(--gold2) 45%,var(--cyan) 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.hero-sub{font-size:19px;color:var(--mut);margin-top:14px;max-width:820px}
.hrule{width:72px;height:3px;border-radius:3px;margin:20px 0 0;background:linear-gradient(90deg,var(--gold),var(--cyan))}
.metachips{display:flex;flex-wrap:wrap;gap:12px;margin-top:28px}
.metachip{display:inline-flex;align-items:center;gap:8px;padding:10px 16px;border-radius:999px;
  border:1px solid var(--line);background:var(--panel);font-size:14px;font-weight:600}
.metachip b{color:var(--cyan);font-family:var(--mono)}

.sec{margin-top:56px}
.sec-head{margin-bottom:18px}
.kicker{font-family:var(--mono);font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:var(--cyan)}
.sec h2{font-size:28px;font-weight:800;margin-top:6px}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.kpi{border:1px solid var(--line);background:var(--card);border-left:4px solid var(--c,var(--gold));
  border-radius:14px;padding:18px 18px;box-shadow:var(--shadow)}
.kpi-lbl{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;font-weight:700}
.kpi-val{font-size:19px;font-weight:800;color:var(--c,var(--gold));margin-top:6px;line-height:1.25;
  word-break:normal;overflow-wrap:anywhere}
.kpi-sub{font-size:12.5px;color:var(--dim);margin-top:6px}

.casc{display:grid;gap:12px;margin-top:6px}
.prow{display:flex;align-items:center;gap:16px}
.prow .rk{width:32px;height:32px;flex:0 0 32px;border-radius:9px;display:grid;place-items:center;
  font-weight:800;font-size:14px;font-family:var(--mono);border:1px solid currentColor}
.prow .bar{height:38px;border-radius:9px;display:flex;align-items:center;gap:8px;padding:0 16px;
  font-size:14px;font-weight:700;color:#04121a;white-space:nowrap;box-shadow:0 6px 18px -6px rgba(0,0,0,.5);
  min-width:120px}
.prow .bar b{font-family:var(--mono)}
.prow .meta{font-size:12.5px;color:var(--mut);white-space:nowrap}

.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
table th, table td{padding:10px 12px;text-align:left;white-space:nowrap}
table.rank thead th{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--mut);border-bottom:1px solid var(--line)}
table.rank tbody tr:nth-child(odd){background:rgba(255,255,255,.02)}
table.rank tbody td{color:#d7e4f5;border-bottom:1px solid rgba(120,160,220,.08)}
table.heat th{font-family:var(--mono);font-size:11px;color:var(--mut);text-align:center}
table.heat th.rowlbl{text-align:right;color:var(--ink);font-family:var(--font);font-size:12.5px;font-weight:700}
table.heat td{text-align:center;color:#04121a;font-weight:800;font-size:13px;min-width:44px;border-radius:4px}

.vazio{color:var(--dim);font-size:14px;padding:16px 0}

footer{margin-top:70px;padding-top:24px;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--dim);display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}

@media print{
  body{background:#040a16}
  .sec{page-break-inside:avoid}
}
"""


def gerar_relatorio_html(df: pd.DataFrame, escopo: str) -> str:
    """
    Gera o HTML autônomo do relatório a partir do recorte já filtrado +
    enriquecido da aba Inteligência de Falhas EE.

    Args:
        df:     DataFrame já passado por _render_filtros() + _enriquecer()
                (mesmo recorte exibido na tela no momento da geração).
        escopo: "SP", "VP" ou "GLOBAL" — só pra rótulo.

    Returns:
        HTML completo (str), pronto pra virar bytes de um download_button.
    """
    rotulo = {"SP": "Gerência SP", "VP": "Gerência VP",
              "GLOBAL": "Visão Global (SP + VP)"}.get(escopo, escopo)

    if df is None or df.empty:
        corpo = '<div class="wrap"><h1>Sem dados no recorte filtrado.</h1></div>'
        return (
            f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<title>Relatório EE — {_e(rotulo)}</title><style>{_CSS}</style></head>'
            f'<body>{corpo}</body></html>'
        )

    total = len(df)
    thp_total = float(df["thp_h"].sum()) if "thp_h" in df.columns else 0.0
    reincid = int(df.get("reincidencia_ativo", pd.Series(dtype=bool)).sum())

    datas = pd.to_datetime(df.get("data_nota"), errors="coerce").dropna()
    periodo_txt = (
        f"{datas.min().strftime('%d/%m/%Y')} – {datas.max().strftime('%d/%m/%Y')}"
        if not datas.empty else "período indisponível"
    )

    gerado_em = datetime.now().strftime("%d/%m/%Y %H:%M")

    kpis_html = "".join(_calc_resumo(df))
    pareto_html = _secao_cascata(
        "Falhas × THP por Sintoma", "Pareto de Sintomas",
        _calc_pareto_sintomas(df), "Sem dados de sintoma no recorte.",
    )
    obras_html = _secao_cascata(
        "Falhas × THP por Origem da Atividade", "Obras × Manutenção",
        _calc_obras_manutencao(df), "Sem dados de origem no recorte.",
    )
    heatmap_html = _calc_heatmap(df)
    ranking_html = _calc_ranking(df)

    sistemas = sorted(df["sistema"].dropna().unique().tolist()) if "sistema" in df.columns else []
    patios_n = df["patio"].dropna().nunique() if "patio" in df.columns else 0

    corpo = f"""
<div class="wrap">
  <div class="eyebrow">Inteligência de Falhas de Eletroeletrônica · base RASF (PG-ENG-0088)</div>
  <h1><span class="grad">Relatório de Falhas EE</span></h1>
  <p class="hero-sub">{_e(rotulo)} · Período do recorte: <b>{_e(periodo_txt)}</b> ·
    {_e(len(sistemas))} sistema(s) · {_e(patios_n)} pátio(s) na base filtrada.</p>
  <div class="hrule"></div>
  <div class="metachips">
    <span class="metachip">Falhas <b>{_fmt_int(total)}</b></span>
    <span class="metachip">THP <b>{_fmt_h(thp_total)}</b></span>
    <span class="metachip">Reincid. 90d <b>{_fmt_int(reincid)}</b></span>
    <span class="metachip">Gerado em <b>{_e(gerado_em)}</b></span>
  </div>

  <section class="sec">
    <div class="sec-head"><span class="kicker">Resumo Executivo</span>
      <h2>Panorama do recorte filtrado</h2></div>
    <div class="kpis">{kpis_html}</div>
  </section>

  {pareto_html}
  {obras_html}

  <section class="sec">
    <div class="sec-head"><span class="kicker">Mapa de Calor</span>
      <h2>Pátio × Origem da Atividade (qtd de falhas)</h2></div>
    {heatmap_html}
  </section>

  <section class="sec">
    <div class="sec-head"><span class="kicker">Ranking</span>
      <h2>Reincidência por Ativo — Top {min(15, total)}</h2></div>
    {ranking_html}
  </section>

  <footer>
    <span>MRS Sentinel · Inteligência de Falhas EE</span>
    <span>Relatório estático gerado a partir dos filtros aplicados na tela — não reflete alterações posteriores na base.</span>
  </footer>
</div>
"""

    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'<title>Relatório EE — {_e(rotulo)}</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">'
        f'<style>{_CSS}</style></head><body>{corpo}</body></html>'
    )

# endregion
