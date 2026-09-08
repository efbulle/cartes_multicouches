from pathlib import Path

import geopandas as gpd
import pandas as pd
from _data_sources import load_example

from cartes_multicouches import (
    AnnotationConfig,
    CarteDynMulti,
    GlobalDataConfig,
    InteractionConfig,
    LayerConfig,
    LegendConfig,
    LegendEntry,
    MapConfig,
    StyleConfig,
)


def _find_villes_csv() -> Path:
    candidates = [Path(__file__).resolve().parent / "data" / "villes.csv"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Le fichier villes.csv est introuvable. Placez-le dans le dossier examples "
        "ou adaptez le chemin ci-dessus."
    )


def build_sample_map(output_path: Path | str = "example_map_villes.html") -> Path:
    csv_path = _find_villes_csv()
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["x"], df["y"]),
        crs="EPSG:3857",
    )

    # Taille différente selon la colonne "pref"
    gdf["size"] = gdf["pref"].map({True: 12, False: 7})

    layer_points = LayerConfig(
        name="Villes",
        data=gdf,
        style=StyleConfig(
            color="#818588FF",
            size_or_width="size",
            marker="circle",
            alpha=0.95,
        ),
        tooltips=[],  # pas de tooltip interactif
        columns_to_show=["name", "pref"],
        interaction=InteractionConfig(hover=False, tooltips=False, tap=False),
        annotation=AnnotationConfig(
            text="name",
            x_offset=0,
            y_offset=-4,
            text_align="center",
            text_font_size="10px",
            text_color="#818588FF",
            background_fill_color=None,
            border_line_color=None,
            padding=2,
            text_args={"text_line_height": 1.1},
        ),
        visible_by_default=True,
        has_table=False,
    )

    lignes_path = load_example("lignes_rfn")
    lines_gdf = gpd.read_file(lignes_path).copy()
    lines_gdf = lines_gdf.loc[
        lambda s: s["mnemo"] == "EXPLOITE", ["code_ligne", "libelle", "geometry"]
    ].head(80)

    layer_lines = LayerConfig(
        name="Trajets",
        data=lines_gdf,
        style=StyleConfig(
            color="#2CA02C",
            size_or_width=3,
            alpha=0.9,
            line_dash="solid",
        ),
        tooltips=[("code_ligne", "@code_ligne"), ("Statut", "@libelle")],
        columns_to_show=["code_ligne", "libelle"],
        interaction=InteractionConfig(hover=True, tooltips=True, tap=True),
        visible_by_default=True,
        has_table=True,
    )

    carte = CarteDynMulti(
        [layer_points, layer_lines],
        map_config=MapConfig(
            title="Villes de France",
            height=700,
            left_panel_width=170,
            tile_provider="CartoDB.PositronNoLabels",
        ),
        data_config=GlobalDataConfig(),
        legend_config=LegendConfig(
            title="Légende",
            entries=[
                LegendEntry(
                    label="Préfecture",
                    color="#B3BAC1",
                    shape="point",
                    marker="circle",
                    size=12,
                ),
                LegendEntry(
                    label="Autre ville",
                    color="#B3BAC1",
                    shape="point",
                    marker="circle",
                    size=7,
                ),
                LegendEntry(label="Trajet", color="#2CA02C", shape="line", size=3),
            ],
        ),
    )

    output_path = Path(output_path)
    carte.save(output_path)
    return output_path


output_dir = Path(__file__).resolve().parent / "output"
output_dir.mkdir(exist_ok=True)
output_file = build_sample_map(output_dir / "example_map_villes.html")
print(f"Page HTML générée : {output_file}")
