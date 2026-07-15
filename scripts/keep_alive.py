# scripts/keep_alive.py
# Visita o MRS Sentinel com um navegador headless (Playwright) para mantê-lo
# acordado no Streamlit Community Cloud.
#
# Por que não um simples HTTP GET (curl, cron-job.org, etc.)?
# O Streamlit Community Cloud coloca todo app público atrás de um "bootstrap"
# em share.streamlit.io que só um navegador de verdade (executa JS, segue
# redirecionamentos, aceita cookies) consegue atravessar — inclusive o
# endpoint de health check (/_stcore/health) cai na mesma barreira. Um
# navegador headless real passa por isso normalmente.

import sys

from playwright.sync_api import sync_playwright

URL = "https://sentinelmrs.streamlit.app/"
TEXTO_ESPERADO = "MRS Sentinel"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(URL, wait_until="networkidle", timeout=45_000)
            conteudo = page.content()
            titulo = page.title()
        finally:
            browser.close()

    if TEXTO_ESPERADO not in conteudo:
        print(f"❌ Conteúdo inesperado. Título da página: {titulo!r}")
        return 1

    print(f"✅ App respondeu normalmente. Título: {titulo!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
