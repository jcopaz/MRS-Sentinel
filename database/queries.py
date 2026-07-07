# database/queries.py
# Queries reutilizáveis para acesso ao Supabase — Sprint 1 + Sprint 3
# Atualizado: Sprint 3 — Visualizações por Gerência
#
# Padrão: funções retornam pd.DataFrame ou None em caso de erro
# Sempre aplica normalizar_coluna_ramal() após o load (ASP→VSU etc.)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database.client import get_supabase
from core.glossarios import normalizar_coluna_ramal

# region ====================== SESSÃO 1: Queries base (Sprint 1) ==============

def _upload_ids_ativos(gerencia: str, disciplina: str | None = None) -> list[str]:
    """
    Retorna os IDs de uploads com status 'ativo' para a gerencia
    (e disciplina, se informada). Base da leitura anti-duplicação.
    """
    try:
        supabase = get_supabase()
        q = (
            supabase.table("uploads_historico")
            .select("id")
            .eq("gerencia", gerencia)
            .eq("status", "ativo")
        )
        if disciplina:
            q = q.eq("disciplina", disciplina)
        resp = q.execute()
        return [r["id"] for r in (resp.data or [])]
    except Exception:
        return []


def get_notas_gerencia(gerencia: str, disciplina: str | None = None) -> pd.DataFrame:
    """
    Busca todas as notas ativas de uma gerência.

    Filtros: gerencia obrigatório, disciplina opcional ('VP' ou 'EE').
    Sempre normaliza a coluna 'ramal' (ASP→VSU, etc.) após o load.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None (ambas)

    Returns:
        pd.DataFrame com todas as notas, ou DataFrame vazio em caso de erro.
    """
    try:
        supabase = get_supabase()

        # ⭐ ANTI-DUPLICAÇÃO: lê apenas as notas do(s) upload(s) ATIVO(s).
        # Um novo upload marca o anterior como 'substituido' mas NÃO apaga as
        # notas antigas — por isso filtramos pelos upload_id ainda ativos.
        upload_ids = _upload_ids_ativos(gerencia, disciplina)
        if not upload_ids:
            return pd.DataFrame()

        query = (
            supabase.table("notas")
            .select("*, uploads_historico(enviado_em, usuario_id, nome_arquivo)")
            .eq("gerencia", gerencia)
            .in_("upload_id", upload_ids)
        )
        if disciplina:
            query = query.eq("disciplina", disciplina)

        response = query.execute()

        if not response.data:
            return pd.DataFrame()

        df = pd.DataFrame(response.data)

        # ⭐ ESSENCIAL: normaliza siglas de ramal logo após o load
        df = normalizar_coluna_ramal(df, "ramal")

        # Converte colunas de data
        for col in ["data_nota", "data_encerramento", "data_planejada", "criado_em"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        # Garante numérico em colunas sensíveis
        for col in ["score", "km_real", "km_fim_real", "lead_time_dias", "peso_prio"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    except Exception as e:
        st.error(f"❌ Erro ao buscar notas ({gerencia}/{disciplina}): {e}")
        return pd.DataFrame()


def get_uploads_historico(gerencia: str | None = None) -> pd.DataFrame:
    """
    Retorna o histórico de uploads de uma gerência (ou todos, se gerencia=None).
    Usado no card de 'última atualização' e na auditoria.

    Args:
        gerencia: 'SP', 'VP' ou None

    Returns:
        pd.DataFrame com histórico de uploads
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("uploads_historico")
            .select("*, usuarios(nome, email)")
            .order("enviado_em", desc=True)
        )
        if gerencia:
            query = query.eq("gerencia", gerencia)

        response = query.execute()
        df = pd.DataFrame(response.data or [])

        if not df.empty and "enviado_em" in df.columns:
            df["enviado_em"] = pd.to_datetime(df["enviado_em"], errors="coerce")

        return df

    except Exception as e:
        st.error(f"❌ Erro ao buscar histórico de uploads: {e}")
        return pd.DataFrame()


def get_ultima_atualizacao(gerencia: str | None = None, disciplina: str | None = None) -> str:
    """
    Retorna a data/hora do último upload ativo para o card de 'última atualização'.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None

    Returns:
        String formatada (ex: '05/07/2026 às 14:32') ou 'Sem dados'
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("uploads_historico")
            .select("enviado_em")
            .eq("status", "ativo")
            .order("enviado_em", desc=True)
            .limit(1)
        )
        if gerencia:
            query = query.eq("gerencia", gerencia)
        if disciplina:
            query = query.eq("disciplina", disciplina)

        response = query.execute()

        if response.data:
            dt = pd.to_datetime(response.data[0]["enviado_em"])
            return dt.strftime("%d/%m/%Y às %H:%M")

        return "Sem dados"

    except Exception:
        return "Sem dados"

# endregion


# region ====================== SESSÃO 2: Queries Sprint 3 =====================

@st.cache_data(ttl=300)  # Cache de 5 minutos — dados não mudam frequentemente
def get_notas_cached(gerencia: str, disciplina: str | None = None) -> pd.DataFrame:
    """
    Versão cacheada de get_notas_gerencia para uso nas telas de visualização.
    TTL de 5 minutos evita múltiplos round-trips ao banco em recargas normais.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None

    Returns:
        pd.DataFrame com as notas (cacheado)
    """
    return get_notas_gerencia(gerencia, disciplina)


def get_kpis_gerencia(gerencia: str, disciplina: str | None = None) -> dict:
    """
    Retorna KPIs aggregados diretamente do banco (query leve).

    KPIs calculados:
      - total_notas
      - notas_abertas
      - score_medio
      - lead_time_medio
      - ramal_mais_critico (sigla)
      - notas_muito_alta

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None

    Returns:
        dict com os KPIs, ou dict vazio em caso de erro
    """
    try:
        df = get_notas_cached(gerencia, disciplina)

        if df.empty:
            return {}

        kpis = {
            "total_notas":     len(df),
            "notas_abertas":   int((df.get("status_usuario", pd.Series()).str.upper() == "ABER").sum()),
            "score_medio":     round(df["score"].dropna().mean(), 2) if "score" in df.columns else 0.0,
            "lead_time_medio": round(df["lead_time_dias"].dropna().mean(), 1) if "lead_time_dias" in df.columns else 0.0,
            "notas_muito_alta": int(
                df["prioridade"].str.contains("1-Muito alta", na=False).sum()
            ) if "prioridade" in df.columns else 0,
        }

        # Ramal mais crítico — maior score total
        if "ramal" in df.columns and "score" in df.columns:
            por_ramal = df.groupby("ramal")["score"].sum().dropna()
            if not por_ramal.empty:
                kpis["ramal_mais_critico"] = por_ramal.idxmax()

        return kpis

    except Exception as e:
        st.error(f"❌ Erro ao calcular KPIs ({gerencia}/{disciplina}): {e}")
        return {}


def get_notas_por_periodo(
    gerencia: str,
    disciplina: str | None = None,
    dias: int = 90,
) -> pd.DataFrame:
    """
    Retorna notas criadas nos últimos N dias — otimiza a série temporal
    para não trazer o histórico completo.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None
        dias:       janela de tempo em dias (padrão 90)

    Returns:
        pd.DataFrame filtrado por data_nota >= (hoje - dias)
    """
    df = get_notas_cached(gerencia, disciplina)

    if df.empty or "data_nota" not in df.columns:
        return df

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=dias)
    df_periodo = df[df["data_nota"] >= cutoff].copy()

    return df_periodo


def get_ranking_hotspots(
    gerencia: str,
    disciplina: str | None = None,
    top_n: int = 20,
) -> pd.DataFrame:
    """
    Retorna os top N trechos mais críticos por score total.

    Args:
        gerencia:   'SP' ou 'VP'
        disciplina: 'VP', 'EE' ou None
        top_n:      número de registros a retornar

    Returns:
        pd.DataFrame com colunas: ramal, origem, score_total, n_notas, lead_medio
    """
    df = get_notas_cached(gerencia, disciplina)

    if df.empty:
        return pd.DataFrame()

    group_cols = [c for c in ["ramal", "origem"] if c in df.columns]

    if not group_cols:
        return pd.DataFrame()

    agg_dict = {}
    if "score" in df.columns:
        agg_dict["score"] = "sum"
    if "lead_time_dias" in df.columns:
        agg_dict["lead_time_dias"] = "mean"
    agg_dict["numero_nota"] = "count"

    ranking = (
        df.groupby(group_cols)
        .agg(agg_dict)
        .reset_index()
        .rename(columns={
            "score":          "score_total",
            "lead_time_dias": "lead_medio",
            "numero_nota":    "n_notas",
        })
        .sort_values("score_total", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )

    return ranking

# endregion


# region ====================== SESSÃO 3: Invalidação de cache =================

def invalidar_cache_notas() -> None:
    """
    Força limpeza do cache de notas.
    Deve ser chamada após um novo upload para garantir dados frescos.

    Uso:
        from database.queries import invalidar_cache_notas
        invalidar_cache_notas()  # chamado em data_uploader.py após upload
    """
    get_notas_cached.clear()
    st.toast("🔄 Cache de notas atualizado.", icon="✅")

# endregion

# region ====================== SESSÃO 4: Autenticação (Sprint 1) =============

def get_usuario_by_email(email: str) -> dict | None:
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("usuarios")
            .select("*")
            .eq("email", email.strip().lower())
            .eq("ativo", True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        st.error(f"❌ Erro ao buscar usuário: {e}")
        return None


def atualizar_ultimo_login(user_id: str) -> None:
    try:
        from datetime import datetime
        supabase = get_supabase()
        supabase.table("usuarios").update({
            "ultimo_login": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
    except Exception:
        pass


def log_acesso(
    usuario_id: str | None,
    acao: str,
    detalhes: dict | None = None,
    ip: str | None = None,
) -> None:
    try:
        from datetime import datetime
        supabase = get_supabase()
        supabase.table("logs_acesso").insert({
            "usuario_id": usuario_id,
            "acao":       acao,
            "detalhes":   detalhes or {},
            "ip":         ip,
            "quando":     datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass
def get_ultima_atualizacao_info() -> dict:
    """Retorna dict com dados do último upload — usado pelo home.py."""
    try:
        supabase = get_supabase()
        resp = (
            supabase.table("uploads_historico")
            .select("enviado_em, gerencia, disciplina, nome_arquivo")
            .eq("status", "ativo")
            .order("enviado_em", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            dt = pd.to_datetime(row.get("enviado_em"))
            row["enviado_em_fmt"] = dt.strftime("%d/%m/%Y às %H:%M") if dt else "—"
            return row
        return {}
    except Exception:
        return {}
# endregion


# region ====================== SESSÃO 5: Alertas (Sprint 5) ===================

@st.cache_data(ttl=300)
def get_alertas(gerencia: str, disciplina: str | None = None) -> pd.DataFrame:
    """
    Busca os alertas persistidos de uma gerência (opcionalmente por disciplina).
    Retorna DataFrame ordenável (severidade + score) ou vazio em caso de erro.
    """
    try:
        supabase = get_supabase()
        query = supabase.table("alertas").select("*").eq("gerencia", gerencia)
        if disciplina:
            query = query.eq("disciplina", disciplina)
        resp = query.order("criado_em", desc=True).execute()
        return pd.DataFrame(resp.data or [])
    except Exception as e:
        st.error(f"❌ Erro ao buscar alertas ({gerencia}): {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def contar_alertas_novos(gerencia: str | None = None) -> int:
    """
    Conta alertas com status='novo' (para o badge da sidebar).
    Se gerencia=None, conta em todas. Falha graciosamente para 0.
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("alertas")
            .select("id", count="exact")
            .eq("status", "novo")
        )
        if gerencia:
            query = query.eq("gerencia", gerencia)
        resp = query.execute()
        return int(resp.count or 0)
    except Exception:
        return 0


def marcar_alerta_status(alerta_id, status: str, usuario_id: str | None = None) -> bool:
    """
    Atualiza o status de um alerta ('novo' | 'visto' | 'resolvido').
    Registra quem/quando resolveu. Retorna True em sucesso.
    """
    if status not in ("novo", "visto", "resolvido"):
        return False
    try:
        supabase = get_supabase()
        dados = {"status": status, "atualizado_em": datetime.utcnow().isoformat()}
        if status == "resolvido":
            dados["resolvido_por"] = usuario_id
            dados["resolvido_em"]  = datetime.utcnow().isoformat()
        supabase.table("alertas").update(dados).eq("id", alerta_id).execute()
        log_acesso(usuario_id, f"alerta_{status}", {"alerta_id": str(alerta_id)})
        return True
    except Exception as e:
        st.error(f"❌ Erro ao atualizar alerta: {e}")
        return False

# endregion