# cartes-multicouches-builder

Génère des pages HTML [PyScript](https://pyscript.net) qui construisent des cartes
[`cartes_multicouches`](../README.md) dans le navigateur à partir d'un fichier Excel
(sélecteur de feuille/colonnes, bouton « Construire », export HTML de la carte).

Sous-projet du dépôt `cartes_multicouches` (workspace uv), **non inclus dans son wheel**.
Il embarque ce wheel dans les pages générées.

```bash
uv sync --group dev                      # installe cartes_builder dans le workspace
pip install "git+https://github.com/efbulle/cartes_multicouches#subdirectory=builder"  # autre projet
```

## Usage

```python
from cartes_builder import Dataset, gen_carte


def macarte(xl, feuille, tronloc, attribution_config):
    df = pd.read_excel(xl, sheet_name=feuille)
    gdf = ajoute_geo(
        df,
        tronloc,
        on="code_ligne",
        pk_lbls=("pkmd", "pkmf"),
        tronloc_pk_lbls=("pkmd", "pkmf"),
        pk_unit_m=1000.0,
    )
    return CarteDynMulti(...)


gen_carte(
    macarte,
    "output/carte.html",
    datasets={"tronloc": Dataset("data/tronloc.parquet")},
    select={"Feuille": "xl_sheetnames"},
    repo_dir="../cartes_multicouches",  # ou wheel_path=...
)
```

- Les paramètres finaux de `macarte` nommés comme une clé de `datasets`, `attribution_config`
  ou `tile_provider_api_key` sont fournis par la page ; les autres reçoivent la valeur des
  `select` (`"xl_sheetnames"`, `"xl_cols"` ou une liste de choix).
- `macarte` est copiée dans la page : elle ne peut utiliser que ses arguments, les noms
  importés par la page (`cartes_multicouches`, `pd`, `gpd`...) et les fonctions des modules
  injectés (`geoloc_modules`, par défaut `cartes_builder.geoloc.ajoute_geo`).

## Deux modes

| | `standalone=True` (défaut) | `standalone=False` |
|---|---|---|
| Wheel et données | embarqués en base64 (un seul fichier) | `assets/` chargé par `pyfetch` |
| Serveur nécessaire | non | oui (GitHub Pages...) |
| Jeux `private=True`, clé d'API | acceptés | **refusés** |

Les jeux « geo » sont arrondis à 0,1 m et compressés (gzip) pour limiter le poids.

## Référentiel public et unités

`cartes_builder.data.download_and_prepare_tronloc` construit, depuis les
[PK OpenData SNCF](https://github.com/nicolaswurtz/extras-opendata-sncf-reseau) (ODbL),
un GeoDataFrame EPSG:3857 : `code_ligne` (entier), `pkmd`, `pkmf` en **kilomètres**.
`ajoute_geo` joint sur `on` et suppose des PK de même unité dans les deux tables ;
`pk_unit_m` (1000 pour des km) sert à dimensionner la fenêtre des PK ponctuels.

## Usage privé

Référentiel ad hoc + clé d'API : voir [`examples/private_builder.py`](examples/private_builder.py).
Le fichier produit contient données et clé en clair : le diffuser seulement en interne et
restreindre la clé côté fournisseur (domaines autorisés).

## Démonstration

`scripts/build_demo.py` génère `docs/builder/` (carte Bokeh classique, applications PyScript
légères et version autoportante) avec des tuiles sans clé (`Esri.WorldGrayCanvas`).
