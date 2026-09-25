-- Diagnóstico: todos os uploads (ativo + substituído) de disciplina VP,
-- pra ver se sobrou mais de um 'ativo' por gerência (causa mais provável
-- da soma inflada em SP/VP e da falta em FN/FS/LC).
SELECT
    gerencia,
    disciplina,
    status,
    nome_arquivo,
    total_notas,
    enviado_em,
    id
FROM uploads_historico
WHERE disciplina = 'VP'
ORDER BY gerencia, enviado_em DESC;
