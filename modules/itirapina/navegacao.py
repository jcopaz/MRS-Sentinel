# =============================================================================
# modules/itirapina/navegacao.py — Subaba 🛤️ Unifilar navegável por km
#
# Estado único da janela de km: st.session_state["itp_km"] = (km_a, km_b),
# compartilhado com Travamento ("Ver no unifilar") e One Page. O slider é a
# fonte da verdade (o Streamlit não devolve o relayout do zoom do Plotly).
# Controles: faixa de km, "Ir para km" (±1 km), atalhos (pátio, SB, ponto
# C/T, Top 10, restrição), ◀ ▶ e "Trecho inteiro".
# Nível de detalhe pelo tamanho da janela (unifilar.lod_da_janela).
# Painel "O que tem neste trecho" sincronizado + ficha por clique.
# =============================================================================

import pandas as pd
import streamlit as st

from core.analise_trecho import (
    TRECHO_KM, faixas_sb, limite_pela_vma, perfil_trecho, restricoes_trecho, defeitos_por_equipamento,
)
from core.analise_velocidade import restricoes_da_sub
from core.exportacao import gerar_excel_bytes
from core.plano_itirapina import quadro_equipamentos
from modules.itirapina.execucao import carregar_execucao
from modules.itirapina.unifilar import fig_unifilar_trecho, lod_da_janela, motivo_curto

CHAVE = "itp_km"
ROTULO_LOD = {"agregado": "visão agregada", "medio": "rótulos das restrições",
              "detalhe": "modo detalhe (cada defeito)"}


def _limitar(a: float, b: float) -> tuple[float, float]:
    ext = max(0.2, b - a)
    a = max(TRECHO_KM[0], min(a, TRECHO_KM[1] - ext))
    return round(a, 1), round(min(TRECHO_KM[1], a + ext), 1)


def _ir(a: float, b: float) -> None:
    st.session_state[CHAVE] = _limitar(a, b)
    st.session_state["nav_slider"] = st.session_state[CHAVE]


def _ir_para_km() -> None:
    km = st.session_state.get("nav_ir")
    if km is not None:
        _ir(km - 1, km + 1)


def _ir_atalho(op: dict) -> None:
    sel = st.session_state.get("nav_atalho")
    if sel in op:
        _ir(*op[sel])


def _atalhos(refs: dict, rA: pd.DataFrame) -> dict:
    """rótulo → (a, b) para o seletor rápido."""
    op = {}
    e = refs.get("estacoes")
    if e is not None and len(e):
        for r in e.sort_values("km_inicio").itertuples():
            op[f"Pátio · {r.codigo} {r.nome}"] = (r.km_inicio - 0.5, r.km_fim + 0.5)
    for r in faixas_sb(None, refs.get("sb_faixas")).itertuples():
        op[f"SB · {r.sb}"] = (r.km_ini, r.km_fim)
    p = refs.get("pontos")
    if p is not None and len(p):
        for r in p.itertuples():
            rot = "Ponto" if str(r.ponto)[0] in "CT" and str(r.ponto)[1:].isdigit() else "Top 10"
            op[f"{rot} · {r.ponto} · km {r.km_inicio:.1f}"] = (r.km_inicio - 0.5, r.km_fim + 0.5)
    if rA is not None and len(rA):
        for r in rA.sort_values("a").itertuples():
            op[f"Restrição · km {r.a:.1f} · {r.vel:.0f} km/h · {motivo_curto(r.motivo)}"] = (r.a - 1, r.b + 1)
    return op


def controles_km(refs: dict, rA: pd.DataFrame) -> tuple[float, float]:
    if CHAVE not in st.session_state:
        st.session_state[CHAVE] = TRECHO_KM
    if st.session_state.get("nav_slider") != st.session_state[CHAVE]:
        st.session_state["nav_slider"] = tuple(st.session_state[CHAVE])
    c = st.columns([5, 1.4, 3, 0.6, 0.6, 1.4])
    a, b = c[0].slider("Janela de km", TRECHO_KM[0], TRECHO_KM[1], step=0.1, key="nav_slider")
    st.session_state[CHAVE] = (a, b)
    # callbacks (on_change) rodam antes do redesenho — o slider ainda pode mudar
    c[1].number_input("Ir para km", TRECHO_KM[0], TRECHO_KM[1], value=None, step=0.1,
                      placeholder="ex.: 285", key="nav_ir", on_change=_ir_para_km)
    op = _atalhos(refs, rA)
    c[2].selectbox("Atalho", [""] + list(op), key="nav_atalho", on_change=_ir_atalho, args=(op,),
                   format_func=lambda x: x or "Pátio, SB, ponto C/T, Top 10, restrição…")
    ext = b - a
    c[3].button("◀", key="nav_esq", on_click=_ir, args=(a - ext, b - ext), help="Janela anterior")
    c[4].button("▶", key="nav_dir", on_click=_ir, args=(a + ext, b + ext), help="Próxima janela")
    c[5].button("Trecho inteiro", key="nav_tudo", on_click=_ir, args=TRECHO_KM)
    return a, b


def _na_janela(df: pd.DataFrame, a: float, b: float, ini: str = "km_inicio", fim: str | None = "km_fim"):
    if df is None or df.empty or ini not in df.columns:
        return pd.DataFrame()
    if fim and fim in df.columns:
        return df[(df[fim] >= a) & (df[ini] <= b)]
    return df[(df[ini] >= a) & (df[ini] <= b)]


def _painel(a, b, dados, refs, rA, q, ativos, vag) -> None:
    st.markdown(f"##### 🔎 O que tem neste trecho · km {a:.1f}–{b:.1f} ({b - a:.1f} km)")
    t = st.tabs(["Resumo", "Restrições", "Defeitos", "Dormentes/equipamentos", "Inspeção"])
    eq = _na_janela(q, a, b) if q is not None else pd.DataFrame()
    r = rA[(rA["b"] >= a) & (rA["a"] <= b)] if rA is not None and len(rA) else pd.DataFrame()
    d = _na_janela(ativos, a, b, "km", None)
    insp = _na_janela(dados.get("inspecao"), a, b, "km", None)
    with t[0]:
        k = st.columns(4)
        if len(eq):
            tot = eq["inserv_atual"].sum()
            k[0].metric("Equipamentos", len(eq), f"taxa média {eq['taxa_pct'].mean():.1f}%", delta_color="off")
            k[1].metric("Travamento previsto", f"{eq['dorm_travamento'].sum():.0f}",
                        f"executado {eq['executado'].sum():.0f}", delta_color="off")
            k[3].metric("Inservíveis", f"{tot:.0f}")
        via = int((r["grupo"] == "Via").sum()) if len(r) else 0
        k[2].metric("Restrições A", len(r), f"{via} via · {len(r) - via} ANTT", delta_color="off")
        k = st.columns(4)
        k[0].metric("Defeitos ativos", len(d))
        if len(d):
            k[1].metric("…grupo principal", d["grupo"].fillna("—").value_counts().index[0])
        if vag is not None and len(vag):
            vv = _na_janela(vag, a, b, "km", None)
            k[2].metric("Vagão acima do limite da VMA", int((vv.get("razao_limite", pd.Series(dtype=float)) > 1).sum()))
        k[3].metric("Inspeções", len(insp))
    with t[1]:
        if r.empty:
            st.info("Sem restrição A na janela.")
        else:
            rr = r.assign(quem=r["grupo"].map({"Via": "Manutenção", "ANTT": "ANTT / terceiros"}),
                          motivo_curto=r["motivo"].map(motivo_curto))
            st.dataframe(rr[["a", "b", "linha", "vel", "motivo_curto", "grupo", "quem"]], hide_index=True,
                         use_container_width=True, column_config={
                             "a": st.column_config.NumberColumn("km de", format="%.3f"),
                             "b": st.column_config.NumberColumn("km até", format="%.3f"), "linha": "Linha",
                             "vel": st.column_config.NumberColumn("Vel.", format="%.0f km/h"),
                             "motivo_curto": "Motivo", "grupo": "Grupo", "quem": "Quem resolve"})
    with t[2]:
        if d.empty:
            st.info("Sem defeitos ativos na janela.")
        else:
            g = st.multiselect("Grupo", sorted(d["grupo"].dropna().unique()), key="nav_def_g", placeholder="Todos")
            dd = d[d["grupo"].isin(g)] if g else d
            cols = [c for c in ("km", "linha", "equipamento_siv", "nome_defeito", "grupo", "classe_via",
                                "vel_max_classe_kmh", "tamanho", "dias_ativo", "origem") if c in dd.columns]
            st.dataframe(dd[cols].sort_values("km"), hide_index=True, use_container_width=True, height=300)
            st.download_button("📥 Excel", gerar_excel_bytes(dd[cols], "Defeitos"),
                               file_name=f"defeitos_km{a:.1f}-{b:.1f}.xlsx", key="nav_def_xls")
    with t[3]:
        if eq.empty:
            st.info("Sem equipamentos do plano na janela.")
        else:
            st.dataframe(eq[["equipamento_siv", "linha", "km_inicio", "km_fim", "taxa_pct", "malhas_3",
                             "dorm_travamento", "dorm_meta20", "pct_exec", "ponto_critico"]],
                         hide_index=True, use_container_width=True, column_config={
                             "equipamento_siv": "Equipamento", "linha": "Linha",
                             "km_inicio": st.column_config.NumberColumn("km início", format="%.3f"),
                             "km_fim": st.column_config.NumberColumn("km fim", format="%.3f"),
                             "taxa_pct": st.column_config.NumberColumn("Taxa", format="%.1f%%"),
                             "malhas_3": "Malhas ≥3", "dorm_travamento": "Travamento", "dorm_meta20": "Meta 20%",
                             "pct_exec": st.column_config.ProgressColumn("Executado", format="%.0f%%",
                                                                         min_value=0, max_value=100),
                             "ponto_critico": "Ponto"})
    with t[4]:
        if insp.empty:
            st.info("Sem inspeção de campo na janela.")
        else:
            from modules.itirapina.inspecao import render_cards_inspecao
            render_cards_inspecao(insp, dados, refs)


def render_unifilar(dados: dict, refs: dict) -> None:
    rel = dados.get("rel")
    if rel is None or rel.empty:
        st.info("📭 Carregue o Relatório de Velocidade da base para ver o unifilar.")
        return
    rA = restricoes_trecho(rel)
    a, b = controles_km(refs, rA)
    lod = lod_da_janela(a, b)
    st.caption(f"Janela {b - a:.1f} km · {ROTULO_LOD[lod]} · arraste no gráfico para ampliar; "
               "a janela de km vale para toda a aba.")

    p = perfil_trecho(rel)
    rB = restricoes_da_sub(rel, "78", "LP", tipo="restricao_b")
    if len(rB):
        rB = rB[(rB["a"] < TRECHO_KM[1]) & (rB["b"] > TRECHO_KM[0])]
    dorm = dados.get("dormentes")
    plano = refs.get("plano")
    seg = dorm[dorm["linha"] == "LP"] if dorm is not None and not dorm.empty else None
    if seg is not None and plano is not None and len(plano):
        seg = seg.merge(plano[["equipamento_siv", "linha", "raio"]].rename(columns={"raio": "raio_p"}),
                        on=["equipamento_siv", "linha"], how="left")
        seg["raio"] = seg["raio"].fillna(seg["raio_p"]) if "raio" in seg else seg["raio_p"]
    defe = dados.get("defeitos")
    ativos = defe[defe["status"].fillna("Ativo") == "Ativo"] if defe is not None and not defe.empty \
        and "status" in defe else defe
    def_eq = defeitos_por_equipamento(ativos, dorm) if ativos is not None and not ativos.empty \
        and dorm is not None and not dorm.empty else None
    vag = None
    if ativos is not None and not ativos.empty:
        via = ativos[ativos["origem"] == "VIA"]
        if len(via):
            ult = pd.to_numeric(via["numero_viagem"], errors="coerce").max()
            if pd.notna(ult):
                via = via[pd.to_numeric(via["numero_viagem"], errors="coerce") == ult]
            vag = limite_pela_vma(via, refs.get("limites"), p)
    fig = fig_unifilar_trecho(
        p, rB, "TQ Carreg", seg=seg, estacoes=refs.get("estacoes"), def_eq=def_eq,
        vagao=_na_janela(vag, a - 1, b + 1, "km", None) if vag is not None else None,
        insp=dados.get("inspecao"), pontos=refs.get("pontos"), x_range=(a, b), lod=lod,
        defeitos_pts=_na_janela(ativos, a, b, "km", None) if lod == "detalhe" else None)
    ev = st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False},
                         on_select="rerun", selection_mode="points", key="nav_fig")

    e, _ = carregar_execucao()
    q = quadro_equipamentos(plano, dorm, ativos, rA, e) if plano is not None and len(plano) else None
    _painel(a, b, dados, refs, rA, q, ativos, vag)

    pts = getattr(getattr(ev, "selection", None), "points", None) or \
        ((ev or {}).get("selection", {}).get("points", []) if isinstance(ev, dict) else [])
    cd = next((x.get("customdata") for x in pts if x.get("customdata")), None)
    if cd and q is not None:
        from modules.itirapina.travamento import _ficha
        st.divider()
        _ficha(q, (cd[0], cd[1]), dados)
