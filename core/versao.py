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

# 3.9.0 (2026-08-30): performance, parte 2 -- @st.fragment sozinho só
# controla ONDE um rerun acontece; não impede que o trabalho seja refeito
# quando o fragmento é RE-CHAMADO pelo pai (não pelo próprio widget dele).
# Fechando essa lacuna:
#   - components/visao_gerencial.py: as 7 seções (Criticidade, Status
#     Ordem, Tipo de Inspeção, Código de Anomalia, Notas por Período,
#     Planejado×Realizado, Quadro Resumo) viram @st.fragment cada uma
#     (mesmo achado que motivou o 3.8.0: mexer no drill-down de período
#     ou no "mostrar N" do Quadro Resumo recalculava as outras 6 seções
#     inteiras). Cada seção também ganha uma função _calc_*() cacheada
#     (st.cache_data) separada da renderização -- agora, mesmo quando o
#     fragmento PAI (a aba inteira) re-invoca as 7 seções por outro
#     motivo, o cálculo pesado (groupby/pivot/opt do ECharts) só roda de
#     novo se o conteúdo real mudou.
#   - components/heatmap.py: mesmo tratamento nas 3 funções (heatmap,
#     ranking de pátio, série temporal) -- aqui sem fragment extra (cada
#     uma já É uma aba inteira), só separação cálculo/render + cache.
#   - components/unifilar.py: _bar_empilhado_ranking() (usada pelos 3
#     rankings, já fragmentados desde antes) ganha o mesmo tratamento —
#     _calc_ranking() cacheado.
#   - core/exportacao.py (novo): gerar_excel_bytes()/gerar_csv_bytes()
#     cacheados, fonte única -- substituem os helpers duplicados que o
#     3.8.0 tinha criado só dentro de unifilar.py; agora reusados também
#     no Quadro Resumo de visao_gerencial.py (fim da duplicação).
#   - modules/gerencia_dashboard.py: o card de cabeçalho ("Gerência X —
#     Coordenações...") ganha uma linha com o período de Abertura da Nota
#     realmente aplicado (e uma nota de que o RASF tem filtro de período
#     próprio, mesmo padrão de ano vigente) -- pedido do Julio pra deixar
#     explícito de que dia a que dia são as notas mostradas, ainda mais
#     relevante depois do default de "ano vigente" do 3.8.0.
#   Testado em runtime: os 11 _calc_*() novos (7 de visao_gerencial + 3 de
#   heatmap + 1 de unifilar) chamados 2x com o mesmo df/parâmetros dão
#   resultado idêntico e não lançam exceção (cache-safe); os fluxos
#   completos de render_gerencia()/render_gerencia_geral() (agora com as
#   7 seções internas também fragmentadas) continuam rodando ponta a
#   ponta sem exceção; regressões de zoom (3.6.1) e barras espelhadas
#   (3.7.0) re-confirmadas intactas. Mesma limitação de teste do 3.8.0
#   registrada lá: o AppTest não simula fragment-only-rerun -- a redução
#   de reprocessamento em si só é confirmável no navegador real. MINOR --
#   aditivo (funções _calc_*/módulo exportacao.py novos, nenhuma API
#   pública das telas mudou de assinatura).

# 3.9.1 (2026-08-30): corrige etiquetas do Unifilar de Ativo se
# sobrepondo em produção (print real do Julio: nomes de ativo colidindo
# na faixa central com muitos ativos próximos no KM). Causa raiz: o
# "dodge" horizontal (3.7.0) só garantia espaço pra largura da BARRA
# (16px) — a largura real da ETIQUETA (que varia com o tamanho do nome,
# ex. "AMV 334S — Linha 1" bem mais larga que "AMV 1") nunca entrava na
# conta. Corrigido do mesmo jeito que gráficos de barra comuns resolvem
# esse problema (o Julio trouxe um exemplo): nome do ativo virou texto
# ROTACIONADO A 55°, não mais uma etiqueta com caixa branca — texto na
# diagonal ocupa bem menos largura horizontal por ativo. Isso permitiu
# afinar a barra (16px -> 10px) e reduzir o espaçamento mínimo do dodge
# (pedido do próprio Julio: "assim também dá pra diminuir o espaçamento
# entre as barras") sem voltar a sobrepor. Crônico virou um ponto roxo
# (era borda da caixa); a altura total do gráfico cresceu (620px dual /
# 360px empilhado, era 460/320) pra sobrar espaço vertical pro texto
# diagonal sem encostar na barra da via oposta — estimativa sem medição
# real de texto (sem navegador neste ambiente); nomes muito longos podem
# ainda pedir mais altura, a confirmar com o Julio olhando ao vivo.
# Testado em runtime: 8 ativos com nomes longos a 20m de distância entre
# si — todos os rótulos com rotate=55/position=bottom confirmados, dodge
# recalculado com o novo espaçamento mínimo (16px equiv.) continua
# garantindo que nenhum par de barras fica mais perto que isso; teste de
# regressão do 3.7.0 (dual/empilhado/vazio) e do 3.6.1 (zoom sincronizado)
# re-confirmados intactos após ajustar a constante de espaçamento
# hardcoded que o teste antigo tinha. PATCH -- ajuste visual pontual,
# mesmo comportamento/API, corrige bug real de sobreposição.

# 3.9.2 (2026-08-30): ajuste fino do Unifilar de Ativo a partir de print
# real (Julio, mesmo dia): hot-spot crônico virou uma AURA ROXA em volta
# da BARRA (retângulo vazado com brilho, mesma linguagem do anel roxo do
# Unifilar por KM — _serie_anel_cronico), substituindo o pontinho ao lado
# do nome da v3.9.1, que era sutil demais pra notar e usava uma cor
# neutra (#cbd5e1) que em telas pequenas lia como "meio roxo" pra
# QUALQUER ativo, cronico ou não — daí a pergunta certeira do Julio
# ("não deveria ser roxo piscante..."). Nome do ativo cronico também fica
# na cor roxa (reforço). Barra ficou ainda mais fina (10px -> 7px) e o
# espaçamento mínimo do dodge encolheu de novo (pedido do Julio: "diminuir
# ainda mais o espaçamento entre as barras") — o rótulo rotacionado a 55°
# (3.9.1) segue absorvendo a folga que a barra fina não precisa mais.
# Testado em runtime: aura aparece só no ativo com is_cronico=True (não
# no vizinho sem), maior em largura E altura que a própria barra, cor
# roxa correta; nome do ativo cronico com label.color roxo, do não-cronico
# com a cor normal; regressões de zoom, barras (dual/empilhado/vazio) e
# rótulo rotacionado re-confirmadas intactas após atualizar a constante
# de espaçamento hardcoded nos testes. PATCH -- ajuste visual pontual.

# 4.0.0 (2026-08-30): "Modo TV" -- tela nova pra reproduzir em loop numa
# TV/monitor parado (pedido do Julio, coordenador de Jundiaí: TV parada na
# coordenação, conectada por HDMI a um PC/notebook, mostrando as notas e o
# Unifilar do trecho sem ninguém mexer em nada).
#   - modules/modo_tv.py (novo): 3 slides (KPIs, Unifilar completo, Ranking
#     de hot-spots por pátio) girando sozinhos a cada 25s, fixo em
#     Gerência SP / Centro de Trabalho CIJN (Jundiaí). Sidebar e todo
#     controle interativo (sliders, radios, tabela, downloads) escondidos
#     via CSS -- é só pra assistir. Fundo escuro + fonte maior, pra
#     leitura de longe.
#   - O loop NÃO recarrega a página: o login deste app vive só em
#     st.session_state, sem cookie/token persistente (auth/session.py) --
#     um location.reload()/navegação JS derrubaria a sessão a cada troca
#     de slide. Em vez disso, time.sleep()+st.rerun() DENTRO da mesma
#     sessão -- login sobrevive, sessão fica aberta indefinidamente no
#     navegador do PC conectado à TV.
#   - RBAC (pedido do Julio): acesso restrito a admin por enquanto. Campo
#     novo 'acesso_tv' em usuarios (database/schema_modo_tv.sql, rodar
#     manualmente no Supabase) + checkbox "📺 Acesso ao Modo TV" no Painel
#     Admin (criar E editar usuário) -- já pronto pra delegar acesso a uma
#     conta dedicada de kiosk no futuro sem dar admin completo pra ela
#     (auth/permissions.py::can_access_modo_tv: admin sempre acessa,
#     outro perfil só com o campo marcado). Botão "📺 Modo TV" na sidebar
#     só aparece pra quem tem acesso.
#   Limitação consciente desta v1: render_unifilar() hoje é uma função só
#   (gráfico de KM + de Ativo + rankings + tabela) sem como pedir "só uma
#   parte" sem duplicar lógica interna arriscada -- por isso "Unifilar por
#   KM" e "Unifilar de Ativo" saíram como 1 slide só ("Unifilar completo"),
#   não 2 separados como as outras opções pedidas. Documentado no próprio
#   módulo; separar em slides distintos fica pra uma iteração futura se
#   fizer falta na prática.
#   Testado em runtime: guard bloqueia usuário sem 'acesso_tv' (st.error
#   visível, sem renderizar nada do painel) e libera usuário comum COM o
#   campo marcado e admin SEM o campo; filtro de centro_trab=='CIJN'
#   confirmado (exclui nota de outro centro no dataset de teste); CSS
#   injetado; giro de slide confirmado 0->1->2->0 ao longo de rodadas
#   sucessivas (parâmetro _loop=False criado só pra teste -- o AppTest
#   processa st.rerun() de forma síncrona dentro da MESMA chamada,
#   diferente do navegador real que faz round-trip de rede a cada rerun;
#   sem esse parâmetro o teste entrava em loop infinito). MAJOR pela
#   própria regra (tela nova + mudança de schema de banco), mesmo sendo
#   100% aditiva e com RBAC fail-closed (admin-only por padrão) -- nenhuma
#   tela existente muda de comportamento.

# 4.1.0 (2026-08-31): senha provisória padronizada em Sentinel@123 (pedido
# do Julio) -- constante SENHA_PADRAO única em modules/admin_panel.py,
# usada tanto no formulário de criar usuário (já vem pré-preenchida, pode
# trocar na hora) quanto no reset, que virou um BOTÃO ÚNICO ("Resetar para
# a senha padrão") em vez do formulário com campo de texto de antes --
# não precisa mais digitar nada, um clique já reseta pra Sentinel@123.
# Registrado explicitamente (não existe hoje): NÃO há obrigatoriedade de
# troca de senha no primeiro acesso -- sem SMTP confiável pra reset
# autoatendido (auth/recuperar_senha.py), quem não trocar manualmente
# fica com a senha padrão indefinidamente. Candidato de próxima
# funcionalidade se o Julio quiser (campo 'deve_trocar_senha' + tela de
# troca obrigatória interceptando o pós-login).
# Testado em runtime: clicar no botão de reset chama _resetar_senha com
# nova_senha=='Sentinel@123' pro usuário certo (sem exceção, sem mais
# precisar de texto digitado). MINOR -- simplifica um fluxo existente,
# não quebra nada, nenhuma tela nova nem mudança de schema.

# 4.1.1 (2026-08-31): corrige o Modo TV dando "nenhum dado encontrado
# para Jundiaí" mesmo com dado real na base. Causa raiz real: centro_trab
# chega do parser no formato hierárquico completo (ex.: "V.SP.CIJN" —
# core/parser.py::detectar_gerencia_nota já extrai a sigla via
# centro.split(".")[-1]), não a sigla pura "CIJN" — o filtro do Modo TV
# comparava direto com "CIJN" e nunca batia. Corrigido extraindo o último
# segmento (mesma lógica defensiva do parser, cobre tanto formato com
# prefixo quanto sem, e ignora maiúsc./minúsc.). Bônus: quando o filtro
# ainda assim não encontra nada, a tela agora lista os centro_trab reais
# presentes nos dados de SP — identifica na hora se o código fixo mudou,
# sem precisar investigar direto no banco de novo.
#   Achado relacionado, NÃO corrigido aqui (fora do pedido, escopo maior
# — afeta a tela principal, não só o Modo TV): components/filtros.py::
# _opcoes_centros() tem o MESMO problema de fundo — compara as siglas
# puras de CENTROS_POR_GERENCIA (ex. "CIJN") contra os valores brutos
# reais de centro_trab (ex. "V.SP.CIJN"), então a lista "conhecidos"
# nunca bate e todo centro cai como "extra", aparecendo no multiselect
# com o código bruto em vez do nome organizado — sem quebrar o filtro em
# si (a seleção/comparação funciona, só a apresentação fica feia/sem
# priorização). Registrado pra decisão do Julio antes de mexer.
# Testado em runtime: dataset com centro_trab "V.SP.CIJN" e variante
# minúscula "v.sp.cijn" agora é encontrado corretamente (2 notas, exclui
# a de outro centro); cenário sem nenhuma nota de Jundiaí mostra o aviso
# E a lista de centro_trab realmente disponíveis; guard de permissão e
# giro de slides re-confirmados intactos. PATCH -- bugfix, mesmo
# comportamento esperado.

# 4.2.0 (2026-08-31): Modo TV ganha tela de seleção de Gerência +
# Coordenação (pedido do Julio) em vez de Jundiaí fixo no código. Só
# aparece na primeira vez (sidebar normal, widgets visíveis); depois de
# "▶️ Iniciar" fica salva em session_state pro resto da sessão e entra no
# loop de sempre. Gerências disponíveis: só SP e VP — são as únicas com
# CENTROS_POR_GERENCIA (sigla de centro_trab) preenchido em
# core/glossarios.py; as 4 gerências novas (FN/FS/RJ/LC) têm nome de
# coordenação cadastrado mas ainda sem a sigla correspondente (mesma
# limitação de dado já registrada no projeto) — generalizar é só
# preencher esse mapeamento quando o dado existir.
#   Resposta à pergunta do Julio sobre a sessão cair pra tela de login
# sozinha: confirmado em auth/login.py que NÃO existe token/JWT
# persistido nem timeout por tempo — a sessão só cai se o processo do
# Streamlit reiniciar (novo deploy/push, restart do servidor, crash), já
# que o login vive só em st.session_state sem cookie. Documentado
# explicitamente no topo do módulo.
# Testado em runtime: tela de seleção mostra Gerências=[SP,VP] e
# Coordenações reais de SP=[Jundiaí,Paranapiacaba,Piaçaguera]; fluxo
# real de clique (selecionar "Jundiaí" no dropdown + clicar "Iniciar")
# salva tv_gerencia=SP/tv_centro_trab=CIJN/tv_nome_local=Jundiaí
# corretamente em session_state; guard de permissão, filtro de
# centro_trab, giro de slides e diagnóstico de "sem dado" re-confirmados
# intactos depois da escolha. MINOR -- funcionalidade nova compatível,
# rota/permissão/comportamento do loop em si não mudam.

APP_VERSION = "4.2.0"
