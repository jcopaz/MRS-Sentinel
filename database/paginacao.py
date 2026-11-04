# database/paginacao.py — Leitura paginada das tabelas grandes (notas, RASF...)
#
# O PostgREST do Supabase devolve no máximo 1.000 linhas por chamada. Antes,
# cada função buscava as páginas UMA POR VEZ (17 chamadas seguidas só para as
# notas de SP ≈ 13 s, e mais no Streamlit Cloud, que fica nos EUA). Aqui:
#   1. a 1ª página vem com a contagem total (count="exact");
#   2. as demais são pedidas em paralelo (TRABALHADORES chamadas ao mesmo tempo);
#   3. tudo ordenado por id (chave primária) — sem ordem, o Postgres não garante
#      a mesma sequência entre páginas e uma linha podia vir repetida ou faltar.

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from database.client import get_supabase

PAGE_SIZE = 1000
# Bases só mudam por upload (que limpa o cache na hora) — 6 h evita recarregar
# ~30 MB a cada 5 min. Admin → "Limpar Cache de Dados" força a releitura.
TTL_BASES = 6 * 3600
TRABALHADORES = 6


def buscar_paginado(tabela: str, filtrar: Callable, colunas: str = "*") -> list[dict]:
    """Todas as linhas de ``tabela`` que passam em ``filtrar(query)``.

    ``filtrar`` recebe a query já com o select e devolve a query com os filtros
    (.eq, .in_ ...), sem .range/.order — isso fica por conta daqui.
    """
    supabase = get_supabase()

    def pagina(i: int, contar: bool = False):
        q = supabase.table(tabela).select(colunas, count="exact" if contar else None)
        return filtrar(q).order("id").range(i * PAGE_SIZE, (i + 1) * PAGE_SIZE - 1).execute()

    primeira = pagina(0, contar=True)
    registros = list(primeira.data or [])
    total = primeira.count if primeira.count is not None else len(registros)
    n_paginas = -(-total // PAGE_SIZE)
    ultima = len(registros)
    if n_paginas > 1:
        with ThreadPoolExecutor(max_workers=min(TRABALHADORES, n_paginas - 1)) as ex:
            for resp in ex.map(pagina, range(1, n_paginas)):
                registros.extend(resp.data or [])
                ultima = len(resp.data or [])
    # Tabela cresceu entre a contagem e a leitura (upload simultâneo): segue até uma página incompleta.
    i = max(n_paginas, 1)
    while ultima == PAGE_SIZE:
        resp = pagina(i)
        registros.extend(resp.data or [])
        ultima, i = len(resp.data or []), i + 1
    return registros
