-- database/schema_notas_tratamento.sql — Tratamento de Notas (2026-09-05)
--
-- Nova fonte de upload: "Tratamento de Notas GG" — lista as notas VP que já
-- passaram (ou estão passando) pelo fluxo de diagnóstico do Técnico Fiscal
-- (coluna "Status diag ok": Diagnosticada / Diagnosticar). Cruzada com a
-- base de Notas (por numero_nota) pra classificar cada nota em
-- Sim / Não / Pendente Saneamento / Encerrada — Aguarda Baixa no SAP /
-- Não se Aplica — ver core/parser.py::processar_planilha_tratamento e
-- database/queries.py::calcular_diagnosticada.
--
-- Achado real (Julio, 2026-09-05, comparando as duas planilhas): das notas
-- VP "Aberta" que não aparecem no Tratamento, 80,8% já estão com
-- status_final='Encerrado' — não é falta de diagnóstico, é status_usuario
-- que ficou preso em ABER sem ser atualizado junto (daí a categoria
-- "Encerrada — Aguarda Baixa no SAP", separada da "Pendente Saneamento" de
-- verdade).
--
-- Idempotente — seguro rodar mais de uma vez.

CREATE TABLE IF NOT EXISTS notas_tratamento (
    id            BIGSERIAL PRIMARY KEY,
    upload_id     UUID REFERENCES uploads_historico(id) NOT NULL,
    gerencia      VARCHAR NOT NULL,
    numero_nota   BIGINT NOT NULL,
    ordem         VARCHAR,
    status_diag   VARCHAR,   -- valor bruto: 'Diagnosticada' ou 'Diagnosticar'
    data_nota     DATE,
    centro_trab   VARCHAR,
    ramal         VARCHAR,
    trecho        VARCHAR,
    origem        VARCHAR,
    criado_em     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notas_tratamento_numero   ON notas_tratamento(numero_nota);
CREATE INDEX IF NOT EXISTS idx_notas_tratamento_upload   ON notas_tratamento(upload_id);
CREATE INDEX IF NOT EXISTS idx_notas_tratamento_gerencia ON notas_tratamento(gerencia);

COMMENT ON TABLE notas_tratamento IS
    'Upload "Tratamento de Notas GG" — status de diagnóstico (Técnico Fiscal) por nota VP, cruzado com notas.numero_nota pro filtro/gráfico de Diagnosticada.';

-- RLS desligado (mesmo modelo do resto do projeto — segurança na camada do app)
ALTER TABLE notas_tratamento DISABLE ROW LEVEL SECURITY;

-- ============================================================
-- uploads_historico.disciplina — incluir 'TRATAMENTO' no CHECK
-- ============================================================
-- schema_rasf_baseline.sql já tinha ampliado pra ('VP','EE','RASF',
-- 'RASF_BASE'). Aqui só acrescenta 'TRATAMENTO'.
ALTER TABLE uploads_historico DROP CONSTRAINT IF EXISTS uploads_historico_disciplina_check;
ALTER TABLE uploads_historico ADD CONSTRAINT uploads_historico_disciplina_check
    CHECK (disciplina IN ('VP', 'EE', 'RASF', 'RASF_BASE', 'TRATAMENTO'));

-- Verificação
SELECT gerencia, disciplina, status, total_notas, enviado_em
FROM uploads_historico WHERE disciplina = 'TRATAMENTO' ORDER BY enviado_em DESC LIMIT 10;
