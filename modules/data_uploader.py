# modules/data_uploader.py — Tela de Upload de Planilhas SAP
# Acessível apenas para Admin e Assistente (da gerência correspondente).
# Pipeline: upload → parser → preview → confirmar → gravar no Supabase

import io
import streamlit as st
import pandas as pd

from auth.permissions import require_login, can_upload
from auth.session import get_id, get_gerencia, get_perfil
from database.client import get_supabase
from database.queries import log_acesso
from core.parser import processar_planilha, df_para_registros_supabase


# region ====================== SESSÃO 1: Header ======================

def _render_header():
    st.markdown("""
    <div style="margin-bottom: 0.5rem;">
        <span style="font-size:0.8rem; color:#6b7280; font-weight:500;
                     text-transform:uppercase; letter-spacing:1px;">
            ALIMENTAÇÃO DE DADOS
        </span>
        <h1 style="font-size:1.9rem; font-weight:700; color:#1e3a5f;
                    margin:4px 0 0 0; line-height:1.2;">
            📤 Upload de Planilhas
        </h1>
        <p style="color:#6b7280; font-size:0.92rem; margin:6px 0 0 0;">
            Envie a planilha exportada do SAP para atualizar a base de dados.
        </p>
    </div>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Seleção de Gerência e Disciplina ======================

def _render_selecao() -> tuple[str, str]:
    """
    Retorna (gerencia_selecionada, disciplina_selecionada).
    Admin pode escolher qualquer gerência. Assistente vê só a sua.
    """
    perfil   = get_perfil()
    gerencia_usuario = get_gerencia()

    st.markdown("### ⚙️ Configuração do Upload")
    col1, col2 = st.columns(2)

    with col1:
        if perfil == "admin":
            gerencia = st.selectbox(
                "🏭 Gerência de destino",
                ["SP", "VP"],
                help="Para qual gerência os dados serão carregados?"
            )
        else:
            gerencia = gerencia_usuario
            st.markdown(f"""
            <div style="background:#eff6ff; border:1px solid #bfdbfe;
                border-radius:8px; padding:10px 14px;">
                <div style="font-size:0.75rem; color:#1e40af; font-weight:600;">GERÊNCIA</div>
                <div style="font-size:1.1rem; font-weight:700; color:#1e3a5f;">🏭 {gerencia}</div>
            </div>
            """, unsafe_allow_html=True)

    with col2:
        disciplina = st.selectbox(
            "📋 Disciplina",
                ["VP", "EE", "RASF"],
                format_func=lambda x: {
                    "VP":   "🛤️ Via Permanente (VP)",
                    "EE":   "⚡ Eletroeletrônica (EE)",
                    "RASF": "🔌 RASF — Análise de Falha EE",
                }.get(x, x),
                help="VP/EE = planilha SAP de notas. RASF = export da Reunião de "
                     "Análise Sistêmica de Falha (alimenta a aba de Inteligência EE)."
            )

    return gerencia, disciplina

# endregion


# region ====================== SESSÃO 3: Upload e Processamento ======================

def _render_upload_area(gerencia: str, disciplina: str):
    """Área de upload + pipeline completo."""

    # RASF tem pipeline próprio (parser + tabela dedicada rasf_ee).
    if disciplina == "RASF":
        _render_upload_rasf(gerencia)
        return

    st.markdown("---")
    st.markdown("### 📁 Selecione o Arquivo")

    # Info sobre formatos aceitos
    st.markdown("""
    <div style="background:#f8fafc; border:1px solid #e5e7eb; border-radius:10px;
        padding:12px 16px; margin-bottom:1rem; font-size:0.85rem; color:#374151;">
        <strong>Formatos aceitos:</strong> &nbsp;
        ✅ <code>.xlsx</code> &nbsp;|&nbsp; ✅ <code>.xls</code><br>
        <strong>Tipos de planilha SAP:</strong> Unificada · Notas Abertas · Notas Concluídas
        <em>(detecção automática)</em><br>
        <strong>Tamanho máximo:</strong> 50 MB
    </div>
    """, unsafe_allow_html=True)

    arquivo = st.file_uploader(
        "Planilha SAP",
        type=["xlsx", "xls"],
        key="upload_arquivo",
        label_visibility="collapsed",
        help="Arraste o arquivo ou clique para selecionar",
    )

    if not arquivo:
        return

    # Valida tamanho
    tamanho_mb = arquivo.size / (1024 * 1024)
    if tamanho_mb > 50:
        st.error(f"❌ Arquivo muito grande ({tamanho_mb:.1f} MB). Máximo: 50 MB.")
        return

    # Processa
    st.markdown("---")
    st.markdown("### 🔄 Processando...")

    with st.spinner(f"Analisando planilha **{arquivo.name}**..."):
        try:
            arquivo_bytes = io.BytesIO(arquivo.read())
            df, formato, disc_detectada = processar_planilha(
                arquivo_bytes=arquivo_bytes,
                nome_arquivo=arquivo.name,
                gerencia=gerencia,
                disciplina_override=disciplina,
            )
        except ValueError as e:
            st.error(f"❌ {e}")
            return
        except Exception as e:
            st.error(f"❌ Erro inesperado ao processar: {e}")
            return

    if df.empty:
        st.warning("⚠️ Nenhuma nota encontrada na planilha.")
        return

    # Notas cuja gerência detectada (por centro_trab/gerencia_origem) o
    # usuário não tem permissão de subir são descartadas do upload — evita
    # que um Assistente da SP suba, sem querer, notas da VP misturadas
    # no mesmo arquivo.
    gerencias_presentes = sorted(df["gerencia"].dropna().unique().tolist())
    nao_permitidas = [g for g in gerencias_presentes if not can_upload(g)]
    if nao_permitidas:
        qtd_excluida = int(df["gerencia"].isin(nao_permitidas).sum())
        st.warning(
            f"⚠️ {qtd_excluida} nota(s) identificadas para a(s) gerência(s) "
            f"**{', '.join(nao_permitidas)}** foram descartadas — você só tem "
            f"permissão de upload para a Gerência **{gerencia}**."
        )
        df = df[~df["gerencia"].isin(nao_permitidas)].reset_index(drop=True)
        if df.empty:
            st.error("❌ Nenhuma nota restante após aplicar as permissões de upload.")
            return

    # Mostra resultado do processamento
    _render_preview(df, arquivo.name, formato, disc_detectada, tamanho_mb, gerencia)


def _render_preview(
    df: pd.DataFrame,
    nome_arquivo: str,
    formato: str,
    disciplina: str,
    tamanho_mb: float,
    gerencia: str,
):
    """Mostra preview dos dados e botão de confirmação."""

    formato_legivel = {
        "A": "Unificada (Status_Final_ok)",
        "B": "Notas Abertas (Marcador inic.)",
        "C": "Notas Concluídas (Ponto de partida)",
    }.get(formato, formato)

    total_notas = len(df)
    gerencias_presentes = sorted(df["gerencia"].dropna().unique().tolist()) if "gerencia" in df.columns else [gerencia]
    mista = len(gerencias_presentes) > 1

    # Cards de resumo
    st.markdown("### ✅ Planilha Reconhecida")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📋 Total de Notas", f"{total_notas:,}".replace(",", "."))
    with col2:
        st.metric("🏭 Gerência", " + ".join(gerencias_presentes) if mista else gerencia)
    with col3:
        st.metric("📌 Disciplina", disciplina)
    with col4:
        st.metric("📄 Formato", f"Tipo {formato}")

    st.caption(f"Formato detectado: **{formato_legivel}** · Arquivo: `{nome_arquivo}` ({tamanho_mb:.1f} MB)")

    # Planilha com mais de uma gerência detectada — mostra o detalhamento
    if mista:
        contagem = df["gerencia"].value_counts()
        st.info(
            "📦 **Arquivo com notas de mais de uma gerência** — detectado pelo "
            "centro de trabalho de cada nota. Cada gerência será gravada "
            "separadamente:\n\n" +
            "\n".join(f"- **{g}**: {int(contagem[g]):,} nota(s)".replace(",", ".") for g in gerencias_presentes)
        )

    if "gerencia_auto" in df.columns:
        qtd_fallback = int((~df["gerencia_auto"]).sum())
        if qtd_fallback:
            st.warning(
                f"⚠️ {qtd_fallback} nota(s) não puderam ser classificadas automaticamente "
                f"pelo centro de trabalho e foram associadas à Gerência **{gerencia}** "
                "(selecionada manualmente) — confira se está correto."
            )

    # KPIs rápidos
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if "prioridade" in df.columns:
            criticos = df["prioridade"].astype(str).str.contains("1-|2-", na=False).sum()
            st.metric("🚨 Prioridade 1+2", f"{criticos:,}".replace(",", "."))
    with col_b:
        if "ramal" in df.columns:
            ramais = df["ramal"].nunique()
            st.metric("🚂 Ramais únicos", ramais)
    with col_c:
        if "lead_time_dias" in df.columns:
            lt_medio = df["lead_time_dias"].dropna().mean()
            st.metric("⏱️ Lead Time Médio", f"{lt_medio:.0f} dias" if not pd.isna(lt_medio) else "—")

    # Preview da tabela (primeiras 20 linhas)
    with st.expander("🔍 Preview dos dados (primeiras 20 linhas)", expanded=False):
        colunas_show = [c for c in [
            "numero_nota", "gerencia", "prioridade", "ramal", "trecho", "origem",
            "familia_defeito", "defeito_legivel", "status_amigavel",
            "lead_time_dias", "score", "data_nota",
        ] if c in df.columns and (c != "gerencia" or mista)]
        st.dataframe(
            df[colunas_show].head(20),
            use_container_width=True,
            hide_index=True,
        )

    # Aviso sobre substituição
    gerencias_txt = " e ".join(gerencias_presentes) if mista else gerencia
    st.warning(
        f"⚠️ **Atenção:** Esta ação irá **substituir** a base ativa da "
        f"Gerência **{gerencias_txt}** — Disciplina **{disciplina}**. "
        "Os dados anteriores serão arquivados e não poderão ser recuperados automaticamente.",
        icon="⚠️"
    )

    # Botão de confirmação
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    col_btn, col_vazio = st.columns([1, 3])
    with col_btn:
        confirmar = st.button(
            f"✅ Confirmar Upload — {total_notas} notas",
            type="primary",
            use_container_width=True,
            key="btn_confirmar_upload",
        )

    if confirmar:
        _executar_upload(df, nome_arquivo, disciplina, tamanho_mb)

# endregion


# region ====================== SESSÃO 4: Persistência no Supabase ======================

def _executar_upload(
    df: pd.DataFrame,
    nome_arquivo: str,
    disciplina: str,
    tamanho_mb: float,
):
    """
    Persiste as notas no Supabase, agrupando por gerência detectada em cada
    linha (ver core/parser.py: detectar_gerencia_nota) — permite subir um
    arquivo com notas de mais de uma gerência de uma vez.
    """
    gerencias_presentes = sorted(df["gerencia"].dropna().unique().tolist())
    total_geral = len(df)
    mista = len(gerencias_presentes) > 1

    sucesso_algum = False
    for ger in gerencias_presentes:
        sub_df = df[df["gerencia"] == ger].reset_index(drop=True)
        tamanho_proporcional = (
            tamanho_mb * (len(sub_df) / total_geral) if total_geral else tamanho_mb
        )
        if mista:
            st.markdown(f"#### 🏭 Gerência {ger} — {len(sub_df):,} nota(s)".replace(",", "."))
        if _executar_upload_gerencia(sub_df, nome_arquivo, ger, disciplina, tamanho_proporcional):
            sucesso_algum = True

    if sucesso_algum:
        st.balloons()
        # Limpa o estado do uploader para permitir novo upload
        st.session_state.pop("upload_arquivo", None)


def _executar_upload_gerencia(
    df: pd.DataFrame,
    nome_arquivo: str,
    gerencia: str,
    disciplina: str,
    tamanho_mb: float,
) -> bool:
    """
    Persiste as notas de UMA gerência em 3 etapas:
    1. Arquiva uploads ativos anteriores (gerencia+disciplina)
    2. Insere registro em uploads_historico
    3. Insere notas em lote

    Retorna True em caso de sucesso, False em caso de falha.
    """
    supabase    = get_supabase()
    usuario_id  = get_id()
    total_notas = len(df)

    barra = st.progress(0, text="Iniciando upload...")

    try:
        # Etapa 1: Arquivar uploads anteriores da mesma gerência+disciplina
        barra.progress(10, text="Arquivando base anterior...")
        supabase.table("uploads_historico").update({"status": "substituido"}).match({
            "gerencia":   gerencia,
            "disciplina": disciplina,
            "status":     "ativo",
        }).execute()

        # Etapa 2: Criar registro em uploads_historico
        barra.progress(25, text="Registrando upload...")
        resp_upload = supabase.table("uploads_historico").insert({
            "usuario_id":    usuario_id,
            "gerencia":      gerencia,
            "disciplina":    disciplina,
            "nome_arquivo":  nome_arquivo,
            "total_notas":   total_notas,
            "tamanho_bytes": int(tamanho_mb * 1024 * 1024),
            "status":        "ativo",
            "metadados": {
                "colunas": list(df.columns),
                "ramais":  df["ramal"].dropna().unique().tolist() if "ramal" in df.columns else [],
            },
        }).execute()

        upload_id = resp_upload.data[0]["id"]

        # Etapa 3: Inserir notas em lotes de 500
        barra.progress(40, text="Convertendo dados...")
        registros = df_para_registros_supabase(df, upload_id)

        tamanho_lote = 500
        total_lotes  = (len(registros) + tamanho_lote - 1) // tamanho_lote

        for i in range(0, len(registros), tamanho_lote):
            lote = registros[i : i + tamanho_lote]
            supabase.table("notas").insert(lote).execute()

            progresso = 40 + int(55 * (i + tamanho_lote) / len(registros))
            lote_num  = i // tamanho_lote + 1
            barra.progress(
                min(progresso, 95),
                text=f"Inserindo notas... lote {lote_num}/{total_lotes}"
            )

        barra.progress(100, text="Concluído!")

        # Log de auditoria
        log_acesso(usuario_id, "upload_dados", {
            "gerencia":    gerencia,
            "disciplina":  disciplina,
            "arquivo":     nome_arquivo,
            "total_notas": total_notas,
            "upload_id":   upload_id,
        })

        st.success(
            f"✅ **Upload concluído!** {total_notas:,} notas da Gerência **{gerencia}** "
            f"— **{disciplina}** carregadas com sucesso.".replace(",", ".")
        )

        from database.queries import invalidar_cache_notas
        invalidar_cache_notas()

        # Recálculo automático de alertas (Sprint 5) — não bloqueia o upload
        _recalcular_alertas_pos_upload(gerencia, disciplina)

        return True

    except Exception as e:
        barra.empty()
        st.error(f"❌ Falha durante o upload da Gerência {gerencia}: {e}")
        st.info(
            "Os dados anteriores **não foram removidos** pois o erro ocorreu antes da substituição.",
            icon="ℹ️"
        )
        return False


def _recalcular_alertas_pos_upload(gerencia: str, disciplina: str) -> None:
    """
    Dispara o motor de alertas (Sprint 5) logo após um upload bem-sucedido.
    Falha graciosamente: um erro aqui NÃO deve invalidar o upload já concluído.
    """
    try:
        from core.alertas import gerar_alertas, persistir_alertas
        from database.queries import get_alertas, contar_alertas_novos

        with st.spinner("🚨 Recalculando alertas automáticos..."):
            df_alertas = gerar_alertas(gerencia, disciplina)
            n = persistir_alertas(df_alertas)

        get_alertas.clear()
        contar_alertas_novos.clear()

        if n:
            st.info(f"🚨 {n} alerta(s) atualizado(s). Veja em **🚨 Alertas** na barra lateral.")

        # Previsão de e-mail: só envia se ativado nas configurações
        try:
            from core.notificacoes import enviar_email_alertas
            if not df_alertas.empty:
                enviar_email_alertas(df_alertas, gerencia)
        except Exception:
            pass
    except Exception as e:
        st.warning(f"⚠️ Upload concluído, mas o recálculo de alertas falhou: {e}")

# endregion


# region ====================== SESSÃO 4B: Pipeline RASF (Inteligência EE) ======

def _render_upload_rasf(gerencia: str):
    """
    Upload do export RASF (Reunião de Análise Sistêmica de Falha).
    Parser dedicado (core.parser_rasf) → tabela rasf_ee. Mesmo padrão
    anti-duplicação dos uploads de notas (uploads_historico, disciplina='RASF').
    """
    from core.parser_rasf import carregar_rasf_xlsx
    from database.queries_rasf import carregar_gatilhos_analise

    gatilhos_ativos = carregar_gatilhos_analise()

    st.markdown("---")
    st.markdown("### 📁 Selecione o export RASF")
    st.markdown(f"""
    <div style="background:#faf5ff; border:1px solid #e9d5ff; border-radius:10px;
        padding:12px 16px; margin-bottom:1rem; font-size:0.85rem; color:#374151;">
        <strong>Arquivo esperado:</strong> export RASF de Eletroeletrônica
        (aba <code>Export</code>, layout canônico de 77 colunas).<br>
        <strong>Alimenta:</strong> a aba <em>🔌 Inteligência de Falhas EE</em>
        nas Gerências e na Visão Global.<br>
        <strong>Tamanho máximo:</strong> 50 MB<br>
        <strong>Gatilhos de análise ativos</strong> (PG-ENG-0088, editável em
        Configurações): {', '.join(sorted(gatilhos_ativos))}
    </div>
    """, unsafe_allow_html=True)

    arquivo = st.file_uploader(
        "Export RASF",
        type=["xlsx", "xls"],
        key="upload_rasf",
        label_visibility="collapsed",
    )
    if not arquivo:
        return

    tamanho_mb = arquivo.size / (1024 * 1024)
    if tamanho_mb > 50:
        st.error(f"❌ Arquivo muito grande ({tamanho_mb:.1f} MB). Máximo: 50 MB.")
        return

    st.markdown("---")
    st.markdown("### 🔄 Processando RASF...")
    with st.spinner(f"Analisando **{arquivo.name}**..."):
        try:
            arquivo_bytes = io.BytesIO(arquivo.read())
            df = carregar_rasf_xlsx(arquivo_bytes, gatilhos_analise=gatilhos_ativos)
        except Exception as e:
            st.error(f"❌ Erro ao processar o RASF: {e}")
            return

    if df.empty:
        st.warning("⚠️ Nenhuma linha válida encontrada no export RASF.")
        return

    # Linhas com "Gerência" fora de GEE.SP/GEV.SP/GEE.VP/GEV.VP viram None em
    # core.parser_rasf._mapear_gerencia() — sem este aviso elas desapareceriam
    # silenciosamente do upload (nunca entram em gerencias_presentes abaixo).
    sem_gerencia = df["gerencia"].isna()
    if sem_gerencia.any():
        qtd_sem = int(sem_gerencia.sum())
        valores_originais = (
            df.loc[sem_gerencia, "_gerencia_raw"].dropna().unique().tolist()
            if "_gerencia_raw" in df.columns else []
        )
        detalhe = f" (valores encontrados: {', '.join(map(str, valores_originais))})" if valores_originais else ""
        st.warning(
            f"⚠️ **{qtd_sem} linha(s) com gerência não reconhecida** foram descartadas{detalhe}. "
            f"Só são aceitos: GEE.SP, GEV.SP, GEE.VP, GEV.VP. Verifique a coluna "
            f"'Gerência' no export se o número parecer alto."
        )
        df = df[~sem_gerencia].reset_index(drop=True)
        if df.empty:
            st.error("❌ Nenhuma linha com gerência reconhecida no arquivo.")
            return

    # Descarta gerências sem permissão (mesma regra dos uploads de notas).
    gerencias_presentes = sorted(df["gerencia"].dropna().unique().tolist())
    nao_permitidas = [g for g in gerencias_presentes if not can_upload(g)]
    if nao_permitidas:
        qtd = int(df["gerencia"].isin(nao_permitidas).sum())
        st.warning(
            f"⚠️ {qtd} linha(s) da(s) gerência(s) **{', '.join(nao_permitidas)}** "
            f"foram descartadas — você só pode subir RASF da Gerência **{gerencia}**."
        )
        df = df[~df["gerencia"].isin(nao_permitidas)].reset_index(drop=True)
        if df.empty:
            st.error("❌ Nenhuma linha restante após aplicar as permissões.")
            return

    # Preview enxuto
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Linhas", f"{len(df):,}".replace(",", "."))
    c2.metric("Reincid. ativo", f"{int(df['reincidencia_ativo'].sum()):,}".replace(",", "."))
    c3.metric("Sem 6M classificado", f"{int(df['lacuna_rca'].sum()):,}".replace(",", "."))
    c4.metric("THP (h)", f"{df['thp_min'].sum()/60:,.0f}".replace(",", "."))

    st.dataframe(
        df[[c for c in ["data_nota", "numero_nota", "gerencia", "local_patio",
                        "sistema", "anomalia_sintoma", "gatilho_eng", "thp_min"]
            if c in df.columns]].head(20),
        use_container_width=True, hide_index=True,
    )

    if st.button("✅ Confirmar e gravar RASF", type="primary", use_container_width=True):
        _executar_upload_rasf(df, arquivo.name, gerencia, tamanho_mb)


def _executar_upload_rasf(df, nome_arquivo: str, gerencia_default: str, tamanho_mb: float):
    """Grava o RASF em rasf_ee, uma gerência por vez (anti-duplicação)."""
    from core.parser_rasf import df_rasf_para_registros
    from database.queries_rasf import DISCIPLINA_RASF, get_rasf_cached

    gerencias_presentes = sorted(df["gerencia"].dropna().unique().tolist())
    total = len(df)
    sucesso = False

    for ger in gerencias_presentes:
        sub = df[df["gerencia"] == ger].reset_index(drop=True)
        if _gravar_rasf_gerencia(sub, nome_arquivo, ger,
                                 tamanho_mb * (len(sub) / total) if total else tamanho_mb):
            sucesso = True

    if sucesso:
        try:
            get_rasf_cached.clear()
        except Exception:
            pass
        st.balloons()
        st.session_state.pop("upload_rasf", None)


def _gravar_rasf_gerencia(df, nome_arquivo: str, gerencia: str, tamanho_mb: float) -> bool:
    from core.parser_rasf import df_rasf_para_registros
    from database.queries_rasf import DISCIPLINA_RASF

    supabase   = get_supabase()
    usuario_id = get_id()
    total      = len(df)
    barra = st.progress(0, text="Iniciando gravação do RASF...")

    try:
        barra.progress(10, text="Arquivando RASF anterior...")
        supabase.table("uploads_historico").update({"status": "substituido"}).match({
            "gerencia": gerencia, "disciplina": DISCIPLINA_RASF, "status": "ativo",
        }).execute()

        barra.progress(25, text="Registrando upload...")
        resp = supabase.table("uploads_historico").insert({
            "usuario_id":    usuario_id,
            "gerencia":      gerencia,
            "disciplina":    DISCIPLINA_RASF,
            "nome_arquivo":  nome_arquivo,
            "total_notas":   total,
            "tamanho_bytes": int(tamanho_mb * 1024 * 1024),
            "status":        "ativo",
            "metadados": {"origem": "RASF", "colunas": list(df.columns)},
        }).execute()
        upload_id = resp.data[0]["id"]

        barra.progress(40, text="Convertendo dados...")
        registros = df_rasf_para_registros(df, upload_id)

        lote = 500
        total_lotes = (len(registros) + lote - 1) // lote
        for i in range(0, len(registros), lote):
            supabase.table("rasf_ee").insert(registros[i:i + lote]).execute()
            barra.progress(min(40 + int(55 * (i + lote) / len(registros)), 95),
                           text=f"Inserindo... lote {i//lote + 1}/{total_lotes}")

        barra.progress(100, text="Concluído!")
        log_acesso(usuario_id, "upload_rasf", {
            "gerencia": gerencia, "arquivo": nome_arquivo,
            "total": total, "upload_id": upload_id,
        })
        st.success(
            f"✅ **RASF gravado!** {total:,} linha(s) da Gerência **{gerencia}** "
            f"carregadas.".replace(",", ".")
        )
        return True

    except Exception as e:
        barra.empty()
        st.error(f"❌ Falha ao gravar RASF da Gerência {gerencia}: {e}")
        return False

# endregion


# region ====================== SESSÃO 5: Histórico de Uploads ======================

def _render_historico():
    """Exibe o histórico de uploads do usuário atual."""
    st.markdown("---")
    st.markdown("### 📋 Histórico de Uploads")

    try:
        supabase     = get_supabase()
        perfil       = get_perfil()
        usuario_id   = get_id()
        gerencia_usr = get_gerencia()

        query = (
            supabase.table("uploads_historico")
            .select("*, usuarios(nome, email)")
            .order("enviado_em", desc=True)
            .limit(20)
        )

        # Assistente vê só os próprios; admin vê todos
        if perfil == "assistente":
            query = query.eq("usuario_id", usuario_id)

        resp = query.execute()

        if not resp.data:
            st.info("Nenhum upload realizado ainda.", icon="📭")
            return

        df_hist = pd.DataFrame(resp.data)

        # Formata para exibição
        from datetime import datetime as dt
        def fmt_data(val):
            try:
                d = dt.fromisoformat(str(val).replace("Z", "+00:00"))
                return d.strftime("%d/%m/%Y %H:%M")
            except Exception:
                return "—"

        def fmt_status(val):
            return {"ativo": "🟢 Ativo", "substituido": "🔵 Substituído", "arquivado": "⚫ Arquivado"}.get(val, val)

        df_hist["Enviado em"]  = df_hist["enviado_em"].apply(fmt_data)
        df_hist["Status"]      = df_hist["status"].apply(fmt_status)
        df_hist["Notas"]       = df_hist["total_notas"].apply(lambda x: f"{int(x):,}".replace(",", "."))
        df_hist["Enviado por"] = df_hist["usuarios"].apply(
            lambda x: x.get("nome", "—") if isinstance(x, dict) else "—"
        )

        colunas_show = ["gerencia", "disciplina", "nome_arquivo", "Notas", "Enviado em", "Enviado por", "Status"]
        colunas_show = [c for c in colunas_show if c in df_hist.columns or c in df_hist.columns]

        st.dataframe(
            df_hist[[c for c in colunas_show if c in df_hist.columns]].rename(columns={
                "gerencia":    "Gerência",
                "disciplina":  "Disciplina",
                "nome_arquivo":"Arquivo",
            }),
            use_container_width=True,
            hide_index=True,
        )

    except Exception as e:
        if "SSL" in str(e) or "certificate" in str(e).lower():
            st.warning("⚠️ Sem acesso ao banco via rede corporativa. Use hotspot ou Streamlit Cloud.", icon="🔒")
        else:
            st.error(f"Erro ao buscar histórico: {e}")

# endregion


# region ====================== SESSÃO 6: Renderização Principal ======================

def render_upload():
    """Ponto de entrada: renderiza a tela de upload."""
    require_login()

    _render_header()
    st.divider()

    gerencia, disciplina = _render_selecao()

    # Verifica permissão para a gerência selecionada
    if not can_upload(gerencia):
        st.error(f"🚫 Você não tem permissão para fazer upload na Gerência {gerencia}.")
        return

    _render_upload_area(gerencia, disciplina)
    _render_historico()

# endregion
