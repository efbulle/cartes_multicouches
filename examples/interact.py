"""Script d'interaction avec la carte multi-couches pour générer des captures d'écran."""

import re
from pathlib import Path

from playwright.sync_api import sync_playwright

PARENT_DIR = Path(__file__).parent
OUTPUT_DIR = PARENT_DIR / "output"
ILLUSTRATIONS_DIR = PARENT_DIR / "illustrations"

FRAMES = OUTPUT_DIR / "frames"
FRAMES.mkdir(parents=True, exist_ok=True)

HTML = OUTPUT_DIR / "example_map_gares.html"


def button(page, label: str):
    """Retourne un bouton Bokeh d'après son libellé visible."""
    return page.locator("button.bk-btn").filter(has_text=label).first


def layer_checkbox(page, label: str):
    """Retourne la case d'une couche, sans dépendre des IDs Bokeh générés."""
    return page.locator("label").filter(has_text=re.compile(rf"^\s*{re.escape(label)}\s*$")).first


def is_tile_response(response) -> bool:
    """Indique qu'une tuile CartoDB a été chargée avec succès."""
    return response.ok and "basemaps.cartocdn.com" in response.url


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 800})
    with page.expect_response(is_tile_response, timeout=30_000):
        page.goto(HTML.as_uri(), wait_until="domcontentloaded")
    page.wait_for_selector("button.bk-btn", timeout=30_000)
    page.evaluate(
        """() => new Promise((resolve) => requestAnimationFrame(
            () => requestAnimationFrame(resolve)
        ))"""
    )

    # Frame 0 : état initial
    page.screenshot(path=str(FRAMES / "f0.png"))

    mnemo_select = (
        page.locator("select[multiple]").filter(has=page.locator("option", has_text="Autre")).first
    )
    mnemo_select.wait_for()
    mnemo_select.select_option(["A"])
    page.wait_for_timeout(600)
    page.screenshot(path=str(FRAMES / "f1.png"))

    mnemo_select.select_option(["A", "B", "Autre"])
    page.wait_for_timeout(600)
    page.screenshot(path=str(FRAMES / "f2.png"))

    button(page, "Réinitialiser").click()
    page.wait_for_timeout(500)
    page.screenshot(path=str(FRAMES / "f3.png"))

    # Frame 4 : ouvrir le panneau des couches et masquer "Gares"
    button(page, "Couches").click()
    page.wait_for_timeout(400)
    layer_checkbox(page, "Gares de voyageurs").click()
    page.wait_for_timeout(500)
    page.screenshot(path=str(FRAMES / "f4.png"))

    # Frame 5 : réafficher Gares, ouvrir la table de données
    layer_checkbox(page, "Gares de voyageurs").click()
    page.wait_for_timeout(300)
    button(page, "Couches").click()  # referme le panneau couches
    page.wait_for_timeout(300)
    button(page, "Tables").click()
    page.wait_for_timeout(600)
    page.screenshot(path=str(FRAMES / "f5.png"))

    browser.close()

print("frames done")
