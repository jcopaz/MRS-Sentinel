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
    desc_origem_atividade   VARCHAR,
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

    criado_em               TIMESTAMP DEFAULT NOW()
);

-- Índices para os filtros mais comuns da aba de inteligência
CREATE INDEX IF NOT EXISTS idx_rasf_gerencia       ON rasf_ee(gerencia);
CREATE INDEX IF NOT EXISTS idx_rasf_upload         ON rasf_ee(upload_id);
CREATE INDEX IF NOT EXISTS idx_rasf_data           ON rasf_ee(data_nota);
CREATE INDEX IF NOT EXISTS idx_rasf_ativo          ON rasf_ee(local_instalacao);
CREATE INDEX IF NOT EXISTS idx_rasf_sintoma        ON rasf_ee(anomalia_sintoma);
CREATE INDEX IF NOT EXISTS idx_rasf_patio          ON rasf_ee(local_patio);
CREATE INDEX IF NOT EXISTS idx_rasf_lacuna         ON rasf_ee(lacuna_rca);
CREATE INDEX IF NOT EXISTS idx_rasf_reincid        ON rasf_ee(reincidencia_ativo);

COMMENT ON TABLE  rasf_ee IS 'Export RASF (Reunião de Análise Sistêmica de Falha) de Eletroeletrônica — camada RCA do PG-ENG-0088. Sprint 6.';
COMMENT ON COLUMN rasf_ee.lacuna_rca IS 'TRUE quando a nota é Gatilho de Análise mas ainda não tem causa raiz (6M/Componente) — alimenta o Backlog RCA.';
COMMENT ON COLUMN rasf_ee.thp_min IS 'Tempo de Trem Hora Parado (min) — usado para priorização por impacto operacional.';

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
