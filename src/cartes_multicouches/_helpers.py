"""Constructeurs rapides pour les cas d'usage courants de CarteDynMulti."""

import geopandas as gpd

from ._models import (
    ColorMapping,
    GlobalDataConfig,
    InteractionConfig,
    LayerConfig,
    LegendConfig,
    MapConfig,
    SizeMapping,
    StyleConfig,
)
from .dynamic import CarteDynMulti

__all__ = ["carte_une_couche"]


def carte_une_couche(
    gdf: gpd.GeoDataFrame,
    *,
    # -- LayerConfig --
    name: str = "Tronçons",
    tooltips: list[tuple[str, str]] | None = None,
    columns_to_show: list[str] | None = None,
    interaction: InteractionConfig | None = None,
    # -- StyleConfig (sous-ensemble) --
    color: str | ColorMapping | None = "navy",
    alpha: float = 0.8,
    size_or_width: float | str | SizeMapping = 3,
    # -- MapConfig (sous-ensemble) --
    title: str = "Carte",
    height: int = 650,
    width: int | None = None,
    # -- GlobalDataConfig --
    filters: list[str] | None = None,
    multi_select_size: int = 4,
    # -- LegendConfig : transmis tel quel si fourni --
    legend_config: LegendConfig | None = None,
) -> CarteDynMulti:
    """Construit une CarteDynMulti à une seule couche de tronçons.

    Chaque paramètre correspond directement à un champ des dataclasses
    de configuration existantes (voir _models.py) et lui est transmis
    sans transformation. Pour tout paramètre non exposé ici, construire
    les dataclasses à la main et appeler CarteDynMulti directement.

    Args:
        gdf: GeoDataFrame de tronçons (LineString/MultiLineString).
        name: LayerConfig.name.
        tooltips: LayerConfig.tooltips.
        columns_to_show: LayerConfig.columns_to_show.
        interaction: LayerConfig.interaction ; InteractionConfig() par
            défaut si non fourni.
        color: StyleConfig.color.
        alpha: StyleConfig.alpha.
        size_or_width: StyleConfig.size_or_width.
        title: MapConfig.title.
        height: MapConfig.height.
        width: MapConfig.width.
        filters: colonnes pour des MultiSelect spécifiques à la couche
            (GlobalDataConfig.specific_filters[name]).
        multi_select_size: hauteur des MultiSelect, exprimée en nombre
            d'éléments visibles ; la valeur est automatiquement réduite si
            la liste d'options est plus courte.
        legend_config: LegendConfig transmis tel quel ; à construire par
            l'appelant, aucune dérivation automatique n'est faite ici.

    Returns:
        Une instance CarteDynMulti déjà construite (appeler .show() ou
        .save() ensuite).
    """
    layer_cfg = LayerConfig(
        name=name,
        data=gdf,
        style=StyleConfig(color=color, alpha=alpha, size_or_width=size_or_width),
        tooltips=tooltips,
        columns_to_show=columns_to_show,
        interaction=interaction or InteractionConfig(),
    )

    data_config = GlobalDataConfig(
        specific_filters={name: filters} if filters else {},
        multi_select_size=multi_select_size,
    )

    return CarteDynMulti(
        layers_config=[layer_cfg],
        map_config=MapConfig(title=title, height=height, width=width),
        data_config=data_config,
        legend_config=legend_config,
    )
