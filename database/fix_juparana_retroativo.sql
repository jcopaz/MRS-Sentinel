-- ============================================================
-- MRS Sentinel — Correção retroativa: notas de Barão de Juparanã (FBJ)
-- ============================================================
-- Contexto: a coordenação Barão de Juparanã (código de trabalho sempre
-- "V.RJ.FBJ", nunca mudou) migrou de Rio de Janeiro pra Linha do Centro,
-- mas até 2026-08-25 o parser só traduzia código legado no nível da
-- Gerência inteira (MG->LC) — não pegava esse caso de coordenação isolada
-- com Gerência dona diferente. Corrigido em core/glossarios.py
-- (COORDENACAO_REALOCADA) e core/parser.py/parser_rasf.py — mas isso só
-- vale pra uploads NOVOS a partir de agora. Este script corrige o que já
-- está gravado no banco com a gerência errada.
--
-- Rode a Etapa 1 (preview) primeiro pra conferir o tamanho do impacto
-- antes de rodar a Etapa 2 (UPDATE de verdade).

-- ============================================================
-- Etapa 1 — Preview (só leitura, não muda nada)
-- ============================================================
SELECT 'notas' AS tabela, gerencia, count(*) AS qtd
FROM notas
WHERE centro_trab ILIKE '%.FBJ'
GROUP BY gerencia
UNION ALL
SELECT 'rasf_ee' AS tabela, gerencia, count(*) AS qtd
FROM rasf_ee
WHERE centro_trab ILIKE '%.FBJ'
GROUP BY gerencia
ORDER BY tabela, gerencia;

-- Confira o resultado: linhas com gerencia='RJ' são as que a Etapa 2 vai
-- corrigir pra 'LC'. Se já aparecer só 'LC', não tem nada pra corrigir.

-- ============================================================
-- Etapa 2 — Correção de verdade (só rode depois de conferir a Etapa 1)
-- ============================================================
UPDATE notas
SET gerencia = 'LC'
WHERE centro_trab ILIKE '%.FBJ'
  AND gerencia <> 'LC';

UPDATE rasf_ee
SET gerencia = 'LC'
WHERE centro_trab ILIKE '%.FBJ'
  AND gerencia <> 'LC';

-- ============================================================
-- Etapa 3 — Limpar o cache do app pra ele buscar o dado corrigido
-- ============================================================
-- Depois de rodar a Etapa 2, no Painel Admin > Configurações >
-- "🔄 Limpar Cache de Dados" (ou espere o TTL de 5 min expirar sozinho) —
-- senão o app continua mostrando os números antigos até o cache vencer.
