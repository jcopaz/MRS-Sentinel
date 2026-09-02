# modules/home.py — Sidebar de navegação (renderizado após login)
# A sidebar é a "espinha dorsal" da navegação. Persiste em todas as telas.
# Contém: logo, usuário ativo, botões de gerência, card última atualização, logout.

from pathlib import Path

import streamlit as st
from auth.session import get_nome, get_perfil, get_gerencia, set_pagina, get_pagina, clear_session, get_id
from auth.permissions import can_admin_panel, can_upload, gerencias_visiveis, can_access_modo_tv, can_ver_visao_geral, is_admin
from database.queries import log_acesso, contar_alertas_novos
from core.glossarios import GERENCIAS_COM_DASHBOARD, GERENCIA_GERAL_DE
from core.versao import APP_VERSION

# Logo animado — mp4 em vez de gif (mesmo conteúdo, muito mais leve: H.264
# comprime bem melhor que a paleta do GIF). Servido via static file serving
# do Streamlit (ver .streamlit/config.toml -> enableStaticServing) a partir
# de static/, pasta irmã de app.py na raiz do repo — por isso dois caminhos:
# um absoluto (checagem de existência em disco) e um relativo (URL do <video>).
LOGO_VIDEO_PATH = Path(__file__).resolve().parent.parent / "static" / "Sentinel_logo.mp4"
LOGO_VIDEO_URL = "app/static/Sentinel_logo.mp4"
LOGO_WIDTH = 240  # px — mesmo tamanho usado na tela de Login (auth/login.py)


# region ====================== SESSÃO 1: CSS da Sidebar ======================

def _inject_sidebar_css():
    """CSS para estilizar a sidebar com identidade MRS."""
    st.markdown("""
    <style>
    /* Fundo escuro da sidebar */
    [data-testid="stSidebar"] > div:first-child {
        background: #1b2130;
        padding: 0;
    }

    /* Logo em vídeo — centralizado direto no HTML (ver _render_logo), não
       precisa de regra aqui: é um <div style="text-align:center"> escrito à
       mão, sem depender de testid interno do Streamlit (que muda de versão
       pra versão — foi o que quebrou a centralização do st.image antes).
       Só o respiro em relação à borda da sidebar continua aqui. */
    [data-testid="stSidebar"] .sentinel-logo-wrap {
        padding: 1.2rem 0 0 0;
    }

    /* Todos os textos na sidebar ficam brancos */
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div {
        color: #ffffff !important;
    }

    /* st.date_input (Abertura/Encerramento da Nota) herdava o branco da
       regra genérica acima e ficava com texto branco sobre o fundo claro
       que o BaseWeb usa nesse componente — a data estava lá (o widget
       sempre recebe um value), só invisível: texto branco em cima de caixa
       branca (reportado pelo Julio, 2026-09-01, como "campo não aparece
       preenchido clicando"). 1ª tentativa (só `input`) não resolveu —
       confirmado pelo Julio com print, continuava em branco. Mesma
       armadilha já registrada com BaseWeb noutro projeto irmão (Gestão_OS):
       BaseWeb não obedece estilo elemento-por-elemento, precisa "* {color:
       preto}" pegando TODOS os descendentes (o texto visível pode estar
       num <div>/<span> interno do BaseWeb, não direto no <input>). Reforça
       com id extra (o próprio Streamlit) e maior especificidade pra vencer
       o CSS-in-JS do BaseWeb, que injeta <style> depois do nosso bloco. */
    [data-testid="stSidebar"] [data-testid="stDateInput"],
    [data-testid="stSidebar"] [data-testid="stDateInput"] * {
        color: #000000 !important;
    }
    [data-testid="stSidebar"] [data-testid="stDateInput"] input {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        caret-color: #000000 !important;
        background: #ffffff !important;
    }
    /* "Início"/"Fim" (Abertura/Encerramento da Nota): a tentativa anterior
       (só no <label> e no wrapper stWidgetLabel) não pegou — o texto
       "Início"/"Fim" de verdade fica num <p> AINDA MAIS interno (dentro de
       stMarkdownContainer), que é exatamente um dos "TODOS os
       descendentes" pintados de preto pela regra `* {color:preto}" acima
       (pensada pro valor da data, não pro rótulo). Pintar só o <label>/
       stWidgetLabel de branco não adianta: esse <p> tem uma regra própria
       (via a wildcard) que bate DIRETO nele, e "regra direta no elemento"
       sempre vence "cor herdada do pai", não importa a especificidade do
       pai. Corrigido pegando TAMBÉM os descendentes do label (`label *`),
       com especificidade maior que a wildcard genérica -> essa parte
       específica vence, o resto do stDateInput (o valor da data) continua
       preto como deve ser. */
    [data-testid="stSidebar"] [data-testid="stDateInput"] label,
    [data-testid="stSidebar"] [data-testid="stDateInput"] label *,
    [data-testid="stSidebar"] [data-testid="stDateInput"] [data-testid="stWidgetLabel"],
    [data-testid="stSidebar"] [data-testid="stDateInput"] [data-testid="stWidgetLabel"] * {
        color: #ffffff !important;
        opacity: 1 !important;
    }

    /* Botões da sidebar — estilo ghost */
    [data-testid="stSidebar"] .stButton > button {
        background: transparent !important;
        color: #d1d5db !important;
        border: 1px solid rgba(255,255,255,0.15) !important;
        border-radius: 10px !important;
        text-align: left !important;
        padding: 10px 16px !important;
        font-size: 14px !important;
        width: 100% !important;
        transition: all 0.2s ease !important;
        margin-bottom: 4px;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(255,255,255,0.12) !important;
        border-color: rgba(255,255,255,0.35) !important;
        color: #ffffff !important;
        transform: translateX(3px);
    }

    /* Divisor */
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.12) !important;
        margin: 12px 0 !important;
    }

    /* Texto "SENTINEL" em dourado 3D reluzente — cor sólida + relevo nítido
       (sombras SEM blur, só deslocadas — nada de "0 0 Xpx", que é o que cria
       o halo/glow espalhado atrás da palavra). O brilho vem só de um pulso
       de brightness() no próprio texto, não de sombra difusa. Seletor com
       prefixo [data-testid="stSidebar"] pra vencer em especificidade a
       regra genérica "div{color:#fff!important}" acima. */
    [data-testid="stSidebar"] .sentinel-gold-3d {
        font-family: 'Arial Black', Arial, sans-serif;
        font-weight: 900 !important;
        letter-spacing: 0.14em;
        text-align: center;
        line-height: 1.1;
        color: #e8a920 !important;
        text-shadow:
            0 1px 0 #8a6314,
            0 2px 0 #7a5610,
            0 3px 2px rgba(0,0,0,.30);
        animation: sentinelShimmer 2.8s ease-in-out infinite;
    }
    [data-testid="stSidebar"] .sentinel-gold-3d.sm { font-size: 1.35rem; }
    @keyframes sentinelShimmer {
        0%, 100% { filter: brightness(1); }
        50%      { filter: brightness(1.22); }
    }
    </style>
    """, unsafe_allow_html=True)

# endregion


# region ====================== SESSÃO 2: Componentes da Sidebar ======================

def _render_logo():
    """Logo animado + nome do app no topo da sidebar."""
    if LOGO_VIDEO_PATH.exists():
        st.sidebar.html(f"""
        <div class="sentinel-logo-wrap" style="text-align:center;">
            <video autoplay loop muted playsinline
                style="width:{LOGO_WIDTH}px;max-width:100%;display:inline-block;">
                <source src="{LOGO_VIDEO_URL}" type="video/mp4">
            </video>
        </div>
        """)
    else:
        st.sidebar.markdown(
            "<div style='text-align:center;color:#f87171;font-size:0.75rem;padding-top:1rem;'>"
            "⚠️ Logo não encontrado (static/Sentinel_logo.mp4)</div>",
            unsafe_allow_html=True,
        )

    st.sidebar.markdown("""
    <div style="padding: 0.3rem 1rem 1rem 1rem; text-align: center;">
        <div class="sentinel-gold-3d sm">SENTINEL</div>
        <div style="font-size:0.72rem; color:rgba(255,255,255,0.5); margin-top:4px; letter-spacing:0.3px;">
            INTELIGÊNCIA DE MANUTENÇÃO
        </div>
        <div style="font-size:0.7rem; color:rgba(255,255,255,0.35); margin-top:6px; letter-spacing:0.5px;">
            v""" + APP_VERSION + """
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_usuario_badge():
    """Card do usuário logado com perfil e gerência."""
    nome    = get_nome()
    perfil  = get_perfil()
    gerencia = get_gerencia()

    # Ícone e cor por perfil
    perfil_cfg = {
        "admin":      ("👑", "#fbbf24", "Admin"),
        "assistente": ("🔧", "#60a5fa", "Assistente"),
        "usuario":    ("👤", "#a3e635", "Usuário"),
    }
    icone, cor, label = perfil_cfg.get(perfil, ("👤", "#a3e635", perfil or "?"))
    ger_txt = f" · Ger. {gerencia}" if gerencia else " · Global"

    st.sidebar.markdown(f"""
    <div style="
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 10px;
        padding: 10px 12px;
        margin: 0 1rem 1rem 1rem;
    ">
        <div style="font-size:0.8rem; color:rgba(255,255,255,0.6); margin-bottom:3px;">
            {icone} {label}{ger_txt}
        </div>
        <div style="font-size:0.92rem; font-weight:600; color:#ffffff;
                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            {nome}
        </div>
        <div style="
            display:inline-block;
            background:{cor}22; border:1px solid {cor}55;
            border-radius:20px; padding:1px 8px;
            font-size:0.7rem; color:{cor}; margin-top:4px;
        ">● Online</div>
    </div>
    """, unsafe_allow_html=True)


def _render_nav_buttons():
    """Botões de navegação entre gerências."""
    pagina_atual = get_pagina()

    st.sidebar.markdown(
        "<div style='padding:0 1rem; margin-bottom:6px;'>"
        "<span style='font-size:0.7rem; color:rgba(255,255,255,0.4); "
        "letter-spacing:1px; text-transform:uppercase;'>NAVEGAÇÃO</span></div>",
        unsafe_allow_html=True
    )

    # Define os botões disponíveis com base nas permissões
    nav_items = []

    # Só quem não tem gerência fixa (admin/global) passa pela tela de
    # escolher a Gerência Geral no login — dá pra voltar lá a qualquer
    # momento por este botão (antes só existia o redirect automático).
    if get_gerencia() is None:
        ativo_gg = "🔵 " if pagina_atual == "selecionar_gg" else ""
        nav_items.append(("GG", f"{ativo_gg}🗺️  Trocar Gerência Geral", "selecionar_gg"))

    # Admin/global só vê os botões de gerência DEPOIS de escolher uma
    # Gerência Geral em modules/selecionar_gg.py, e só as gerências
    # daquela GG (antes mostrava as 6 juntas, de todas as GGs, o tempo
    # todo). Quem tem gerência fixa (assistente/usuário) não passa por
    # essa escolha — gerencias_visiveis() já devolve só a dele mesmo.
    siglas_ger = gerencias_visiveis()
    if get_gerencia() is None:
        gg_ativa = st.session_state.get("gg_ativa")
        if not gg_ativa and pagina_atual.startswith("gerencia_"):
            # Sessão antiga/F5 caiu direto numa tela de gerência sem passar
            # pelo seletor — infere a GG a partir da tela atual em vez de
            # esconder a navegação (senão o admin fica sem sair dali).
            sigla_atual = pagina_atual.removeprefix("gerencia_").upper()
            gg_ativa = GERENCIA_GERAL_DE.get(sigla_atual)
            if pagina_atual == "gerencia_geral":
                gg_ativa = "São Paulo"
            st.session_state["gg_ativa"] = gg_ativa
        siglas_ger = [s for s in siglas_ger if GERENCIA_GERAL_DE.get(s) == gg_ativa] if gg_ativa else []

    for sigla in siglas_ger:
        pagina_ger = f"gerencia_{sigla.lower()}"
        ativo_ger = "🔵 " if pagina_atual == pagina_ger else ""
        # 🚧 pras gerências sem dashboard ligado ainda — evita que o
        # usuário só descubra clicando (ver modules/gerencia_placeholder.py)
        icone = "🏭" if sigla in GERENCIAS_COM_DASHBOARD else "🚧"
        nav_items.append((sigla, f"{ativo_ger}{icone}  Gerência {sigla}", pagina_ger))

    # Visão Geral: combina SP+VP — só quem NÃO tem uma Gerência específica
    # delegada (2026-09-02, corrige achado do Julio: usuário com Gerência
    # SP via a Visão Geral, que mostra mais que o escopo dele).
    if can_ver_visao_geral():
        ativo_geral = "🔵 " if pagina_atual == "gerencia_geral" else ""
        nav_items.append(("GERAL", f"{ativo_geral}🌐  Visão Geral", "gerencia_geral"))

    # Evolução da Malha: comparativo período a período (base viva de notas)
    ativo_evo = "🔵 " if pagina_atual == "evolucao" else ""
    nav_items.append(("EVOLUCAO", f"{ativo_evo}📈  Evolução da Malha", "evolucao"))

    # Visão de Campo e Alertas: restritos a admin (pedido do Julio,
    # 2026-09-01) — "não faz sentido da maneira que está" pros demais
    # perfis. Botão some do menu E a tela em si é bloqueada em
    # modules/visao_campo.py / modules/alertas.py (require_admin()) —
    # não só o link some, o acesso direto por pagina_atual também.
    if is_admin():
        ativo_campo = "🔵 " if pagina_atual == "campo" else ""
        nav_items.append(("CAMPO", f"{ativo_campo}📱  Visão de Campo", "campo"))

        ativo_alertas = "🔵 " if pagina_atual == "alertas" else ""
        try:
            n_novos = contar_alertas_novos(get_gerencia())
        except Exception:
            n_novos = 0
        badge = f"  ({n_novos})" if n_novos else ""
        nav_items.append(("ALERTAS", f"{ativo_alertas}🚨  Alertas{badge}", "alertas"))

    # Upload: admin e assistente
    gerencia_usr = get_gerencia()
    gerencia_upload = gerencia_usr or "SP"
    if can_upload(gerencia_upload) or get_perfil() == "admin":
        ativo_upload = "🔵 " if pagina_atual == "upload" else ""
        nav_items.append(("UPLOAD", f"{ativo_upload}📤  Upload de Dados", "upload"))

    # Modo TV: admin, ou usuário com 'acesso_tv' marcado no Painel Admin
    # (pensado pra uma TV/monitor de coordenação — ver modules/modo_tv.py)
    if can_access_modo_tv():
        ativo_tv = "🔵 " if pagina_atual == "modo_tv" else ""
        nav_items.append(("MODO_TV", f"{ativo_tv}📺  Modo TV", "modo_tv"))

    # Admin Panel: somente admin
    if can_admin_panel():
        ativo_admin = "🔵 " if pagina_atual == "admin" else ""
        nav_items.append(("ADMIN", f"{ativo_admin}⚙️  Administração", "admin"))

    # Renderiza os botões
    with st.sidebar:
        for _, label, pagina_destino in nav_items:
            if st.button(label, key=f"nav_{pagina_destino}", use_container_width=True):
                set_pagina(pagina_destino)
                uid = get_id()
                if uid:
                    log_acesso(uid, f"view_{pagina_destino}")
                st.rerun()


def _render_ultima_atualizacao():
    """Card de 'última atualização' consultando o banco."""
    from datetime import datetime

    st.sidebar.markdown("<br>", unsafe_allow_html=True)
    st.sidebar.markdown(
        "<div style='padding:0 1rem; margin-bottom:6px;'>"
        "<span style='font-size:0.7rem; color:rgba(255,255,255,0.4); "
        "letter-spacing:1px; text-transform:uppercase;'>ÚLTIMA ATUALIZAÇÃO</span></div>",
        unsafe_allow_html=True
    )

    from database.queries import get_ultima_atualizacao_info
    ultimo = get_ultima_atualizacao_info()


    if not ultimo:
        st.sidebar.markdown("""
        <div style="
            background: rgba(255,255,255,0.05);
            border: 1px dashed rgba(255,255,255,0.2);
            border-radius: 10px; padding: 12px 14px; margin: 0 1rem;
            font-size:0.82rem; color:rgba(255,255,255,0.45); text-align:center;
        ">
            📭 Sem dados carregados ainda
        </div>
        """, unsafe_allow_html=True)
        return

    # Formata a data de envio
    try:
        dt = datetime.fromisoformat(ultimo["enviado_em"].replace("Z", "+00:00"))
        data_fmt = dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        data_fmt = "—"

    gerencia  = ultimo.get("gerencia", "?")
    disciplina = ultimo.get("disciplina", "?")
    total     = f"{ultimo.get('total_notas', 0):,}".replace(",", ".")

    st.sidebar.markdown(f"""
    <div style="
        background: rgba(255,176,0,0.08);
        border: 1px solid rgba(255,176,0,0.25);
        border-radius: 10px; padding: 12px 14px; margin: 0 1rem;
    ">
        <div style="font-size:0.78rem; color:#ffb000; font-weight:600; margin-bottom:4px;">
            Ger. {gerencia} — {disciplina}
        </div>
        <div style="font-size:0.82rem; color:rgba(255,255,255,0.7);">
            {data_fmt}
        </div>
        <div style="font-size:0.78rem; color:rgba(255,255,255,0.5); margin-top:2px;">
            {total} notas carregadas
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_logout():
    """Botão de logout no fundo da sidebar."""
    st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
    st.sidebar.divider()

    with st.sidebar:
        if st.button("🚪  Sair", key="btn_logout", use_container_width=True):
            uid = get_id()
            if uid:
                log_acesso(uid, "logout")
            # Não chama auth.sign_out() no client compartilhado (get_supabase())
            # de propósito — login já não usa esse client pra autenticar (ver
            # database/client.py::criar_cliente_auth_temporario), então ele
            # nunca tem uma sessão "logada" própria dele pra encerrar; um
            # sign_out ali arriscaria derrubar a sessão de outro usuário
            # concorrente caso o client acabe acumulando estado no futuro.
            # Bastar limpar o estado da aplicação:
            clear_session()
            st.rerun()

    # Versão no rodapé — só de core/versao.py (ver comentário em auth/login.py)
    st.sidebar.markdown(
        f"<div style='text-align:center; padding:0.5rem; "
        f"font-size:0.7rem; color:rgba(255,255,255,0.25);'>v{APP_VERSION}</div>",
        unsafe_allow_html=True
    )

# endregion


# region ====================== SESSÃO 3: Renderização Principal ======================

def render_sidebar():
    """
    Ponto de entrada: renderiza a sidebar completa.
    Deve ser chamado ANTES de renderizar o conteúdo da página.
    """
    _inject_sidebar_css()
    _render_logo()
    _render_usuario_badge()
    _render_nav_buttons()
    _render_ultima_atualizacao()
    _render_logout()

# endregion
