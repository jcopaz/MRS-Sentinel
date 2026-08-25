-- ============================================================
-- MRS Sentinel — Organograma genérico (fundação multi-tenant)
-- ============================================================
-- Contexto: hoje "gerencia" é fixo via CHECK ('SP','VP') em usuarios e
-- uploads_historico, e as Coordenações (Jundiaí, Paranapiacaba,
-- Piaçaguera / Pinheirinho, Agulhas Negras, Taubaté) só existem como
-- dicionário Python fixo (core/glossarios.CENTROS_POR_GERENCIA). Isso
-- funciona bem pra UMA Gerência Geral (São Paulo), mas não escala pra
-- outras gerências gerais sem editar código.
--
-- Este arquivo cria a árvore genérica Gerência Geral > Gerência >
-- Coordenação e semeia com a estrutura real confirmada em 2026-08-21
-- (análise de "Notas Via GG.xlsx", 21.083 notas, + confirmação do Julio):
-- 4 Gerências Gerais — São Paulo, Ferrovia do Aço, Rio de Janeiro e
-- Linha do Centro.
--
-- ⚠️ ADITIVO: nenhuma tela, query ou permissão do app lê destas tabelas
-- ainda. usuarios.gerencia e os CHECKs existentes continuam sendo a
-- única fonte de verdade em produção até uma sessão dedicada rewirar
-- cada tela pra consultar o organograma. Rodar isso agora só prepara o
-- terreno — é seguro, não muda nenhum comportamento visível do sistema.
-- Idempotente.

CREATE TABLE IF NOT EXISTS org_unidades (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo           VARCHAR NOT NULL CHECK (tipo IN ('geral', 'gerencia', 'coordenacao')),
    sigla          VARCHAR NOT NULL,
    nome           VARCHAR NOT NULL,
    apelido        VARCHAR,               -- ex.: "Arará" pra Rocha Sobrinho — só exibição, nunca usado em filtro
    unidade_pai_id UUID REFERENCES org_unidades(id),
    ativo          BOOLEAN DEFAULT TRUE,
    criado_em      TIMESTAMP DEFAULT NOW(),
    UNIQUE (unidade_pai_id, sigla)
);

-- ⚠️ A UNIQUE(unidade_pai_id, sigla) acima NÃO barra duplicata nas linhas
-- tipo='geral' (unidade_pai_id sempre NULL) — o Postgres trata NULL≠NULL
-- em constraint única. Índice parcial cobre esse caso específico.
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_unidades_geral_sigla
    ON org_unidades (sigla) WHERE tipo = 'geral';

CREATE INDEX IF NOT EXISTS idx_org_unidades_pai ON org_unidades(unidade_pai_id);

COMMENT ON TABLE org_unidades IS
    'Organograma genérico (Gerência Geral > Gerência > Coordenação). Sigla é única só dentro do pai — códigos de coordenação se repetem entre Gerências diferentes na base real (ex.: FBC, FCL, FFB, FBR, FBV aparecem em mais de uma Gerência). Ainda não usado por nenhuma tela.';


-- ============================================================
-- Códigos SAP conhecidos por unidade (histórico + vigente)
-- ============================================================
-- Por quê: a reorganização real da MRS move coordenação de Gerência (às
-- vezes trocando o código SAP, às vezes não) sem reprocessar o histórico.
-- Ex. confirmado: Belo Vale e Brumadinho saíram de "V.MG.*" (Linha do
-- Centro) pra "V.FA.*" (Frente Norte) — código mudou. Já Barão de
-- Juparanã saiu de RJ pra Linha do Centro mantendo o código "V.RJ.FBJ"
-- — código não mudou, só o dono. Esta tabela deixa uma coordenação ter
-- vários códigos (um vigente + quantos legados existirem), todos
-- resolvendo pra unidade_id atual — assim uma nota antiga com código
-- legado ainda é lida sob a Gerência correta de hoje.
CREATE TABLE IF NOT EXISTS org_codigo_sap (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unidade_id      UUID NOT NULL REFERENCES org_unidades(id) ON DELETE CASCADE,
    disciplina      VARCHAR NOT NULL CHECK (disciplina IN ('VP', 'EE')),
    codigo_completo VARCHAR NOT NULL,   -- ex.: 'V.RJ.FBJ' (coordenação) ou 'V.MG' (gerência) — bate com Gerencia/Centro_de_trabalho_responsável do SAP
    vigente         BOOLEAN NOT NULL DEFAULT TRUE,
    observacao      VARCHAR,
    criado_em       TIMESTAMP DEFAULT NOW(),
    UNIQUE (disciplina, codigo_completo)
);

CREATE INDEX IF NOT EXISTS idx_org_codigo_sap_unidade ON org_codigo_sap(unidade_id);
CREATE INDEX IF NOT EXISTS idx_org_codigo_sap_codigo  ON org_codigo_sap(codigo_completo);

COMMENT ON TABLE org_codigo_sap IS
    'Mapeia código SAP (Gerencia ou Centro_de_trabalho_responsável, com prefixo V./E. de disciplina) pra um nó do organograma. Uma unidade pode ter vários códigos (vigente=true = atual, vigente=false = legado) — resolve o histórico quando a MRS reorganiza sem reprocessar notas antigas.';


-- ============================================================
-- Escopo de acesso em cascata (delegação de acesso por nó do organograma)
-- ============================================================
CREATE TABLE IF NOT EXISTS usuario_escopo (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id   UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    unidade_id   UUID NOT NULL REFERENCES org_unidades(id) ON DELETE CASCADE,
    criado_em    TIMESTAMP DEFAULT NOW(),
    UNIQUE (usuario_id, unidade_id)
);

COMMENT ON TABLE usuario_escopo IS
    'Concede a um usuário acesso a um nó do organograma e a tudo abaixo dele em cascata. Ainda não usado por auth/permissions.py.';


-- ============================================================
-- Seed: estrutura real confirmada (2026-08-21)
-- ============================================================

-- 4 Gerências Gerais
INSERT INTO org_unidades (tipo, sigla, nome) VALUES
    ('geral', 'GGSP', 'Gerência Geral São Paulo'),
    ('geral', 'GGFA', 'Gerência Geral Ferrovia do Aço'),
    ('geral', 'GGRJ', 'Gerência Geral Rio de Janeiro'),
    ('geral', 'GGLC', 'Gerência Geral Linha do Centro')
ON CONFLICT (sigla) WHERE tipo = 'geral' DO NOTHING;

-- Gerências (filhas de cada Gerência Geral)
INSERT INTO org_unidades (tipo, sigla, nome, unidade_pai_id)
SELECT 'gerencia', v.sigla, v.nome, gg.id
FROM org_unidades gg,
     (VALUES ('GGSP', 'SP', 'Gerência de Malha SP'),
             ('GGSP', 'VP', 'Gerência de Malha VP'),
             ('GGFA', 'FN', 'Gerência Frente Norte'),
             ('GGFA', 'FS', 'Gerência Frente Sul'),
             ('GGRJ', 'RJ', 'Gerência de Malha Rio de Janeiro'),
             ('GGLC', 'LC', 'Gerência de Malha Linha do Centro')
     ) AS v(gg_sigla, sigla, nome)
WHERE gg.tipo = 'geral' AND gg.sigla = v.gg_sigla
ON CONFLICT (unidade_pai_id, sigla) DO NOTHING;

-- Coordenações (filhas de cada Gerência)
INSERT INTO org_unidades (tipo, sigla, nome, apelido, unidade_pai_id)
SELECT 'coordenacao', c.sigla, c.nome, c.apelido, ger.id
FROM org_unidades ger,
     (VALUES
        -- Gerência SP
        ('SP', 'IPG', 'Piaçaguera', NULL),
        ('SP', 'IPA', 'Paranapiacaba', NULL),
        ('SP', 'PJU', 'Jundiaí', NULL),
        -- Gerência VP
        ('VP', 'FAN', 'Agulhas Negras', NULL),
        ('VP', 'FTA', 'Taubaté', NULL),
        ('VP', 'FPI', 'Pinheirinho', NULL),
        -- Gerência Frente Norte (inclui Belo Vale/Brumadinho, migradas de Linha do Centro)
        ('FN', 'FJC', 'P1-07', NULL),
        ('FN', 'ZAS', 'ZAS', NULL),
        ('FN', 'FBV', 'Belo Vale', NULL),
        ('FN', 'FBR', 'Brumadinho/Barreiro', NULL),
        -- Gerência Frente Sul
        ('FS', 'FDE', 'São João del Rey', NULL),
        ('FS', 'FOJ', 'Bom Jardim', NULL),
        ('FS', 'FPT', 'Quatis', NULL),
        -- Gerência Malha RJ (sem Juparanã, migrada pra Linha do Centro)
        ('RJ', 'FPL', 'Pinheiral', NULL),
        ('RJ', 'FBA', 'Brisamar', NULL),
        ('RJ', 'FBP', 'Barra do Piraí', NULL),
        ('RJ', 'FAR', 'Rocha Sobrinho', 'Arará'),
        -- Gerência Linha do Centro (inclui Juparanã, migrada de RJ; sem Belo Vale/Brumadinho, migradas pra FN)
        ('LC', 'FCL', 'Conselheiro Lafaiete', NULL),
        ('LC', 'FBC', 'Barbacena', NULL),
        ('LC', 'FFB', 'Francisco Bernardino', NULL),
        ('LC', 'FBJ', 'Barão de Juparanã', NULL)
     ) AS c(ger_sigla, sigla, nome, apelido)
WHERE ger.tipo = 'gerencia' AND ger.sigla = c.ger_sigla
ON CONFLICT (unidade_pai_id, sigla) DO NOTHING;


-- ============================================================
-- Seed: códigos SAP (vigentes + legados) por coordenação e por gerência
-- ============================================================
-- Gerência-level: código atual de cada Gerência (V./E.). Linha do Centro
-- tem código legado (V.MG/E.MG) além do atual (V.LC/E.LC).
INSERT INTO org_codigo_sap (unidade_id, disciplina, codigo_completo, vigente)
SELECT ger.id, d.disciplina, d.prefixo || '.' || ger.sigla, d.vigente
FROM org_unidades ger,
     (VALUES ('VP','V',true), ('EE','E',true)) AS d(disciplina, prefixo, vigente)
WHERE ger.tipo = 'gerencia'
ON CONFLICT (disciplina, codigo_completo) DO NOTHING;

INSERT INTO org_codigo_sap (unidade_id, disciplina, codigo_completo, vigente, observacao)
SELECT ger.id, d.disciplina, d.prefixo || '.MG', false, 'Código legado — Gerência Minas Gerais, renomeada para Linha do Centro (LC)'
FROM org_unidades ger,
     (VALUES ('VP','V'), ('EE','E')) AS d(disciplina, prefixo)
WHERE ger.tipo = 'gerencia' AND ger.sigla = 'LC'
ON CONFLICT (disciplina, codigo_completo) DO NOTHING;

-- Coordenação-level: código VIGENTE — o segmento do meio nem sempre bate
-- com a sigla da Gerência dona (ex.: FJC/ZAS/FBV/FBR moram em Frente
-- Norte mas o código real de sempre é "V.FA.*"; FBJ mora em Linha do
-- Centro mas o código nunca saiu de "V.RJ.FBJ"). Por isso a lista é
-- explícita, não gerada a partir da sigla da Gerência.
INSERT INTO org_codigo_sap (unidade_id, disciplina, codigo_completo, vigente)
SELECT coord.id, d.disciplina, d.prefixo || '.' || c.prefixo_sap || '.' || coord.sigla, true
FROM org_unidades coord
JOIN org_unidades ger ON ger.id = coord.unidade_pai_id,
     (VALUES ('VP','V'), ('EE','E')) AS d(disciplina, prefixo),
     (VALUES
        ('IPG','SP'), ('IPA','SP'), ('PJU','SP'),
        ('FAN','VP'), ('FTA','VP'), ('FPI','VP'),
        ('FJC','FA'), ('ZAS','FA'), ('FBV','FA'), ('FBR','FA'),
        ('FDE','FA'), ('FOJ','FA'), ('FPT','FA'),
        ('FPL','RJ'), ('FBA','RJ'), ('FBP','RJ'), ('FAR','RJ'),
        ('FCL','LC'), ('FBC','LC'), ('FFB','LC'),
        ('FBJ','RJ')   -- migrou de RJ pra Linha do Centro, mas o código nunca mudou
     ) AS c(coord_sigla, prefixo_sap)
WHERE coord.tipo = 'coordenacao' AND coord.sigla = c.coord_sigla
ON CONFLICT (disciplina, codigo_completo) DO NOTHING;

-- Códigos LEGADOS de coordenação (histórico, antes da reorganização):
--   Belo Vale/Brumadinho: vinham de Linha do Centro (V.MG.*) antes de
--     migrar pra Frente Norte (a Gerência mudou, e o código também).
--   Barbacena/Conselheiro Lafaiete/Francisco Bernardino: mesma
--     coordenação, mesma Gerência — só o código mudou de V.MG.* pra
--     V.LC.* a partir de 2026 (confirmado pelo Julio).
INSERT INTO org_codigo_sap (unidade_id, disciplina, codigo_completo, vigente, observacao)
SELECT coord.id, d.disciplina, d.prefixo || '.MG.' || coord.sigla, false, c.motivo
FROM org_unidades coord
JOIN org_unidades ger ON ger.id = coord.unidade_pai_id,
     (VALUES ('VP','V'), ('EE','E')) AS d(disciplina, prefixo),
     (VALUES
        ('FBV', 'Código legado — coordenação migrou de Linha do Centro (MG) para Frente Norte (FA)'),
        ('FBR', 'Código legado — coordenação migrou de Linha do Centro (MG) para Frente Norte (FA)'),
        ('FCL', 'Código legado — a partir de 2026 o SAP passou a usar V.LC em vez de V.MG'),
        ('FBC', 'Código legado — a partir de 2026 o SAP passou a usar V.LC em vez de V.MG'),
        ('FFB', 'Código legado — a partir de 2026 o SAP passou a usar V.LC em vez de V.MG')
     ) AS c(coord_sigla, motivo)
WHERE coord.tipo = 'coordenacao' AND coord.sigla = c.coord_sigla
ON CONFLICT (disciplina, codigo_completo) DO NOTHING;

-- Inconsistência de digitação confirmada na base de EE: "FBF" (letras
-- trocadas) é Francisco Bernardino (FFB), só na disciplina EE, nos dois
-- prefixos de Gerência que já circularam (E.MG.FBF e E.LC.FBF).
INSERT INTO org_codigo_sap (unidade_id, disciplina, codigo_completo, vigente, observacao)
SELECT coord.id, 'EE', c.codigo, false,
       'Inconsistência de digitação no SAP (EE) — "FBF" é Francisco Bernardino (FFB) com as letras trocadas'
FROM org_unidades coord,
     (VALUES ('E.MG.FBF'), ('E.LC.FBF')) AS c(codigo)
WHERE coord.tipo = 'coordenacao' AND coord.sigla = 'FFB'
ON CONFLICT (disciplina, codigo_completo) DO NOTHING;

-- Segundo prefixo observado nas duas bases (VP e EE) pras coordenações
-- de Frente Norte/Sul que hoje são cadastradas como "V.FA.*"/"E.FA.*"
-- (vigente): existem também notas com o prefixo da própria Gerência
-- (V.FN.*/V.FS.* e E.FN.*/E.FS.*), em volume menor. Registrado como
-- código adicional conhecido pra não perder nenhuma nota — marcado
-- como não-vigente por ora (a tabela do Julio aponta "FA" como o CT novo
-- pra Belo Vale/Brumadinho); se for o contrário, é só trocar o flag.
INSERT INTO org_codigo_sap (unidade_id, disciplina, codigo_completo, vigente, observacao)
SELECT coord.id, d.disciplina, d.prefixo || '.' || c.ger_sigla || '.' || coord.sigla, false,
       'Segundo prefixo observado na base (junto com o "FA") — confirmar com o Julio qual é o vigente'
FROM org_unidades coord
JOIN org_unidades ger ON ger.id = coord.unidade_pai_id,
     (VALUES ('VP','V'), ('EE','E')) AS d(disciplina, prefixo),
     (VALUES ('FJC','FN'), ('FBR','FN'), ('FBV','FN'),
             ('FDE','FS'), ('FOJ','FS'), ('FPT','FS')) AS c(coord_sigla, ger_sigla)
WHERE coord.tipo = 'coordenacao' AND coord.sigla = c.coord_sigla
ON CONFLICT (disciplina, codigo_completo) DO NOTHING;
