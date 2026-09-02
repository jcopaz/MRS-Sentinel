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

# 4.2.1 (2026-08-31): corrige de vez o "sem dado" do Modo TV (a correção
# do 4.1.1 tinha ficado incompleta) + botão de sair. Diagnóstico real
# trazido pelo Julio: os centro_trab realmente presentes em SP são
# "E.SP.IPA, E.SP.IPG, V.SP.IPA, V.SP.IPG, V.SP.PJU" — nenhum contém
# "CIJN". Causa raiz de verdade: centro_trab NÃO termina na sigla da
# coordenação — termina no PÁTIO (core/glossarios.py::PATIOS_POR_CENTRO:
# CIJN → [IJN, ILA, IAB]). "V.SP.IPA" é o pátio IPA, que pertence à
# coordenação CIPA (Piaçaguera), não a CIJN. O filtro do 4.1.1 comparava
# o último segmento contra a sigla da coordenação inteira — nunca ia
# bater, porque essa sigla nunca aparece sozinha no dado.
#   Corrigido comparando contra a LISTA de pátios da coordenação
# (PATIOS_POR_CENTRO[sigla]), não mais uma sigla única — COORDENACOES_TV
# agora é {gerência: {nome: [pátios]}}, encadeando
# COORDENACOES_POR_GERENCIA → CENTROS_POR_GERENCIA → PATIOS_POR_CENTRO.
# tv_centro_trab virou tv_patios (lista) em session_state.
#   Achado dos dados reais nesse mesmo diagnóstico (não é mais bug de
# código): os dados de SP carregados até agora só têm pátios de
# Piaçaguera (IPA) e Paranapiacaba (IPG) + um "PJU" não catalogado em
# PATIOS_POR_CENTRO — nenhum pátio de Jundiaí (IJN/ILA/IAB) ainda. É
# upload pendente pra essa coordenação, não um bug de filtro.
#   Botão "🚪 Sair do Modo TV" (pedido do Julio): fica visível o tempo
# todo durante o loop (removido stButton da lista de seletores CSS
# escondidos — nenhum st.button "solto" aparecia nos slides mesmo, só
# st.download_button, que continua escondido por seu próprio testid).
# Limpa as chaves de sessão do Modo TV e navega de volta pra
# gerencia_<sigla> — sai de vez, não só reseta a escolha.
# Testado em runtime: filtro com pátios reais (V.SP.IJN maiúsculo +
# v.sp.ila minúsculo) encontra as 2 notas de Jundiaí, exclui a de IPA;
# cenário sem nenhum pátio de Jundiaí mostra o aviso com a lista de
# pátios esperados + diagnóstico dos centro_trab reais; clique no botão
# de sair confirmado limpando tv_gerencia e navegando pra 'gerencia_sp';
# guard de permissão, seleção e giro de slides re-confirmados intactos.
# PATCH -- bugfix + ajuste de fluxo, mesma API/rota.

# 5.0.0 (2026-09-01): três pedidos do Julio no mesmo lote.
#   (1) "Alertas Automáticos" e "Visão de Campo" (modules/alertas.py,
# modules/visao_campo.py) viram admin-only — "não faz sentido da maneira
# que está" pros outros perfis. Bloqueio real via require_admin() (novo
# guard usado, já existia em auth/permissions.py sem nenhum caller até
# agora) no topo das duas telas, não só o botão sumindo da sidebar
# (modules/home.py::_render_nav_buttons) — acesso direto por
# session_state["pagina"] antigo também cai no guard.
#   (2) Score sai do sidebar de cada Gerência (SP/VP/Geral tinham cada
# uma o SEU expander "⚙️ Score", nenhum deles salvava nada — resetava pro
# padrão a cada F5/sessão) e vira UM painel só em Administração →
# Configurações → "🎯 Score — Pesos e Multiplicadores", persistido de
# verdade (tabela configuracoes, gerencia=NULL — config global pra SP, VP,
# Geral e Modo TV; decisão registrada no cabeçalho de core/score_engine.py
# por não ter sido confirmada explicitamente antes de codar: os 3
# expanders antigos já usavam os mesmos valores padrão, então não perde
# nada de fato hoje). Peso de Prioridade migrou junto, como pedido. Toda
# dimensão multiplicadora passa a seguir o mesmo padrão "selecionável +
# peso por item" (pedido explícito): Família de defeito (VP e EE
# continuam com listas separadas — vocabulário diferente, não é
# por-Gerência) e Tipo (CT/PV) ganharam esse tratamento; Tipo de Inspeção
# é DIMENSÃO NOVA no score (Ronda/Drone/Trackstar/etc., mesmo catálogo
# dinâmico do filtro homônimo) — nasce OFF e sem peso salvo, então ninguém
# tem o próprio score recalculado sozinho no dia do deploy. render_score_
# sidebar() foi removido de vez (core/score_engine.py); carregar_score_
# config() (cacheada, ttl=300, invalidada na hora do save) é a nova fonte
# única, chamada por gerencia_dashboard.py, gerencia_geral.py e também
# modo_tv.py (Modo TV usava ScoreConfig() puro/hardcoded antes — passa a
# refletir os mesmos pesos configurados). _get_config/_salvar_config
# também saíram de dentro de modules/admin_panel.py e viraram fonte única
# em database/queries.py (get_config/salvar_config), pra score_engine.py
# poder ler sem import circular. Upload/parser (core/parser.py) e
# snapshots (core/snapshots.py) NÃO foram alterados de propósito — o
# score ali continua com pesos de fábrica fixos (congelado, pra manter
# histórico comparável mesmo se o admin mudar pesos depois).
#   (3) Bugfix: st.date_input de "Abertura da Nota"/"Encerramento da
# Nota" (components/filtros.py, na sidebar) parecia sempre vazio ao
# clicar — não estava vazio, a REGRA CSS genérica que pinta todo texto da
# sidebar de branco (pensada pros textos sobre o fundo escuro da sidebar,
# modules/home.py) também pintava de branco o valor dentro do campo de
# data, que o BaseWeb renderiza sobre fundo claro — texto branco em caixa
# branca, invisível. Corrigido com uma regra mais específica (cor preta,
# sem mexer no fundo, que já era o padrão claro do próprio BaseWeb) que
# vence a genérica na cascata.
# Testado em runtime (AppTest): guard bloqueia usuario/assistente nas 2
# telas sem exceção e com mensagem clara, admin continua vendo os 2
# botões na sidebar e usuário comum não vê nenhum dos dois; carregar_
# score_config() cai nos padrões de código quando não há nada salvo ainda
# (idênticos aos que os 3 expanders antigos usavam); aba Configurações
# renderiza o novo painel sem exceção; clique em "Salvar Configuração de
# Score" grava as 12 chaves esperadas em configuracoes.
# MAJOR -- reorganização de fluxo (Score sai do sidebar, vira config
# persistida) + restrição de acesso a 2 telas inteiras.

# 5.1.0 (2026-09-01): Julio pediu de volta, ainda no mesmo dia, o que o
# 5.0.0 tinha simplificado pra config única: "pode haver mais de uma
# configuração distinta para cada Gerência Local". core/score_engine.py::
# carregar_score_config() ganhou o parâmetro `gerencia` obrigatório — cada
# Gerência (SP/VP/FN/FS/RJ/LC) e a Geral/Modo TV voltam a ter sua PRÓPRIA
# linha em `configuracoes` (coluna gerencia = a sigla), como já era antes
# do 5.0.0, só que agora salvo de verdade (motivo do 5.0.0 original).
# Todos os 3 callers (gerencia_dashboard.py, gerencia_geral.py, modo_tv.py)
# passam a sigla certa. O painel em Administração ganhou um seletor
# "🏭 Configurando a Gerência" (SP/VP/FN/FS/RJ/LC/GERAL) — toda a edição
# abaixo dele é daquela Gerência; troquei os keys dos widgets pra incluir
# a Gerência no prefixo (cfg_score_{GER}_...), senão editar SP e trocar
# pra VP mostraria o valor ainda não salvo de SP (widget com key fixa
# ignora o value= depois da 1ª renderização).
#   Dois pedidos extras no mesmo lote: (1) "📸 foto" de como a Gerência
# selecionada está calculando o score AGORA, mostrada ANTES dos controles
# de edição — core/score_engine.py::render_conteudo_transparencia() é o
# conteúdo de render_painel_transparencia() extraído sem o st.expander
# embutido (Streamlit não permite expander dentro de expander, e o
# painel de Score já é um expander); (2) botão "♻️ Resetar para o padrão"
# por Gerência — grava de volta os *_PADRAO de código e limpa os
# session_state daquela Gerência (senão os widgets, por terem key fixa,
# continuariam mostrando o valor antigo mesmo com o banco já resetado).
#   Achado ao testar o reset: number_input com min/max fixo (0–5) quebra a
# aba INTEIRA se o valor salvo estiver fora da faixa (ex.: editado à mão
# no Supabase) — StreamlitValueAboveMaxError, e aí o admin nem consegue
# abrir a tela pra corrigir. Corrigido com _clamp() (novo helper em
# admin_panel.py) em todo `value=` que lê peso salvo — só afeta a exibição,
# o cálculo real em core/score_engine.py não impõe faixa nenhuma.
# Testado em runtime (AppTest): config salva só pra SP não vaza pra VP
# (isolamento real); painel renderiza com o seletor certo (7 opções,
# default SP); clique em Salvar grava as 12 chaves com gerencia='SP';
# clique em Resetar (com SP pré-sujo, inclusive com um peso fora da faixa
# 0–5) grava os padrões de fábrica e o widget na tela já reflete isso,
# sem quebrar.
# MINOR -- capacidade nova (seletor por Gerência, foto do estado atual,
# reset ao padrão) sobre a mesma tela introduzida no 5.0.0 no mesmo dia.

# 5.1.1 (2026-09-01): o fix de CSS do 5.0.0 pro st.date_input (Abertura/
# Encerramento da Nota) não resolveu — Julio confirmou com print, campo
# continuava em branco. A tentativa anterior só forçava `color` no
# `<input>`; o texto visível do BaseWeb provavelmente está num <div>/<span>
# interno, não direto no input (mesma armadilha já registrada com BaseWeb
# no app irmão Gestão_OS: precisa pintar TODOS os descendentes, não
# elemento por elemento). modules/home.py::_inject_sidebar_css() reforçado:
# `*` dentro de [data-testid="stDateInput"] pinta tudo de preto, com
# exceção explícita do <label> ("Início"/"Fim"), que volta a branco (regra
# mais específica que a wildcard, continua legível sobre o fundo escuro da
# sidebar); fundo do <input> passa a #ffffff forçado (antes ficava
# "transparent", dependendo do padrão do próprio BaseWeb — mais frágil).
# Não pôde ser validado visualmente neste sandbox (sem navegador real) —
# só sintaxe/CSS revisados; aguardando confirmação do Julio em produção.
# PATCH -- bugfix (correção de um fix que não pegou).

# 6.0.0 (2026-09-02): dois achados reais do Julio testando com um usuário
# de teste, ambos de segurança/escopo de dado.
#
#   (1) RBAC de Gerência estava furado pro perfil "usuario": criou uma
# conta usuário com Gerência SP delegada e ela enxergava TODAS as outras
# Gerências (botão habilitado na sidebar pra cada uma) e também a Visão
# Geral (SP+VP combinadas) — mais que o escopo dela. Causa raiz:
# auth/permissions.py::can_see_gerencia() tinha uma regra explícita
# "Usuário: pode ver tudo (somente leitura)", só "Assistente" era restrito
# à própria Gerência. Corrigido: a regra agora é sobre TER ou NÃO uma
# Gerência delegada (campo `gerencia` do cadastro), não sobre o nome do
# perfil — com Gerência delegada (usuario OU assistente), só ela, nem
# Visão Geral; sem Gerência delegada (gerencia=NULL, hoje só acontece com
# Admin/contas globais), vê tudo. Nova can_ver_visao_geral() com a mesma
# regra. E — mais importante — o bloqueio deixou de ser só o botão sumir
# da sidebar: require_gerencia(sigla)/require_visao_geral() (novos guards
# em auth/permissions.py) entram no TOPO de render_gerencia() (dashboard
# genérico), render_gerencia_placeholder() (Gerências ainda sem dashboard)
# e render_gerencia_geral() — um session_state velho/manipulado não
# contorna mais o bloqueio, mesmo padrão de defesa já usado pra
# Alertas/Visão de Campo (require_admin, 2026-09-01).
#
#   (2) Criou um usuário de teste e não foi pedido pra trocar a senha
# provisória — toda conta nova (e todo reset de senha) nasce/volta pra
# SENHA_PADRAO ("Sentinel@123", igual pra todo mundo) e não havia
# NENHUMA obrigatoriedade de troca (limitação já documentada antes — sem
# SMTP confiável pra reset autoatendido, a rede corporativa bloqueia porta
# de saída SMTP). Novo campo usuarios.deve_trocar_senha (ver
# database/schema_deve_trocar_senha.sql — rodar no Supabase) setado TRUE
# em toda criação (_criar_usuario) e todo reset (_resetar_senha) de
# usuário em modules/admin_panel.py. Nova tela
# auth/trocar_senha_obrigatoria.py intercepta o app INTEIRO em
# app.py::main() (antes de sidebar/rotas) enquanto esse campo for TRUE —
# só sai trocando a senha (API admin do Supabase, mesmo mecanismo sem
# SMTP já usado em auth/recuperar_senha.py e no reset do admin) ou fazendo
# logout. Aba Usuários do Painel Admin ganhou coluna "Senha Provisória"
# (🔑 Pendente / ✅ Trocada) pro admin ver quem ainda não trocou.
#
# Testado em runtime (AppTest): usuário com Gerência SP delegada bloqueado
# ao tentar ver VP e a Visão Geral (mensagem clara, sem exceção), mas
# acessa a própria SP normalmente; assistente com Gerência VP continua
# bloqueado tentando ver SP (regra que já existia, confirmado que não
# regrediu); admin acessa qualquer Gerência sem bloqueio; um perfil
# usuario SEM Gerência delegada (gerencia=NULL) continua vendo tudo
# (fallback intencional); sidebar do usuário SP só mostra o botão da
# própria SP (sem as outras 5 Gerências nem Visão Geral). Troca de senha:
# rejeita senha <8 caracteres e senhas que não conferem sem chamar a API;
# troca bem-sucedida chama update_user_by_id com o auth_user_id certo e
# desmarca deve_trocar_senha; conta sem auth_user_id salvo usa o fallback
# por e-mail (mesmo mecanismo do reset de senha); botão cancelar faz
# logout.
# MAJOR -- duas correções de segurança/escopo de dado no mesmo lote.

# 6.0.1 (2026-09-02): confirmado pelo Julio que o fix de CSS do 5.1.1
# funcionou (data aparece preenchida) — mas os rótulos "Início"/"Fim" de
# Abertura/Encerramento da Nota ficavam acinzentados, não no branco
# "cheio" dos demais títulos da sidebar. Causa: o wrapper de rótulo do
# Streamlit (stWidgetLabel) carrega um `opacity` próprio (texto secundário,
# pensado pra tema claro) — `color:#fff` sozinho não resolve opacity.
# modules/home.py::_inject_sidebar_css() ganha `opacity:1 !important`
# junto do color, no <label> e no wrapper stWidgetLabel dentro de
# stDateInput. Só os rótulos — os campos de data em si (já corrigidos no
# 5.1.1) não foram tocados, como pedido.
# PATCH -- ajuste de estilo, sem mudar comportamento.

# 6.0.2 (2026-09-02): o fix do 6.0.1 piorou em vez de resolver — Julio
# reportou "Início"/"Fim" agora em PRETO (antes era cinza esmaecido). Causa
# raiz de verdade: o texto "Início"/"Fim" fica num <p> AINDA MAIS interno
# (dentro de stMarkdownContainer), não direto no <label>/stWidgetLabel que
# o 6.0.1 pintou de branco. Esse <p> é um dos "TODOS os descendentes" que
# a regra `* {color:preto}` do 5.1.1 (pensada pro VALOR da data) também
# pinta — e uma regra que bate DIRETO num elemento sempre vence a cor
# herdada do pai, não importa a especificidade do pai (por isso pintar só
# o <label> de branco não tinha efeito nenhum no <p> de dentro). Corrigido
# em modules/home.py::_inject_sidebar_css() acrescentando `label *` e
# `[stWidgetLabel] *` às regras brancas — cobre TODOS os descendentes do
# rótulo, com especificidade maior que a wildcard genérica, então essa
# parte específica vence e o resto do campo (o valor da data) continua
# preto normalmente.
# PATCH -- ajuste de estilo, sem mudar comportamento (correção do 6.0.1).

APP_VERSION = "6.0.2"
