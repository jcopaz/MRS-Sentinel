# core/versao.py — Versão única do MRS Sentinel (SemVer: MAJOR.MINOR.PATCH)
#
# Fonte única — antes existiam 2 constantes "APP_VERSION" hardcoded e
# desincronizadas (auth/login.py e modules/home.py) mais uma terceira
# string solta em modules/admin_panel.py, nenhuma delas mudando a cada
# release. Daqui pra frente, todo commit que muda comportamento do app
# bump essa versão — mesmo critério já adotado no Gestão_OS/SGO
# Eletroeletrônica (regra de mercado, mas com MAJOR mais abrangente que o
# SemVer clássico):
#   PATCH: correção pontual sem mudar comportamento/fluxo — bugfix, texto,
#          cor, espaçamento, digitação.
#   MINOR: funcionalidade nova mas compatível com o que já existia — toggle,
#          filtro, opção nova num formulário já existente.
#   MAJOR: tela/aba nova, reorganização de fluxo, correção de segurança,
#          correção de integridade de dado, ou mudança de schema de banco —
#          qualquer coisa que mude COMO uma funcionalidade inteira funciona.
#   Se um commit mistura tipos, sobe pelo nível MAIS ALTO presente.
#
# 2.0.0 (2026-08-25): sessão com telas novas (seleção de Gerência Geral,
# dashboard genérico pras 4 gerências novas), 4 schemas de banco novos,
# correção de bug de sessão Auth compartilhada entre usuários e correção
# de integridade de dado (notas de Barão de Juparanã caindo na gerência
# errada) — MAJOR pela própria regra acima.
# 2.0.1 (2026-08-25): corrige NameError em core/parser.py — import de
# COORDENACAO_REALOCADA esquecido no commit do 2.0.0, quebrava todo upload.
# 2.0.2 (2026-08-25): auth/login.py::_autenticar mostra o erro real do
# Supabase em vez da mensagem genérica — diagnóstico temporário pra achar
# por que login com senha confirmada correta (testada via curl direto no
# Supabase) falhava pelo app. Reverter a mensagem amigável depois.
# 3.0.0 (2026-08-25): correção de segurança — RLS estava ligado na tabela
# usuarios sem nenhuma policy pra chave anon (achado real: linha existia
# no banco mas a chave anon usada pelo app sempre via lista vazia, é a
# causa raiz do login travado do Julio), corrigido com
# schema_usuarios_rls.sql. Reverte também o diagnóstico temporário do
# 2.0.2, que expunha em texto se um e-mail/matrícula existe no sistema e
# o erro cru do Supabase — voltou a mostrar só a mensagem genérica. MAJOR
# pela própria regra acima (correção de segurança).
# 3.1.0 (2026-08-25): Painel Admin ganha "Excluir Definitivamente" usuário
# (apaga de usuarios + Supabase Auth, bloqueia com erro claro se o
# usuário já tiver upload/log vinculado) — funcionalidade nova compatível
# com o que já existia (desativar continua igual). MINOR.
# 3.2.0 (2026-08-28): filtro novo "Tipo de anomalia" (código + descrição,
# mais granular que Família de defeito) abaixo dele nos filtros de
# atributo; ranking de Ativo da aba Unifilar passa a usar os campos
# linha/ativo já decodificados do TPLNR (rótulo "AMV 22 — Linha 2" em vez
# do TPLNR bruto abreviado) — é o "Unifilar de Ativo" pedido por um
# técnico na apresentação da ferramenta. Funcionalidade nova/melhorada
# compatível com o que já existia. MINOR.
# 3.3.0 (2026-08-28): "Unifilar de Ativo" de verdade — gráfico de bolhas
# no eixo de KM (igual ao Unifilar principal, eixo alinhado), mas cada
# bolha é um Ativo específico em vez de um trecho de KM, respeitando o
# mesmo recorte de Ramal/Trecho/KM já filtrado. Complementa o ranking em
# barras adicionado no 3.2.0 — agora dá pra ver visualmente ONDE no KM os
# ativos problemáticos se concentram, não só a lista ordenada. MINOR.

# 3.4.0 (2026-08-28): "Unifilar de Ativo" ganha modo Dual (topo=Abertas,
# base=Concluídas), espelhando o mesmo modo do Unifilar por KM — antes
# misturava tudo numa linha só, o que escondia a comparação entre o que
# ainda está pendente e o que já foi atuado no mesmo ativo. MINOR.

# 3.4.1 (2026-08-28): corrige vazamento de conexao HTTP em
# criar_cliente_auth_temporario() (auth/login.py) -- cada tentativa de
# login criava um client novo e nunca fechava; sob varios logins
# seguidos (comum numa depuracao), acumulava conexoes abertas no
# processo ate faltar recurso pra chamadas nao relacionadas (ex.: "Erro
# ao buscar notas: [Errno 11] Resource temporarily unavailable"). Nova
# fechar_cliente_temporario() em database/client.py, chamada num
# finally. PATCH -- bugfix, sem mudar comportamento esperado.

# 3.5.0 (2026-08-28): Unifilar de Ativo agora responde ao zoom do Unifilar
# por KM -- arrastar o slider (ou dar scroll) no grafico principal
# estreita automaticamente o recorte de KM do grafico de Ativo logo
# abaixo, sem precisar de nenhum filtro manual novo. Usa o suporte a
# eventos do streamlit-echarts (events={"datazoom": ...}) pra capturar o
# zoom do lado do JS e devolver pro Python, guardado em session_state
# pra sobreviver a reruns de outra origem. Cada zoom dispara um rerun do
# Streamlit -- pode ficar um pouco mais lento durante o arrasto continuo
# do slider, sem jeito simples de evitar com essa biblioteca; reportar
# se sentir lentidao real de uso. MINOR (funcionalidade nova compativel).

# 3.6.0 (2026-08-28): Repaginação UI/UX + Responsividade. Nasce o DESIGN
# SYSTEM único (core/tema.py) — fim das cópias de COR_PRIMARIA/COR_CRIT/... que
# viviam duplicadas em 7 arquivos (mesmo problema de "fonte única" que motivou
# core/versao.py e core/glossarios.py). Nasce a camada de UI global
# (core/ui_global.py): CSS GLOBAL RESPONSIVO injetado 1x em app.py (@media pra
# tablet<=1200px e mobile<=768px; grid fluida de KPIs 4->2->1 colunas;
# tipografia com clamp()), helper altura_responsiva() pra trocar os 34
# height="XXXpx" fixos por altura relativa a vh, e o componente reutilizável
# radar-pulse (pulso + anel concentrico) que leva o "DNA do Unifilar" pros KPIs
# e Alertas SEM tocar em components/unifilar.py (que segue INTOCADO, a pedido
# do Julio). components/kpi_card.py e modules/alertas.py repaginados (hover
# elevado, fade-up, KPI de criticidade pulsa quando >=40%, barra de severidade
# animada nos alertas criticos). Auditoria: antes havia @media=0 no projeto
# inteiro. Nenhuma mudanca de schema, RBAC, filtros ou logica de negocio —
# so estilo/UX. MAJOR pela propria regra (reorganizacao de fluxo visual +
# nova camada de app), MINOR no espirito (100% retrocompativel, APIs publicas
# preservadas). Adotado 3.6.0 (MINOR) por ser aditivo e nao quebrar nada.

# 3.6.1 (2026-08-29): corrige o zoom do Unifilar por KM nunca "pegar" no
# Unifilar de Ativo (relatado pelo Julio: "nao esta sendo responsivo").
# Causa raiz real: a cada rerun, o dataZoom do grafico principal era
# remontado do zero SEM start/end explicitos -- o ECharts entao resetava
# visualmente o zoom pra 0-100%, o que disparava um NOVO evento "datazoom"
# (0-100%) que sobrescrevia em session_state o zoom que o usuario tinha
# acabado de aplicar. O zoom "brigava" com o proprio rerun e nunca ficava
# de pe. Corrigido persistindo start/end (lidos de session_state) no
# dataZoom do grafico principal a cada remontagem -- validado em runtime
# via AppTest com um stub de streamlit_echarts (2 fases: sem zoom salvo =
# 0/100, com zoom salvo = 20/60 refletido na remontagem). PATCH -- bugfix,
# sem mudar comportamento esperado (o pedido original do zoom sincronizado
# ja tinha sido feito no 3.5.0; aqui so' conserta o que estava quebrado).

# 3.7.0 (2026-08-29): "Unifilar de Ativo" redesenhado de bolhas pra BARRAS
# ESPELHADAS por KM (ideia do Julio, validada com protótipos comparativos
# antes de codar -- 4 alternativas avaliadas: treemap, ranking em barras,
# bolhas com jitter, e a escolhida). Bolhas se atropelavam quando varios
# ativos ficavam proximos no KM (mesmo bug que motivou a correcao 3.6.1);
# agora cada ativo vira 1 par de barras de largura FIXA que "empurra" a
# vizinha (dodge horizontal em KM, ver docstring de render_unifilar_ativo)
# em vez de se sobrepor. Modo Dual: topo = score das notas Abertas
# (cresce a partir da linha "Via Abertas"), base = score das Concluidas
# (espelhado, cresce a partir da linha "Via Concluidas") -- mesmo criterio
# de score/cor/cronico/top-10% do resto do Unifilar. Nome do ativo agora
# fica numa etiqueta na faixa vazia ENTRE as duas linhas de referencia
# (nao mais flutuando em cima da bolha/barra). construir_serie_unifilar_
# ativo() ganhou 3 colunas novas em `agreg` (tooltipHTML/is_top/is_cronico)
# -- aditivo, pn/pp/pc do retorno original preservados intactos. Testado
# em runtime via AppTest (dual/empilhado/vazio, dodge com ativos a 20-50m
# de distancia, deteccao de hotspot) e a regressao do fix 3.6.1 (zoom
# sincronizado) re-confirmada intacta. MINOR (repaginação de uma
# visualização existente, comportamento geral e API preservados).

# 3.8.0 (2026-08-30): performance -- Julio relatou o site "muito pesado e
# demorado" no celular, principalmente no Unifilar, a ponto de nao
# conseguir usar. Causa raiz real: st.tabs() executa o codigo Python de
# TODAS as abas em TODO rerun -- so' esconde a inativa via CSS (limitacao
# conhecida do Streamlit, nao bug). Sem isolamento, mexer num widget
# dentro de UMA aba (ex.: o slider de KM do Unifilar) recalculava as
# outras 6 abas inteiras a cada interacao -- KPIs, Visao Gerencial,
# Heatmap, Ranking, Temporal e Inteligencia EE, cada uma com varios
# graficos ECharts/Plotly. No celular isso travava a tela.
#   - modules/gerencia_dashboard.py e modules/gerencia_geral.py: as 7
#     abas de cada tela viram @st.fragment (funcao aninhada, mesmo padrao
#     ja usado com sucesso nos rankings de components/unifilar.py e nos 6
#     fragments de components/inteligencia_ee.py -- nao inventei nada
#     novo, generalizei o que ja funcionava). Interagir com um widget de
#     UMA aba agora reage sozinho, sem recalcular as outras 6.
#   - components/unifilar.py: render_tabela_completa_unifilar() tambem
#     virou @st.fragment (o seletor "Mostrar" nao recalcula mais o
#     grafico de KM/Ativo/rankings acima); Excel/CSV do recorte
#     exportavel agora sao cacheados por conteudo (_gerar_excel_unifilar/
#     _gerar_csv_unifilar, st.cache_data) -- antes eram regerados do zero
#     em TODO rerun da aba, mesmo sem ninguem clicar em baixar.
#   - Filtro de "Abertura da Nota" (components/filtros.py) e periodo do
#     RASF (components/inteligencia_ee.py) agora comecam no ANO VIGENTE
#     (1o/jan do ano corrente) em vez do historico completo desde 2018 --
#     menos dado processado por padrao em toda tela (KPIs, graficos,
#     export), some sozinho ano que vem (deriva de date.today().year).
#     Gerencia nova (nota mais antiga posterior ao 1o/jan) cai pra data
#     real, nunca abre um recorte padrao vazio; quem quiser ver anos
#     anteriores ajusta o filtro manualmente.
#   Limitacao de teste registrada: o harness AppTest usado pra validar
#   este projeto NAO simula fragment-only-rerun (sempre reexecuta o
#   script inteiro a cada .run(), confirmado com um teste minimo
#   dedicado) -- entao a reducao de reprocessamento em si so' e'
#   confirmavel no navegador real, nao neste sandbox. O que FOI validado
#   em runtime: os fluxos completos de render_gerencia() e
#   render_gerencia_geral() (14 abas fragmentadas) rodam ponta a ponta
#   sem excecao com dados sinteticos e as funcoes de render REAIS (nao
#   mockadas); os 3 cenarios do novo default de data (historico desde
#   2018, gerencia nova, sem coluna data_nota) e o efeito real do filtro
#   RASF; e as regressoes de zoom sincronizado (3.6.1) e barras
#   espelhadas (3.7.0) continuam intactas. MAJOR -- reorganizacao de
#   fluxo de execucao que atinge as 14 abas das duas telas principais do
#   app (regra de versionamento: reorganizacao de fluxo = MAJOR, mesmo
#   sem quebrar nenhuma API publica nem comportamento visivel esperado).

APP_VERSION = "3.8.0"
