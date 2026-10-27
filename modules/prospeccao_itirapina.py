# =============================================================================
# modules/prospeccao_itirapina.py — Itirapina–Pederneiras · Marco Zero
#
# Trecho Itirapina–Pederneiras (Sub 78, km 174,8–303,8) que entra na MRS em
# 2027. Aba restrita por e-mail (auth/permissions.py::can_ver_prospeccao —
# dono fixo + liberados no Painel Admin → Configurações). Sem georreferência
# do KMZ: o "mapa" é linear, no KM real.
#
# Dados versionados por BASE (trecho_bases): o marco zero 26/10/2026 é a
# fotografia congelada de entrada; cada carga de 2027+ vira uma base nova.
# Seletor de base no topo. Sem schema_itirapina.sql rodado, a aba
# funciona no modo legado (Dashboard/Dormentes/Restrições/Segmentos/Upload).
#
# Subabas:
#   📈 Evolução    — base A × base B (modules/itirapina/evolucao.py)
#   📊 Dashboard   — KPIs, unifilar (pátios, VMA × praticada × restrições,
#                    dormentes, defeitos/km, Vagão × limite, inspeção),
#                    Pareto de motivos e cruzamento restrição × dormentação
#   🔥 Dormentes   — faixa LP/LD por indicador + matriz SB × indicador + ranking
#   🚧 Restrições  — restrições A/B e observações do Relatório de Velocidade
#   🛠️ Defeitos    — export Rumo + Vagão de Via (modules/itirapina/defeitos.py)
#   🚆 Transit time — ZPD ↔ ZIQ (modules/itirapina/transit.py)
#   📷 Inspeção    — galeria com mídias por link (modules/itirapina/inspecao.py)
#   🔧 Execução    — o que a Manutenção fez × plano de travamento + metas
#                    (modules/itirapina/execucao.py)
#   📋 Segmentos   — tabela completa da prospecção + exportação
#   📤 Upload      — por base (modules/itirapina/upload.py)
#
# Chave comum: Sub + linha + KM (velocidade) e equipamento SIV (defeitos).
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from auth.permissions import require_prospeccao, can_upload_prospeccao
from auth.session import get_id
from core.exportacao import gerar_excel_bytes
from core.parser_prospeccao import ler_prospeccao, enriquecer_prospeccao, _norm
from database.queries import log_acesso
from database.queries_prospeccao import (
    TRECHO_ITIRAPINA, TabelaAusente, get_prospeccao, substituir_prospeccao,
    get_relatorio_velocidade, substituir_relatorio_velocidade,
)
from core.analise_velocidade import (
    normalizar_relatorio, rotulos_sub, perfil_velocidade, resumo_perfil,
    cruzar_prospeccao, restricoes_da_sub,
)
from core.parser_relatorio_velocidade import ler_relatorio_velocidade
from core.analise_trecho import (
    TRECHO_KM, recortar, defeitos_por_equipamento, limite_pela_vma, restricoes_trecho,
)
from modules.itirapina.dados import (
    TRECHO_ROTULO, carregar_bases, carregar_base, carregar_referencias,
)
from modules.itirapina.unifilar import fig_unifilar_trecho

ESCALA_CALOR = "RdYlGn_r"
SUB_PROSPECCAO = "78"  # Itirapina–Bauru — Sub onde está a prospecção
CORES_CATEGORIA = {
    "Via permanente":           "#dc2626",
    "Externa (ANTT/PN/urbano)": "#f59e0b",
    "OAE":                      "#7c3aed",
    "Outras":                   "#64748b",
}
LIMITE_TAXA_CRITICA = 30.0  # % — destaque nos KPIs

# rótulo → (coluna, formato, teto fixo da escala ou None = p95 dos dados)
INDICADORES = {
    "Taxa de inservíveis (%)":             ("taxa_pct", "{:.1f}%", 50.0),
    "Inservíveis por km":                  ("inserv_por_km", "{:.0f}", None),
    "Malhas críticas (≥3 seguidos) por km": ("malhas_criticas_por_km", "{:.1f}", None),
    "Inserv. junta/guarda/solda por km":   ("jgs_por_km", "{:.1f}", None),
}
# endregion


# region ====================== SESSÃO 2: Entrada ==============================

MSG_SQL = ("⚙️ A tabela `{}` ainda não existe no banco — rode "
           "`database/schema_itirapina.sql` no SQL Editor do Supabase.")


def _carregar(func, tabela: str, pos=None) -> tuple[pd.DataFrame, str | None]:
    """(df, aviso) — aviso preenchido quando a tabela não existe ou dá erro."""
    try:
        df = func()
        return (pos(df) if pos else df), None
    except TabelaAusente:
        return pd.DataFrame(), MSG_SQL.format(tabela)
    except Exception as e:
        return pd.DataFrame(), f"❌ Erro ao carregar `{tabela}`: {e}"


def _seletor_base(bases: pd.DataFrame):
    """Seletor fixo no topo; padrão = base mais recente. None = modo legado."""
    if bases is None or bases.empty:
        return None
    b = bases.sort_values("data_base").reset_index(drop=True)
    rot = {int(r.id): f"{pd.to_datetime(r.data_base):%d/%m/%Y}" + (" 🔒" if r.congelada else "")
           + (" · marco zero" if r.marco_zero else "") for r in b.itertuples()}
    ids = list(rot)
    c1, c2 = st.columns([2, 3])
    # Com a key já no session_state, o widget usa esse valor (não passar index).
    if st.session_state.get("base_sel") not in ids:
        st.session_state["base_sel"] = ids[-1]
    bid = c1.selectbox("Base", ids, format_func=rot.get, key="base_sel")
    mz = b[b["marco_zero"].fillna(False)]
    if len(mz):
        m = mz.iloc[0]
        estado = " 🔒 congelado" if m["congelada"] else " · em conferência (não congelado)"
        c2.markdown(f"<div style='padding-top:30px;color:#6b7280;font-size:0.85rem;'>"
                    f"Marco zero {pd.to_datetime(m['data_base']):%d/%m/%Y}{estado}</div>",
                    unsafe_allow_html=True)
    return b[b["id"] == bid].iloc[0]


def render_prospeccao_itirapina() -> None:
    require_prospeccao()

    st.markdown(
        f"""
        <div style='background: linear-gradient(135deg, #1e3a5f 0%, #b45309 100%);
                    padding: 16px 24px; border-radius: 12px; margin-bottom: 16px;'>
            <h2 style='color:#fff; margin:0; font-size:22px;'>
                🛤️ {TRECHO_ROTULO} · Marco Zero
            </h2>
            <p style='color:rgba(255,255,255,0.75); margin:4px 0 0 0; font-size:13px;'>
                Sub 78 · km 174,8–303,8 · entrada na MRS em 2027 · acesso restrito
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    bases, aviso_bases = carregar_bases()
    base = _seletor_base(bases)
    base_id = int(base["id"]) if base is not None else None
    if base is None:
        st.caption("ℹ️ Modo legado (sem bases): " + (aviso_bases or "nenhuma base criada.")
                   + " Rode `database/schema_itirapina.sql` para ativar marco zero, "
                     "Evolução, Defeitos, Transit time e Inspeção.")

    dados = carregar_base(base_id)
    refs = carregar_referencias() if base_id is not None else {"avisos": []}
    df, rel = dados["dormentes"], dados["rel"]
    aviso_df = next((a for a in dados["avisos"] if "prospeccao_dormentes" in a), None)
    aviso_rel = next((a for a in dados["avisos"] if "relatorio_velocidade" in a), None)
    outros = [a for a in dados["avisos"] if a not in (aviso_df, aviso_rel)]
    if outros and base_id is not None:
        with st.expander(f"⚠️ {len(outros)} aviso(s) de carga"):
            for a in outros:
                st.caption(a)

    pode_upload = can_upload_prospeccao()
    nomes = ["📈 Evolução", "📊 Dashboard", "🔥 Dormentes", "🚧 Restrições", "🛠️ Defeitos",
             "🚆 Transit time", "📷 Inspeção", "🔧 Execução", "📋 Segmentos"] + (["📤 Upload"] if pode_upload else [])
    abas = dict(zip(nomes, st.tabs(nomes)))

    from modules.itirapina import evolucao, defeitos, transit, inspecao, upload, execucao
    with abas["📈 Evolução"]:
        evolucao.render_evolucao(bases, refs)
    with abas["📊 Dashboard"]:
        extra = None
        if base_id is not None:
            extra = {"defeitos": dados["defeitos"], "inspecao": dados["inspecao"],
                     "estacoes": refs.get("estacoes"), "limites": refs.get("limites"),
                     "pontos": refs.get("pontos"), "bases": bases, "base_id": base_id}
        _render_dashboard(df, rel, aviso_df, aviso_rel, extra)
    with abas["🔥 Dormentes"]:
        st.warning(aviso_df) if aviso_df else _render_mapa(df)
    with abas["🚧 Restrições"]:
        st.warning(aviso_rel) if aviso_rel else _render_restricoes(rel)
    with abas["🛠️ Defeitos"]:
        defeitos.render_defeitos(dados)
    with abas["🚆 Transit time"]:
        transit.render_transit(dados["transit"])
    with abas["📷 Inspeção"]:
        inspecao.render_inspecao(dados, refs)
    with abas["🔧 Execução"]:
        if base_id is None:
            st.info("A Execução usa as tabelas da fase 2 — rode `database/schema_itirapina.sql`.")
        else:
            execucao.render_execucao(refs, pode_upload)
    with abas["📋 Segmentos"]:
        st.warning(aviso_df) if aviso_df else _render_tabela(df)
    if pode_upload:
        with abas["📤 Upload"]:
            if base_id is None and aviso_bases:
                st.warning(aviso_bases + " Enquanto isso, o envio abaixo grava sem base (modo legado).")
                _render_upload()
                st.divider()
                _render_upload_relatorio()
            else:
                upload.render_upload(bases)

# endregion


# region ====================== SESSÃO 3: Mapa de Calor ========================

def _filtrar(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    c1, c2, c3 = st.columns([1, 2, 2])
    linhas = sorted(df["linha"].dropna().unique())
    sel_linhas = c1.multiselect("Linha", linhas, default=linhas, key="prosp_linha")
    ordem_sb = (df.groupby("sb")["km_inicio"].min().sort_values().index.tolist())
    sel_sb = c2.multiselect("SB", ordem_sb, default=[], key="prosp_sb",
                            placeholder="Todas as SBs")
    indicador = c3.selectbox("Indicador do mapa", list(INDICADORES), key="prosp_ind")

    f = df[df["linha"].isin(sel_linhas)]
    if sel_sb:
        f = f[f["sb"].isin(sel_sb)]
    return f, indicador


def _render_kpis(f: pd.DataFrame) -> None:
    total = f["total_prospectado"].sum()
    inserv = f["qtd_inservivel"].sum()
    taxa = inserv / total * 100 if total else 0
    k = st.columns(5)
    k[0].metric("Extensão prospectada", f"{f['extensao_km'].sum():.1f} km")
    k[1].metric("Dormentes prospectados", f"{total:,.0f}".replace(",", "."))
    k[2].metric("Inservíveis", f"{inserv:,.0f}".replace(",", "."), f"{taxa:.1f}% do total",
                delta_color="off")
    k[3].metric("Malhas críticas (≥3)", f"{f['malhas_criticas'].sum():,.0f}".replace(",", "."),
                f"{f['dorm_malha_critica'].sum():,.0f} dormentes".replace(",", "."),
                delta_color="off")
    n_crit = int((f["taxa_pct"] >= LIMITE_TAXA_CRITICA).sum())
    k[4].metric(f"Segmentos ≥ {LIMITE_TAXA_CRITICA:.0f}%", f"{n_crit}",
                f"de {len(f)} segmentos", delta_color="off")


def _escala(serie: pd.Series, teto_fixo: float | None) -> float:
    if teto_fixo is not None:
        return teto_fixo
    v = serie.replace([np.inf, -np.inf], np.nan).dropna()
    return float(v.quantile(0.95)) if len(v) else 1.0


def _fig_faixa(f: pd.DataFrame, indicador: str) -> go.Figure:
    col, fmt, teto = INDICADORES[indicador]
    cmax = max(_escala(f[col], teto), 1e-6)
    linhas = sorted(f["linha"].dropna().unique(), reverse=True)  # LP em cima

    def _txt(r):
        raio = "tangente" if pd.isna(r.raio) or not r.raio else f"R{r.raio:.0f}"
        data = pd.to_datetime(r.data_prospeccao).strftime("%d/%m/%Y") if pd.notna(r.data_prospeccao) else "—"
        return (f"<b>{r.equipamento_siv}</b><br>SB {r.sb} · {r.linha}<br>"
                f"km {r.km_inicio:.3f} → {r.km_fim:.3f} ({r.extensao_km * 1000:.0f} m)<br>"
                f"{r.geometria_txt} · {raio}{' · OAE' if r.oae else ''}{' · PU' if r.pu else ''}<br>"
                f"Inservíveis: {r.qtd_inservivel:.0f} de {r.total_prospectado:.0f} "
                f"(<b>{r.taxa_pct:.1f}%</b>)<br>"
                f"Malhas ≥3: {r.malhas_criticas:.0f} · Junta/guarda/solda: {r.inserv_jgs:.0f}<br>"
                f"Prospecção: {data}")

    fig = go.Figure(go.Bar(
        orientation="h",
        y=f["linha"], base=f["km_inicio"], x=f["extensao_km"],
        marker=dict(color=f[col].clip(upper=cmax), colorscale=ESCALA_CALOR,
                    cmin=0, cmax=cmax, line=dict(width=0.4, color="#ffffff"),
                    colorbar=dict(title=dict(text=indicador, side="right"), thickness=12)),
        hovertext=[_txt(r) for r in f.itertuples()],
        hovertemplate="%{hovertext}<extra></extra>",
        width=0.8,
    ))

    # Divisas de SB (pela menor km de cada SB) com o nome no topo.
    limites = f.groupby("sb")["km_inicio"].min().sort_values()
    for sb, km in limites.items():
        fig.add_vline(x=km, line=dict(color="#94a3b8", width=1, dash="dot"))
        fig.add_annotation(x=km, y=1.0, yref="paper", text=sb, showarrow=False,
                           textangle=-60, xanchor="left", yanchor="bottom",
                           font=dict(size=10, color="#475569"))
    fig.update_layout(
        height=260 + 40 * len(linhas), margin=dict(l=10, r=10, t=80, b=40),
        xaxis=dict(title="KM", showgrid=True, gridcolor="#e5e7eb"),
        yaxis=dict(categoryorder="array", categoryarray=linhas, title=None),
        plot_bgcolor="#ffffff", bargap=0.15, dragmode="zoom",
    )
    return fig


def _fig_matriz_sb(f: pd.DataFrame) -> go.Figure:
    g = f.groupby("sb").agg(
        km_ini=("km_inicio", "min"), ext=("extensao_km", "sum"),
        total=("total_prospectado", "sum"), inserv=("qtd_inservivel", "sum"),
        malhas=("malhas_criticas", "sum"), jgs=("inserv_jgs", "sum"),
        sem_leit=("ext_sem_leitura_m", "sum"),
    ).sort_values("km_ini")
    ext = g["ext"].replace(0, np.nan)
    linhas = {
        "Taxa inservíveis (%)":       (g["inserv"] / g["total"].replace(0, np.nan) * 100, "{:.1f}"),
        "Inservíveis / km":           (g["inserv"] / ext, "{:.0f}"),
        "Malhas ≥3 / km":             (g["malhas"] / ext, "{:.1f}"),
        "Junta/guarda/solda / km":    (g["jgs"] / ext, "{:.1f}"),
        "Extensão sem leitura (m)":   (g["sem_leit"], "{:.0f}"),
    }
    z, texto = [], []
    for serie, fmt in linhas.values():
        v = serie.fillna(0).astype(float)
        topo = v.max()
        z.append((v / topo).tolist() if topo else [0.0] * len(v))
        texto.append([fmt.format(x) for x in v])

    fig = go.Figure(go.Heatmap(
        z=z, x=g.index.tolist(), y=list(linhas), text=texto,
        texttemplate="%{text}", textfont=dict(size=11),
        colorscale=ESCALA_CALOR, zmin=0, zmax=1, showscale=False,
        hovertemplate="SB %{x}<br>%{y}: %{text}<extra></extra>", xgap=2, ygap=2,
    ))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=60),
                      yaxis=dict(autorange="reversed"), xaxis=dict(tickangle=-45))
    return fig


def _render_mapa(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("📭 Nenhuma prospecção carregada ainda — envie a planilha na aba **📤 Upload**.")
        return

    f, indicador = _filtrar(df)
    if f.empty:
        st.info("Nenhum segmento para os filtros escolhidos.")
        return

    _render_kpis(f)

    st.markdown("##### 🔥 Mapa de calor ao longo do trecho")
    st.caption("Cada barra é um segmento prospectado no KM real; a cor segue o indicador "
               "escolhido. Arraste para dar zoom, duplo clique para voltar.")
    st.plotly_chart(_fig_faixa(f, indicador), use_container_width=True,
                    config={"displaylogo": False})

    st.markdown("##### 🧭 Matriz SB × indicador")
    st.caption("SBs em ordem de KM. Cor relativa dentro de cada linha (vermelho = pior SB "
               "naquele indicador); o número é o valor real.")
    st.plotly_chart(_fig_matriz_sb(f), use_container_width=True,
                    config={"displaylogo": False})

    col, fmt, _ = INDICADORES[indicador]
    st.markdown(f"##### 🎯 Segmentos mais críticos — {indicador}")
    top = (f.sort_values(col, ascending=False).head(15)
           [["sb", "linha", "equipamento_siv", "km_inicio", "km_fim", "geometria_txt",
             "raio", "qtd_inservivel", "total_prospectado", "taxa_pct",
             "malhas_criticas", "inserv_jgs"]])
    st.dataframe(
        top, hide_index=True, use_container_width=True,
        column_config={
            "sb": "SB", "linha": "Linha", "equipamento_siv": "Equipamento SIV",
            "km_inicio": st.column_config.NumberColumn("KM início", format="%.3f"),
            "km_fim": st.column_config.NumberColumn("KM fim", format="%.3f"),
            "geometria_txt": "Geometria",
            "raio": st.column_config.NumberColumn("Raio", format="%.0f"),
            "qtd_inservivel": "Inservíveis", "total_prospectado": "Prospectados",
            "taxa_pct": st.column_config.ProgressColumn(
                "Taxa", format="%.1f%%", min_value=0, max_value=100),
            "malhas_criticas": "Malhas ≥3", "inserv_jgs": "Junta/guarda/solda",
        },
    )

# endregion


# region ====================== SESSÃO 4: Tabela ===============================

COLS_TABELA = {
    "sb": "SB", "linha": "Linha", "equipamento_siv": "Equipamento SIV",
    "km_inicio": "KM início", "km_fim": "KM fim", "extensao_km": "Extensão (km)",
    "geometria_txt": "Geometria", "raio": "Raio", "oae": "OAE", "pu": "PU",
    "tipo_fixacao": "Fixação", "espacamento_cm": "Espaçamento (cm)",
    "total_prospectado": "Prospectados", "qtd_inservivel": "Inservíveis",
    "taxa_pct": "Taxa (%)", "malhas_criticas": "Malhas ≥3",
    "dorm_malha_critica": "Dorm. em malha ≥3", "inserv_junta": "Junta",
    "inserv_guarda": "Guarda", "inserv_solda": "Solda", "qtd_ruina": "Ruína",
    "ext_sem_leitura_m": "Sem leitura (m)", "data_prospeccao": "Data prospecção",
    "fonte": "Fonte", "observacao": "Observação",
}


def _render_tabela(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("📭 Nenhuma prospecção carregada ainda.")
        return
    t = df[[c for c in COLS_TABELA if c in df.columns]].rename(columns=COLS_TABELA)
    enviado = (pd.to_datetime(df["enviado_em"], errors="coerce").max()
               if "enviado_em" in df.columns else pd.NaT)
    if pd.notna(enviado):
        st.caption(f"Base enviada em {enviado:%d/%m/%Y %H:%M} (UTC) · {len(df)} segmentos.")
    st.dataframe(t, hide_index=True, use_container_width=True, height=520)
    st.download_button(
        "📥 Exportar Excel", data=gerar_excel_bytes(t, "Prospecção"),
        file_name="prospeccao_itirapina_triagem.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="prosp_export",
    )

# endregion


# region ====================== SESSÃO 5: Upload ===============================

def _render_upload() -> None:
    st.markdown("##### 📤 Enviar planilha de prospecção")
    st.caption(
        "Formato da planilha *Prospecção Itirapina Engenharia.xlsx* (1ª aba). O envio "
        "**substitui todos os segmentos** do trecho Itirapina–Triagem. Colunas de "
        "cenário (20% / 16% / 30%) são ignoradas."
    )
    arquivo = st.file_uploader("Planilha (.xlsx)", type=["xlsx"], key="prosp_upload")
    if not arquivo:
        return

    try:
        novo, avisos = ler_prospeccao(arquivo)
    except Exception as e:
        st.error(f"❌ Não foi possível ler a planilha: {e}")
        return

    trechos = novo["trecho"].dropna().map(_norm).unique()
    if _norm(TRECHO_ITIRAPINA) not in trechos:
        st.error(f"❌ A planilha não tem segmentos do trecho **{TRECHO_ITIRAPINA}** "
                 f"(encontrado: {', '.join(novo['trecho'].dropna().unique()[:5])}).")
        return
    outros = novo[novo["trecho"].map(_norm) != _norm(TRECHO_ITIRAPINA)]
    if len(outros):
        avisos.append(f"{len(outros)} linha(s) de outros trechos ignorada(s).")
        novo = novo[novo["trecho"].map(_norm) == _norm(TRECHO_ITIRAPINA)]

    for a in avisos:
        st.warning(f"⚠️ {a}")

    resumo = enriquecer_prospeccao(novo)
    total = resumo["total_prospectado"].sum()
    c = st.columns(4)
    c[0].metric("Segmentos", len(resumo))
    c[1].metric("KM", f"{resumo['km_inicio'].min():.1f} → {resumo['km_fim'].max():.1f}")
    c[2].metric("SBs", resumo["sb"].nunique())
    c[3].metric("Taxa de inservíveis",
                f"{resumo['qtd_inservivel'].sum() / total * 100:.1f}%" if total else "—")
    st.dataframe(novo.head(10), hide_index=True, use_container_width=True)

    if st.button("✅ Substituir base do trecho", type="primary", key="prosp_confirmar"):
        try:
            n = substituir_prospeccao(TRECHO_ITIRAPINA, novo, get_id())
        except TabelaAusente:
            st.error("⚙️ Rode `database/schema_itirapina.sql` no Supabase antes do upload.")
            return
        except Exception as e:
            st.error(f"❌ Erro ao gravar: {e}")
            return
        log_acesso(get_id(), "upload_prospeccao",
                   {"trecho": TRECHO_ITIRAPINA, "segmentos": n, "arquivo": arquivo.name})
        st.success(f"✅ {n} segmentos gravados. Abra a aba 📊 Dashboard.")

# endregion


# region ====================== SESSÃO 6: Dashboard ============================

def _degraus(p: pd.DataFrame, col: str) -> tuple[list, list]:
    """Série em degraus (km_de→km_ate) com quebra onde há buraco no perfil."""
    xs, ys, fim_ant = [], [], None
    for r in p.itertuples():
        v = getattr(r, col)
        if fim_ant is not None and abs(r.km_de - fim_ant) > 1e-6:
            xs.append(None)
            ys.append(None)
        xs += [r.km_de, r.km_ate]
        ys += [None if pd.isna(v) else v] * 2
        fim_ant = r.km_ate
    return xs, ys


def _controles(rel: pd.DataFrame):
    rotulos = rotulos_sub(rel)
    subs_vel = rel.loc[rel["tipo"].isin(["vma", "restricao_a"]), "sub"].dropna().unique()
    subs = [s for s in rotulos if s in subs_vel]
    padrao = subs.index(SUB_PROSPECCAO) if SUB_PROSPECCAO in subs else 0
    c1, c2, c3 = st.columns([3, 1, 2])
    sub = c1.selectbox("Sub (trecho do SRM)", subs, index=padrao,
                       format_func=lambda s: rotulos.get(s, s), key="dash_sub")
    linhas = sorted(rel.loc[(rel["sub"] == sub) & rel["linha"].notna(), "linha"].unique()) or ["LP"]
    linha = c2.selectbox("Linha", linhas, index=linhas.index("LP") if "LP" in linhas else 0,
                         key="dash_linha")
    tipos = list(rel[(rel["tipo"] == "vma") & (rel["sub"] == sub)]
                 [["bitola", "trem_tipo"]].drop_duplicates()
                 .sort_values(["bitola", "trem_tipo"]).itertuples(index=False, name=None))
    tipos = tipos or [("Larga", "TQ Carreg")]
    padrao_t = tipos.index(("Larga", "TQ Carreg")) if ("Larga", "TQ Carreg") in tipos else 0
    bitola, trem = c3.selectbox("Trem-tipo (VMA)", tipos, index=padrao_t,
                                format_func=lambda t: f"{t[1]} · bitola {t[0].lower()}",
                                key="dash_trem")
    return sub, linha, bitola, trem


def _fmt_data(d) -> str:
    return d.strftime("%d/%m %H:%M") if pd.notna(d) else "—"


def _fig_unifilar(p: pd.DataFrame, rB: pd.DataFrame, seg, trem: str) -> go.Figure:
    tem_dorm = seg is not None and not seg.empty
    alturas = [0.58, 0.12, 0.30] if tem_dorm else [0.82, 0.18]
    fig = make_subplots(rows=len(alturas), cols=1, shared_xaxes=True,
                        vertical_spacing=0.04, row_heights=alturas)

    # ── 1: velocidades ───────────────────────────────────────────────────────
    x, y = _degraus(p, "vma")
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=f"VMA {trem}",
                             line=dict(color="#94a3b8", width=2, dash="dash"),
                             hovertemplate="km %{x:.1f}<br>VMA %{y:.0f} km/h<extra></extra>"),
                  row=1, col=1)
    x, y = _degraus(p, "v_prat")
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Velocidade praticada",
                             line=dict(color="#1e3a5f", width=2), fill="tozeroy",
                             fillcolor="rgba(30,58,95,0.08)",
                             hovertemplate="km %{x:.1f}<br>Praticada %{y:.0f} km/h<extra></extra>"),
                  row=1, col=1)
    restr = p[p["restrito"]]
    for cat, cor in CORES_CATEGORIA.items():
        sub_r = restr[restr["categoria"] == cat]
        if sub_r.empty:
            continue
        xs, ys, txt = [], [], []
        for r in sub_r.itertuples():
            vma = f" (VMA {r.vma:.0f})" if pd.notna(r.vma) else ""
            h = (f"<b>{r.motivo}</b><br>SB {r.sb} · km {r.km_de:.1f}–{r.km_ate:.1f}<br>"
                 f"{r.v_prat:.0f} km/h{vma}")
            xs += [r.km_de, r.km_ate, None]
            ys += [r.v_prat, r.v_prat, None]
            txt += [h, h, None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=f"Restrição · {cat}",
                                 line=dict(color=cor, width=7), hovertext=txt,
                                 hovertemplate="%{hovertext}<extra></extra>"),
                      row=1, col=1)

    # ── 2: restrições programadas (B) ────────────────────────────────────────
    if not rB.empty:
        pare = rB["condicao"].fillna("").str.contains("sim", case=False)
        fig.add_trace(go.Bar(
            orientation="h", y=["Programadas"] * len(rB), base=rB["a"], x=rB["b"] - rB["a"],
            marker=dict(color=np.where(pare, "#dc2626", "#f59e0b")),
            hovertext=[f"<b>{r.sb}</b> · {r.condicao}<br>km {r.a:.1f}–{r.b:.1f}<br>"
                       f"Resp. {r.responsavel}<br>{_fmt_data(r.inicio)} → {_fmt_data(r.fim)}"
                       for r in rB.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", name="Restrição B",
            showlegend=False, width=0.6), row=2, col=1)
    else:
        fig.add_annotation(text="sem restrições programadas", x=0.5, y=0.5, showarrow=False,
                           xref="x2 domain", yref="y2 domain", font=dict(color="#94a3b8"))
        fig.update_yaxes(showticklabels=False, row=2, col=1)

    # ── 3: faixa de dormentes ────────────────────────────────────────────────
    if tem_dorm:
        def _h(r):
            v = f"{r.v_prat_min:.0f} km/h" if pd.notna(r.v_prat_min) else "—"
            return (f"<b>{r.equipamento_siv}</b> · SB {r.sb} · {r.linha}<br>"
                    f"km {r.km_inicio:.3f}–{r.km_fim:.3f}<br>"
                    f"Inservíveis {r.qtd_inservivel:.0f}/{r.total_prospectado:.0f} "
                    f"(<b>{r.taxa_pct:.1f}%</b>) · malhas ≥3: {r.malhas_criticas:.0f}<br>"
                    f"Restrições A: {r.n_restr_a} · praticada mín. {v}")
        fig.add_trace(go.Bar(
            orientation="h", y=["Dormentes"] * len(seg), base=seg["km_inicio"],
            x=seg["extensao_km"],
            marker=dict(color=seg["taxa_pct"].clip(upper=50), colorscale=ESCALA_CALOR,
                        cmin=0, cmax=50, line=dict(width=0.3, color="#fff"),
                        colorbar=dict(title=dict(text="Inserv. %", side="right"),
                                      thickness=10, len=0.3, y=0.15)),
            hovertext=[_h(r) for r in seg.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>", name="Dormentes",
            showlegend=False, width=0.8), row=3, col=1)

    fig.update_yaxes(title_text="km/h", rangemode="tozero", row=1, col=1)
    fig.update_xaxes(title_text="KM", row=len(alturas), col=1, showgrid=True, gridcolor="#e5e7eb")
    fig.update_layout(
        height=620 if tem_dorm else 480, margin=dict(l=10, r=10, t=30, b=40),
        plot_bgcolor="#ffffff", hovermode="closest", barmode="overlay",
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)),
    )
    return fig


def _fig_pareto(rA: pd.DataFrame) -> go.Figure:
    g = (rA.assign(ext=rA["b"] - rA["a"], categoria=rA["categoria"].fillna("Outras"))
         .groupby(["motivo", "categoria"]).agg(km=("ext", "sum"), n=("ext", "size"))
         .reset_index().sort_values("km", ascending=False).head(12).iloc[::-1])
    fig = go.Figure(go.Bar(
        orientation="h", y=g["motivo"].str.slice(0, 45), x=g["km"],
        marker_color=g["categoria"].map(CORES_CATEGORIA).fillna("#64748b"),
        text=[f"{k:.1f} km · {n}×" for k, n in zip(g["km"], g["n"])], textposition="outside",
        hovertemplate="%{y}<br>%{x:.1f} km<extra></extra>"))
    fig.update_layout(height=80 + 30 * len(g), margin=dict(l=10, r=70, t=10, b=30),
                      xaxis_title="km sob restrição", plot_bgcolor="#ffffff")
    return fig


def _fig_dispersao(c: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for flag, nome, cor in ((True, "Com restrição de via", "#dc2626"),
                            (False, "Sem restrição de via", "#1e3a5f")):
        d = c[(c["restr_via"] == flag) & c["v_prat_min"].notna()]
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["taxa_pct"], y=d["v_prat_min"], mode="markers", name=nome,
            marker=dict(color=cor, size=(d["extensao_km"] * 12).clip(6, 26), opacity=0.7,
                        line=dict(width=0.5, color="#fff")),
            hovertext=[f"<b>{r.equipamento_siv}</b> · SB {r.sb} · {r.linha}<br>"
                       f"Inserv. {r.taxa_pct:.1f}% · praticada {r.v_prat_min:.0f} km/h<br>"
                       f"{r.motivos_restr or 'sem restrição A'}" for r in d.itertuples()],
            hovertemplate="%{hovertext}<extra></extra>"))
    fig.add_vline(x=LIMITE_TAXA_CRITICA, line=dict(color="#dc2626", dash="dot", width=1))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=40),
                      xaxis_title="Taxa de inservíveis do segmento (%)",
                      yaxis_title="Velocidade praticada mínima (km/h)",
                      plot_bgcolor="#ffffff", legend=dict(orientation="h", y=1.08))
    return fig


def _render_kpis_velocidade(res: dict, rA: pd.DataFrame, rB: pd.DataFrame) -> None:
    k = st.columns(6)
    k[0].metric("VMA média", f"{res['vma_media']:.1f} km/h")
    k[1].metric("Velocidade média praticada", f"{res['v_media']:.1f} km/h",
                f"{res['v_media'] - res['vma_media']:+.1f} km/h vs VMA")
    k[2].metric("Km sob restrição A", f"{res['km_restrito']:.1f} km",
                f"{res['pct_restrito']:.0f}% da extensão", delta_color="off")
    k[3].metric("Tempo perdido / passagem", f"{res['min_perdidos']:.0f} min",
                help="Σ extensão × (1/praticada − 1/VMA), para o trem-tipo escolhido.")
    if "grupo" in rA.columns:  # modo trecho: restricoes_trecho (LP+LD) = mesma conta da Evolução
        via = int((rA["grupo"] == "Via").sum())
        k[4].metric("Restrições A", f"{len(rA)}", f"{via} via · {len(rA) - via} ANTT",
                    delta_color="off", help="Sub 78, km ≤ 303,8, LP + LD.")
    else:
        k[4].metric("Restrições A", f"{len(rA)}",
                    f"{(rA['categoria'] == 'Via permanente').sum()} de via", delta_color="off")
    pare = rB["condicao"].fillna("").str.contains("sim", case=False).sum() if len(rB) else 0
    k[5].metric("Restrições B (programadas)", f"{len(rB)}", f"{pare} com Pare sim",
                delta_color="off")


def _render_kpis_cruzamento(cruz: pd.DataFrame) -> None:
    crit = cruz["taxa_pct"] >= LIMITE_TAXA_CRITICA
    tot = cruz["total_prospectado"].sum()
    d = st.columns(4)
    d[0].metric("Inservíveis na prospecção",
                f"{cruz['qtd_inservivel'].sum() / tot * 100:.1f}%" if tot else "—",
                f"{len(cruz)} segmentos · {cruz['extensao_km'].sum():.0f} km", delta_color="off")
    d[1].metric(f"Segmentos ≥ {LIMITE_TAXA_CRITICA:.0f}% inservíveis", int(crit.sum()))
    d[2].metric("Críticos SEM restrição", int((crit & (cruz["n_restr_a"] == 0)).sum()),
                "dormentação ruim rodando na VMA", delta_color="off")
    d[3].metric("Críticos COM restrição de via", int((crit & cruz["restr_via"]).sum()))


def _camadas_trecho(extra, df: pd.DataFrame, p: pd.DataFrame, linha: str, sub: str) -> dict:
    """Faixas extras do unifilar quando a Sub é a do trecho (78)."""
    if not extra or sub != SUB_PROSPECCAO:
        return {}
    c1, c2, c3 = st.columns([2, 2, 3])
    camadas = {"estacoes": extra.get("estacoes"), "pontos": extra.get("pontos"),
               "insp": extra.get("inspecao")}
    defe = extra.get("defeitos")
    if defe is not None and not defe.empty:
        ativos = defe[defe["status"].fillna("Ativo") == "Ativo"] if "status" in defe else defe
        if not df.empty:
            camadas["def_eq"] = defeitos_por_equipamento(ativos, df)
        via = ativos[ativos["origem"] == "VIA"]
        if len(via):
            viagens = sorted(via["numero_viagem"].dropna().astype(int).unique())
            if not viagens:
                c1.warning("Export sem número de viagem do Vagão — recarregue com o "
                           "'Vagão Via – Defeitos'.")
            sel = c1.multiselect("Vagão de Via — viagem", viagens, default=viagens[-1:],
                                 key="dash_viagem", help="168 = mai/26 · 180 = set/26")
            via = via[via["numero_viagem"].isin(sel)] if sel else via
            camadas["vagao"] = limite_pela_vma(via, extra.get("limites"), recortar(p))
    bases = extra.get("bases")
    if bases is not None and len(bases) > 1:
        outras = bases[bases["id"] != extra["base_id"]].sort_values("data_base")
        rot = {None: "—"}
        rot.update({int(b.id): f"{pd.to_datetime(b.data_base):%d/%m/%Y}" for b in outras.itertuples()})
        mz = outras[outras["marco_zero"].fillna(False)]
        padrao = int(mz.iloc[0]["id"]) if len(mz) else None
        id_a = c2.selectbox("Sobrepor dormentes da base", list(rot), index=list(rot).index(padrao),
                            format_func=rot.get, key="dash_base_a")
        if id_a is not None:
            try:
                a = enriquecer_prospeccao(get_prospeccao(TRECHO_ITIRAPINA, id_a))
                camadas["seg_a"] = a[a["linha"] == linha]
                camadas["rotulo_a"] = f"Base {rot[id_a]}"
            except Exception:
                pass
    c3.caption("Faixas: pátios · velocidade · restrições B · dormentes · defeitos/km · "
               "Vagão (tamanho ÷ limite da classe da VMA vigente; acima de 1,0 a VMA não "
               "admite) · inspeção (vazado = km estimado).")
    return camadas


def _render_dashboard(df, rel, aviso_df, aviso_rel, extra=None) -> None:
    if aviso_rel:
        st.warning(aviso_rel)
        return
    if rel.empty:
        st.info("📭 Nenhum Relatório de Velocidade carregado — envie os PDFs do SRM "
                "na aba **📤 Upload**.")
        return

    sub, linha, bitola, trem = _controles(rel)
    p = perfil_velocidade(rel, sub, linha, bitola, trem)
    if p.empty:
        st.info("Sem VMA nem restrições para essa combinação de Sub/linha/trem-tipo.")
        return
    rA = restricoes_da_sub(rel, sub, linha, bitola)
    rB = restricoes_da_sub(rel, sub, linha, tipo="restricao_b")
    if extra and sub == SUB_PROSPECCAO:
        # Modo trecho: a Sub 78 vai até km 337,9, o trecho só até 303,8.
        p = recortar(p, *TRECHO_KM)
        rA = rA[(rA["a"] < TRECHO_KM[1]) & (rA["b"] > TRECHO_KM[0])]
        rB = rB[(rB["a"] < TRECHO_KM[1]) & (rB["b"] > TRECHO_KM[0])]
        rA = restricoes_trecho(rel)
    res = resumo_perfil(p)

    exp = (pd.to_datetime(rel["data_exportacao"], errors="coerce").max()
           if "data_exportacao" in rel.columns else pd.NaT)
    legenda = f"KM {res['km_ini']:.1f} → {res['km_fim']:.1f}"
    if pd.notna(exp):
        legenda += f" · Relatório de Velocidade SRM exportado em {exp:%d/%m/%Y %H:%M}"
    st.caption(legenda)

    _render_kpis_velocidade(res, rA, rB)

    perfis = {l: perfil_velocidade(rel, sub, l, bitola, trem) for l in ("LP", "LD")}
    cruz = cruzar_prospeccao(df, rel, perfis, sub) if not df.empty else pd.DataFrame()
    seg_linha = cruz[cruz["linha"] == linha] if not cruz.empty else None

    if not cruz.empty:
        _render_kpis_cruzamento(cruz)
    elif aviso_df:
        st.caption(aviso_df)
    elif not df.empty:
        st.caption(f"ℹ️ A prospecção de dormentes cobre só a Sub {SUB_PROSPECCAO} — "
                   "nesta Sub o painel mostra apenas velocidade e restrições.")

    st.markdown("##### 🛤️ Unifilar — velocidade, restrições e dormentes")
    st.caption("Tracejado = VMA do trem-tipo · azul = velocidade praticada · barras grossas = "
               "restrição A limitante (cor = família do motivo) · restrições programadas "
               "(vermelho = Pare sim) · taxa de inservíveis por segmento. Arraste para dar "
               "zoom; duplo clique volta.")
    camadas = _camadas_trecho(extra, df, p, linha, sub)
    if camadas:
        fig = fig_unifilar_trecho(p, rB, trem, seg=seg_linha, **camadas)
    else:
        fig = _fig_unifilar(p, rB, seg_linha, trem)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 📊 Motivos das restrições A (km afetados)")
        rA_todas = restricoes_da_sub(rel, sub)
        if rA_todas.empty:
            st.info("Sem restrições A nesta Sub.")
        else:
            st.plotly_chart(_fig_pareto(rA_todas), use_container_width=True,
                            config={"displaylogo": False})
    with c2:
        st.markdown("##### 🔗 Dormentação × velocidade praticada")
        if cruz.empty:
            st.info("Sem prospecção de dormentes nesta Sub.")
        else:
            st.plotly_chart(_fig_dispersao(cruz), use_container_width=True,
                            config={"displaylogo": False})

    if not cruz.empty:
        st.markdown("##### 🎯 Segmentos críticos de dormentação × restrições")
        top = (cruz[cruz["taxa_pct"] >= LIMITE_TAXA_CRITICA]
               .sort_values(["n_restr_a", "taxa_pct"], ascending=[True, False]))
        st.dataframe(
            top[["sb", "linha", "equipamento_siv", "km_inicio", "km_fim", "taxa_pct",
                 "malhas_criticas", "n_restr_a", "v_prat_min", "vma_min", "motivos_restr",
                 "n_restr_b"]],
            hide_index=True, use_container_width=True,
            column_config={
                "sb": "SB", "linha": "Linha", "equipamento_siv": "Equipamento SIV",
                "km_inicio": st.column_config.NumberColumn("KM início", format="%.3f"),
                "km_fim": st.column_config.NumberColumn("KM fim", format="%.3f"),
                "taxa_pct": st.column_config.ProgressColumn(
                    "Inservíveis", format="%.1f%%", min_value=0, max_value=100),
                "malhas_criticas": "Malhas ≥3", "n_restr_a": "Restr. A",
                "v_prat_min": st.column_config.NumberColumn("Praticada mín.", format="%.0f km/h"),
                "vma_min": st.column_config.NumberColumn("VMA", format="%.0f km/h"),
                "motivos_restr": "Motivos", "n_restr_b": "Restr. B",
            },
        )
        st.caption(f"Segmentos SEM restrição aparecem primeiro: dormentação ≥ "
                   f"{LIMITE_TAXA_CRITICA:.0f}% rodando na VMA é o ponto de atenção.")

    obs = rel[(rel["tipo"] == "obs_trecho") & (rel["sub"] == sub)]
    if not obs.empty:
        with st.expander(f"📝 Observações do trecho ({len(obs)})"):
            for o in obs["observacao"]:
                st.markdown(f"- {o}")

# endregion


# region ====================== SESSÃO 7: Restrições ===========================

def _render_restricoes(rel: pd.DataFrame) -> None:
    if rel.empty:
        st.info("📭 Nenhum Relatório de Velocidade carregado.")
        return
    rotulos = rotulos_sub(rel)
    subs = [s for s in rotulos if s in rel["sub"].dropna().unique()]
    padrao = [SUB_PROSPECCAO] if SUB_PROSPECCAO in subs else []
    sel = st.multiselect("Sub", subs, default=padrao, format_func=lambda s: rotulos.get(s, s),
                         key="restr_sub", placeholder="Todas as Subs")
    base = rel[rel["sub"].isin(sel)] if sel else rel

    if "rota" in rel.columns and "data_exportacao" in rel.columns:
        rotas = rel.groupby("rota")["data_exportacao"].max()
        st.caption("Rotas carregadas: " + " · ".join(
            f"{r} ({pd.to_datetime(d):%d/%m/%Y})" if pd.notna(d) else str(r)
            for r, d in rotas.items()))

    a = base[base["tipo"] == "restricao_a"].sort_values(["sub", "km_de"])
    b = base[base["tipo"] == "restricao_b"].sort_values(["sub", "km_de"])
    t1, t2, t3 = st.tabs([f"🔒 Permanentes (A) · {len(a)}", f"🕒 Programadas (B) · {len(b)}",
                          "📝 Observações"])
    with t1:
        cols = {"sub": "Sub", "sb": "SB", "linha": "Linha", "bitola": "Bitola", "km_de": "KM de",
                "km_ate": "KM até", "vel": "km/h", "motivo": "Motivo", "categoria": "Família"}
        ta = a[list(cols)].rename(columns=cols)
        st.dataframe(ta, hide_index=True, use_container_width=True, height=480)
        st.download_button("📥 Exportar Excel", gerar_excel_bytes(ta, "Restrições A"),
                           file_name="restricoes_A.xlsx", key="exp_restr_a")
    with t2:
        cols = {"sub": "Sub", "sb": "SB", "linha": "Linha", "km_de": "KM de", "km_ate": "KM até",
                "condicao": "Condição", "responsavel": "Resp.", "inicio": "Início", "fim": "Fim"}
        tb = b[list(cols)].rename(columns=cols)
        st.dataframe(tb, hide_index=True, use_container_width=True, height=420)
        st.download_button("📥 Exportar Excel", gerar_excel_bytes(tb, "Restrições B"),
                           file_name="restricoes_B.xlsx", key="exp_restr_b")
    with t3:
        ot = base[base["tipo"] == "obs_trecho"][["sub", "trecho_desc", "observacao"]]
        st.markdown("**Por trecho**")
        st.dataframe(ot.rename(columns={"sub": "Sub", "trecho_desc": "Trecho",
                                        "observacao": "Observação"}),
                     hide_index=True, use_container_width=True)
        oe = rel[rel["tipo"] == "obs_estacao"][["estacao", "vel", "observacao"]]
        st.markdown("**Linhas secundárias e pátios** (todas as rotas)")
        st.dataframe(oe.rename(columns={"estacao": "Estação", "vel": "km/h",
                                        "observacao": "Observação"}),
                     hide_index=True, use_container_width=True)

# endregion


# region ====================== SESSÃO 8: Upload do Relatório de Velocidade ====

def _render_upload_relatorio() -> None:
    st.markdown("##### 🚧 Enviar Relatório de Velocidade (PDF do SRM)")
    st.caption("Um PDF por rota, exportado do SRM (*Relatório de Velocidade*). Cada envio "
               "**substitui a rota inteira**: VMA, restrições A/B e observações.")
    arquivos = st.file_uploader("PDFs", type=["pdf"], accept_multiple_files=True,
                                key="relvel_upload")
    if not arquivos:
        return

    lidos = []
    for arq in arquivos:
        try:
            rota, exportado, d = ler_relatorio_velocidade(arq)
        except Exception as e:
            st.error(f"❌ {arq.name}: {e}")
            continue
        if not rota:
            st.error(f"❌ {arq.name}: rota não encontrada no cabeçalho do PDF.")
            continue
        lidos.append((arq.name, rota, exportado, d))
    if not lidos:
        return

    resumo = pd.DataFrame([{
        "Arquivo": n, "Rota": r,
        "Exportado em": e.strftime("%d/%m/%Y %H:%M") if e else "—",
        "VMA": int((d["tipo"] == "vma").sum()),
        "Restrições A": int((d["tipo"] == "restricao_a").sum()),
        "Restrições B": int((d["tipo"] == "restricao_b").sum()),
        "Observações": int(d["tipo"].str.startswith("obs").sum()),
        "Subs": ", ".join(sorted(d["sub"].dropna().unique(), key=lambda s: (len(s), s))),
    } for n, r, e, d in lidos])
    st.dataframe(resumo, hide_index=True, use_container_width=True)

    if st.button(f"✅ Gravar {len(lidos)} relatório(s)", type="primary", key="relvel_confirmar"):
        total = 0
        for nome, rota, exportado, d in lidos:
            try:
                total += substituir_relatorio_velocidade(rota, exportado, d, get_id())
            except TabelaAusente:
                st.error("⚙️ Rode `database/schema_itirapina.sql` no Supabase antes do upload.")
                return
            except Exception as e:
                st.error(f"❌ Erro ao gravar {nome}: {e}")
                return
        log_acesso(get_id(), "upload_relatorio_velocidade",
                   {"rotas": [r for _, r, _, _ in lidos], "registros": total})
        st.success(f"✅ {total} registros gravados. Abra a aba 📊 Dashboard.")

# endregion
