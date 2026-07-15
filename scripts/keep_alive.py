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
import time

from playwright.sync_api import sync_playwright

URL = "https://sentinelmrs.streamlit.app/"
TEXTO_ESPERADO = "MRS Sentinel"

# "Over capacity" é a infra compartilhada do Streamlit Community Cloud
# recusando recursos temporariamente (tier gratuito) — não tem a ver com
# nosso app. Costuma ser transitório, então vale tentar de novo antes de
# desistir e marcar o job como falho.
TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS_S = 20


def _visitar(page) -> tuple[str, str]:
    page.goto(URL, wait_until="networkidle", timeout=45_000)
    return page.content(), page.title()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            for tentativa in range(1, TENTATIVAS + 1):
                conteudo, titulo = _visitar(page)
                if TEXTO_ESPERADO in conteudo:
                    print(f"✅ App respondeu normalmente. Título: {titulo!r}")
                    return 0

                print(f"⚠️ Tentativa {tentativa}/{TENTATIVAS} — título inesperado: {titulo!r}")
                if tentativa < TENTATIVAS:
                    time.sleep(ESPERA_ENTRE_TENTATIVAS_S)
        finally:
            browser.close()

    print(f"❌ App não respondeu como esperado após {TENTATIVAS} tentativas. Último título: {titulo!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
