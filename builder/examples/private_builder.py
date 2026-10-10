"""Exemple d'usage privé du builder : référentiel ad hoc et clé d'API pour les tuiles.

Les chemins ci-dessous sont fictifs : adaptez-les. Le fichier produit contient les
données privées et la clé en clair ; il ne doit donc pas être publié
(`standalone=True` est le seul mode accepté dès qu'un jeu est `private=True`
ou qu'une clé est utilisée).

La clé est lue dans la variable d'environnement CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY
(ou passée via `tile_provider_api_key=`).
"""

from pathlib import Path

import pandas as pd
from cartes_builder import Dataset, gen_carte

from cartes_multicouches import (
    AttributionConfig,
    CarteDynMulti,
    InteractionConfig,
    LayerConfig,
    MapConfig,
    StyleConfig,
)

REPO_CARTES = Path("../cartes_multicouches")  # dépôt où `uv build` a produit dist/*.whl
REFERENTIEL_PRIVE = Path("data/referentiel_prive.parquet")
MODULE_GEOLOC_PRIVE = Path("monprojet/geoloc.py")  # définit `ajoute_geo` pour ce référentiel


def macarte(xl, feuille, referentiel, attribution_config, tile_provider_api_key):
    # `ajoute_geo` vient du module injecté via `geoloc_modules`.
    df = pd.read_excel(xl, sheet_name=feuille)
    gdf = ajoute_geo(  # noqa: F821
        df,
        referentiel,
        on="ligne",
        pk_lbls=("pkd", "pkf"),
        tronloc_pk_lbls=("pkd", "pkf"),
    )
    layer = LayerConfig(
        name="Tronçons",
        data=gdf,
        style=StyleConfig(color="red", size_or_width=3),
        interaction=InteractionConfig(),
    )
    return CarteDynMulti(
        layers_config=[layer],
        map_config=MapConfig(title=feuille, tile_provider_api_key=tile_provider_api_key),
        attribution_config=AttributionConfig(**attribution_config),
    )


if __name__ == "__main__":
    gen_carte(
        macarte,
        "output/carte_privee.html",
        datasets={"referentiel": Dataset(REFERENTIEL_PRIVE, private=True)},
        select={"Feuille": "xl_sheetnames"},
        geoloc_modules=[MODULE_GEOLOC_PRIVE],
        repo_dir=REPO_CARTES,
        standalone=True,
    )
