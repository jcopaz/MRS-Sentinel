# =============================================================================
# core/eventos_restricao.py — Histórico de retirada de restrição entre bases
#
# Cada Relatório de Velocidade novo vira uma base. A diferença entre as
# restrições A da base anterior e da atual gera eventos:
#   'retirada' (existia e saiu) · 'nova' (não existia) · 'alterada' (mudou a
#   velocidade). Funções puras.
# Chave de casamento: linha + km_de (± 20 m) + código do motivo — a "Seq" da
# Rumo muda entre relatórios. Grupo: códigos 503/185/502 (perímetro urbano,
# PN) = 'ANTT/terceiros'; o resto = 'via' (lição nº 11).
# =============================================================================

import re

import numpy as np
import pandas as pd

from core.analise_trecho import restricoes_trecho

TOL_KM = 0.020
CODIGOS_TERCEIROS = {"503", "185", "502"}
# código do motivo → texto legível (One Page)
MOTIVO_LEGIVEL = {
    "509": "via desnivelada", "092": "via desnivelada", "204": "torção",
    "050": "junta com taco", "038": "lastro contaminado",
    "503": "perímetro urbano", "185": "perímetro urbano", "502": "PN sem sinalização",
}


def codigo_motivo(m) -> str | None:
    g = re.match(r"\s*(\d{3})\b", str(m or ""))
    return g.group(1) if g else None


def grupo_evento(codigo) -> str:
    return "ANTT/terceiros" if codigo in CODIGOS_TERCEIROS else "via"


def motivo_legivel(m) -> str:
    c = codigo_motivo(m)
    if c in MOTIVO_LEGIVEL:
        return MOTIVO_LEGIVEL[c]
    s = re.sub(r"^\s*\d{3}\s*", "", str(m or ""))
    s = re.sub(r"^(ANTT|VG VIA|VIA)\s*-\s*", "", s, flags=re.I)
    return s.strip().lower() or "—"


def _prep(rel_ou_rA: pd.DataFrame) -> pd.DataFrame:
    if rel_ou_rA is None or rel_ou_rA.empty:
        return pd.DataFrame(columns=["linha", "a", "b", "vel", "motivo", "codigo", "sb", "seq"])
    r = rel_ou_rA if "a" in rel_ou_rA.columns else restricoes_trecho(rel_ou_rA)
    r = r.copy()
    r["codigo"] = r["motivo"].map(codigo_motivo)
    if "seq" not in r.columns:
        r["seq"] = None
    if "sb" not in r.columns:
        r["sb"] = None
    return r.reset_index(drop=True)


def comparar_restricoes(anterior: pd.DataFrame, atual: pd.DataFrame, tol: float = TOL_KM) -> pd.DataFrame:
    """anterior/atual: relatório normalizado ou saída de restricoes_trecho."""
    a, b = _prep(anterior), _prep(atual)
    usados_b = np.zeros(len(b), bool)
    eventos = []

    def ev(tipo, r, vel_antes, vel_depois):
        return {"evento": tipo, "seq_rumo": None if pd.isna(r.seq) else r.seq, "sb": r.sb, "linha": r.linha,
                "km_de": float(r.a), "km_ate": float(r.b), "vel_antes": vel_antes, "vel_depois": vel_depois,
                "codigo": r.codigo, "motivo": r.motivo, "grupo": grupo_evento(r.codigo)}

    for r in a.itertuples():
        cand = b[(~usados_b) & (b["linha"] == r.linha) & ((b["a"] - r.a).abs() <= tol + 1e-9)
                 & (b["codigo"].fillna("") == (r.codigo or ""))]
        if cand.empty:
            eventos.append(ev("retirada", r, float(r.vel), None))
            continue
        j = (cand["a"] - r.a).abs().idxmin()
        usados_b[j] = True
        if abs(float(b.at[j, "vel"]) - float(r.vel)) > 1e-6:
            eventos.append(ev("alterada", next(b.loc[[j]].itertuples()), float(r.vel), float(b.at[j, "vel"])))
    for j in np.where(~usados_b)[0]:
        r = next(b.iloc[[j]].itertuples())
        eventos.append(ev("nova", r, None, float(r.vel)))
    cols = ["evento", "seq_rumo", "sb", "linha", "km_de", "km_ate", "vel_antes", "vel_depois", "codigo",
            "motivo", "grupo"]
    return pd.DataFrame(eventos, columns=cols)


def resumo_eventos(eventos: pd.DataFrame) -> dict:
    if eventos is None or eventos.empty:
        return {"via_retiradas": 0, "terceiros_retiradas": 0, "novas_via": 0, "alteradas": 0}
    e = eventos
    return {
        "via_retiradas": int(((e["evento"] == "retirada") & (e["grupo"] == "via")).sum()),
        "terceiros_retiradas": int(((e["evento"] == "retirada") & (e["grupo"] != "via")).sum()),
        "novas_via": int(((e["evento"] == "nova") & (e["grupo"] == "via")).sum()),
        "alteradas": int((e["evento"] == "alterada").sum()),
    }
