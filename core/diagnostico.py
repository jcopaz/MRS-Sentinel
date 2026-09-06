# =============================================================================
# core/diagnostico.py — Classificação "Diagnosticada" (Sprint Tratamento, 2026-09-05)
#
# Cruza a base de Notas (VP) com a base de Tratamento de Notas — upload
# separado (ver core/parser.py::processar_planilha_tratamento e a tabela
# notas_tratamento, database/schema_notas_tratamento.sql) — por
# numero_nota. Não é um score: é um status derivado, calculado AO VIVO a
# cada carregamento de tela (igual o score em core/score_engine.py), nunca
# gravado fixo em `notas`.
#
# ACHADO REAL que gerou esta regra (Julio, 2026-09-05 — comparação das
# duas planilhas "Notas em Aberto GG" x "Tratamento de Notas GG"):
#   Das notas VP "Aberta" (status_amigavel) que NÃO aparecem na base de
#   Tratamento, 80,8% (15.544 de 19.230) já têm status_final='Encerrado'
#   — ou seja, NÃO é falta de diagnóstico, é status_usuario que ficou
#   preso em "ABER" sem ser atualizado junto do encerramento real da nota
#   (confirmado por status_sistema='MSEN', código técnico de "Encerrada",
#   nesses mesmos casos). Só as 19,2% restantes (3.686, concentradas em
#   RJ) são abertas de verdade em todo campo — essas sim precisam de
#   diagnóstico/ação.
#
# Por isso a categoria "ausente do Tratamento" se divide em duas, cada
# uma com um significado operacional diferente:
#   - Pendente Saneamento              → precisa de diagnóstico de verdade
#   - Encerrada — Aguarda Baixa no SAP → só precisa regularizar o status
#     no SAP, a nota já foi resolvida na prática
#
# Sessão 1: Constantes (rótulos + texto de ajuda do filtro)
# Sessão 2: calcular_diagnosticada()
# =============================================================================

import pandas as pd
import streamlit as st

# region ====================== SESSÃO 1: Constantes ============================

DIAGNOSTICADA_SIM                 = "Sim"
DIAGNOSTICADA_NAO                 = "Não"
DIAGNOSTICADA_PENDENTE_SANEAMENTO = "Pendente Saneamento"
DIAGNOSTICADA_AGUARDA_BAIXA       = "Encerrada — Aguarda Baixa no SAP"
DIAGNOSTICADA_NAO_SE_APLICA       = "Não se Aplica"

# Ordem oficial de exibição (filtros/legendas de gráfico)
DIAGNOSTICADA_OPCOES = [
    DIAGNOSTICADA_PENDENTE_SANEAMENTO,
    DIAGNOSTICADA_NAO,
    DIAGNOSTICADA_AGUARDA_BAIXA,
    DIAGNOSTICADA_SIM,
    DIAGNOSTICADA_NAO_SE_APLICA,
]

# Texto do "?" ao lado do filtro (pedido do Julio, 2026-09-05: "coloque um
# ? do lado do filtro explicando o que é cada categoria... para o caso de
# terem dúvidas") — vira o parâmetro help= do widget.
DIAGNOSTICADA_AJUDA = (
    "**Sim** — nota já diagnosticada pelo Técnico Fiscal (consta na base de "
    "Tratamento de Notas como \"Diagnosticada\").\n\n"
    "**Não** — nota aguardando diagnóstico (consta como \"Diagnosticar\").\n\n"
    "**Pendente Saneamento** — nota Aberta sem nenhum registro na base de "
    "Tratamento, e o status final confirma que ela segue aberta de "
    "verdade. Precisa de ação/diagnóstico de fato.\n\n"
    "**Encerrada — Aguarda Baixa no SAP** — nota sem registro na base de "
    "Tratamento, mas o status final já mostra \"Encerrado\": ela já foi "
    "resolvida na prática, só falta alguém regularizar o status detalhado "
    "no SAP. Não precisa de diagnóstico.\n\n"
    "**Não se Aplica** — nota já Cancelada/Concluída e nunca esteve na "
    "base de Tratamento — é o comportamento normal, a base de Tratamento "
    "só lista o que está em aberto sendo trabalhado."
)

# endregion


# region ====================== SESSÃO 2: Cálculo ================================

def _normalizar_numero_nota(valor) -> str | None:
    """'10013765.0' / 10013765 / '10013765' → '10013765' (chave de cruzamento)."""
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return str(int(float(valor)))
    except (TypeError, ValueError):
        s = str(valor).strip()
        return s or None


def calcular_diagnosticada(df_notas: pd.DataFrame, df_tratamento: pd.DataFrame) -> pd.Series:
    """
    Calcula a classificação "Diagnosticada" pra cada linha de df_notas,
    cruzando por numero_nota com df_tratamento.

    Args:
        df_notas: DataFrame de notas (precisa de 'numero_nota' e
            'status_amigavel'; 'status_final' é opcional — sem ele, cai
            no lado mais cauteloso de "Pendente Saneamento" em vez de
            "Encerrada — Aguarda Baixa no SAP").
        df_tratamento: DataFrame de core.parser.processar_planilha_tratamento()
            ou vindo do banco (precisa de 'numero_nota' e 'status_diag').
            Pode ser None/vazio (ex.: gerência sem upload de Tratamento
            ainda) — nesse caso tudo que não for Cancelada/Concluída cai
            em Pendente Saneamento/Aguarda Baixa, e o resto em Não se
            Aplica, igual se o cruzamento desse "ausente" pra tudo.

    Returns:
        pd.Series (mesmo index de df_notas) com um dos valores de
        DIAGNOSTICADA_OPCOES.
    """
    n = len(df_notas)
    if n == 0:
        return pd.Series([], dtype=str, index=df_notas.index)

    if "numero_nota" not in df_notas.columns or "status_amigavel" not in df_notas.columns:
        return pd.Series([DIAGNOSTICADA_NAO_SE_APLICA] * n, index=df_notas.index)

    nota_norm = df_notas["numero_nota"].apply(_normalizar_numero_nota)

    status_diag_por_nota: dict[str, str] = {}
    if df_tratamento is not None and not df_tratamento.empty and "numero_nota" in df_tratamento.columns:
        tr = df_tratamento.copy()
        tr["_nota"] = tr["numero_nota"].apply(_normalizar_numero_nota)
        # Nota duplicada no upload (2 linhas) — mantém a última (mais recente
        # na planilha), mesmo critério de "usar o dado mais novo" do resto do app.
        status_diag_por_nota = (
            tr.dropna(subset=["_nota"])
              .drop_duplicates("_nota", keep="last")
              .set_index("_nota")["status_diag"]
              .to_dict()
        )

    diag_raw = nota_norm.map(status_diag_por_nota)

    aberta = df_notas["status_amigavel"].astype(str).str.strip() == "Aberta"
    if "status_final" in df_notas.columns:
        encerrado_final = df_notas["status_final"].astype(str).str.strip().str.lower() == "encerrado"
    else:
        encerrado_final = pd.Series(False, index=df_notas.index)

    resultado = pd.Series(DIAGNOSTICADA_NAO_SE_APLICA, index=df_notas.index)

    diag_raw_norm  = diag_raw.astype(str).str.strip().str.lower()
    eh_diagnosticada = diag_raw_norm == "diagnosticada"
    eh_diagnosticar  = diag_raw_norm == "diagnosticar"
    resultado[eh_diagnosticada] = DIAGNOSTICADA_SIM
    resultado[eh_diagnosticar]  = DIAGNOSTICADA_NAO

    ausente = diag_raw.isna()
    resultado[ausente & aberta & encerrado_final]  = DIAGNOSTICADA_AGUARDA_BAIXA
    resultado[ausente & aberta & ~encerrado_final] = DIAGNOSTICADA_PENDENTE_SANEAMENTO
    # ausente & ~aberta continua Não se Aplica (valor padrão já setado acima)

    return resultado

# endregion


# region ====================== SESSÃO 3: Painel resumo ==========================

def render_resumo_diagnosticada(df: pd.DataFrame) -> None:
    """
    Painel resumo do status Diagnosticada — pedido do Julio: "gráficos de
    quantidades de Notas Diagnosticadas x Não Diagnosticadas". Some
    sozinho se não houver nenhuma nota VP com a coluna calculada (ex.:
    Gerência sem upload de Tratamento ainda, ou só EE carregado).
    """
    if df.empty or "diagnosticada" not in df.columns:
        return

    df_vp = df[df["disciplina_label"] == "VP"] if "disciplina_label" in df.columns else df
    contagem = df_vp["diagnosticada"].value_counts()
    if contagem.empty:
        return

    with st.expander("🔍 Diagnóstico de Notas (Tratamento de Notas)", expanded=False):
        st.caption(
            "Cruzamento da base de Notas com a base de Tratamento de Notas "
            "(upload em Upload de Dados → Tratamento de Notas). "
            + DIAGNOSTICADA_AJUDA
        )
        ordenado = contagem.reindex([o for o in DIAGNOSTICADA_OPCOES if o in contagem.index]).fillna(0)
        st.bar_chart(ordenado)
        cols = st.columns(len(ordenado))
        for col, (rotulo, qtd) in zip(cols, ordenado.items()):
            col.metric(rotulo, f"{int(qtd):,}".replace(",", "."))

# endregion
