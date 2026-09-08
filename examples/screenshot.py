from pathlib import Path

from playwright.sync_api import sync_playwright

PARENT_DIR = Path(__file__).parent
OUTPUT_DIR = PARENT_DIR / "output"
ILLUSTRATIONS_DIR = PARENT_DIR / "illustrations"


def screenshot(html_path: Path, png_path: Path, width=1400, height=800, wait_ms=2500):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(wait_ms)
        page.screenshot(path=str(png_path))
        browser.close()


screenshot(OUTPUT_DIR / "example_map_gares.html", ILLUSTRATIONS_DIR / "example_map_gares.png")
print("done 1")
