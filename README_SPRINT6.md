# Sprint 6 — Geografia Real da Malha 🗺️

Substitui o KM fictício/sequencial pela **geografia real** dos marcos de KM da
MRS, extraídos do KMZ oficial `Marcos_KM_Malha_MRS` (2.298 marcos). Habilita
mapa geográfico interativo e KM real no Unifilar.

## O que entra

| Arquivo | Papel |
|---|---|
| `data/geo_marcos.csv` | **Referência embarcada** — 368 segmentos `(trecho,origem,destino)` → lat/lon/km, agregados do KMZ. Fonte primária, funciona offline. |
| `core/geo.py` | Loader cacheado + `enriquecer_geo(df)` (adiciona `lat`,`lon`,`km_real`,`geo_fonte`) + `geo_lookup` (cascata segmento→pátio) + `cobertura_geo`. |
| `components/mapa_geografico.py` | Bloco de mapa. **Folium** (principal) → **Plotly** open-street-map (fallback, sem token) → `st.map` (último recurso). Cor=score, tamanho=volume, anel roxo=crônico. |
| `components/inteligencia_ee.py` | Aba EE: enriquece o df com geo e adiciona o mapa na **Visão Macro**. *Já inclui o YoY do Sprint 7 — este arquivo supersede o do Sprint 7.* |
| `components/unifilar.py` | Unifilar VP/EE: injeta **KM real** do KMZ (eixo híbrido — real onde há marco, sequencial no resto). |
| `core/glossarios.py` | + `RAMAIS_KMZ`: rótulos **provisórios** dos 11 ramais que existem no KMZ e ainda não têm nome oficial. |
| `database/schema_geo.sql` | Tabela `geo_marcos` (opcional) + seed dos 368 segmentos, p/ quem preferir servir a referência pelo Supabase. |
| `database/queries_geo.py` | `get_geo_marcos_cached()` — leitura da tabela (alternativa ao CSV). |
| `scripts/verificar_geo_e2e.py` | Teste headless (referência, lookup, enriquecimento, agregação, render). |
| `requirements.txt` | + `folium`, `streamlit-folium`. |

## Instalação

1. `pip install -r requirements.txt` (folium + streamlit-folium).
2. Copie os arquivos para o repositório (respeitando as pastas).
3. **Opcional** (referência via banco): rode `database/schema_geo.sql` no Supabase.
4. Nada mais é obrigatório — o CSV embarcado já alimenta tudo.

## Validação

```
PYTHONPATH=<raiz> python3 scripts/verificar_geo_e2e.py   # ✅ e2e
```

## Pendências para o Julio ⚠️

- **11 ramais sem nome oficial** (`RAMAIS_KMZ` em `core/glossarios.py`): ACL,
  AJC, LC1, LC2, LFA, LRJ, LSM, P12, RGI, VBA, VPB. Rótulos atuais são
  provisórios (derivados do campo *Deno* do KMZ). Confirmar denominação oficial.
- **6 ramais do glossário sem marcos no KMZ** (BPD, JIT, RCB, RCF, RPB, RWL):
  ficam sem geo (fallback sequencial) até virem no KMZ.
- Dispersão dos marcos por pátio: mediana ~3 km — um ponto por pátio é honesto.

## Ordem de aplicação com os outros sprints

Aplicar **depois** do Sprint 7 (RASF YoY): o `inteligencia_ee.py` daqui já
contém o bloco YoY, então este arquivo é o que deve ficar no repo.
