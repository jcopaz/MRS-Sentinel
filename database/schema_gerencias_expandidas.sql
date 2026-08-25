-- ============================================================
-- MRS Sentinel — Expande CHECK de gerência pra além de SP/VP
-- ============================================================
-- Contexto: usuarios, uploads_historico, alertas e snapshots restringiam
-- "gerencia" a CHECK (gerencia IN ('SP','VP')) via constraint sem nome
-- (Postgres nomeia automaticamente como <tabela>_gerencia_check). Isso
-- bloqueava cadastro de usuário, upload e geração de alerta/snapshot
-- pras novas gerências (Frente Norte, Frente Sul, Rio de Janeiro, Linha
-- do Centro — ver database/schema_organograma.sql pra estrutura
-- completa). Idempotente — seguro rodar de novo.
--
-- ⚠️ Cada bloco usa DO $$ ... IF to_regclass(...) IS NOT NULL ... $$ pra
-- não quebrar se a tabela em questão ainda não existir neste ambiente
-- (ex.: 'snapshots' só existe depois de rodar schema_snapshots.sql) — o
-- SQL Editor do Supabase roda o script colado como UMA transação só, e
-- um único ALTER TABLE numa tabela inexistente cancela TUDO, inclusive
-- os blocos que rodariam certo antes dele.

DO $$ BEGIN
    IF to_regclass('public.usuarios') IS NOT NULL THEN
        ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_gerencia_check;
        ALTER TABLE usuarios ADD CONSTRAINT usuarios_gerencia_check
            CHECK (gerencia IN ('SP', 'VP', 'FN', 'FS', 'RJ', 'LC'));
    END IF;
END $$;

DO $$ BEGIN
    IF to_regclass('public.uploads_historico') IS NOT NULL THEN
        ALTER TABLE uploads_historico DROP CONSTRAINT IF EXISTS uploads_historico_gerencia_check;
        ALTER TABLE uploads_historico ADD CONSTRAINT uploads_historico_gerencia_check
            CHECK (gerencia IN ('SP', 'VP', 'FN', 'FS', 'RJ', 'LC'));
    END IF;
END $$;

DO $$ BEGIN
    IF to_regclass('public.alertas') IS NOT NULL THEN
        ALTER TABLE alertas DROP CONSTRAINT IF EXISTS alertas_gerencia_check;
        ALTER TABLE alertas ADD CONSTRAINT alertas_gerencia_check
            CHECK (gerencia IN ('SP', 'VP', 'FN', 'FS', 'RJ', 'LC'));
    END IF;
END $$;

DO $$ BEGIN
    IF to_regclass('public.snapshots') IS NOT NULL THEN
        ALTER TABLE snapshots DROP CONSTRAINT IF EXISTS snapshots_gerencia_check;
        ALTER TABLE snapshots ADD CONSTRAINT snapshots_gerencia_check
            CHECK (gerencia IN ('SP', 'VP', 'FN', 'FS', 'RJ', 'LC'));
    END IF;
END $$;
