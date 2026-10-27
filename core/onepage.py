# =============================================================================
# core/onepage.py — Dados da One Page do trecho Itirapina–Pederneiras
#
# montar_onepage(...) é PURA e devolve um dict com tudo o que a página mostra.
# A tela (modules/itirapina/onepage.py) e a exportação matplotlib
# (core/onepage_render.py) leem o MESMO dict — o PNG/PDF/PPTX é a mesma peça.
#
# Modos:
#   'evolucao' — marco zero × base atual (cards "antes → agora", frases de ganho)
#   'partida'  — só o marco zero: valor + meta, sem setas; bloco ⑤ = "O plano"
# Regra de ouro: mérito da Manutenção (tempo de marcha, velocidade praticada,
# restrições de VIA, travamento) separado do que depende de outros
# (restrições ANTT/terceiros; transit time inclui circulação e pátio).
# =============================================================================

from datetime import date, datetime

import numpy as np
import pandas as pd

from core.analise_trecho import TRECHO_KM, restricoes_trecho
from core.eventos_restricao import comparar_restricoes, motivo_legivel, grupo_evento, codigo_motivo
from core.indicadores_trecho import derivados
from core.onepage_textos import frases_evolucao, frases_plano, _n
from core.parser_execucao import ATIVIDADES
from core.plano_itirapina import CONCLUIDO, avanco_travamento, top_n

ICONE_ATIVIDADE = {"troca_dormente": "🪵", "solda": "🔥", "retirada_tala": "🔩", "socaria": "⚙️",
                   "nivelamento": "📏", "limpeza_lastro": "🧹", "descarga_lastro": "🚛",
                   "troca_trilho": "🛤️", "drenagem": "💧", "outro": "🔧"}


def _total(foto) -> pd.Series:
    if foto is None or len(foto) == 0:
        return pd.Series(dtype=float)
    f = foto[(foto["escopo"] == "trecho") & (foto["chave"] == "TOTAL")]
    return pd.to_numeric(f.set_index("indicador")["valor"], errors="coerce")


def _meta(metas, ind):
    if metas is None or len(metas) == 0 or ind not in set(metas["indicador"]):
        return None
    return metas[metas["indicador"] == ind].iloc[0]


def _card(chave, titulo, valor, *, antes=None, delta=None, cor="neutro", rodape="", destaque=False,
          ajuda=""):
    return {"chave": chave, "titulo": titulo, "valor": valor, "antes": antes, "delta": delta, "cor": cor,
            "rodape": rodape, "destaque": destaque, "ajuda": ajuda}


def _dif(b, a):
    try:
        v = float(b) - float(a)
        return None if np.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _sinal(v, casas=1) -> str | None:
    return None if v is None else ("+" if v > 0 else "−" if v < 0 else "") + _n(abs(v), casas)


def _cor(delta, sentido) -> str:
    if delta is None or (isinstance(delta, float) and np.isnan(delta)) or abs(delta) < 1e-9:
        return "neutro"
    bom = delta < 0 if sentido == "menor_melhor" else delta > 0
    return "bom" if bom else "ruim"


def _transit_mensal(transit, ate, meses=12) -> pd.DataFrame:
    if transit is None or len(transit) == 0:
        return pd.DataFrame(columns=["mes", "sentido", "mediana", "media", "trens"])
    t = transit[transit["valido"].astype(bool) & ~transit["outlier"].astype(bool)].copy()
    t["partida"] = pd.to_datetime(t["partida"])
    t = t[t["partida"] <= pd.Timestamp(ate) + pd.Timedelta(days=1)]
    t["mes"] = t["partida"].dt.to_period("M").dt.to_timestamp()
    g = (t.groupby(["mes", "sentido"])["horas"].agg(mediana="median", media="mean", trens="size")
         .reset_index())
    ult = g["mes"].max() if len(g) else None
    return g[g["mes"] > ult - pd.DateOffset(months=meses)] if ult is not None else g


def _transit_ref(foto_mz) -> dict:
    if foto_mz is None or len(foto_mz) == 0:
        return {}
    f = foto_mz[foto_mz["escopo"] == "transit"]
    out = {}
    for s, g in f.groupby("chave"):
        v = g.set_index("indicador")["valor"]
        out[s] = {"mediana": v.get("mediana"), "programado": v.get("programado")}
    return out


def montar_onepage(*, data_mz: date, data_atual: date, foto_mz: pd.DataFrame,
                   foto_atual: pd.DataFrame | None = None, rel_mz: pd.DataFrame | None = None,
                   rel_atual: pd.DataFrame | None = None, dorm_mz: pd.DataFrame | None = None,
                   dorm_atual: pd.DataFrame | None = None, defeitos_mz: pd.DataFrame | None = None,
                   defeitos_atual: pd.DataFrame | None = None, transit: pd.DataFrame | None = None,
                   plano: pd.DataFrame | None = None, execucao: pd.DataFrame | None = None,
                   metas: pd.DataFrame | None = None, estacoes: pd.DataFrame | None = None,
                   pontos: pd.DataFrame | None = None, gerado_em: datetime | None = None) -> dict:
    evol = foto_atual is not None and len(foto_atual) > 0 and data_atual != data_mz
    a = _total(foto_mz)
    b = _total(foto_atual) if evol else a
    rel_b = rel_atual if evol and rel_atual is not None and len(rel_atual) else rel_mz
    dorm_b = dorm_atual if evol and dorm_atual is not None and len(dorm_atual) else dorm_mz

    # ── execução / travamento (desde o marco zero) ──────────────────────────
    exe = execucao
    if exe is not None and len(exe):
        exe = exe[(pd.to_datetime(exe["data"]) >= pd.Timestamp(data_mz))
                  & (pd.to_datetime(exe["data"]) <= pd.Timestamp(data_atual) + pd.Timedelta(days=1))]
    av = avanco_travamento(plano, exe) if plano is not None and len(plano) else None

    # ── eventos (marco zero × atual) ────────────────────────────────────────
    ev = comparar_restricoes(rel_mz, rel_b) if evol and rel_mz is not None and len(rel_mz) else None
    d = derivados(foto_mz, foto_atual, ev, transit, defeitos_mz, defeitos_atual, av, data_atual) if evol \
        else ({"travamento_pct": av["pct"] * 100, "pontos_concluidos": av["pontos_concluidos"],
               "travamento_exec": av["executado"]} if av else {})

    # ── cards ───────────────────────────────────────────────────────────────
    cards = []
    via_a, via_b = a.get("restricoes_via"), b.get("restricoes_via")
    antt_a, antt_b = a.get("restricoes_antt"), b.get("restricoes_antt")
    mt = _meta(metas, "restricoes_via")
    if evol:
        m = d.get("minutos_ganhos")
        cards.append(_card("marcha", "TEMPO DE MARCHA",
                           f"{_sinal(-m, 1 if abs(m) < 10 else 0)} min/trem" if m is not None else "—",
                           cor=_cor(-(m or 0), "menor_melhor"), destaque=True,
                           rodape=f"{_n(d['horas_mes'])} h de trem/mês" if d.get("horas_mes") else "",
                           ajuda="Tempo para atravessar o trecho na velocidade praticada (VMA + restrições), "
                                 "marco zero − agora."))
        va, vb = a.get("v_media_praticada"), b.get("v_media_praticada")
        cards.append(_card("vprat", "VELOCIDADE PRATICADA", f"{_n(vb, 1)} km/h", antes=f"{_n(va, 1)}",
                           delta=_sinal(_dif(vb, va)), cor=_cor(_dif(vb, va), "maior_melhor"),
                           destaque=True, rodape="média ponderada pelo km"))
        dv = _dif(via_b, via_a)
        cards.append(_card("restr", "RESTRIÇÕES DE VIA", f"{_n(via_b)}", antes=f"{_n(via_a)}",
                           delta=f"{dv / via_a * 100:+.0f}%" if dv is not None and via_a else None,
                           cor=_cor(dv, "menor_melhor"), destaque=True,
                           rodape=f"ANTT/terceiros: {_n(antt_b)} ({'=' if antt_a == antt_b else _n(antt_a) + '→'})"))
        vma_a, vma_b = a.get("vma_media"), b.get("vma_media")
        cards.append(_card("vma", "VMA MÉDIA TQ carregado", f"{_n(vma_b, 1)} km/h", antes=f"{_n(vma_a, 1)}",
                           delta=_sinal(_dif(vma_b, vma_a)), cor=_cor(_dif(vma_b, vma_a), "maior_melhor")))
    else:
        cards.append(_card("marcha", "TEMPO DE MARCHA", f"{_n(a.get('tempo_marcha_prat_min', np.nan))} min",
                           destaque=True, rodape=f"na VMA seriam {_n(a.get('tempo_marcha_vma_min', np.nan))} min"))
        cards.append(_card("vprat", "VELOCIDADE PRATICADA", f"{_n(a.get('v_media_praticada', np.nan), 1)} km/h",
                           destaque=True, rodape="média ponderada pelo km"))
        cards.append(_card("restr", "RESTRIÇÕES DE VIA", f"{_n(via_a or 0)}", destaque=True,
                           rodape=(f"meta {_n(mt['valor_meta'])}" if mt is not None else "")
                           + f" · ANTT/terceiros: {_n(antt_a or 0)}"))
        mv = _meta(metas, "vma_media")
        cards.append(_card("vma", "VMA MÉDIA TQ carregado", f"{_n(a.get('vma_media', np.nan), 1)} km/h",
                           rodape=f"meta {_n(mv['valor_meta'])} km/h" if mv is not None else ""))
    if av:
        cards.append(_card("trav", "TRECHO TRAVADO", f"{_n(av['pct'] * 100)}%",
                           rodape=f"{_n(av['executado'])}/{_n(av['travamento'])} dormentes",
                           cor="bom" if av["pct"] > 0 else "neutro"))
    tm = _transit_mensal(transit, data_atual)
    ref = _transit_ref(foto_mz)
    sent = "ZIQ→ZPD"
    if len(tm) and (tm["sentido"] == sent).any():
        ult = tm[tm["sentido"] == sent].sort_values("mes").iloc[-1]
        mz_med = (ref.get(sent) or {}).get("mediana")
        cards.append(_card("transit", f"TRANSIT TIME {sent}", f"{_n(ult['mediana'], 1)} h",
                           antes=f"{_n(mz_med, 1)}" if evol and mz_med is not None else None,
                           cor=_cor(_dif(ult["mediana"], mz_med), "menor_melhor") if evol else "neutro",
                           rodape=f"mediana {ult['mes']:%m/%Y} · inclui circulação e pátio"))

    # ── restrições no esquemático ───────────────────────────────────────────
    rA = restricoes_trecho(rel_b) if rel_b is not None and len(rel_b) else pd.DataFrame()
    restr = pd.DataFrame()
    if len(rA):
        restr = pd.DataFrame({"a": rA["a"], "b": rA["b"], "linha": rA["linha"], "vel": rA["vel"],
                              "motivo": rA["motivo"].map(motivo_legivel),
                              "grupo": rA["motivo"].map(lambda m: grupo_evento(codigo_motivo(m))),
                              "status": "ativa"})
    if ev is not None and len(ev):
        ret = ev[ev["evento"] == "retirada"]
        restr = pd.concat([restr, pd.DataFrame({
            "a": ret["km_de"], "b": ret["km_ate"], "linha": ret["linha"], "vel": ret["vel_antes"],
            "motivo": ret["motivo"].map(motivo_legivel), "grupo": ret["grupo"], "status": "retirada"})],
            ignore_index=True)

    # ── dormentação por equipamento ─────────────────────────────────────────
    def _seg(dd):
        if dd is None or len(dd) == 0:
            return pd.DataFrame(columns=["linha", "km_inicio", "km_fim", "taxa_pct", "equipamento_siv"])
        return dd[["equipamento_siv", "linha", "km_inicio", "km_fim", "taxa_pct"]].copy()
    dorm = _seg(dorm_b)
    dorm_ref = _seg(dorm_mz) if evol else None

    # ── travamento / top / feito ────────────────────────────────────────────
    trav = av["pontos"] if av else pd.DataFrame()
    top = pd.DataFrame()
    proximos = []
    if plano is not None and len(plano):
        top = top_n(plano, 10)
        pct = av["equip"].set_index(["equipamento_siv", "linha"])["pct"] if av else pd.Series(dtype=float)
        top["pct"] = [float(pct.get((e, l), 0.0)) for e, l in zip(top["equipamento_siv"], top["linha"])]
        top["situacao"] = np.select([top["pct"] >= CONCLUIDO, top["pct"] > 0], ["concluído", "em curso"],
                                    "a iniciar")
        pend = top[top["situacao"] != "concluído"].sort_values(["dorm_travamento"], ascending=False).head(3)
        proximos = [f"{('C' if r.tipo == 'curva' else 'T')}#{int(r.rank_calc)} km {_n(r.km_inicio, 1)} "
                    f"({_n(r.dorm_travamento)} dorm.)" for r in pend.itertuples()]
    feito = pd.DataFrame(columns=["atividade", "rotulo", "icone", "unidade", "total"])
    if exe is not None and len(exe):
        feito = (exe.groupby(["atividade", "unidade"])["quantidade"].sum().reset_index()
                 .rename(columns={"quantidade": "total"}))
        feito["rotulo"] = feito["atividade"].map(lambda x: ATIVIDADES.get(x, (x,))[0])
        feito["icone"] = feito["atividade"].map(lambda x: ICONE_ATIVIDADE.get(x, "🔧"))

    # ── frases ──────────────────────────────────────────────────────────────
    vag_a = a.get("vagao_sem_restricao")
    plano_txt = {"pontos": len(trav) or 7, "travamento": av["travamento"] if av else 4645,
                 "restricoes_via": int(via_a or 14), "restricoes_antt": int(antt_a or 16),
                 "vagao": int(vag_a) if vag_a is not None and not np.isnan(vag_a) else 52}
    frases = frases_evolucao(d, {
        "restricoes_via_mz": int(via_a or 14), "vma_atual": b.get("vma_media"),
        "taxa_mz": a.get("taxa_inserviveis_pct"), "taxa_atual": b.get("taxa_inserviveis_pct"),
        "vagao_mz": vag_a, "vagao_atual": b.get("vagao_sem_restricao"), "pontos_total": len(trav) or 7,
    }) if evol else []
    if not frases:
        frases = frases_plano(plano_txt)

    # ── segurança ───────────────────────────────────────────────────────────
    seg = {"defeitos_acidente": b.get("defeitos_acidente")}
    ua = _meta(metas, "ultimo_acidente")
    if ua is not None and pd.notna(ua.get("prazo")):
        seg["dias_sem_acidente"] = (pd.Timestamp(data_atual) - pd.Timestamp(ua["prazo"])).days

    ext = TRECHO_KM[1] - TRECHO_KM[0]
    return {
        "modo": "evolucao" if evol else "partida",
        "titulo": "MANUTENÇÃO DE VIA · ITIRAPINA–PEDERNEIRAS",
        "subtitulo": f"Sub 78 · km {_n(TRECHO_KM[0], 1)}–{_n(TRECHO_KM[1], 1)} · {_n(ext)} km",
        "linha_datas": (f"Marco zero {data_mz:%d/%m/%Y}  →  Situação em {data_atual:%d/%m/%Y}" if evol
                        else f"Ponto de partida – onde a Manutenção começa · marco zero {data_mz:%d/%m/%Y}"),
        "data_mz": data_mz, "data_atual": data_atual,
        "cards": cards, "derivados": d,
        "restricoes": restr, "estacoes": estacoes if estacoes is not None else pd.DataFrame(),
        "dorm": dorm, "dorm_ref": dorm_ref,
        "pontos": pontos if pontos is not None else pd.DataFrame(),
        "transit": tm, "transit_ref": ref,
        "travamento": trav, "top": top, "proximos": proximos,
        "feito": feito, "plano": plano_txt, "frases": frases, "seguranca": seg,
        "fontes": ("Fonte: SRM Rel. Velocidade · Prospecção GeVia/Engenharia · Defeitos Rumo/Vagão · "
                   "Transit SRM · Execução Manutenção. Transit time sem outliers (> 72 h). "
                   f"Gerado pelo Sentinel em {(gerado_em or datetime.now()):%d/%m/%Y %H:%M}."),
    }
