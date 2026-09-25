-- Diagnóstico: confirma que a conta admin está com email/ativo corretos
-- (troque 'seu.email@mrs.com.br' pelo email que você usa pra logar)
SELECT id, nome, email, matricula, perfil, gerencia, ativo, auth_user_id
FROM usuarios
WHERE email = 'seu.email@mrs.com.br';
