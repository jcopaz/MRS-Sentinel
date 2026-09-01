# modules/admin_panel.py
# Painel Administrativo — CRUD de Usuários + Logs de Acesso + Configurações
# Sprint 4 — Visão Geral + Admin
#
# Acesso: apenas perfil 'admin'
#
# Abas:
#   1. 👥 Usuários    — CRUD completo (criar, editar, ativar/desativar)
#   2. 📋 Logs        — Histórico de acessos e uploads
#   3. ⚙️ Configurações — Score (pesos e multiplicadores, config única —
#      migrou do sidebar de cada Gerência em 2026-09-01), km de malha

from datetime import datetime

import streamlit as st
import pandas as pd

from database.client  import get_supabase, get_supabase_admin
from database.queries import (
    get_uploads_historico, gerar_email_sintetico, get_notas_cached,
    get_config as _get_config, salvar_config as _salvar_config_shared,
)
from core.glossarios   import LISTA_GERENCIAS
from core.versao       import APP_VERSION
from core.score_engine import (
    carregar_score_config, MULT_FAMILIA_VP_PADRAO, MULT_FAMILIA_EE_PADRAO,
    ALPHA_PADRAO, BETA_REINCIDENCIA_PADRAO,
    CHAVE_PESO_PRIORIDADE, CHAVE_USAR_IDADE, CHAVE_ALPHA,
    CHAVE_USAR_REINCIDENCIA, CHAVE_BETA_REINCIDENCIA,
    CHAVE_USAR_FAMILIA, CHAVE_MULT_FAMILIA_VP, CHAVE_MULT_FAMILIA_EE,
    CHAVE_USAR_TIPO, CHAVE_MULT_TIPO,
    CHAVE_USAR_TIPO_INSPECAO, CHAVE_MULT_TIPO_INSPECAO,
)

# Senha provisória padrão — mesma pra toda conta nova E pra todo reset
# (pedido do Julio, 2026-08-31). Fonte única: usada tanto no formulário de
# criação quanto no botão de resetar senha, pra nunca dessincronizar.
# Não há hoje nenhuma obrigatoriedade de troca no primeiro acesso (sem
# SMTP confiável pra reset autoatendido — ver auth/recuperar_senha.py) —
# quem não trocar manualmente fica com essa senha indefinidamente.
SENHA_PADRAO = "Sentinel@123"

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
            "nome", "matricula", "email", "email_gerado", "perfil", "gerencia", "ativo",
            "ultimo_login", "criado_em",
        ] if c in df_users.columns]].copy()

        # E-mail sintético (login por matrícula) não é um e-mail real — não exibir
        if "email_gerado" in df_display.columns:
            df_display.loc[df_display["email_gerado"].fillna(False), "email"] = "— (login por matrícula)"
            df_display.drop(columns=["email_gerado"], inplace=True)

        df_display.rename(columns={
            "nome":         "Nome",
            "matricula":    "Matrícula",
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
            nome      = st.text_input("Nome completo *", placeholder="Ex: João da Silva")
            matricula = st.text_input(
                "Matrícula *", placeholder="Ex: 123456",
                help="Identificador de login. Não depende de e-mail corporativo.",
            )
            email  = st.text_input(
                "E-mail corporativo (opcional)", placeholder="joao.silva@mrs.com.br",
                help="Deixe em branco se o colaborador não tiver e-mail — o login "
                     "será feito só pela matrícula (não há SMTP para recuperação por e-mail).",
            )
            senha  = st.text_input(
                "Senha provisória *", value=SENHA_PADRAO, type="password",
                help="Mínimo 8 caracteres. Padrão pré-preenchido — troque aqui se "
                     "quiser outra. Como não há reset por e-mail, quem não trocar "
                     "fica com essa senha até você resetar manualmente no painel "
                     "(seção Editar Usuário).",
            )
            perfil = st.selectbox("Perfil *", options=["usuario", "assistente", "admin"])
            gerencia = st.selectbox(
                "Gerência",
                options=[""] + LISTA_GERENCIAS,
                help="Obrigatório para Assistente. Admin não precisa.",
            )
            acesso_tv = st.checkbox(
                "📺 Acesso ao Modo TV",
                value=False,
                help="Deixa esse usuário abrir o Modo TV (painel em loop pra "
                     "TV/monitor de uma coordenação) mesmo sem ser admin — "
                     "pensado pra uma conta dedicada de kiosk. Admin sempre "
                     "tem acesso, com ou sem essa marcação.",
            )

            submit = st.form_submit_button("✅ Criar Usuário", type="primary")

        if submit:
            erros = []
            if not nome.strip():
                erros.append("Nome é obrigatório.")
            if not matricula.strip():
                erros.append("Matrícula é obrigatória.")
            if email.strip() and "@" not in email:
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
                    matricula=matricula.strip(),
                    email=(email.strip().lower() or None),
                    senha=senha,
                    perfil=perfil,
                    gerencia=gerencia or None,
                    acesso_tv=acesso_tv,
                    criado_por=admin_logado.get("id"),
                )


def _form_editar_usuario(df_users: pd.DataFrame) -> None:
    """Formulário para editar ou ativar/desativar usuário."""
    with st.expander("✏️ Editar / Desativar Usuário", expanded=False):
        if df_users.empty:
            st.caption("_(nenhum usuário disponível)_")
            return

        opcoes = {
            row["id"]: f"{row.get('nome','?')} ({row.get('matricula') or row.get('email','?')})"
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
                nova_matricula = st.text_input("Matrícula", value=row.get("matricula") or "")
                novo_perfil  = st.selectbox("Perfil", ["usuario", "assistente", "admin"],
                                            index=["usuario","assistente","admin"].index(row.get("perfil","usuario")))
                opcoes_gerencia = [""] + LISTA_GERENCIAS
                nova_gerencia = st.selectbox("Gerência", opcoes_gerencia,
                                             index=opcoes_gerencia.index(row.get("gerencia","") or ""))
                novo_acesso_tv = st.checkbox(
                    "📺 Acesso ao Modo TV", value=bool(row.get("acesso_tv", False)),
                    help="Deixa esse usuário abrir o Modo TV mesmo sem ser "
                         "admin. Admin sempre tem acesso, com ou sem essa marcação.",
                )
                ativo        = st.checkbox("Usuário ativo", value=bool(row.get("ativo", True)))

                submit_edit = st.form_submit_button("💾 Salvar Alterações", type="primary")

            if submit_edit:
                _editar_usuario(
                    user_id=user_id_sel,
                    matricula=(nova_matricula.strip() or None),
                    perfil=novo_perfil,
                    gerencia=nova_gerencia or None,
                    acesso_tv=novo_acesso_tv,
                    ativo=ativo,
                )

            st.markdown("---")
            st.markdown("**🔑 Resetar Senha**")
            st.caption(
                f"Volta a senha para a padrão (`{SENHA_PADRAO}`). Repasse ao "
                "usuário por um canal seguro — não há e-mail automático de "
                "recuperação, este é o único jeito de resetar."
            )
            if st.button("🔑 Resetar para a senha padrão", key=f"btn_resetar_senha_{user_id_sel}"):
                admin_logado = st.session_state.get("usuario", {})
                _resetar_senha(
                    user_id=user_id_sel,
                    email=row.get("email", ""),
                    auth_user_id=row.get("auth_user_id"),
                    nova_senha=SENHA_PADRAO,
                    admin_id=admin_logado.get("id"),
                )

            st.markdown("---")
            st.markdown("**🗑️ Excluir Definitivamente**")
            admin_logado = st.session_state.get("usuario", {})
            if user_id_sel == admin_logado.get("id"):
                st.caption("Você não pode excluir a própria conta logada.")
            else:
                st.warning(
                    "⚠️ Apaga o usuário do banco de dados e do login (Supabase Auth) "
                    "**para sempre** — diferente de desativar, não dá pra desfazer. Só "
                    "funciona se esse usuário nunca fez upload nem tem log de acesso "
                    "vinculado (senão a exclusão é bloqueada pra não perder histórico "
                    "— desative em vez de excluir nesse caso).",
                    icon="⚠️",
                )
                confirma_exclusao = st.text_input(
                    'Digite "EXCLUIR" para habilitar o botão:',
                    key=f"confirma_exclusao_{user_id_sel}",
                )
                if st.button(
                    "🗑️ Excluir usuário definitivamente",
                    type="primary",
                    disabled=(confirma_exclusao.strip().upper() != "EXCLUIR"),
                    key=f"btn_excluir_usuario_{user_id_sel}",
                ):
                    _excluir_usuario_definitivo(
                        user_id=user_id_sel,
                        email=row.get("email", ""),
                        auth_user_id=row.get("auth_user_id"),
                        admin_id=admin_logado.get("id"),
                    )


def _buscar_usuarios() -> pd.DataFrame:
    """Busca todos os usuários no banco."""
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("usuarios")
            .select("id, nome, matricula, email, email_gerado, auth_user_id, perfil, gerencia, acesso_tv, ativo, ultimo_login, criado_em")
            .order("criado_em", desc=True)
            .execute()
        )
        return pd.DataFrame(resp.data or [])
    except Exception as e:
        st.error(f"❌ Erro ao buscar usuários: {e}")
        return pd.DataFrame()


def _criar_usuario(
    nome: str,
    matricula: str,
    email: str | None,
    senha: str,
    perfil: str,
    gerencia: str | None,
    criado_por: str | None,
    acesso_tv: bool = False,
) -> None:
    """
    Cria a conta de login (Supabase Auth) e o perfil (tabela 'usuarios').

    Login por matrícula: quando o colaborador não tem e-mail corporativo,
    geramos um e-mail sintético (nunca enviado) só pra satisfazer o
    Supabase Auth por baixo dos panos — quem loga digita a matrícula
    (ver auth/login.py). auth_user_id é salvo direto na criação pra não
    depender de busca paginada por e-mail no reset de senha.

    A senha nunca é armazenada pelo app — ela vive só no Supabase Auth
    (ver database/schema.sql). email_confirm=True libera o acesso na hora,
    sem precisar de e-mail de confirmação (a MRS não tem SMTP disponível).
    """
    email_gerado = not email
    email_final = email or gerar_email_sintetico(matricula)

    try:
        admin = get_supabase_admin()
        resp_auth = admin.auth.admin.create_user({
            "email":         email_final,
            "password":      senha,
            "email_confirm": True,
        })
        auth_user_id = resp_auth.user.id if resp_auth and resp_auth.user else None

        supabase = get_supabase()
        dados = {
            "nome":         nome,
            "matricula":    matricula,
            "email":        email_final,
            "email_gerado": email_gerado,
            "auth_user_id": auth_user_id,
            "perfil":       perfil,
            "gerencia":     gerencia,
            "acesso_tv":    acesso_tv,
            "ativo":        True,
            "criado_por":   criado_por,
        }
        supabase.table("usuarios").insert(dados).execute()

        # Registra no log de auditoria
        _registrar_log(
            acao="CRIAR_USUARIO",
            detalhes={"matricula": matricula, "email_gerado": email_gerado, "perfil": perfil, "gerencia": gerencia},
            admin_id=criado_por,
        )

        st.success(
            f"✅ Usuário **{nome}** criado com sucesso! Login pela matrícula "
            f"**{matricula}**" + ("" if email_gerado else f" ou e-mail **{email_final}**") +
            ", com a senha provisória."
        )
        st.rerun()

    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg or "already been registered" in msg or "already registered" in msg:
            if "matricula" in msg:
                st.error("❌ Matrícula já cadastrada na plataforma.")
            else:
                st.error("❌ E-mail já cadastrado na plataforma.")
        else:
            st.error(f"❌ Erro ao criar usuário: {e}")


def _resetar_senha(
    user_id: str,
    email: str,
    nova_senha: str,
    admin_id: str | None,
    auth_user_id: str | None = None,
) -> None:
    """
    Reseta a senha de um usuário diretamente via API admin do Supabase —
    não depende de SMTP/e-mail de recuperação.

    Usa o auth_user_id salvo na criação da conta quando disponível
    (rápido e direto). Contas criadas antes desse campo existir caem no
    fallback: busca paginada por e-mail no Supabase Auth.
    """
    try:
        admin = get_supabase_admin()

        if not auth_user_id:
            from database.queries import buscar_auth_user_id_por_email
            auth_user_id = buscar_auth_user_id_por_email(email)

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
    matricula: str | None,
    perfil: str,
    gerencia: str | None,
    ativo: bool,
    acesso_tv: bool = False,
) -> None:
    """Atualiza matrícula, perfil, gerência, acesso ao Modo TV e status
    ativo do usuário.

    Só atualiza a tabela 'usuarios' — o e-mail de login no Supabase Auth
    (real ou sintético) não muda aqui, então login por matrícula continua
    funcionando via get_usuario_by_matricula (auth/login.py).
    """
    try:
        supabase = get_supabase()
        supabase.table("usuarios").update({
            "matricula":  matricula,
            "perfil":     perfil,
            "gerencia":   gerencia,
            "acesso_tv":  acesso_tv,
            "ativo":      ativo,
        }).eq("id", user_id).execute()

        admin = st.session_state.get("usuario", {})
        _registrar_log(
            acao="EDITAR_USUARIO",
            detalhes={"user_id": user_id, "matricula": matricula, "perfil": perfil, "ativo": ativo},
            admin_id=admin.get("id"),
        )

        st.success("✅ Usuário atualizado com sucesso!")
        st.rerun()

    except Exception as e:
        st.error(f"❌ Erro ao editar usuário: {e}")


def _excluir_usuario_definitivo(
    user_id: str,
    email: str,
    auth_user_id: str | None,
    admin_id: str | None,
) -> None:
    """
    Apaga o usuário de vez — da tabela 'usuarios' E do Supabase Auth.
    Diferente de _editar_usuario(ativo=False), que é reversível.

    Se o usuário já tiver upload/log vinculado, o DELETE em 'usuarios'
    falha por causa da FK (uploads_historico.usuario_id é NOT NULL,
    não aceita 'órfão') — nesse caso mostra um erro claro em vez do erro
    cru do Postgres, orientando a desativar em vez de excluir.
    """
    try:
        supabase = get_supabase()
        supabase.table("usuarios").delete().eq("id", user_id).execute()
    except Exception as e:
        msg = str(e).lower()
        if "foreign key" in msg or "violates" in msg or "23503" in msg:
            st.error(
                "❌ Esse usuário já tem upload ou log de acesso vinculado — "
                "excluir apagaria esse histórico. Desative a conta em vez de "
                "excluir (seção acima)."
            )
        else:
            st.error(f"❌ Erro ao excluir usuário: {e}")
        return

    # Usuário apagado com sucesso da tabela — agora tenta apagar do Auth
    # também (best-effort: se falhar aqui, o login já não funciona mesmo,
    # porque get_usuario_by_email/matricula não vai mais achar a linha).
    try:
        admin = get_supabase_admin()
        alvo_id = auth_user_id
        if not alvo_id and email:
            from database.queries import buscar_auth_user_id_por_email
            alvo_id = buscar_auth_user_id_por_email(email)
        if alvo_id:
            admin.auth.admin.delete_user(alvo_id)
    except Exception:
        pass

    _registrar_log(
        acao="EXCLUIR_USUARIO",
        detalhes={"user_id": user_id, "email": email},
        admin_id=admin_id,
    )

    st.success("✅ Usuário excluído definitivamente.")
    st.rerun()

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

@st.cache_data(ttl=300, show_spinner=False)
def _catalogo_tipos_inspecao() -> list[str]:
    """
    Valores reais de 'Tipo de inspeção' (coluna tipo_atividade) já
    carregados no banco — mesmo catálogo dinâmico do filtro homônimo em
    components/filtros.py::_opcoes_tipos_inspecao, só que combinando SP+VP
    de uma vez (o filtro olha só a gerência da tela atual; aqui é pro
    admin ponderar globalmente). Reaproveita get_notas_cached (mesmo TTL
    de 5min já usado nas telas de Gerência) — não abre uma query nova.
    Defensivo: erro ou base vazia -> lista vazia, nunca quebra a aba.
    """
    valores: set[str] = set()
    for ger in ("SP", "VP"):
        try:
            df = get_notas_cached(ger, None)
            if not df.empty and "tipo_atividade" in df.columns:
                valores |= set(df["tipo_atividade"].dropna().unique().tolist())
        except Exception:
            continue
    return sorted(v for v in valores if v)


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
        km_por_gerencia = {}
        cols_km = st.columns(len(LISTA_GERENCIAS))
        for col, ger in zip(cols_km, LISTA_GERENCIAS):
            km_por_gerencia[ger] = col.number_input(
                f"Km — Gerência {ger}", min_value=1.0, max_value=2000.0,
                value=float(_get_config(ger, "km_malha", 200.0)),
                step=1.0, key=f"cfg_km_{ger.lower()}",
            )

        if st.button("💾 Salvar Km de Malha", key="btn_km"):
            for ger, valor in km_por_gerencia.items():
                _salvar_config(ger, "km_malha", valor)
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

    # ── 4.2b: Metas dos Indicadores (IMT / DI / Aderência) ────────────────────
    with st.expander("🎯 Metas dos Indicadores (IMT / DI / Aderência)", expanded=False):
        st.caption(
            "Não há fórmula oficial da MRS para as notas — os limites do semáforo "
            "🟢🟡🔴 do painel Consolidado são configuráveis aqui.\n\n"
            "**IMT** = encerradas ÷ total × 100 · **DI** = encerradas no prazo "
            "(`data_enc ≤ data_planejada`) ÷ encerradas × 100 · **Aderência** = "
            "abertas com data planejada ÷ abertas × 100. Meta = quanto **maior**, melhor."
        )

        def _meta_row(rot: str, k_at: str, d_at: float, k_cr: str, d_cr: float):
            a, b = st.columns(2)
            atencao = a.number_input(
                f"{rot} — Meta / Atenção (🟢≥ · 🟡<)", min_value=0.0, max_value=100.0,
                value=float(_get_config(None, k_at, d_at)), step=1.0, key=f"cfg_{k_at}")
            critico = b.number_input(
                f"{rot} — Crítico (🔴<)", min_value=0.0, max_value=100.0,
                value=float(_get_config(None, k_cr, d_cr)), step=1.0, key=f"cfg_{k_cr}")
            if critico >= atencao:
                st.warning(f"⚠️ {rot}: o limite Crítico deve ser MENOR que o de Atenção.")
            return atencao, critico

        imt_at, imt_cr = _meta_row("IMT", "meta_imt_atencao", 85.0, "meta_imt_critico", 70.0)
        di_at,  di_cr  = _meta_row("DI",  "meta_di_atencao",  80.0, "meta_di_critico",  60.0)
        adh_at, adh_cr = _meta_row("Aderência", "meta_adh_atencao", 85.0, "meta_adh_critico", 70.0)

        if st.button("💾 Salvar Metas dos Indicadores", key="btn_metas_ind"):
            _salvar_config(None, "meta_imt_atencao", imt_at)
            _salvar_config(None, "meta_imt_critico", imt_cr)
            _salvar_config(None, "meta_di_atencao",  di_at)
            _salvar_config(None, "meta_di_critico",  di_cr)
            _salvar_config(None, "meta_adh_atencao", adh_at)
            _salvar_config(None, "meta_adh_critico", adh_cr)
            st.success("✅ Metas dos indicadores atualizadas! Aplicadas na próxima renderização.")

    # ── 4.3: Score — Pesos e Multiplicadores ─────────────────────────────────
    # Migrou do expander "⚙️ Score" que existia na sidebar de cada tela de
    # Gerência (SP/VP/Geral) — pedido do Julio, 2026-09-01: "o item Score -
    # Geral deverá entrar na aba administração e sair do sidebar". Config
    # ÚNICA agora (não mais 3 versões independentes que nem eram salvas —
    # ver decisão registrada no cabeçalho de core/score_engine.py). Toda
    # dimensão que multiplica o score (família, tipo, tipo de inspeção) usa
    # o mesmo padrão: multiselect pra ESCOLHER quais itens entram + peso
    # numérico por item escolhido — pedido explícito do Julio ("todas as
    # opções que forem multiplicadores do score... deverá ser possível
    # selecionar e ponderar o peso por item selecionado").
    with st.expander("🎯 Score — Pesos e Multiplicadores", expanded=False):
        st.caption(
            "Config única, vale para SP + VP + Geral (inclusive Modo TV). "
            "Fórmula: Peso Prioridade × Família × Tipo × Tipo de Inspeção × "
            "(1 + α · anos em aberto) × (1 + β · reincidências no local)."
        )

        cfg_atual = carregar_score_config()

        # -- Peso de Prioridade (pedido do Julio: junto do score aqui) ------
        st.markdown("**🎯 Peso de Prioridade**")
        pcol1, pcol2 = st.columns(2)
        with pcol1:
            p1 = st.number_input(
                "Muito Alta", min_value=1, max_value=10,
                value=int(cfg_atual.peso_prioridade.get("1-Muito alta", 4)),
                step=1, key="cfg_score_p1",
            )
            p3 = st.number_input(
                "Média", min_value=1, max_value=10,
                value=int(cfg_atual.peso_prioridade.get("3-Média", 2)),
                step=1, key="cfg_score_p3",
            )
        with pcol2:
            p2 = st.number_input(
                "Alta", min_value=1, max_value=10,
                value=int(cfg_atual.peso_prioridade.get("2-Alta", 3)),
                step=1, key="cfg_score_p2",
            )
            p4 = st.number_input(
                "Baixa", min_value=1, max_value=10,
                value=int(cfg_atual.peso_prioridade.get("4-Baixa", 1)),
                step=1, key="cfg_score_p4",
            )

        st.markdown("---")

        # -- Envelhecimento (idade) ------------------------------------------
        usar_idade = st.checkbox(
            "📅 Penalizar notas antigas", value=cfg_atual.usar_idade,
            key="cfg_score_usar_idade",
            help="Acrescenta peso para notas abertas há mais tempo.",
        )
        alpha = ALPHA_PADRAO
        if usar_idade:
            alpha = st.slider(
                "α — Acréscimo por ano em aberto", 0.0, 0.5,
                value=float(cfg_atual.alpha), step=0.01, format="%.2f",
                key="cfg_score_alpha",
                help="0.10 = +10% por ano. Nota com 2 anos → ×1.20",
            )

        st.markdown("---")

        # -- Reincidência no local --------------------------------------------
        usar_reinc = st.checkbox(
            "🔁 Penalizar reincidência no mesmo local", value=cfg_atual.usar_reincidencia,
            key="cfg_score_usar_reinc",
            help="Mesmo ramal+pátio+família com múltiplas notas pesa mais — "
                 "mesma lógica dos hot-spots crônicos (aba Alertas).",
        )
        beta = BETA_REINCIDENCIA_PADRAO
        if usar_reinc:
            beta = st.slider(
                "β — Acréscimo por ocorrência repetida", 0.0, 0.5,
                value=float(cfg_atual.beta_reincidencia), step=0.01, format="%.2f",
                key="cfg_score_beta",
                help="0.15 = +15% por repetição. 4ª nota no mesmo local → ×1.45",
            )

        st.markdown("---")

        # -- Família de defeito (selecionável + peso por item) ---------------
        usar_familia = st.checkbox(
            "🔩 Multiplicar por família de defeito", value=cfg_atual.usar_familia,
            key="cfg_score_usar_familia",
        )
        mult_fam_vp = dict(cfg_atual.mult_familia_vp)
        mult_fam_ee = dict(cfg_atual.mult_familia_ee)
        if usar_familia:
            st.caption(
                "Escolha quais famílias entram no score e o peso de cada uma "
                "(ex.: AMV, Dormente, Geometria...). As não escolhidas ficam "
                "neutras (×1.0) — não somem do app, só não pesam no score."
            )
            fcol1, fcol2 = st.columns(2)
            with fcol1:
                st.markdown("_Via Permanente (VP)_")
                fam_vp_sel = st.multiselect(
                    "Famílias VP", options=list(MULT_FAMILIA_VP_PADRAO.keys()),
                    default=[f for f in cfg_atual.mult_familia_vp if f in MULT_FAMILIA_VP_PADRAO],
                    key="cfg_score_fam_vp_sel", label_visibility="collapsed",
                )
                mult_fam_vp = {}
                for fam in fam_vp_sel:
                    mult_fam_vp[fam] = st.number_input(
                        fam, min_value=0.0, max_value=5.0,
                        value=float(cfg_atual.mult_familia_vp.get(fam, MULT_FAMILIA_VP_PADRAO.get(fam, 1.0))),
                        step=0.1, key=f"cfg_score_fam_vp_{fam}",
                    )
            with fcol2:
                st.markdown("_Eletroeletrônica (EE)_")
                fam_ee_sel = st.multiselect(
                    "Famílias EE", options=list(MULT_FAMILIA_EE_PADRAO.keys()),
                    default=[f for f in cfg_atual.mult_familia_ee if f in MULT_FAMILIA_EE_PADRAO],
                    key="cfg_score_fam_ee_sel", label_visibility="collapsed",
                )
                mult_fam_ee = {}
                for fam in fam_ee_sel:
                    mult_fam_ee[fam] = st.number_input(
                        fam, min_value=0.0, max_value=5.0,
                        value=float(cfg_atual.mult_familia_ee.get(fam, MULT_FAMILIA_EE_PADRAO.get(fam, 1.0))),
                        step=0.1, key=f"cfg_score_fam_ee_{fam}",
                    )

        st.markdown("---")

        # -- Tipo de nota (CT/PV) ---------------------------------------------
        usar_tipo = st.checkbox(
            "📋 Multiplicar por tipo (CT/PV)", value=cfg_atual.usar_tipo,
            key="cfg_score_usar_tipo",
            help="CT = Corretiva · PV = Preventiva",
        )
        mult_tipo = dict(cfg_atual.mult_tipo)
        if usar_tipo:
            tcol1, tcol2 = st.columns(2)
            mult_tipo = {
                "CT": tcol1.number_input(
                    "CT — Corretiva", min_value=0.0, max_value=5.0,
                    value=float(cfg_atual.mult_tipo.get("CT", 1.5)),
                    step=0.1, key="cfg_score_tipo_ct",
                ),
                "PV": tcol2.number_input(
                    "PV — Preventiva", min_value=0.0, max_value=5.0,
                    value=float(cfg_atual.mult_tipo.get("PV", 1.0)),
                    step=0.1, key="cfg_score_tipo_pv",
                ),
            }

        st.markdown("---")

        # -- Tipo de Inspeção (dimensão nova, selecionável + peso) ------------
        usar_tipo_insp = st.checkbox(
            "🔍 Multiplicar por tipo de inspeção", value=cfg_atual.usar_tipo_inspecao,
            key="cfg_score_usar_tipo_insp",
            help="Origem da nota: Ronda, Drone, Trackstar, Inspeção técnica "
                 "de AMV, etc. — dimensão nova, desligada até você escolher pesos.",
        )
        mult_tipo_insp = dict(cfg_atual.mult_tipo_inspecao)
        if usar_tipo_insp:
            opcoes_insp = _catalogo_tipos_inspecao()
            # Une com o que já está salvo — um peso configurado antes continua
            # selecionável mesmo se a amostra atual de dados não tiver esse valor.
            universo_insp = sorted(set(opcoes_insp) | set(cfg_atual.mult_tipo_inspecao.keys()))
            if not universo_insp:
                st.caption(
                    "_(Nenhum dado carregado ainda pra listar tipos de inspeção "
                    "reais — faça upload em alguma Gerência primeiro.)_"
                )
            else:
                tipo_insp_sel = st.multiselect(
                    "Tipos de inspeção a ponderar", options=universo_insp,
                    default=list(cfg_atual.mult_tipo_inspecao.keys()),
                    key="cfg_score_tipo_insp_sel",
                )
                mult_tipo_insp = {}
                for t in tipo_insp_sel:
                    mult_tipo_insp[t] = st.number_input(
                        t, min_value=0.0, max_value=5.0,
                        value=float(cfg_atual.mult_tipo_inspecao.get(t, 1.0)),
                        step=0.1, key=f"cfg_score_tipo_insp_{t}",
                    )

        st.markdown("---")

        if st.button("💾 Salvar Configuração de Score", key="btn_score_cfg", type="primary"):
            _salvar_config(None, CHAVE_PESO_PRIORIDADE, {
                "1-Muito alta": p1, "2-Alta": p2, "3-Média": p3, "4-Baixa": p4,
            })
            _salvar_config(None, CHAVE_USAR_IDADE, usar_idade)
            _salvar_config(None, CHAVE_ALPHA, alpha)
            _salvar_config(None, CHAVE_USAR_REINCIDENCIA, usar_reinc)
            _salvar_config(None, CHAVE_BETA_REINCIDENCIA, beta)
            _salvar_config(None, CHAVE_USAR_FAMILIA, usar_familia)
            _salvar_config(None, CHAVE_MULT_FAMILIA_VP, mult_fam_vp)
            _salvar_config(None, CHAVE_MULT_FAMILIA_EE, mult_fam_ee)
            _salvar_config(None, CHAVE_USAR_TIPO, usar_tipo)
            _salvar_config(None, CHAVE_MULT_TIPO, mult_tipo)
            _salvar_config(None, CHAVE_USAR_TIPO_INSPECAO, usar_tipo_insp)
            _salvar_config(None, CHAVE_MULT_TIPO_INSPECAO, mult_tipo_insp)
            carregar_score_config.clear()  # efeito imediato pra quem salvou, sem esperar o TTL de 5min
            st.success("✅ Configuração de Score salva! Já vale pra SP, VP, Geral e Modo TV.")

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
            f"""
            | Item | Valor |
            |---|---|
            | **App** | MRS Sentinel |
            | **Stack** | Streamlit + Supabase + ECharts + Plotly |
            | **Versão** | v{APP_VERSION} |
            | **Perfis** | Admin / Assistente / Usuário |
            | **Banco** | Supabase (PostgreSQL) |
            """
        )
        if st.button("🔄 Limpar Cache de Dados", key="btn_cache"):
            st.cache_data.clear()
            st.success("✅ Cache limpo! Próxima navegação buscará dados frescos do banco.")


# _get_config/_salvar_config viraram fonte única em database/queries.py
# (get_config/salvar_config), reaproveitada também por core/score_engine.py
# (score_engine é importado POR admin_panel — import circular se fosse o
# contrário). _get_config é usado direto via alias no import acima; só
# _salvar_config precisa deste wrapper fino aqui pra continuar injetando o
# admin_id automaticamente (a versão compartilhada recebe por parâmetro,
# a antiga pegava sozinha de st.session_state — sem este wrapper, as
# dezenas de chamadas já existentes que não passam admin_id perderiam o
# registro de "quem alterou" em atualizado_por).
def _salvar_config(gerencia: str | None, chave: str, valor) -> None:
    admin_id = st.session_state.get("usuario", {}).get("id")
    _salvar_config_shared(gerencia, chave, valor, admin_id)

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
        ger_del = st.selectbox("Gerência", LISTA_GERENCIAS, key="del_ger")
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

    st.markdown("---")
    _render_secao_resolver_duplicados()

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
        ger_del_rasf = st.selectbox("Gerência", LISTA_GERENCIAS + ["Todas"], key="del_ger_rasf")

    supabase = get_supabase()
    ger_filtro = ger_del_rasf if ger_del_rasf != "Todas" else None

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


# region ================ SESSÃO X.2: Resolver uploads duplicados =============

# Mapa disciplina -> tabela onde as linhas de dados daquele upload vivem.
# Disciplinas fora deste mapa são ignoradas na limpeza (não sabemos onde
# apagar os dados filhos com segurança).
_TABELA_POR_DISCIPLINA = {
    "VP":        "notas",
    "EE":        "notas",
    "RASF":      "rasf_ee",
    "RASF_BASE": "rasf_baseline",
}


def _render_secao_resolver_duplicados() -> None:
    """
    Detecta e resolve uploads com status='ativo' duplicados na mesma
    Gerência+Disciplina — situação que não deveria existir (só 1 upload
    'ativo' por combinação), mas pode acontecer se o UPDATE de arquivamento
    em data_uploader.py falhar parcialmente numa rede corporativa instável
    (ver docstring de _verificar_arquivamento em modules/data_uploader.py).

    A leitura (database/queries*.py) já se blinda disso escolhendo apenas o
    upload mais recente de cada combinação, mas os registros antigos ficam
    "presos" como 'ativo' no banco, poluindo o Histórico de Uploads e
    disparando o aviso ⚠️ toda vez que a tela é aberta. Esta seção resolve
    de vez: apaga as linhas de dados (notas/rasf_ee/rasf_baseline) e o
    próprio registro de uploads_historico dos uploads antigos, mantendo só
    o mais recente de cada Gerência+Disciplina.
    """
    st.markdown("#### 🔁 Resolver Uploads Duplicados (status 'ativo' preso)")
    st.caption(
        "Detecta uploads que ficaram marcados como 'ativo' quando já deveriam "
        "ter sido substituídos (falha de rede durante o upload) e apaga os "
        "antigos — dados e registro do upload — mantendo só o mais recente "
        "de cada Gerência+Disciplina."
    )

    supabase = get_supabase()

    try:
        resp = (
            supabase.table("uploads_historico")
            .select("id, gerencia, disciplina, nome_arquivo, total_notas, enviado_em")
            .eq("status", "ativo")
            .execute()
        )
        registros = resp.data or []
    except Exception as e:
        st.error(f"❌ Erro ao buscar uploads: {e}")
        return

    grupos: dict[tuple[str, str], list[dict]] = {}
    for r in registros:
        grupos.setdefault((r["gerencia"], r["disciplina"]), []).append(r)

    a_remover: list[dict] = []
    for (gerencia, disciplina), lst in grupos.items():
        if len(lst) <= 1:
            continue
        lst_ordenado = sorted(lst, key=lambda r: r.get("enviado_em") or "", reverse=True)
        for antigo in lst_ordenado[1:]:
            a_remover.append({**antigo, "gerencia": gerencia, "disciplina": disciplina})

    if not a_remover:
        st.success("✅ Nenhum upload duplicado encontrado — tudo em ordem.")
        return

    # Preview com impacto real (linhas filhas que seriam apagadas)
    linhas_preview = []
    for item in a_remover:
        tabela = _TABELA_POR_DISCIPLINA.get(item["disciplina"])
        qtd_filhas = None
        if tabela:
            try:
                r = (
                    supabase.table(tabela)
                    .select("id", count="exact")
                    .eq("upload_id", item["id"])
                    .execute()
                )
                qtd_filhas = r.count or 0
            except Exception:
                qtd_filhas = "?"
        item["_qtd_filhas"] = qtd_filhas if isinstance(qtd_filhas, int) else 0
        linhas_preview.append({
            "Gerência":    item["gerencia"],
            "Disciplina":  item["disciplina"],
            "Arquivo":     item["nome_arquivo"],
            "Enviado em":  item.get("enviado_em"),
            "Nº notas (registrado no upload)": item.get("total_notas"),
            "Tabela filha": tabela or "⚠️ desconhecida — não será apagado",
            "Linhas filhas hoje no banco": qtd_filhas,
        })

    df_preview = pd.DataFrame(linhas_preview)
    if "Enviado em" in df_preview.columns:
        df_preview["Enviado em"] = pd.to_datetime(df_preview["Enviado em"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")

    st.warning(
        f"⚠️ {len(a_remover)} upload(s) antigo(s) presos como 'ativo' serão "
        "**apagados permanentemente** (registro do upload + linhas de dados "
        "associadas), mantendo apenas o mais recente de cada Gerência+Disciplina.",
        icon="⚠️",
    )
    st.dataframe(df_preview, use_container_width=True, hide_index=True)

    confirmacao_dup = st.text_input(
        'Digite "CONFIRMAR" para habilitar o botão:',
        key="dup_confirm_txt",
    )

    if st.button(
        f"🗑️ Apagar {len(a_remover)} upload(s) duplicado(s)",
        type="primary",
        disabled=(confirmacao_dup.strip().upper() != "CONFIRMAR"),
        key="btn_resolver_duplicados",
    ):
        total_filhas_apagadas = 0
        erros = []
        for item in a_remover:
            tabela = _TABELA_POR_DISCIPLINA.get(item["disciplina"])
            try:
                if tabela:
                    supabase.table(tabela).delete().eq("upload_id", item["id"]).execute()
                    total_filhas_apagadas += item["_qtd_filhas"]
                else:
                    erros.append(
                        f"Disciplina '{item['disciplina']}' (upload {item['id']}) "
                        "não tem tabela mapeada — registro de upload não apagado."
                    )
                    continue

                supabase.table("uploads_historico").delete().eq("id", item["id"]).execute()
            except Exception as ex:
                erros.append(f"upload {item['id']} ({item['nome_arquivo']}): {ex}")

        # Limpa os caches que podem ter dados desses uploads
        from database.queries import invalidar_cache_notas
        from database.queries_rasf import invalidar_cache_rasf
        from database.queries_baseline import invalidar_cache_baseline
        invalidar_cache_notas()
        invalidar_cache_rasf()
        invalidar_cache_baseline()

        admin_logado = st.session_state.get("usuario", {})
        _registrar_log(
            acao="RESOLVER_UPLOADS_DUPLICADOS",
            detalhes={
                "uploads_removidos": [item["id"] for item in a_remover],
                "linhas_filhas_apagadas": total_filhas_apagadas,
                "erros": erros,
            },
            admin_id=admin_logado.get("id"),
        )

        if erros:
            for e in erros:
                st.error(f"❌ {e}")
        st.success(
            f"✅ {len(a_remover) - len(erros)} upload(s) duplicado(s) apagado(s) "
            f"({total_filhas_apagadas} linhas de dados removidas)."
        )
        st.rerun()

# endregion