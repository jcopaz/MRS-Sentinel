# scripts/diagnostico_geo.py
# Diagnóstico do Mapa Geográfico: por que as notas não estão georreferenciando.
# Uso (na raiz do projeto, com o venv/creds do app):
#     $env:PYTHONPATH="."
#     python scripts/diagnostico_geo.py SP        # ou VP
#
# Mostra: amostra das colunas que o geo usa, cobertura por enriquecer_geo,
# quebra por geo_fonte e os pares (trecho, origem) que NÃO casaram com a
# referência — para sabermos se é formato dos dados ou marco faltando no KMZ.

import sys
import pandas as pd

from database.queries import get_notas_gerencia
from core import geo as g

GER = (sys.argv[1] if len(sys.argv) > 1 else "SP").upper()

print("=" * 70)
print(f"DIAGNÓSTICO GEO — Gerência {GER}")
print("=" * 70)

frames = []
for disc in ("VP", "EE"):
    try:
        d = get_notas_gerencia(GER, disc)
        if d is not None and not d.empty:
            frames.append(d)
            print(f"[carregado] {disc}: {len(d)} notas")
    except Exception as e:
        print(f"[aviso] {disc}: {e}")

if not frames:
    print("Sem notas para esta gerência.")
    sys.exit(0)

df = pd.concat(frames, ignore_index=True)
cols_geo = [c for c in ("local_instalacao", "ramal", "trecho",
                        "origem", "destino", "km_real") if c in df.columns]
print("\nColunas geo presentes:", cols_geo)
print("Colunas AUSENTES:",
      [c for c in ("local_instalacao", "ramal", "trecho",
                   "origem", "destino", "km_real") if c not in df.columns])

print("\n── Amostra (10 primeiras) das colunas usadas pelo geo ──")
print(df[cols_geo].head(10).to_string())

print("\n── Preenchimento (% não-nulo) ──")
for c in cols_geo:
    pct = 100.0 * df[c].notna().mean()
    print(f"  {c:18s}: {pct:5.1f}% preenchido")

# Referência
lk = g.carregar_ref_geo()
rk = g.carregar_ref_km()
print(f"\nReferência: fino={len(lk['fino'])} patio={len(lk['patio'])} "
      f"ramais_km={len(rk)}")

# Enriquecimento
enr = g.enriquecer_geo(df)
cob = g.cobertura_geo(enr)
print(f"\n>>> COBERTURA: {cob['com_geo']}/{cob['total']} ({cob['pct']}%)")
if "geo_fonte" in enr.columns:
    print("Quebra por geo_fonte:")
    print(enr["geo_fonte"].value_counts(dropna=False).to_string())

# Pares que NÃO casaram
nao = enr[enr["lat"].isna()]
if not nao.empty and "trecho" in nao.columns and "origem" in nao.columns:
    print("\n── Top pares (trecho, origem) NÃO georreferenciados ──")
    top = (nao.groupby(["trecho", "origem"]).size()
              .sort_values(ascending=False).head(15))
    print(top.to_string())
    patio_keys = set(lk["patio"].keys())
    print("\n(esses pares existem na referência de PÁTIO?)")
    for (t, o), _ in top.items():
        tk = (str(t).upper() if pd.notna(t) else None,
              str(o).upper() if pd.notna(o) else None)
        print(f"  {tk} -> {'SIM' if tk in patio_keys else 'não'}")

print("\nFim do diagnóstico.")
