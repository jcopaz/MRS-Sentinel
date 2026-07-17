-- ============================================================
-- schema_rasf.sql — Tabela dedicada ao export RASF de Eletroeletrônica
-- Sprint 6 — MRS Sentinel · Aba "Inteligência de Falhas EE"
--
-- Opção B: tabela SEPARADA de `notas`. O RASF carrega a camada de análise
-- de causa raiz (RCA) do PG-ENG-0088 (Gatilho, THP, 6M, Componente Causador,
-- reincidência, confiabilidade) que a tabela `notas` não modela.
--
-- Reaproveita `uploads_historico` para versionamento anti-duplicação
-- (mesmo padrão de `notas`: upload novo marca o anterior como 'substituido').
-- ============================================================

CREATE TABLE IF NOT EXISTS rasf_ee (
    id                      BIGSERIAL PRIMARY KEY,
    upload_id               UUID REFERENCES uploads_historico(id) NOT NULL,
    gerencia                VARCHAR NOT NULL,          -- SP | VP (derivado de GEE.xx)
    disciplina              VARCHAR NOT NULL DEFAULT 'EE',

    -- Identificação / tempo
    ano                     INT,
    mes                     INT,
    numero_nota             BIGINT,
    data_nota               DATE,
    ordem                   VARCHAR,

    -- Localização / ativo
    centro_trab             VARCHAR,
    local_patio             VARCHAR,                   -- Pátio (IPG, IRS, IAA...)
    desc_tipo_solicitacao   VARCHAR,
    local_instalacao        VARCHAR,                   -- TPLNR (ativo — ranking reincidência)
    local_instalacao_desc   VARCHAR,
    num_equipamento         VARCHAR,
    grupo_ativo             VARCHAR,
    sistema                 VARCHAR,                   -- SINALIZAÇÃO, ENERGIA, TELECOM...
    anomalia_sintoma        VARCHAR,                   -- Sintoma (Pareto)
    desc_origem_atividade   VARCHAR,                   -- Origem bruta (coluna P) — referência de causa raiz
    origem_atividade_correta VARCHAR,                  -- Correção feita em reunião (coluna AW), quando houver
    origem_atividade_efetiva VARCHAR,                  -- desc_origem_atividade OU origem_atividade_correta, ver origem_efetiva()
    consenso_origem         VARCHAR,                   -- Sim/Não/vazio bruto (coluna AV)
    consenso_origem_status  VARCHAR,                   -- Sim | Não | Pendente — ver status_consenso_origem()
    texto_parte_objeto      VARCHAR,                   -- Objeto (coluna Q) — tabela Detalhamento de Notas
    texto_problema_erro     VARCHAR,                   -- Perda (coluna R) — tabela Detalhamento de Notas
    texto_longo             TEXT,

    -- Reincidência (pré-calculada no RASF)
    ultima_data_ativo        DATE,
    dias_ultima_falha_ativo  INT,
    reincidencia_ativo       BOOLEAN DEFAULT FALSE,
    ultima_data_sintoma      DATE,
    dias_ultima_falha_sintoma INT,
    reincidencia_sintoma     BOOLEAN DEFAULT FALSE,

    -- THP (Trem Hora Parado) — moeda de impacto operacional
    gerador_thp             BOOLEAN DEFAULT FALSE,
    thp_min                 NUMERIC DEFAULT 0,         -- Tempo THP 300 (min)
    thp_num_eventos         INT,
    thp_min_133             NUMERIC,

    -- Status / confiabilidade
    status_sistema          VARCHAR,
    impacta_confiabilidade  BOOLEAN DEFAULT FALSE,

    -- Camada RCA (PG-ENG-0088)
    gatilho_campo           VARCHAR,                   -- (Campo) Gatilho
    gatilho_eng             VARCHAR,                   -- (Eng) Gatilho
    gatilho_analise         BOOLEAN DEFAULT FALSE,     -- exige análise de causa raiz
    tipo_falha              VARCHAR,                   -- Alto/Médio/Baixo Impacto, Crítica
    m6n1_mf                 VARCHAR,                   -- 6M Nível 1 - Manutenção/Field
    m6n1_eng                VARCHAR,                   -- 6M Nível 1 - Engenharia
    m6_nivel1               VARCHAR,                   -- 6M consolidado (Eng > MF)
    arvore_falhas_mf        TEXT,
    componente_causador     VARCHAR,
    rca_preenchida          BOOLEAN DEFAULT FALSE,     -- tem causa raiz classificada
    lacuna_rca              BOOLEAN DEFAULT FALSE,     -- gatilho SEM causa raiz (backlog)

    -- Gestão da RASF
    pendente                BOOLEAN DEFAULT FALSE,
    disposicoes_reuniao     TEXT,
    responsavel             VARCHAR,
    item_sac                VARCHAR,

    -- Categorização Obras × Manutenção (a partir de "Descrição da Origem
    -- da Atividade") — ver core.parser_rasf.classificar_origem_atividade()
    origem_categoria         VARCHAR,

    criado_em               TIMESTAMP DEFAULT NOW()
);

-- Coluna nova em tabela já existente (upgrade idempotente — CREATE TABLE
-- IF NOT EXISTS acima não altera tabelas já criadas antes desta revisão).
ALTER TABLE rasf_ee ADD COLUMN IF NOT EXISTS origem_categoria VARCHAR;
ALTER TABLE rasf_ee ADD COLUMN IF NOT EXISTS origem_atividade_correta VARCHAR;
ALTER TABLE rasf_ee ADD COLUMN IF NOT EXISTS origem_atividade_efetiva VARCHAR;
ALTER TABLE rasf_ee ADD COLUMN IF NOT EXISTS consenso_origem VARCHAR;
ALTER TABLE rasf_ee ADD COLUMN IF NOT EXISTS consenso_origem_status VARCHAR;
ALTER TABLE rasf_ee ADD COLUMN IF NOT EXISTS texto_parte_objeto VARCHAR;
ALTER TABLE rasf_ee ADD COLUMN IF NOT EXISTS texto_problema_erro VARCHAR;

-- Índices para os filtros mais comuns da aba de inteligência
CREATE INDEX IF NOT EXISTS idx_rasf_gerencia       ON rasf_ee(gerencia);
CREATE INDEX IF NOT EXISTS idx_rasf_upload         ON rasf_ee(upload_id);
CREATE INDEX IF NOT EXISTS idx_rasf_data           ON rasf_ee(data_nota);
CREATE INDEX IF NOT EXISTS idx_rasf_ativo          ON rasf_ee(local_instalacao);
CREATE INDEX IF NOT EXISTS idx_rasf_sintoma        ON rasf_ee(anomalia_sintoma);
CREATE INDEX IF NOT EXISTS idx_rasf_patio          ON rasf_ee(local_patio);
CREATE INDEX IF NOT EXISTS idx_rasf_lacuna         ON rasf_ee(lacuna_rca);
CREATE INDEX IF NOT EXISTS idx_rasf_reincid        ON rasf_ee(reincidencia_ativo);
CREATE INDEX IF NOT EXISTS idx_rasf_origem_cat     ON rasf_ee(origem_categoria);
CREATE INDEX IF NOT EXISTS idx_rasf_origem_efetiva ON rasf_ee(origem_atividade_efetiva);
CREATE INDEX IF NOT EXISTS idx_rasf_consenso       ON rasf_ee(consenso_origem_status);

COMMENT ON TABLE  rasf_ee IS 'Export RASF (Reunião de Análise Sistêmica de Falha) de Eletroeletrônica — camada RCA do PG-ENG-0088. Sprint 6.';
COMMENT ON COLUMN rasf_ee.lacuna_rca IS 'TRUE quando a nota é Gatilho de Análise mas ainda não tem causa raiz (6M/Componente) — alimenta o Backlog RCA.';
COMMENT ON COLUMN rasf_ee.thp_min IS 'Tempo de Trem Hora Parado (min) — usado para priorização por impacto operacional.';
COMMENT ON COLUMN rasf_ee.origem_categoria IS 'Obras | Manutenção | Não classificado | Não informado — derivado de origem_atividade_efetiva, regra por substring + overrides configuráveis.';
COMMENT ON COLUMN rasf_ee.origem_atividade_efetiva IS 'Referência de causa raiz/responsabilidade — desc_origem_atividade, MAS sobreposta por origem_atividade_correta quando esta foi preenchida em reunião com valor diferente (responsabilidade corrigida). Ver core.parser_rasf.origem_efetiva().';
COMMENT ON COLUMN rasf_ee.consenso_origem_status IS 'Sim (processo encerrado) | Não (pode caber revisão) | Pendente (em branco — reunião ainda não decidiu). Ver core.parser_rasf.status_consenso_origem().';

-- ============================================================
-- RLS: desligado, mesmo modelo do resto do projeto
-- ============================================================
-- Nenhuma tabela deste app (notas, uploads_historico, alertas, configuracoes)
-- usa Row-Level Security do Postgres — a segurança é toda na camada do app
-- (auth/permissions.py: require_login(), can_upload(), perfil/gerência),
-- via o client anon key (database/client.py.get_supabase()). Se o projeto
-- Supabase tiver RLS habilitado por padrão em tabelas novas, o insert em
-- rasf_ee falha com 42501 "new row violates row-level security policy"
-- até isso ser desligado explicitamente. Idempotente — seguro rodar de novo.
ALTER TABLE rasf_ee DISABLE ROW LEVEL SECURITY;

-- ============================================================
-- CORREÇÃO: uploads_historico.disciplina tem CHECK restrito a ('VP','EE')
-- ============================================================
-- ⚠️ O comentário original aqui dizia que a coluna era "VARCHAR livre" —
-- ERRADO. database/schema.sql cria uploads_historico com
-- `disciplina VARCHAR NOT NULL CHECK (disciplina IN ('VP', 'EE'))`, então
-- gravar upload_historico com disciplina='RASF' falha com
-- "violates check constraint uploads_historico_disciplina_check" (23514).
-- Precisa recriar a constraint incluindo 'RASF'. Idempotente — pode rodar
-- de novo sem erro mesmo se já tiver sido aplicado.
ALTER TABLE uploads_historico DROP CONSTRAINT IF EXISTS uploads_historico_disciplina_check;
ALTER TABLE uploads_historico ADD CONSTRAINT uploads_historico_disciplina_check
    CHECK (disciplina IN ('VP', 'EE', 'RASF'));

-- ============================================================
-- CONFIGURAÇÃO: Gatilhos de Análise de Falha (PG-ENG-0088, seção 6.4.1)
-- ============================================================
-- O procedimento diz que essa regra muda por ciclo de metas da Coordenação
-- de Análise de Falhas — fica em `configuracoes` (editável pelo Admin, sem
-- deploy) em vez de fixa em core/parser_rasf.py. Mesmo padrão dos parâmetros
-- de alerta do Sprint 5 (alerta_n_min, alerta_janela_meses).
INSERT INTO configuracoes (gerencia, chave, valor)
VALUES
    (NULL, 'rasf_gatilhos_analise', '["Falha THP", "Falha Segurança", "Defeito THP"]')
ON CONFLICT (gerencia, chave) DO NOTHING;

-- ============================================================
-- CONFIGURAÇÃO: Overrides de Categoria Obras × Manutenção
-- ============================================================
-- classificar_origem_atividade() já classifica automaticamente por
-- substring ("OBRA"→Obras, "MANUTEN"→Manutenção). Valores ambíguos (ex.:
-- "MECÂNICA", "TRILHO OXIDADO", "VIA PERMANENTE") caem em
-- "Não classificado" por padrão. Use este override pra reclassificar
-- valores específicos sem precisar de deploy — edite o JSON abaixo direto
-- no Supabase. Formato: {"valor exato do RASF": "categoria desejada"}.
-- Categorias sugeridas: "Obras", "Manutenção" (ou crie outras livremente,
-- a UI só agrupa pelo que vier aqui).
INSERT INTO configuracoes (gerencia, chave, valor)
VALUES
    (NULL, 'rasf_origem_categoria_overrides', '{}')
ON CONFLICT (gerencia, chave) DO NOTHING;
