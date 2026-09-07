# MRS Sentinel — Documentação Técnica (estado em 2026-09-06, v10.0.0)

> Este documento registra COMO o app está montado hoje — pra não perder o que foi
> feito. Não substitui `core/versao.py` (changelog linha a linha, com causa raiz de
> cada bug) nem `README.md` (setup do zero) — complementa os dois com uma foto do
> conjunto: arquitetura, modelo de dados, RBAC, telas, e pendências conhecidas.
>
> Sempre que uma mudança relevante entrar, atualize a seção correspondente aqui
> (não precisa reescrever tudo — só o trecho que mudou) e registre o changelog
> normal em `core/versao.py`, como sempre.

---

## 1. Stack e ponto de entrada

- **Frontend:** Streamlit (`app.py` na raiz), deploy no **Streamlit Community Cloud**
  (mount path `/mount/src/mrs-sentinel`). Auto-deploy no push pro GitHub — **às vezes
  falha silenciosamente/fica desatualizado**; se algo que já foi corrigido continuar
  dando erro, o primeiro passo é confirmar em "Manage app" → Reboot, não assumir bug
  de código de novo.
- **Banco:** Supabase (Postgres + PostgREST), acesso via `database/client.py`
  (`get_supabase()` = client anon, singleton `@st.cache_resource`; `get_supabase_admin()`
  = client com service_role, usado só pra operações administrativas: criar/editar
  usuário, resetar senha). RLS está **desligado** em todas as tabelas do app — a
  segurança é 100% na camada da aplicação (`auth/permissions.py`), não no banco.
- **Gráficos:** ECharts (`streamlit_echarts`) pro Unifilar/heatmaps; Plotly pra
  indicadores da Visão Geral; Folium/`components/mapa_geografico.py` pro mapa
  geográfico (Sprint 6).
- **`app.py`** — ordem de execução: `st.set_page_config` (sempre primeiro) →
  `injetar_css_global()` → `init_session()` → `is_logged_in()`? não → `render_login()`;
  sim + `deve_trocar_senha`? → `render_trocar_senha_obrigatoria()` (bloqueia tudo,
  sem sidebar); sim, senha ok → `render_sidebar()` + `_rotear()` (dict de rotas por
  `st.session_state["pagina"]`, mais o padrão `"gerencia_<sigla>"` genérico).

---

## 2. Autenticação e RBAC

### 2.1 Login (`auth/login.py`, `auth/session.py`)

- Login por **matrícula OU e-mail** no mesmo campo — quem não tem e-mail corporativo
  loga só pela matrícula (e-mail sintético `<matricula>@matricula.sentinel.local` por
  baixo dos panos, só pra satisfazer o Supabase Auth).
- **Sessão vive só em `st.session_state`** — não existe cookie/token persistente.
  Consequência: (a) não há timeout por tempo, a sessão só morre se o processo do
  Streamlit reiniciar (novo deploy, crash, restart do servidor); (b) qualquer
  `location.reload()`/navegação JS derruba a sessão — é por isso que o Modo TV usa
  loop interno (`st.rerun()`) em vez de recarregar a página.
- `auth/session.py` centraliza toda leitura/escrita: `get_usuario()`, `get_perfil()`,
  `get_gerencia()`, `set_usuario()`, `clear_session()`, `set_pagina()`/`get_pagina()`.

### 2.2 Perfis e delegação de Gerência (`auth/permissions.py`)

Três perfis: `admin`, `assistente`, `usuario`. **Regra corrigida em 2026-09-02**
(achado real: um usuário de teste com Gerência SP delegada enxergava todas as outras
Gerências e a Visão Geral): a regra hoje é sobre **ter ou não uma Gerência delegada**
(campo `usuarios.gerencia`), não sobre o nome do perfil.

| | Admin (`gerencia=NULL`) | Assistente/Usuário **com** Gerência | Assistente/Usuário **sem** Gerência (raro) |
|---|---|---|---|
| Ver uma Gerência | ✅ todas | Só a delegada | ✅ todas |
| Ver Visão Geral (SP+VP) | ✅ | ❌ | ✅ |
| Upload de dados | ✅ | Assistente: só a sua · Usuário: ❌ | — |
| Alertas / Visão de Campo | ✅ | ❌ (admin-only, 2026-09-01) | ❌ |
| Modo TV | ✅ | Só se `acesso_tv=True` | idem |
| Painel Admin | ✅ | ❌ | ❌ |

Funções-chave: `can_see_gerencia(sigla)`, `can_ver_visao_geral()`, `can_upload(sigla)`,
`can_manage_alertas(sigla)`, `can_access_modo_tv()`, `can_admin_panel()`.

**Guards reais** (não só o botão sumir da sidebar — um `session_state` velho/manipulado
não contorna): `require_login()`, `require_admin()`, `require_gerencia(sigla)`,
`require_visao_geral()`, `require_upload_permission(sigla)`, `require_modo_tv()`. Estão
no TOPO de cada `render_*()` de tela protegida (`gerencia_dashboard.py`,
`gerencia_geral.py`, `gerencia_placeholder.py`, `alertas.py`, `visao_campo.py`,
`modo_tv.py`, `admin_panel.py`).

### 2.3 Senha (2026-09-02)

- Senha provisória padrão pra toda conta nova E todo reset: `SENHA_PADRAO =
  "Sentinel@123"` (`modules/admin_panel.py`) — fonte única, usada no formulário de
  criação (pré-preenchido) e no botão "Resetar para a senha padrão".
- **Troca obrigatória**: coluna `usuarios.deve_trocar_senha` (ver
  `database/schema_deve_trocar_senha.sql`) setada `True` em toda criação e todo
  reset. Enquanto `True`, `app.py::main()` intercepta o app inteiro com
  `auth/trocar_senha_obrigatoria.py::render_trocar_senha_obrigatoria()` — sem
  sidebar, sem rotas, só sai trocando a senha ou fazendo logout. Troca em si usa a
  API admin do Supabase (`update_user_by_id`), o mesmo mecanismo sem SMTP já usado em
  `auth/recuperar_senha.py` (a rede corporativa da MRS **bloqueia porta de saída
  SMTP por completo** — reset autoatendido por e-mail nunca funciona na prática;
  existe só pra quem tem e-mail corporativo real cadastrado).
- Aba Usuários do Painel Admin mostra coluna "Senha Provisória" (🔑 Pendente / ✅
  Trocada) pra o admin acompanhar quem ainda não trocou.

---

## 3. Modelo de dados (Supabase / Postgres)

Schema base em `database/schema.sql` (v1.0.0, Sprint 1) + uma série de scripts
incrementais (`database/schema_*.sql`) que foram adicionando colunas/tabelas sem
reescrever o baseline — **rode os incrementais na ordem em que foram criados** se for
montar um projeto Supabase do zero. Lista (a maioria idempotente, `ADD COLUMN IF NOT
EXISTS`):

| Arquivo | O que adiciona |
|---|---|
| `schema.sql` | Baseline: `usuarios`, `uploads_historico`, `notas`, `configuracoes`, `logs_acesso`, `alertas` |
| `schema_matricula.sql` | Login por matrícula (e-mail sintético) |
| `schema_usuarios_rls.sql` | Fix de RLS que travava login (ver `core/versao.py` 3.0.0) |
| `schema_gerencias_expandidas.sql` | 6 gerências (SP/VP/FN/FS/RJ/LC) em vez de só SP/VP |
| `schema_organograma.sql` | Estrutura de coordenações/organograma multi-GG |
| `schema_geo.sql` | Marcos geográficos (KMZ) |
| `schema_rasf.sql`, `schema_rasf_baseline.sql` | Tabelas RASF (viva + congelada YoY) |
| `schema_snapshots.sql` | Fotos semanais pra Evolução da Malha |
| `schema_sprint5.sql` | Parâmetros do motor de Alertas |
| `schema_upload_unico.sql` | Reforço da regra "1 upload ativo por gerência+disciplina" |
| `schema_modo_tv.sql` | `usuarios.acesso_tv` |
| `schema_deve_trocar_senha.sql` | `usuarios.deve_trocar_senha` |
| `schema_rls_desligar_tudo.sql` | Garante RLS desligado em todas as tabelas (segurança é só no app) |

### Tabelas principais

- **`usuarios`** — `id, email, nome, perfil, gerencia, matricula, email_gerado,
  auth_user_id, acesso_tv, deve_trocar_senha, ativo, criado_em, ultimo_login,
  criado_por`. `auth_user_id` é salvo direto na criação (pra reset de senha não
  depender de busca paginada no Supabase Auth).
- **`notas`** — a base operacional. Colunas relevantes: `gerencia, disciplina
  (VP/EE), numero_nota, ordem, data_nota, data_encerramento, data_planejada,
  centro_trab, ramal, trecho, origem (pátio), destino, linha, ativo, km_real,
  km_fim_real, subsistema (só EE), prioridade, peso_prio, score, code_codificacao,
  defeito_legivel, familia_cod, familia_defeito, tipo_nota, tipo_atividade,
  status_usuario, status_final, lead_time_dias, upload_id`. `upload_id` referencia
  `uploads_historico` — é assim que a regra de substituição funciona (ver §4).
- **`uploads_historico`** — auditoria de cada upload: quem, quando, gerência,
  disciplina, total de notas, `status` (`ativo`/`substituido`/`arquivado`).
- **`configuracoes`** — chave/valor JSONB, `UNIQUE(gerencia, chave)`. Usada por:
  Score Engine (`score_*`, uma linha por Gerência incl. `GERAL`), limites de alerta,
  metas de indicadores, parâmetros do motor de Alertas, overrides do RASF.
  `gerencia=NULL` = config global (ex.: parâmetros de alerta, versão do schema).
- **`logs_acesso`** — auditoria de ações (login/logout/upload/reset de
  senha/exclusão de usuário/etc.).
- **`alertas`** — hot-spots crônicos e reincidências persistidos (ver §6.3), upsert
  por `chave_alerta` (evita duplicar a cada recálculo).
- **`rasf_ee`**, **`rasf_baseline`**, **`snapshots`**, **`geo_marcos`**,
  **`org_unidades`**, **`org_codigo_sap`**, **`usuario_escopo`** — tabelas
  específicas de RASF/geografia/organograma/snapshots (ver os `schema_*.sql`
  correspondentes pra estrutura completa).

---

## 4. Upload de dados (`modules/data_uploader.py`, `core/parser.py`)

Acesso: admin (qualquer gerência) e assistente (só a sua, `require_upload_permission`).

**Pipeline:** upload → `processar_planilha()` detecta o formato → preview →
confirmar → grava no Supabase.

### 4.1 Formatos de planilha reconhecidos (VP/EE — `core/parser.py::detectar_formato`)

| Formato | Como é identificado | Apelido na UI |
|---|---|---|
| A — Unificada | tem `Status_Final_ok`, **não** tem `Número_da_nota` | "Unificada" |
| B — Notas Abertas | tem `Marcador inic.` | "Notas Abertas" |
| C — Notas Concluídas | tem `Ponto de partida` | "Notas Concluídas" |
| D — SAP Fiori/BW | tem `Número_da_nota` (prioridade sobre os outros) | export novo do Fiori |

Cada formato tem seu próprio dicionário de renomeação de coluna
(`COLUNAS_FORMATO_A/B/C/D`) — o parser converte pro nome canônico interno
(`numero_nota`, `centro_trab`, etc.) antes de gravar.

### 4.2 Disciplinas de upload

`VP` · `EE` · `RASF` (pipeline próprio, tabela `rasf_ee`) · `RASF_BASE` (base
congelada do ano anterior, tabela `rasf_baseline`, habilita comparativo YoY) ·
`TRATAMENTO` (ver §4.4 — status de diagnóstico das notas VP).

### 4.4 Tratamento de Notas → filtro "Diagnosticada" (2026-09-05, v7.0.0)

Quarta fonte de upload: planilha do Técnico Fiscal ("Tratamento de Notas GG"),
mesmo Formato D + coluna extra `Status diag ok` (Diagnosticada/Diagnosticar).
Parser dedicado, mais enxuto que o de VP/EE (sem score/família — é só uma fonte
de status): `core/parser.py::processar_planilha_tratamento()` →
`df_para_registros_tratamento_supabase()` → tabela `notas_tratamento`
(`database/schema_notas_tratamento.sql`). Mesmo padrão anti-duplicação (1 upload
'ativo' por gerência, disciplina='TRATAMENTO' em `uploads_historico`) e mesmo
suporte a arquivo com várias Gerências juntas.

**Classificação `diagnosticada`** (`core/diagnostico.py::calcular_diagnosticada`,
cruza `notas` × `notas_tratamento` por `numero_nota`, calculada ao vivo — nunca
gravada em `notas`, mesmo padrão do score):

| Categoria | Critério |
|---|---|
| Sim | Aparece no Tratamento como "Diagnosticada" |
| Não | Aparece no Tratamento como "Diagnosticar" |
| Pendente Saneamento | Nota Aberta, ausente do Tratamento, `status_final` também "Aberto" — precisa de diagnóstico de verdade |
| Encerrada — Aguarda Baixa no SAP | Nota Aberta, ausente do Tratamento, mas `status_final` já "Encerrado" — só falta regularizar o status_usuario no SAP |
| Não se Aplica | Nota não-Aberta (Cancelada/Concluída) ausente do Tratamento — comportamento normal |

Achado real que motivou a separação das duas últimas categorias (comparação das
planilhas reais, 2026-09-05): das notas VP "Aberta" ausentes do Tratamento,
**80,8%** já tinham `status_final='Encerrado'` — não era falta de diagnóstico, era
`status_usuario` preso em "ABER" sem acompanhar o encerramento real da nota.

Só se aplica a linhas VP (`disciplina_label == "VP"`) — EE fica sempre "Não se
Aplica", não tem esse fluxo. Wired em `modules/gerencia_dashboard.py`
(`_com_diagnosticada()`, chamada logo após `_carregar_dados()`); filtro
"🔍 Diagnosticada" em `components/filtros.py` (com `help=` explicando as 5
categorias) e painel resumo/gráfico em `core/diagnostico.py::render_resumo_
diagnosticada()` (aba KPIs). **Visão Geral e Modo TV ainda não recebem essa
coluna/filtro** — pendente, ver §8.

### 4.3 Regra de substituição (não somar bases)

- Cada upload cria uma linha em `uploads_historico` com `status='ativo'` e associa
  as notas a ela via `notas.upload_id`.
- **Antes de inserir as notas novas**, o upload arquiva (`status='substituido'`)
  qualquer upload anterior da MESMA `gerencia+disciplina` — é assim que "subir uma
  base nova substitui a antiga" em vez de somar.
- `_verificar_arquivamento()` **confirma** que esse arquivamento realmente zerou os
  uploads antigos ANTES de inserir — proteção contra a rede corporativa (proxy/SSL
  instáveis) deixar o UPDATE aplicar só parte do filtro e sobrar 2 uploads "ativo" ao
  mesmo tempo (bug real já visto — nesse caso o Dash somava as duas bases). Se a
  checagem falhar, aborta o upload em vez de arriscar duplicar.
- A leitura (`database/queries.py`, `queries_rasf.py`) tem uma blindagem equivalente
  do lado de quem já estiver duplicado no banco (soma upload_ids de todos os
  "ativo" daquela gerência+disciplina, mas prioriza o mais recente quando há mais
  de um — ver comentário em `_upload_ids_ativos`).
- **Qualquer novo tipo de upload (ex.: Tratamento de Notas) precisa respeitar esse
  mesmo desenho**: upload_id próprio, arquivamento do anterior antes de inserir,
  auditoria em `uploads_historico` (ou tabela irmã com a mesma disciplina).

---

## 5. Score Engine (`core/score_engine.py`)

Fórmula (Sprint 3, estendida na 4.5):

```
Score = Peso Prioridade × Mult. Status (neutro desde 10/07/2026)
      × Mult. Família × Mult. Tipo (CT/PV) × Mult. Tipo de Inspeção
      × (1 + α · anos em aberto)
      × (1 + β · (ocorrências repetidas no mesmo local − 1))
```

- **Config por Gerência** (2026-09-02, depois de uma passagem curta como config
  global no mesmo dia): cada Gerência (SP/VP/FN/FS/RJ/LC) **e** a Geral (usada
  também pelo Modo TV) tem sua PRÓPRIA linha em `configuracoes`
  (`gerencia=<sigla>`, chaves prefixadas `score_`). `carregar_score_config(gerencia)`
  é a fonte única de leitura (cacheada, `ttl=300s`); `calcular_score_dataframe(df,
  cfg)` aplica.
- Toda dimensão multiplicadora (Família, Tipo, Tipo de Inspeção) segue o mesmo
  padrão: **selecionável + peso por item** — só os itens escolhidos ganham peso
  ≠1.0, o resto fica neutro. Família continua com listas separadas VP/EE
  (vocabulário de dado diferente, não é por Gerência). Tipo de Inspeção é dimensão
  nova (nasce OFF/sem peso, pra não recalcular ranking de ninguém sozinho no dia do
  deploy).
- **Painel de configuração**: `Administração → Configurações → 🎯 Score — Pesos e
  Multiplicadores` (`modules/admin_panel.py`). Seletor "Configurando a Gerência" +
  "📸 foto" do estado atual (`render_conteudo_transparencia`, tabelas de peso reais,
  não só ligado/desligado) + botão "💾 Salvar" + botão "♻️ Resetar para o padrão".
  Todo `value=` que lê peso salvo passa por `_clamp()` — sem isso, um peso fora da
  faixa do widget (editado à mão no Supabase, por ex.) quebraria a aba inteira e o
  admin nem conseguiria abrir a tela pra corrigir.
- Upload/parser (`core/parser.py`) e Snapshots (`core/snapshots.py`) **usam
  `ScoreConfig()` padrão fixo, de propósito** — não a config do admin. O score
  gravado no upload é recalculado ao vivo em cada tela de Gerência de qualquer
  forma; os Snapshots (Evolução da Malha) precisam de pesos CONGELADOS pra manter
  o histórico comparável mesmo se o admin mudar pesos depois.

---

## 6. Telas (`modules/*.py`, `components/*.py`)

### 6.1 Gerência (`gerencia_dashboard.py::render_gerencia(sigla)`)

Genérico pra qualquer gerência cadastrada (substituiu os antigos `gerencia_sp.py`/
`gerencia_vp.py` específicos). 7 abas, cada uma isolada em `@st.fragment` (interagir
com um widget de uma aba não recalcula as outras 6 — mobile ficava pesado sem isso):
KPIs, Visão Gerencial, Unifilar Dual (VP+EE por ramal), Heatmap, Ranking, Temporal,
Inteligência EE.

Filtros em cascata na sidebar (`components/filtros.py::render_filtros_cascata`):
Centro de Trabalho → Ramal → Trecho → Pátio → Período (Abertura/Encerramento,
padrão "ano vigente" desde 2026-08-30) → Prioridade/Família/Tipo de
anomalia/Tipo de inspeção/Status Base VP/EE. Filtro de "Centro de Trabalho" já
usa comparação DIRETA contra o valor bruto de `centro_trab` (`.isin()`, sem
parsing de hierarquia) — mesmo mecanismo que o Modo TV passou a usar em
2026-09-02 (ver §6.5).

### 6.2 Visão Geral (`gerencia_geral.py::render_gerencia_geral()`)

Combina SP+VP num painel só (indicadores IMT/DI/Aderência/Lead Time, comparativo,
Unifilar Total, Temporal Global, Ranking unificado). Bloqueada (`require_visao_geral`)
pra quem tem Gerência específica delegada (§2.2).

### 6.3 Alertas (`modules/alertas.py`) — **admin-only desde 2026-09-01**

Motor `core/alertas.py`: hot-spots crônicos (≥N notas da mesma família em M meses,
mesmo ramal+origem) e reincidência (reabertura ≤X dias). Parâmetros em
`Administração → Configurações → 🚨 Alertas Automáticos`.

### 6.4 Visão de Campo (`modules/visao_campo.py`) — **admin-only desde 2026-09-01**

Tela mobile-first enxuta (KPIs grandes + top-N prioridades + alertas resumidos).

### 6.5 Modo TV (`modules/modo_tv.py`) — **corrigido em 2026-09-02, v6.1.0**

Painel em loop pra TV/monitor de uma coordenação (pedido original: TV parada na
coordenação de Jundiaí). Login persiste via loop interno (`time.sleep()` +
`st.rerun()`, sem recarregar o navegador). Histórico do bug (documentado em detalhe
no cabeçalho do módulo): tentou filtrar por "Coordenação" derivada de `centro_trab`
duas vezes (sigla da coordenação, depois lista de pátios) e nunca funcionou de
verdade. **Solução final**: abandona "Coordenação" — a tela de seleção pergunta
Gerência + Centro(s) de Trabalho (multiselect com valores REAIS presentes nos
dados) + Trecho opcional, e o filtro é `.isin()` direto contra `centro_trab`, igual
ao resto do app. Funciona pra qualquer gerência com dado carregado, não só SP/VP.
3 slides: KPIs, Unifilar, Ranking de hot-spots. Acesso: admin sempre, ou
`acesso_tv=True` delegado no Painel Admin.

### 6.6 Evolução da Malha (`modules/evolucao_malha.py`)

Compara indicadores da base viva entre dois períodos (semanal/mensal), a partir de
fotos semanais automáticas (`core/snapshots.py`, tabela `snapshots`).

### 6.7 Inteligência EE (`components/inteligencia_ee.py`, aba dentro de Gerência)

Recorte unifilar de falhas EE a partir do RASF (PG-ENG-0088). Visão Macro (cards +
mapa de falhas por trecho + heatmap Pátio×Origem + tendência) e Visão Micro
(detalhamento nota a nota, quebra por Sintoma/Objeto/Problema). Comparativo YoY
usa a base congelada (`rasf_baseline`, upload disciplina `RASF_BASE`).

### 6.8 Painel Admin (`modules/admin_panel.py`) — só admin

4 abas: **Usuários** (CRUD, senha provisória, acesso Modo TV, exclusão definitiva
com trava de confirmação), **Logs de Acesso**, **Configurações** (km de malha,
limites de alerta IMT, metas dos indicadores, 🎯 Score, 🚨 Alertas, ℹ️ Info do
sistema), **Gestão de Dados**.

---

## 7. Convenções do projeto

- **Versão única**: `core/versao.py::APP_VERSION`, changelog linha a linha logo
  acima (causa raiz + o que foi testado em runtime + classificação
  PATCH/MINOR/MAJOR). Bump em TODO commit que muda comportamento — MAJOR é mais
  abrangente que o SemVer clássico aqui: tela nova, mudança de schema, correção de
  segurança OU de integridade de dado já contam como MAJOR.
- **Fonte única**: quando a mesma lógica apareceria em 2 lugares, vira uma função
  compartilhada (`database/queries.py::get_config/salvar_config`,
  `core/exportacao.py` pros exports Excel/CSV, `SENHA_PADRAO`, etc.) em vez de
  duplicar.
- **Fail closed / bloqueio real**: toda tela restrita tem um `require_*()` no
  próprio topo da função de render, não só o botão escondido na sidebar.
- **Testes**: sem browser real neste ambiente — validação via `python -m
  py_compile` (sintaxe) + `streamlit.testing.v1.AppTest` (fluxo real: cliques,
  formulários, session_state, exceções), com um stub de `streamlit_echarts` (versão
  instalada no sandbox não é compatível com o runtime de componente do Streamlit
  1.57 — não é regressão do app, é só limitação de teste local).

---

## 8. Pendências conhecidas (em 2026-09-06)

- **"GC" — nome ainda não confirmado**: virou Gerência própria no 9.0.0 (ver
  §3), mas `core/glossarios.py::NOME_GERENCIA["GC"]` está com um placeholder
  explícito ("Gerência GC (nome a confirmar)") até o Julio dizer o que a sigla
  significa de verdade.
- **Diagnosticada — Visão Geral e Modo TV**: o filtro/coluna (§4.4) só está
  ligado nas telas de Gerência (`gerencia_dashboard.py`). Visão Geral
  (`gerencia_geral.py`) e Modo TV (`modules/modo_tv.py`) ainda carregam as
  notas sem essa coluna — fast-follow, se o Julio confirmar que quer lá também.
- **Rodar `database/schema_notas_tratamento.sql` no Supabase** antes do primeiro
  upload de Tratamento de Notas (cria a tabela `notas_tratamento` e amplia o
  CHECK de `uploads_historico.disciplina`) — mesmo processo dos scripts
  incrementais anteriores.
- **Password reset por e-mail** (`auth/recuperar_senha.py`) não funciona de fato na
  rede da MRS (SMTP de saída bloqueado) — existe só pra quando/se isso mudar.
- **Gerências FN/FS/RJ/LC** têm nome de coordenação cadastrado mas ainda sem sigla
  de `centro_trab` mapeada em `core/glossarios.py::CENTROS_POR_GERENCIA` — Modo TV
  e outras telas já funcionam pra elas assim que houver dado carregado (não dependem
  mais desse mapeamento), mas alguns relatórios que ainda usam
  `CENTROS_POR_GERENCIA`/`COORDENACOES_POR_GERENCIA` diretamente ficam limitados a
  SP/VP até essas listas serem preenchidas.
