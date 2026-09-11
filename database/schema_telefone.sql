-- database/schema_telefone.sql — Telefone para recuperação de senha por SMS (2026-09-11)
--
-- Por quê: o reset de senha autoatendido (auth/recuperar_senha.py) depende de
-- e-mail, e o Julio recebeu relato de que o envio por e-mail não está
-- chegando. Telefone vira canal alternativo/futuro de recuperação por SMS.
-- Captado no momento da troca obrigatória de senha (1º acesso/reset) —
-- ver auth/trocar_senha_obrigatoria.py — e, pra quem já tinha conta antes
-- desta mudança, num prompt único (auth/confirmar_telefone.py).
--
-- Formato: E.164 (+55DDDNNNNNNNNN), normalizado por auth/telefone.py antes
-- de gravar — nunca grava o texto digitado cru.
--
-- Idempotente: seguro rodar mais de uma vez.

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS telefone TEXT;

COMMENT ON COLUMN usuarios.telefone IS
    'Celular em E.164 (+55DDDNNNNNNNNN), usado só para recuperação de acesso. Captado na troca obrigatória de senha ou no prompt de confirmação (auth/confirmar_telefone.py). Envio de SMS em si ainda não implementado neste app.';

-- Verificação
SELECT matricula, nome, perfil, deve_trocar_senha, telefone
FROM usuarios ORDER BY criado_em DESC LIMIT 10;
