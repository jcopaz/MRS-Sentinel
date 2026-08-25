-- ============================================================
-- MRS Sentinel — Login por matrícula (sem depender de e-mail/SMTP)
-- ============================================================
-- Contexto: não há servidor SMTP disponível para o Sentinel, e nem todo
-- colaborador de campo tem e-mail corporativo. O Supabase Auth exige um
-- "email" como identidade interna, mas o login em auth/login.py passa a
-- aceitar MATRÍCULA (além de e-mail, que continua funcionando pra quem já
-- tem conta). Quando o colaborador não tem e-mail real, o admin cria a
-- conta só com matrícula e o sistema gera um e-mail sintético (nunca
-- enviado — ver database/queries.gerar_email_sintetico) só pra satisfazer
-- o Auth por baixo dos panos.
--
-- Recuperação de senha continua 100% administrada: só o admin reseta, via
-- API service-role do Supabase (Painel Admin > Usuários > Resetar Senha),
-- sem depender de e-mail de recuperação. Idempotente — seguro rodar de novo.

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS matricula VARCHAR;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS auth_user_id UUID;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email_gerado BOOLEAN DEFAULT FALSE;

-- Único quando preenchido (permite múltiplos NULL para contas legadas
-- que ainda só têm e-mail).
CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_matricula
    ON usuarios (matricula) WHERE matricula IS NOT NULL;

COMMENT ON COLUMN usuarios.matricula IS
    'Identificador de login alternativo ao e-mail (matrícula MRS). Único quando preenchido.';
COMMENT ON COLUMN usuarios.auth_user_id IS
    'UUID do usuário no Supabase Auth (auth.users) — evita busca paginada por e-mail ao resetar senha.';
COMMENT ON COLUMN usuarios.email_gerado IS
    'TRUE quando o e-mail foi gerado internamente (usuário sem e-mail corporativo real) — nunca usar para envio.';
