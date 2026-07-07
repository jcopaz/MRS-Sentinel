-- ============================================================
-- MRS Sentinel — Schema do Banco de Dados
-- Versão: 1.0.0 | Sprint 1 — Fundação
-- Execute este arquivo no SQL Editor do Supabase
-- ============================================================

-- Habilita extensão de UUID (já ativa no Supabase, por precaução)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ============================================================
-- SESSÃO 1: USUÁRIOS (perfis e permissões)
-- ============================================================
-- Obs: a senha é gerenciada pelo Supabase Auth (auth.users).
--      Esta tabela armazena apenas o perfil e permissões.
-- ============================================================
CREATE TABLE IF NOT EXISTS usuarios (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR UNIQUE NOT NULL,
    nome        VARCHAR NOT NULL,
    perfil      VARCHAR NOT NULL CHECK (perfil IN ('admin', 'assistente', 'usuario')),
    gerencia    VARCHAR CHECK (gerencia IN ('SP', 'VP')), -- NULL = acesso global (admin)
    ativo       BOOLEAN DEFAULT TRUE,
    criado_em   TIMESTAMP DEFAULT NOW(),
    ultimo_login TIMESTAMP,
    criado_por  UUID REFERENCES usuarios(id)
);

-- Comentários explicativos nas colunas
COMMENT ON COLUMN usuarios.perfil IS 'admin=acesso total; assistente=upload+visualização da sua gerência; usuario=só visualização';
COMMENT ON COLUMN usuarios.gerencia IS 'NULL para admin (acesso global). SP ou VP para assistentes.';


-- ============================================================
-- SESSÃO 2: HISTÓRICO DE UPLOADS (auditoria)
-- ============================================================
CREATE TABLE IF NOT EXISTS uploads_historico (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id    UUID REFERENCES usuarios(id) NOT NULL,
    gerencia      VARCHAR NOT NULL CHECK (gerencia IN ('SP', 'VP')),
    disciplina    VARCHAR NOT NULL CHECK (disciplina IN ('VP', 'EE')),
    nome_arquivo  VARCHAR NOT NULL,
    total_notas   INT NOT NULL,
    enviado_em    TIMESTAMP DEFAULT NOW(),
    tamanho_bytes BIGINT,
    metadados     JSONB,
    status        VARCHAR DEFAULT 'ativo'
                  CHECK (status IN ('ativo', 'substituido', 'arquivado'))
);

COMMENT ON TABLE uploads_historico IS 'Auditoria de uploads: quem enviou, quando, quantas notas, qual gerência/disciplina.';


-- ============================================================
-- SESSÃO 3: BASE DE NOTAS (dados operacionais)
-- ============================================================
CREATE TABLE IF NOT EXISTS notas (
    id                  BIGSERIAL PRIMARY KEY,
    upload_id           UUID REFERENCES uploads_historico(id) NOT NULL,
    gerencia            VARCHAR NOT NULL,
    disciplina          VARCHAR NOT NULL,

    -- Identificação
    numero_nota         BIGINT,
    ordem               VARCHAR,

    -- Datas
    data_nota           DATE,
    data_encerramento   DATE,
    data_planejada      DATE,

    -- Localização geográfica
    local_instalacao    VARCHAR,
    ramal               VARCHAR,  -- Sigla canônica (SJU, JIT, RCO...) — UI mostra nome completo
    trecho              VARCHAR,  -- Par Origem-Destino dentro do Ramal
    origem              VARCHAR,  -- Pátio de origem (IPA, IPG...)
    destino             VARCHAR,  -- Pátio de destino
    linha               VARCHAR,
    ativo               VARCHAR,
    km_real             NUMERIC,
    km_fim_real         NUMERIC,
    subsistema          VARCHAR,  -- Só EE: SINALIZ, ENERGIA, TELECOM, WAYSIDE

    -- Classificação
    prioridade          VARCHAR,
    peso_prio           INT,
    score               NUMERIC,
    code_codificacao    VARCHAR,
    defeito_legivel     VARCHAR,
    familia_cod         VARCHAR,
    familia_defeito     VARCHAR,
    tipo_nota           VARCHAR,
    tipo_atividade      VARCHAR,

    -- Status
    status_usuario      VARCHAR,
    status_amigavel     VARCHAR,
    status_final        VARCHAR,
    status_nota_ordem   VARCHAR,

    -- Operacional
    centro_trab         VARCHAR,
    centro_planejamento VARCHAR,
    gerencia_origem     VARCHAR,
    modificado_por      VARCHAR,
    lead_time_dias      INT,

    -- Textos livres
    descricao           TEXT,
    texto_longo         TEXT,
    texto_code          VARCHAR,

    criado_em           TIMESTAMP DEFAULT NOW()
);

-- Índices de performance para filtros mais comuns
CREATE INDEX IF NOT EXISTS idx_notas_gerencia_disciplina ON notas(gerencia, disciplina);
CREATE INDEX IF NOT EXISTS idx_notas_upload ON notas(upload_id);
CREATE INDEX IF NOT EXISTS idx_notas_ramal ON notas(ramal);
CREATE INDEX IF NOT EXISTS idx_notas_trecho ON notas(trecho);
CREATE INDEX IF NOT EXISTS idx_notas_data ON notas(data_nota);
CREATE INDEX IF NOT EXISTS idx_notas_status ON notas(status_usuario);
CREATE INDEX IF NOT EXISTS idx_notas_prioridade ON notas(prioridade);


-- ============================================================
-- SESSÃO 4: CONFIGURAÇÕES POR GERÊNCIA
-- ============================================================
CREATE TABLE IF NOT EXISTS configuracoes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gerencia       VARCHAR,
    chave          VARCHAR NOT NULL,
    valor          JSONB NOT NULL,
    atualizado_por UUID REFERENCES usuarios(id),
    atualizado_em  TIMESTAMP DEFAULT NOW(),
    UNIQUE(gerencia, chave)
);

COMMENT ON TABLE configuracoes IS 'Parâmetros configuráveis por gerência: pesos de score, alertas, etc.';


-- ============================================================
-- SESSÃO 5: LOG DE ACESSOS (auditoria de segurança)
-- ============================================================
CREATE TABLE IF NOT EXISTS logs_acesso (
    id          BIGSERIAL PRIMARY KEY,
    usuario_id  UUID REFERENCES usuarios(id),
    acao        VARCHAR NOT NULL,  -- 'login', 'logout', 'upload', 'view_sp', etc.
    detalhes    JSONB,
    ip          VARCHAR,
    quando      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_usuario ON logs_acesso(usuario_id);
CREATE INDEX IF NOT EXISTS idx_logs_quando ON logs_acesso(quando);


-- ============================================================
-- SESSÃO 6: DADOS INICIAIS — Usuário Admin
-- ============================================================
-- ⚠️ INSTRUÇÃO: Após executar este script:
--   1. Acesse Supabase > Authentication > Users > "Add User"
--   2. Crie um usuário com o email abaixo e uma senha forte
--   3. Execute o INSERT abaixo com o mesmo email
-- ============================================================
INSERT INTO usuarios (email, nome, perfil, gerencia, ativo)
VALUES (
    'seu.email@mrs.com.br',   -- ← Substitua pelo seu email real
    'Administrador MRS',
    'admin',
    NULL,                      -- Admin tem acesso global
    TRUE
)
ON CONFLICT (email) DO NOTHING;

-- ============================================================
-- SESSÃO 7: CONFIGURAÇÕES PADRÃO
-- ============================================================
INSERT INTO configuracoes (gerencia, chave, valor)
VALUES
    ('SP', 'score_alpha_idade', '0.10'),
    ('SP', 'score_mult_dife',   '0.50'),
    ('VP', 'score_alpha_idade', '0.10'),
    ('VP', 'score_mult_dife',   '0.50'),
    (NULL, 'versao_schema',     '"1.0.0"')
ON CONFLICT (gerencia, chave) DO NOTHING;

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
