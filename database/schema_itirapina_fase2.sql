-- =============================================================================
-- database/schema_itirapina_fase2.sql — Fase 2 do trecho Itirapina–Pederneiras
-- (One Page, Unifilar navegável, Travamento). Rodar DEPOIS de
-- schema_itirapina.sql, no SQL Editor do Supabase. Idempotente.
--
--   itp_sb_faixas          SBs da Rumo por km (SB vazia → pelo km)
--   itp_plano              estratégia congelada por equipamento (travamento,
--                          meta 20%/16%, ponto crítico C/T, Top 10)
--   itp_metas              metas editáveis pelo admin
--   itp_execucao           o que a Manutenção fez (base da One Page)
--   itp_restricoes_eventos retirada/nova/alterada entre Relatórios de Velocidade
--
-- Seeds (sb_faixas, plano, metas): python scripts/seed_trecho_itirapina.py
-- Mesmo isolamento da fase 1: só tabelas itp_, RLS desligado (controle no app).
-- =============================================================================

CREATE TABLE IF NOT EXISTS itp_sb_faixas (
    trecho    VARCHAR NOT NULL DEFAULT 'Itirapina-Triagem',
    sb        VARCHAR NOT NULL,
    km_inicio DOUBLE PRECISION NOT NULL,
    km_fim    DOUBLE PRECISION NOT NULL,
    ordem     SMALLINT,
    fonte     TEXT,
    PRIMARY KEY (trecho, sb)
);

CREATE TABLE IF NOT EXISTS itp_plano (
    equipamento_siv VARCHAR NOT NULL,
    linha           VARCHAR NOT NULL,
    tipo            VARCHAR,                -- curva | tangente
    km_inicio       DOUBLE PRECISION,
    km_fim          DOUBLE PRECISION,
    raio            NUMERIC,
    sb              VARCHAR,
    inserviveis_mz  INT,                    -- marco zero
    taxa_mz         NUMERIC,                -- 0–1
    dorm_travamento INT,                    -- "Cenário Travamento - Risco Operacional" (negativo → 0)
    dorm_meta20     INT,                    -- "2º Cenário Dorm. Nec. 20%"
    dorm_meta16     INT,                    -- "3º Cenário Dorm. Nec. 16%"
    ponto_critico   VARCHAR,                -- C1..C3 / T1..T4 ou NULL
    rank_top10      SMALLINT,               -- 1..10 dentro do tipo ou NULL
    PRIMARY KEY (equipamento_siv, linha)
);

CREATE TABLE IF NOT EXISTS itp_metas (
    indicador   VARCHAR PRIMARY KEY,
    rotulo      VARCHAR,
    valor_meta  NUMERIC,
    prazo       DATE,
    observacao  TEXT,
    atualizado_por UUID,
    atualizado_em  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS itp_execucao (
    id BIGSERIAL PRIMARY KEY,
    trecho          VARCHAR NOT NULL DEFAULT 'Itirapina-Triagem',
    data            DATE NOT NULL,
    atividade       VARCHAR NOT NULL,       -- troca_dormente | solda | retirada_tala | socaria | nivelamento |
                                            -- limpeza_lastro | descarga_lastro | troca_trilho | drenagem | outro
    km_inicio       DOUBLE PRECISION NOT NULL,
    km_fim          DOUBLE PRECISION,
    linha           VARCHAR DEFAULT 'LP',
    equipamento_siv VARCHAR,                -- calculado pelo km se vier vazio
    quantidade      NUMERIC NOT NULL,
    unidade         VARCHAR NOT NULL,       -- dorm | und | m | km
    equipe          VARCHAR,
    nota_sap        VARCHAR,
    observacao      TEXT,
    enviado_por     UUID,
    enviado_em      TIMESTAMP DEFAULT NOW(),
    UNIQUE (data, atividade, km_inicio, linha, quantidade)
);
CREATE INDEX IF NOT EXISTS idx_itp_execucao_data ON itp_execucao (data);

CREATE TABLE IF NOT EXISTS itp_restricoes_eventos (
    id BIGSERIAL PRIMARY KEY,
    base_id    BIGINT REFERENCES itp_trecho_bases(id) ON DELETE CASCADE,
    base_ant_id BIGINT REFERENCES itp_trecho_bases(id) ON DELETE CASCADE,
    evento     VARCHAR NOT NULL,            -- retirada | nova | alterada
    seq_rumo   INT,
    sb         VARCHAR,
    linha      VARCHAR,
    km_de      DOUBLE PRECISION,
    km_ate     DOUBLE PRECISION,
    vel_antes  NUMERIC,
    vel_depois NUMERIC,
    codigo     VARCHAR,
    motivo     TEXT,
    grupo      VARCHAR,                     -- via | ANTT/terceiros
    UNIQUE (base_id, evento, linha, km_de, motivo)
);

ALTER TABLE itp_sb_faixas          DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_plano              DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_metas              DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_execucao           DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_restricoes_eventos DISABLE ROW LEVEL SECURITY;
