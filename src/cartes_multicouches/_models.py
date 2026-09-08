from dataclasses import dataclass, field
from typing import Any, Literal

import geopandas as gpd
import pandas as pd
from bokeh import models

# Noms de colonnes utilisés comme contrat entre le Python et le JS embarqué.
# Toute modification ici doit rester cohérente avec le code des CustomJS.
COL_INDEX_STR = "index_str"
COL_COLOR_MAP = "__color_map"
COL_SIZE_MAP = "__size_map"
COL_X = "x"
COL_Y = "y"
COL_XS = "xs"
COL_YS = "ys"
COL_X_START = "x_start"
COL_Y_START = "y_start"
COL_X_END = "x_end"
COL_Y_END = "y_end"
COL_ANN_X = "__ann_x"
COL_ANN_Y = "__ann_y"

# Colonnes de plomberie interne : jamais montrées dans les tooltips/tables par défaut.
INTERNAL_COLUMNS = {COL_INDEX_STR, COL_COLOR_MAP, COL_SIZE_MAP, COL_ANN_X, COL_ANN_Y}

# Constantes UI pour éviter les nombres magiques dispersés.
OVERLAY_EDGE_OFFSET_PX = 10
OVERLAY_TOP_WITH_TOOLBAR_OFFSET_PX = 44
OVERLAY_BOX_GAP_PX = 36
LEGEND_BUTTON_WIDTH_PX = 90
TABLES_BUTTON_WIDTH_PX = 72
TABLES_BUTTON_SPACING_PX = 6
OVERLAY_BUTTON_HEIGHT_PX = 28
LAYER_VISIBILITY_BUTTON_WIDTH_PX = 82
LAYER_VISIBILITY_PANEL_WIDTH_PX = 220
LAYER_VISIBILITY_PANEL_GAP_PX = 8

SELECT_BTN_ALL_WIDTH_PX = 34
SELECT_BTN_NONE_WIDTH_PX = 40
SELECT_BTN_HEIGHT_PX = 17
SELECT_BTN_FONT_SIZE_PX = 7
SELECT_BTN_LINE_HEIGHT_PX = 16
SELECT_BTN_SPACING_PX = 6

LEFT_PANEL_MIN_WIDTH_PX = 180
LEFT_PANEL_MAX_WIDTH_PX = 360
LEFT_PANEL_PX_PER_CHAR = 7.2
LEFT_PANEL_CHROME_PADDING_PX = 50
FILTER_HELP_FONT_SIZE_PX = 11

#: Géométries prises en charge par CarteDynMulti. Toute autre valeur de
#: geom_type (Polygon, MultiPolygon, MultiPoint, GeometryCollection...)
#: est rejetée explicitement dans _build_layer_columns.
SUPPORTED_GEOMETRY_TYPES = {"Point", "LineString", "MultiLineString"}


@dataclass(frozen=True)
class DiscreteMapping[T]:
    """Valeur dérivée d'une colonne via un mapping explicite valeur -> T."""

    column: str
    mapping: dict[str, T]


class ColorMapping(DiscreteMapping[str]):
    """Couleur dérivée d'une colonne via un mapping explicite valeur -> couleur."""


class SizeMapping(DiscreteMapping[float]):
    """Taille dérivée d'une colonne via un mapping explicite valeur -> taille."""


@dataclass
class StyleConfig:
    """Paramètres visuels d'une couche."""

    color: str | ColorMapping | None = "navy"
    missing_color: str = "gray"
    size_or_width: int | float | str | SizeMapping = 3
    missing_size_or_width: int | float = 3
    alpha: float = 0.8
    nonselection_alpha: float = 0.15
    marker: str = "circle"
    line_dash: str = "solid"
    hover_mode: Literal["mouse", "hline", "vline"] = "mouse"
    endpoint_color: str = "#111111"
    endpoint_size: int | float = 8


@dataclass(frozen=True)
class LayerIndicator:
    """Indicateur agrégé affiché pour une couche."""

    label: str
    kind: Literal["count", "sum"]
    column: str | None = None


@dataclass
class InteractionConfig:
    """Configuration des interactions de survol et de clic d'une couche."""

    hover: bool = True
    tooltips: bool = True
    tap: bool = True


@dataclass
class AnnotationConfig:
    """Configuration d'annotations textuelles liées à une couche."""

    text: str
    x: str = COL_ANN_X
    y: str = COL_ANN_Y
    #: Décalage horizontal en pixels. Un nombre s'applique à toutes les
    #: étiquettes de la couche ; le nom d'une colonne du GeoDataFrame permet
    #: un offset différent par étiquette (valeurs en pixels écran, stables
    #: quel que soit le niveau de zoom).
    x_offset: int | float | str = 0
    #: Décalage vertical en pixels. Mêmes règles que ``x_offset``.
    y_offset: int | float | str = 0
    text_align: Literal["left", "center", "right"] = "center"
    text_font_size: str = "12px"
    text_color: str = "black"
    background_fill_color: str | None = "white"
    border_line_color: str | None = "red"
    padding: int = 2
    text_args: dict[str, Any] = field(default_factory=dict)
    #: Nom d'une colonne booléenne du GeoDataFrame de la couche. Si renseigné,
    #: seules les lignes où cette colonne vaut True sont annotées ; les autres
    #: gardent leur géométrie affichée mais n'ont pas de texte. Ce sous-ensemble
    #: est statique (fixé à la construction de la carte) et se combine avec le
    #: filtrage interactif : une ligne exclue par un widget de filtre reste
    #: masquée même si elle fait partie du sous-ensemble annoté.
    subset_column: str | None = None


@dataclass
class LayerConfig:
    """Configuration d'une couche Bokeh."""

    name: str
    data: gpd.GeoDataFrame
    style: StyleConfig = field(default_factory=StyleConfig)
    tooltips: list[tuple[str, str]] | None = None
    columns_to_show: list[str] | None = None
    indicators: list[LayerIndicator] | None = None
    annotation: AnnotationConfig | None = None
    interaction: InteractionConfig = field(default_factory=InteractionConfig)
    visible_by_default: bool = True
    has_table: bool = True
    show_endpoints: bool = False


@dataclass
class LayerColumns:
    """Résultat pur du calcul des colonnes d'une couche, sans aucun objet Bokeh."""

    gdf: gpd.GeoDataFrame
    source_data: pd.DataFrame
    geometry_type: str
    color_field: str | dict[str, Any]
    size_field: int | float | str
    tooltips: list[tuple[str, str]]


@dataclass(frozen=True)
class ColorResolution:
    """Résolution explicite de la couleur d'une couche."""

    color_spec: str | dict[str, Any]
    derived_column: pd.Series | None = None
    field_name: str | None = None


@dataclass(frozen=True)
class SizeResolution:
    """Résolution explicite de la taille/largeur d'une couche."""

    size_spec: int | float | str
    derived_column: pd.Series | None = None
    field_name: str | None = None


@dataclass
class LayerState:
    """État Bokeh d'une couche enregistrée."""

    cfg: LayerConfig
    raw_data: gpd.GeoDataFrame
    indicator_specs: list[dict[str, Any]]
    src_geo: models.ColumnDataSource
    filtre: models.IndexFilter
    view: models.CDSView
    renderer: models.GlyphRenderer
    annotation_renderer: models.GlyphRenderer | None = None
    endpoint_renderers: tuple[models.GlyphRenderer, models.GlyphRenderer] | None = None


@dataclass
class GlobalDataConfig:
    """Configuration des filtres partagés et spécifiques."""

    global_filters: list[str] = field(default_factory=list)
    global_select_filters: list[str] = field(default_factory=list)
    specific_filters: dict[str, list[str]] = field(default_factory=dict)
    specific_select_filters: dict[str, list[str]] = field(default_factory=dict)
    multi_select_size: int = 4
    global_filters_order: dict[str, list[str]] = field(default_factory=dict)
    global_select_filters_order: dict[str, list[str]] = field(default_factory=dict)
    specific_filters_order: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    specific_select_filters_order: dict[str, dict[str, list[str]]] = field(default_factory=dict)


@dataclass
class MapConfig:
    """Paramètres de mise en page et de carte."""

    title: str = "Carte Dynamique Multi-couches"
    height: int = 650
    width: int | None = None
    tile_provider: str = "CartoDB.Positron"
    tile_provider_api_key: str | None = None
    left_panel_width: int | None = None
    tables_panel_width: int = 320
    toolbar_location: Literal["above", "below", "left", "right"] | None = "above"
    legend_position: Literal["top-right", "top-left", "bottom-right", "bottom-left"] = "top-right"


@dataclass
class LegendEntry:
    """Une ligne de légende, déclarée indépendamment des couches réelles."""

    label: str
    color: str
    shape: Literal["point", "line"] = "point"
    marker: str = "circle"
    size: float = 10


@dataclass
class LegendConfig:
    """Configuration déclarative de la légende, séparée des LayerConfig."""

    title: str = "Légende"
    entries: list[LegendEntry] = field(default_factory=list)
    visible_by_default: bool = True
    width: int | None = None
    """Largeur (px) de la fenêtre de légende ; None = largeur automatique (200px max)."""


@dataclass
class AttributionConfig:
    """Configuration de la signature affichée sur la carte."""

    text: str = "@efbulle"
    href: str = "https://github.com/efbulle"
