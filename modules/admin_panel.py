# modules/admin_panel.py
# Painel Administrativo — CRUD de Usuários + Logs de Acesso + Configurações
# Sprint 4 — Visão Geral + Admin
#
# Acesso: apenas perfil 'admin'
#
# Abas:
#   1. 👥 Usuários    — CRUD completo (criar, editar, ativar/desativar)
#   2. 📋 Logs        — Histórico de acessos e uploads
#   3. ⚙️ Configurações — Pesos padrão de score por gerência, km de malha

from datetime import datetime

import streamlit as st
import pandas as pd

from database.client  import get_supabase, get_supabase_admin
from database.queries import get_uploads_historico

# region ====================== SESSÃO 1: Guard de acesso =====================

def render_admin_panel() -> None:
    """
    Ponto de entrada do painel admin.
    Chamado pelo app.py; verifica perfil antes de renderizar.
    """
    usuario = st.session_state.get("usuario")

    if not usuario or usuario.get("perfil") != "admin":
        st.error("🚫 Acesso restrito — apenas Administradores.")
        st.stop()
        return

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='
            background: linear-gradient(135deg, #1e3a5f 0%, #dc2626 100%);
            padding: 16px 24px;
            border-radius: 12px;
            margin-bottom: 16px;
        '>
            <h2 style='color:#fff; margin:0; font-size:22px;'>
                👑 Painel Administrativo — MRS Sentinel
            </h2>
            <p style='color:rgba(255,255,255,0.7); margin:4px 0 0 0; font-size:13px;'>
                Gestão de usuários · Auditoria de acessos · Configurações da plataforma
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    
    tab_users, tab_logs, tab_config, tab_dados = st.tabs([
        "👥 Usuários",
        "📋 Logs de Acesso",
        "⚙️ Configurações",
        "🗑️ Gestão de Dados",
    ])

    with tab_users:
        _render_aba_usuarios(usuario)

    with tab_logs:
        _render_aba_logs()

    with tab_config:
        _render_aba_configuracoes()

    with tab_dados:
        _render_aba_gestao_dados()

# endregion


# region ====================== SESSÃO 2: Aba Usuários (CRUD) =================

def _render_aba_usuarios(admin_logado: dict) -> None:
    """
    CRUD completo de usuários.

    Funcionalidades:
      - Listagem com status ativo/inativo
      - Criar novo usuário (conta real no Supabase Auth, sem depender de SMTP)
      - Editar perfil e gerência
      - Resetar senha diretamente via API admin do Supabase
      - Ativar / desativar (soft delete — nunca apaga do banco)
    """
    st.markdown("### 👥 Gestão de Usuários")

    # ── 2.1: Lista de usuários ────────────────────────────────────────────────
    df_users = _buscar_usuarios()

    if df_users.empty:
        st.info("📭 Nenhum usuário cadastrado.")
    else:
        # Formata para exibição
        df_display = df_users[[c for c in [
            "nome", "email", "perfil", "gerencia", "ativo",
            "ultimo_login", "criado_em",
        ] if c in df_users.columns]].copy()

        df_display.rename(columns={
            "nome":         "Nome",
            "email":        "E-mail",
            "perfil":       "Perfil",
            "gerencia":     "Gerência",
            "ativo":        "Ativo",
            "ultimo_login": "Último Login",
            "criado_em":    "Criado em",
        }, inplace=True)

        # Formata datas
        for col in ["Último Login", "Criado em"]:
            if col in df_display.columns:
                df_display[col] = pd.to_datetime(df_display[col], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            height=min(400, 45 * len(df_display) + 80),
        )

    st.markdown("---")

    # ── 2.2: Ações em cols ────────────────────────────────────────────────────
    acao_col1, acao_col2 = st.columns([1, 1])

    with acao_col1:
        _form_criar_usuario(admin_logado)

    with acao_col2:
        _form_editar_usuario(df_users)


def _form_criar_usuario(admin_logado: dict) -> None:
    """Formulário para criar novo usuário."""
    with st.expander("➕ Criar Novo Usuário", expanded=False):
        with st.form("form_criar_user"):
            nome   = st.text_input("Nome completo *", placeholder="Ex: João da Silva")
            email  = st.text_input("E-mail *", placeholder="joao.silva@mrs.com.br")
            senha  = st.text_input("Senha provisória *", type="password",
                                   help="Mínimo 8 caracteres. O usuário poderá alterar depois.")
            perfil = st.selectbox("Perfil *", options=["usuario", "assistente", "admin"])
            gerencia = st.selectbox(
                "Gerência",
                options=["", "SP", "VP"],
                help="Obrigatório para Assistente. Admin não precisa.",
            )

            submit = st.form_submit_button("✅ Criar Usuário", type="primary")

        if submit:
            erros = []
            if not nome.strip():
                erros.append("Nome é obrigatório.")
            if not email.strip() or "@" not in email:
                erros.append("E-mail inválido.")
            if len(senha) < 8:
                erros.append("Senha deve ter no mínimo 8 caracteres.")
            if perfil == "assistente" and not gerencia:
                erros.append("Assistente deve ter gerência definida.")

            if erros:
                for e in erros:
                    st.error(f"❌ {e}")
            else:
                _criar_usuario(
                    nome=nome.strip(),
                    email=email.strip().lower(),
                    senha=senha,
                    perfil=perfil,
                    gerencia=gerencia or None,
                    criado_por=admin_logado.get("id"),
                )


def _form_editar_usuario(df_users: pd.DataFrame) -> None:
    """Formulário para editar ou ativar/desativar usuário."""
    with st.expander("✏️ Editar / Desativar Usuário", expanded=False):
        if df_users.empty:
            st.caption("_(nenhum usuário disponível)_")
            return

        opcoes = {
            row["id"]: f"{row.get('nome','?')} ({row.get('email','?')})"
            for _, row in df_users.iterrows()
        }

        user_id_sel = st.selectbox(
            "Selecione o usuário",
            options=list(opcoes.keys()),
            format_func=lambda uid: opcoes[uid],
            key="sel_edit_user",
        )

        if user_id_sel:
            row = df_users[df_users["id"] == user_id_sel].iloc[0]

            with st.form("form_editar_user"):
                novo_perfil  = st.selectbox("Perfil", ["usuario", "assistente", "admin"],
                                            index=["usuario","assistente","admin"].index(row.get("perfil","usuario")))
                nova_gerencia = st.selectbox("Gerência", ["", "SP", "VP"],
                                             index=["","SP","VP"].index(row.get("gerencia","") or ""))
                ativo        = st.checkbox("Usuário ativo", value=bool(row.get("ativo", True)))

                submit_edit = st.form_submit_button("💾 Salvar Alterações", type="primary")

            if submit_edit:
                _editar_usuario(
                    user_id=user_id_sel,
                    perfil=novo_perfil,
                    gerencia=nova_gerencia or None,
                    ativo=ativo,
                )

            st.markdown("---")
            st.markdown("**🔑 Resetar Senha**")
            with st.form("form_resetar_senha"):
                nova_senha = st.text_input(
                    "Nova senha provisória", type="password",
                    help="Mínimo 8 caracteres. Repasse ao usuário por um canal seguro.",
                )
                submit_reset = st.form_submit_button("🔑 Resetar Senha")

            if submit_reset:
                if len(nova_senha) < 8:
                    st.error("❌ Senha deve ter no mínimo 8 caracteres.")
                else:
                    admin_logado = st.session_state.get("usuario", {})
                    _resetar_senha(
                        user_id=user_id_sel,
                        email=row.get("email", ""),
                        nova_senha=nova_senha,
                        admin_id=admin_logado.get("id"),
                    )


def _buscar_usuarios() -> pd.DataFrame:
    """Busca todos os usuários no banco."""
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("usuarios")
            .select("id, nome, email, perfil, gerencia, ativo, ultimo_login, criado_em")
            .order("criado_em", desc=True)
            .execute()
        )
        return pd.DataFrame(resp.data or [])
    except Exception as e:
        st.error(f"❌ Erro ao buscar usuários: {e}")
        return pd.DataFrame()


def _criar_usuario(
    nome: str,
    email: str,
    senha: str,
    perfil: str,
    gerencia: str | None,
    criado_por: str | None,
) -> None:
    """
    Cria a conta de login (Supabase Auth) e o perfil (tabela 'usuarios').

    A senha nunca é armazenada pelo app — ela vive só no Supabase Auth
    (ver database/schema.sql). email_confirm=True libera o acesso na hora,
    sem precisar de e-mail de confirmação (a MRS ainda não liberou SMTP).
    """
    try:
        admin = get_supabase_admin()
        admin.auth.admin.create_user({
            "email":         email,
            "password":      senha,
            "email_confirm": True,
        })

        supabase = get_supabase()
        dados = {
            "nome":       nome,
            "email":      email,
            "perfil":     perfil,
            "gerencia":   gerencia,
            "ativo":      True,
            "criado_por": criado_por,
        }
        supabase.table("usuarios").insert(dados).execute()

        # Registra no log de auditoria
        _registrar_log(
            acao="CRIAR_USUARIO",
            detalhes={"email": email, "perfil": perfil, "gerencia": gerencia},
            admin_id=criado_por,
        )

        st.success(f"✅ Usuário **{nome}** criado com sucesso! Já pode logar com a senha provisória.")
        st.rerun()

    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "already been registered" in msg or "already registered" in msg:
            st.error("❌ E-mail já cadastrado na plataforma.")
        else:
            st.error(f"❌ Erro ao criar usuário: {e}")


def _resetar_senha(user_id: str, email: str, nova_senha: str, admin_id: str | None) -> None:
    """
    Reseta a senha de um usuário diretamente via API admin do Supabase —
    não depende de SMTP/e-mail de recuperação.
    """
    try:
        admin = get_supabase_admin()

        # Localiza o usuário no Supabase Auth pelo e-mail (a API admin não
        # busca por e-mail diretamente, então paginamos até encontrar).
        auth_user_id = None
        pagina = 1
        while auth_user_id is None:
            resp = admin.auth.admin.list_users(page=pagina, per_page=200)
            usuarios_pagina = resp.users if hasattr(resp, "users") else resp
            if not usuarios_pagina:
                break
            for u in usuarios_pagina:
                if (u.email or "").strip().lower() == email.strip().lower():
                    auth_user_id = u.id
                    break
            pagina += 1

        if not auth_user_id:
            st.error("❌ Usuário não encontrado no Supabase Auth (conta pode ter sido criada antes da correção — recrie o usuário).")
            return

        admin.auth.admin.update_user_by_id(auth_user_id, {"password": nova_senha})

        _registrar_log(
            acao="RESETAR_SENHA",
            detalhes={"user_id": user_id, "email": email},
            admin_id=admin_id,
        )

        st.success(f"✅ Senha de **{email}** redefinida com sucesso!")

    except Exception as e:
        st.error(f"❌ Erro ao resetar senha: {e}")


def _editar_usuario(
    user_id: str,
    perfil: str,
    gerencia: str | None,
    ativo: bool,
) -> None:
    """Atualiza perfil, gerência e status ativo do usuário."""
    try:
        supabase = get_supabase()
        supabase.table("usuarios").update({
            "perfil":   perfil,
            "gerencia": gerencia,
            "ativo":    ativo,
        }).eq("id", user_id).execute()

        admin = st.session_state.get("usuario", {})
        _registrar_log(
            acao="EDITAR_USUARIO",
            detalhes={"user_id": user_id, "perfil": perfil, "ativo": ativo},
            admin_id=admin.get("id"),
        )

        st.success("✅ Usuário atualizado com sucesso!")
        st.rerun()

    except Exception as e:
        st.error(f"❌ Erro ao editar usuário: {e}")

# endregion


# region ====================== SESSÃO 3: Aba Logs de Acesso ==================

def _render_aba_logs() -> None:
    """
    Exibe os logs de acesso e o histórico de uploads.

    Seções:
      - Logs de ações (tabela paginada)
      - Histórico de uploads (quem subiu o quê)
    """
    st.markdown("### 📋 Auditoria de Acessos e Uploads")

    # ── 3.1: Filtros ──────────────────────────────────────────────────────────
    c_fil1, c_fil2, c_fil3 = st.columns([1, 1, 2])
    with c_fil1:
        acao_filtro = st.selectbox(
            "Filtrar por ação",
            options=["Todas", "LOGIN", "LOGOUT", "UPLOAD", "CRIAR_USUARIO", "EDITAR_USUARIO"],
            key="log_acao_filtro",
        )
    with c_fil2:
        limite = st.selectbox("Registros", options=[50, 100, 200, 500], key="log_limite")

    # ── 3.2: Logs de acesso ────────────────────────────────────────────────────
    st.markdown("#### 🔐 Logs de Acesso")
    df_logs = _buscar_logs(acao_filtro if acao_filtro != "Todas" else None, limite)

    if df_logs.empty:
        st.info("📭 Sem registros de log.")
    else:
        df_display = df_logs[[c for c in [
            "quando", "acao", "detalhes", "ip",
        ] if c in df_logs.columns]].copy()
        df_display.rename(columns={"quando": "Data/Hora", "acao": "Ação", "detalhes": "Detalhes", "ip": "IP"}, inplace=True)
        if "Data/Hora" in df_display.columns:
            df_display["Data/Hora"] = pd.to_datetime(df_display["Data/Hora"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M:%S")

        st.dataframe(df_display, use_container_width=True, hide_index=True, height=300)

        csv_logs = df_display.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Exportar Logs CSV", csv_logs, file_name="logs_acesso_sentinel.csv", mime="text/csv", key="dl_logs")

    st.markdown("---")

    # ── 3.3: Histórico de uploads ──────────────────────────────────────────────
    st.markdown("#### 📤 Histórico de Uploads")
    df_up = _buscar_uploads()

    if df_up.empty:
        st.info("📭 Sem uploads registrados.")
    else:
        col_disp = [c for c in [
            "enviado_em", "gerencia", "disciplina",
            "nome_arquivo", "total_notas", "status",
        ] if c in df_up.columns]
        df_up_disp = df_up[col_disp].copy()
        df_up_disp.rename(columns={
            "enviado_em":  "Data/Hora",
            "gerencia":    "Gerência",
            "disciplina":  "Disciplina",
            "nome_arquivo":"Arquivo",
            "total_notas": "Nº Notas",
            "status":      "Status",
        }, inplace=True)
        if "Data/Hora" in df_up_disp.columns:
            df_up_disp["Data/Hora"] = pd.to_datetime(df_up_disp["Data/Hora"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

        st.dataframe(df_up_disp, use_container_width=True, hide_index=True, height=280)


def _buscar_logs(acao: str | None, limite: int) -> pd.DataFrame:
    try:
        supabase = get_supabase()
        q = (
            supabase.table("logs_acesso")
            .select("quando, acao, detalhes, ip")
            .order("quando", desc=True)
            .limit(limite)
        )
        if acao:
            q = q.eq("acao", acao)
        resp = q.execute()
        return pd.DataFrame(resp.data or [])
    except Exception as e:
        st.error(f"❌ Erro ao buscar logs: {e}")
        return pd.DataFrame()


def _buscar_uploads() -> pd.DataFrame:
    return get_uploads_historico()

# endregion


# region ====================== SESSÃO 4: Aba Configurações ===================

def _render_aba_configuracoes() -> None:
    """
    Configurações da plataforma por gerência.

    Seções:
      A. Extensão da malha (km por gerência) — afeta IMT e DI
      B. Pesos padrão de score (α, DIFE, CT, família) por gerência
      C. Limites de alerta de IMT (crítico, atenção)
    """
    st.markdown("### ⚙️ Configurações da Plataforma")
    st.caption(
        "Alterações são salvas no banco (tabela `configuracoes`) e aplicadas "
        "imediatamente na próxima renderização."
    )

    # ── 4.1: Extensão da malha ────────────────────────────────────────────────
    with st.expander("🗺️ Extensão da Malha (km)", expanded=True):
        c1, c2 = st.columns(2)
        km_sp = c1.number_input("Km — Gerência SP", min_value=1.0, max_value=2000.0,
                                 value=float(_get_config("SP", "km_malha", 320.0)),
                                 step=1.0, key="cfg_km_sp")
        km_vp = c2.number_input("Km — Gerência VP", min_value=1.0, max_value=2000.0,
                                 value=float(_get_config("VP", "km_malha", 410.0)),
                                 step=1.0, key="cfg_km_vp")

        if st.button("💾 Salvar Km de Malha", key="btn_km"):
            _salvar_config("SP", "km_malha", km_sp)
            _salvar_config("VP", "km_malha", km_vp)
            st.success("✅ Km de malha atualizados!")

    # ── 4.2: Limites de alerta IMT ────────────────────────────────────────────
    with st.expander("🚦 Limites de Alerta IMT", expanded=False):
        c3, c4 = st.columns(2)
        imt_atencao  = c3.number_input("IMT — Limite Atenção (🟡)",
                                        min_value=0.1, max_value=20.0,
                                        value=float(_get_config(None, "imt_atencao", 2.5)),
                                        step=0.1, key="cfg_imt_atencao")
        imt_critico  = c4.number_input("IMT — Limite Crítico (🔴)",
                                        min_value=0.1, max_value=50.0,
                                        value=float(_get_config(None, "imt_critico", 5.0)),
                                        step=0.5, key="cfg_imt_critico")

        if imt_critico <= imt_atencao:
            st.warning("⚠️ O limite Crítico deve ser maior que o limite de Atenção.")

        if st.button("💾 Salvar Limites IMT", key="btn_imt"):
            _salvar_config(None, "imt_atencao", imt_atencao)
            _salvar_config(None, "imt_critico", imt_critico)
            st.success("✅ Limites de IMT atualizados!")

    # ── 4.3: Score padrão por gerência ───────────────────────────────────────
    with st.expander("⚖️ Score Padrão — Fator Idade (α)", expanded=False):
        c5, c6 = st.columns(2)
        alpha_sp = c5.slider("α — Gerência SP", 0.0, 0.5,
                              value=float(_get_config("SP", "alpha_idade", 0.10)),
                              step=0.01, format="%.2f", key="cfg_alpha_sp")
        alpha_vp = c6.slider("α — Gerência VP", 0.0, 0.5,
                              value=float(_get_config("VP", "alpha_idade", 0.10)),
                              step=0.01, format="%.2f", key="cfg_alpha_vp")

        if st.button("💾 Salvar α Padrão", key="btn_alpha"):
            _salvar_config("SP", "alpha_idade", alpha_sp)
            _salvar_config("VP", "alpha_idade", alpha_vp)
            st.success("✅ Fator α atualizado!")

    # ── 4.4: Alertas Automáticos (Sprint 5) ──────────────────────────────────
    with st.expander("🚨 Alertas Automáticos", expanded=False):
        st.caption("Parâmetros do motor de detecção e canal de e-mail (previsão).")

        d1, d2, d3 = st.columns(3)
        n_min = d1.number_input(
            "Nº mínimo de notas (crônico)", min_value=2, max_value=20,
            value=int(float(_get_config(None, "alerta_n_min", 3))),
            step=1, key="cfg_alerta_n")
        janela = d2.number_input(
            "Janela de análise (meses)", min_value=1, max_value=24,
            value=int(float(_get_config(None, "alerta_janela_meses", 6))),
            step=1, key="cfg_alerta_janela")
        reincid = d3.number_input(
            "Reincidência (dias)", min_value=15, max_value=365,
            value=int(float(_get_config(None, "alerta_reincidencia_dias", 90))),
            step=5, key="cfg_alerta_reincid")

        if st.button("💾 Salvar Parâmetros de Alerta", key="btn_alerta_param"):
            _salvar_config(None, "alerta_n_min", n_min)
            _salvar_config(None, "alerta_janela_meses", janela)
            _salvar_config(None, "alerta_reincidencia_dias", reincid)
            st.success("✅ Parâmetros de alerta atualizados!")

        st.markdown("---")
        st.markdown("**📧 Notificação por e-mail (previsão)**")

        email_ativo = st.toggle(
            "Ativar envio de e-mail de alertas",
            value=str(_get_config(None, "email_alertas_ativo", False)).lower() in ("true", "1", "sim"),
            key="cfg_email_ativo",
            help="Requer credenciais SMTP em st.secrets['smtp']. Desligado por padrão.")

        dest_raw = _get_config(None, "email_destinatarios", [])
        if isinstance(dest_raw, list):
            dest_txt = ", ".join(dest_raw)
        else:
            dest_txt = str(dest_raw or "")
        dest_input = st.text_input(
            "Destinatários (separados por vírgula)", value=dest_txt,
            placeholder="julio.paz@mrs.com.br, gestor@mrs.com.br",
            key="cfg_email_dest")

        if st.button("💾 Salvar Config de E-mail", key="btn_email_cfg"):
            destinatarios = [e.strip() for e in dest_input.split(",") if e.strip()]
            _salvar_config(None, "email_alertas_ativo", bool(email_ativo))
            _salvar_config(None, "email_destinatarios", destinatarios)
            st.success("✅ Configuração de e-mail salva!")

    # ── 4.5: Informações do sistema ───────────────────────────────────────────
    with st.expander("ℹ️ Informações do Sistema", expanded=False):
        st.markdown(
            """
            | Item | Valor |
            |---|---|
            | **App** | MRS Sentinel |
            | **Stack** | Streamlit + Supabase + ECharts + Plotly |
            | **Versão** | Sprint 4 |
            | **Perfis** | Admin / Assistente / Usuário |
            | **Banco** | Supabase (PostgreSQL) |
            """
        )
        if st.button("🔄 Limpar Cache de Dados", key="btn_cache"):
            st.cache_data.clear()
            st.success("✅ Cache limpo! Próxima navegação buscará dados frescos do banco.")


def _get_config(gerencia: str | None, chave: str, default):
    """
    Busca valor de configuração no banco.
    Retorna default se não encontrado ou em caso de erro.
    """
    try:
        supabase = get_supabase()
        q = supabase.table("configuracoes").select("valor").eq("chave", chave)
        if gerencia:
            q = q.eq("gerencia", gerencia)
        else:
            q = q.is_("gerencia", "null")
        resp = q.limit(1).execute()
        if resp.data:
            return resp.data[0]["valor"]
        return default
    except Exception:
        return default


def _salvar_config(gerencia: str | None, chave: str, valor) -> None:
    """Persiste configuração no banco via upsert."""
    try:
        supabase = get_supabase()
        admin = st.session_state.get("usuario", {})
        dados = {
            "gerencia":        gerencia,
            "chave":           chave,
            "valor":           valor,
            "atualizado_por":  admin.get("id"),
            "atualizado_em":   datetime.utcnow().isoformat(),
        }
        supabase.table("configuracoes").upsert(
            dados, on_conflict="gerencia,chave"
        ).execute()
    except Exception as e:
        st.error(f"❌ Erro ao salvar configuração '{chave}': {e}")

# endregion


# region ====================== SESSÃO 5: Helper de log =======================

def _registrar_log(acao: str, detalhes: dict, admin_id: str | None = None) -> None:
    """
    Registra ação administrativa na tabela logs_acesso.
    Falha silenciosa — log não deve quebrar fluxo principal.
    """
    try:
        supabase = get_supabase()
        supabase.table("logs_acesso").insert({
            "usuario_id": admin_id,
            "acao":       acao,
            "detalhes":   detalhes,
            "quando":     datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass  # log nunca deve quebrar operação principal

# endregion

# region ====================== SESSÃO X: Aba Gestão de Dados ================

def _render_aba_gestao_dados() -> None:
    """Permite apagar notas por gerência/disciplina para reprocessamento."""
    st.markdown("### 🗑️ Gestão de Dados — Reprocessamento")

    st.warning(
        "⚠️ **Atenção**: Esta operação apaga permanentemente as notas do banco. "
        "Use apenas para reprocessar uma planilha com parser corrigido.",
        icon="⚠️",
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        ger_del = st.selectbox("Gerência", ["SP", "VP"], key="del_ger")
    with col2:
        disc_del = st.selectbox("Disciplina", ["VP", "EE", "Todas"], key="del_disc")

    # Preview de quantas notas serão apagadas
    supabase = get_supabase()
    try:
        q = supabase.table("notas").select("id", count="exact").eq("gerencia", ger_del)
        if disc_del != "Todas":
            q = q.eq("disciplina", disc_del)
        res = q.execute()
        total = res.count or 0
    except Exception:
        total = "?"

    st.info(f"📊 Notas que serão apagadas: **{total}**")

    confirmacao = st.text_input(
        'Digite "CONFIRMAR" para habilitar o botão:',
        key="del_confirm_txt",
    )

    if st.button(
        f"🗑️ Apagar notas — {ger_del}/{disc_del}",
        type="primary",
        disabled=(confirmacao.strip().upper() != "CONFIRMAR"),
        key="btn_apagar_notas",
    ):
        try:
            q = supabase.table("notas").delete().eq("gerencia", ger_del)
            if disc_del != "Todas":
                q = q.eq("disciplina", disc_del)
            q.execute()

            # Limpa cache
            from database.queries import invalidar_cache_notas
            invalidar_cache_notas()

            st.success(f"✅ {total} notas de {ger_del}/{disc_del} apagadas com sucesso!")
            st.rerun()
        except Exception as ex:
            st.error(f"❌ Erro ao apagar: {ex}")

    st.markdown("---")
    st.caption("💡 Após apagar, vá para a tela da Gerência e faça um novo upload da planilha.")

    st.markdown("---")
    _render_secao_apagar_rasf()

# endregion


# region ====================== SESSÃO X.1: Apagar RASF =======================

def _render_secao_apagar_rasf() -> None:
    """Permite apagar a base RASF (rasf_ee) por gerência para reprocessamento —
    mesmo padrão da seção de notas acima, mas na tabela dedicada do RASF."""
    st.markdown("#### 🗑️ Apagar base RASF (Eletroeletrônica)")

    st.warning(
        "⚠️ **Atenção**: Esta operação apaga permanentemente as linhas do RASF "
        "no banco (tabela `rasf_ee`). Use apenas para reprocessar um export "
        "com parser corrigido.",
        icon="⚠️",
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        ger_del_rasf = st.selectbox("Gerência", ["SP", "VP", "Ambas"], key="del_ger_rasf")

    supabase = get_supabase()
    ger_filtro = ger_del_rasf if ger_del_rasf != "Ambas" else None

    # Preview de quantas linhas serão apagadas
    try:
        q = supabase.table("rasf_ee").select("id", count="exact")
        if ger_filtro:
            q = q.eq("gerencia", ger_filtro)
        res = q.execute()
        total_rasf = res.count or 0
    except Exception:
        total_rasf = "?"

    st.info(f"📊 Linhas RASF que serão apagadas: **{total_rasf}**")

    confirmacao_rasf = st.text_input(
        'Digite "CONFIRMAR" para habilitar o botão:',
        key="del_confirm_txt_rasf",
    )

    if st.button(
        f"🗑️ Apagar base RASF — {ger_del_rasf}",
        type="primary",
        disabled=(confirmacao_rasf.strip().upper() != "CONFIRMAR"),
        key="btn_apagar_rasf",
    ):
        try:
            q = supabase.table("rasf_ee").delete()
            if ger_filtro:
                q = q.eq("gerencia", ger_filtro)
            else:
                q = q.gt("id", 0)  # id é BIGSERIAL >0 — PostgREST exige um filtro no delete()
            q.execute()

            from database.queries_rasf import invalidar_cache_rasf
            invalidar_cache_rasf()

            st.success(f"✅ {total_rasf} linhas RASF de {ger_del_rasf} apagadas com sucesso!")
            st.rerun()
        except Exception as ex:
            st.error(f"❌ Erro ao apagar RASF: {ex}")

    st.caption("💡 Após apagar, vá para Alimentação de Dados e refaça o upload do export RASF.")

# endregion