"""Construit la démonstration publique du builder dans `docs/builder/`.

Usage :
    uv run python scripts/build_demo.py [--out docs/builder] [--refresh]

Étapes :
  1. référentiel public des PK (OpenData SNCF, ODbL) -> cache `build/tronloc.parquet`
  2. wheel de cartes_multicouches (`uv build`)
  3. fichier Excel de test
  4. carte Bokeh statique d'exemple
  5. applications PyScript : version légère (assets chargés par pyfetch) et autoportante
  6. page d'accueil de la démo + vérification qu'aucun secret n'a été publié

Aucune clé d'API n'est utilisée : les tuiles viennent d'un fournisseur sans clé.
"""

import argparse
import html
import os
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from bokeh.resources import CDN
from cartes_builder import (
    PKS_ATTRIBUTION,
    Dataset,
    ajoute_geo,
    build_tronloc_file,
    build_wheel,
    gen_carte,
)

from cartes_multicouches import (
    AnnotationConfig,
    AttributionConfig,
    CarteDynMulti,
    GlobalDataConfig,
    InteractionConfig,
    LayerConfig,
    MapConfig,
    StyleConfig,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "build"
VILLES_PATH = ROOT / "examples" / "data" / "villes.csv"
ATTRIBUTION = {"text": "@efbulle", "href": "https://github.com/efbulle"}
SECRET_ENV_VARS = ("CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY",)

SHEET = "Ma carte de test"
TEST_DATA = pd.DataFrame(
    [
        [830000, 0.0, 150.0, 12.5, "A"],
        [830000, 150.0, 320.0, 8.0, "B"],
        [5000, 25.0, 350.0, 15.2, "A"],
        [420000, 150.0, 350.0, 4.1, "B"],
        [752000, 0.0, 200.0, 10.3, "A"],
        [570000, 10.0, 300.0, 6.7, "B"],
    ],
    columns=["code_ligne", "pkmd", "pkmf", "valeur", "categorie"],
)


def macarte_simple(xl, feuille, tronloc, attribution_config):
    """Une couche de tronçons géolocalisés, sans clé d'API."""
    df = pd.read_excel(xl, sheet_name=feuille)
    # PK en km, clé de jointure `code_ligne` : voir `cartes_builder.data`.
    gdf = ajoute_geo(
        df,
        tronloc,
        on="code_ligne",
        pk_lbls=("pkmd", "pkmf"),
        tronloc_pk_lbls=("pkmd", "pkmf"),
        pk_unit_m=1000.0,
    )
    layer = LayerConfig(
        name="Tronçons",
        data=gdf,
        style=StyleConfig(color="red", size_or_width=3),
        interaction=InteractionConfig(),
    )
    return CarteDynMulti(
        layers_config=[layer],
        map_config=MapConfig(title=feuille, tile_provider="Esri.WorldGrayCanvas"),
        attribution_config=AttributionConfig(**attribution_config),
    )


def macarte_complete(xl, feuille, legende, selecteur, tronloc, villes, attribution_config):
    """Tronçons filtrables par colonnes de l'Excel, sur fond de villes."""
    df = pd.read_excel(xl, sheet_name=feuille)
    gdf = ajoute_geo(
        df,
        tronloc,
        on="code_ligne",
        pk_lbls=("pkmd", "pkmf"),
        tronloc_pk_lbls=("pkmd", "pkmf"),
        pk_unit_m=1000.0,
    )
    layer = LayerConfig(
        name="Tronçons",
        data=gdf,
        style=StyleConfig(color="red", size_or_width=3),
        interaction=InteractionConfig(),
    )
    villes_loc = gpd.GeoDataFrame(
        villes,
        geometry=gpd.points_from_xy(villes["x"], villes["y"]),
        crs="EPSG:3857",
    )
    villes_loc["size"] = villes_loc["pref"].map({True: 12, False: 7})
    layer_villes = LayerConfig(
        name="Villes",
        data=villes_loc,
        style=StyleConfig(color="#818588FF", size_or_width="size", marker="circle", alpha=0.95),
        tooltips=[],
        columns_to_show=["name", "pref"],
        interaction=InteractionConfig(hover=False, tooltips=False, tap=False),
        annotation=AnnotationConfig(
            text="name",
            y_offset=-4,
            text_align="center",
            text_font_size="10px",
            text_color="#818588FF",
            background_fill_color=None,
            border_line_color=None,
            padding=2,
        ),
        has_table=False,
    )
    return CarteDynMulti(
        layers_config=[layer_villes, layer],
        map_config=MapConfig(title=feuille, tile_provider="Esri.WorldGrayCanvas"),
        data_config=GlobalDataConfig(specific_filters={"Tronçons": [legende, selecteur]}),
        attribution_config=AttributionConfig(**attribution_config),
    )


def _write_index(out: Path, standalone_mb: float) -> None:
    page = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>cartes_multicouches — builder</title>
<style>body{{font-family:system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1e2530}}
li{{margin:.6rem 0}}small{{color:#6b7686}}</style></head><body>
<h1>cartes_multicouches — démonstrations du builder</h1>
<p>Le builder génère des pages HTML qui construisent des cartes
<a href="https://github.com/efbulle/cartes_multicouches">cartes_multicouches</a>
dans le navigateur (PyScript), à partir d'un fichier Excel de tronçons (<code>code_ligne</code>,
PK début/fin en km).</p>
<ul>
<li><a href="maps/carte_troncons.html">Carte Bokeh classique</a> — rendu direct.</li>
<li><a href="app.html">Application PyScript</a> — importez un .xlsx (exemple :
<a href="test_tron.xlsx">test_tron.xlsx</a>), choisissez feuille, légende et sélecteur.</li>
<li><a href="app_simple.html">Application PyScript minimale</a> — une couche de tronçons.</li>
<li><a href="standalone/app_standalone.html">Version autoportante</a> ({standalone_mb:.0f} Mo, tout
est embarqué dans un seul fichier) — <small>à télécharger pour un usage hors ligne.</small></li>
</ul>
<p><small>{html.escape(PKS_ATTRIBUTION)}</small></p>
</body></html>
"""
    (out / "index.html").write_text(page, encoding="utf-8")


def _check_no_secret(out: Path) -> None:
    """Échoue si une valeur de secret connue apparaît dans les fichiers publiés."""
    secrets = [v for name in SECRET_ENV_VARS if (v := os.environ.get(name))]
    if not secrets:
        return
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".json", ".csv", ".gz"}:
            data = path.read_bytes()
            for secret in secrets:
                if secret.encode() in data:
                    raise SystemExit(f"Secret détecté dans {path} : publication annulée.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "builder")
    parser.add_argument("--refresh", action="store_true", help="retélécharge le référentiel")
    args = parser.parse_args()
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    tronloc_path = CACHE / "tronloc.parquet"
    if args.refresh or not tronloc_path.exists():
        print("Génération du référentiel des PK...")
        build_tronloc_file(tronloc_path)
    wheel = build_wheel(ROOT)

    xlsx = out / "test_tron.xlsx"
    with pd.ExcelWriter(xlsx) as writer:
        TEST_DATA.to_excel(writer, index=False, sheet_name=SHEET)

    datasets = {"tronloc": Dataset(tronloc_path), "villes": Dataset(VILLES_PATH)}

    tronloc = gpd.read_parquet(tronloc_path)
    villes = pd.read_csv(VILLES_PATH)
    with pd.ExcelFile(xlsx) as xl:
        carte = macarte_complete(xl, SHEET, "valeur", "categorie", tronloc, villes, ATTRIBUTION)
    (out / "maps").mkdir()
    carte.save(out / "maps" / "carte_troncons.html", resources=CDN)

    common = {
        "wheel_path": wheel,
        "attribution_config": ATTRIBUTION,
        "assets_dir": out / "assets",
        "standalone": False,
    }
    gen_carte(
        macarte_complete,
        out / "app.html",
        datasets=datasets,
        select={"Feuille": "xl_sheetnames", "Légende": "xl_cols", "Sélecteur": "xl_cols"},
        title="Démonstration — carte de tronçons",
        **common,
    )
    gen_carte(
        macarte_simple,
        out / "app_simple.html",
        datasets={"tronloc": datasets["tronloc"]},
        select={"Feuille": "xl_sheetnames"},
        title="Démonstration — carte minimale",
        **common,
    )
    standalone = gen_carte(
        macarte_complete,
        out / "standalone" / "app_standalone.html",
        datasets=datasets,
        select={"Feuille": "xl_sheetnames", "Légende": "xl_cols", "Sélecteur": "xl_cols"},
        title="Démonstration — carte de tronçons",
        wheel_path=wheel,
        attribution_config=ATTRIBUTION,
    )

    _write_index(out, standalone.stat().st_size / 1e6)
    _check_no_secret(out)
    print(f"Démo générée dans {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
