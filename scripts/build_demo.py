"""Construit la démonstration publique du builder dans `docs/builder/`.

Usage :
    uv run python scripts/build_demo.py [--out docs/builder] [--refresh]

Étapes :
  1. référentiel public des PK (OpenData SNCF, ODbL) -> cache `build/tronloc.parquet`
  2. wheel de cartes_multicouches (`uv build`)
  3. fichier Excel de test
  4. applications PyScript : version légère (assets chargés par pyfetch) et autoportante
  5. page d'accueil de la démo + vérification qu'aucun secret n'a été publié

Aucune clé d'API n'est utilisée : les tuiles viennent d'un fournisseur sans clé.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from cartes_builder import (
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
ATTRIBUTION = {
    "text": "@efbulle · Données : SNCF / SNCF Réseau (open data), extras-opendata-sncf-reseau (ODbL)",
    "href": "https://github.com/efbulle",
}
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


INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>cartes_multicouches — démonstrations</title>
<meta name="description" content="Cartes Bokeh multi-couches filtrables à partir d’un fichier Excel de tronçons, sans serveur Python.">
<meta property="og:type" content="website">
<meta property="og:title" content="cartes_multicouches — démonstrations">
<meta property="og:description" content="Cartes Bokeh multi-couches filtrables à partir d’un fichier Excel de tronçons, sans serveur Python.">
<meta property="og:image" content="https://efbulle.github.io/cartes_multicouches/preview.png">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🗺️%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#f4f6fa;--panel:#fff;--border:#dde3ec;--text:#1e2530;--muted:#657084;
--accent:#2d5ba3;--accent-dark:#0d3f8f;--soft:#e4edf9;--radius:14px}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
color:var(--text);background:var(--bg);line-height:1.55}
a{color:var(--accent)}
.wrap{max-width:68rem;margin:0 auto}

/* Hero */
.hero{background:linear-gradient(135deg,#0d3f8f 0%,#2d5ba3 60%,#4a82cc 100%);color:#fff;
text-align:center;padding:4rem 1.25rem 8rem}
.hero h1{margin:0 auto .8rem;max-width:60rem;font-size:clamp(1.8rem,4vw,2.4rem);
line-height:1.15;text-wrap:balance}
.hero .lead{margin:0 auto;max-width:56rem;font-size:1.1rem;opacity:.92;text-wrap:balance}
.hero .cta{display:flex;flex-wrap:wrap;justify-content:center;gap:.75rem;margin-top:1.6rem}

/* Boutons */
.btn{display:inline-block;padding:.7rem 1.3rem;border-radius:999px;font-weight:600;
text-decoration:none;border:2px solid #fff;transition:transform .12s,background .12s,color .12s}
.btn:hover{transform:translateY(-1px)}
.btn--primary{background:#fff;color:var(--accent-dark)}
.btn--ghost{color:#fff}
.btn--ghost:hover{background:rgba(255,255,255,.15)}
.btn:focus-visible{outline:3px solid #ffd54a;outline-offset:3px}

/* Aperçu */
.preview{margin:-5rem 0 0;padding:0}
.preview a{display:block;border-radius:var(--radius);overflow:hidden;background:var(--panel);
box-shadow:0 18px 50px rgba(13,63,143,.28);border:1px solid var(--border)}
.preview a:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.preview img{display:block;width:100%;height:auto;transition:transform .3s}
.preview a:hover img{transform:scale(1.012)}
.preview figcaption{padding:.6rem 1rem;font-size:.85rem;color:var(--muted);background:var(--panel)}

h2{margin:3rem 0 1rem;font-size:1.4rem}

/* Cartes */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:1.1rem}
.card{display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--border);
border-radius:var(--radius);padding:1.3rem;text-decoration:none;color:inherit;
transition:box-shadow .15s,transform .15s,border-color .15s}
.card:hover{box-shadow:0 10px 28px rgba(30,37,48,.12);transform:translateY(-2px);
border-color:var(--accent)}
.card:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.card .tag{align-self:flex-start;font-size:.72rem;font-weight:700;letter-spacing:.05em;
text-transform:uppercase;color:var(--accent);background:var(--soft);padding:.2rem .6rem;
border-radius:999px}
.card h3{margin:.8rem 0 .4rem;font-size:1.1rem}
.card p{margin:0 0 1rem;color:var(--muted);font-size:.95rem}
.card .go{margin-top:auto;font-weight:600;color:var(--accent)}

/* Étapes */
.how{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:1.1rem;
counter-reset:step;padding:0;list-style:none}
.how li{counter-increment:step;background:var(--panel);border:1px solid var(--border);
border-radius:var(--radius);padding:1.1rem 1.2rem 1.1rem 3.4rem;position:relative}
.how li::before{content:counter(step);position:absolute;left:1rem;top:1rem;width:1.8rem;
height:1.8rem;border-radius:50%;background:var(--accent);color:#fff;font-weight:700;
display:grid;place-items:center}

footer{margin:3.5rem 0 2rem;padding-top:1.2rem;border-top:1px solid var(--border);
font-size:.85rem;color:var(--muted)}

/* Mobile */
@media (max-width:30rem){.hero .cta .btn{width:100%;text-align:center}}

/* Mouvement réduit */
@media (prefers-reduced-motion:reduce){
*{transition:none!important}
.btn:hover,.card:hover,.preview a:hover img{transform:none}}
</style>
</head>
<body>
<header class="hero"><div class="wrap">
<h1>Des cartes interactives, construites dans votre navigateur</h1>
<p class="lead"><strong>cartes_multicouches</strong> assemble des cartes Bokeh multi-couches filtrables.
Le builder en fait des pages HTML qui transforment un simple fichier Excel de tronçons en carte,
sans serveur Python.</p>
<div class="cta">
<a class="btn btn--primary" href="app.html">Essayer l’application</a>
<a class="btn btn--ghost" href="../index.html">Voir la carte d’exemple</a>
<a class="btn btn--ghost" href="https://github.com/efbulle/cartes_multicouches">GitHub</a>
</div></div></header>

<main class="wrap">
<figure class="preview">
<a href="../index.html"><img src="../preview.png" alt="Carte du réseau ferré : gares et lignes, avec filtres, indicateurs et légende"></a>
<figcaption>Un extrait de ce que produit le package&nbsp;: couches, filtres, indicateurs et légende.
Cliquez pour ouvrir la carte interactive.</figcaption>
</figure>

<h2>Les démonstrations</h2>
<div class="cards">
<a class="card" href="../index.html"><span class="tag">Carte Bokeh</span>
<h3>Réseau ferré&nbsp;: gares et lignes</h3>
<p>Rendu direct, ultra-rapide&nbsp;: plusieurs couches, filtres, tables liées et indicateurs.</p>
<span class="go">Ouvrir la carte&nbsp;→</span></a>
<a class="card" href="app.html"><span class="tag">Application</span>
<h3>Studio PyScript</h3>
<p>Importez un .xlsx, choisissez la feuille, la légende et le sélecteur, puis construisez et
exportez la carte.</p><span class="go">Lancer le studio&nbsp;→</span></a>
<a class="card" href="app_simple.html"><span class="tag">Application</span>
<h3>Version minimale</h3>
<p>Une seule couche de tronçons géolocalisés&nbsp;: le plus court chemin de l’Excel à la carte.</p>
<span class="go">Essayer&nbsp;→</span></a>
<a class="card" href="standalone/app_standalone.html"><span class="tag">Hors ligne</span>
<h3>Version autoportante</h3>
<p>Un seul fichier de {standalone_mb:.0f}&nbsp;Mo qui embarque tout&nbsp;: à télécharger et à partager.</p>
<span class="go">Ouvrir&nbsp;→</span></a>
</div>

<h2>Comment ça marche</h2>
<ol class="how">
<li><a href="test_tron.xlsx">Téléchargez test_tron.xlsx</a> ou préparez votre fichier
(<code>code_ligne</code>, PK début et fin en km).</li>
<li>Ouvrez le studio et chargez le fichier. Le premier démarrage prend quelques secondes.</li>
<li>Choisissez les paramètres puis cliquez sur &laquo;&nbsp;Construire la carte&nbsp;&raquo;.</li>
<li>Sauvegardez le résultat en HTML autonome.</li>
</ol>

<footer>
<p><strong>Sources des données.</strong>
Les gares et les lignes du réseau ferré national proviennent de l’open data de
<a href="https://data.sncf.com/">SNCF et SNCF Réseau</a>.</p>
<p>La géolocalisation des tronçons s’appuie sur les jeux de données du dépôt
<a href="https://github.com/nicolaswurtz/extras-opendata-sncf-reseau">nicolaswurtz/extras-opendata-sncf-reseau</a>.
Ils sont intégralement fabriqués par transformation ou extrapolation des jeux de données
publiés en open data, entre autres, par SNCF et SNCF Réseau
(cf. <a href="https://data.sncf.com/">data.sncf.com</a>), et sont diffusés sous
<a href="https://opendatacommons.org/licenses/odbl/1.0/index.html">licence ODbL</a>.</p>
<p>Tuiles&nbsp;: Esri World Gray Canvas, sans clé d’API. Code source et documentation sur
<a href="https://github.com/efbulle/cartes_multicouches">GitHub</a>.</p>
</footer>
</main>
</body>
</html>
"""


def _write_index(out: Path, standalone_mb: float) -> None:
    page = INDEX_TEMPLATE.replace("{standalone_mb:.0f}", f"{standalone_mb:.0f}")
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
