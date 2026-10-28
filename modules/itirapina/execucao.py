# =============================================================================
# modules/itirapina/execucao.py — Execução (visão ⚙️ Dados)
#
# O que a Manutenção fez (itp_execucao, série contínua, sem base): envio pela
# planilha-modelo (core/parser_execucao.py), troca de dormente acumulada ×
# plano, totais por atividade e mês, tabela com exclusão. render_metas edita
# itp_metas. O avanço do travamento fica na visão 🎯 Travamento.
# =============================================================================

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from auth.session import get_id
from core.parser_execucao import ATIVIDADES, MODELO, gerar_modelo, ler_execucao
from core.plano_itirapina import avanco_travamento, completar_equipamento
from database.queries_prospeccao import TRECHO_ITIRAPINA, TabelaAusente
from database.queries_trecho import apagar_execucao, get_execucao, salvar_execucao, salvar_metas
from database.queries import log_acesso

CFG = {"displaylogo": False}
MARCO_ZERO = date(2026, 10, 26)
MSG_FASE2 = ("⚙️ Tabela `itp_{}` ausente — rode `database/schema_itirapina_fase2.sql` e o seed "
             "(`scripts/seed_trecho_itirapina.py`) no SQL Editor do Supabase.")


def carregar_execucao() -> tuple[pd.DataFrame, str | None]:
    try:
        e = get_execucao(TRECHO_ITIRAPINA)
    except TabelaAusente:
        return pd.DataFrame(), MSG_FASE2.format("execucao")
    except Exception as ex:
        return pd.DataFrame(), f"❌ Erro ao ler `itp_execucao`: {ex}"
    if not e.empty:
        e["data"] = pd.to_datetime(e["data"], errors="coerce")
        for c in ("km_inicio", "km_fim", "quantidade"):
            e[c] = pd.to_numeric(e[c], errors="coerce")
    return e, None


def _fig_acumulado(e: pd.DataFrame, plano_total: int, meta: pd.Series | None) -> go.Figure:
    t = e[e["atividade"] == "troca_dormente"].sort_values("data")
    fig = go.Figure()
    if len(t):
        acc = t.groupby("data")["quantidade"].sum().cumsum()
        fig.add_trace(go.Scatter(x=acc.index, y=acc.values, mode="lines+markers", name="Executado",
                                 line=dict(color="#0f766e", width=3)))
    prazo = pd.to_datetime(meta.get("prazo")) if meta is not None and pd.notna(meta.get("prazo")) else None
    if prazo is not None:
        fig.add_trace(go.Scatter(x=[pd.Timestamp(MARCO_ZERO), prazo], y=[0, plano_total], mode="lines",
                                 name="Plano linear", line=dict(color="#94a3b8", dash="dash")))
    fig.add_hline(y=plano_total, line=dict(color="#b45309", dash="dot"),
                  annotation_text=f"Travamento {plano_total:,}".replace(",", "."))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=30), plot_bgcolor="#fff",
                      yaxis_title="dormentes trocados (acumulado)",
                      xaxis=dict(type="date", tickformat="%m/%Y"), legend=dict(orientation="h", y=1.12))
    return fig


def _upload(plano: pd.DataFrame) -> None:
    st.download_button("📥 Baixar modelo", gerar_modelo(), file_name="Modelo_Execucao_Itirapina.xlsx",
                       key="exe_modelo")
    arq = st.file_uploader("Planilha de execução (.xlsx no formato do modelo)", type=["xlsx"], key="exe_up")
    if arq is None:
        return
    df, avisos = ler_execucao(arq)
    for a in avisos:
        st.warning(a)
    if df.empty:
        return
    df = completar_equipamento(df, plano) if plano is not None and not plano.empty else df
    st.caption(f"{len(df)} registro(s) válidos — equipamento calculado pelo km quando vazio.")
    st.dataframe(df, hide_index=True, use_container_width=True, height=220)
    if st.button("✅ Gravar execução", key="exe_ok", type="primary"):
        try:
            n = salvar_execucao(TRECHO_ITIRAPINA, df, get_id())
        except TabelaAusente:
            st.error(MSG_FASE2.format("execucao"))
            return
        except Exception as ex:
            st.error(f"Erro ao gravar: {ex}")
            return
        log_acesso(get_id(), "upload_execucao_itirapina", {"registros": n})
        st.success(f"✅ {n} registro(s) gravados (repetidos atualizados).")
        st.rerun()


def render_metas(metas: pd.DataFrame) -> None:
    if metas is None or metas.empty:
        st.info(MSG_FASE2.format("metas"))
        return
    m = metas.reindex(columns=["indicador", "rotulo", "valor_meta", "prazo", "observacao"]).copy()
    m["prazo"] = pd.to_datetime(m["prazo"], errors="coerce").dt.date
    ed = st.data_editor(m, hide_index=True, use_container_width=True, key="exe_metas",
                        disabled=["indicador", "rotulo"], column_config={
                            "indicador": "Código", "rotulo": "Indicador",
                            "valor_meta": st.column_config.NumberColumn("Meta"),
                            "prazo": st.column_config.DateColumn("Prazo", format="DD/MM/YYYY"),
                            "observacao": "Observação"})
    if st.button("💾 Salvar metas", key="exe_metas_ok"):
        salvar_metas(ed, get_id())
        from modules.itirapina.dados import limpar_caches_trecho
        limpar_caches_trecho()
        log_acesso(get_id(), "metas_itirapina", {"n": len(ed)})
        st.success("Metas salvas.")
        st.rerun()


def render_execucao(refs: dict, pode_editar: bool) -> None:
    plano = refs.get("plano")
    e, aviso = carregar_execucao()
    if plano is None or plano.empty:
        st.warning(MSG_FASE2.format("plano"))
    if aviso:
        st.warning(aviso)

    if pode_editar:
        with st.expander("📤 Enviar execução (planilha-modelo)", expanded=e.empty):
            _upload(plano)
    if plano is not None and not plano.empty and not e.empty:
        av = avanco_travamento(plano, e)
        metas = refs.get("metas")
        meta = None
        if metas is not None and not metas.empty and (metas["indicador"] == "travamento").any():
            meta = metas[metas["indicador"] == "travamento"].iloc[0]
        st.markdown("##### Troca de dormente acumulada × plano")
        st.plotly_chart(_fig_acumulado(e, av["travamento"], meta), use_container_width=True, config=CFG)

    if not e.empty:
        st.markdown("##### O que foi feito")
        c1, c2 = st.columns([2, 3])
        rot = {k: v[0] for k, v in ATIVIDADES.items()}
        sel = c1.multiselect("Atividade", sorted(e["atividade"].unique()), format_func=lambda a: rot.get(a, a),
                             key="exe_f_ativ", placeholder="Todas")
        ini, fim = e["data"].min().date(), e["data"].max().date()
        per = c2.date_input("Período", (ini, fim), format="DD/MM/YYYY", key="exe_f_per")
        f = e[e["atividade"].isin(sel)] if sel else e
        if isinstance(per, tuple) and len(per) == 2:
            f = f[(f["data"].dt.date >= per[0]) & (f["data"].dt.date <= per[1])]
        tot = (f.groupby(["atividade", "unidade"])["quantidade"].sum().reset_index()
               .assign(atividade=lambda d: d["atividade"].map(lambda a: rot.get(a, a))))
        c1, c2 = st.columns([2, 3])
        c1.dataframe(tot.rename(columns={"atividade": "Atividade", "unidade": "Unidade",
                                         "quantidade": "Total"}), hide_index=True, use_container_width=True)
        mes = f.assign(mes=f["data"].dt.to_period("M").dt.to_timestamp())
        fig = go.Figure()
        for a, g in mes.groupby("atividade"):
            s = g.groupby("mes")["quantidade"].sum()
            fig.add_trace(go.Bar(x=s.index, y=s.values, name=rot.get(a, a)))
        fig.update_layout(barmode="group", height=260, margin=dict(l=10, r=10, t=10, b=30),
                          plot_bgcolor="#fff", xaxis=dict(type="date", tickformat="%m/%Y"),
                          legend=dict(orientation="h", y=1.15))
        c2.plotly_chart(fig, use_container_width=True, config=CFG)
        cols = ["id"] + [c for c in MODELO.values() if c in f.columns]
        tab = f[cols].sort_values("data", ascending=False).assign(
            data=lambda d: d["data"].dt.date, atividade=lambda d: d["atividade"].map(lambda a: rot.get(a, a)))
        if pode_editar:
            tab.insert(0, "apagar", False)
            ed = st.data_editor(tab, hide_index=True, use_container_width=True, height=300,
                                disabled=[c for c in tab.columns if c != "apagar"], key="exe_tab")
            ids = ed.loc[ed["apagar"], "id"].tolist()
            if ids and st.button(f"🗑️ Apagar {len(ids)} registro(s)", key="exe_del"):
                apagar_execucao(ids)
                log_acesso(get_id(), "apagar_execucao_itirapina", {"ids": ids})
                st.rerun()
        else:
            st.dataframe(tab.drop(columns="id"), hide_index=True, use_container_width=True, height=300)
    elif not aviso:
        st.info("📭 Nenhuma execução registrada ainda.")

