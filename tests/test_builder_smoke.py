"""Test de fumée du builder PyScript : parcours « configuration JSON ».

Génère une page autoportante avec un mini-référentiel de PK, charge un Excel
puis une spec JSON dans un vrai navigateur, construit la carte et vérifie
qu'elle s'affiche sans erreur JS. Lent (démarrage de Pyodide) : marqué `builder`.

Nécessite l'accès réseau (CDN PyScript/Pyodide) et `uv` (construction du wheel).
Exclusion : pytest -m "not builder"
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
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
    page.on("pageerror", lambda exc: erreurs_js.append(str(exc)))

    page.goto(f"file://{html}")
    page.wait_for_selector("#loading", state="hidden", timeout=240_000)
    # Les gestionnaires PyScript se branchent au clic : passer par le sélecteur de fichier.
    for label, fichier in (("#file-input-label", xlsx), ("#spec-input-label", spec)):
        with page.expect_file_chooser() as chooser:
            page.click(label)
        chooser.value.set_files(str(fichier))

    bouton = page.locator("#cstr_carte")
    page.wait_for_function("() => !document.getElementById('cstr_carte').disabled", timeout=60_000)
    bouton.click()

    page.wait_for_selector("#myplot .bk-Canvas, #myplot canvas", timeout=120_000)
    assert "Erreur" not in page.locator("#rapport-container").inner_text()
    assert page.locator("#exporte").is_enabled()
    assert not erreurs_js, f"Erreurs JS : {erreurs_js}"
