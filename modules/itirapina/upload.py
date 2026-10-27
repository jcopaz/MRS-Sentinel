# =============================================================================
# modules/itirapina/upload.py — Subaba 📤 Upload por BASE
#
# 1º passo: escolher ou criar a base (data). Base congelada → envio
# desabilitado. Seis cartões: Prospecção (detecta Engenharia / Rev 1 /
# Relatório GeVia com ciclo), Relatório de Velocidade (PDF), Defeitos,
# Transit time (série contínua), Inspeção (planilha + manifest; imagens só
# para miniatura) e Repositório de mídias. Pré-visualização com avisos antes
# de gravar; ao confirmar roda calcular_indicadores(base) e registra log.
# "🔒 Congelar base": só o dono, com a data digitada.
# =============================================================================

import io
from datetime import date

import pandas as pd
import streamlit as st

from auth.permissions import DONO_PROSPECCAO
from auth.session import get_id, get_usuario
from core.analise_velocidade import normalizar_relatorio
from core.eventos_restricao import comparar_restricoes, resumo_eventos
from core.indicadores_trecho import calcular_indicadores
from core.parser_defeitos_via import ler_defeitos_via
from core.parser_inspecao import ler_inspecao, montar_link, _chave_nome
from core.parser_prospeccao import ler_prospeccao, separar_ciclos, ler_trilho_engenharia, _norm
from core.parser_prospeccao_campo import detectar_formato, ler_prospeccao_campo, comparar_rev1_r1
from core.parser_relatorio_velocidade import ler_relatorio_velocidade
from core.parser_transit_time import ler_transit_time
from database.queries import log_acesso
from database.queries_prospeccao import (
    TRECHO_ITIRAPINA, TabelaAusente, get_prospeccao, substituir_prospeccao,
    substituir_relatorio_velocidade,
)
from database.queries_trecho import (
    BaseCongelada, criar_base, congelar_base, substituir_por_base, substituir_inspecao,
    upsert_transit_time, get_repositorios_midia, salvar_repositorio_midia, limpar_caches,
)

KM_FIM = 303.8
COLS_TRANSIT = ["trem", "patio_a", "patio_b", "sentido", "partida", "tipo_parte", "chegada",
                "tipo_chega", "horas", "horas_programadas", "estado", "dt_encer", "valido", "outlier"]


def _avisos(av):
    for a in av:
        st.warning(f"⚠️ {a}")


def _pos_gravacao(base, acao: str, detalhes: dict) -> None:
    """Recalcula a foto de indicadores, limpa caches e registra o log."""
    try:
        n = calcular_indicadores(int(base["id"]), TRECHO_ITIRAPINA,
                                 pd.to_datetime(base["data_base"]).date())
        st.caption(f"📊 {n} indicadores recalculados para a base.")
    except BaseCongelada:
        pass
    except Exception as e:
        st.warning(f"Indicadores não recalculados: {e}")
    limpar_caches()
    log_acesso(get_id(), acao, {"base_id": int(base["id"]), **detalhes})


def _gravar(func, *args, **kw):
    """Executa a gravação tratando tabela ausente / base congelada."""
    try:
        return func(*args, **kw)
    except BaseCongelada:
        st.error("🔒 Base congelada — crie uma base nova para corrigir dados.")
    except TabelaAusente as e:
        st.error(f"⚙️ Tabela `{e}` ausente — rode `database/schema_itirapina.sql`.")
    except Exception as e:
        st.error(f"❌ Erro ao gravar: {e}")
    return None


# region ====================== SESSÃO 1: Base ================================

def _escolher_base(bases: pd.DataFrame):
    st.markdown("##### 1️⃣ Base da carga")
    with st.popover("➕ Nova base"):
        d = st.date_input("Data da base", value=date.today(), format="DD/MM/YYYY", key="nova_base_data")
        desc = st.text_input("Descrição", placeholder="Ex.: carga mensal nov/2027", key="nova_base_desc")
        if st.button("Criar base", key="nova_base_ok", type="primary"):
            bid = _gravar(criar_base, TRECHO_ITIRAPINA, d, desc or None, get_id())
            if bid:
                st.session_state["upload_base"] = bid
                st.session_state["base_sel"] = bid
                st.rerun()
    if bases.empty:
        st.info("Nenhuma base ainda — crie a primeira (o marco zero 26/10/2026 nasce na migração do SQL).")
        return None
    rot = {int(b.id): f"{pd.to_datetime(b.data_base):%d/%m/%Y}"
           + (" · marco zero" if b.marco_zero else "") + (" 🔒" if b.congelada else "")
           + (f" — {b.descricao}" if isinstance(b.descricao, str) and b.descricao else "")
           for b in bases.itertuples()}
    ids = list(rot)
    if st.session_state.get("upload_base") not in ids:
        st.session_state["upload_base"] = st.session_state.get("base_sel") \
            if st.session_state.get("base_sel") in ids else ids[-1]
    bid = st.selectbox("Base", ids, format_func=rot.get, key="upload_base")
    base = bases[bases["id"] == bid].iloc[0]
    if bool(base["congelada"]):
        st.info("🔒 Base congelada — somente leitura. Para corrigir, crie uma base nova.")
    return base

# endregion


# region ====================== SESSÃO 2: Cartões =============================

def _card_prospeccao(base, travada: bool) -> None:
    arq = st.file_uploader("Planilha (.xlsx) — Engenharia, Rev 1 de campo ou Relatório de Prospecção GeVia",
                           type=["xlsx"], key="up_prosp")
    if not arq:
        return
    try:
        fmt = detectar_formato(arq)
    except Exception as e:
        st.error(f"❌ {e}")
        return
    bid = int(base["id"])
    if fmt == "engenharia":
        st.caption("Formato **Engenharia (R1)** — base oficial de dormentes (lição nº 4).")
        dorm, av = ler_prospeccao(arq)
        abas = [_norm(a) for a in pd.ExcelFile(arq).sheet_names]
        trilho, av_t = ler_trilho_engenharia(arq) if "trilho" in abas else (pd.DataFrame(), [])
        _avisos(av + av_t)
        dorm = dorm[dorm["trecho"].map(_norm) == _norm(TRECHO_ITIRAPINA)]
        c = st.columns(3)
        c[0].metric("Equipamentos", len(dorm))
        c[1].metric("Inservíveis", f"{dorm['qtd_inservivel'].sum() / dorm['total_prospectado'].sum() * 100:.1f}%")
        c[2].metric("Linhas da aba Trilho", len(trilho))
        if st.button("✅ Gravar dormentes + trilho na base", disabled=travada, key="ok_eng", type="primary"):
            n = _gravar(substituir_prospeccao, TRECHO_ITIRAPINA, dorm, get_id(), bid)
            if n is not None and len(trilho):
                _gravar(substituir_por_base, "prospeccao_trilho", bid, trilho)
            if n is not None:
                st.success(f"✅ {n} equipamentos gravados.")
                _pos_gravacao(base, "upload_prospeccao_engenharia", {"segmentos": n, "arquivo": arq.name})
    elif fmt == "campo_rev1":
        st.caption("Formato **Rev 1 de campo** — Lastro e Fixação só existem aqui; Dormentes e Trilho "
                   "da Rev 1 são conferência (a base oficial é a da Engenharia).")
        abas, av = ler_prospeccao_campo(arq)
        _avisos(av)
        d = abas["dormentes"]
        try:
            r1 = get_prospeccao(TRECHO_ITIRAPINA, bid)
        except Exception:
            r1 = pd.DataFrame()
        c = st.columns(4)
        c[0].metric("Equipamentos (LP · LD)", f"{(d['linha'] == 'LP').sum()} · {(d['linha'] == 'LD').sum()}")
        c[1].metric("Dormentes · inservíveis", f"{d['total_prospectado'].sum():,} · {d['qtd_inservivel'].sum():,}"
                    .replace(",", "."))
        c[2].metric("Taxa", f"{d['qtd_inservivel'].sum() / d['total_prospectado'].sum() * 100:.1f}%")
        c[3].metric("Acidentados", int(d["qtd_acidentado"].sum()))
        if not r1.empty:
            cmp_ = comparar_rev1_r1(d, r1)
            st.info(f"Rev 1 × R1 da base: só na Rev 1 {cmp_['so_rev1']} ({cmp_['dormentes_novos']:,} dormentes)"
                    .replace(",", ".")
                    + (f" · só na R1 {cmp_['so_r1']}" if cmp_["so_r1"] else "")
                    + (f" · linha repetida em {cmp_['linha_repetida']} (conferir inversão LP/LD)"
                       if cmp_["linha_repetida"] else ""))
        g_dorm = st.checkbox("Gravar também Dormentes da Rev 1 (substitui a da Engenharia nesta base)",
                             value=r1.empty, key="rev1_dorm")
        g_tri = st.checkbox("Gravar Trilho da Rev 1 (sem a coluna Dentro/Fora da Engenharia)",
                            value=False, key="rev1_tri")
        if st.button("✅ Gravar Lastro + Fixação" + (" + Dormentes" if g_dorm else "") + (" + Trilho" if g_tri else ""),
                     disabled=travada, key="ok_rev1", type="primary"):
            ok = _gravar(substituir_por_base, "prospeccao_lastro", bid, abas["lastro"])
            ok = ok is not None and _gravar(substituir_por_base, "prospeccao_fixacao", bid, abas["fixacao"]) is not None
            if ok and g_dorm:
                if not r1.empty:
                    mapa = r1.drop_duplicates("equipamento_siv").set_index("equipamento_siv")
                    for col in ("sb", "raio", "oae", "pu", "gerencia", "coordenador"):
                        if col in mapa:
                            d[col] = d["equipamento_siv"].map(mapa[col])
                ok = _gravar(substituir_prospeccao, TRECHO_ITIRAPINA, d, get_id(), bid) is not None
            if ok and g_tri:
                ok = _gravar(substituir_por_base, "prospeccao_trilho", bid, abas["trilho"]) is not None
            if ok:
                st.success("✅ Prospecção de campo gravada.")
                _pos_gravacao(base, "upload_prospeccao_rev1", {"arquivo": arq.name})
    else:
        df, av = ler_prospeccao(arq)
        _avisos(av)
        ciclos = separar_ciclos(df, km_max=KM_FIM)
        op = sorted(c for c in ciclos if c is not None)
        ciclo = st.selectbox("Ciclo a gravar nesta base", op, index=0, key="ciclo_gevia")
        sel = ciclos[ciclo]
        st.caption(f"Relatório GeVia — ciclo {ciclo}: {len(sel)} equipamentos (km ≤ {KM_FIM}), "
                   f"{sel['qtd_inservivel'].sum() / sel['total_prospectado'].sum() * 100:.1f}% inservíveis. "
                   "Ciclo 2025 = base histórica 'ponto de partida Rumo' (data 30/11/2025, anterior ao marco zero).")
        if st.button(f"✅ Gravar ciclo {ciclo} na base", disabled=travada, key="ok_gevia", type="primary"):
            n = _gravar(substituir_prospeccao, TRECHO_ITIRAPINA, sel, get_id(), bid)
            if n is not None:
                st.success(f"✅ {n} equipamentos gravados.")
                _pos_gravacao(base, "upload_prospeccao_gevia", {"ciclo": ciclo, "segmentos": n})


def gerar_eventos_restricao(base, bases: pd.DataFrame) -> str | None:
    """
    Compara as restrições A da base com as da base anterior (mais recente com
    Relatório de Velocidade) e grava itp_restricoes_eventos. Retorna o resumo.
    """
    from database.queries_prospeccao import get_relatorio_velocidade
    anteriores = bases[pd.to_datetime(bases["data_base"]) < pd.to_datetime(base["data_base"])] \
        .sort_values("data_base", ascending=False)
    atual = normalizar_relatorio(get_relatorio_velocidade(int(base["id"])))
    for b in anteriores.itertuples():
        ant = normalizar_relatorio(get_relatorio_velocidade(int(b.id)))
        if ant.empty:
            continue
        ev = comparar_restricoes(ant, atual)
        try:
            substituir_por_base("restricoes_eventos", int(base["id"]), ev, {"base_ant_id": int(b.id)})
        except TabelaAusente:
            return "⚙️ Tabela itp_restricoes_eventos ausente — rode database/schema_itirapina_fase2.sql."
        r = resumo_eventos(ev)
        return (f"Comparado com a base de {pd.to_datetime(b.data_base):%d/%m/%Y}: {r['via_retiradas']} "
                f"restrição(ões) de via retirada(s), {r['novas_via']} nova(s) de via, {r['alteradas']} alterada(s).")
    return None


def _card_velocidade(base, travada: bool, bases: pd.DataFrame | None = None) -> None:
    arqs = st.file_uploader("PDFs do SRM (Relatório de Velocidade, um por rota)", type=["pdf"],
                            accept_multiple_files=True, key="up_relvel")
    if not arqs:
        return
    lidos = []
    for a in arqs:
        try:
            rota, exp, d = ler_relatorio_velocidade(a)
            lidos.append((a.name, rota, exp, d))
        except Exception as e:
            st.error(f"❌ {a.name}: {e}")
    if not lidos:
        return
    st.dataframe(pd.DataFrame([{"Arquivo": n, "Rota": r, "Exportado": e.strftime("%d/%m/%Y %H:%M") if e else "—",
                                "Restrições A": int((d["tipo"] == "restricao_a").sum()),
                                "Restrições B": int((d["tipo"] == "restricao_b").sum())}
                               for n, r, e, d in lidos]), hide_index=True, use_container_width=True)
    if st.button("✅ Gravar relatório(s) na base", disabled=travada, key="ok_relvel", type="primary"):
        total = 0
        for n, rota, exp, d in lidos:
            r = _gravar(substituir_relatorio_velocidade, rota, exp, d, get_id(), int(base["id"]))
            if r is None:
                return
            total += r
        st.success(f"✅ {total} registros gravados.")
        if bases is not None and len(bases) > 1:
            try:
                msg = gerar_eventos_restricao(base, bases)
                if msg:
                    st.info(f"🚧 {msg}")
            except Exception as e:
                st.warning(f"Eventos de restrição não gerados: {e}")
        _pos_gravacao(base, "upload_relatorio_velocidade", {"rotas": [r for _, r, _, _ in lidos]})


def _card_defeitos(base, travada: bool) -> None:
    arq = st.file_uploader("Export de defeitos Rumo (Defeitos SUB 78 ou Vagão Via – Defeitos)",
                           type=["xlsx"], key="up_def")
    if not arq:
        return
    try:
        d, av = ler_defeitos_via(arq)
    except Exception as e:
        st.error(f"❌ {e}")
        return
    _avisos(av)
    c = st.columns(4)
    c[0].metric("Defeitos no trecho", f"{len(d):,}".replace(",", "."))
    c[1].metric("Classe ≤ 40 km/h", int((d["vel_max_classe_kmh"] <= 40).sum()))
    c[2].metric("Vagão de Via", int((d["origem"] == "VIA").sum()))
    c[3].metric("Com lat/long", int(d["latitude"].notna().sum()))
    if st.button("✅ Gravar defeitos na base", disabled=travada, key="ok_def", type="primary"):
        n = _gravar(substituir_por_base, "defeitos_via", int(base["id"]), d)
        if n is not None:
            st.success(f"✅ {n} defeitos gravados.")
            _pos_gravacao(base, "upload_defeitos_via", {"defeitos": n, "arquivo": arq.name})


def _card_transit(base) -> None:
    st.caption("Série contínua: não pertence a uma base — novos trens entram, repetidos são atualizados.")
    arqs = st.file_uploader("Consultas SRM 'Transit Time entre dois locais' (os dois sentidos)",
                            type=["xlsx"], accept_multiple_files=True, key="up_tt")
    if not arqs:
        return
    partes = []
    for a in arqs:
        try:
            t, av = ler_transit_time(a)
            _avisos([f"{a.name}: {x}" for x in av])
            partes.append(t)
        except Exception as e:
            st.error(f"❌ {a.name}: {e}")
    if not partes:
        return
    t = pd.concat(partes, ignore_index=True)
    resumo = (t[t["valido"]].groupby("sentido")
              .agg(trens=("horas", "size"), mediana=("horas", "median"),
                   p90=("horas", lambda s: s.quantile(0.9))).round(1).reset_index())
    st.dataframe(resumo, hide_index=True, use_container_width=True)
    if st.button("✅ Gravar transit time", key="ok_tt", type="primary"):
        n = _gravar(upsert_transit_time, t[COLS_TRANSIT])
        if n is not None:
            st.success(f"✅ {n} trens gravados/atualizados.")
            _pos_gravacao(base, "upload_transit_time", {"trens": n})


def _miniatura(arquivo) -> bytes | None:
    try:
        from PIL import Image
        img = Image.open(arquivo)
        img.thumbnail((320, 320))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=70)
        return buf.getvalue()
    except Exception:
        return None


def _card_inspecao(base, travada: bool) -> None:
    c1, c2 = st.columns(2)
    plan = c1.file_uploader("Planilha do Marco Zero (aba Inspecoes_Campo)", type=["xlsx"], key="up_insp")
    man = c2.file_uploader("Manifest de mídias (.csv) — opcional", type=["csv"], key="up_man")
    imgs = st.file_uploader("Imagens locais (.jpg/.png) — opcional, só para gerar miniaturas",
                            type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="up_imgs")
    if not plan:
        return
    try:
        insp, midias, av = ler_inspecao(plan, man, [i.name for i in imgs] if not man else None)
    except Exception as e:
        st.error(f"❌ {e}")
        return
    _avisos(av)
    thumbs = {_chave_nome(i.name): _miniatura(i) for i in imgs or []}
    midias["miniatura"] = midias["arquivo"].map(lambda a: thumbs.get(_chave_nome(a)))
    try:
        repos = get_repositorios_midia(TRECHO_ITIRAPINA)
        ativo = repos[repos["ativo"].fillna(True)]
        midias["repositorio_id"] = int(ativo.iloc[0]["id"]) if len(ativo) else None
    except Exception:
        midias["repositorio_id"] = None
    c = st.columns(4)
    c[0].metric("Registros", len(insp))
    c[1].metric("Mídias (arquivos)", midias["arquivo"].nunique())
    c[2].metric("Km estimado", int((insp["km_fonte"] == "estimado").sum()))
    c[3].metric("Miniaturas", int(midias["miniatura"].notna().sum()))
    if st.button("✅ Gravar inspeção na base", disabled=travada, key="ok_insp", type="primary"):
        r = _gravar(substituir_inspecao, int(base["id"]), insp, midias)
        if r is not None:
            st.success(f"✅ {r[0]} registros e {r[1]} vínculos de mídia gravados (só referências).")
            _pos_gravacao(base, "upload_inspecao", {"registros": r[0], "midias": r[1]})


def _card_repositorio() -> None:
    st.caption("As mídias NÃO vão para o Supabase: ficam no SharePoint/OneDrive MRS (ou outro "
               "servidor). Trocar de servidor = editar a base_url aqui; todos os links mudam juntos.")
    try:
        repos = get_repositorios_midia(TRECHO_ITIRAPINA)
    except Exception as e:
        st.warning(f"Repositórios indisponíveis: {e}")
        repos = pd.DataFrame()
    atual = repos.iloc[0] if len(repos) else None
    with st.form("form_repo"):
        nome = st.text_input("Nome", value=atual["nome"] if atual is not None else "SharePoint MRS – Base Itirapina")
        url = st.text_input("base_url (raiz da pasta)", value=atual["base_url"] if atual is not None else "",
                            placeholder="https://mrslogistica.sharepoint.com/sites/.../Base_Conhecimento_Itirapina_Pederneiras")
        tipos = ["sharepoint", "onedrive", "gdrive", "http", "s3"]
        tipo = st.selectbox("Tipo", tipos, index=tipos.index(atual["tipo"]) if atual is not None
                            and atual["tipo"] in tipos else 0)
        if st.form_submit_button("💾 Salvar repositório") and url.strip():
            _gravar(salvar_repositorio_midia, TRECHO_ITIRAPINA, nome.strip(), url.strip(), tipo)
            st.success("✅ Repositório salvo.")
    if atual is not None and isinstance(atual["base_url"], str):
        st.link_button("🔗 Testar link (abre a 1ª mídia do marco zero)",
                       montar_link(atual["base_url"], "marco_zero/Mídia (59).jpg"))

# endregion


# region ====================== SESSÃO 3: Congelar ============================

def _congelar(base) -> None:
    email = str((get_usuario() or {}).get("email") or "").strip().lower()
    if email != DONO_PROSPECCAO or bool(base["congelada"]):
        return
    st.divider()
    with st.expander("🔒 Congelar base (definitivo — não há descongelar)"):
        data_txt = f"{pd.to_datetime(base['data_base']):%d/%m/%Y}"
        st.caption(f"Recalcula os indicadores e trava a base {data_txt} para escrita. "
                   "Correções depois disso exigem uma base nova.")
        conf = st.text_input(f"Digite a data da base ({data_txt}) para confirmar", key="conf_congelar")
        if st.button("🔒 Congelar", disabled=conf.strip() != data_txt, key="ok_congelar"):
            _pos_gravacao(base, "congelar_base_preparo", {})
            if _gravar(congelar_base, int(base["id"])):
                limpar_caches()
                log_acesso(get_id(), "congelar_base", {"base_id": int(base["id"]), "data_base": data_txt})
                st.success(f"🔒 Base {data_txt} congelada.")
                st.rerun()

# endregion


def render_upload(bases: pd.DataFrame) -> None:
    base = _escolher_base(bases)
    if base is None:
        return
    travada = bool(base["congelada"])
    st.markdown("##### 2️⃣ Arquivos")
    with st.expander("🔥 Prospecção (Engenharia · Rev 1 · Relatório GeVia)", expanded=True):
        _card_prospeccao(base, travada)
    with st.expander("🚧 Relatório de Velocidade (PDF do SRM)"):
        _card_velocidade(base, travada, bases)
    with st.expander("🛠️ Defeitos de via (export Rumo / Vagão de Via)"):
        _card_defeitos(base, travada)
    with st.expander("🚆 Transit time (SRM)"):
        _card_transit(base)
    with st.expander("📷 Inspeção de campo (planilha + manifest)"):
        _card_inspecao(base, travada)
    with st.expander("🗂️ Repositório de mídias"):
        _card_repositorio()
    _congelar(base)
