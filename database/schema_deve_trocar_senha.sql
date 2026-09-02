-- database/schema_deve_trocar_senha.sql — Troca de senha obrigatória (2026-09-02)
--
-- Novo campo em `usuarios` pra forçar a troca de senha no próximo login.
-- Achado real do Julio: criou um usuário de teste e não foi pedido pra
-- trocar a senha provisória (SENHA_PADRAO, ver modules/admin_panel.py) —
-- quem não trocasse manualmente ficava com ela pra sempre. Setado TRUE em
-- toda CRIAÇÃO de usuário e todo RESET de senha (ambos deixam a conta com
-- a mesma senha provisória); a tela auth/trocar_senha_obrigatoria.py
-- intercepta o app inteiro em app.py::main() enquanto estiver TRUE.
--
-- Idempotente: seguro rodar mais de uma vez.

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS deve_trocar_senha BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN usuarios.deve_trocar_senha IS
    'TRUE = próximo login intercepta com tela obrigatória de troca de senha (setado na criação e em todo reset) — ver auth/trocar_senha_obrigatoria.py';

-- Verificação
SELECT matricula, nome, perfil, deve_trocar_senha FROM usuarios ORDER BY criado_em DESC LIMIT 10;
