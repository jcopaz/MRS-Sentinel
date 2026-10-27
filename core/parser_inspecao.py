# =============================================================================
# core/parser_inspecao.py — Inspeção de campo do Marco Zero + mídias por link
#
# Entrada:
#   - aba Inspecoes_Campo de MarcoZero_Itirapina_Pederneiras_v2.xlsx (83
#     linhas revisadas pelo coordenador; km_ref → km);
#   - midias_manifest_marco_zero.csv (arquivo; tipo; caminho_relativo;
#     msg_n separados por ";"; url) — fonte da verdade arquivo ↔ registro.
#     Sem manifest, casa a coluna foto_video pelo nome (sem acento, sem
#     maiúsculas, sem extensão: "Midia (59)" ↔ "Mídia (59).jpg").
#
# NÃO faz upload de arquivo: o Sentinel guarda só a referência; o arquivo
# fica no repositório externo (midias_repositorio.base_url).
#
# Exporta:
#   ler_inspecao(arquivo_planilha, arquivo_manifest=None, nomes_disco=None)
#       -> (inspecoes, midias, avisos)
#   nivel_gravidade(texto) -> 0..3
#   montar_link(base_url, caminho_relativo, url) -> str | None
# =============================================================================

import re
from urllib.parse import quote

import numpy as np
import pandas as pd

from core.parser_prospeccao import _norm

TIPO_POR_EXT = {".jpg": "foto", ".jpeg": "foto", ".png": "imagem", ".mp4": "video", ".mov": "video"}


def nivel_gravidade(texto) -> int:
    t = _norm(texto or "")
    if any(k in t for k in ("critic", "urgent")):
        return 3
    if any(k in t for k in ("sever", "forte")):
        return 2
    if "ruim" in t:
        return 1
    return 0


def montar_link(base_url, caminho_relativo, url=None):
    if isinstance(url, str) and url.strip():
        return url.strip()
    if not base_url or not isinstance(caminho_relativo, str) or not caminho_relativo:
        return None
    return base_url.rstrip("/") + "/" + quote(caminho_relativo.replace("\\", "/"))


def _chave_nome(nome: str) -> str:
    """'Mídia (59).jpg' / 'Midia (59)' → 'midia (59)'."""
    t = _norm(re.sub(r"\.[A-Za-z0-9]{2,4}$", "", str(nome).strip()))
    return re.sub(r"\s+", " ", t)


def _separar_nomes(texto) -> list[str]:
    if texto is None or (isinstance(texto, float) and np.isnan(texto)):
        return []
    t = str(texto).strip()
    if _norm(t) in ("nao", "", "-", "—"):
        return []
    partes = re.split(r",|;|\n|\s+e\s+", t)
    return [p.strip() for p in partes if p.strip()]


def _data_hora(texto, ano: int):
    t = str(texto or "").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m %H:%M"):
        try:
            d = pd.to_datetime(t if "%Y" in fmt else f"{t}", format=fmt)
            return d.replace(year=ano) if "%Y" not in fmt else d
        except (ValueError, TypeError):
            continue
    return pd.NaT


def ler_inspecao(planilha, manifest=None, nomes_disco: list[str] | None = None):
    xl = pd.ExcelFile(planilha)
    aba = next((a for a in xl.sheet_names if _norm(a) == "inspecoes_campo"), xl.sheet_names[0])
    d = pd.read_excel(xl, sheet_name=aba)
    d.columns = [_norm(c) for c in d.columns]
    avisos: list[str] = []
    d = d[d["msg_n"].notna()].copy()

    base = pd.to_datetime(d["data_base"].iloc[0]) if "data_base" in d and len(d) else pd.Timestamp.now()
    km = pd.to_numeric(d.get("km_ref"), errors="coerce")
    insp = pd.DataFrame({
        "msg_n": pd.to_numeric(d["msg_n"], errors="coerce").astype("Int64"),
        "data_hora": [_data_hora(v, base.year) for v in d.get("data_hora", [])],
        "responsavel": d.get("autor"),
        "km": km,
        "km_fim": pd.to_numeric(d.get("km_fim"), errors="coerce"),
        "km_fonte": np.where(d.get("km_fonte", "").astype(str).str.startswith("estimado"), "estimado",
                             np.where(km.isna(), "sem km", "informado")),
        "linha": d.get("linha"),
        "sb": d.get("sb"),
        "equipamento_siv": d.get("equipamento_siv"),
        "local": d.get("local"),
        "tema": d.get("tema"),
        "descricao": d.get("descricao"),
        "gravidade": d.get("gravidade"),
        "acao_sugerida": d.get("acao_sugerida"),
        "ponto_critico": d.get("ponto_critico"),
        "top10": d.get("top10"),
        "taxa_inserv_equip": pd.to_numeric(d.get("taxa_inserv_equip"), errors="coerce"),
        "defeitos_rumo_janela": pd.to_numeric(d.get("defeitos_rumo_janela"), errors="coerce").astype("Int64"),
        "restricoes_janela": d.get("restricoes_janela"),
        "fonte": d.get("fonte"),
    })
    for c in ("local", "tema", "descricao", "gravidade", "acao_sugerida", "ponto_critico", "top10",
              "restricoes_janela", "sb", "equipamento_siv", "linha"):
        insp[c] = insp[c].map(lambda v: None if pd.isna(v) or str(v).strip() in ("", "—", "n/i") else str(v))
    insp["data_hora"] = pd.to_datetime(insp["data_hora"])

    # ── Mídias ───────────────────────────────────────────────────────────────
    if manifest is not None:
        m = pd.read_csv(manifest, sep=None, engine="python", encoding="utf-8-sig", dtype=str)
        m.columns = [_norm(c) for c in m.columns]
        sem_ref = m[m["msg_n"].isna() | (m["msg_n"].str.strip() == "")]
        for a in sem_ref["arquivo"]:
            avisos.append(f"Mídia sem registro de inspeção: {a}.")
        m = m.dropna(subset=["msg_n"]).copy()
        m["msg_n"] = m["msg_n"].str.split(";")
        m = m.explode("msg_n")
        m["msg_n"] = pd.to_numeric(m["msg_n"].str.strip(), errors="coerce").astype("Int64")
        midias = m[["msg_n", "arquivo", "tipo", "caminho_relativo", "url"]].copy()
        n_arquivos = m["arquivo"].nunique() + len(sem_ref)
        avisos.append(f"{n_arquivos} arquivo(s) no manifest · {len(midias)} vínculo(s) mídia × registro.")
    else:
        disco = {_chave_nome(n): n for n in (nomes_disco or [])}
        linhas = []
        for msg, texto in zip(insp["msg_n"], d.get("foto_video", [])):
            for nome in _separar_nomes(texto):
                arq = disco.get(_chave_nome(nome))
                if arq is None:
                    avisos.append(f"Msg {msg}: '{nome}' sem arquivo correspondente.")
                    continue
                ext = re.search(r"\.[A-Za-z0-9]+$", arq)
                linhas.append({"msg_n": msg, "arquivo": arq,
                               "tipo": TIPO_POR_EXT.get(ext.group(0).lower() if ext else "", "foto"),
                               "caminho_relativo": arq, "url": None})
        midias = pd.DataFrame(linhas, columns=["msg_n", "arquivo", "tipo", "caminho_relativo", "url"])
        usados = set(midias["arquivo"])
        for n in nomes_disco or []:
            if n not in usados:
                avisos.append(f"Arquivo sem referência na planilha: {n}.")

    orfas = set(midias["msg_n"].dropna()) - set(insp["msg_n"].dropna())
    if orfas:
        avisos.append(f"Mídias apontando para msg inexistente: {sorted(orfas)}.")
    return insp.reset_index(drop=True), midias.reset_index(drop=True), avisos
