from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point

from cartes_multicouches import (
    CarteDynMulti,
    ColorMapping,
    GlobalDataConfig,
    LayerConfig,
    LegendConfig,
    LegendEntry,
    MapConfig,
    StyleConfig,
)

# Couleurs partagées entre le style des couches et la légende : la légende
# étant déclarative et découplée des couches, c'est à l'appelant de garder
# les deux cohérents (rien ne les lie automatiquement).
COLOR_VILLES = "#1f77b4"
COLOR_GARES = "#ff7f0e"
COLOR_OUVERTE = "#2ca02c"
COLOR_FERMEE = "#d62728"


def build_sample_map(output_path: Path | str = "example_map.html") -> Path:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B", "C"],
            "category": ["villes", "gares", "villes"],
            "type": ["point", "point", "point"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86), Point(2.33, 48.84)],
        crs="EPSG:4326",
    )

    lines = gpd.GeoDataFrame(
        {
            "name": ["Ligne 1", "Ligne 2"],
            "line_no": ["1", "2"],
            "status": ["ouverte", "fermée"],
        },
        geometry=[
            LineString([(2.33, 48.84), (2.36, 48.86)]),
            LineString([(2.34, 48.85), (2.32, 48.83)]),
        ],
        crs="EPSG:4326",
    ).assign(
        col1="coucoulong",
        col2="coucoulong2",
        col3="coucoulong3",
        col4="coucoulong4",
        col5="coucoulong5",
    )

    layers = [
        LayerConfig(
            name="Points d'intérêt",
            data=points,
            style=StyleConfig(
                color=ColorMapping(
                    column="category", mapping={"villes": COLOR_VILLES, "gares": COLOR_GARES}
                ),
                size_or_width=12,
                marker="diamond",
                alpha=0.9,
            ),
            tooltips=[("Nom", "@name"), ("Type", "@type")],
            columns_to_show=["name", "category", "type"],
            visible_by_default=True,
        ),
        LayerConfig(
            name="Tronçons",
            data=lines,
            style=StyleConfig(
                color=ColorMapping(
                    column="status", mapping={"ouverte": COLOR_OUVERTE, "fermée": COLOR_FERMEE}
                ),
                size_or_width=4,
                line_dash="dashed",
                alpha=0.8,
            ),
            tooltips=[("Route", "@name"), ("N° ligne", "@line_no"), ("État", "@status")],
            # columns_to_show=["name", "line_no", "status"],
            visible_by_default=True,
        ),
    ]

    data_config = GlobalDataConfig(
        global_select_filters=["line_no"],
        global_select_filters_order={"line_no": ["1", "2"]},
        global_filters=["status"],
        specific_filters={"Points d'intérêt": ["category"]},
    )
    map_config = MapConfig(title="Exemple de carte multi-couches", height=700, left_panel_width=150)

    # La légende est déclarée à part, indépendamment des LayerConfig : ses
    # entrées peuvent regrouper/renommer librement les valeurs des couches.
    legend_config = LegendConfig(
        title="Légende",
        entries=[
            LegendEntry(
                label="Villes", color=COLOR_VILLES, shape="point", marker="diamond", size=12
            ),
            LegendEntry(label="Gares", color=COLOR_GARES, shape="point", marker="diamond", size=12),
            LegendEntry(label="Ligne ouverte", color=COLOR_OUVERTE, shape="line", size=4),
            LegendEntry(label="Ligne fermée", color=COLOR_FERMEE, shape="line", size=4),
        ],
    )

    carte = CarteDynMulti(
        layers,
        map_config=map_config,
        data_config=data_config,
        legend_config=legend_config,
    )
    output_path = Path(output_path)
    carte.save(output_path)
    return output_path


output_dir = Path(__file__).parent / "output"
output_dir.mkdir(exist_ok=True)
output_file = build_sample_map(output_dir / "example_map.html")
print(f"Page HTML générée : {output_file}")
