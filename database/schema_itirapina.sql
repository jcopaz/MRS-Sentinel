-- ============================================================
-- schema_itirapina.sql — Trecho Itirapina–Pederneiras · Marco Zero
--
-- ÚNICO script do trecho (substitui schema_prospeccao.sql e
-- schema_trecho_marco_zero.sql). Rodar manualmente no SQL Editor do
-- Supabase. Idempotente — pode rodar de novo sem perder dados.
--
-- ISOLAMENTO: todas as tabelas do trecho têm o prefixo itp_ e NÃO se
-- misturam com as tabelas da malha MRS (notas, rasf_ee, snapshots...).
-- Os dados aqui estão no formato Rumo (export SRM, GeVia, Vagão de Via).
-- Quando o trecho virar MRS, as prospecções e notas no formato MRS entram
-- nas tabelas normais do Sentinel; o que está em itp_* fica como histórico
-- de transição (marco zero e cargas Rumo), sem nenhum JOIN obrigatório.
--
-- Versionamento por BASE (itp_trecho_bases.data_base): cada carga apaga e
-- regrava só dentro da sua base; base congelada = somente leitura (bloqueio
-- no app: database/queries_trecho.py::BaseCongelada). Marco zero = base
-- 2026-10-26, criada aqui ainda NÃO congelada (congela pela tela).
--
-- Chave do trecho no banco: 'Itirapina-Triagem' (rótulo na tela:
-- "Itirapina–Pederneiras"). RLS desligado: acesso controlado no app
-- (auth/permissions.py::require_prospeccao). Depois rodar o seed:
--   python scripts/seed_trecho_itirapina.py > seed_itirapina.sql
-- ============================================================


-- ── 1. Bases (versionamento) ───────────────────────────────
CREATE TABLE IF NOT EXISTS itp_trecho_bases (
    id           BIGSERIAL PRIMARY KEY,
    trecho       VARCHAR NOT NULL,
    data_base    DATE    NOT NULL,
    descricao    TEXT,
    marco_zero   BOOLEAN DEFAULT FALSE,
    congelada    BOOLEAN DEFAULT FALSE,
    criado_por   UUID REFERENCES usuarios(id),
    criado_em    TIMESTAMP DEFAULT NOW(),
    UNIQUE (trecho, data_base)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_itp_marco_zero
    ON itp_trecho_bases(trecho) WHERE marco_zero;

INSERT INTO itp_trecho_bases (trecho, data_base, descricao, marco_zero, congelada)
VALUES ('Itirapina-Triagem', DATE '2026-10-26',
        'Marco zero — cenário de entrada do trecho Itirapina–Pederneiras', TRUE, FALSE)
ON CONFLICT (trecho, data_base) DO NOTHING;


-- ── 2. Prospecção de dormentes (Engenharia R1 / GeVia / Rev 1) ──
CREATE TABLE IF NOT EXISTS itp_prospeccao_dormentes (
    id                    BIGSERIAL PRIMARY KEY,
    base_id               BIGINT REFERENCES itp_trecho_bases(id),
    trecho                VARCHAR NOT NULL,
    gerencia              VARCHAR,
    coordenador           VARCHAR,
    sb                    VARCHAR,
    sub                   VARCHAR,
    equipamento_siv       VARCHAR,
    linha                 VARCHAR,                -- LP / LD
    km_inicio             DOUBLE PRECISION NOT NULL,
    km_fim                DOUBLE PRECISION NOT NULL,
    geometria             VARCHAR,                -- cv / tg
    raio                  DOUBLE PRECISION,
    oae                   BOOLEAN,
    pu                    BOOLEAN,
    fonte                 VARCHAR,
    data_prospeccao       DATE,
    ciclo                 INT,                    -- 2025 = histórico Rumo · 2026 = R1
    espacamento_cm        DOUBLE PRECISION,
    tipo_dormente         VARCHAR,
    tipo_fixacao          VARCHAR,
    dormentes_intercalados INT,
    malha_1  INT DEFAULT 0, malha_2  INT DEFAULT 0, malha_3 INT DEFAULT 0,
    malha_4  INT DEFAULT 0, malha_5  INT DEFAULT 0, malha_6 INT DEFAULT 0,
    malha_7  INT DEFAULT 0, malha_8  INT DEFAULT 0, malha_9 INT DEFAULT 0,
    malha_10 INT DEFAULT 0,                       -- malha_N = grupos de N inservíveis seguidos
    inserv_junta          INT DEFAULT 0,
    inserv_guarda         INT DEFAULT 0,
    inserv_solda          INT DEFAULT 0,
    total_prospectado     INT,
    dormentes_projetados  DOUBLE PRECISION,
    qtd_inservivel        INT,
    taxa_inservivel       DOUBLE PRECISION,       -- 0..1
    qtd_ruina             INT DEFAULT 0,
    qtd_acidentado        INT DEFAULT 0,
    ext_sem_leitura_m     DOUBLE PRECISION,
    observacao            TEXT,
    trem_passageiro       VARCHAR,
    aderencia             VARCHAR,
    responsavel           VARCHAR,
    status                VARCHAR,
    enviado_por           UUID REFERENCES usuarios(id),
    enviado_em            TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_itp_dorm_base ON itp_prospeccao_dormentes(base_id, linha, km_inicio);


-- ── 3. Relatório de Velocidade do SRM (PDF por rota) ────────
CREATE TABLE IF NOT EXISTS itp_relatorio_velocidade (
    id                BIGSERIAL PRIMARY KEY,
    base_id           BIGINT REFERENCES itp_trecho_bases(id),
    rota              VARCHAR NOT NULL,
    data_exportacao   TIMESTAMP,
    tipo              VARCHAR NOT NULL,   -- vma | restricao_a | restricao_b | obs_trecho | obs_estacao
    sub               VARCHAR,
    sb                VARCHAR,
    linha             VARCHAR,
    bitola            VARCHAR,
    trem_tipo         VARCHAR,
    km_de             DOUBLE PRECISION,
    km_ate            DOUBLE PRECISION,
    vel               DOUBLE PRECISION,
    motivo            TEXT,
    condicao          VARCHAR,
    responsavel       VARCHAR,
    inicio            TIMESTAMP,
    fim               TIMESTAMP,
    estacao           VARCHAR,
    trecho_desc       VARCHAR,
    observacao        TEXT,
    enviado_por       UUID REFERENCES usuarios(id),
    enviado_em        TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_itp_relvel_base ON itp_relatorio_velocidade(base_id, tipo);
CREATE INDEX IF NOT EXISTS idx_itp_relvel_sub  ON itp_relatorio_velocidade(sub, km_de);


-- ── 4. Prospecção de campo Rev 1: lastro, fixação, trilho ───
CREATE TABLE IF NOT EXISTS itp_prospeccao_lastro (
    id BIGSERIAL PRIMARY KEY, base_id BIGINT REFERENCES itp_trecho_bases(id),
    equipamento_siv VARCHAR, linha VARCHAR,
    km_inicio DOUBLE PRECISION, km_fim DOUBLE PRECISION, data_prospeccao DATE,
    cont_severa INT, cont_moderada INT, cont_leve INT, insuficiente INT, excesso INT,
    altura_excessiva INT, bolsao_bombeando INT, bolsao_nao_bombeando INT,
    drenagem_inexistente INT, drenagem_obstruida INT,
    medidas JSONB, observacao TEXT, responsavel VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_itp_lastro_base ON itp_prospeccao_lastro(base_id, km_inicio);

CREATE TABLE IF NOT EXISTS itp_prospeccao_fixacao (
    id BIGSERIAL PRIMARY KEY, base_id BIGINT REFERENCES itp_trecho_bases(id),
    equipamento_siv VARCHAR, linha VARCHAR,
    km_inicio DOUBLE PRECISION, km_fim DOUBLE PRECISION, data_prospeccao DATE,
    faltantes JSONB, total_faltantes INT, observacao TEXT, responsavel VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_itp_fixacao_base ON itp_prospeccao_fixacao(base_id, km_inicio);

CREATE TABLE IF NOT EXISTS itp_prospeccao_trilho (
    id BIGSERIAL PRIMARY KEY, base_id BIGINT REFERENCES itp_trecho_bases(id),
    equipamento_siv VARCHAR, linha VARCHAR,
    km_inicio DOUBLE PRECISION, km_fim DOUBLE PRECISION, data_prospeccao DATE,
    fila SMALLINT, fabricante VARCHAR, ano_mes VARCHAR, localizacao VARCHAR,
    medidas JSONB, perfil_predominante VARCHAR,
    situacao_desgaste VARCHAR,          -- Dentro / Fora / Sem parâmetro (Engenharia)
    extensao_m NUMERIC,
    rcf_muito_severo_und INT, rcf_severo_m NUMERIC, rcf_moderado_m NUMERIC, rcf_leve_m NUMERIC,
    corrugacao_p1_m NUMERIC, corrugacao_p2_m NUMERIC, corrugacao_p3_m NUMERIC,
    corrosao_m NUMERIC, patinado_m NUMERIC, trilho_invertido_m NUMERIC,
    junta_bom INT, junta_taco INT, junta_tala_quebrada INT, junta_desligada INT,
    junta_deformada INT, junta_tala_emergencia INT,
    solda_conoada_p1 INT, solda_conoada_p2 INT, solda_conoada_p3 INT,
    impacto_patim INT, solda_inadequada INT,
    observacao TEXT, responsavel VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_itp_trilho_base ON itp_prospeccao_trilho(base_id, km_inicio);


-- ── 5. Defeitos de via (export Rumo, inclui Vagão de Via) ───
CREATE TABLE IF NOT EXISTS itp_defeitos_via (
    id BIGSERIAL PRIMARY KEY, base_id BIGINT REFERENCES itp_trecho_bases(id),
    defeito_id BIGINT NOT NULL, status VARCHAR, sub VARCHAR, km DOUBLE PRECISION,
    equipamento_siv VARCHAR, linha VARCHAR, sb VARCHAR,
    nome_defeito VARCHAR, grupo VARCHAR, grupo_grafico VARCHAR,
    classe_via VARCHAR, vel_max_classe_kmh SMALLINT,
    classificacao VARCHAR,
    limite_malha VARCHAR, tamanho NUMERIC, extensao NUMERIC, peso NUMERIC,
    data_entrada DATE, data_baixa DATE, dias_ativo INT,
    origem VARCHAR,
    tipo_inspecao VARCHAR, numero_viagem INT, sentido_viagem VARCHAR, giro_via VARCHAR,
    perimetro_urbano BOOLEAN, obra_de_arte BOOLEAN, amv VARCHAR, area_risco_antt BOOLEAN,
    acidente BOOLEAN, data_acidente DATE, causa_acidente TEXT,
    latitude DOUBLE PRECISION, longitude DOUBLE PRECISION,
    supervisor VARCHAR, extra JSONB,
    UNIQUE (base_id, defeito_id)
);
CREATE INDEX IF NOT EXISTS idx_itp_defvia_base_km ON itp_defeitos_via(base_id, km);
CREATE INDEX IF NOT EXISTS idx_itp_defvia_origem  ON itp_defeitos_via(base_id, origem, numero_viagem);


-- ── 6. Transit time ZPD ↔ ZIQ (série contínua, sem base) ────
CREATE TABLE IF NOT EXISTS itp_transit_time (
    id BIGSERIAL PRIMARY KEY, trem VARCHAR NOT NULL,
    patio_a VARCHAR NOT NULL, patio_b VARCHAR NOT NULL, sentido VARCHAR,
    partida TIMESTAMP NOT NULL, tipo_parte CHAR(1), chegada TIMESTAMP, tipo_chega CHAR(1),
    horas NUMERIC, horas_programadas NUMERIC, estado VARCHAR, dt_encer TIMESTAMP,
    valido BOOLEAN, outlier BOOLEAN,
    UNIQUE (trem, patio_a, patio_b, partida)
);
CREATE INDEX IF NOT EXISTS idx_itp_transit_sentido ON itp_transit_time(sentido, partida);


-- ── 7. Inspeção de campo + mídias por referência ────────────
CREATE TABLE IF NOT EXISTS itp_inspecoes_campo (
    id BIGSERIAL PRIMARY KEY, base_id BIGINT REFERENCES itp_trecho_bases(id),
    msg_n INT, data_hora TIMESTAMP, responsavel VARCHAR,
    km DOUBLE PRECISION, km_fim DOUBLE PRECISION, km_fonte VARCHAR,
    linha VARCHAR, sb VARCHAR, equipamento_siv VARCHAR, local TEXT,
    tema VARCHAR, descricao TEXT, gravidade VARCHAR, acao_sugerida TEXT,
    ponto_critico VARCHAR, top10 VARCHAR, taxa_inserv_equip NUMERIC,
    defeitos_rumo_janela INT, restricoes_janela TEXT,
    fonte VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_itp_inspecao_base ON itp_inspecoes_campo(base_id, km);

-- O arquivo fica no SharePoint/OneDrive MRS; aqui só a referência.
CREATE TABLE IF NOT EXISTS itp_midias_repositorio (
    id BIGSERIAL PRIMARY KEY, trecho VARCHAR NOT NULL,
    nome VARCHAR NOT NULL, base_url TEXT NOT NULL, tipo VARCHAR,
    ativo BOOLEAN DEFAULT TRUE,
    UNIQUE (trecho, nome)
);

CREATE TABLE IF NOT EXISTS itp_inspecao_midias (
    id BIGSERIAL PRIMARY KEY,
    inspecao_id BIGINT REFERENCES itp_inspecoes_campo(id) ON DELETE CASCADE,
    base_id BIGINT REFERENCES itp_trecho_bases(id),
    msg_n INT,
    arquivo VARCHAR NOT NULL, tipo VARCHAR, caminho_relativo TEXT, url TEXT,
    repositorio_id BIGINT REFERENCES itp_midias_repositorio(id),
    miniatura BYTEA
);
CREATE INDEX IF NOT EXISTS idx_itp_midias_base ON itp_inspecao_midias(base_id, msg_n);


-- ── 8. Referências estáticas (seed) ─────────────────────────
CREATE TABLE IF NOT EXISTS itp_trecho_estacoes (
    trecho VARCHAR, codigo VARCHAR, nome VARCHAR,
    km_inicio DOUBLE PRECISION, km_fim DOUBLE PRECISION, ordem SMALLINT, observacao TEXT,
    PRIMARY KEY (trecho, codigo)
);
CREATE TABLE IF NOT EXISTS itp_limites_geometria (
    bitola VARCHAR, classe VARCHAR, vel_min_kmh SMALLINT, vel_max_kmh SMALLINT,
    parametro VARCHAR, limite_mm NUMERIC,
    PRIMARY KEY (bitola, classe, parametro)
);
CREATE TABLE IF NOT EXISTS itp_trecho_pontos_criticos (
    trecho VARCHAR, ponto VARCHAR, tipo VARCHAR,
    rank SMALLINT, equipamento_siv VARCHAR, secao VARCHAR,
    km_inicio DOUBLE PRECISION, km_fim DOUBLE PRECISION,
    PRIMARY KEY (trecho, ponto)
);


-- ── 9. Foto dos indicadores por base ────────────────────────
CREATE TABLE IF NOT EXISTS itp_trecho_indicadores (
    id BIGSERIAL PRIMARY KEY, base_id BIGINT REFERENCES itp_trecho_bases(id),
    escopo VARCHAR NOT NULL, chave VARCHAR NOT NULL, indicador VARCHAR NOT NULL,
    valor NUMERIC, calculado_em TIMESTAMP DEFAULT NOW(),
    UNIQUE (base_id, escopo, chave, indicador)
);


-- ── 10. Aproveita carga antiga (só se schema_prospeccao.sql de 09/10 chegou
--        a ser rodado): copia para as tabelas itp_ na base do marco zero.
--        As tabelas antigas NÃO são apagadas — conferir e dropar à mão. ──
DO $$
DECLARE mz BIGINT;
BEGIN
    SELECT id INTO mz FROM itp_trecho_bases WHERE trecho = 'Itirapina-Triagem' AND marco_zero;
    IF to_regclass('public.prospeccao_dormentes') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM itp_prospeccao_dormentes) THEN
        INSERT INTO itp_prospeccao_dormentes (
            base_id, trecho, gerencia, coordenador, sb, sub, equipamento_siv, linha, km_inicio, km_fim,
            geometria, raio, oae, pu, fonte, data_prospeccao, espacamento_cm, tipo_dormente, tipo_fixacao,
            malha_1, malha_2, malha_3, malha_4, malha_5, malha_6, malha_7, malha_8, malha_9, malha_10,
            inserv_junta, inserv_guarda, inserv_solda, total_prospectado, dormentes_projetados,
            qtd_inservivel, taxa_inservivel, qtd_ruina, ext_sem_leitura_m, observacao,
            trem_passageiro, aderencia, enviado_por, enviado_em)
        SELECT mz, trecho, gerencia, coordenador, sb, sub, equipamento_siv, linha, km_inicio, km_fim,
            geometria, raio, oae, pu, fonte, data_prospeccao, espacamento_cm, tipo_dormente, tipo_fixacao,
            malha_1, malha_2, malha_3, malha_4, malha_5, malha_6, malha_7, malha_8, malha_9, malha_10,
            inserv_junta, inserv_guarda, inserv_solda, total_prospectado, dormentes_projetados,
            qtd_inservivel, taxa_inservivel, qtd_ruina, ext_sem_leitura_m, observacao,
            trem_passageiro, aderencia, enviado_por, enviado_em
        FROM prospeccao_dormentes WHERE trecho = 'Itirapina-Triagem';
    END IF;
    IF to_regclass('public.relatorio_velocidade') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM itp_relatorio_velocidade) THEN
        INSERT INTO itp_relatorio_velocidade (
            base_id, rota, data_exportacao, tipo, sub, sb, linha, bitola, trem_tipo, km_de, km_ate, vel,
            motivo, condicao, responsavel, inicio, fim, estacao, trecho_desc, observacao,
            enviado_por, enviado_em)
        SELECT mz, rota, data_exportacao, tipo, sub, sb, linha, bitola, trem_tipo, km_de, km_ate, vel,
            motivo, condicao, responsavel, inicio, fim, estacao, trecho_desc, observacao,
            enviado_por, enviado_em
        FROM relatorio_velocidade;
    END IF;
END $$;


-- ── RLS: mesmo padrão das demais tabelas do app ─────────────
ALTER TABLE itp_trecho_bases           DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_prospeccao_dormentes   DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_relatorio_velocidade   DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_prospeccao_lastro      DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_prospeccao_fixacao     DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_prospeccao_trilho      DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_defeitos_via           DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_transit_time           DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_inspecoes_campo        DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_midias_repositorio     DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_inspecao_midias        DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_trecho_estacoes        DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_limites_geometria      DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_trecho_pontos_criticos DISABLE ROW LEVEL SECURITY;
ALTER TABLE itp_trecho_indicadores     DISABLE ROW LEVEL SECURITY;
