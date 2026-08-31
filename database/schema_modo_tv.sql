-- database/schema_modo_tv.sql — Acesso ao Modo TV (perf/RBAC, 2026-08-30)
--
-- Novo campo em `usuarios` pra delegar acesso ao Modo TV (tela de exibição
-- em loop, pensada pra TV/monitor de uma coordenação — ex.: TV parada na
-- coordenação de Jundiaí) sem precisar dar perfil admin completo pra uma
-- conta dedicada de kiosk. Hoje (2026-08-30) só admin de fato usa o Modo
-- TV — o campo já nasce pronto pra delegar no futuro (ver
-- auth/permissions.py::can_access_modo_tv).
--
-- Idempotente: seguro rodar mais de uma vez.

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS acesso_tv BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN usuarios.acesso_tv IS
    'Acesso ao Modo TV (tela de exibição em loop) mesmo sem ser admin — ver auth/permissions.py::can_access_modo_tv';

-- Verificação
SELECT matricula, nome, perfil, acesso_tv FROM usuarios ORDER BY criado_em DESC LIMIT 10;
