# 🚂 MRS Nexus — Plataforma de Inteligência de Manutenção da Malha

> Sistema multi-gerencial unificando Via Permanente (VP) e Eletroeletrônica (EE)
> das Gerências SP e VP da MRS Logística.

---

## 🚀 Setup — Do Zero ao Deploy

### 1. Pré-requisitos

- Python 3.11+
- Conta no [Supabase](https://supabase.com) (gratuito)
- Conta no [GitHub](https://github.com) (repositório privado)
- Conta no [Streamlit Community Cloud](https://streamlit.io/cloud)

---

### 2. Banco de Dados (Supabase)

1. Acesse [supabase.com](https://supabase.com) → **New Project**
2. Escolha nome (ex: `mrs-sentinel`) e senha forte
3. Vá em **SQL Editor** → cole o conteúdo de `database/schema.sql` → **Run**
4. No SQL, atualize o email do admin:
   ```sql
   UPDATE usuarios SET email = 'seu.email@mrs.com.br' WHERE perfil = 'admin';
   ```
5. Crie o usuário Auth:
   - **Authentication** → **Users** → **Add User**
   - Email: `seu.email@mrs.com.br` | Senha: (forte)
   - ✅ "Auto Confirm User"

---

### 3. Configuração Local

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/mrs-painel-malha.git
cd mrs-painel-malha

# Crie ambiente virtual
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows

# Instale dependências
pip install -r requirements.txt

# Configure as chaves (copie o template)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edite secrets.toml com suas chaves do Supabase
```

### 4. Preencher secrets.toml

```toml
[supabase]
url         = "https://SEU_PROJETO.supabase.co"
key         = "eyJhbGc..."       # Anon/Public Key
service_key = "eyJhbGc..."       # Service Role Key ⚠️

[app]
nome     = "MRS Sentinel"
versao   = "1.0.0"
ambiente = "desenvolvimento"
```

> Onde achar as chaves: **Supabase → Settings → API**

---

### 5. Rodar Localmente

```bash
streamlit run app.py
```

Acesse: `http://localhost:8501`

---

### 6. Deploy no Streamlit Cloud

1. Faça push do código para o GitHub (sem o `secrets.toml`)
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. **New App** → selecione o repositório → branch `main` → `app.py`
4. **Advanced Settings** → cole o conteúdo do `secrets.toml` em **Secrets**
5. **Deploy** 🚀

---

## 📁 Estrutura do Projeto

```
mrs-painel-malha/
├── .streamlit/
│   ├── config.toml              # Tema MRS (azul-marinho + dourado)
│   └── secrets.toml.example     # Template de configuração
├── app.py                       # Ponto de entrada + roteador
├── auth/
│   ├── login.py                 # Tela de login Supabase Auth
│   ├── session.py               # Gerenciamento de sessão
│   └── permissions.py           # RBAC (Admin/Assistente/Usuário)
├── database/
│   ├── client.py                # Cliente Supabase singleton
│   ├── queries.py               # Queries reutilizáveis
│   └── schema.sql               # Schema completo do banco
├── core/
│   └── glossarios.py            # Ramais, defeitos VP/EE
├── modules/
│   ├── home.py                  # Sidebar de navegação
│   ├── gerencia_sp.py           # Tela Gerência SP
│   ├── gerencia_vp.py           # Tela Gerência VP
│   ├── gerencia_geral.py        # Visão Geral multi-gerencial
│   └── admin_panel.py           # Painel Administrativo
├── requirements.txt
└── .gitignore
```

---

## 👥 Perfis de Acesso

| Perfil | Descrição | Permissões |
|---|---|---|
| 👑 **Admin** | Acesso total | Tudo: criar usuários, ver logs, todas gerências |
| 🔧 **Assistente** | Técnico de campo | Upload + visualização da sua gerência |
| 👤 **Usuário** | Gestão/diretoria | Visualização de todas as gerências |

---

## 🗺️ Roadmap de Sprints

| Sprint | Foco | Status |
|---|---|---|
| **Sprint 1** | Login + RBAC + Roteamento | ✅ Concluído |
| **Sprint 2** | Upload de planilhas + Persistência | ⬜ Próxima |
| **Sprint 3** | Visualizações SP e VP (9 elementos) | ⬜ Planejado |
| **Sprint 4** | Visão Geral + Admin completo | ⬜ Planejado |
| **Sprint 5+** | Alertas, Mapas, PDF, SAP | 🔮 Futuro |

---

## 🛠️ Stack Tecnológica

- **Frontend:** Streamlit
- **Banco:** Supabase (PostgreSQL)
- **Auth:** Supabase Auth
- **Gráficos:** ECharts + Plotly
- **Deploy:** Streamlit Community Cloud

---

## 📞 Contato

**Julio Cesar de Oliveira Paz** — Especialista Ferroviário I  
MRS Logística · Juiz de Fora, MG  
`30028203@mrs.com.br`

*Para hospedagem corporativa MRS: contatar Bruno Capobiango (TI)*
