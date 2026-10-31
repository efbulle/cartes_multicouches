# API cartes_multicouches (résumé pour les cas avancés)

Référence complète : README du dépôt https://github.com/efbulle/cartes_multicouches

Import unique : `from cartes_multicouches import CarteDynMulti, LayerConfig, StyleConfig, ColorMapping, MapConfig, GlobalDataConfig, AnnotationConfig, LayerIndicator, LegendConfig, LegendEntry, AttributionConfig, InteractionConfig, carte_une_couche`

Contraintes : géométries Point, LineString ou MultiLineString (pas de polygones) ; CRS d'entrée libre (reprojeté en EPSG:3857) ; noms de couches uniques ; sortie = HTML autonome via `carte.save("x.html")`.

## Squelette

```python
import geopandas as gpd
from cartes_multicouches import (CarteDynMulti, LayerConfig, StyleConfig, ColorMapping,
                                 MapConfig, GlobalDataConfig)

couche = LayerConfig(
    name="Gares", data=gdf_points,                      # GeoDataFrame
    style=StyleConfig(color=ColorMapping(column="categorie",
                                         mapping={"gare": "#ff7f0e", "ville": "#1f77b4"})),
    tooltips=[("Nom", "@nom")],
)
carte = CarteDynMulti(
    [couche, autre_couche],                             # une couche par entrée
    map_config=MapConfig(title="Ma carte", tile_provider="EsriGrayCanvas"),
    data_config=GlobalDataConfig(global_filters=["categorie"]),
)
carte.save("carte.html")
```

## Points clés par classe

- `StyleConfig.color` : couleur fixe, nom de colonne (palette automatique), `ColorMapping(column, mapping)` ou `None`. Aussi `size_or_width`, `alpha`, `marker`, `line_dash`, `missing_color`.
- `LayerConfig` : `tooltips` (paires `(libellé, "@colonne")`), `columns_to_show` (tableau lié), `indicators`, `annotation`, `interaction`, `visible_by_default`, `has_table`, `show_endpoints` (lignes).
- `LayerIndicator(label, kind="count"|"sum", column=None)` : agrégat affiché en haut de la carte ; `column` obligatoire pour `sum`.
- `AnnotationConfig(text="colonne_texte", ...)` : étiquettes ; `subset_column` (colonne booléenne) restreint les lignes annotées.
- `GlobalDataConfig` : `global_filters` / `global_select_filters` (toutes les couches possédant la colonne), `specific_filters` / `specific_select_filters` (`{nom_couche: [colonnes]}`). Filtres appliqués côté navigateur.
- `LegendConfig(entries=[LegendEntry(label, color, shape="point"|"line")])` : légende déclarative, indépendante des couches. Garder les couleurs cohérentes à la main.
- `MapConfig` : `title`, `height`, `width`, `tile_provider` (défaut `CartoDB.Positron`, qui exige une clé API ; `EsriGrayCanvas` n'en demande pas), `tile_provider_api_key`.
- `carte_une_couche(gdf, ...)` : raccourci une couche, mais n'expose pas `tile_provider` ; pour un fond sans clé, utiliser `CarteDynMulti` directement.
