# =============================================================================
# core/parser_prospeccao_campo.py — Prospecção bruta de campo (formato Rev 1)
#
# Fonte: "Prospecção - Sub 78 Rev (1).xlsx" — 4 abas (Dormentes, Lastro,
# Fixação, Trilho), cabeçalho em 2–3 linhas mescladas. O nome de cada
# coluna é montado com ffill nas linhas de cabeçalho e unido com " > "
# (ex.: "totais > qtde inservivel"), depois casado por _norm().
# Km vêm em METROS (174839 → 174,839).
#
# Lição nº 4: a base oficial de DORMENTES é a da Engenharia (R1). A Rev 1 é a
# fonte bruta de campo da mesma prospecção: Lastro e Fixação só existem aqui;
# Dormentes/Trilho da Rev 1 servem para conferência (gravar é opcional).
#
# Funções puras (sem Streamlit):
#   detectar_formato(arquivo) -> 'engenharia' | 'campo_rev1' | 'relatorio_gevia'
#   ler_aba_multicabecalho(arquivo, aba) -> DataFrame com nomes "a > b"
#   ler_prospeccao_campo(arquivo) -> ({'dormentes','lastro','fixacao','trilho'}, avisos)
#   montar_trilho(bruto) -> (DataFrame prospeccao_trilho, avisos)
#   comparar_rev1_r1(rev1, r1) -> dict (achados da seção 6.3)
# =============================================================================

import re
from collections import Counter

import numpy as np
import pandas as pd

from core.parser_prospeccao import _norm, COLS_INT

TRECHO_CHAVE = "Itirapina-Triagem"
SUB_TRECHO = "78"


# region ====================== SESSÃO 1: Leitura genérica =====================

def detectar_formato(arquivo) -> str:
    abas = [_norm(a) for a in pd.ExcelFile(arquivo).sheet_names]
    if {"lastro", "trilho"} <= set(abas) and ("dormentes" in abas or "dormente" in abas) \
            and "fixacao" in abas:
        return "campo_rev1"
    if "export" in abas:
        cab = [_norm(c) for c in pd.read_excel(arquivo, sheet_name=abas.index("export"), nrows=0).columns]
        if "ciclo" in cab:
            return "relatorio_gevia"
    return "engenharia"


def _aba(arquivo, nome: str):
    """Nome real da aba pelo nome normalizado."""
    for a in pd.ExcelFile(arquivo).sheet_names:
        if _norm(a) == _norm(nome):
            return a
    raise ValueError(f"Aba '{nome}' não encontrada.")


def ler_aba_multicabecalho(arquivo, aba: str) -> pd.DataFrame:
    """
    Lê a aba com cabeçalho mesclado. As linhas de cabeçalho são as que vêm
    antes da 1ª linha com Equipamento preenchido no formato 78/xxxxx.
    """
    bruto = pd.read_excel(arquivo, sheet_name=_aba(arquivo, aba), header=None)
    cab0 = [_norm(c) for c in bruto.iloc[0]]
    i_eq = cab0.index("equipamento") if "equipamento" in cab0 else None
    if i_eq is None:
        raise ValueError(f"Aba '{aba}': coluna Equipamento não encontrada.")
    n_cab = next(i for i in range(1, min(len(bruto), 8))
                 if re.match(r"^\d+/\d", str(bruto.iat[i, i_eq]).strip()))
    cab = bruto.iloc[:n_cab].copy()
    cab = cab.ffill(axis=1) if n_cab > 1 else cab
    # ffill horizontal só nas linhas de GRUPO (todas menos a última); a última
    # linha é o nome da coluna e não pode herdar o vizinho.
    nomes = []
    for j in range(bruto.shape[1]):
        partes = []
        for i in range(n_cab):
            v = bruto.iat[i, j] if i == n_cab - 1 else cab.iat[i, j]
            t = _norm(v) if pd.notna(v) else ""
            if t and t != "nan" and (not partes or partes[-1] != t):
                partes.append(t)
        nomes.append(" > ".join(partes) or f"col_{j}")
    corpo = bruto.iloc[n_cab:].copy()
    corpo.columns = nomes
    corpo = corpo[corpo[nomes[i_eq]].notna()].reset_index(drop=True)
    return corpo


def _col(df: pd.DataFrame, *padroes: str):
    """1ª coluna cujo nome normalizado termina com algum dos padrões."""
    for p in padroes:
        for c in df.columns:
            if c == p or c.endswith(" > " + p):
                return c
    return None


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _km(s):
    v = _num(s)
    return np.where(v > 1000, v / 1000, v)


def _base_comum(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "equipamento_siv": df[_col(df, "equipamento")].astype(str).str.strip(),
        "linha": df[_col(df, "linha")].astype(str).str.strip().str.upper(),
        "km_inicio": _km(df[_col(df, "km inicial")]),
        "km_fim": _km(df[_col(df, "km final")]),
        "data_prospeccao": pd.to_datetime(df[_col(df, "data")], errors="coerce").dt.date,
    })
    c_obs, c_resp = _col(df, "observacao"), _col(df, "responsavel")
    out["observacao"] = df[c_obs].replace({"": None}) if c_obs else None
    out["responsavel"] = df[c_resp] if c_resp else None
    return out

# endregion


# region ====================== SESSÃO 2: Abas da Rev 1 ========================

def _dormentes(df: pd.DataFrame) -> pd.DataFrame:
    out = _base_comum(df)
    out["trecho"] = TRECHO_CHAVE
    out["sub"] = SUB_TRECHO
    out["geometria"] = out["equipamento_siv"].str.extract(r"(cv|tg)\s*$", flags=re.I)[0].str.lower()
    esp = _num(df[_col(df, "espacamento medio (cm)")])
    out["espacamento_cm"] = np.where(esp < 5, esp * 100, esp)  # Rev 1 vem em metros
    out["tipo_dormente"] = df[_col(df, "tipo de dormente")]
    out["tipo_fixacao"] = df[_col(df, "tipo de fixacao")]
    out["dormentes_intercalados"] = _num(df[_col(df, "quantidade de dormentes intercalados")])
    out["ext_sem_leitura_m"] = _num(df[_col(df, "extensao sem leitura (m)")])
    malha = [c for c in df.columns if c.startswith("malha de dormentacao")]
    for c in malha:
        n = c.rsplit(" > ", 1)[-1]
        n = 10 if ">=" in n else int(float(n))
        out[f"malha_{n}"] = _num(df[c])
    out["inserv_junta"] = _num(df[_col(df, "junta")])
    out["inserv_guarda"] = _num(df[_col(df, "guarda")])
    out["inserv_solda"] = _num(df[_col(df, "solda")])
    out["total_prospectado"] = _num(df[_col(df, "totais > total de dormentes")])
    out["qtd_inservivel"] = _num(df[_col(df, "totais > qtde inservivel")])
    taxa = _num(df[_col(df, "totais > taxa inservivel")])
    out["taxa_inservivel"] = taxa / 100 if taxa.max(skipna=True) > 1.5 else taxa
    out["qtd_acidentado"] = _num(df[_col(df, "totais acidentados > qtde acidentado")])
    out["status"] = df[_col(df, "status")] if _col(df, "status") else None
    for c in COLS_INT + ["qtd_acidentado", "dormentes_intercalados"]:
        if c in out.columns:
            out[c] = _num(out[c]).fillna(0).round().astype(int)
    return out


LASTRO = {
    "cont. severa": "cont_severa", "cont. moderada": "cont_moderada", "cont. leve": "cont_leve",
    "insuficiente": "insuficiente", "excesso": "excesso", "altura excessiva": "altura_excessiva",
    "bolsao bombeando": "bolsao_bombeando", "bolsao nao bombeando": "bolsao_nao_bombeando",
    "drenagem > inexistente": "drenagem_inexistente", "drenagem > obstruida": "drenagem_obstruida",
}


def _lastro(df: pd.DataFrame) -> pd.DataFrame:
    out = _base_comum(df)
    for padrao, col in LASTRO.items():
        c = _col(df, padrao)
        out[col] = _num(df[c]).fillna(0).astype(int) if c else 0
    medidas = []
    for _, r in df.iterrows():
        m = []
        for k in (1, 2, 3):
            vals = {}
            for campo, nome in (("ombro direito", "ombro_d"), ("ombro esquerdo", "ombro_e"),
                                ("altura direita", "altura_d"), ("altura esquerda", "altura_e")):
                c = _col(df, f"medidas {k} > {campo}")
                v = pd.to_numeric(r[c], errors="coerce") if c else np.nan
                vals[nome] = None if pd.isna(v) else float(v)
            m.append(vals)
        medidas.append(m)
    out["medidas"] = medidas
    return out


def _fixacao(df: pd.DataFrame) -> pd.DataFrame:
    out = _base_comum(df)
    tipos = [c for c in df.columns if c.startswith("tipo > ")]
    faltantes = []
    for _, r in df.iterrows():
        d = {}
        for c in tipos:
            v = pd.to_numeric(r[c], errors="coerce")
            if pd.notna(v) and v > 0:
                d[c.split(" > ", 1)[1]] = int(v)
        faltantes.append(d)
    out["faltantes"] = faltantes
    out["total_faltantes"] = [sum(d.values()) for d in faltantes]
    return out


TRILHO_NUM = {
    "rcf muito severo (und)": "rcf_muito_severo_und",
    "rcf extensao severo (m)": "rcf_severo_m",
    "rcf extensao moderado (m)": "rcf_moderado_m",
    "rcf extensao leve (m)": "rcf_leve_m",
    "corrugacao extensao p1 (m)": "corrugacao_p1_m",
    "corrugacao extensao p2 (m)": "corrugacao_p2_m",
    "corrugacao extensao p3 (m)": "corrugacao_p3_m",
    "corrosao extensao (m) - interno e externo": "corrosao_m",
    "patinado - extensao para retirada (m)": "patinado_m",
    "trilho invertido (m)": "trilho_invertido_m",
    "juntas > bom estado": "junta_bom",
    "juntas > com taco": "junta_taco",
    "juntas > tala quebrada": "junta_tala_quebrada",
    "juntas > desligada": "junta_desligada",
    "juntas > deformada": "junta_deformada",
    "juntas > tala de emergencia/xuxa": "junta_tala_emergencia",
    "juntas > solda conoada p1": "solda_conoada_p1",
    "juntas > solda conoada p2": "solda_conoada_p2",
    "juntas > solda conoada p3": "solda_conoada_p3",
    "juntas > impacto em patim": "impacto_patim",
    "juntas > solda inadequada": "solda_inadequada",
}


def montar_trilho(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Aba Trilho (Rev 1 ou Engenharia) → linhas de prospeccao_trilho."""
    avisos: list[str] = []
    out = _base_comum(df)
    out["fila"] = _num(df[_col(df, "fila")]).astype("Int64")
    out["fabricante"] = df[_col(df, "fabricante")]
    out["ano_mes"] = df[_col(df, "ano/mes")].astype(str)
    out["localizacao"] = df[_col(df, "localizacao")]
    out["extensao_m"] = _num(df[_col(df, "extensao (m)")])
    for padrao, col in TRILHO_NUM.items():
        c = _col(df, padrao)
        out[col] = _num(df[c]).fillna(0) if c else 0
    c_fora = _col(df, "medida trilho 1 > fora")
    out["situacao_desgaste"] = df[c_fora].astype(str).str.strip() if c_fora else None
    medidas, perfis = [], []
    for _, r in df.iterrows():
        m = []
        for k in (1, 2, 3):
            def g(campo):
                c = _col(df, f"medida trilho {k} > {campo}")
                return r[c] if c else None
            perfil = g("perfil")
            if perfil is None or pd.isna(perfil):
                continue
            item = {"perfil": str(perfil).split(".")[0], "classe": g("classe perfil")}
            for campo, nome in (("dv (mm)", "dv"), ("dh/dd i (mm)", "dh_i"), ("dh/dd e (mm)", "dh_e"),
                                ("perda massa", "perda_massa"), ("extensao (m)", "extensao")):
                v = pd.to_numeric(g(campo), errors="coerce")
                item[nome] = None if pd.isna(v) else float(v)
            m.append(item)
        medidas.append(m)
        cont = Counter(f"{(i['classe'] or '')}{i['perfil']}" for i in m)
        perfis.append(cont.most_common(1)[0][0] if cont else None)
    out["medidas"] = medidas
    out["perfil_predominante"] = perfis
    int_cols = [c for c in TRILHO_NUM.values() if c.startswith(("junta", "solda", "impacto", "rcf_muito"))]
    for c in int_cols:
        out[c] = out[c].round().astype(int)
    return out, avisos


def ler_prospeccao_campo(arquivo) -> tuple[dict, list[str]]:
    """As 4 abas da Rev 1 → {'dormentes','lastro','fixacao','trilho'}, avisos."""
    avisos: list[str] = []
    abas = {_norm(a): a for a in pd.ExcelFile(arquivo).sheet_names}
    nome_dorm = "dormentes" if "dormentes" in abas else "dormente"
    out = {
        "dormentes": _dormentes(ler_aba_multicabecalho(arquivo, nome_dorm)),
        "lastro": _lastro(ler_aba_multicabecalho(arquivo, "lastro")),
        "fixacao": _fixacao(ler_aba_multicabecalho(arquivo, "fixacao")),
    }
    out["trilho"], av = montar_trilho(ler_aba_multicabecalho(arquivo, "trilho"))
    avisos += av
    for nome, df in out.items():
        sem_km = df["km_inicio"].isna().sum()
        if sem_km:
            avisos.append(f"{nome}: {sem_km} linha(s) sem km.")
    return out, avisos

# endregion


# region ====================== SESSÃO 3: Rev 1 × R1 ===========================

def comparar_rev1_r1(rev1: pd.DataFrame, r1: pd.DataFrame) -> dict:
    """
    Equipamento+linha só na Rev 1 / só na R1, equipamentos com a mesma linha
    repetida (ex.: 2× LP no 78/300818-302202tg — inversão LP/LD a conferir)
    e dormentes dos pares novos.
    """
    chave = ["equipamento_siv", "linha"]
    a = set(map(tuple, rev1[chave].values))
    b = set(map(tuple, r1[chave].values))
    so_rev1, so_r1 = sorted(a - b), sorted(b - a)
    novos = rev1[rev1[chave].apply(tuple, axis=1).isin(so_rev1)]
    repetidas = sorted(set(
        e for df in (rev1, r1) for e in df[df.duplicated(chave, keep=False)]["equipamento_siv"]))
    return {"so_rev1": so_rev1, "so_r1": so_r1, "linha_repetida": repetidas,
            "dormentes_novos": int(novos["total_prospectado"].sum())}

# endregion
