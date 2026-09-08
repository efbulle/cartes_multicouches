"""Exemple autoportant : carte à une seule couche via carte_une_couche.

Génère quelques tronçons fictifs (LineString) et produit une carte HTML
autonome avec un filtre et une légende basique.

Usage :
    python example_carte_une_couche.py
"""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

from cartes_multicouches import ColorMapping, LegendConfig, LegendEntry, carte_une_couche

troncons = gpd.GeoDataFrame(
    {
        "libelle": ["Paris-Lyon", "Lyon-Marseille", "Paris-Lille"],
        "mnemo": ["TER", "FRET", "TER"],
    },
    geometry=[
        LineString([(2.35, 48.85), (4.83, 45.76)]),
        LineString([(4.83, 45.76), (5.37, 43.30)]),
        LineString([(2.35, 48.85), (3.06, 50.63)]),
    ],
    crs="EPSG:4326",
)

carte = carte_une_couche(
    troncons,
    name="Tronçons",
    tooltips=[("Ligne", "@libelle"), ("Type", "@mnemo")],
    color=ColorMapping(column="mnemo", mapping={"TER": "#1f77b4", "FRET": "#d62728"}),
    size_or_width=4,
    filters=["mnemo"],
    title="Exemple — carte à une couche",
    legend_config=LegendConfig(
        entries=[
            LegendEntry(label="TER", color="#1f77b4", shape="line", size=4),
            LegendEntry(label="FRET", color="#d62728", shape="line", size=4),
        ],
    ),
)

output_dir = Path(__file__).parent / "output"
output_dir.mkdir(exist_ok=True)
carte.save(output_dir / "example_carte_une_couche.html")
print(f"Page HTML générée : {output_dir / 'example_carte_une_couche.html'}")
