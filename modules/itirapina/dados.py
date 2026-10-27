# =============================================================================
# modules/itirapina/dados.py — Carga dos dados de uma base do trecho
#
# carregar_base(base_id) devolve um dict com todos os DataFrames da base
# (tipados) + a lista de avisos (tabela ausente etc.). Com base_id=None
# (schema_itirapina.sql sem as tabelas de base) cai no modo legado:
# prospecção e relatório de velocidade sem filtro de base, demais vazios.
# =============================================================================

import pandas as pd

from core.analise_trecho import preencher_sb
from core.analise_velocidade import normalizar_relatorio
from core.parser_prospeccao import enriquecer_prospeccao
from database.queries_prospeccao import (
    TRECHO_ITIRAPINA, TabelaAusente, get_prospeccao, get_relatorio_velocidade,
)
from database.queries_trecho import (
    get_bases, get_por_base, get_transit_time, get_referencia, get_repositorios_midia,
)

TRECHO_ROTULO = "Itirapina–Pederneiras"
MSG_SQL = ("⚙️ Tabela `itp_{}` ausente — rode `database/schema_itirapina.sql` "
           "no SQL Editor do Supabase.")


def _ler(func, tabela: str, avisos: list) -> pd.DataFrame:
    try:
        return func()
    except TabelaAusente:
        avisos.append(MSG_SQL.format(tabela))
    except Exception as e:  # rede/proxy: não derruba a tela
        avisos.append(f"❌ Erro ao ler `{tabela}`: {e}")
    return pd.DataFrame()


def carregar_bases() -> tuple[pd.DataFrame, str | None]:
    avisos: list = []
    df = _ler(lambda: get_bases(TRECHO_ITIRAPINA), "trecho_bases", avisos)
    return df, (avisos[0] if avisos else None)


def _tipar_defeitos(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return d
    for c in ("km", "tamanho", "extensao", "peso", "latitude", "longitude",
              "vel_max_classe_kmh", "dias_ativo", "numero_viagem"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("data_entrada", "data_baixa"):
        if c in d.columns:
            d[c] = pd.to_datetime(d[c], errors="coerce")
    return d


def _tipar(d: pd.DataFrame, numericas: tuple) -> pd.DataFrame:
    for c in numericas:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def carregar_base(base_id: int | None) -> dict:
    avisos: list = []
    if base_id is None:
        dorm = _ler(lambda: get_prospeccao(TRECHO_ITIRAPINA), "prospeccao_dormentes", avisos)
        rel = _ler(get_relatorio_velocidade, "relatorio_velocidade", avisos)
        vazio = pd.DataFrame()
        dados = dict(defeitos=vazio, trilho=vazio, lastro=vazio, fixacao=vazio,
                     inspecao=vazio, midias=vazio)
    else:
        dorm = _ler(lambda: get_prospeccao(TRECHO_ITIRAPINA, base_id), "prospeccao_dormentes", avisos)
        rel = _ler(lambda: get_relatorio_velocidade(base_id), "relatorio_velocidade", avisos)
        dados = {
            "defeitos": _tipar_defeitos(_ler(lambda: get_por_base("defeitos_via", base_id),
                                             "defeitos_via", avisos)),
            "trilho": _tipar(_ler(lambda: get_por_base("prospeccao_trilho", base_id),
                                  "prospeccao_trilho", avisos),
                             ("km_inicio", "km_fim", "extensao_m")),
            "lastro": _tipar(_ler(lambda: get_por_base("prospeccao_lastro", base_id),
                                  "prospeccao_lastro", avisos), ("km_inicio", "km_fim")),
            "fixacao": _tipar(_ler(lambda: get_por_base("prospeccao_fixacao", base_id),
                                   "prospeccao_fixacao", avisos), ("km_inicio", "km_fim")),
            "inspecao": _tipar(_ler(lambda: get_por_base("inspecoes_campo", base_id),
                                    "inspecoes_campo", avisos), ("km", "km_fim", "taxa_inserv_equip")),
            "midias": _ler(lambda: get_por_base(
                "inspecao_midias", base_id,
                "id,inspecao_id,msg_n,arquivo,tipo,caminho_relativo,url,repositorio_id,miniatura"),
                "inspecao_midias", avisos),
        }
    # SB vazia (Rev 1 não tem SB) → pela faixa de km das SBs da Rumo
    fx = _ler(lambda: get_referencia("sb_faixas", TRECHO_ITIRAPINA), "sb_faixas", [])
    dorm = preencher_sb(dorm, "km_inicio", "km_fim", fx)
    for k, km in (("defeitos", "km"), ("inspecao", "km")):
        if k in dados:
            dados[k] = preencher_sb(dados[k], km, faixas=fx)
    dados["sb_faixas"] = fx
    dados["dormentes"] = enriquecer_prospeccao(dorm) if not dorm.empty else dorm
    dados["rel"] = normalizar_relatorio(rel)
    dados["transit"] = _carregar_transit(avisos)
    dados["avisos"] = list(dict.fromkeys(avisos))
    return dados


def _carregar_transit(avisos: list) -> pd.DataFrame:
    t = _ler(get_transit_time, "transit_time", avisos)
    if t.empty:
        return t
    for c in ("partida", "chegada", "dt_encer"):
        t[c] = pd.to_datetime(t[c], errors="coerce")
    for c in ("horas", "horas_programadas"):
        t[c] = pd.to_numeric(t[c], errors="coerce")
    t["valido"] = t["valido"].fillna(False).astype(bool)
    t["outlier"] = t["outlier"].fillna(False).astype(bool)
    return t


def carregar_referencias() -> dict:
    avisos: list = []
    refs = {
        "estacoes": _ler(lambda: get_referencia("trecho_estacoes", TRECHO_ITIRAPINA),
                         "trecho_estacoes", avisos),
        "limites": _ler(lambda: get_referencia("limites_geometria"), "limites_geometria", avisos),
        "pontos": _ler(lambda: get_referencia("trecho_pontos_criticos", TRECHO_ITIRAPINA),
                       "trecho_pontos_criticos", avisos),
        "sb_faixas": _ler(lambda: get_referencia("sb_faixas", TRECHO_ITIRAPINA), "sb_faixas", avisos),
        "repositorios": _ler(lambda: get_repositorios_midia(TRECHO_ITIRAPINA),
                             "midias_repositorio", avisos),
    }
    for k in ("estacoes", "pontos"):
        refs[k] = _tipar(refs[k], ("km_inicio", "km_fim"))
    refs["limites"] = _tipar(refs["limites"], ("vel_min_kmh", "vel_max_kmh", "limite_mm"))
    refs["avisos"] = avisos
    return refs
