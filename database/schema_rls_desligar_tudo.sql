-- ============================================================
-- MRS Sentinel — Desliga RLS em TODAS as tabelas do app
-- ============================================================
-- Achado em 2026-08-25: `usuarios` e `uploads_historico` estavam com RLS
-- ligado sem nenhuma policy pra chave anon (a que o app usa) — a linha
-- existia no banco mas toda leitura/escrita da chave anon falhava
-- silenciosamente (SELECT vazio) ou com erro 42501 (INSERT/UPDATE). Em
-- vez de corrigir tabela por tabela cada vez que uma nova bater nessa
-- parede, este script cobre TODAS as tabelas conhecidas do app de uma
-- vez.
--
-- O modelo de segurança deste app é 100% em camada de aplicação (perfil/
-- gerência checados em Python — auth/permissions.py), não em RLS do
-- Postgres — rasf_ee já tinha esse ajuste desde o Sprint 6 (ver
-- database/schema_rasf.sql), as demais tabelas ficaram pra trás. Cada
-- bloco checa se a tabela existe antes de tentar — seguro rodar em
-- qualquer ambiente, mesmo faltando alguma tabela opcional. Idempotente.

DO $$
DECLARE
    tabela TEXT;
BEGIN
    FOREACH tabela IN ARRAY ARRAY[
        'usuarios', 'uploads_historico', 'notas', 'configuracoes',
        'logs_acesso', 'alertas', 'geo_marcos', 'org_unidades',
        'org_codigo_sap', 'usuario_escopo', 'rasf_ee', 'rasf_baseline',
        'snapshots'
    ]
    LOOP
        IF to_regclass('public.' || tabela) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', tabela);
        END IF;
    END LOOP;
END $$;

-- Conferência: lista quais tabelas ainda estão com RLS ligado (deve
-- voltar 0 linhas depois do bloco acima).
SELECT relname AS tabela_ainda_com_rls
FROM pg_class
WHERE relrowsecurity = true
  AND relnamespace = 'public'::regnamespace;
