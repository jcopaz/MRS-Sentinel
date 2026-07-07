-- ============================================================
-- SESSÃO 8: ALERTAS (Sprint 5 — Alertas Automáticos)
-- ============================================================
-- Armazena hot-spots crônicos e reincidências detectados pelo
-- motor core/alertas.py. Recalculado a cada upload + botão manual.
-- ============================================================
CREATE TABLE IF NOT EXISTS alertas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gerencia         VARCHAR NOT NULL CHECK (gerencia IN ('SP', 'VP')),
    disciplina       VARCHAR NOT NULL CHECK (disciplina IN ('VP', 'EE')),

    -- Tipo e severidade
    tipo             VARCHAR NOT NULL
                     CHECK (tipo IN ('cronico', 'reincidencia')),
    severidade       VARCHAR NOT NULL
                     CHECK (severidade IN ('critico', 'atencao', 'info')),

    -- Localização (granularidade ramal + origem)
    ramal            VARCHAR,
    origem           VARCHAR,
    familia_defeito  VARCHAR,

    -- Métricas do alerta
    n_ocorrencias    INT     NOT NULL DEFAULT 0,
    score_acumulado  NUMERIC NOT NULL DEFAULT 0,

    -- Chave de deduplicação (gerencia|disciplina|tipo|ramal|origem|familia)
    chave_alerta     VARCHAR NOT NULL,

    -- Detalhes livres (nºs das notas, datas, lead time, janela, etc.)
    detalhes         JSONB,

    -- Ciclo de vida
    status           VARCHAR NOT NULL DEFAULT 'novo'
                     CHECK (status IN ('novo', 'visto', 'resolvido')),
    criado_em        TIMESTAMP DEFAULT NOW(),
    atualizado_em    TIMESTAMP DEFAULT NOW(),
    resolvido_por    UUID REFERENCES usuarios(id),
    resolvido_em     TIMESTAMP,

    -- Um alerta ativo por chave (upsert evita duplicar a cada recálculo)
    UNIQUE (chave_alerta)
);

COMMENT ON TABLE alertas IS 'Hot-spots crônicos e reincidências (Sprint 5). Recalculado a cada upload.';
COMMENT ON COLUMN alertas.chave_alerta IS 'Hash lógico gerencia|disciplina|tipo|ramal|origem|familia — base do upsert.';
COMMENT ON COLUMN alertas.tipo IS 'cronico = >=N notas mesma familia na janela; reincidencia = reabertura <=X dias.';

CREATE INDEX IF NOT EXISTS idx_alertas_gerencia   ON alertas(gerencia, disciplina);
CREATE INDEX IF NOT EXISTS idx_alertas_status     ON alertas(status);
CREATE INDEX IF NOT EXISTS idx_alertas_severidade ON alertas(severidade);


-- ============================================================
-- SESSÃO 9: CONFIGURAÇÕES DE ALERTA (Sprint 5)
-- ============================================================
-- Parâmetros globais (gerencia = NULL) do motor de alertas.
-- Editáveis pelo Admin → aba Configurações.
-- ============================================================
INSERT INTO configuracoes (gerencia, chave, valor)
VALUES
    (NULL, 'alerta_n_min',              '3'),
    (NULL, 'alerta_janela_meses',       '6'),
    (NULL, 'alerta_reincidencia_dias',  '90'),
    (NULL, 'email_alertas_ativo',       'false'),
    (NULL, 'email_destinatarios',       '[]')
ON CONFLICT (gerencia, chave) DO NOTHING;
