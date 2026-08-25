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

APP_VERSION = "3.0.0"
