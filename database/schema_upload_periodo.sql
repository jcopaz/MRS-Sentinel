-- ============================================================
-- schema_upload_periodo.sql — Upload de Notas (VP/EE) por período
-- ============================================================
-- Contexto: até aqui, cada upload de Notas (VP/EE) substituía a base
-- INTEIRA da Gerência+Disciplina (1 upload 'ativo' por vez, controlado por
-- uploads_historico.status + idx_uploads_historico_ativo_unico). Pedido do
-- Julio: se o arquivo enviado cobre só um pedaço do tempo (ex.: só 2026,
-- ou só setembro/2026), substituir só as notas ABERTAS (data_nota) naquele
-- período — o resto do histórico fica intocado.
--
-- Decisão de escopo: só Notas (VP/EE, tabela `notas`). RASF (rasf_ee),
-- RASF_BASE (já fora de uso) e Tratamento (notas_tratamento) continuam
-- exatamente como estão — substituição da base inteira por upload.
--
-- A trava de duplicidade, que hoje é "1 upload ativo por Gerência+
-- Disciplina" (nível de UPLOAD), passa a ser por LINHA em `notas`
-- (`vigente`). uploads_historico.status deixa de ser a trava de leitura
-- para VP/EE — vira só auditoria (fica 'ativo' pra sempre depois de
-- criado, já que um upload novo não substitui mais um upload antigo
-- inteiro, só o período que ele cobre).
--
-- Idempotente — seguro rodar mais de uma vez.

-- ============================================================
-- 1) notas.vigente — trava de duplicidade por linha
-- ============================================================
ALTER TABLE notas ADD COLUMN IF NOT EXISTS vigente BOOLEAN NOT NULL DEFAULT true;

-- ⚠️ BACKFILL OBRIGATÓRIO — rodar JUNTO com o ALTER acima, antes de
-- liberar a versão nova do app. Sem isso, o DEFAULT true acima marca TODAS
-- as notas como vigentes, inclusive as que já tinham sido "substituídas"
-- por um upload mais recente (status <> 'ativo') — voltariam a aparecer
-- duplicadas nos dashboards.
UPDATE notas n
SET vigente = false
FROM uploads_historico u
WHERE n.upload_id = u.id
  AND u.status <> 'ativo'
  AND n.vigente = true;

CREATE INDEX IF NOT EXISTS idx_notas_vigente ON notas(gerencia, disciplina, vigente);


-- ============================================================
-- 2) uploads_historico.periodo_ini/periodo_fim — auditoria do período
--    coberto por cada upload de VP/EE (NULL em uploads antigos e em
--    RASF/RASF_BASE/TRATAMENTO — não usado pra travar leitura em lugar
--    nenhum, só exibição/histórico).
-- ============================================================
ALTER TABLE uploads_historico ADD COLUMN IF NOT EXISTS periodo_ini DATE;
ALTER TABLE uploads_historico ADD COLUMN IF NOT EXISTS periodo_fim DATE;


-- ============================================================
-- 3) Índice único "1 upload ativo por Gerência+Disciplina" — relaxa só
--    pra VP/EE (onde agora pode e deve haver vários uploads 'ativo'
--    simultâneos, um por período já enviado). RASF/RASF_BASE/TRATAMENTO
--    continuam com a proteção de sempre, sem nenhuma mudança de
--    comportamento pra eles.
-- ============================================================
DROP INDEX IF EXISTS idx_uploads_historico_ativo_unico;
CREATE UNIQUE INDEX IF NOT EXISTS idx_uploads_historico_ativo_unico
    ON uploads_historico (gerencia, disciplina)
    WHERE status = 'ativo' AND disciplina NOT IN ('VP', 'EE');

-- Pendência CONHECIDA e aceita por ora (não bloqueia esta versão): sem o
-- índice acima cobrindo VP/EE, dois uploads simultâneos pro MESMO período
-- (duplo-clique, ou dois admins subindo ao mesmo tempo) não são mais
-- barrados pelo banco como eram antes. Uma trava de verdade exigiria mover
-- "arquivar período + inserir lote" pra dentro de uma função Postgres (RPC)
-- com pg_advisory_xact_lock, já que cada chamada do cliente Supabase hoje
-- é uma transação isolada — mais trabalho (seria a 1ª RPC do projeto) pra
-- um risco do mesmo tamanho do que já era aceito no modelo antigo. Fica
-- registrado aqui pra retomar se um dia fizer falta na prática.


-- ============================================================
-- Verificação
-- ============================================================
SELECT
    (SELECT count(*) FROM notas WHERE vigente = false) AS notas_arquivadas_no_backfill,
    (SELECT count(*) FROM notas WHERE vigente = true)  AS notas_vigentes_apos_backfill;
