# =============================================================================
# core/parser_relatorio_velocidade.py — "Relatório de Velocidade" (SRM Rumo)
#
# PDF exportado do SRM (srm.rumolog.com → speed_report) por rota, ex.:
# "JUNDIAI-TRIAGEM PAULISTA.pdf". Seções reconhecidas pelo CABEÇALHO de
# cada tabela (pdfplumber), não pela página — tabelas continuam entre
# páginas repetindo o cabeçalho:
#
#   Velocidade Máxima Trem Tipo  → tipo 'vma'          (1 linha por trem-tipo)
#   Velocidade Máxima por AMV    → ignorada (sem km, só pares de AMV)
#   Velocidade Máxima Restrição A→ tipo 'restricao_a'  (permanentes c/ motivo)
#   Velocidade Máxima Restrição B→ tipo 'restricao_b'  (programadas do dia)
#   Linhas Secundárias / Estações→ tipo 'obs_estacao'
#   Observação em trecho         → tipo 'obs_trecho'
#
# A tabela de trem-tipo sai cortada na margem direita do PDF (última coluna
# vem como "Tr\nCom", "A" etc.) — nomes casados por prefixo; o que ficar
# ambíguo é descartado.
#
# Exporta:
#   ler_relatorio_velocidade(arquivo) -> (rota, data_exportacao, DataFrame)
#   categoria_motivo(motivo) -> str
# =============================================================================

import re
from datetime import datetime

import pandas as pd

TREM_TIPOS = ("TQ Carreg", "TQ Vazio", "Trem Misto", "Trem Comum",
              "Fibria", "Helper", "Auto de Linha")

COLUNAS = ["tipo", "sub", "sb", "linha", "bitola", "trem_tipo", "km_de", "km_ate",
           "vel", "motivo", "condicao", "responsavel", "inicio", "fim",
           "estacao", "trecho_desc", "observacao"]


# region ====================== SESSÃO 1: Helpers ==============================

def _limpa(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _num(v):
    t = _limpa(v).replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _data(v):
    t = _limpa(v)
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            pass
    return None


def _trem_tipo(nome: str) -> str | None:
    """Casa nome (possivelmente cortado na margem) com TREM_TIPOS."""
    toks = _limpa(nome).split()
    if not toks:
        return None
    cands = []
    for k in TREM_TIPOS:
        kt = k.split()
        if len(toks) <= len(kt) and all(a.lower().startswith(b.lower()) for a, b in zip(kt, toks)):
            cands.append(k)
    return cands[0] if len(cands) == 1 else None


def categoria_motivo(motivo: str) -> str:
    """Agrupa o motivo da restrição em 4 famílias para o dashboard."""
    m = _limpa(motivo).upper()
    if any(k in m for k in ("OAE", "PONTE", "CONTRATRILHO")):
        return "OAE"
    if "ANTT" in m or "PERIMETRO URBANO" in m or "INVAS" in m or m[4:6] == "PN":
        return "Externa (ANTT/PN/urbano)"
    if any(k in m for k in ("DESNIVEL", "DESALINH", "DESBITOL", "NIVELAMENTO", "TORÇÃO",
                            "TORCAO", "LASTRO", "PLATAFORMA", "FLAMBADA", "ESTABILIZA",
                            "DORMENT", "JUNTA", "TRILHO", "JACAR", "AMV", "DRENAGEM",
                            "PLASSER", "NOSSOS DEFEITOS", "MODERNIZA", "MANUTEN",
                            "DANIFICADA")):
        return "Via permanente"
    return "Outras"

# endregion


# region ====================== SESSÃO 2: Leitura ==============================

def _cab(tabela) -> list[str]:
    return [_limpa(c) for c in (tabela[0] if tabela else [])]


def ler_relatorio_velocidade(arquivo) -> tuple[str, datetime | None, pd.DataFrame]:
    import pdfplumber  # import tardio: só quem faz upload de PDF precisa

    rota, exportado = "", None
    regs: list[dict] = []
    layout_vma = None  # [(idx_coluna, bitola, trem_tipo)] — reaproveitado entre páginas
    secao = None       # última seção vista, p/ tabelas que continuam sem cabeçalho

    with pdfplumber.open(arquivo) as pdf:
        texto1 = pdf.pages[0].extract_text() or ""
        m = re.search(r"Rota:\s*(.+)", texto1)
        rota = _limpa(m.group(1)) if m else ""
        m = re.search(r"Exporta\S*:\s*([\d/]+\s+[\d:]+)", texto1)
        exportado = _data(m.group(1)) if m else None

        for page in pdf.pages:
            for t in page.extract_tables():
                if not t:
                    continue
                cab = _cab(t)
                corpo = t
                if "Bitola Larga" in cab or "Bitola Estreita" in cab:
                    nomes = [_limpa(c) for c in t[1]]
                    i_larga = cab.index("Bitola Larga") if "Bitola Larga" in cab else len(cab)
                    i_estr = cab.index("Bitola Estreita") if "Bitola Estreita" in cab else len(cab)
                    layout_vma = []
                    for i, n in enumerate(nomes):
                        if i < 5:
                            continue
                        bitola = "Larga" if i >= i_larga else ("Estreita" if i >= i_estr else None)
                        tt = _trem_tipo(n)
                        if bitola and tt:
                            layout_vma.append((i, bitola, tt))
                    secao, corpo = "vma", t[2:]
                elif cab[:4] == ["Seq.", "De", "Até", "km/h"]:
                    secao = "amv"
                    continue
                elif cab[:3] == ["Seq.", "SB", "Sub."] and "Motivo" in cab:
                    secao, corpo = "restricao_a", t[1:]
                elif cab[:3] == ["Seq.", "SB", "Sub."] and "Condição" in cab:
                    secao, corpo = "restricao_b", t[1:]
                elif cab[:2] == ["Estação", "Vel."]:
                    secao, corpo = "linha_secundaria", t[1:]
                elif cab == ["Trecho", "Observações"]:
                    secao, corpo = "obs_trecho", t[1:]
                elif cab == ["Estação", "Observações"]:
                    secao, corpo = "obs_patio", t[1:]

                for r in corpo:
                    r = [_limpa(c) for c in r]
                    if not any(r):
                        continue
                    if secao == "vma" and layout_vma and len(r) >= 5 and r[0].isdigit():
                        de, ate = _num(r[2]), _num(r[3])
                        for i, bitola, tt in layout_vma:
                            v = _num(r[i]) if i < len(r) else None
                            if v is not None and de is not None and ate is not None:
                                regs.append(dict(tipo="vma", sub=r[1], linha=r[4], bitola=bitola,
                                                 trem_tipo=tt, km_de=de, km_ate=ate, vel=v))
                    elif secao == "restricao_a" and len(r) >= 9 and r[0].isdigit():
                        regs.append(dict(tipo="restricao_a", sb=r[1], sub=r[2], linha=r[3],
                                         bitola=r[4], km_de=_num(r[5]), km_ate=_num(r[6]),
                                         vel=_num(r[7]), motivo=r[8]))
                    elif secao == "restricao_b" and len(r) >= 10 and r[0].isdigit():
                        regs.append(dict(tipo="restricao_b", sb=r[1], sub=r[2], linha=r[3],
                                         km_de=_num(r[4]), km_ate=_num(r[5]), condicao=r[6],
                                         responsavel=r[7], inicio=_data(r[8]), fim=_data(r[9])))
                    elif secao == "linha_secundaria" and len(r) >= 3:
                        regs.append(dict(tipo="obs_estacao", estacao=r[0], vel=_num(r[1]),
                                         observacao=r[2]))
                    elif secao == "obs_trecho" and len(r) >= 2 and r[1]:
                        m = re.match(r"(\d+)\s*-\s*(.*)", r[0])
                        regs.append(dict(tipo="obs_trecho", sub=m.group(1) if m else None,
                                         trecho_desc=m.group(2) if m else r[0], observacao=r[1]))
                    elif secao == "obs_patio" and len(r) >= 2 and r[1]:
                        regs.append(dict(tipo="obs_estacao", estacao=r[0], observacao=r[1]))

    df = pd.DataFrame(regs, columns=COLUNAS)
    if not len(df):
        raise ValueError("Nenhuma tabela do Relatório de Velocidade reconhecida no PDF.")
    df = df.drop_duplicates().reset_index(drop=True)
    return rota, exportado, df

# endregion
