#!/usr/bin/env python3
# scripts/verificar_geo_e2e.py — Sprint 6 (Geografia Real)
#
# Teste headless: valida a camada geo (core.geo), o enriquecimento de um df de
# falhas com lat/lon/km_real e a agregação do mapa (components.mapa_geografico),
# sem depender de servidor Streamlit nem de Supabase.
#
# Uso:  PYTHONPATH=<raiz_do_app> python3 scripts/verificar_geo_e2e.py

import sys
import types


# ── Stub mínimo do Streamlit (decoradores de cache como identidade) ───────────
def _instalar_stub_streamlit():
    st = types.ModuleType("streamlit")

    def _ident(*a, **k):
        def deco(fn):
            try:
                fn.clear = lambda: None
            except Exception:
                pass
            return fn
        if a and callable(a[0]):
            return deco(a[0])
        return deco

    st.cache_data = _ident
    st.cache_resource = _ident
    st.fragment = _ident
    for nome in ("info", "warning", "caption", "markdown", "map", "dataframe",
                 "plotly_chart", "write", "error", "success"):
        setattr(st, nome, lambda *a, **k: None)

    from contextlib import contextmanager

    @contextmanager
    def _ctx(*a, **k):
        yield

    st.expander = _ctx
    st.container = _ctx
    sys.modules["streamlit"] = st


def main() -> int:
    _instalar_stub_streamlit()

    import pandas as pd
    from core.geo import (carregar_ref_geo, enriquecer_geo, geo_lookup,
                          cobertura_geo, carregar_ref_km, carregar_tracado,
                          geo_por_km)

    falhas = []

    # 1) Referência carregada -------------------------------------------------
    lk = carregar_ref_geo()
    n = lk.get("n", 0)
    print(f"[1] Referência geo carregada: {n} segmentos, "
          f"{len(lk['patio'])} pátios.")
    if n < 100:
        falhas.append("Referência geo vazia ou insuficiente (data/geo_marcos.csv).")

    # 1B) Referência por KM + traçado -----------------------------------------
    rk = carregar_ref_km()
    tr = carregar_tracado()
    n_km = sum(len(v["km"]) for v in rk.values())
    print(f"[1B] Referência por KM: {len(rk)} ramais / {n_km} marcos · "
          f"traçado: {len(tr)} polilinhas.")
    if len(rk) < 10 or n_km < 500:
        falhas.append("Referência por KM (data/geo_km.csv) vazia/insuficiente.")
    if len(tr) < 10:
        falhas.append("Traçado (data/geo_tracado.csv) vazio/insuficiente.")

    # 1C) geo_por_km: posição exata + interpolação ----------------------------
    ramal_km = next(iter(rk))
    kms = rk[ramal_km]["km"]
    km_meio = float((kms.min() + kms.max()) / 2)
    lat_k, lon_k, fonte_k = geo_por_km(ramal_km, km_meio, ref_km=rk)
    print(f"[1C] geo_por_km({ramal_km}, {km_meio}) -> "
          f"({lat_k},{lon_k}) fonte={fonte_k}")
    if fonte_k != "km" or pd.isna(lat_k):
        falhas.append("geo_por_km não resolveu posição exata por KM.")
    # Fora da faixa não deve extrapolar:
    _, _, fonte_fora = geo_por_km(ramal_km, float(kms.max()) + 999, ref_km=rk)
    if fonte_fora is not None:
        falhas.append("geo_por_km extrapolou fora da faixa (não deveria).")

    # 2) Lookup fino (segmento) e fallback pátio ------------------------------
    # Pega uma chave real da referência.
    chave = next(iter(lk["fino"]))
    tplnr = f"MF-{chave[0]}-{chave[1]}_{chave[2]}-L000001-AMV999N"
    lat, lon, km, fonte = geo_lookup(tplnr=tplnr, lookups=lk)
    print(f"[2] geo_lookup segmento {tplnr} -> ({lat},{lon}) km={km} fonte={fonte}")
    if fonte != "segmento" or pd.isna(lat):
        falhas.append("geo_lookup não resolveu no nível segmento.")

    # Fallback pátio: destino inexistente força cair de segmento p/ pátio.
    tplnr_p = f"MF-{chave[0]}-{chave[1]}_ZZZ-L000001-AMV999N"
    _, _, _, fonte_p = geo_lookup(tplnr=tplnr_p, lookups=lk)
    print(f"[3] geo_lookup fallback pátio -> fonte={fonte_p}")
    if fonte_p not in ("patio", "segmento"):
        falhas.append("Fallback de pátio não funcionou.")

    # 3) enriquecer_geo em df misto (com e sem cobertura) ---------------------
    df = pd.DataFrame({
        "local_instalacao": [
            tplnr,
            f"MF-{chave[0]}-{chave[1]}_{chave[2]}-SINALIZ-XYZ",
            "MF-ZZZ-QQQ_WWW-L000001-NADA",   # ramal inexistente
        ],
        "ramal": [chave[0], chave[0], "ZZZ"],
        "origem": [chave[1], chave[1], "QQQ"],
        "thp_min": [60, 120, 30],
        "score_ee": [0.9, 0.4, 0.2],
    })
    dfe = enriquecer_geo(df)
    for c in ("lat", "lon", "km_real", "geo_fonte"):
        if c not in dfe.columns:
            falhas.append(f"enriquecer_geo não criou coluna '{c}'.")
    cob = cobertura_geo(dfe)
    print(f"[4] enriquecer_geo cobertura: {cob}")
    if cob["com_geo"] < 2:
        falhas.append("Cobertura geo do df de teste abaixo do esperado (>=2).")
    if cob["com_geo"] == cob["total"]:
        falhas.append("Ramal inexistente deveria ficar SEM geo (esperado 1 NaN).")

    # km_real preexistente não deve ser sobrescrito -------------------------
    df2 = df.copy()
    df2["km_real"] = [123.4, None, None]
    dfe2 = enriquecer_geo(df2)
    if abs(float(dfe2["km_real"].iloc[0]) - 123.4) > 1e-6:
        falhas.append("enriquecer_geo sobrescreveu km_real preexistente.")
    print(f"[5] km_real preexistente preservado: {dfe2['km_real'].iloc[0]}")

    # 3B) Notas VP: km_real + ramal -> posição EXATA (geo_fonte='km') ---------
    df_vp = pd.DataFrame({
        "numero_nota": [1001, 1002, 1003],
        "ramal": [ramal_km, ramal_km, "ZZZ"],
        "km_real": [km_meio, float(kms.min()), 50.0],
        "familia_defeito": ["Trilho", "Solda", "AMV"],
        "score": [0.8, 0.3, 0.5],
    })
    dfe_vp = enriquecer_geo(df_vp)
    n_exato = int((dfe_vp["geo_fonte"] == "km").sum())
    print(f"[5B] notas VP posicionadas por KM exato: {n_exato}/3 "
          f"(fontes={list(dfe_vp['geo_fonte'])})")
    if n_exato < 2:
        falhas.append("enriquecer_geo não posicionou notas VP por KM exato.")
    # Ponto exato deve bater com geo_por_km:
    if pd.notna(dfe_vp["lat"].iloc[0]) and abs(dfe_vp["lat"].iloc[0] - lat_k) > 1e-6:
        falhas.append("lat da nota VP não bate com geo_por_km.")

    # 4) Agregação do mapa + paleta -----------------------------------------
    from components.mapa_geografico import _agregar_pontos, _cor_score
    g = _agregar_pontos(dfe)
    print(f"[6] _agregar_pontos -> {len(g)} pontos, "
          f"colunas={list(g.columns)}")
    if g.empty:
        falhas.append("Agregação do mapa não gerou pontos.")
    for req in ("lat", "lon", "volume", "score", "thp_h", "cronico"):
        if req not in g.columns:
            falhas.append(f"Agregação do mapa sem coluna '{req}'.")
    c_lo, c_hi = _cor_score(0.1), _cor_score(0.95)
    print(f"[7] paleta score: 0.1->{c_lo}  0.95->{c_hi}")
    if not (c_lo.startswith('#') and c_hi.startswith('#')):
        falhas.append("Paleta de cor inválida.")

    # 5) render_mapa_geografico não deve lançar (streamlit stubbado) ---------
    from components.mapa_geografico import render_mapa_geografico
    try:
        # modo segmento (EE, sem KM)
        render_mapa_geografico(dfe, escopo="TEST_SEG",
                               granularidade="segmento", ja_enriquecido=True)
        # modo nota (VP, KM exato)
        render_mapa_geografico(dfe_vp, escopo="TEST_NOTA",
                               granularidade="nota", ja_enriquecido=True)
        # auto
        render_mapa_geografico(dfe_vp, escopo="TEST_AUTO",
                               granularidade="auto", ja_enriquecido=True)
        print("[8] render_mapa_geografico executou (segmento/nota/auto) sem exceção.")
    except Exception as e:
        falhas.append(f"render_mapa_geografico lançou exceção: {e}")

    print("\n" + ("=" * 56))
    if falhas:
        print(f"❌ FALHOU ({len(falhas)}):")
        for f in falhas:
            print("   -", f)
        return 1
    print("✅ Sprint 6 (Geografia Real) — e2e PASSOU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
