# MRS Sentinel — Aba "Inteligência de Falhas EE" (RASF) — Sprint 6→7

Recorte unifilar das falhas de Eletroeletrônica a partir do **RASF**, alinhado
ao **PG-ENG-0088**. Entra como aba **🔌 Inteligência EE** em cada Gerência
(SP / VP, filtrada) e na **Visão Global** (Gerência Geral, consolidada).

## 📦 Arquivos

### NOVOS (copiar para o projeto)
| Arquivo | Destino |
|---|---|
| `core/parser_rasf.py` | `core/` |
| `database/schema_rasf.sql` | `database/` |
| `database/queries_rasf.py` | `database/` |
| `components/inteligencia_ee.py` | `components/` |
| `scripts/verificar_rasf_e2e.py` | `scripts/` |

### MODIFICADOS (substituir — já contêm as edições)
| Arquivo | O que mudou |
|---|---|
| `modules/data_uploader.py` | opção "RASF" na disciplina + pipeline `rasf_ee` |
| `modules/gerencia_sp.py` | +aba 🔌 Inteligência EE (escopo SP) |
| `modules/gerencia_vp.py` | +aba 🔌 Inteligência EE (escopo VP) |
| `modules/gerencia_geral.py` | +aba 🔌 Inteligência EE (Visão Global) |

## 🚀 Passo a passo

1. **Aplique o schema** no Supabase (SQL Editor): cole e rode
   `database/schema_rasf.sql`. Cria a tabela `rasf_ee` + índices.
   Não altera `notas` nem nada existente.

2. **Copie os arquivos** novos e substitua os modificados (tabela acima).

3. **(Recomendado) Valide e2e** localmente, com seu `secrets.toml` preenchido:
   ```bash
   python scripts/verificar_rasf_e2e.py caminho/para/RASF_ELET.xlsx
   # e, quando quiser ingerir de verdade:
   python scripts/verificar_rasf_e2e.py caminho/para/RASF_ELET.xlsx --gravar
   ```

4. **Ou suba pelo app**: menu **📤 Upload** → Disciplina **🔌 RASF** →
   selecione o export → **Confirmar e gravar RASF**.

5. Abra qualquer Gerência ou a Visão Global → aba **🔌 Inteligência EE**.

## 🧩 Os 6 blocos
1. **Painel de Prioridade** — KPIs + Pareto de sintomas (contagem × THP).
2. **Ranking de Reincidência por Ativo** (TPLNR) — qual ativo mais reincide.
3. **Unifilar EE** — pátios; bolha=volume, cor=score, 🟣 anel=crônico, pulso=crítico.
4. **Backlog RCA / Gatilho** — gatilhos sem causa raiz (fila de análise).
5. **Análise 6M** — Ishikawa consolidado (Eng > Manutenção).
6. **Tendência** — evolução mensal de falhas e THP.

## 🔐 Segurança
As credenciais que você colou no chat (incluindo a `service_key`, em ambiente
de produção) devem ser **rotacionadas no Supabase** por precaução. Nenhuma
credencial foi incluída neste pacote.

## ⚠️ Notas técnicas
- **THP** (`Tempo THP 300 (min)`) é a moeda de impacto; o Pareto e o ranking
  usam-no para priorizar por horas de trem parado, não só por contagem.
- **Backlog RCA** = `(Eng) Gatilho ∈ {Falha THP, Falha Segurança, Defeito THP}`
  **e** sem `6M`/`Componente Causador`. Nos seus dados atuais: 623 gatilhos,
  149 no backlog.
- **Reincidência**: usa o campo pré-calculado do RASF (`Reincidência 90 dias
  ativo` = 1.440 no seu export).
- O layout de 77 colunas foi cravado como canônico (confirmado por você).
- A **Base Congelada 2025** pode ser incorporada depois como camada YoY
  (tabela `rasf_baseline`), quando quiser fechar o Sprint 7 de tendência.
