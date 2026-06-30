# modules/admin_panel.py — Painel de Administração
# Acessível apenas para perfil 'admin'.
# Sprint 1: Listagem de usuários + criação de novos usuários.
# Sprint 4: CRUD completo + logs de acesso + configurações.

import streamlit as st
import pandas as pd
from datetime import datetime

from auth.permissions import require_admin
from auth.session import get_id
from database.queries import (
    get_todos_usuarios,
    criar_usuario_auth,
    criar_usuario_perfil,
    toggle_usuario_ativo,
    log_acesso,
)


# region ====================== SESSÃO 1: Header ======================

def _render_header():
    st.markdown("""
    <div style="margin-bottom: 0.5rem;">
        <span style="font-size:0.8rem; color:#6b7280; font-weight:500;
                     text-transform:uppercase; letter-spacing:1px;">
            ACESSO RESTRITO — ADMINISTRAÇÃO
        </span>
        <h1 style="font-size:1.9rem; font-weight:700; color:#1e3a5f;
                    margin:4px 0 0 0; line-height:1.2;">
            ⚙️ Painel Administrativo
        </h1>
        <p style="color:#6b7280; font-size:0.92rem; margin:6px 0 0 0;">
            Gerenciamento de usuários, acessos e configurações da plataforma.
        </p>
    </div>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Criação de Usuário ======================

def _render_form_criar_usuario():
    """
    Formulário para criar novo usuário.
    Fluxo:
    1. Cria no Supabase Auth (via service_key) → email confirmado automaticamente
    2. Insere perfil na tabela 'usuarios'
    """
    with st.expander("➕ Criar Novo Usuário", expanded=False):
        st.markdown("""
        <div style="
            background: #eff6ff; border: 1px solid #bfdbfe;
            border-radius: 10px; padding: 12px 16px; margin-bottom: 1rem;
            font-size:0.85rem; color:#1e40af;
        ">
            ℹ️ O usuário receberá acesso imediato com e-mail pré-confirmado.
            Compartilhe a senha gerada via canal seguro (Teams/e-mail corporativo).
        </div>
        """, unsafe_allow_html=True)

        with st.form("form_novo_usuario", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nome  = st.text_input("Nome completo *", placeholder="João Silva")
                email = st.text_input("E-mail corporativo *", placeholder="joao.silva@mrs.com.br")
            with col2:
                perfil = st.selectbox(
                    "Perfil *",
                    ["usuario", "assistente", "admin"],
                    format_func=lambda x: {
                        "usuario":    "👤 Usuário (só visualização)",
                        "assistente": "🔧 Assistente (upload + visualização)",
                        "admin":      "👑 Admin (acesso total)",
                    }[x]
                )
                gerencia = st.selectbox(
                    "Gerência",
                    [None, "SP", "VP"],
                    format_func=lambda x: "🌐 Global (Admin)" if x is None else f"🏭 Gerência {x}",
                    help="Obrigatório para Assistente. Admin fica como Global.",
                )

            senha = st.text_input(
                "Senha inicial *",
                type="password",
                placeholder="Mínimo 8 caracteres",
                help="Deve ter ao menos 8 caracteres. Troque na primeira entrada.",
            )

            criar = st.form_submit_button("✅ Criar Usuário", use_container_width=True)

            if criar:
                # Validações
                erros = []
                if not nome or len(nome.strip()) < 3:
                    erros.append("Nome deve ter ao menos 3 caracteres.")
                if not email or "@" not in email:
                    erros.append("E-mail inválido.")
                if not senha or len(senha) < 8:
                    erros.append("Senha deve ter ao menos 8 caracteres.")
                if perfil == "assistente" and not gerencia:
                    erros.append("Assistente precisa ter uma gerência definida.")

                if erros:
                    for e in erros:
                        st.error(f"⚠️ {e}")
                else:
                    with st.spinner("Criando usuário..."):
                        # Passo 1: criar no Supabase Auth
                        auth_ok = criar_usuario_auth(email.strip().lower(), senha)
                        if auth_ok:
                            # Passo 2: criar perfil na tabela usuarios
                            perfil_ok = criar_usuario_perfil(
                                email=email.strip().lower(),
                                nome=nome.strip(),
                                perfil=perfil,
                                gerencia=gerencia,
                                criado_por_id=get_id(),
                            )
                            if perfil_ok:
                                log_acesso(get_id(), "criar_usuario", {"email": email, "perfil": perfil})
                                st.success(f"✅ Usuário **{nome}** criado com sucesso!")
                                st.rerun()
                            else:
                                st.error("❌ Usuário criado no Auth mas falhou ao salvar perfil. Verifique o Supabase.")
                        # Erro do Auth já é exibido dentro de criar_usuario_auth()

# endregion


# region ====================== SESSÃO 3: Tabela de Usuários ======================

def _render_tabela_usuarios():
    """Lista todos os usuários com opções de ativar/desativar."""
    st.markdown("""
    <p style='font-size:0.8rem; color:#9ca3af; text-transform:uppercase;
               letter-spacing:1px; font-weight:600; margin: 1.5rem 0 0.8rem 0;'>
        Usuários Cadastrados
    </p>
    """, unsafe_allow_html=True)

    df = get_todos_usuarios()

    if df.empty:
        st.info("Nenhum usuário cadastrado ainda. Crie o primeiro acima.", icon="👥")
        return

    # Formata colunas para exibição
    df_display = df.copy()

    # Ícone de perfil
    perfil_icon = {"admin": "👑 Admin", "assistente": "🔧 Assistente", "usuario": "👤 Usuário"}
    df_display["Perfil"] = df_display["perfil"].map(lambda x: perfil_icon.get(x, x))

    # Gerência
    df_display["Gerência"] = df_display["gerencia"].fillna("Global").map(
        lambda x: f"🏭 {x}" if x in ("SP", "VP") else "🌐 Global"
    )

    # Status
    df_display["Status"] = df_display["ativo"].map(lambda x: "🟢 Ativo" if x else "🔴 Inativo")

    # Último login
    def fmt_login(val):
        if pd.isna(val) or not val:
            return "Nunca"
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return "—"

    df_display["Último Login"] = df_display.get("ultimo_login", pd.Series()).apply(fmt_login)

    # Criado em
    def fmt_data(val):
        if pd.isna(val) or not val:
            return "—"
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return "—"

    df_display["Criado em"] = df_display["criado_em"].apply(fmt_data)

    # Colunas a exibir
    cols_show = ["nome", "email", "Perfil", "Gerência", "Status", "Último Login", "Criado em"]
    cols_show = [c for c in cols_show if c in df_display.columns]

    st.dataframe(
        df_display[cols_show].rename(columns={"nome": "Nome", "email": "E-mail"}),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Nome":        st.column_config.TextColumn(width="medium"),
            "E-mail":      st.column_config.TextColumn(width="large"),
            "Perfil":      st.column_config.TextColumn(width="medium"),
            "Gerência":    st.column_config.TextColumn(width="small"),
            "Status":      st.column_config.TextColumn(width="small"),
            "Último Login":st.column_config.TextColumn(width="medium"),
            "Criado em":   st.column_config.TextColumn(width="small"),
        }
    )

    # Ativar / Desativar usuário
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    with st.expander("🔧 Ativar / Desativar Usuário"):
        emails_disponiveis = df["email"].tolist()
        email_sel = st.selectbox("Selecione o usuário", emails_disponiveis)

        if email_sel:
            usuario_sel = df[df["email"] == email_sel].iloc[0]
            ativo_atual = usuario_sel.get("ativo", True)
            uid_sel     = usuario_sel.get("id", "")

            st.markdown(
                f"**Status atual:** {'🟢 Ativo' if ativo_atual else '🔴 Inativo'} &nbsp;|&nbsp; "
                f"**Perfil:** {usuario_sel.get('perfil', '?')}"
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Ativar", disabled=ativo_atual, use_container_width=True):
                    if toggle_usuario_ativo(uid_sel, True):
                        log_acesso(get_id(), "ativar_usuario", {"email": email_sel})
                        st.success(f"Usuário {email_sel} ativado.")
                        st.rerun()
            with col2:
                if st.button("🔴 Desativar", disabled=not ativo_atual, use_container_width=True):
                    if toggle_usuario_ativo(uid_sel, False):
                        log_acesso(get_id(), "desativar_usuario", {"email": email_sel})
                        st.warning(f"Usuário {email_sel} desativado.")
                        st.rerun()

# endregion


# region ====================== SESSÃO 4: Métricas de Resumo ======================

def _render_metricas():
    """Cards com totais de usuários por perfil."""
    df = get_todos_usuarios()

    if df.empty:
        return

    total   = len(df)
    ativos  = df["ativo"].sum() if "ativo" in df.columns else 0
    admins  = (df["perfil"] == "admin").sum() if "perfil" in df.columns else 0
    assists = (df["perfil"] == "assistente").sum() if "perfil" in df.columns else 0

    cols = st.columns(4)
    metricas = [
        ("👥", "Total de Usuários", total,   "#1e3a5f"),
        ("🟢", "Usuários Ativos",   ativos,  "#16a34a"),
        ("👑", "Administradores",   admins,  "#f59e0b"),
        ("🔧", "Assistentes",       assists, "#0891b2"),
    ]
    for i, (ico, titulo, valor, cor) in enumerate(metricas):
        with cols[i]:
            st.markdown(f"""
            <div style="background:white; border:1px solid #e5e7eb; border-top:3px solid {cor};
                         border-radius:12px; padding:16px; text-align:center;
                         box-shadow:0 2px 8px rgba(0,0,0,0.04);">
                <div style="font-size:1.5rem;">{ico}</div>
                <div style="font-size:0.75rem; color:#6b7280; text-transform:uppercase;
                             letter-spacing:0.5px; margin:4px 0;">{titulo}</div>
                <div style="font-size:1.8rem; font-weight:700; color:{cor};">{valor}</div>
            </div>
            """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 5: Renderização Principal ======================

def render_admin_panel():
    """Ponto de entrada: renderiza o painel administrativo."""
    require_admin()  # Guard — para tudo se não for admin

    _render_header()
    st.divider()

    # Métricas resumo
    _render_metricas()

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

    # Tabs: Usuários | Uploads | Logs
    tab_usuarios, tab_uploads, tab_logs = st.tabs([
        "👥 Usuários",
        "📤 Histórico de Uploads",
        "📋 Logs de Acesso",
    ])

    with tab_usuarios:
        _render_form_criar_usuario()
        _render_tabela_usuarios()

    with tab_uploads:
        st.info(
            "📤 Histórico de uploads será preenchido automaticamente a partir da **Sprint 2**, "
            "quando o módulo de upload for ativado.",
            icon="⏳"
        )

    with tab_logs:
        st.info(
            "📋 Logs de acesso serão listados aqui a partir da **Sprint 4** "
            "(os logs já estão sendo registrados no banco desde agora).",
            icon="⏳"
        )

# endregion
