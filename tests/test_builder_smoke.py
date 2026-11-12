"""Test de fumée du builder PyScript : parcours « configuration JSON ».

Génère une page autoportante avec un mini-référentiel de PK, charge un Excel
puis une spec JSON dans un vrai navigateur, construit la carte et vérifie
qu'elle s'affiche sans erreur JS. Lent (démarrage de Pyodide) : marqué `builder`.

Nécessite l'accès réseau (CDN PyScript/Pyodide) et `uv` (construction du wheel).
Exclusion : pytest -m "not builder"
"""

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import geopandas as gpd
import pandas as pd
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from shapely.geometry import LineString

pytest.importorskip("cartes_builder")
from cartes_builder import Dataset, build_wheel, gen_carte

from cartes_multicouches import CarteDynMulti, LayerConfig

pytestmark = pytest.mark.builder

SHEET = "Feuille1"
SPEC = {
    "version": 1,
    "titre": "Carte de fumée",
    "referentiels": {
        "rfn": {
            "donnees": "tronloc",
            "colonnes": {"ligne": "code_ligne", "pk_debut": "pkmd", "pk_fin": "pkmf"},
            "unite_pk": "km",
        }
    },
    "couches": [
        {
            "fichier": "principal",
            "feuille": SHEET,
            "geometrie": {
                "pk": {
                    "ligne": "code_ligne",
                    "pk_debut": "pkmd",
                    "pk_fin": "pkmf",
                    "unite_pk": "km",
                    "referentiel": "rfn",
                }
            },
            "nom_couche": "Tronçons fumée",
            "couleur": "categorie",
            "tooltips": ["code_ligne", "valeur"],
            "filtres": ["categorie"],
        }
    ],
}


def _mafunc(xl, feuille, tronloc):
    """Parcours sans configuration, requis par gen_carte (non utilisé ici)."""
    return CarteDynMulti(layers_config=[LayerConfig(name="x", data=tronloc)])


@pytest.fixture(scope="module")
def page_builder(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("builder")
    tronloc = gpd.GeoDataFrame(
        {
            "code_ligne": [830000] * 20,
            "pkmd": [float(i) for i in range(20)],
            "pkmf": [float(i + 1) for i in range(20)],
        },
        geometry=[LineString([(i * 1000, 0), ((i + 1) * 1000, 0)]) for i in range(20)],
        crs="EPSG:3857",
    )
    tronloc_path = tmp / "tronloc.parquet"
    tronloc.to_parquet(tronloc_path)

    xlsx = tmp / "donnees.xlsx"
    pd.DataFrame(
        {
            "code_ligne": [830000, 830000],
            "pkmd": [0.0, 5.0],
            "pkmf": [4.0, 12.0],
            "valeur": [1.5, 2.5],
            "categorie": ["A", "B"],
        }
    ).to_excel(xlsx, index=False, sheet_name=SHEET)

    spec = tmp / "spec.json"
    spec.write_text(json.dumps(SPEC), encoding="utf-8")

    html = gen_carte(
        _mafunc,
        tmp / "app.html",
        datasets={"tronloc": Dataset(tronloc_path)},
        select={"Feuille": "xl_sheetnames"},
        wheel_path=build_wheel(Path(__file__).resolve().parents[1]),
        standalone=True,
    )
    return html, xlsx, spec


def test_parcours_configuration_json(page, page_builder):
    html, xlsx, spec = page_builder
    erreurs_js = []
    page.on("pageerror", lambda exc: erreurs_js.append(exc.stack or str(exc)))

    page.goto(f"file://{html}")
    page.wait_for_selector("#loading", state="hidden", timeout=240_000)
    page.evaluate("""() => {
        const readAsText = FileReader.prototype.readAsText;
        FileReader.prototype.readAsText = function(...args) {
            this.addEventListener("loadend", () => { window.specReadFinished = true; }, {once: true});
            return readAsText.apply(this, args);
        };
    }""")
    # Les gestionnaires PyScript se branchent au clic : passer par le sélecteur de fichier.
    for label, fichier in (("#file-input-label", xlsx), ("#spec-input-label", spec)):
        with page.expect_file_chooser() as chooser:
            page.click(label)
        chooser.value.set_files(str(fichier))
    page.wait_for_function("() => window.specReadFinished === true", timeout=60_000)

    bouton = page.locator("#cstr_carte")
    page.wait_for_function("() => !document.getElementById('cstr_carte').disabled", timeout=60_000)
    bouton.click()

    try:
        page.wait_for_selector("#myplot .bk-Canvas, #myplot canvas", timeout=120_000)
    except PlaywrightTimeoutError as exc:
        rapport = page.locator("#rapport-container").inner_text()
        raise AssertionError(f"Carte non affichée : {rapport}; erreurs JS : {erreurs_js}") from exc
    assert "Erreur" not in page.locator("#rapport-container").inner_text()
    assert page.locator("#exporte").is_enabled()
    assert not erreurs_js, f"Erreurs JS : {erreurs_js}"


def _mafunc_pktools(xl, feuille):
    from pktools.pandas import ext_to_m  # pyright: ignore[reportMissingImports]

    df = pd.read_excel(xl, sheet_name=feuille)
    metres = ext_to_m(df["pk"])
    if metres.tolist() != [4514, 413795]:
        raise ValueError(f"Conversion inattendue : {metres.tolist()}")
    geo = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy([2.0, 2.1], [48.0, 48.1]), crs=4326)
    return CarteDynMulti(layers_config=[LayerConfig(name="PK", data=geo)])


@pytest.fixture(scope="module")
def pktools_wheel():
    path = os.environ.get("PKTOOLS_WHEEL")
    if not path:
        pytest.skip("Définir PKTOOLS_WHEEL vers une wheel locale de pktools pour ce test.")
    return Path(path)


@pytest.fixture(scope="module")
def carte_wheel():
    return build_wheel(Path(__file__).resolve().parents[1])


@pytest.mark.parametrize("standalone", [True, False])
def test_parcours_pktools(page, tmp_path, carte_wheel, pktools_wheel, standalone):
    html = gen_carte(
        _mafunc_pktools,
        tmp_path / "app.html",
        wheel_path=carte_wheel,
        pktools_wheel_path=pktools_wheel,
        select={"Feuille": "xl_sheetnames"},
        standalone=standalone,
    )
    valid = tmp_path / "valid.xlsx"
    invalid = tmp_path / "invalid.xlsx"
    pd.DataFrame({"pk": ["4+514", "412B+795"]}).to_excel(valid, index=False)
    pd.DataFrame({"pk": ["invalide", "412B+795"]}).to_excel(invalid, index=False)

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        erreurs = []
        page.on("pageerror", lambda exc: erreurs.append(str(exc)))
        page.on("console", lambda msg: erreurs.append(msg.text) if msg.type == "error" else None)
        page.goto(f"http://127.0.0.1:{server.server_port}/{html.name}")
        try:
            page.wait_for_function("() => document.body.dataset.ready === '1'", timeout=240_000)
        except PlaywrightTimeoutError as exc:
            raise AssertionError(f"Initialisation impossible : {erreurs}") from exc
        for xlsx in (valid, invalid):
            with page.expect_file_chooser() as chooser:
                page.click("#file-input-label")
            chooser.value.set_files(str(xlsx))
            if xlsx == invalid:
                page.wait_for_function(
                    "() => document.getElementById('myplot').innerHTML === ''", timeout=60_000
                )
            page.wait_for_function(
                "() => !document.getElementById('cstr_carte').disabled", timeout=60_000
            )
            page.click("#cstr_carte")
            if xlsx == valid:
                page.wait_for_selector("#myplot .bk-Canvas, #myplot canvas", timeout=120_000)
            else:
                page.wait_for_function(
                    "() => document.getElementById('rapport-container').textContent"
                    ".includes('PK externe invalide')",
                    timeout=60_000,
                )
                assert "invalide" in page.locator("#rapport-container").inner_text()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
