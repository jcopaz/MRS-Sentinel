# MRS Sentinel — Aba "Inteligência de Falhas EE" (RASF) — Sprint 6→7

Recorte unifilar das falhas de Eletroeletrônica a partir do **RASF**, alinhado
ao **PG-ENG-0088**. Entra como aba **🔌 Inteligência EE** em cada Gerência
(SP / VP, filtrada) e na **Visão Global** (Gerência Geral, consolidada).

## 📦 Arquivos

| Arquivo | Papel |
|---|---|
| `core/parser_rasf.py` | Parser do export RASF → DataFrame canônico; regras de causa raiz efetiva e status de consenso |
| `database/schema_rasf.sql` | Schema da tabela `rasf_ee` + índices + migrações incrementais (`ALTER TABLE ADD COLUMN IF NOT EXISTS`) |
| `database/queries_rasf.py` | Leitura/cache do Supabase para a aba |
| `components/inteligencia_ee.py` | A aba em si (filtros, blocos, gráficos) |
| `components/relatorio_ee.py` | Gerador de relatório HTML autônomo (botão "🧾 Gerar relatório" na aba) |
| `scripts/verificar_rasf_e2e.py` | Validação e2e do parser fora do Streamlit |
| `modules/data_uploader.py` | Upload do export RASF → pipeline `rasf_ee` |
| `modules/gerencia_sp.py` / `gerencia_vp.py` / `gerencia_geral.py` | Ponto de entrada da aba 🔌 Inteligência EE por escopo |

## 🚀 Passo a passo (upload de RASF)

1. **Aplique o schema** no Supabase (SQL Editor) sempre que `database/schema_rasf.sql`
   mudar — é idempotente (`CREATE TABLE IF NOT EXISTS` + `ADD COLUMN IF NOT EXISTS`),
   seguro rodar de novo. **Pular esse passo faz o próximo upload falhar** com
   `PGRST204 — Could not find the '<coluna>' column of 'rasf_ee' in the schema cache`.
2. **(Recomendado) Valide e2e** localmente, com seu `secrets.toml` preenchido:
   ```bash
   python scripts/verificar_rasf_e2e.py caminho/para/RASF_ELET.xlsx
   # e, quando quiser ingerir de verdade:
   python scripts/verificar_rasf_e2e.py caminho/para/RASF_ELET.xlsx --gravar
   ```
3. **Ou suba pelo app**: menu **📤 Upload** → Disciplina **🔌 RASF** →
   selecione o export → **Confirmar e gravar RASF**.
4. Abra qualquer Gerência ou a Visão Global → aba **🔌 Inteligência EE**.

## 🧩 Estrutura atual da aba (16/07/2026)

Todos os filtros vivem dentro de um único expander recolhível **🔍 Filtros**:
Sistema · Reincidência (90d) · Gerador THP (coluna Z) · Período (data da nota)
· Descrição Tipo Solicitação · Origem da Atividade (efetiva) · Consenso Origem
de Atividade · Coordenação (Centro de Trabalho, filtra a lista de Pátio em
cascata) · Pátio · Grupo do Ativo.

O seletor **🚂 Trecho** (dentro do bloco Unifilar) filtra **todos** os blocos
abaixo dele, não só o próprio gráfico — "🌐 Todos os trechos" mostra a malha
inteira.

1. **📄 Exportar Relatório** — gera um `.html` autônomo do recorte filtrado
   (ver `components/relatorio_ee.py`).
2. **📌 Cards Resumo** — ativo com mais falhas (+ tipo predominante), ativo
   com maior THP, ativo mais reincidente, sintoma mais crítico por THP,
   origem de atividade mais frequente.
3. **🗺️ Unifilar EE** — ativos por trecho; bolha=qtd de falhas, cor=score,
   🟣 anel=reincidente (≥3 em 90d), pulso=top 10% score. Inclui a leitura
   rápida (Ativos/Densidade/Ativo mais crítico) **acima** do gráfico.
4. **📊 Pareto de Sintomas** — Falhas × THP por sintoma, barras com % de
   representatividade sobre o total do recorte.
5. **🏗️ Obras × Manutenção** — Falhas × THP por Origem da Atividade
   **efetiva** (ver regra de causa raiz abaixo).
6. **🔥 Mapa de Calor** — Pátio × Origem da Atividade efetiva × qtd de falhas.
7. **♻️ Ranking de Reincidência por Ativo** — agrupado por **TPLNR**
   (`local_instalacao`, chave única); a coluna K (`local_instalacao_desc`)
   é usada só como rótulo de exibição, nunca como chave de agrupamento —
   ela não é garantidamente única por ativo físico. Traz também a coluna
   "Classificação" (moda da origem efetiva por ativo).

## ⚖️ Regra de causa raiz/responsabilidade (pedido do Julio, 16/07/2026)

"Descrição da Origem da Atividade" (coluna P) é a referência, **mas**
"Origem de Atividade Correta" (coluna AW) sobrepõe quando foi preenchida em
reunião com valor diferente — a responsabilidade foi corrigida. O resultado
vai em `origem_atividade_efetiva` (persistida) / `origem_efetiva` (recalculada
client-side em `_preparar_origem()`, funciona mesmo em bases antigas ainda
não reprocessadas). **Toda** classificação por origem na aba usa essa coluna,
nunca a bruta.

"Consenso Origem de Atividade" (coluna AV): Sim → **"Sim"** (processo
encerrado), Não → **"Não"** (pode caber revisão), vazio → **"Pendente"**.

## 🔐 Segurança
As credenciais que você colou no chat (incluindo a `service_key`, em ambiente
de produção) devem ser **rotacionadas no Supabase** por precaução. Nenhuma
credencial foi incluída neste pacote.

## ⚠️ Notas técnicas
- **THP** (`Tempo THP 300 (min)`) é a moeda de impacto; Pareto, Obras×Manutenção
  e Ranking usam-no para priorizar por horas de trem parado, não só por contagem.
- **Reincidência**: usa o campo pré-calculado do RASF (`Reincidência 90 dias ativo`).
- O layout de 77 colunas do export é canônico (confirmado pelo Julio).
- Qualquer coluna nova adicionada a `core.parser_rasf.COLUNAS_RASF_EE` precisa
  do `ALTER TABLE` correspondente em `database/schema_rasf.sql` rodado no
  Supabase **antes** do próximo upload de RASF — ver passo 1 acima.
