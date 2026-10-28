# =============================================================================
# modules/itirapina/navegacao.py — Visão 🛤️ Trecho (unifilar navegável)
#
# Substitui Dashboard, Restrições e Defeitos. Janela de km única da aba em
# st.session_state["itp_km"] (slider = fonte da verdade). Controles: faixa de
# km, "Ir para km" (±1 km), atalho (pátio, SB, ponto C/T, restrição) e
# "Trecho inteiro" — por callback, antes do redesenho do slider.
# Gráfico: velocidade × restrições, dormentes e defeitos (agregado por
# equipamento; ≤ 5 km, cada defeito) — em cache por (base, janela).
# Painel da janela: Restrições · Defeitos · Vagão · Equipamentos.
# Clique numa barra de dormentes → ficha do equipamento.
# =============================================================================

import pandas as pd
import streamlit as st

from core.analise_trecho import (
    TRECHO_KM, cobertura_restricao, defeitos_por_equipamento, faixas_sb, perfil_trecho, restricoes_trecho,
)
from core.eventos_restricao import motivo_legivel
from core.exportacao import gerar_excel_bytes
from modules.itirapina.unifilar import fig_unifilar_trecho, lod_da_janela

CHAVE = "itp_km"
CFG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


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
    op = {}
    e = refs.get("estacoes")
    if e is not None and len(e):
        for r in e.sort_values("km_inicio").itertuples():
            op[f"Pátio {r.codigo} · {r.nome}"] = (r.km_inicio - 0.5, r.km_fim + 0.5)
    p = refs.get("pontos")
    if p is not None and len(p):
        for r in p[p["ponto"].astype(str).str.match(r"^[CT]\d+$")].itertuples():
            op[f"Ponto crítico {r.ponto} · km {r.km_inicio:.1f}"] = (r.km_inicio - 0.5, r.km_fim + 0.5)
    for r in faixas_sb(None, refs.get("sb_faixas")).itertuples():
        op[f"SB {r.sb}"] = (r.km_ini, r.km_fim)
    if rA is not None and len(rA):
        for r in rA.sort_values("a").itertuples():
            op[f"Restrição km {r.a:.1f} · {r.vel:.0f} km/h · {motivo_legivel(r.motivo)}"] = (r.a - 1, r.b + 1)
    return op


def controles_km(refs: dict, rA: pd.DataFrame) -> tuple[float, float]:
    if CHAVE not in st.session_state:
        st.session_state[CHAVE] = TRECHO_KM
    if st.session_state.get("nav_slider") != tuple(st.session_state[CHAVE]):
        st.session_state["nav_slider"] = tuple(st.session_state[CHAVE])
    c = st.columns([5, 1.3, 3, 1.3])
    a, b = c[0].slider("Janela de km", TRECHO_KM[0], TRECHO_KM[1], step=0.1, key="nav_slider")
    st.session_state[CHAVE] = (a, b)
    c[1].number_input("Ir para km", TRECHO_KM[0], TRECHO_KM[1], value=None, step=0.1, placeholder="285",
                      key="nav_ir", on_change=_ir_para_km)
    op = _atalhos(refs, rA)
    c[2].selectbox("Ir para", [""] + list(op), key="nav_atalho", on_change=_ir_atalho, args=(op,),
                   format_func=lambda x: x or "pátio, ponto crítico, SB ou restrição…")
    c[3].button("Trecho inteiro", key="nav_tudo", on_click=_ir, args=TRECHO_KM, use_container_width=True)
    return a, b


def _janela(df, a, b, ini="km_inicio", fim="km_fim"):
    if df is None or df.empty or ini not in df.columns:
        return pd.DataFrame()
    if fim and fim in df.columns:
        return df[(df[fim] >= a) & (df[ini] <= b)]
    return df[(df[ini] >= a) & (df[ini] <= b)]


def _ativos(dados: dict) -> pd.DataFrame:
    d = dados.get("defeitos")
    if d is None or d.empty:
        return pd.DataFrame()
    return d[d["status"].fillna("Ativo") == "Ativo"] if "status" in d.columns else d


@st.cache_data(ttl=600, show_spinner=False, max_entries=20)
def _figura(base_id: int, a: float, b: float, _dados: dict, _refs: dict):
    rel = _dados["rel"]
    p = perfil_trecho(rel)
    dorm = _dados.get("dormentes")
    ativos = _ativos(_dados)
    lod = lod_da_janela(a, b)
    seg = dorm[dorm["linha"] == "LP"] if dorm is not None and not dorm.empty else None
    def_eq = defeitos_por_equipamento(ativos, dorm) if len(ativos) and seg is not None and lod != "detalhe" \
        else None
    return fig_unifilar_trecho(p, None, "TQ Carreg", seg=seg, estacoes=_refs.get("estacoes"), def_eq=def_eq,
                               pontos=_refs.get("pontos"), x_range=(a, b), lod=lod,
                               defeitos_pts=_janela(ativos, a, b, "km", None) if lod == "detalhe" else None)


@st.cache_data(ttl=600, show_spinner=False)
def _vagao(base_id: int, _dados: dict) -> pd.DataFrame:
    """Última viagem do Vagão: defeitos com classe < 35 km/h e se há restrição cobrindo."""
    ativos = _ativos(_dados)
    if ativos.empty or "origem" not in ativos.columns:
        return pd.DataFrame()
    v = ativos[(ativos["origem"] == "VIA") & (pd.to_numeric(ativos["vel_max_classe_kmh"], errors="coerce") < 35)]
    vi = pd.to_numeric(v["numero_viagem"], errors="coerce")
    if vi.notna().any():
        v = v[vi == vi.max()]
    return cobertura_restricao(v, _dados["rel"]) if len(v) else pd.DataFrame()


def _painel(a, b, dados, rA, q, vag) -> None:
    r = rA[(rA["b"] >= a) & (rA["a"] <= b)] if rA is not None and len(rA) else pd.DataFrame()
    d = _janela(_ativos(dados), a, b, "km", None)
    v = _janela(vag, a, b, "km", None)
    sem = v[~v["coberto"]] if len(v) else v
    eq = _janela(q, a, b) if q is not None else pd.DataFrame()
    via = int((r["grupo"] == "Via").sum()) if len(r) else 0
    t = st.tabs([f"Restrições ({len(r)})", f"Defeitos ({len(d)})", f"Vagão sem restrição ({len(sem)})",
                 f"Equipamentos ({len(eq)})"])
    with t[0]:
        if r.empty:
            st.caption("Sem restrição A nesta janela.")
        else:
            st.caption(f"{via} de via (Manutenção resolve) · {len(r) - via} de ANTT/terceiros")
            st.dataframe(r.assign(motivo_txt=r["motivo"].map(motivo_legivel))[
                ["a", "b", "linha", "vel", "motivo_txt", "grupo"]].sort_values("a"),
                hide_index=True, use_container_width=True, column_config={
                    "a": st.column_config.NumberColumn("km de", format="%.2f"),
                    "b": st.column_config.NumberColumn("km até", format="%.2f"), "linha": "Linha",
                    "vel": st.column_config.NumberColumn("Velocidade", format="%.0f km/h"),
                    "motivo_txt": "Motivo", "grupo": "Grupo"})
    with t[1]:
        if d.empty:
            st.caption("Sem defeitos ativos nesta janela.")
        else:
            st.caption(" · ".join(f"{g} {n}" for g, n in d["grupo"].fillna("—").value_counts().head(5).items()))
            cols = [c for c in ("km", "linha", "nome_defeito", "grupo", "classe_via", "dias_ativo",
                                "equipamento_siv") if c in d.columns]
            st.dataframe(d[cols].sort_values("km"), hide_index=True, use_container_width=True, height=280,
                         column_config={"km": st.column_config.NumberColumn("km", format="%.3f"),
                                        "nome_defeito": "Defeito", "classe_via": "Classe",
                                        "dias_ativo": "Dias ativo", "equipamento_siv": "Equipamento"})
            st.download_button("📥 Excel", gerar_excel_bytes(d[cols], "Defeitos"),
                               file_name=f"defeitos_km{a:.1f}-{b:.1f}.xlsx", key="nav_def_xls")
    with t[2]:
        if v.empty:
            st.caption("Sem defeito do Vagão de Via pedindo < 35 km/h nesta janela.")
        else:
            st.caption(f"Última viagem do Vagão: {len(v)} defeitos pedem < 35 km/h — {len(v) - len(sem)} "
                       "cobertos por restrição a até 50 m.")
            cols = [c for c in ("km", "linha", "nome_defeito", "vel_max_classe_kmh", "vma", "latitude",
                                "longitude") if c in sem.columns]
            st.dataframe(sem[cols].sort_values("km"), hide_index=True, use_container_width=True,
                         column_config={"km": st.column_config.NumberColumn("km", format="%.3f"),
                                        "nome_defeito": "Defeito", "vel_max_classe_kmh": "Pede (km/h)",
                                        "vma": "VMA"})
            st.download_button("📥 Excel com lat/long", gerar_excel_bytes(sem[cols], "Vagao"),
                               file_name=f"vagao_sem_restricao_km{a:.1f}-{b:.1f}.xlsx", key="nav_vag_xls")
    with t[3]:
        if eq.empty:
            st.caption("Sem equipamentos do plano nesta janela.")
        else:
            st.dataframe(eq[["equipamento_siv", "linha", "km_inicio", "taxa_pct", "dorm_travamento", "pct_exec",
                             "ponto_critico"]].sort_values("km_inicio"), hide_index=True, use_container_width=True,
                         column_config={"equipamento_siv": "Equipamento", "linha": "Linha",
                                        "km_inicio": st.column_config.NumberColumn("km", format="%.1f"),
                                        "taxa_pct": st.column_config.NumberColumn("Inserv.", format="%.0f%%"),
                                        "dorm_travamento": "Travamento",
                                        "pct_exec": st.column_config.ProgressColumn(
                                            "Executado", format="%.0f%%", min_value=0, max_value=100),
                                        "ponto_critico": "Ponto"})


def render_unifilar(dados: dict, refs: dict, base_id: int) -> None:
    rel = dados.get("rel")
    if rel is None or rel.empty:
        st.info("📭 Carregue o Relatório de Velocidade da base (⚙️ Dados) para ver o trecho.")
        return
    rA = restricoes_trecho(rel)
    a, b = controles_km(refs, rA)
    ev = st.plotly_chart(_figura(base_id, a, b, dados, refs), use_container_width=True, config=CFG,
                         on_select="rerun", selection_mode="points", key="nav_fig")
    st.caption("Tracejado = VMA · azul = velocidade praticada · barras grossas = restrições "
               "(vermelho via, laranja ANTT) · faixa de dormentes = % inservíveis. "
               + ("Clique num dormente para ver o equipamento." if refs.get("plano") is not None else ""))

    q = None
    plano = refs.get("plano")
    if plano is not None and len(plano):
        from modules.itirapina.execucao import carregar_execucao
        from modules.itirapina.travamento import _ficha, assinatura, quadro_cache
        e, _ = carregar_execucao()
        q = quadro_cache(base_id, assinatura(e), plano, dados, e)
        pts = getattr(getattr(ev, "selection", None), "points", None) or []
        cd = next((x.get("customdata") for x in pts if x.get("customdata")), None)
        if cd:
            _ficha(q, (cd[0], cd[1]), dados)
    _painel(a, b, dados, rA, q, _vagao(base_id, dados))
