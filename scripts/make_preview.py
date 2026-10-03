"""Génère la vignette (aperçu Open Graph) de la page publiée sur GitHub Pages.

Ce script capture une image PNG 1200x627 de ``docs/index.html`` (la page
générée par ``examples/example_gares.py``) une fois les tuiles de fond de
carte chargées, et l'enregistre sous ``docs/preview.png`` — c'est-à-dire
dans le dossier publié tel quel par GitHub Pages, à l'URL
https://efbulle.github.io/cartes_multicouches/preview.png.

Ce script n'est volontairement pas exécuté par la CI : il se lance
manuellement après avoir régénéré ``docs/index.html``, et l'image produite
est committée dans le dépôt.

Usage :
    uv run python examples/example_gares.py
    uv run python scripts/make_preview.py
"""

import time
from pathlib import Path

from playwright.sync_api import Request, Response, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
PAGE_PATH = DOCS_DIR / "index.html"
PREVIEW_PATH = DOCS_DIR / "preview.png"

WIDTH = 1200
HEIGHT = 627

# Bokeh ajuste automatiquement le zoom après le premier rendu, ce qui
# déclenche une seconde vague de requêtes de tuiles juste après que le
# réseau soit redevenu inactif une première fois. On attend donc que plus
# aucune image ne soit chargée pendant QUIET_PERIOD_S, borné par MAX_WAIT_S,
# plutôt que de se fier à un délai fixe après "networkidle".
QUIET_PERIOD_S = 1.5
MAX_WAIT_S = 25.0


def make_preview(page_path: Path = PAGE_PATH, preview_path: Path = PREVIEW_PATH) -> Path:
    if not page_path.exists():
        raise FileNotFoundError(
            f"'{page_path}' est introuvable. Générez-la d'abord avec "
            "'uv run python examples/example_gares.py'."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})

        def on_http_error(response: Response) -> None:
            if response.status >= 400:
                print(f"[HTTP {response.status}] {response.url}")

        page.on("response", on_http_error)

        last_image_activity = time.monotonic()

        def on_image_activity(request: Request) -> None:
            nonlocal last_image_activity
            if request.resource_type == "image":
                last_image_activity = time.monotonic()

        def on_request_failed(request: Request) -> None:
            print(f"[ÉCHEC] {request.url} ({request.failure})")
            on_image_activity(request)

        page.on("requestfinished", on_image_activity)
        page.on("requestfailed", on_request_failed)

        page.goto(f"file://{page_path}")
        page.wait_for_load_state("networkidle")

        # Tant que des images (tuiles) ont fini de charger il y a moins de
        # QUIET_PERIOD_S, on continue d'attendre une nouvelle vague éventuelle.
        deadline = time.monotonic() + MAX_WAIT_S
        while time.monotonic() - last_image_activity < QUIET_PERIOD_S:
            if time.monotonic() >= deadline:
                print(f"[Attention] Délai maximal ({MAX_WAIT_S}s) atteint, capture anticipée.")
                break
            page.wait_for_timeout(200)

        page.screenshot(path=str(preview_path))
        browser.close()

    print(f"Aperçu Open Graph généré : {preview_path}")
    return preview_path


if __name__ == "__main__":
    make_preview()
