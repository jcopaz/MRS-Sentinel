# =============================================================================
# modules/itirapina/inspecao.py — Subaba 📷 Inspeção de campo
#
# Galeria filtrável (tema, gravidade, SB, faixa de km). Cada card: texto, km
# (informado/estimado), equipamento, taxa de inservíveis, defeitos na janela
# ±200 m, ponto crítico/Top 10, restrições e as mídias.
#
# Mídias ficam em repositório EXTERNO (SharePoint/OneDrive MRS): link =
# url do arquivo, senão base_url do repositório + caminho_relativo. Links
# exigem login MRS — abrem no navegador do usuário (st.link_button); o
# servidor não consegue baixar. Miniatura (opcional, gerada no upload) dá a
# prévia na galeria.
# =============================================================================

import base64

import pandas as pd
import streamlit as st

from core.parser_inspecao import montar_link, nivel_gravidade

ICONE_TIPO = {"foto": "📷", "imagem": "🖼️", "video": "▶️"}
JANELA_KM = 0.2


def _miniatura(valor):
    """bytea vem do PostgREST como '\\x89504e...' (hex)."""
    if not isinstance(valor, str) or not valor.startswith("\\x"):
        return None
    try:
        return bytes.fromhex(valor[2:])
    except ValueError:
        return None


def _defeitos_janela(defeitos: pd.DataFrame, km) -> int:
    if defeitos is None or defeitos.empty or pd.isna(km):
        return 0
    return int(((defeitos["km"] - km).abs() <= JANELA_KM).sum())


def render_inspecao(dados: dict, refs: dict) -> None:
    insp = dados.get("inspecao")
    if insp is None or insp.empty:
        st.info("📭 Nenhuma inspeção de campo nesta base — envie a planilha do Marco Zero na subaba **📤 Upload**.")
        return
    midias = dados.get("midias")
    repos = refs.get("repositorios")
    repo = repos[repos["ativo"].fillna(True)].iloc[0] if repos is not None and len(repos) else None
    base_url = repo["base_url"] if repo is not None else None

    i = insp.copy()
    i["nivel"] = i["gravidade"].map(nivel_gravidade)
    c = st.columns([2, 2, 2, 3])
    temas = c[0].multiselect("Tema", sorted(i["tema"].dropna().unique()), key="insp_tema", placeholder="Todos")
    grav = c[1].multiselect("Gravidade", ["crítico/urgente", "severo/forte", "ruim", "sem"], key="insp_grav",
                            placeholder="Todas")
    sbs = c[2].multiselect("SB", sorted(i["sb"].dropna().unique()), key="insp_sb", placeholder="Todas")
    kms = i["km"].dropna()
    faixa = c[3].slider("Faixa de km", float(kms.min()) if len(kms) else 174.0,
                        float(kms.max()) if len(kms) else 304.0,
                        (float(kms.min()) if len(kms) else 174.0, float(kms.max()) if len(kms) else 304.0),
                        key="insp_km")
    if temas:
        i = i[i["tema"].isin(temas)]
    if grav:
        mapa = {"crítico/urgente": 3, "severo/forte": 2, "ruim": 1, "sem": 0}
        i = i[i["nivel"].isin([mapa[g] for g in grav])]
    if sbs:
        i = i[i["sb"].isin(sbs)]
    i = i[i["km"].isna() | i["km"].between(*faixa)]
    i = i.sort_values(["nivel", "km"], ascending=[False, True])

    st.caption(f"{len(i)} registro(s) · "
               + ("mídias no repositório **" + repo["nome"] + "**" if repo is not None
                  else "⚠️ sem repositório de mídias configurado (📤 Upload → Repositório de mídias)"))
    if base_url is None and midias is not None and len(midias) and midias["url"].isna().all():
        st.warning("As mídias estão referenciadas, mas sem base_url os links não abrem.")

    defe = dados.get("defeitos")
    cols = st.columns(3)
    for n, r in enumerate(i.itertuples()):
        with cols[n % 3].container(border=True):
            selo = {3: "🔴", 2: "🟠", 1: "🟡"}.get(r.nivel, "⚪")
            km = f"km {r.km:.3f}" + (" (estimado)" if str(r.km_fonte).startswith("estim") else "") \
                if pd.notna(r.km) else "km n/i"
            tema = r.tema if isinstance(r.tema, str) else "—"
            st.markdown(f"{selo} **{tema}** · {km}")
            st.markdown(r.descricao if isinstance(r.descricao, str) else "")
            linhas = []
            if isinstance(r.equipamento_siv, str) and r.equipamento_siv:
                taxa = f" · inserv. {r.taxa_inserv_equip * 100:.0f}%" if pd.notna(r.taxa_inserv_equip) else ""
                linhas.append(f"`{r.equipamento_siv}`{taxa}")
            pc = " · ".join(x for x in (r.ponto_critico, r.top10) if isinstance(x, str) and x)
            if pc:
                linhas.append(f"🎯 {pc}")
            linhas.append(f"🛠️ {_defeitos_janela(defe, r.km)} defeitos a ±200 m")
            if isinstance(r.restricoes_janela, str) and r.restricoes_janela:
                linhas.append(f"🚧 {r.restricoes_janela}")
            if isinstance(r.acao_sugerida, str) and r.acao_sugerida:
                linhas.append(f"➡️ {r.acao_sugerida}")
            st.caption("  \n".join(linhas))
            if midias is not None and len(midias):
                ms = midias[midias["msg_n"] == r.msg_n]
                for m in ms.itertuples():
                    thumb = _miniatura(getattr(m, "miniatura", None))
                    if thumb:
                        st.image(thumb, use_container_width=True)
                    link = montar_link(base_url, m.caminho_relativo, m.url)
                    rot = f"{ICONE_TIPO.get(m.tipo, '📎')} {m.arquivo}"
                    if link:
                        st.link_button(rot, link, use_container_width=True)
                    else:
                        st.caption(rot)
