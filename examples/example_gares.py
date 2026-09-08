import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

try:
    from _data_sources import load_example
except ModuleNotFoundError:  # pragma: no cover - fallback for pytest and local imports
    from examples._data_sources import load_example

from cartes_multicouches import (
    AnnotationConfig,
    CarteDynMulti,
    ColorMapping,
    GlobalDataConfig,
    LayerConfig,
    LayerIndicator,
    LegendConfig,
    LegendEntry,
    MapConfig,
    SizeMapping,
    StyleConfig,
)

codes_lignes_rfn = [
    "001000",
    "005000",
    "014000",
    "070000",
    "089000",
    "115000",
    "180000",
    "216000",
    "226000",
    "270000",
    "272000",
    "340000",
    "366000",
    "420000",
    "431000",
    "450000",
    "468000",
    "470000",
    "515000",
    "538000",
    "570000",
    "590000",
    "640000",
    "655000",
    "677000",
    "750000",
    "753000",
    "752000",
    "785000",
    "787000",
    "790000",
    "810000",
    "830000",
    "850000",
    "883000",
    "884000",
    "890000",
    "905000",
    "930000",
]

# 1. Couleurs
COLOR_GARE_A = "#1f77b4"  # Segment DRG - A (Grandes gares)
COLOR_GARE_B = "#ff7f0e"  # Segment DRG - B
COLOR_GARE_AUTRE = "#7f7f7f"  # Autres segments

COLOR_EXPLOITEE = "#2ca02c"  # Lignes exploitées
COLOR_NON_EXPLOITEE = "#d62728"  # Lignes fermées / non exploitées

SIZE_GARE_A = 10
SIZE_GARE_B = 6
SIZE_GARE_AUTRE = 6


def default_output_path() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "docs" / "index.html"


def build_sample_map(output_path: Path | str = "example_map_gares.html") -> Path:
    fichier_gares = load_example("gares_voyageurs")
    fichier_lignes = load_example("lignes_rfn")

    gdf_gares_full = gpd.read_file(fichier_gares).assign(
        categorie_drg=lambda s: s["segment_drg"].apply(lambda x: x if x in ["A", "B"] else "Autre")
    )
    gdf_lignes_full = gpd.read_file(fichier_lignes)

    mask_a = gdf_gares_full["categorie_drg"] == "A"
    gdf_gares = gpd.GeoDataFrame(
        pd.concat(
            [
                gdf_gares_full.loc[mask_a],
                gdf_gares_full.loc[~mask_a].sample(n=min(100, (~mask_a).sum()), random_state=42),
            ]
        ),
        crs=gdf_gares_full.crs,
    )
    gdf_lignes = gdf_lignes_full.loc[gdf_lignes_full["code_ligne"].isin(codes_lignes_rfn)]
    gdf_lignes["filtre_annotation"] = gdf_lignes["mnemo"] == "EXPLOITE"

    # 4. Configuration des couches avec les colonnes réelles de l'Open Data SNCF
    layers = [
        LayerConfig(
            name="Gares de voyageurs",
            data=gdf_gares,
            style=StyleConfig(
                color=ColorMapping(
                    column="categorie_drg", mapping={"A": COLOR_GARE_A, "B": COLOR_GARE_B}
                ),
                missing_color=COLOR_GARE_AUTRE,
                size_or_width=SizeMapping(
                    column="categorie_drg",
                    mapping={"A": SIZE_GARE_A, "B": SIZE_GARE_B, "Autre": SIZE_GARE_AUTRE},
                ),
                marker="circle",
                alpha=0.9,
            ),
            tooltips=[
                ("Gare", "@nom"),
                ("Code INSEE", "@codeinsee"),
                ("Segment DRG", "@segment_drg"),
            ],
            columns_to_show=["nom", "codeinsee", "segment_drg"],
            indicators=[
                LayerIndicator(label="Nombre de gares", kind="count"),
            ],
            visible_by_default=True,
        ),
        LayerConfig(
            name="Formes des lignes (RFN)",
            data=gdf_lignes,
            style=StyleConfig(
                color=ColorMapping(column="mnemo", mapping={"EXPLOITE": COLOR_EXPLOITEE}),
                missing_color=COLOR_NON_EXPLOITEE,
                size_or_width=3,
                alpha=0.8,
            ),
            tooltips=[
                ("Ligne", "@libelle"),
                ("Code Ligne", "@code_ligne"),
                ("Statut", "@mnemo"),
            ],
            columns_to_show=["libelle", "code_ligne", "mnemo"],
            indicators=[
                LayerIndicator(label="Nombre de tronçons", kind="count"),
                LayerIndicator(label="Somme de rg_troncon", kind="sum", column="rg_troncon"),
            ],
            annotation=AnnotationConfig(
                text="code_ligne",
                x_offset=0,
                y_offset=0,
                text_align="center",
                text_font_size="10px",
                text_color="black",
                background_fill_color="white",
                border_line_color="red",
                padding=2,
                subset_column="filtre_annotation",
            ),
            visible_by_default=True,
            show_endpoints=True,
        ),
    ]

    # 5. Configuration des filtres et de la carte
    data_config = GlobalDataConfig(
        global_filters=[],
        global_select_filters=["code_ligne"],
        specific_filters={
            "Gares de voyageurs": ["categorie_drg"],
            "Formes des lignes (RFN)": ["mnemo"],
        },
        specific_select_filters={
            "Gares de voyageurs": ["nom"],
        },
        specific_filters_order={
            "Gares de voyageurs": {"categorie_drg": ["A", "B", "Autre"]},
            "Formes des lignes (RFN)": {"mnemo": ["EXPLOITE", "FERME"]},
        },
    )

    map_config = MapConfig(
        title="Extrait de carte du Réseau Ferré National : gares et lignes",
        height=750,
        left_panel_width=200,
        tile_provider_api_key=os.getenv("CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY"),
    )

    # 6. Légende explicite
    legend_config = LegendConfig(
        title="Légende SNCF",
        entries=[
            LegendEntry(
                label="Gare Segment A (Nationale)",
                color=COLOR_GARE_A,
                shape="point",
                marker="circle",
                size=SIZE_GARE_A,
            ),
            LegendEntry(
                label="Gare Segment B (Régionale)",
                color=COLOR_GARE_B,
                shape="point",
                marker="circle",
                size=SIZE_GARE_B,
            ),
            LegendEntry(
                label="Autre gare",
                color=COLOR_GARE_AUTRE,
                shape="point",
                marker="circle",
                size=SIZE_GARE_AUTRE,
            ),
            LegendEntry(
                label="Ligne exploitée",
                color=COLOR_EXPLOITEE,
                shape="line",
                size=3,
            ),
            LegendEntry(
                label="Ligne non exploitée",
                color=COLOR_NON_EXPLOITEE,
                shape="line",
                size=3,
            ),
        ],
    )

    carte = CarteDynMulti(
        layers,
        map_config=map_config,
        data_config=data_config,
        legend_config=legend_config,
    )

    output_path = Path(output_path)
    carte.save(output_path, resources="inline")
    return output_path


if __name__ == "__main__":
    output_file = default_output_path()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    generated = build_sample_map(output_file)
    print(f"Page HTML générée : {generated}")
