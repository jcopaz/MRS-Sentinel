-- ============================================================
-- MRS Sentinel — Índice único: só 1 upload 'ativo' por Gerência+Disciplina
-- ============================================================
-- Contexto: o upload faz "arquivar o anterior (UPDATE) → checar se
-- zerou (SELECT count) → inserir o novo ('ativo')" — um check-then-act
-- sem trava. Dois uploads simultâneos pra mesma Gerência+Disciplina (ex.:
-- duplo-clique, ou dois admins subindo a mesma base ao mesmo tempo) podem
-- os dois passar pela checagem antes de qualquer um inserir o próprio
-- registro, resultando em 2 uploads 'ativo' ao mesmo tempo (mesmo bug de
-- fundo que motivou a blindagem de leitura em database/queries.py e a
-- limpeza manual em modules/admin_panel.py — mas aqui ataca a causa, não
-- só o sintoma). Com este índice, o segundo INSERT falha na hora (em vez
-- de silenciosamente duplicar), e data_uploader.py mostra erro claro.
-- Idempotente — seguro rodar de novo.

CREATE UNIQUE INDEX IF NOT EXISTS idx_uploads_historico_ativo_unico
    ON uploads_historico (gerencia, disciplina)
    WHERE status = 'ativo';
