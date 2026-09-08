from typing import cast

import geopandas as gpd
import pytest
from bokeh.models import (
    CategoricalColorMapper,
    ColumnDataSource,
    HoverTool,
    IndexFilter,
    IntersectionFilter,
    Select,
    TapTool,
)
from bokeh.resources import INLINE
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from xyzservices import TileProvider

from cartes_multicouches import dynamic as dynamic_module
from cartes_multicouches._config import _load_pyproject_config
from cartes_multicouches._models import (
    COL_COLOR_MAP,
    COL_SIZE_MAP,
    ColorMapping,
    ColorResolution,
    InteractionConfig,
    SizeMapping,
    SizeResolution,
)
from cartes_multicouches.dynamic import (
    AnnotationConfig,
    AttributionConfig,
    CarteDynMulti,
    GlobalDataConfig,
    LayerConfig,
    LayerIndicator,
    MapConfig,
    StyleConfig,
)


def _minimal_points_layer() -> LayerConfig:
    points = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    return LayerConfig(name="Points", data=points)


def test_cartodb_api_key_is_injected_for_apikey_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TileProvider(
        name="CartoDB.Custom",
        url="https://tiles/{z}/{x}/{y}.png?key={apikey}",
        attribution="x",
    )
    monkeypatch.setattr(dynamic_module, "_load_tile_provider_key", lambda _override=None: "secret")
    monkeypatch.setattr(dynamic_module.xyz, "query_name", lambda _name: provider)

    carte = CarteDynMulti(
        [_minimal_points_layer()],
        map_config=MapConfig(tile_provider="CartoDB.Positron"),
    )

    tile_source = carte._resolve_tile_sources()[0]
    assert isinstance(tile_source, TileProvider)
    assert tile_source["apikey"] == "secret"


def test_cartodb_api_key_is_injected_for_key_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TileProvider(
        name="CartoDB.Legacy",
        url="https://tiles/{z}/{x}/{y}.png?key={key}",
        attribution="x",
    )
    monkeypatch.setattr(dynamic_module, "_load_tile_provider_key", lambda _override=None: "secret")
    monkeypatch.setattr(dynamic_module.xyz, "query_name", lambda _name: provider)

    carte = CarteDynMulti(
        [_minimal_points_layer()],
        map_config=MapConfig(tile_provider="CartoDB.Positron"),
    )

    tile_source = carte._resolve_tile_sources()[0]
    assert isinstance(tile_source, TileProvider)
    assert tile_source["key"] == "secret"


def test_layers_build_column_data_sources_for_points_and_lines() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "category": ["villes", "villes"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    lines = gpd.GeoDataFrame(
        {
            "name": ["Ligne 1"],
            "status": ["ouverte"],
        },
        geometry=[LineString([(2.33, 48.84), (2.36, 48.86)])],
        crs="EPSG:4326",
    )

    layers = [
        LayerConfig(
            name="Points",
            data=points,
            style=StyleConfig(color="category", size_or_width=12, marker="diamond"),
        ),
        LayerConfig(
            name="Tronçons",
            data=lines,
            style=StyleConfig(color="status", size_or_width=4, line_dash="dashed"),
        ),
    ]

    carte = CarteDynMulti(
        layers,
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    point_source = carte.layers["Points"].src_geo
    line_source = carte.layers["Tronçons"].src_geo
    point_data = cast(dict[str, list[object]], point_source.data)
    line_data = cast(dict[str, list[list[float]]], line_source.data)

    assert point_data["x"] is not None
    assert point_data["y"] is not None
    assert len(point_data["x"]) == 2

    assert line_data["xs"] is not None
    assert line_data["ys"] is not None
    assert len(line_data["xs"]) == 1


def test_layers_can_disable_hover_and_tap_tools() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A"],
        },
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
            interaction=InteractionConfig(hover=False, tooltips=False, tap=False),
        )
    ]

    carte = CarteDynMulti(
        layers,
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    assert not any(isinstance(tool, HoverTool) for tool in carte.fig.tools)
    assert not any(isinstance(tool, TapTool) for tool in carte.fig.tools)


def test_tap_tool_is_shared_across_layers() -> None:
    points = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    lines = gpd.GeoDataFrame(
        {"name": ["L1"]},
        geometry=[LineString([(2.33, 48.84), (2.36, 48.86)])],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [
            LayerConfig(name="Points", data=points),
            LayerConfig(name="Tronçons", data=lines),
        ],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    tap_tools = [tool for tool in carte.fig.tools if isinstance(tool, TapTool)]
    assert len(tap_tools) == 1
    assert len(tap_tools[0].renderers) == 2


def test_multiline_annotations_use_labelset_renderer() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["Clermont\nFerrand"],
        },
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    layer = LayerConfig(
        name="Points",
        data=points,
        annotation=AnnotationConfig(text="name"),
    )

    carte = CarteDynMulti(
        [layer],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    renderer = carte.layers["Points"].annotation_renderer
    assert renderer is not None
    assert hasattr(renderer.glyph, "text")


def test_escaped_newline_annotations_are_normalized() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["Clermont\\nFerrand"],
        },
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    layer = LayerConfig(
        name="Points",
        data=points,
        annotation=AnnotationConfig(text="name"),
    )

    carte = CarteDynMulti(
        [layer],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    renderer = carte.layers["Points"].annotation_renderer
    assert renderer is not None
    annotation_source = cast(ColumnDataSource, renderer.data_source)
    assert annotation_source.data["name"][0] == "Clermont\nFerrand"


def test_annotation_without_subset_column_shares_dynamic_view() -> None:
    """Non-régression : sans subset_column, le renderer d'annotation
    continue de partager exactement la vue du renderer géométrique."""
    points = gpd.GeoDataFrame(
        {"name": ["A", "B"]},
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    layer = LayerConfig(
        name="Points",
        data=points,
        annotation=AnnotationConfig(text="name"),
    )

    carte = CarteDynMulti(
        [layer],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    renderer = carte.layers["Points"].annotation_renderer
    assert renderer is not None
    assert renderer.view is carte.layers["Points"].view


def test_annotation_subset_column_restricts_static_indices() -> None:
    lines = gpd.GeoDataFrame(
        {
            "name": ["A", "B", "C"],
            "annoter": [True, False, True],
        },
        geometry=[
            LineString([(2.33, 48.84), (2.36, 48.86)]),
            LineString([(2.34, 48.85), (2.32, 48.83)]),
            LineString([(2.35, 48.86), (2.31, 48.82)]),
        ],
        crs="EPSG:4326",
    )
    layer = LayerConfig(
        name="Tronçons",
        data=lines,
        annotation=AnnotationConfig(text="name", subset_column="annoter"),
    )

    carte = CarteDynMulti(
        [layer],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    renderer = carte.layers["Tronçons"].annotation_renderer
    assert renderer is not None
    annotation_view = renderer.view
    assert isinstance(annotation_view.filter, IntersectionFilter)

    dynamic_operand, static_operand = annotation_view.filter.operands
    assert isinstance(dynamic_operand, IndexFilter)
    assert isinstance(static_operand, IndexFilter)
    # Le premier opérande est le même objet que le filtre dynamique du
    # renderer géométrique : les changements faits par filter_callback.js
    # continuent donc de s'appliquer aux annotations.
    assert dynamic_operand is carte.layers["Tronçons"].filtre
    assert static_operand.indices == [0, 2]

    # Le renderer géométrique, lui, n'est pas restreint par le sous-ensemble.
    geometry_view = carte.layers["Tronçons"].view
    assert geometry_view.filter is carte.layers["Tronçons"].filtre


def test_annotation_subset_column_with_multiline_text_still_filters() -> None:
    """Le sous-ensemble statique doit aussi s'appliquer sur le chemin
    LabelSet (texte multi-lignes), qui construit sa propre source/vue."""
    points = gpd.GeoDataFrame(
        {
            "name": ["Paris\nGare", "Lyon\nPart-Dieu"],
            "annoter": [True, False],
        },
        geometry=[Point(2.35, 48.85), Point(4.84, 45.75)],
        crs="EPSG:4326",
    )
    layer = LayerConfig(
        name="Gares",
        data=points,
        annotation=AnnotationConfig(text="name", subset_column="annoter"),
    )

    carte = CarteDynMulti(
        [layer],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    renderer = carte.layers["Gares"].annotation_renderer
    assert renderer is not None
    assert isinstance(renderer.view.filter, IntersectionFilter)
    _, static_operand = renderer.view.filter.operands
    assert isinstance(static_operand, IndexFilter)
    assert static_operand.indices == [0]


def test_annotation_missing_subset_column_raises_value_error() -> None:
    points = gpd.GeoDataFrame(
        {"name": ["A", "B"]},
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    layer = LayerConfig(
        name="Points",
        data=points,
        annotation=AnnotationConfig(text="name", subset_column="colonne_absente"),
    )

    with pytest.raises(ValueError, match="colonne_absente"):
        CarteDynMulti(
            [layer],
            map_config=MapConfig(title="Test", height=300),
            data_config=GlobalDataConfig(),
        )


def test_categorical_color_field_uses_color_mapper() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "category": ["villes", "routes"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
            style=StyleConfig(color="category", size_or_width=12, marker="diamond"),
        )
    ]
    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=GlobalDataConfig()
    )
    renderer = carte.layers["Points"].renderer
    fill_color = renderer.glyph.fill_color
    assert hasattr(fill_color, "transform")
    assert fill_color.transform is not None
    assert fill_color.transform.__class__.__name__ == "CategoricalColorMapper"


def test_color_column_uses_bokeh_colors_directly() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "color": ["#ff0000", "navy"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points, style=StyleConfig(color="color"))],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    fill_color = carte.layers["Points"].renderer.glyph.fill_color

    assert fill_color.field == "color"
    assert not isinstance(fill_color.transform, CategoricalColorMapper)


def test_partially_recognized_color_column_warns_and_uses_categorical_mapping() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "color": ["red", "ville"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )

    with pytest.warns(UserWarning, match=r"valeur\(s\) non reconnues comme couleur"):
        carte = CarteDynMulti(
            [LayerConfig(name="Points", data=points, style=StyleConfig(color="color"))],
            map_config=MapConfig(title="Test", height=300),
            data_config=GlobalDataConfig(),
        )

    fill_color = carte.layers["Points"].renderer.glyph.fill_color

    assert fill_color.field == "color"
    assert isinstance(fill_color.transform, CategoricalColorMapper)
    assert fill_color.transform.factors == ["red", "ville"]


def test_manual_color_mapping_uses_missing_color_from_style() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "status": ["ouverte", "fermée"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
            style=StyleConfig(
                color=ColorMapping(column="status", mapping={"ouverte": "green"}),
                missing_color="red",
            ),
        )
    ]
    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=GlobalDataConfig()
    )

    source = carte.layers["Points"].src_geo
    assert source.data[COL_COLOR_MAP][0] == "green"
    assert source.data[COL_COLOR_MAP][1] == "red"


def test_manual_size_mapping_uses_missing_size_from_style() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "status": ["ouverte", "fermée"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
            style=StyleConfig(
                size_or_width=SizeMapping(column="status", mapping={"ouverte": 11.0}),
                missing_size_or_width=5,
            ),
        )
    ]
    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=GlobalDataConfig()
    )

    source = carte.layers["Points"].src_geo
    assert source.data[COL_SIZE_MAP][0] == 11.0
    assert source.data[COL_SIZE_MAP][1] == 5.0


def test_resolve_color_field_returns_field_name_for_manual_mapping() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "status": ["ouverte", "fermée"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points)],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    result = carte._resolve_color_field(
        points,
        ColorMapping(column="status", mapping={"ouverte": "green"}),
        missing_color="red",
    )

    assert isinstance(result, ColorResolution)
    assert result.color_spec == COL_COLOR_MAP
    assert result.field_name == "status"
    assert result.derived_column is not None


def test_resolve_size_field_returns_field_name_for_manual_mapping() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "status": ["ouverte", "fermée"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points)],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    result = carte._resolve_size_field(
        points,
        SizeMapping(column="status", mapping={"ouverte": 11.0}),
        missing_size_or_width=5,
    )

    assert isinstance(result, SizeResolution)
    assert result.size_spec == COL_SIZE_MAP
    assert result.field_name == "status"
    assert result.derived_column is not None


def test_resolve_color_field_returns_field_name_for_categorical_column() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
            "category": ["villes", "routes"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points)],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    result = carte._resolve_color_field(points, "category", missing_color="gray")

    assert isinstance(result, ColorResolution)
    assert result.field_name == "category"
    assert result.derived_column is None


def test_resolve_color_field_keeps_field_name_none_for_fixed_color() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points)],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    result = carte._resolve_color_field(points, "navy", missing_color="gray")

    assert isinstance(result, ColorResolution)
    assert result.color_spec == "navy"
    assert result.derived_column is None
    assert result.field_name is None


def test_left_panel_width_is_configured_via_map_config() -> None:
    points = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points)],
        map_config=MapConfig(title="Test", height=300, left_panel_width=280),
        data_config=GlobalDataConfig(),
    )

    assert carte.map_config.left_panel_width == 280


def test_filter_options_respect_explicit_order_from_global_data_config() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B", "C"],
            "category": ["routes", "villes", "autres"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86), Point(2.38, 48.87)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
            style=StyleConfig(color="category"),
        )
    ]

    data_config = GlobalDataConfig(
        global_filters=["category"],
        global_filters_order={"category": ["villes", "routes"]},
    )
    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=data_config
    )

    widget = carte.widgets_filters["global__category"]
    assert widget.options == ["villes", "routes", "autres"]


def test_specific_filter_options_respect_explicit_order_from_global_data_config() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B", "C"],
            "category": ["routes", "villes", "autres"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86), Point(2.38, 48.87)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
            style=StyleConfig(color="category"),
        )
    ]

    data_config = GlobalDataConfig(
        specific_filters={"Points": ["category"]},
        specific_filters_order={"Points": {"category": ["villes", "routes"]}},
    )
    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=data_config
    )

    widget = carte.widgets_filters["Points__category"]
    assert widget.options == ["villes", "routes", "autres"]


def test_specific_select_filter_builds_dropdown_with_all_option() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B", "C"],
            "category": ["routes", "villes", "autres"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86), Point(2.38, 48.87)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
        )
    ]

    data_config = GlobalDataConfig(
        specific_select_filters={"Points": ["name"]},
    )
    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=data_config
    )

    widget = carte.widgets_filters["Points__name__select"]
    assert isinstance(widget, Select)
    assert widget.value == "__all__"
    options = widget.options
    assert isinstance(options, list)
    assert options[0] == ("__all__", "Tous")


def test_global_select_filter_builds_dropdown_and_aggregates_values() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B"],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    lines = gpd.GeoDataFrame(
        {
            "name": ["L1", "L2"],
            "line_no": ["2", "1"],
        },
        geometry=[
            LineString([(2.33, 48.84), (2.36, 48.86)]),
            LineString([(2.34, 48.85), (2.32, 48.83)]),
        ],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(name="Points", data=points),
        LayerConfig(name="Tronçons", data=lines),
    ]

    data_config = GlobalDataConfig(
        global_select_filters=["line_no"],
        global_select_filters_order={"line_no": ["1", "2"]},
    )
    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=data_config
    )

    widget = carte.widgets_filters["global__line_no__select"]
    assert isinstance(widget, Select)
    assert widget.value == "__all__"
    assert widget.options == [("__all__", "Tous"), "1", "2"]


def test_duplicate_layer_names_raise_value_error() -> None:
    points = gpd.GeoDataFrame(
        {"name": ["A", "B"]},
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(name="Points", data=points),
        LayerConfig(name="Points", data=points),
    ]

    with pytest.raises(ValueError, match="Noms de couches en double"):
        CarteDynMulti(
            layers,
            map_config=MapConfig(title="Test", height=300),
            data_config=GlobalDataConfig(),
        )


def test_indicator_overlay_renders_initial_totals() -> None:
    points = gpd.GeoDataFrame(
        {
            "name": ["A", "B", "C"],
            "value": [1, 2, 3],
        },
        geometry=[Point(2.35, 48.85), Point(2.37, 48.86), Point(2.38, 48.87)],
        crs="EPSG:4326",
    )
    layers = [
        LayerConfig(
            name="Points",
            data=points,
            indicators=[
                LayerIndicator(label="Nombre d'objets", kind="count"),
                LayerIndicator(label="Somme de value", kind="sum", column="value"),
            ],
        )
    ]

    carte = CarteDynMulti(
        layers, map_config=MapConfig(title="Test", height=300), data_config=GlobalDataConfig()
    )

    assert carte.indicators_widget is not None
    assert "Indicateurs" in carte.indicators_widget.text
    assert "Nombre d'objets" in carte.indicators_widget.text
    assert ">3</b> / 3" in carte.indicators_widget.text
    assert ">6</b> / 6" in carte.indicators_widget.text


def test_line_string_and_multi_line_string_can_share_a_layer() -> None:
    lines = gpd.GeoDataFrame(
        {"name": ["A", "B"]},
        geometry=[
            LineString([(2.33, 48.84), (2.36, 48.86)]),
            MultiLineString([[(2.34, 48.85), (2.32, 48.83)]]),
        ],
        crs="EPSG:4326",
    )

    carte = CarteDynMulti(
        [LayerConfig(name="Lignes", data=lines)],
        map_config=MapConfig(title="Test", height=300),
        data_config=GlobalDataConfig(),
    )

    layer = carte.layers["Lignes"]
    assert layer.raw_data.geometry.geom_type.tolist() == ["LineString", "MultiLineString"]
    assert len(layer.src_geo.data["xs"]) == 2
    assert len(layer.src_geo.data["ys"]) == 2


def test_point_and_line_mixture_raise_value_error() -> None:
    mixed = gpd.GeoDataFrame(
        {"name": ["A", "B"]},
        geometry=[Point(2.35, 48.85), LineString([(2.33, 48.84), (2.36, 48.86)])],
        crs="EPSG:4326",
    )
    layer = LayerConfig(name="Mixed", data=mixed)

    with pytest.raises(ValueError, match="mélange des points et des lignes"):
        CarteDynMulti(
            [layer],
            map_config=MapConfig(title="Test", height=300),
            data_config=GlobalDataConfig(),
        )


def test_unsupported_geometry_type_raise_value_error() -> None:
    polygons = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Polygon([(2.33, 48.84), (2.36, 48.84), (2.35, 48.86)])],
        crs="EPSG:4326",
    )

    with pytest.raises(ValueError, match="non prises en charge"):
        CarteDynMulti(
            [LayerConfig(name="Polygones", data=polygons)],
            map_config=MapConfig(title="Test", height=300),
            data_config=GlobalDataConfig(),
        )


def test_save_can_embed_bokeh_resources_inline(tmp_path) -> None:
    points = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points)],
        map_config=MapConfig(title="Test", height=300),
    )

    cdn_path = tmp_path / "cdn.html"
    inline_path = tmp_path / "inline.html"
    inline_string_path = tmp_path / "inline-string.html"
    carte.save(cdn_path)
    carte.save(inline_path, resources=INLINE)
    carte.save(inline_string_path, resources="inline")

    assert "cdn.bokeh.org" in cdn_path.read_text(encoding="utf-8")
    assert "cdn.bokeh.org" not in inline_path.read_text(encoding="utf-8")
    assert "cdn.bokeh.org" not in inline_string_path.read_text(encoding="utf-8")


def test_attribution_accepts_mailto_href() -> None:
    points = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti(
        [LayerConfig(name="Points", data=points)],
        map_config=MapConfig(title="Test attribution"),
        attribution_config=AttributionConfig(text="myname", href="mailto:user@example.com"),
    )

    assert carte.attribution_config.href == "mailto:user@example.com"
    assert 'href="mailto:user@example.com"' in carte._build_attribution_widget().text
    assert ">myname</a>" in carte._build_attribution_widget().text


def test_attribution_uses_personal_toml_config(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "cartes_multicouches"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[attribution]\ntext = "Mon nom"\nhref = "https://example.com"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(tmp_path))

    points = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )
    carte = CarteDynMulti([LayerConfig(name="Points", data=points)])

    assert carte.attribution_config == AttributionConfig(
        text="Mon nom",
        href="https://example.com",
    )


def test_attribution_uses_defaults_without_personal_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    points = gpd.GeoDataFrame(
        {"name": ["A"]},
        geometry=[Point(2.35, 48.85)],
        crs="EPSG:4326",
    )

    with pytest.warns(UserWarning, match=r"CartoDB tiles now require an API key"):
        carte = CarteDynMulti([LayerConfig(name="Points", data=points)])

    assert carte.attribution_config == AttributionConfig()


def test_load_tile_provider_key_uses_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(dynamic_module._TILE_PROVIDER_API_KEY_ENV_VAR, "env-secret")

    assert dynamic_module._load_tile_provider_key() == "env-secret"
    assert dynamic_module._load_tile_provider_key("override-secret") == "override-secret"


def test_load_pyproject_config_ignores_cwd_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.cartes_multicouches]\nattribution = { text = "cwd" }\n',
        encoding="utf-8",
    )

    result = _load_pyproject_config()

    assert result != {"attribution": {"text": "cwd"}}


def test_load_pyproject_config_can_read_explicit_start_path(tmp_path) -> None:
    config_dir = tmp_path / "project"
    config_dir.mkdir()
    (config_dir / "pyproject.toml").write_text(
        '[tool.cartes_multicouches]\nattribution = { text = "local" }\n',
        encoding="utf-8",
    )

    result = _load_pyproject_config(start=config_dir)

    assert result == {"attribution": {"text": "local"}}
