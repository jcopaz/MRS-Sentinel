# MRS Sentinel — Pacote Consolidado (Sprints 5 + 6 + 7)

Este ZIP é o **app completo** com os três sprints já integrados. É só implantar.

## O que está incluído

### Sprint 5 — Alertas (fechamento)
- Export **PDF** de alertas (reportlab, fallback HTML) — `core/notificacoes.py`
- **RBAC granular** `can_manage_alertas` (admin/assistente/usuário) — `auth/permissions.py`, `modules/alertas.py`
- e2e `scripts/verificar_alertas_e2e.py`

### Sprint 6 — Geografia Real 🗺️
- `data/geo_marcos.csv` (368 segmentos do KMZ) + `core/geo.py` (`enriquecer_geo`)
- Mapa `components/mapa_geografico.py` (Folium → Plotly → st.map)
- KM real no Unifilar (`components/unifilar.py`) e mapa na aba EE (`components/inteligencia_ee.py`)
- `RAMAIS_KMZ` (11 ramais, nomes provisórios) — `core/glossarios.py`
- `database/schema_geo.sql` (opcional) + `database/queries_geo.py`
- e2e `scripts/verificar_geo_e2e.py`

### Sprint 7 — RASF YoY (Base Congelada 2025)
- Tabela `rasf_baseline` — `database/schema_rasf_baseline.sql`
- Parser/queries — `core/parser_rasf_baseline.py`, `database/queries_baseline.py`
- Bloco **Comparativo Anual (YoY)** na aba EE — `components/inteligencia_ee.py`
- Pipeline de upload "RASF — Base Congelada 2025" — `modules/data_uploader.py`
- Wiring nas 3 telas de gerência — `modules/gerencia_sp.py`, `gerencia_vp.py`, `gerencia_geral.py`
- e2e `scripts/verificar_baseline_yoy_e2e.py`

> Obs.: `components/inteligencia_ee.py` deste pacote já contém **mapa (S6) + YoY (S7)** juntos.

## Deploy

1. **Segredos:** copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml`
   e preencha (o `secrets.toml` real **não** vai neste pacote, por segurança).
2. `pip install -r requirements.txt`
3. **Supabase** — rode os SQL na ordem:
   - `database/schema.sql`, `schema_rasf.sql`, `schema_sprint5.sql` (se ainda não rodou)
   - `database/schema_rasf_baseline.sql` (Sprint 7)
   - `database/schema_geo.sql` (Sprint 6 — **opcional**; o CSV embarcado já basta)
4. `streamlit run app.py`

## Validação (headless, sem Supabase)

```
PYTHONPATH=. python3 scripts/verificar_alertas_e2e.py       # S5 ✅
PYTHONPATH=. python3 scripts/verificar_geo_e2e.py           # S6 ✅
PYTHONPATH=. python3 scripts/verificar_baseline_yoy_e2e.py  # S7 ✅
```

## Pendências (Julio)
- Confirmar nomes oficiais dos **11 ramais** em `RAMAIS_KMZ` (rótulos provisórios do KMZ).
- **Rotacionar a chave Supabase** (vazou em zips anteriores).
- Fornecer o `Base_de_Falhas_Congelado_2025_EE.xlsx` real p/ validação final do YoY.
- 6 ramais do glossário sem marcos no KMZ (BPD, JIT, RCB, RCF, RPB, RWL) — sem geo.
