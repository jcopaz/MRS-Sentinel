# =============================================================================
# core/score_engine.py — Motor de Score Composto
# Sprint 3 — MRS Sentinel (fórmula estendida na Sprint 4.5; config migrada
# do sidebar de cada Gerência pra Administração > Configurações em 2026-09-01)
#
# Fórmula:
#   Score = peso_prio × mult_status × mult_familia × mult_tipo × mult_tipo_insp
#         × (1 + α × anos_aberta)
#         × (1 + β × (n_ocorrencias_local - 1))
#
# mult_status: neutro (1.0) para todos os códigos desde 10/07/2026 — decisão
#   do Julio de não penalizar/bonificar por status, só por tempo aberto e
#   criticidade do local/família.
# n_ocorrencias_local: reincidência do mesmo defeito no mesmo local — conta
#   quantas notas do DataFrame atual compartilham ramal+origem+familia_defeito
#   (mesma granularidade do motor de alertas, core/alertas.py).
#
# CONFIG PERSISTIDA POR GERÊNCIA (2026-09-01): até aqui, cada tela de
# Gerência (SP/VP/Geral) tinha seu PRÓPRIO expander de Score na sidebar
# (render_score_sidebar, removido) — nada disso era salvo, resetava pros
# valores padrão a cada acesso/F5. Passou primeiro por uma versão com UMA
# config global só (mesmo commit, mesmo dia) — revertido ainda no mesmo
# dia a pedido do Julio: "pode haver mais de uma configuração distinta
# para cada Gerência Local". Ficou como no desenho original, só que agora
# de fato salvo: cada Gerência (SP/VP/FN/FS/RJ/LC) tem sua PRÓPRIA linha
# em `configuracoes` (coluna gerencia = a sigla, chave prefixada 'score_'),
# e a Visão Geral/Modo TV usam uma linha própria com gerencia='GERAL'
# (mesmo padrão que já existia: a Geral sempre teve config independente de
# SP e VP, não é uma combinação das duas). O painel em Administração tem
# um seletor "Configurando a Gerência" — edita uma de cada vez, com botão
# de resetar ao padrão e uma "foto" (render_conteudo_transparencia) de
# como aquela Gerência está calculando o score AGORA, antes de mexer.
# Família de defeito continua com DUAS listas de pesos (VP e EE) DENTRO de
# cada Gerência — isso não é por Gerência, é porque VP e EE têm
# vocabulário de família diferente (Trilho/AMV/... x Wayside/Sinalização/
# ...), distinção real de dado, mantida como estava.
#
# Exporta:
#   ScoreConfig                    — dataclass com pesos configuráveis
#   carregar_score_config(gerencia) — lê a config persistida de 1 Gerência
#   calcular_score_dataframe()     — aplica score a todo o DataFrame
#   render_painel_transparencia()  — pesos ativos, com expander próprio (telas de Gerência)
#   render_conteudo_transparencia() — mesmo conteúdo, sem expander (reuso em Administração)
#
# Sessão 1: Imports & constantes de peso
# Sessão 2: ScoreConfig (dataclass)
# Sessão 3: calcular_score_linha() — cálculo por linha
# Sessão 4: calcular_score_dataframe() — vetorizado
# Sessão 5: carregar_score_config(gerencia) — lê config persistida de 1 Gerência
# Sessão 6: render_painel_transparencia() / render_conteudo_transparencia()
# =============================================================================

# region ====================== SESSÃO 1: Imports & Constantes =================
import streamlit as st
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# Pesos base (conforme 05_PADROES_TECNICOS.md)
PESO_PRIORIDADE_PADRAO = {
    "1-Muito alta": 4,
    "2-Alta":       3,
    "3-Média":      2,
    "4-Baixa":      1,
}

MULT_STATUS_PADRAO = {
    "ABER": 1.0,   # nota aberta = peso total
    "DIFE": 1.0,   # diferida = peso neutro (decisão do Julio, 10/07/2026 — Sprint 4.5)
}

MULT_FAMILIA_VP_PADRAO = {
    "Trilho":           1.5,
    "Geometria":        1.5,
    "AMV":              1.5,
    "Dormente":         1.2,
    "Lastro":           1.2,
    "Junta":            1.0,
    "Solda":            1.0,
    "Cota Salvaguarda": 1.0,
    "Geral Manutenção": 0.8,
    "Outros":           1.0,
}

MULT_FAMILIA_EE_PADRAO = {
    "Wayside":               1.5,
    "Sinalização":           1.3,
    "Energia":               1.2,
    "Telecomunicações":      1.0,
    "Sinalização Específica":1.1,
    "Outros":                1.0,
}

MULT_TIPO_PADRAO = {
    "CT": 1.5,   # corretiva = mais urgente
    "PV": 1.0,   # preventiva
}

# Tipo de inspeção (coluna tipo_atividade: Ronda, Drone, Trackstar,
# Inspeção técnica de AMV, etc.) — dimensão NOVA (2026-09-01, pedido do
# Julio), sem peso padrão histórico: os valores são 100% definidos pelos
# dados carregados (mesmo catálogo dinâmico do filtro "Tipo de inspeção"
# em components/filtros.py::_opcoes_tipos_inspecao), não um glossário
# fixo. Começa OFF e vazio — ninguém tem um score recalculado sozinho no
# dia em que este recurso for ao ar; só passa a valer quando o admin
# marcar "usar" e escolher pesos em Administração > Configurações.
MULT_TIPO_INSPECAO_PADRAO: dict = {}

ALPHA_PADRAO = 0.10  # 10% de acréscimo por ano aberto

# Reincidência: mesmo ramal+origem+familia_defeito repetido no DataFrame atual.
# Mesma granularidade de "local" usada em core/alertas.py (hot-spots crônicos).
BETA_REINCIDENCIA_PADRAO = 0.15       # +15% de score por ocorrência repetida no local
REINCIDENCIA_MULT_MAX_PADRAO = 3.0    # trava o multiplicador (evita disparo com clusters gigantes)

# endregion


# region ====================== SESSÃO 2: ScoreConfig ==========================

@dataclass
class ScoreConfig:
    """
    Configuração completa dos pesos do score composto.
    Todos os campos têm valores padrão — basta instanciar sem argumentos
    para obter o comportamento canônico.
    """
    # Multiplicador de idade (% por ano em aberto)
    alpha: float = ALPHA_PADRAO

    # Pesos configuráveis via sidebar
    peso_prioridade: dict = field(default_factory=lambda: dict(PESO_PRIORIDADE_PADRAO))
    mult_status:     dict = field(default_factory=lambda: dict(MULT_STATUS_PADRAO))
    mult_familia_vp: dict = field(default_factory=lambda: dict(MULT_FAMILIA_VP_PADRAO))
    mult_familia_ee: dict = field(default_factory=lambda: dict(MULT_FAMILIA_EE_PADRAO))
    mult_tipo:       dict = field(default_factory=lambda: dict(MULT_TIPO_PADRAO))
    # Tipo de inspeção (tipo_atividade) — ver MULT_TIPO_INSPECAO_PADRAO acima.
    # Só as chaves aqui presentes ganham peso ≠ 1.0 — mesmo mecanismo de
    # "selecionar quais entram" que família/tipo já usam: o dict inteiro
    # É a seleção, o que não está aqui fica neutro (.get(x, 1.0)).
    mult_tipo_inspecao: dict = field(default_factory=lambda: dict(MULT_TIPO_INSPECAO_PADRAO))

    # Reincidência: peso extra por nota repetida no mesmo ramal+origem+família
    beta_reincidencia:      float = BETA_REINCIDENCIA_PADRAO
    reincidencia_mult_max:  float = REINCIDENCIA_MULT_MAX_PADRAO

    # Flags de ativação (permite desligar componentes do score)
    usar_familia:       bool = True
    usar_tipo:          bool = True
    usar_tipo_inspecao: bool = False  # nova dimensão nasce desligada — ver comentário acima
    usar_idade:         bool = True
    usar_reincidencia:  bool = True

# endregion


# region ====================== SESSÃO 3: Cálculo por linha ====================

def _anos_abertos(data_nota) -> float:
    """
    Calcula quantos anos a nota está aberta até hoje.
    Defensivo: retorna 0 se data for inválida.
    """
    try:
        if pd.isna(data_nota):
            return 0.0
        dt = pd.Timestamp(data_nota)
        delta = (pd.Timestamp(date.today()) - dt).days
        return max(delta / 365.25, 0.0)
    except Exception:
        return 0.0


def calcular_score_linha(row: pd.Series, cfg: ScoreConfig) -> float:
    """
    Calcula o score composto de uma linha do DataFrame.

    Fórmula:
        score = peso_prio × mult_status × mult_familia × mult_tipo
              × (1 + α × anos_aberta) × (1 + β × (n_ocorrencias_local - 1))

    Args:
        row: Series com campos peso_prio, status_usuario, familia_defeito,
             tipo_nota, data_nota, disciplina_label, n_ocorrencias_local
             (esta última pré-calculada por calcular_score_dataframe — ver
             Sessão 4; ausente aqui = trata como ocorrência única)
        cfg: ScoreConfig com pesos configuráveis

    Returns:
        float: score arredondado a 2 casas decimais
    """
    # Guarda defensiva: se cfg não for ScoreConfig (ex: string passada por engano),
    # usa configuração padrão em vez de explodir com AttributeError
    if not isinstance(cfg, ScoreConfig):
        cfg = ScoreConfig()

    # Base: peso de prioridade
    prio_raw = str(row.get("prioridade", "4-Baixa")).strip()
    score = float(cfg.peso_prioridade.get(prio_raw, 1))

    # Usa peso_prio direto se disponível (mais preciso)
    peso_prio_col = row.get("peso_prio")
    if peso_prio_col and not pd.isna(peso_prio_col):
        score = float(peso_prio_col)

    # Multiplicador de status
    status_raw = str(row.get("status_usuario", "ABER")).strip().upper()[:4]
    score *= cfg.mult_status.get(status_raw, 1.0)

    # Multiplicador de família (VP ou EE)
    if cfg.usar_familia:
        disc = str(row.get("disciplina_label", row.get("disciplina", "VP"))).upper()
        familia = str(row.get("familia_defeito", row.get("familia_cod", "Outros"))).strip()
        if "EE" in disc:
            score *= cfg.mult_familia_ee.get(familia, 1.0)
        else:
            score *= cfg.mult_familia_vp.get(familia, 1.0)

    # Multiplicador de tipo de nota
    if cfg.usar_tipo:
        tipo = str(row.get("tipo_nota", "PV")).strip().upper()[:2]
        score *= cfg.mult_tipo.get(tipo, 1.0)

    # Multiplicador de tipo de inspeção (tipo_atividade: Ronda, Drone,
    # Trackstar, Inspeção técnica de AMV, etc. — ver MULT_TIPO_INSPECAO_PADRAO)
    if cfg.usar_tipo_inspecao:
        tipo_insp = str(row.get("tipo_atividade", "")).strip()
        score *= cfg.mult_tipo_inspecao.get(tipo_insp, 1.0)

    # Fator de envelhecimento
    if cfg.usar_idade:
        anos = _anos_abertos(row.get("data_nota"))
        score *= (1 + cfg.alpha * anos)

    # Fator de reincidência: mesmo defeito repetido no mesmo local
    # (ramal + origem + familia_defeito). n_ocorrencias_local vem pré-calculado
    # por calcular_score_dataframe; se ausente, assume ocorrência única (sem efeito).
    if cfg.usar_reincidencia:
        n_local = row.get("n_ocorrencias_local", 1)
        try:
            n_local = int(n_local) if pd.notna(n_local) else 1
        except (TypeError, ValueError):
            n_local = 1
        mult_reinc = 1 + cfg.beta_reincidencia * max(0, n_local - 1)
        mult_reinc = min(mult_reinc, cfg.reincidencia_mult_max)
        score *= mult_reinc

    return round(score, 2)

# endregion


# region ====================== SESSÃO 4: Vetorizado ===========================

def calcular_score_dataframe(df: pd.DataFrame, cfg: Optional[ScoreConfig] = None) -> pd.DataFrame:
    """
    Aplica o score composto a todo o DataFrame de forma eficiente.

    Cria (ou sobrescreve) a coluna 'score' em cada linha.
    Defensivo: se o DataFrame estiver vazio, retorna sem modificar.

    Args:
        df: DataFrame com notas
        cfg: ScoreConfig; se None, usa configuração padrão

    Returns:
        DataFrame com coluna 'score' adicionada/atualizada
    """
    if df.empty:
        return df

    # Guarda defensiva: se cfg não for ScoreConfig (ex: string passada por engano),
    # usa configuração padrão em vez de explodir com AttributeError
    if cfg is None or not isinstance(cfg, ScoreConfig):
        cfg = ScoreConfig()

    df = df.copy()

    # Pré-calcula reincidência local (ramal+origem+familia_defeito) ANTES do
    # apply por linha — precisa ver o DataFrame inteiro para contar ocorrências.
    # Mesma granularidade de "local" do motor de alertas (core/alertas.py).
    grupo_cols = ["ramal", "origem", "familia_defeito"]
    if cfg.usar_reincidencia and all(c in df.columns for c in grupo_cols):
        df["n_ocorrencias_local"] = (
            df.groupby(grupo_cols, dropna=False)[grupo_cols[0]].transform("size")
        )
    else:
        df["n_ocorrencias_local"] = 1

    # Aplica por linha (axis=1)
    # Nota: para datasets muito grandes (>100k), considerar vetorização numpy
    df["score"] = df.apply(lambda row: calcular_score_linha(row, cfg), axis=1)

    return df

# endregion


# region ====================== SESSÃO 5: Config persistida (Administração) ====

# Chaves em `configuracoes` (gerencia=NULL — config GLOBAL, ver decisão no
# cabeçalho do módulo). Fonte única dos nomes: lidas aqui, escritas pelo
# painel "🎯 Score — Pesos e Multiplicadores" em modules/admin_panel.py.
CHAVE_PESO_PRIORIDADE    = "score_peso_prioridade"
CHAVE_USAR_IDADE         = "score_usar_idade"
CHAVE_ALPHA              = "score_alpha"
CHAVE_USAR_REINCIDENCIA  = "score_usar_reincidencia"
CHAVE_BETA_REINCIDENCIA  = "score_beta_reincidencia"
CHAVE_USAR_FAMILIA       = "score_usar_familia"
CHAVE_MULT_FAMILIA_VP    = "score_mult_familia_vp"
CHAVE_MULT_FAMILIA_EE    = "score_mult_familia_ee"
CHAVE_USAR_TIPO          = "score_usar_tipo"
CHAVE_MULT_TIPO          = "score_mult_tipo"
CHAVE_USAR_TIPO_INSPECAO = "score_usar_tipo_inspecao"
CHAVE_MULT_TIPO_INSPECAO = "score_mult_tipo_inspecao"


def _bool_config(valor, default: bool) -> bool:
    """Normaliza valor vindo do banco (bool nativo, ou 'true'/'false'/1/0 se
    alguém editar a linha manualmente no Supabase) pra bool."""
    if valor is None:
        return default
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("true", "1", "sim")


@st.cache_data(ttl=300, show_spinner=False)
def carregar_score_config(gerencia: str) -> ScoreConfig:
    """
    Monta o ScoreConfig ativo de UMA Gerência a partir da config persistida
    em Administração > Configurações (tabela `configuracoes`, chave
    'gerencia' = a sigla passada aqui — SP/VP/FN/FS/RJ/LC ou 'GERAL' pra
    Visão Geral e Modo TV). Substitui o antigo render_score_sidebar(): a
    config deixou de ser refeita do zero em cada tela/sessão e passou a
    ser definida uma vez pelo admin — e, por pedido do Julio (2026-09-01),
    é distinta por Gerência (voltou a ser assim depois de uma passagem
    curta como config única global — decisão registrada no cabeçalho do
    módulo).

    Args:
        gerencia: sigla da Gerência ('SP', 'VP', 'FN', 'FS', 'RJ', 'LC') ou
            'GERAL' — cada uma tem sua própria linha em `configuracoes`.

    Cacheado por argumento (ttl=300s, mesmo padrão de
    database/queries_rasf.py) — evita round-trip ao banco a cada rerun de
    cada aba de cada Gerência, e cada Gerência tem sua própria entrada no
    cache (st.cache_data cacheia por combinação de argumentos). O painel
    de admin chama carregar_score_config.clear() logo após salvar/resetar
    (limpa TODAS as gerências cacheadas, não só a editada — barato,
    reconstrói na próxima leitura de cada uma), então quem editou já vê o
    efeito na hora; outras sessões pegam em até 5 min.

    Defensivo: qualquer chave ausente (nunca salva) ou corrompida cai no
    padrão de código — nunca quebra a tela por falta de linha no banco.
    """
    from database.queries import get_config

    cfg = ScoreConfig()
    try:
        cfg.peso_prioridade = dict(get_config(gerencia, CHAVE_PESO_PRIORIDADE, PESO_PRIORIDADE_PADRAO))
        cfg.usar_idade = _bool_config(get_config(gerencia, CHAVE_USAR_IDADE, True), True)
        cfg.alpha = float(get_config(gerencia, CHAVE_ALPHA, ALPHA_PADRAO))
        cfg.usar_reincidencia = _bool_config(get_config(gerencia, CHAVE_USAR_REINCIDENCIA, True), True)
        cfg.beta_reincidencia = float(get_config(gerencia, CHAVE_BETA_REINCIDENCIA, BETA_REINCIDENCIA_PADRAO))
        cfg.usar_familia = _bool_config(get_config(gerencia, CHAVE_USAR_FAMILIA, True), True)
        cfg.mult_familia_vp = dict(get_config(gerencia, CHAVE_MULT_FAMILIA_VP, MULT_FAMILIA_VP_PADRAO))
        cfg.mult_familia_ee = dict(get_config(gerencia, CHAVE_MULT_FAMILIA_EE, MULT_FAMILIA_EE_PADRAO))
        cfg.usar_tipo = _bool_config(get_config(gerencia, CHAVE_USAR_TIPO, True), True)
        cfg.mult_tipo = dict(get_config(gerencia, CHAVE_MULT_TIPO, MULT_TIPO_PADRAO))
        cfg.usar_tipo_inspecao = _bool_config(get_config(gerencia, CHAVE_USAR_TIPO_INSPECAO, False), False)
        cfg.mult_tipo_inspecao = dict(get_config(gerencia, CHAVE_MULT_TIPO_INSPECAO, MULT_TIPO_INSPECAO_PADRAO))
    except Exception:
        return ScoreConfig()  # qualquer erro de leitura/formato -> padrão de código, nunca quebra a tela

    return cfg

# endregion


# region ====================== SESSÃO 6: Painel de transparência ==============

def render_conteudo_transparencia(cfg: ScoreConfig, gerencia: str | None = None):
    """
    Conteúdo do "como o score é calculado", SEM expander/container próprio —
    quem chama decide como encaixar (st.expander numa tela de Gerência,
    st.container(border=True) como "foto atual" dentro de outro expander em
    Administração, já que Streamlit não permite expander dentro de expander).
    render_painel_transparencia() abaixo é o uso antigo (com expander
    embutido); esta função existe pra reuso sem essa amarra.

    Args:
        cfg: ScoreConfig a exibir
        gerencia: rótulo opcional só pro texto ("SP", "VP", "GERAL"...)
    """
    alvo = f" — {gerencia}" if gerencia else ""
    st.markdown(
        f"""
        **Fórmula{alvo}:**
        ```
        Score = Peso Prioridade
              × Multiplicador Status (neutro — ver nota abaixo)
              × Multiplicador Família
              × Multiplicador Tipo
              × Multiplicador Tipo de Inspeção
              × (1 + α × Anos em aberto)
              × (1 + β × Ocorrências repetidas no mesmo local - 1)
        ```
        """
    )
    st.caption(
        "ℹ️ Status (ABER/DIFE/etc.) não pondera mais o score — decisão de "
        "10/07/2026. A criticidade agora vem de: tempo aberto, família do "
        "defeito e reincidência no mesmo local (ramal+pátio+família)."
    )

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**🎯 Peso de Prioridade**")
        df_prio = pd.DataFrame(
            list(cfg.peso_prioridade.items()),
            columns=["Prioridade", "Peso Base"]
        )
        st.dataframe(df_prio, hide_index=True, use_container_width=True)

        st.markdown("**🔩 Família de defeito**")
        if not cfg.usar_familia:
            st.info("⏸️ Desativada")
        else:
            fam_vp = pd.DataFrame(list(cfg.mult_familia_vp.items()), columns=["Família (VP)", "Peso"])
            fam_ee = pd.DataFrame(list(cfg.mult_familia_ee.items()), columns=["Família (EE)", "Peso"])
            if not fam_vp.empty:
                st.dataframe(fam_vp, hide_index=True, use_container_width=True)
            if not fam_ee.empty:
                st.dataframe(fam_ee, hide_index=True, use_container_width=True)
            if fam_vp.empty and fam_ee.empty:
                st.caption("Ativa, mas nenhuma família tem peso configurado — efeito neutro (×1.0).")

        st.markdown("**📋 Tipo CT/PV**")
        if not cfg.usar_tipo:
            st.info("⏸️ Desativado")
        else:
            st.dataframe(pd.DataFrame(list(cfg.mult_tipo.items()), columns=["Tipo", "Peso"]),
                         hide_index=True, use_container_width=True)

        st.markdown("**🔍 Tipo de Inspeção**")
        if not cfg.usar_tipo_inspecao:
            st.info("⏸️ Desativado")
        elif not cfg.mult_tipo_inspecao:
            st.caption("Ativo, mas nenhum tipo de inspeção tem peso configurado — efeito neutro (×1.0).")
        else:
            st.dataframe(pd.DataFrame(list(cfg.mult_tipo_inspecao.items()), columns=["Tipo de inspeção", "Peso"]),
                         hide_index=True, use_container_width=True)

    with col_b:
        st.markdown("**📅 Envelhecimento**")
        if cfg.usar_idade:
            st.success(f"✅ Ativo — α = {cfg.alpha:.2f} (+{cfg.alpha*100:.0f}% por ano)")
            st.caption("Exemplo: nota com 3 anos → ×{:.2f}".format(1 + cfg.alpha * 3))
        else:
            st.info("⏸️ Desativado")

        st.markdown("**🔁 Reincidência no local**")
        if cfg.usar_reincidencia:
            st.success(f"✅ Ativa — β = {cfg.beta_reincidencia:.2f} (+{cfg.beta_reincidencia*100:.0f}% por repetição, teto ×{cfg.reincidencia_mult_max:.1f})")
            st.caption("Exemplo: 4ª nota no mesmo ramal+pátio+família → ×{:.2f}".format(
                min(1 + cfg.beta_reincidencia * 3, cfg.reincidencia_mult_max)
            ))
        else:
            st.info("⏸️ Desativada")

        st.markdown("**📋 Status**")
        st.dataframe(pd.DataFrame(list(cfg.mult_status.items()), columns=["Status", "Multiplicador"]),
                     hide_index=True, use_container_width=True)

    st.caption(
        "ℹ️ Scores altos = maior criticidade. Pesos ajustáveis em "
        "Administração → Configurações → 🎯 Score."
    )


def render_painel_transparencia(cfg: ScoreConfig):
    """
    Exibe, dentro de um expander próprio, o painel explicando os pesos
    ativos do score — uso nas telas de Gerência (aba KPIs). Fundamental
    para que gestores entendam como o ranking é calculado.

    Args:
        cfg: ScoreConfig com os pesos configurados pelo usuário
    """
    with st.expander("🔍 Como o score é calculado?", expanded=False):
        render_conteudo_transparencia(cfg)

# endregion


# =============================================================================
# Aliases de compatibilidade
# core/parser.py (Sprint 2) importa pelo nome antigo 'aplicar_score_dataframe'.
# O alias garante retrocompatibilidade sem alterar o parser.
# =============================================================================
aplicar_score_dataframe = calcular_score_dataframe
