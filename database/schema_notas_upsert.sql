-- ============================================================
-- schema_notas_upsert.sql — Notas por UPSERT (1 linha por nota)
-- ============================================================
-- Contexto: desde schema_upload_periodo.sql, cada upload de Notas (VP/EE)
-- marcava vigente=false nas notas do período e INSERIA tudo de novo — sem
-- nunca apagar. Em 2026-10 a tabela tinha 412.650 linhas pra 46.226
-- vigentes (379 MB de 467 MB do banco, quase no limite de 500 MB do Free).
--
-- A partir daqui o upload faz UPSERT pela chave (gerencia, disciplina,
-- numero_nota): nota existente é atualizada na mesma linha, nota nova é
-- inserida, e nota do período que não veio no arquivo é APAGADA (ver
-- modules/data_uploader.py::_executar_upload_gerencia).
--
-- ⚠️ ANTES DE RODAR: exportar o backup das notas arquivadas
-- (Table Editor → notas → filtro vigente = false → Export CSV).
--
-- Ordem: rodar os blocos 0 → 3 e LIBERAR a versão nova do app só depois
-- do bloco 2 (o upsert precisa da constraint). Bloco 4 (VACUUM) sozinho.


-- ============================================================
-- 0) Diagnóstico (só leitura) — anotar os números antes de apagar
-- ============================================================
SELECT
    count(*)                                                AS linhas_total,
    count(*) FILTER (WHERE vigente)                         AS linhas_vigentes,
    count(DISTINCT (gerencia, disciplina, numero_nota))
        FILTER (WHERE vigente)                              AS notas_unicas_vigentes,
    count(*) FILTER (WHERE numero_nota IS NULL)             AS sem_numero
FROM notas;


-- ============================================================
-- 1) Apaga as notas arquivadas (nenhuma tela lê vigente=false)
-- ============================================================
DELETE FROM notas WHERE vigente = false;


-- ============================================================
-- 2) Dedup das vigentes (fica a linha mais recente de cada nota) +
--    chave única que o upsert usa como alvo do ON CONFLICT
-- ============================================================
DELETE FROM notas n
USING notas mais_nova
WHERE n.gerencia    = mais_nova.gerencia
  AND n.disciplina  = mais_nova.disciplina
  AND n.numero_nota = mais_nova.numero_nota
  AND n.id < mais_nova.id;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'notas_gerencia_disciplina_numero_nota_key'
    ) THEN
        ALTER TABLE notas
            ADD CONSTRAINT notas_gerencia_disciplina_numero_nota_key
            UNIQUE (gerencia, disciplina, numero_nota);
    END IF;
END $$;


-- ============================================================
-- 3) Verificação — linhas_total deve ser = notas_unicas
-- ============================================================
SELECT
    count(*)                                            AS linhas_total,
    count(DISTINCT (gerencia, disciplina, numero_nota)) AS notas_unicas,
    pg_size_pretty(pg_total_relation_size('notas'))     AS tamanho_antes_do_vacuum
FROM notas;


-- ============================================================
-- 4) Devolve o espaço ao disco — rodar SOZINHO no SQL Editor (VACUUM
--    não roda dentro de transação), fora do horário de uso: trava a
--    tabela por alguns minutos.
-- ============================================================
-- VACUUM FULL notas;
