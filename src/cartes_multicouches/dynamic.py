import os
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd
import xyzservices.providers as xyz
from bokeh import io, models
from bokeh.layouts import row
from bokeh.plotting import figure
from bokeh.resources import CDN, Resources, ResourcesMode
from xyzservices import TileProvider

from ._config import load_personal_config
from ._mixins import LayerBuilderMixin, UIBuilderMixin
from ._models import (
    COL_ANN_X,
    COL_ANN_Y,
    COL_INDEX_STR,
    AnnotationConfig,
    AttributionConfig,
    ColorMapping,
    GlobalDataConfig,
    InteractionConfig,
    LayerConfig,
    LayerIndicator,
    LayerState,
    LegendConfig,
    LegendEntry,
    MapConfig,
    SizeMapping,
    StyleConfig,
)

__all__ = [
    "COL_ANN_X",
    "COL_ANN_Y",
    "AnnotationConfig",
    "AttributionConfig",
    "CarteDynMulti",
    "ColorMapping",
    "GlobalDataConfig",
    "InteractionConfig",
    "LayerConfig",
    "LayerIndicator",
    "LegendConfig",
    "LegendEntry",
    "MapConfig",
    "SizeMapping",
    "StyleConfig",
]


_ESRI_GRAY_BASE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
_ESRI_GRAY_REFERENCE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
_ESRI_GRAY_ATTRIBUTION = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
_ESRI_GRAY_MAX_ZOOM = 16
_TILE_PROVIDER_API_KEY_ENV_VAR = "CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY"
_TILE_URL_PLACEHOLDER_PATTERN = re.compile(r"{([^{}]+)}")
_TILE_URL_NON_SECRET_PLACEHOLDERS = {
    "bbox-epsg-3857",
    "ext",
    "height",
    "q",
    "quadkey",
    "r",
    "s",
    "scale",
    "tilecol",
    "tilematrix",
    "tilerow",
    "time",
    "variant",
    "width",
    "x",
    "y",
    "z",
}


def _load_attribution_config() -> AttributionConfig:
    attribution = load_personal_config().get("attribution", {})
    if not isinstance(attribution, dict):
        return AttributionConfig()

    valid_fields = {"text", "href"}
    values = {field: value for field, value in attribution.items() if field in valid_fields}
    return AttributionConfig(**values)


def _load_tile_provider_key(override: str | None = None) -> str | None:
    if override:
        return override

    env_key = os.getenv(_TILE_PROVIDER_API_KEY_ENV_VAR)
    if env_key:
        return env_key

    tile_cfg = load_personal_config().get("tile_provider", {})
    if not isinstance(tile_cfg, dict):
        return None
    key = tile_cfg.get("api_key")
    return key if isinstance(key, str) and key else None


class CarteDynMulti(LayerBuilderMixin, UIBuilderMixin):
    """Générateur de carte interactive Bokeh multi-couches."""

    def _multiselect_size(self, option_count: int) -> int:
        configured = max(1, self.data_config.multi_select_size)
        return max(1, min(configured, option_count))

    def __init__(
        self,
        layers_config: list[LayerConfig],
        map_config: MapConfig | None = None,
        data_config: GlobalDataConfig | None = None,
        legend_config: LegendConfig | None = None,
        attribution_config: AttributionConfig | None = None,
    ) -> None:
        layer_names = [cfg.name for cfg in layers_config]
        duplicates = sorted([name for name, count in Counter(layer_names).items() if count > 1])
        if duplicates:
            raise ValueError(f"Noms de couches en double : {duplicates}")

        self.map_config = map_config or MapConfig()
        self.data_config = data_config or GlobalDataConfig()
        self.legend_config = legend_config
        self.attribution_config = attribution_config or _load_attribution_config()
        self.layers: dict[str, LayerState] = {}
        self.widgets_filters: dict[str, models.MultiSelect | models.Select] = {}
        self.widgets_filter_meta: dict[str, dict[str, str]] = {}
        self._tap_renderers: list[models.DataRenderer] = []

        self.fig = self._create_figure()

        for cfg in layers_config:
            self._register_layer(cfg)

        self._register_tap_tool()

        self._init_filter_widgets(layers_config)
        (
            self.layer_toggle_widget,
            self.annotation_toggle_widget,
            default_active_layers,
            default_active_annotations,
        ) = self._create_layer_toggle_widgets()
        self.tables_widget = self._build_tables_tabs()
        self.legend_widget = self._build_legend_widget()
        self.indicators_widget = self._build_indicators_widget()
        self.cb_filter = self._create_central_filter_callback()
        for widget in self.widgets_filters.values():
            widget.js_on_change("value", self.cb_filter)

        self._init_layout(default_active_layers, default_active_annotations)

    def _resolve_tile_sources(self) -> list[str | models.WMTSTileSource | TileProvider]:
        provider_name = self.map_config.tile_provider
        api_key = _load_tile_provider_key(self.map_config.tile_provider_api_key)

        cartodb_provider: TileProvider | None = None
        if provider_name.upper().startswith("CARTODB") and api_key:
            try:
                cartodb_provider = cast(Any, xyz).query_name(provider_name)
            except ValueError:
                cartodb_provider = None

        if cartodb_provider is not None and api_key is not None:
            tile_source: str | models.WMTSTileSource | TileProvider = self._provider_with_api_key(
                cartodb_provider, api_key
            )
            return [tile_source]

        if provider_name.upper() == "ESRIGRAYCANVAS":
            return [
                models.WMTSTileSource(
                    url=_ESRI_GRAY_BASE_URL,
                    attribution=_ESRI_GRAY_ATTRIBUTION,
                    max_zoom=_ESRI_GRAY_MAX_ZOOM,
                ),
                models.WMTSTileSource(
                    url=_ESRI_GRAY_REFERENCE_URL,
                    attribution=_ESRI_GRAY_ATTRIBUTION,
                    max_zoom=_ESRI_GRAY_MAX_ZOOM,
                ),
            ]

        return [provider_name]

    def _provider_with_api_key(self, provider: TileProvider, api_key: str) -> TileProvider:
        placeholder_keys = {
            key
            for key in _TILE_URL_PLACEHOLDER_PATTERN.findall(provider.url)
            if key.lower() not in _TILE_URL_NON_SECRET_PLACEHOLDERS
        }
        metadata_keys = {
            key
            for key, value in provider.items()
            if isinstance(value, str) and "insert your api key" in value.lower()
        }

        # Définit la clé API pour tous les placeholders "secret" détectés,
        # puis ajoute quelques alias fréquents pour compatibilité inter-versions.
        key_names = placeholder_keys | metadata_keys | {"apikey", "key", "api_key"}
        return provider(**{key_name: api_key for key_name in key_names})

    def _create_figure(self) -> figure:
        fig = figure(
            title=self.map_config.title,
            height=self.map_config.height,
            width=self.map_config.width,
            sizing_mode="stretch_both" if self.map_config.width is None else "fixed",
            x_axis_type="mercator",
            y_axis_type="mercator",
            match_aspect=True,
            toolbar_location=self.map_config.toolbar_location,
            tools=["pan", "wheel_zoom", "reset", "save"],
            active_scroll="wheel_zoom",
        )
        for tile_source in self._resolve_tile_sources():
            if isinstance(tile_source, TileProvider):
                fig.add_tile(tile_source, retina=True)
            else:
                renderer = fig.add_tile(tile_source)
                if (
                    isinstance(tile_source, models.WMTSTileSource)
                    and tile_source.url == _ESRI_GRAY_REFERENCE_URL
                ):
                    renderer.level = "annotation"
        fig.toolbar.autohide = True
        fig.axis.visible = False
        fig.grid.visible = False
        return fig

    def _order_filter_values(
        self,
        values: set[str],
        explicit_order: list[str] | None,
    ) -> list[str]:
        ordered_values: list[str] = []
        if explicit_order is not None:
            ordered_values.extend([value for value in explicit_order if value in values])
            ordered_values.extend(sorted(values - set(ordered_values)))
        else:
            ordered_values = sorted(values)
        return ordered_values

    def _register_filter_widget(
        self,
        key: str,
        widget: models.MultiSelect | models.Select,
        kind: Literal["multi", "single"],
        none_value: str = "",
        layer_name: str | None = None,
        column_name: str | None = None,
    ) -> None:
        self.widgets_filters[key] = widget
        self.widgets_filter_meta[key] = {
            "kind": kind,
            "none_value": none_value,
            "layer": layer_name or "",
            "column": column_name or "",
        }

    def _init_filter_widgets(self, layers_config: list[LayerConfig]) -> None:
        for col in self.data_config.global_filters:
            values = set()
            for cfg in layers_config:
                if col in cfg.data.columns:
                    values.update(cfg.data[col].dropna().astype(str).unique())
            if values:
                ordered_values = self._order_filter_values(
                    values,
                    self.data_config.global_filters_order.get(col),
                )
                self._register_filter_widget(
                    f"global__{col}",
                    models.MultiSelect(
                        title=f"Global : {col}",
                        options=cast(list[str | tuple[str, str]], ordered_values),
                        size=self._multiselect_size(len(ordered_values)),
                        sizing_mode="stretch_width",
                    ),
                    kind="multi",
                    column_name=col,
                )

        for col in self.data_config.global_select_filters:
            values = set()
            for cfg in layers_config:
                if col in cfg.data.columns:
                    values.update(cfg.data[col].dropna().astype(str).unique())
            if values:
                ordered_values = self._order_filter_values(
                    values,
                    self.data_config.global_select_filters_order.get(col),
                )
                self._register_filter_widget(
                    f"global__{col}__select",
                    models.Select(
                        title=f"Global : {col}",
                        options=cast(
                            list[str | tuple[str, str]],
                            [("__all__", "Tous")] + ordered_values,
                        ),
                        value="__all__",
                        sizing_mode="stretch_width",
                    ),
                    kind="single",
                    none_value="__all__",
                    column_name=col,
                )

        for layer_name, cols in self.data_config.specific_filters.items():
            layer = next((cfg for cfg in layers_config if cfg.name == layer_name), None)
            if layer is None:
                continue
            layer_order = self.data_config.specific_filters_order.get(layer_name, {})
            for col in cols:
                if col in layer.data.columns:
                    values = set(layer.data[col].dropna().astype(str).unique().tolist())
                    ordered_values = self._order_filter_values(values, layer_order.get(col))
                    self._register_filter_widget(
                        f"{layer_name}__{col}",
                        models.MultiSelect(
                            title=f"{layer_name} : {col}",
                            options=cast(list[str | tuple[str, str]], ordered_values),
                            size=self._multiselect_size(len(ordered_values)),
                            sizing_mode="stretch_width",
                        ),
                        kind="multi",
                        layer_name=layer_name,
                        column_name=col,
                    )

        for layer_name, cols in self.data_config.specific_select_filters.items():
            layer = next((cfg for cfg in layers_config if cfg.name == layer_name), None)
            if layer is None:
                continue
            layer_order = self.data_config.specific_select_filters_order.get(layer_name, {})
            for col in cols:
                if col in layer.data.columns:
                    values = set(layer.data[col].dropna().astype(str).unique().tolist())
                    ordered_values = self._order_filter_values(values, layer_order.get(col))
                    self._register_filter_widget(
                        f"{layer_name}__{col}__select",
                        models.Select(
                            title=f"{layer_name} : {col}",
                            options=cast(
                                list[str | tuple[str, str]],
                                [("__all__", "Tous")] + ordered_values,
                            ),
                            value="__all__",
                            sizing_mode="stretch_width",
                        ),
                        kind="single",
                        none_value="__all__",
                        layer_name=layer_name,
                        column_name=col,
                    )

    def _create_central_filter_callback(self) -> models.CustomJS:
        layers_js = {
            name: {
                "src_geo": layer.src_geo,
                "filtre": layer.filtre,
                "indicators": layer.indicator_specs,
                "boolean_columns": [
                    column
                    for column in layer.raw_data.columns
                    if pd.api.types.is_bool_dtype(layer.raw_data[column])
                ],
            }
            for name, layer in self.layers.items()
        }
        return models.CustomJS.from_file(
            self._js_path("filter_callback.js"),
            layers=layers_js,
            widgets=self.widgets_filters,
            widgetMeta=self.widgets_filter_meta,
            indicatorDiv=self.indicators_widget,
            colIndexStr=COL_INDEX_STR,
        )

    def _create_layer_toggle_widgets(
        self,
    ) -> tuple[models.CheckboxGroup, models.CheckboxGroup | None, list[int], list[int]]:
        labels = list(self.layers.keys())
        active_layers = [
            i for i, name in enumerate(labels) if self.layers[name].cfg.visible_by_default
        ]

        annotation_labels = [
            name for name, layer in self.layers.items() if layer.annotation_renderer is not None
        ]
        active_annotations = [
            i
            for i, name in enumerate(annotation_labels)
            if self.layers[name].cfg.visible_by_default
        ]

        geometry_renderers = {name: layer.renderer for name, layer in self.layers.items()}
        annotation_renderers = {
            name: layer.annotation_renderer
            for name, layer in self.layers.items()
            if layer.annotation_renderer is not None
        }

        layer_widget = models.CheckboxGroup(
            labels=labels,
            active=active_layers,
            sizing_mode="stretch_width",
        )

        annotation_widget: models.CheckboxGroup | None = None
        if annotation_labels:
            annotation_widget = models.CheckboxGroup(
                labels=annotation_labels,
                active=active_annotations,
                sizing_mode="stretch_width",
            )

        layer_widget.js_on_change(
            "active",
            models.CustomJS.from_file(
                self._js_path("layer_toggle.js"),
                geometryRenderers=geometry_renderers,
                annotationRenderers=annotation_renderers,
                layerLabels=labels,
                annotationWidget=annotation_widget,
                annotationLabels=annotation_labels,
            ),
        )
        if annotation_widget is not None:
            annotation_widget.js_on_change(
                "active",
                models.CustomJS.from_file(
                    self._js_path("annotation_toggle.js"),
                    layerWidget=layer_widget,
                    layerLabels=labels,
                    annotationRenderers=annotation_renderers,
                    annotationLabels=annotation_labels,
                    annotationWidget=annotation_widget,
                ),
            )

        return layer_widget, annotation_widget, active_layers, active_annotations

    def _init_layout(
        self,
        default_active_layers: list[int],
        default_active_annotations: list[int],
    ) -> None:
        left_panel_width = self.map_config.left_panel_width or self._compute_left_panel_width()
        left_panel = self._build_left_panel(
            left_panel_width,
            default_active_layers,
            default_active_annotations,
        )
        map_stack = self._build_map_stack()

        main_panel = row(map_stack, self.tables_widget, sizing_mode="stretch_both")
        self.layout_widget = row(left_panel, main_panel, sizing_mode="stretch_both")

    def show(self) -> None:
        io.show(self.layout_widget)

    def save(
        self,
        filepath: str | Path,
        zip: bool = False,
        resources: Resources | ResourcesMode = CDN,
    ) -> None:
        path = Path(filepath)
        bokeh_resources = Resources(mode=resources) if isinstance(resources, str) else resources
        io.save(
            self.layout_widget,
            str(path),
            resources=bokeh_resources,
            title=self.map_config.title,
        )
        if zip:
            with zipfile.ZipFile(path.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(path, path.name)
