# database/client.py

import ssl
import httpx
import streamlit as st
from supabase import create_client, Client

# Bypass SSL para redes corporativas com proxy (afeta httpx e stdlib)
ssl._create_default_https_context = ssl._create_unverified_context

_orig_client_init = httpx.Client.__init__
def _patched_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_client_init

_orig_async_init = httpx.AsyncClient.__init__
def _patched_async_init(self, *args, **kwargs):
    kwargs['verify'] = False
    _orig_async_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = _patched_async_init


@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


@st.cache_resource
def get_supabase_admin() -> Client:
    url = st.secrets["supabase"]["url"]
    service_key = st.secrets["supabase"]["service_key"]
    return create_client(url, service_key)


def criar_cliente_auth_temporario() -> Client:
    """
    Client NOVO (sem @st.cache_resource) só pra validar credenciais em
    auth/login.py::_autenticar via sign_in_with_password.

    Por quê: get_supabase() é um singleton COMPARTILHADO por todos os
    usuários simultâneos do processo Streamlit. sign_in_with_password
    guarda o token de sessão dentro do próprio objeto Client — chamado no
    client compartilhado, o login de um usuário sobrescreve o "usuário
    logado" que outro usuário concorrente estava usando naquele momento
    (e um logout de qualquer um pode derrubar a sessão de outro). Usando
    um client descartável só para essa checagem, a sessão nunca chega a
    existir no objeto compartilhado — mesma lógica já aplicada ao reset
    de senha em auth/recuperar_senha.py.
    """
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


def fechar_cliente_temporario(client: Client) -> None:
    """
    Fecha as conexões HTTP internas de um client criado por
    criar_cliente_auth_temporario() — SEMPRE chamar depois de usar (ver
    auth/login.py::_autenticar, num finally).

    Por quê: create_client() abre um httpx.Client (pool de conexões TCP
    persistentes) por baixo dos panos em client.auth._http_client e
    client.postgrest.session — diferente de get_supabase()/
    get_supabase_admin() (@st.cache_resource, um único client reciclado
    pra sempre), um client "descartável" criado a cada tentativa de login
    nunca mais é referenciado depois — mas o Python só fecha o socket
    quando o garbage collector passar por ali, o que não é imediato. Sob
    várias tentativas de login seguidas (comum numa depuração), isso
    empilha conexões abertas até o processo ficar sem recursos —
    provável causa real de "[Errno 11] Resource temporarily unavailable"
    em chamadas totalmente não relacionadas (ex.: buscar notas) logo
    depois. Fechar explicitamente evita acumular.
    """
    for sub_cliente, atributo in [(getattr(client, "auth", None), "_http_client"),
                                   (getattr(client, "postgrest", None), "session")]:
        try:
            http_client = getattr(sub_cliente, atributo, None)
            if http_client is not None:
                http_client.close()
        except Exception:
            pass

# endregion
