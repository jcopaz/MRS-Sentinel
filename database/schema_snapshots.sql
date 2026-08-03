-- =============================================================================
-- database/schema_snapshots.sql — Sprint 8 (Memória & Comparações)
--
-- Tabela `snapshots`: fotos SEMANAIS agregadas da base VIVA de notas (VP/EE).
-- NÃO é imagem nem cópia da base — é um RECORTE de indicadores por
-- (semana ISO × gerência × disciplina × ramal × trecho), congelado no momento.
-- Permite comparar período × período (semana×semana, mês×mês) e reconstruir a
-- "Evolução da Malha" imune a reprocessamento/edição posterior das notas.
--
-- Idempotente: CREATE ... IF NOT EXISTS + UNIQUE(chave) para o upsert semanal
-- (regravar a semana corrente a cada upload sem duplicar).
-- =============================================================================

CREATE TABLE IF NOT EXISTS snapshots (
    id                     BIGSERIAL PRIMARY KEY,

    -- Âncora temporal (semana ISO)
    semana_iso             VARCHAR NOT NULL,   -- ex.: '2026-W31'
    ano                    INT     NOT NULL,
    semana                 INT     NOT NULL,   -- nº da semana ISO (1..53)
    data_ref               DATE    NOT NULL,   -- segunda-feira da semana (âncora)

    -- Escopo
    gerencia               VARCHAR NOT NULL CHECK (gerencia IN ('SP', 'VP')),
    disciplina             VARCHAR NOT NULL,   -- 'VP' | 'EE'
    ramal                  VARCHAR,
    trecho                 VARCHAR,

    -- Métricas congeladas (estado + fluxo)
    total_notas            INT     DEFAULT 0,  -- total no recorte (histórico vivo)
    notas_abertas          INT     DEFAULT 0,  -- backlog em aberto no momento
    aberturas_periodo      INT     DEFAULT 0,  -- abriram nesta semana
    encerramentos_periodo  INT     DEFAULT 0,  -- encerraram nesta semana
    thp_acumulado          NUMERIC DEFAULT 0,  -- soma de THP (quando houver a coluna)
    score_medio            NUMERIC,            -- score médio (pesos padrão) congelado
    notas_cronicas         INT     DEFAULT 0,  -- notas em grupos crônicos (>= n_min)
    pct_cronico            NUMERIC,            -- notas_cronicas / total_notas (0..100)
    reincidentes           INT     DEFAULT 0,  -- notas reabertas (reincidência)

    criado_em              TIMESTAMPTZ DEFAULT NOW(),

    -- Chave lógica de deduplicação (base do upsert semanal)
    chave                  VARCHAR NOT NULL,   -- semana|ger|disc|ramal|trecho
    UNIQUE (chave)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_semana     ON snapshots(semana_iso);
CREATE INDEX IF NOT EXISTS idx_snapshots_escopo     ON snapshots(gerencia, disciplina);
CREATE INDEX IF NOT EXISTS idx_snapshots_ano_semana ON snapshots(ano, semana);
CREATE INDEX IF NOT EXISTS idx_snapshots_ramal      ON snapshots(ramal);

COMMENT ON TABLE  snapshots            IS 'Sprint 8 — fotos semanais agregadas da base viva de notas (indicadores, não imagem).';
COMMENT ON COLUMN snapshots.chave      IS 'Hash lógico semana_iso|gerencia|disciplina|ramal|trecho — base do upsert semanal (anti-duplicação).';
COMMENT ON COLUMN snapshots.data_ref   IS 'Segunda-feira (ISO) da semana da foto — âncora para agregação mensal.';
COMMENT ON COLUMN snapshots.pct_cronico IS 'Percentual (0..100) de notas do recorte em grupos crônicos (ramal+origem+família >= n_min).';
