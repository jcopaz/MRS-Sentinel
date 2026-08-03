-- ============================================================
-- schema_rasf_baseline.sql — Base de Falhas EE CONGELADA 2025 (camada YoY)
-- Sprint 7 — MRS Sentinel · Aba "🔌 Inteligência de Falhas EE"
--
-- Objetivo: guardar o baseline 2025 (Base_de_Falhas_Congelado_2025_EE.xlsx),
-- que já traz o campo "Causa" classificado, para servir de REFERÊNCIA de
-- comparação ano-a-ano (YoY) contra a base RASF viva (tabela `rasf_ee`).
--
-- Por que tabela SEPARADA de rasf_ee?
--   • O congelado 2025 tem layout mais enxuto (~16 col) e NÃO tem a camada
--     RCA completa do PG-ENG-0088 (6M, gatilho, componente causador). Misturar
--     com rasf_ee (77 col) poluiria as agregações da base viva.
--   • É "congelado": não muda. Fica isolado para não interferir nos blocos
--     operacionais (Backlog RCA, Árvore de Falhas, etc.) que só olham 2026.
--
-- Reaproveita `uploads_historico` para versionamento anti-duplicação, mesmo
-- padrão de `notas`/`rasf_ee` (disciplina = 'RASF_BASE').
-- ============================================================

CREATE TABLE IF NOT EXISTS rasf_baseline (
    id                    BIGSERIAL PRIMARY KEY,
    upload_id             UUID REFERENCES uploads_historico(id) NOT NULL,
    gerencia              VARCHAR NOT NULL,          -- SP | VP (derivado de GEE.xx / Departamento)
    disciplina            VARCHAR NOT NULL DEFAULT 'EE',

    -- Tempo
    ano                   INT,
    mes                   INT,
    numero_nota           BIGINT,
    data_nota             DATE,

    -- Classificação (o valor de ouro do congelado: "Causa" já preenchida)
    desc_tipo_solicitacao VARCHAR,
    anomalia_sintoma      VARCHAR,                   -- "Codificação" (sintoma, ex.: 33-Circuito de via)
    causa                 VARCHAR,                   -- Causa classificada (base do YoY de causa raiz)

    -- Localização / ativo
    local_instalacao      VARCHAR,                   -- TPLNR
    grupo_ativo           VARCHAR,
    sistema               VARCHAR,                   -- SINALIZAÇÃO, ENERGIA, TELECOM...
    status_sistema        VARCHAR,
    novo_indicador        VARCHAR,                   -- "Novo Indicador" (marcação do congelado)

    -- Impacto operacional
    gerador_thp           BOOLEAN DEFAULT FALSE,
    thp_min               NUMERIC DEFAULT 0,         -- "Tempo THP" (min)

    criado_em             TIMESTAMP DEFAULT NOW()
);

-- Upgrades idempotentes (caso a tabela já exista de uma revisão anterior)
ALTER TABLE rasf_baseline ADD COLUMN IF NOT EXISTS causa          VARCHAR;
ALTER TABLE rasf_baseline ADD COLUMN IF NOT EXISTS novo_indicador VARCHAR;
ALTER TABLE rasf_baseline ADD COLUMN IF NOT EXISTS grupo_ativo    VARCHAR;

-- Índices para os cortes do bloco YoY
CREATE INDEX IF NOT EXISTS idx_baseline_gerencia ON rasf_baseline(gerencia);
CREATE INDEX IF NOT EXISTS idx_baseline_upload   ON rasf_baseline(upload_id);
CREATE INDEX IF NOT EXISTS idx_baseline_anomes   ON rasf_baseline(ano, mes);
CREATE INDEX IF NOT EXISTS idx_baseline_sistema  ON rasf_baseline(sistema);
CREATE INDEX IF NOT EXISTS idx_baseline_causa    ON rasf_baseline(causa);

COMMENT ON TABLE  rasf_baseline IS 'Base de Falhas EE congelada 2025 — referência de comparação ano-a-ano (YoY) para a aba Inteligência EE. Sprint 7.';
COMMENT ON COLUMN rasf_baseline.causa IS 'Causa raiz JÁ classificada no congelado 2025 — usada como referência de padronização de causa (contraste com a base viva, onde a causa raiz ainda tem lacuna).';

-- RLS desligado (mesmo modelo do resto do projeto — segurança na camada do app)
ALTER TABLE rasf_baseline DISABLE ROW LEVEL SECURITY;

-- ============================================================
-- uploads_historico.disciplina — incluir 'RASF_BASE' no CHECK
-- ============================================================
-- schema_rasf.sql já ampliou o CHECK para ('VP','EE','RASF'). Aqui apenas
-- acrescentamos 'RASF_BASE'. Idempotente — pode rodar de novo sem erro.
ALTER TABLE uploads_historico DROP CONSTRAINT IF EXISTS uploads_historico_disciplina_check;
ALTER TABLE uploads_historico ADD CONSTRAINT uploads_historico_disciplina_check
    CHECK (disciplina IN ('VP', 'EE', 'RASF', 'RASF_BASE'));
