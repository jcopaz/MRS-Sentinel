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

# endregion
