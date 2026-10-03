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

from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
PAGE_PATH = DOCS_DIR / "index.html"
PREVIEW_PATH = DOCS_DIR / "preview.png"

WIDTH = 1200
HEIGHT = 627


def make_preview(page_path: Path = PAGE_PATH, preview_path: Path = PREVIEW_PATH) -> Path:
    if not page_path.exists():
        raise FileNotFoundError(
            f"'{page_path}' est introuvable. Générez-la d'abord avec "
            "'uv run python examples/example_gares.py'."
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        page.goto(f"file://{page_path}")
        # Attend la fin des requêtes réseau (dont le chargement des tuiles)
        # puis laisse le temps au rendu Canvas de se stabiliser.
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(preview_path))
        browser.close()

    print(f"Aperçu Open Graph généré : {preview_path}")
    return preview_path


if __name__ == "__main__":
    make_preview()
