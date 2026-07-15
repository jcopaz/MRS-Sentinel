# =============================================================================
# components/filtros.py — Filtros em cascata
# Sprint 3 — MRS Sentinel
#
# Exporta render_filtros_cascata() — filtros hierárquicos na sidebar:
#   Centro de Trabalho → Ramal → Trecho → Pátio → Período
#
# Cada nível reage ao anterior (cascata real):
#   - Ao selecionar Centro, só aparecem os Ramais daquele Centro
#   - Ao selecionar Ramal, só aparecem os Trechos daquele Ramal
#   - etc.
#
# Sessão 1: Imports & constantes
# Sessão 2: Helpers de extração de opções
# Sessão 3: render_filtros_cascata()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from core.glossarios import (
    nome_ramal, RAMAIS_MRS, STATUS_BASE, PESO_PRIORIDADE, status_base_efetivo,
)

# Centros de trabalho por gerência (fonte: 08_GLOSSARIOS.md)
CENTROS_POR_GERENCIA = {
    "SP":    ["CIPA", "CIPG", "CIJN"],
    "VP":    ["CFAN", "CFTA", "CFPI"],
    "GERAL": ["CIPA", "CIPG", "CIJN", "CFAN", "CFTA", "CFPI"],
}

# Ordem oficial de exibição da prioridade (mais crítica primeiro)
ORDEM_PRIORIDADE = list(PESO_PRIORIDADE.keys())

# endregion


# region ====================== SESSÃO 2: Helpers ==============================

def _opcoes_centros(df: pd.DataFrame, gerencia: str) -> list[str]:
    """
    Retorna lista de centros presentes nos dados.
    Prioriza os centros conhecidos da gerência; inclui eventuais extras.
    """
    conhecidos = CENTROS_POR_GERENCIA.get(gerencia, [])
    if "centro_trab" in df.columns:
        presentes = df["centro_trab"].dropna().unique().tolist()
        # Ordena: conhecidos primeiro, extras depois
        ordenados = [c for c in conhecidos if c in presentes]
        extras    = [c for c in presentes  if c not in conhecidos]
        return ordenados + sorted(extras)
    return conhecidos


def _opcoes_ramais(df: pd.DataFrame, centros_sel: list[str]) -> list[str]:
    """
    Retorna ramais disponíveis nos dados, filtrados pelos centros selecionados.
    Usa nome completo no label e sigla como valor interno.
    """
    if "ramal" not in df.columns:
        return []

    df_f = df.copy()
    if centros_sel and "centro_trab" in df_f.columns:
        df_f = df_f[df_f["centro_trab"].isin(centros_sel)]

    siglas = sorted(df_f["ramal"].dropna().unique().tolist())
    return siglas


def _opcoes_trechos(df: pd.DataFrame, centros_sel: list[str], ramais_sel: list[str]) -> list[str]:
    """Retorna trechos disponíveis após filtro de centros e ramais."""
    if "trecho" not in df.columns:
        return []

    df_f = df.copy()
    if centros_sel and "centro_trab" in df_f.columns:
        df_f = df_f[df_f["centro_trab"].isin(centros_sel)]
    if ramais_sel and "ramal" in df_f.columns:
        df_f = df_f[df_f["ramal"].isin(ramais_sel)]

    return sorted(df_f["trecho"].dropna().unique().tolist())


def _opcoes_patios(
    df: pd.DataFrame,
    centros_sel: list[str],
    ramais_sel: list[str],
    trechos_sel: list[str],
) -> list[str]:
    """Retorna pátios (origem) disponíveis após filtros anteriores."""
    if "origem" not in df.columns:
        return []

    df_f = df.copy()
    if centros_sel and "centro_trab" in df_f.columns:
        df_f = df_f[df_f["centro_trab"].isin(centros_sel)]
    if ramais_sel and "ramal" in df_f.columns:
        df_f = df_f[df_f["ramal"].isin(ramais_sel)]
    if trechos_sel and "trecho" in df_f.columns:
        df_f = df_f[df_f["trecho"].isin(trechos_sel)]

    return sorted(df_f["origem"].dropna().unique().tolist())


def _opcoes_prioridade(df: pd.DataFrame) -> list[str]:
    """Prioridades presentes nos dados, na ordem oficial (mais crítica primeiro)."""
    if "prioridade" not in df.columns:
        return []
    presentes = set(df["prioridade"].dropna().unique().tolist())
    ordenadas = [p for p in ORDEM_PRIORIDADE if p in presentes]
    extras = sorted(presentes - set(ordenadas))
    return ordenadas + extras


def _opcoes_familias(df: pd.DataFrame) -> list[str]:
    """Famílias de defeito presentes nos dados (VP + EE combinadas)."""
    if "familia_defeito" not in df.columns:
        return []
    return sorted([f for f in df["familia_defeito"].dropna().unique().tolist() if f])


def _opcoes_tipos_inspecao(df: pd.DataFrame) -> list[str]:
    """Tipos de inspeção/atividade presentes nos dados."""
    if "tipo_atividade" not in df.columns:
        return []
    return sorted([
        t for t in df["tipo_atividade"].dropna().unique().tolist()
        if t and str(t).strip()
    ])


def _opcoes_status_base(df: pd.DataFrame) -> list[str]:
    """
    Códigos de Status Base presentes nos dados, na ordem oficial de
    STATUS_BASE (core/glossarios.py). Inclui códigos não catalogados no fim.

    Usa status_base_efetivo() — a EE normalmente não preenche
    'status_usuario' (só tem 'Status_Final_ok'/'status_final' com
    Aberto/Encerrado), então sem esse fallback o filtro fica vazio
    quando só notas EE estão selecionadas.
    """
    if "status_usuario" not in df.columns and "status_final" not in df.columns:
        return []
    col_su = df["status_usuario"] if "status_usuario" in df.columns else pd.Series([None] * len(df), index=df.index)
    col_sf = df["status_final"] if "status_final" in df.columns else pd.Series([None] * len(df), index=df.index)
    presentes = {
        cod for cod in (status_base_efetivo(su, sf) for su, sf in zip(col_su, col_sf))
        if cod
    }
    ordenados = [c for c in STATUS_BASE if c in presentes]
    extras = sorted(presentes - set(ordenados))
    return ordenados + extras

# endregion


# region ====================== SESSÃO 2B: Filtros de atributo ==================
# Prioridade, Família de defeito, Tipo de inspeção e Status Base.
# Sprint 4.5 — recuperação de filtros que existiam no app1.py e não foram
# migrados para a plataforma multi-gerencial.
#
# Renderiza SEM abrir seu próprio st.form — o chamador decide se envolve
# num form (Gerência SP/VP, dentro de render_filtros_cascata) ou usa direto
# na sidebar (Gerência Geral, que não tem cascata geográfica).

def render_filtros_atributos(
    df: pd.DataFrame, gerencia: str = "SP", disciplina_sel: str = "VP+EE",
) -> dict:
    """
    Renderiza os filtros de atributo: Prioridade, Família de defeito,
    Tipo de inspeção, Status Base VP e Status Base EE.

    Status Base VP e EE são filtros separados porque usam colunas/esquemas
    diferentes (VP: 17 códigos de status_usuario; EE: Aberto/Encerrado de
    status_final — ver status_base_efetivo em core/glossarios.py). Cada um
    só enxerga as opções da sua própria disciplina (via 'disciplina_label')
    e fica desabilitado quando a disciplina correspondente não está
    carregada (disciplina_sel = "VP" ou "EE" isolado).

    Returns:
        dict com chaves: prioridades, familias, tipos_inspecao,
        status_base_vp, status_base_ee (listas — vazio/tudo selecionado =
        sem filtro)
    """
    uid = gerencia

    st.markdown("**🎯 Prioridade**")
    opcoes_prio = _opcoes_prioridade(df)
    prioridades_sel = st.multiselect(
        "Prioridade",
        options=opcoes_prio,
        default=opcoes_prio,
        key=f"filtro_prioridade_{uid}",
        label_visibility="collapsed",
    )
    if not prioridades_sel:
        prioridades_sel = opcoes_prio

    st.markdown("**🔩 Família de defeito**")
    opcoes_fam = _opcoes_familias(df)
    familias_sel = st.multiselect(
        "Família de defeito",
        options=opcoes_fam,
        default=opcoes_fam,
        key=f"filtro_familia_{uid}",
        label_visibility="collapsed",
    )
    if not familias_sel:
        familias_sel = opcoes_fam

    st.markdown("**🔍 Tipo de inspeção**")
    opcoes_tipo = _opcoes_tipos_inspecao(df)
    tipos_sel = st.multiselect(
        "Tipo de inspeção",
        options=opcoes_tipo,
        default=opcoes_tipo,
        key=f"filtro_tipo_insp_{uid}",
        label_visibility="collapsed",
        help="Origem da nota: Ronda, Drone, Trackstar, Inspeção técnica de AMV, etc.",
    )
    if not tipos_sel:
        tipos_sel = opcoes_tipo

    tem_vp_carregado = "VP" in disciplina_sel
    tem_ee_carregado = "EE" in disciplina_sel

    df_vp = df[df["disciplina_label"] == "VP"] if "disciplina_label" in df.columns else df
    df_ee = df[df["disciplina_label"] == "EE"] if "disciplina_label" in df.columns else df

    st.markdown("**📋 Status Base VP**")
    opcoes_status_vp = _opcoes_status_base(df_vp) if tem_vp_carregado else []
    opcoes_status_vp_label = {f"{c} — {STATUS_BASE.get(c, c)}": c for c in opcoes_status_vp}
    status_vp_nome_sel = st.multiselect(
        "Status Base VP",
        options=list(opcoes_status_vp_label.keys()),
        default=list(opcoes_status_vp_label.keys()),
        key=f"filtro_status_base_vp_{uid}",
        label_visibility="collapsed",
        help="Classificação oficial de status_usuario (SAP/VP) — ver 08_GLOSSARIOS.",
        disabled=not tem_vp_carregado,
    )
    status_vp_sel = [opcoes_status_vp_label[n] for n in status_vp_nome_sel if n in opcoes_status_vp_label]
    if not status_vp_sel:
        status_vp_sel = opcoes_status_vp

    st.markdown("**📋 Status Base EE**")
    opcoes_status_ee = _opcoes_status_base(df_ee) if tem_ee_carregado else []
    opcoes_status_ee_label = {f"{c} — {STATUS_BASE.get(c, c)}": c for c in opcoes_status_ee}
    status_ee_nome_sel = st.multiselect(
        "Status Base EE",
        options=list(opcoes_status_ee_label.keys()),
        default=list(opcoes_status_ee_label.keys()),
        key=f"filtro_status_base_ee_{uid}",
        label_visibility="collapsed",
        help="Status_Final_ok (Aberto/Encerrado) — único status disponível para EE.",
        disabled=not tem_ee_carregado,
    )
    status_ee_sel = [opcoes_status_ee_label[n] for n in status_ee_nome_sel if n in opcoes_status_ee_label]
    if not status_ee_sel:
        status_ee_sel = opcoes_status_ee

    return {
        "prioridades":     prioridades_sel,
        "familias":        familias_sel,
        "tipos_inspecao":  tipos_sel,
        "status_base_vp":  status_vp_sel,
        "status_base_ee":  status_ee_sel,
    }


def aplicar_filtros_atributos(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """
    Aplica os 4 filtros de atributo retornados por render_filtros_atributos().
    Defensivo: ignora filtros cujas colunas não existem ou vieram vazias.
    """
    if df.empty:
        return df

    prioridades = filtros.get("prioridades") or []
    if prioridades and "prioridade" in df.columns:
        df = df[df["prioridade"].isin(prioridades)]

    familias = filtros.get("familias") or []
    if familias and "familia_defeito" in df.columns:
        df = df[df["familia_defeito"].isin(familias)]

    tipos = filtros.get("tipos_inspecao") or []
    if tipos and "tipo_atividade" in df.columns:
        df = df[df["tipo_atividade"].isin(tipos)]

    # Status Base VP e EE são filtros independentes — cada um só restringe
    # as linhas da SUA disciplina (via 'disciplina_label'); linhas da outra
    # disciplina passam intocadas por aquele filtro.
    status_vp = filtros.get("status_base_vp") or []
    status_ee = filtros.get("status_base_ee") or []
    if (status_vp or status_ee) and "disciplina_label" in df.columns:
        col_su = df["status_usuario"] if "status_usuario" in df.columns else pd.Series([None] * len(df), index=df.index)
        col_sf = df["status_final"] if "status_final" in df.columns else pd.Series([None] * len(df), index=df.index)
        efetivo = pd.Series(
            [status_base_efetivo(su, sf) for su, sf in zip(col_su, col_sf)],
            index=df.index,
        )
        eh_vp = df["disciplina_label"] == "VP"
        eh_ee = df["disciplina_label"] == "EE"

        mantem = pd.Series(True, index=df.index)
        if status_vp:
            mantem &= ~eh_vp | efetivo.isin(status_vp)
        if status_ee:
            mantem &= ~eh_ee | efetivo.isin(status_ee)
        df = df[mantem]

    return df

# endregion


# region ====================== SESSÃO 3: render_filtros_cascata() =============

def render_filtros_cascata(
    df: pd.DataFrame, gerencia: str = "SP", disciplina_sel: str = "VP+EE",
) -> dict:
    """
    Renderiza filtros em cascata na sidebar com botões Aplicar / Limpar.

    Usa st.form para que o app só recarregue os dados quando o usuário
    clicar em "✅ Aplicar Filtros" — evita reruns a cada seleção.

    Hierarquia:
        Centro de Trabalho → Ramal → Trecho → Pátio → Período → Atributos

    Returns:
        dict com chaves: centros, ramais, trechos, patios, data_ini, data_fim,
        data_abertura_ini/fim, data_enc_ini/fim, prioridades, familias,
        tipos_inspecao, status_base (os 4 últimos via render_filtros_atributos)
    """
    uid = gerencia  # prefixo de key único por gerência

    # ── Datas mín/máx ─────────────────────────────────────────────────────────
    # data_max = SEMPRE hoje (não deriva dos dados — evita corte de notas 2026
    # quando há datas mal parseadas que ficam como NaT e puxam o max() p/ 2025)
    data_max = date.today()
    data_min = date(2018, 1, 1)
    if "data_nota" in df.columns:
        datas_validas = pd.to_datetime(df["data_nota"], errors="coerce").dropna()
        if not datas_validas.empty:
            # Clampa em [2018-01-01, data_max] — uma data mal parseada na
            # planilha (ex.: serial Excel/ano incorreto) pode gerar um mínimo
            # fora desse intervalo, o que quebra o st.date_input abaixo
            # (min_value/max_value fixos) com StreamlitAPIException.
            candidato = datas_validas.min().date()
            data_min = min(max(candidato, date(2018, 1, 1)), data_max)
            # ⚠️ NÃO sobrescreve data_max — mantém date.today()

    # ── Botão Limpar (fora do form — limpa session_state e rerun imediato) ───
    if st.button(
        "🗑️ Limpar filtros",
        key=f"filtro_reset_{uid}",
        use_container_width=True,
        type="secondary",
    ):
        for key in [
            f"filtro_centros_{uid}", f"filtro_ramais_{uid}",
            f"filtro_trechos_{uid}", f"filtro_patios_{uid}",
            f"filtro_data_ini_{uid}", f"filtro_data_fim_{uid}",
            f"filtro_prioridade_{uid}", f"filtro_familia_{uid}",
            f"filtro_tipo_insp_{uid}",
            f"filtro_status_base_vp_{uid}", f"filtro_status_base_ee_{uid}",
        ]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # ── Formulário: todos os filtros + botão Aplicar ──────────────────────────
    with st.form(key=f"form_filtros_{uid}"):

        # 1. Centro de Trabalho
        opcoes_centros = _opcoes_centros(df, gerencia)
        centros_sel = st.multiselect(
            "🏢 Centro de Trabalho",
            options=opcoes_centros,
            default=opcoes_centros,
            key=f"filtro_centros_{uid}",
            help="Filtre por centro de coordenação regional",
        )
        if not centros_sel:
            centros_sel = opcoes_centros

        # 2. Ramal (nome completo na exibição, sigla internamente)
        siglas_disp = _opcoes_ramais(df, centros_sel)
        opcoes_ramal_label = {
            nome_ramal(s, "completo_sigla"): s for s in siglas_disp
        }
        ramais_nome_sel = st.multiselect(
            "🚂 Ramal",
            options=list(opcoes_ramal_label.keys()),
            default=list(opcoes_ramal_label.keys()),
            key=f"filtro_ramais_{uid}",
            help="Nome completo do ramal conforme nomenclatura ANTT/MRS",
        )
        ramais_sel = [
            opcoes_ramal_label[n]
            for n in ramais_nome_sel
            if n in opcoes_ramal_label
        ]
        if not ramais_sel and siglas_disp:
            ramais_sel = siglas_disp

        # 3. Trecho
        opcoes_trechos = _opcoes_trechos(df, centros_sel, ramais_sel)
        if opcoes_trechos:
            trechos_sel = st.multiselect(
                "📍 Trecho (Origem → Destino)",
                options=opcoes_trechos,
                default=opcoes_trechos,
                key=f"filtro_trechos_{uid}",
                help="Par Origem-Destino dentro do ramal",
            )
            if not trechos_sel:
                trechos_sel = opcoes_trechos
        else:
            trechos_sel = []

        # 4. Pátio
        opcoes_patios = _opcoes_patios(df, centros_sel, ramais_sel, trechos_sel)
        if opcoes_patios:
            patios_sel = st.multiselect(
                "🚉 Pátio (Origem)",
                options=opcoes_patios,
                default=opcoes_patios,
                key=f"filtro_patios_{uid}",
                help="Estação/ponto de origem da nota de manutenção",
            )
            if not patios_sel:
                patios_sel = opcoes_patios
        else:
            patios_sel = []

        # 5. Período — Abertura da Nota
        st.markdown("**📅 Abertura da Nota**")
        col_ab1, col_ab2 = st.columns(2)
        with col_ab1:
            data_abertura_ini = st.date_input(
                "Início",
                value=data_min,
                min_value=date(2018, 1, 1),
                max_value=data_max,
                key=f"filtro_ab_ini_{uid}",
                format="DD/MM/YYYY",
            )
        with col_ab2:
            data_abertura_fim = st.date_input(
                "Fim",
                value=data_max,
                min_value=date(2018, 1, 1),
                max_value=data_max,
                key=f"filtro_ab_fim_{uid}",
                format="DD/MM/YYYY",
            )
        if data_abertura_ini > data_abertura_fim:
            st.warning("⚠️ Início de abertura maior que o fim.")
            data_abertura_ini, data_abertura_fim = data_abertura_fim, data_abertura_ini

        # 6. Período — Encerramento da Nota (opcional)
        tem_enc = "data_encerramento" in df.columns
        st.markdown("**📅 Encerramento da Nota**")
        if not tem_enc:
            st.caption("_(coluna data_encerramento não disponível nos dados)_")
            data_enc_ini = None
            data_enc_fim = None
        else:
            col_en1, col_en2 = st.columns(2)
            with col_en1:
                data_enc_ini = st.date_input(
                    "Início",
                    value=date(2018, 1, 1),
                    min_value=date(2018, 1, 1),
                    max_value=data_max,
                    key=f"filtro_enc_ini_{uid}",
                    format="DD/MM/YYYY",
                )
            with col_en2:
                data_enc_fim = st.date_input(
                    "Fim",
                    value=data_max,
                    min_value=date(2018, 1, 1),
                    max_value=data_max,
                    key=f"filtro_enc_fim_{uid}",
                    format="DD/MM/YYYY",
                )
            if data_enc_ini > data_enc_fim:
                st.warning("⚠️ Início de encerramento maior que o fim.")
                data_enc_ini, data_enc_fim = data_enc_fim, data_enc_ini

        # st.date_input nunca retorna None — detecta se o usuário realmente
        # estreitou o período de encerramento em relação ao padrão "sem filtro"
        # (intervalo completo). Evita que notas ainda em aberto (sem
        # data_encerramento) sejam descartadas por engano quando o usuário só
        # mexeu no filtro de Abertura.
        filtro_enc_ativo = tem_enc and (
            data_enc_ini != date(2018, 1, 1) or data_enc_fim != data_max
        )

        # 7. Filtros de atributo — Prioridade, Família, Tipo de inspeção, Status Base
        # (Sprint 4.5 — recuperados do app1.py, ver components/filtros.py Sessão 2B)
        st.markdown("---")
        st.markdown("**🎛️ Atributos**")
        filtros_attrs = render_filtros_atributos(df, gerencia, disciplina_sel)

        # Botão Aplicar (dentro do form — dispara o rerun com novos valores)
        st.form_submit_button(
            "✅ Aplicar Filtros",
            use_container_width=True,
            type="primary",
        )

    # Mantém data_ini/data_fim como aliases de abertura (backward compat)
    return {
        "centros":          centros_sel,
        "ramais":           ramais_sel,
        "trechos":          trechos_sel,
        "patios":           patios_sel,
        "data_ini":         data_abertura_ini,   # alias backward compat
        "data_fim":         data_abertura_fim,   # alias backward compat
        "data_abertura_ini": data_abertura_ini,
        "data_abertura_fim": data_abertura_fim,
        "data_enc_ini":     data_enc_ini,
        "data_enc_fim":     data_enc_fim,
        "filtro_enc_ativo": filtro_enc_ativo,
        **filtros_attrs,   # prioridades, familias, tipos_inspecao, status_base
    }

# endregion
