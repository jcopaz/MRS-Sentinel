-- ============================================================
-- MRS Sentinel — Desliga RLS na tabela usuarios
-- ============================================================
-- Achado em 2026-08-25 depurando login travado: a tabela `usuarios`
-- estava com Row Level Security ativado (provavelmente padrão do
-- Supabase pra tabela nova, nunca desligado explicitamente pra esta
-- tabela — diferente de rasf_ee, que já tinha esse ajuste desde o
-- Sprint 6, ver database/schema_rasf.sql) e sem nenhuma policy
-- liberando leitura pra chave anon — a linha existia no banco (confirmado
-- via SQL Editor, que usa privilégio total) mas a query da chave anon
-- retornava sempre vazio, fazendo login/busca de usuário falhar mesmo
-- com senha certa.
--
-- O modelo de segurança deste app é 100% em camada de aplicação (perfil/
-- gerência checados em Python — ver auth/permissions.py), não em RLS do
-- Postgres, igual todas as outras tabelas do sistema. Este ajuste só
-- deixa `usuarios` consistente com o resto. Idempotente.

ALTER TABLE usuarios DISABLE ROW LEVEL SECURITY;
