import math
import re
import warnings
from collections.abc import Sequence
from typing import Any, Protocol, cast

import geopandas as gpd
import pandas as pd
from bokeh import __version__ as bokeh_version
from bokeh import models
from bokeh.core.properties import Color
from bokeh.layouts import column, row
from bokeh.palettes import Category10, Category20
from bokeh.plotting import figure
from packaging.version import Version

from ._geometry import _extract_line_coords, _line_label_point, _line_start_end
from ._models import (
    COL_ANN_X,
    COL_ANN_Y,
    COL_COLOR_MAP,
    COL_INDEX_STR,
    COL_SIZE_MAP,
    COL_X,
    COL_X_END,
    COL_X_START,
    COL_XS,
    COL_Y,
    COL_Y_END,
    COL_Y_START,
    COL_YS,
    FILTER_HELP_FONT_SIZE_PX,
    INTERNAL_COLUMNS,
    LAYER_VISIBILITY_BUTTON_WIDTH_PX,
    LAYER_VISIBILITY_PANEL_GAP_PX,
    LAYER_VISIBILITY_PANEL_WIDTH_PX,
    LEFT_PANEL_CHROME_PADDING_PX,
    LEFT_PANEL_MAX_WIDTH_PX,
    LEFT_PANEL_MIN_WIDTH_PX,
    LEFT_PANEL_PX_PER_CHAR,
    LEGEND_BUTTON_WIDTH_PX,
    OVERLAY_BOX_GAP_PX,
    OVERLAY_BUTTON_HEIGHT_PX,
    OVERLAY_EDGE_OFFSET_PX,
    OVERLAY_TOP_WITH_TOOLBAR_OFFSET_PX,
    SELECT_BTN_ALL_WIDTH_PX,
    SELECT_BTN_FONT_SIZE_PX,
    SELECT_BTN_HEIGHT_PX,
    SELECT_BTN_LINE_HEIGHT_PX,
    SELECT_BTN_NONE_WIDTH_PX,
    SELECT_BTN_SPACING_PX,
    SUPPORTED_GEOMETRY_TYPES,
    TABLES_BUTTON_SPACING_PX,
    TABLES_BUTTON_WIDTH_PX,
    AnnotationConfig,
    AttributionConfig,
    ColorMapping,
    ColorResolution,
    GlobalDataConfig,
    LayerColumns,
    LayerConfig,
    LayerIndicator,
    LayerState,
    LegendConfig,
    LegendEntry,
    MapConfig,
    SizeMapping,
    SizeResolution,
    StyleConfig,
)

_COLOR_VALIDATOR = Color()
_BOKEH_SUPPORTS_IGNORE_VIEWPORT = Version(bokeh_version) >= Version("3.10")


class _CarteDynContext(Protocol):
    fig: figure
    layers: dict[str, LayerState]
    _tap_renderers: list[models.DataRenderer]
    widgets_filters: dict[str, models.MultiSelect | models.Select]
    widgets_filter_meta: dict[str, dict[str, str]]
    layer_toggle_widget: models.Widget
    annotation_toggle_widget: models.Widget | None
    attribution_config: AttributionConfig
    tables_widget: models.Tabs
    legend_widget: models.Div | None
    indicators_widget: models.Div | None
    map_config: MapConfig
    legend_config: LegendConfig | None
    data_config: GlobalDataConfig
    layer_visibility_overlay: models.Column | None
    toggle_layers_button: models.Button | None
    toggle_tables_button: models.Button | None
    toggle_legend_button: models.Button | None
    reset_button: models.Button | None
    cb_filter: Any

    def _build_indicator_specs(
        self,
        indicators: Sequence[LayerIndicator] | None,
        layer_name: str,
        raw_data: gpd.GeoDataFrame,
    ) -> list[dict[str, Any]]: ...

    def _default_display_columns(self, gdf: gpd.GeoDataFrame) -> list[str]: ...


class LayerBuilderMixin(_CarteDynContext):
    def _resolve_color_field(
        self,
        gdf: gpd.GeoDataFrame,
        color: str | ColorMapping | None,
        missing_color: str,
    ) -> ColorResolution:
        if color is None:
            derived = pd.Series(missing_color, index=gdf.index)
            return ColorResolution(
                color_spec=COL_COLOR_MAP, derived_column=derived, field_name=None
            )

        if isinstance(color, ColorMapping):
            derived = gdf[color.column].astype(str).map(color.mapping).fillna(missing_color)
            return ColorResolution(
                color_spec=COL_COLOR_MAP,
                derived_column=derived,
                field_name=color.column,
            )

        if isinstance(color, str) and color in gdf.columns:
            values = gdf[color].dropna().astype(str).unique().tolist()
            valid_flags = [_COLOR_VALIDATOR.is_valid(value) for value in values]
            n_valid = sum(valid_flags)
            if values and n_valid == len(values):
                return ColorResolution(
                    color_spec={"field": color},
                    derived_column=None,
                    field_name=color,
                )
            if n_valid > 0:
                invalid = [v for v, ok in zip(values, valid_flags, strict=False) if not ok]
                warnings.warn(
                    f"Colonne '{color}' : {len(invalid)} valeur(s) non reconnues comme "
                    f"couleur ({invalid[:5]}...), traitement en mode catégoriel appliqué "
                    "à toute la colonne.",
                    stacklevel=2,
                )
            factors = sorted(values)
            if len(factors) <= 1:
                palette = Category10[3]
            elif len(factors) <= 10:
                palette = Category10[max(3, len(factors))]
            elif len(factors) <= 20:
                palette = Category20[len(factors)]
            else:
                palette = Category20[20]

            return ColorResolution(
                color_spec={
                    "field": color,
                    "transform": models.CategoricalColorMapper(factors=factors, palette=palette),
                },
                derived_column=None,
                field_name=color,
            )

        return ColorResolution(color_spec=color, derived_column=None, field_name=None)

    def _resolve_size_field(
        self,
        gdf: gpd.GeoDataFrame,
        size_or_width: float | str | SizeMapping,
        missing_size_or_width: float,
    ) -> SizeResolution:
        if isinstance(size_or_width, SizeMapping):
            mapped = gdf[size_or_width.column].astype(str).map(size_or_width.mapping)
            derived = pd.to_numeric(mapped, errors="coerce").fillna(missing_size_or_width)
            return SizeResolution(
                size_spec=COL_SIZE_MAP,
                derived_column=derived,
                field_name=size_or_width.column,
            )

        if isinstance(size_or_width, str) and size_or_width in gdf.columns:
            return SizeResolution(
                size_spec=size_or_width,
                derived_column=None,
                field_name=size_or_width,
            )

        return SizeResolution(size_spec=size_or_width, derived_column=None, field_name=None)

    def _default_display_columns(self, gdf: gpd.GeoDataFrame) -> list[str]:
        return [c for c in gdf.columns if c != "geometry" and c not in INTERNAL_COLUMNS]

    def _build_indicator_specs(
        self,
        indicators: Sequence[LayerIndicator] | None,
        layer_name: str,
        raw_data: gpd.GeoDataFrame,
    ) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for indicator in indicators or []:
            if indicator.kind == "count":
                total = float(len(raw_data))
            else:
                if indicator.column is None:
                    raise ValueError(
                        f"L'indicateur '{indicator.label}' de la couche '{layer_name}' "
                        "doit définir une colonne pour une somme."
                    )
                if indicator.column not in raw_data.columns:
                    raise ValueError(
                        f"La colonne '{indicator.column}' est absente de la couche '{layer_name}' "
                        f"pour l'indicateur '{indicator.label}'."
                    )
                total = float(
                    pd.to_numeric(raw_data[indicator.column], errors="coerce").fillna(0).sum()
                )

            specs.append(
                {
                    "label": indicator.label,
                    "kind": indicator.kind,
                    "column": indicator.column,
                    "total": total,
                }
            )
        return specs

    def _build_layer_columns(self, cfg: LayerConfig) -> LayerColumns:
        gdf = cfg.data.copy()
        if gdf.crs is not None and gdf.crs.to_string() != "EPSG:3857":
            gdf = gdf.to_crs(epsg=3857)

        gdf = gdf.reset_index(drop=True)
        gdf[COL_INDEX_STR] = gdf.index.astype(str)

        color_resolution = self._resolve_color_field(gdf, cfg.style.color, cfg.style.missing_color)
        color_field = color_resolution.color_spec
        derived_color = color_resolution.derived_column
        size_resolution = self._resolve_size_field(
            gdf,
            cfg.style.size_or_width,
            cfg.style.missing_size_or_width,
        )
        size_field = size_resolution.size_spec
        derived_size = size_resolution.derived_column

        geometry_types = set(gdf.geometry.geom_type.dropna().unique())
        unsupported_types = geometry_types - SUPPORTED_GEOMETRY_TYPES
        if unsupported_types:
            raise ValueError(
                f"Géométries '{sorted(unsupported_types)}' non prises en charge pour la couche "
                f"'{cfg.name}' (types acceptés : {sorted(SUPPORTED_GEOMETRY_TYPES)})."
            )

        geometry_families = {
            "point" if geometry_type == "Point" else "line" for geometry_type in geometry_types
        }
        if len(geometry_families) > 1:
            raise ValueError(
                f"La couche '{cfg.name}' mélange des points et des lignes : "
                f"{sorted(geometry_types)}"
            )

        if not geometry_types or geometry_families == {"point"}:
            geometry_type = "Point"
        elif geometry_types == {"MultiLineString"}:
            geometry_type = "MultiLineString"
        else:
            geometry_type = "LineString"

        source_data = gdf.drop(columns="geometry").copy()
        if derived_color is not None:
            source_data[COL_COLOR_MAP] = derived_color
        if derived_size is not None:
            source_data[COL_SIZE_MAP] = derived_size

        if geometry_type == "Point":
            source_data[COL_X] = gdf.geometry.x
            source_data[COL_Y] = gdf.geometry.y
            source_data[COL_ANN_X] = source_data[COL_X]
            source_data[COL_ANN_Y] = source_data[COL_Y]
        else:
            coords = gdf.geometry.apply(_extract_line_coords)
            source_data[COL_XS] = coords.apply(lambda c: c[0])
            source_data[COL_YS] = coords.apply(lambda c: c[1])
            label_points = gdf.geometry.apply(_line_label_point)
            source_data[COL_ANN_X] = label_points.apply(
                lambda p: p[0] if p is not None else float("nan")
            )
            source_data[COL_ANN_Y] = label_points.apply(
                lambda p: p[1] if p is not None else float("nan")
            )
            if cfg.show_endpoints:
                endpoints = gdf.geometry.apply(_line_start_end)
                source_data[COL_X_START] = endpoints.apply(
                    lambda e: e[0] if e is not None else float("nan")
                )
                source_data[COL_Y_START] = endpoints.apply(
                    lambda e: e[1] if e is not None else float("nan")
                )
                source_data[COL_X_END] = endpoints.apply(
                    lambda e: e[2] if e is not None else float("nan")
                )
                source_data[COL_Y_END] = endpoints.apply(
                    lambda e: e[3] if e is not None else float("nan")
                )

        if cfg.tooltips is not None:
            tooltips = cfg.tooltips
        else:
            columns = cfg.columns_to_show or self._default_display_columns(gdf)
            tooltips = [(col, f"@{{{col}}}") for col in columns[:6]]

        return LayerColumns(
            gdf=gdf,
            source_data=source_data,
            geometry_type=geometry_type,
            color_field=color_field,
            size_field=size_field,
            tooltips=tooltips,
        )

    def _register_layer(self, cfg: LayerConfig) -> None:
        cols = self._build_layer_columns(cfg)

        src_geo = models.ColumnDataSource(cols.source_data)
        filtre = models.IndexFilter(indices=list(range(len(cols.gdf))))
        view = models.CDSView(filter=filtre)
        indicator_specs = self._build_indicator_specs(cfg.indicators, cfg.name, cols.gdf)

        renderer = self._build_renderer(
            src_geo,
            view,
            cfg.name,
            cfg.visible_by_default,
            cols.geometry_type,
            cols.color_field,
            cols.size_field,
            cfg.style,
        )
        annotation_renderer = self._build_annotation_renderer(
            src_geo, view, cfg.annotation, cfg.name, cfg.visible_by_default
        )

        endpoint_renderers = None
        if cfg.show_endpoints and cols.geometry_type in {"LineString", "MultiLineString"}:
            endpoint_renderers = self._build_endpoint_renderers(
                src_geo, view, cfg.name, cfg.style.endpoint_size, cfg.style.endpoint_color
            )

        if cfg.interaction.hover:
            hover = models.HoverTool(
                renderers=[renderer],
                tooltips=cols.tooltips if cfg.interaction.tooltips else [],
                mode=cfg.style.hover_mode,
            )
            self.fig.add_tools(hover)

        if cfg.interaction.tap:
            self._tap_renderers.append(renderer)

        self.layers[cfg.name] = LayerState(
            cfg=cfg,
            raw_data=cols.gdf,
            indicator_specs=indicator_specs,
            src_geo=src_geo,
            filtre=filtre,
            view=view,
            renderer=renderer,
            annotation_renderer=annotation_renderer,
            endpoint_renderers=endpoint_renderers,
        )

    def _register_tap_tool(self) -> None:
        if self._tap_renderers:
            self.fig.add_tools(models.TapTool(renderers=self._tap_renderers))

    def _build_renderer(
        self,
        src_geo: models.ColumnDataSource,
        view: models.CDSView,
        layer_name: str,
        visible_by_default: bool,
        geometry_type: str,
        color: Any,
        size: float | str,
        style: StyleConfig,
    ) -> models.GlyphRenderer:
        render_args = {
            "source": src_geo,
            "view": view,
            "name": layer_name,
            "visible": visible_by_default,
            "nonselection_alpha": style.nonselection_alpha,
        }

        if geometry_type == "Point":
            return self.fig.scatter(
                x=COL_X,
                y=COL_Y,
                size=size,
                color=color,
                alpha=style.alpha,
                marker=style.marker,
                **render_args,
            )

        return self.fig.multi_line(
            xs=COL_XS,
            ys=COL_YS,
            line_color=color,
            line_width=size,
            line_alpha=style.alpha,
            line_dash=style.line_dash,
            **render_args,
        )

    def _build_endpoint_renderers(
        self,
        src_geo: models.ColumnDataSource,
        view: models.CDSView,
        layer_name: str,
        endpoint_size: float,
        endpoint_color: Any,
    ) -> tuple[models.GlyphRenderer, models.GlyphRenderer]:
        common = {
            "source": src_geo,
            "view": view,
            "marker": "circle",
            "size": endpoint_size,
            "color": endpoint_color,
            "visible": False,
            "name": f"{layer_name}__endpoints",
        }
        renderer_start = self.fig.scatter(x=COL_X_START, y=COL_Y_START, **common)
        renderer_end = self.fig.scatter(x=COL_X_END, y=COL_Y_END, **common)
        return renderer_start, renderer_end

    def _build_annotation_renderer(
        self,
        src_geo: models.ColumnDataSource,
        view: models.CDSView,
        annotation: AnnotationConfig | None,
        layer_name: str,
        visible_by_default: bool,
    ) -> models.GlyphRenderer | None:
        if annotation is None:
            return None

        available_columns = set(src_geo.data.keys())
        required = [annotation.x, annotation.y, annotation.text]
        for offset in (annotation.x_offset, annotation.y_offset):
            if isinstance(offset, str):
                required.append(offset)
        if annotation.subset_column is not None:
            required.append(annotation.subset_column)
        missing = [col for col in required if col not in available_columns]
        if missing:
            raise ValueError(
                f"Colonnes d'annotation introuvables dans la couche '{layer_name}' : {missing}."
            )

        annotation_filter: models.Filter = view.filter
        if annotation.subset_column is not None:
            subset_values = src_geo.data[annotation.subset_column]
            static_indices = [i for i, value in enumerate(subset_values) if bool(value)]
            annotation_filter = models.IntersectionFilter(
                operands=[view.filter, models.IndexFilter(indices=static_indices)]
            )

        def _normalize_annotation_text(value: Any) -> Any:
            if isinstance(value, str):
                return value.replace("\\n", "\n")
            return value

        text_values = src_geo.data.get(annotation.text, [])
        normalized_text_values = [_normalize_annotation_text(value) for value in text_values]
        multiline = any(
            isinstance(value, str) and "\n" in value for value in normalized_text_values
        )

        if multiline:
            normalized_data = src_geo.data.copy()
            normalized_data[annotation.text] = [
                _normalize_annotation_text(value) for value in normalized_data[annotation.text]
            ]
            annotation_source = models.ColumnDataSource(normalized_data)
            annotation_view = models.CDSView(filter=annotation_filter)
        else:
            annotation_source = None
            annotation_view = None

        text_args: dict[str, Any] = {
            "x": annotation.x,
            "y": annotation.y,
            "text": annotation.text,
            "x_offset": annotation.x_offset,
            "y_offset": annotation.y_offset,
            "text_align": annotation.text_align,
            "text_font_size": annotation.text_font_size,
            "text_color": annotation.text_color,
            "padding": annotation.padding,
            "name": f"{layer_name}__annotation",
            "visible": visible_by_default,
        }
        if annotation.background_fill_color is not None:
            text_args["background_fill_color"] = annotation.background_fill_color
        if annotation.border_line_color is not None:
            text_args["border_line_color"] = annotation.border_line_color
        text_args.update(annotation.text_args)

        if multiline:
            text_args.update(
                {
                    "source": annotation_source,
                    "view": annotation_view,
                    "text_line_height": annotation.text_args.get("text_line_height", 1.1),
                }
            )
            return self.fig.text(**text_args)

        annotation_view = (
            view if annotation.subset_column is None else models.CDSView(filter=annotation_filter)
        )
        text_args.update({"source": src_geo, "view": annotation_view})
        return self.fig.text(**text_args)


class UIBuilderMixin(_CarteDynContext):
    def _format_indicator_number(self, value: float) -> str:
        text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
        return text.rstrip("0").rstrip(",")

    def _render_indicator_html(self, specs_by_layer: dict[str, list[dict[str, Any]]]) -> str:
        sections: list[str] = []
        for layer_name, specs in specs_by_layer.items():
            if not specs:
                continue
            rows = "".join(
                f"<div style='margin:1px 0;'>{spec['label']} : "
                f"<b>{self._format_indicator_number(spec['total'])}</b> / "
                f"{self._format_indicator_number(spec['total'])}</div>"
                for spec in specs
            )
            sections.append(
                f"<div style='margin-top:6px;'><div style='font-weight:600;'>{layer_name}</div>"
                f"{rows}</div>"
            )

        if not sections:
            return ""

        return "<div style='font-weight:bold; margin-bottom:4px;'>Indicateurs</div>" + "".join(
            sections
        )

    def _indicator_overlay_style(self) -> dict[str, str | None]:
        top = (
            OVERLAY_TOP_WITH_TOOLBAR_OFFSET_PX
            if self.map_config.toolbar_location == "above"
            else OVERLAY_EDGE_OFFSET_PX
        )
        return {
            "position": "absolute",
            "top": f"{top}px",
            "left": f"{OVERLAY_EDGE_OFFSET_PX}px",
            "z-index": "1001",
            "background": "rgba(255, 255, 255, 0.92)",
            "padding": "8px 10px",
            "border-radius": "6px",
            "box-shadow": "0 1px 4px rgba(0, 0, 0, 0.28)",
            "font-size": "12px",
            "line-height": "1.35",
            "max-width": "260px",
            "pointer-events": "none",
        }

    def _build_indicators_widget(self) -> models.Div | None:
        specs_by_layer = {name: layer.indicator_specs for name, layer in self.layers.items()}
        if not any(specs_by_layer.values()):
            return None

        return models.Div(
            text=self._render_indicator_html(specs_by_layer),
            styles=self._indicator_overlay_style(),
        )

    def _overlay_control_styles(
        self,
    ) -> tuple[dict[str, str | None], dict[str, str | None], dict[str, str | None]]:
        vertical, horizontal = self.map_config.legend_position.split("-")
        button_offset = OVERLAY_EDGE_OFFSET_PX
        if vertical == "top" and self.map_config.toolbar_location == "above":
            button_offset = OVERLAY_TOP_WITH_TOOLBAR_OFFSET_PX
        box_offset = button_offset + OVERLAY_BOX_GAP_PX

        legend_button_style: dict[str, str | None] = {
            "position": "absolute",
            vertical: f"{button_offset}px",
            "z-index": "1000",
        }
        tables_button_style: dict[str, str | None] = {
            "position": "absolute",
            vertical: f"{button_offset}px",
            "z-index": "1000",
        }

        if horizontal == "right":
            legend_button_style["right"] = f"{OVERLAY_EDGE_OFFSET_PX}px"
            tables_button_style["right"] = (
                f"{OVERLAY_EDGE_OFFSET_PX + LEGEND_BUTTON_WIDTH_PX + TABLES_BUTTON_SPACING_PX}px"
            )
        else:
            legend_button_style["left"] = f"{OVERLAY_EDGE_OFFSET_PX}px"
            tables_button_style["left"] = (
                f"{OVERLAY_EDGE_OFFSET_PX + LEGEND_BUTTON_WIDTH_PX + TABLES_BUTTON_SPACING_PX}px"
            )

        box_style: dict[str, str | None] = {
            "position": "absolute",
            vertical: f"{box_offset}px",
            horizontal: f"{OVERLAY_EDGE_OFFSET_PX}px",
            "z-index": "999",
        }
        return legend_button_style, tables_button_style, box_style

    def _render_legend_swatch(self, entry: LegendEntry) -> str:
        if entry.shape == "line":
            thickness = max(1.0, min(entry.size, 8.0))
            return (
                f"<span style='display:inline-block; width:18px; height:0; "
                f"border-top:{thickness}px solid {entry.color}; margin-right:6px; "
                f"vertical-align:middle;'></span>"
            )
        size = max(6.0, min(entry.size, 24.0))
        return self._point_marker_svg(entry.marker, entry.color, size)

    def _point_marker_svg(self, marker: str, color: str, size: float) -> str:
        half = size / 2
        stroke_w = max(1.0, size / 6)

        if marker == "square":
            shape = f'<rect x="0" y="0" width="{size:.1f}" height="{size:.1f}" fill="{color}"/>'
        elif marker == "diamond":
            shape = (
                f'<polygon points="{half:.1f},0 {size:.1f},{half:.1f} '
                f'{half:.1f},{size:.1f} 0,{half:.1f}" fill="{color}"/>'
            )
        elif marker == "triangle":
            shape = (
                f'<polygon points="{half:.1f},0 {size:.1f},{size:.1f} '
                f'0,{size:.1f}" fill="{color}"/>'
            )
        elif marker == "inverted_triangle":
            shape = f'<polygon points="0,0 {size:.1f},0 {half:.1f},{size:.1f}" fill="{color}"/>'
        elif marker == "hex":
            pts = self._regular_polygon_points(half, half, half, 6, start_angle=math.pi / 6)
            shape = f'<polygon points="{pts}" fill="{color}"/>'
        elif marker == "cross":
            w = max(1.0, size / 5)
            shape = (
                f'<rect x="{half - w / 2:.1f}" y="0" width="{w:.1f}" '
                f'height="{size:.1f}" fill="{color}"/>'
                f'<rect x="0" y="{half - w / 2:.1f}" width="{size:.1f}" '
                f'height="{w:.1f}" fill="{color}"/>'
            )
        elif marker in ("x", "asterisk"):
            shape = (
                f'<line x1="0" y1="0" x2="{size:.1f}" y2="{size:.1f}" '
                f'stroke="{color}" stroke-width="{stroke_w:.1f}"/>'
                f'<line x1="{size:.1f}" y1="0" x2="0" y2="{size:.1f}" '
                f'stroke="{color}" stroke-width="{stroke_w:.1f}"/>'
            )
            if marker == "asterisk":
                shape += (
                    f'<line x1="{half:.1f}" y1="0" x2="{half:.1f}" y2="{size:.1f}" '
                    f'stroke="{color}" stroke-width="{stroke_w:.1f}"/>'
                )
        elif marker == "star":
            pts = self._star_points(half, half, half, half * 0.45, 5)
            shape = f'<polygon points="{pts}" fill="{color}"/>'
        else:
            shape = f'<circle cx="{half:.1f}" cy="{half:.1f}" r="{half:.1f}" fill="{color}"/>'

        return (
            f'<svg width="{size:.1f}" height="{size:.1f}" viewBox="0 0 {size:.1f} {size:.1f}" '
            f"style='vertical-align:middle; margin-right:6px;'>{shape}</svg>"
        )

    @staticmethod
    def _regular_polygon_points(
        cx: float, cy: float, r: float, sides: int, start_angle: float = 0.0
    ) -> str:
        points = []
        for i in range(sides):
            angle = start_angle + 2 * math.pi * i / sides
            points.append(f"{cx + r * math.cos(angle):.1f},{cy + r * math.sin(angle):.1f}")
        return " ".join(points)

    @staticmethod
    def _star_points(cx: float, cy: float, outer_r: float, inner_r: float, spikes: int) -> str:
        points = []
        for i in range(spikes * 2):
            angle = math.pi / spikes * i - math.pi / 2
            r = outer_r if i % 2 == 0 else inner_r
            points.append(f"{cx + r * math.cos(angle):.1f},{cy + r * math.sin(angle):.1f}")
        return " ".join(points)

    def _build_legend_widget(self) -> models.Div | None:
        if self.legend_config is None or not self.legend_config.entries:
            return None

        rows = "".join(
            f"<div style='margin:3px 0;'>{self._render_legend_swatch(entry)}"
            f"<span>{entry.label}</span></div>"
            for entry in self.legend_config.entries
        )
        html = (
            f"<div style='font-weight:bold; margin-bottom:4px;'>"
            f"{self.legend_config.title}</div>{rows}"
        )

        _, _, box_style = self._overlay_control_styles()
        legend_width = self.legend_config.width
        box_style = {
            **box_style,
            "background": "white",
            "padding": "8px 12px",
            "border-radius": "6px",
            "box-shadow": "0 1px 4px rgba(0, 0, 0, 0.3)",
            "font-size": "12px",
            "line-height": "1.4",
            "max-width": f"{legend_width}px" if legend_width is not None else "200px",
        }
        return models.Div(
            text=html,
            styles=box_style,
            visible=self.legend_config.visible_by_default,
        )

    def _build_attribution_widget(self) -> models.Div:
        """Construit la signature cliquable, y compris pour les liens mailto:."""
        attribution = self.attribution_config
        return models.Div(
            text=(
                f'<a href="{attribution.href}" target="_blank" '
                'rel="noopener noreferrer" '
                f'style="color:#000; text-decoration:none;">{attribution.text}</a>'
            ),
            styles={
                "position": "absolute",
                "bottom": "16px",
                "right": "0px",
                "z-index": "998",
                "font-size": "10px",
                "opacity": "0.6",
                "background": "rgba(255, 255, 255, 0.6)",
                "padding": "0 4px",
                "border-radius": "3px",
                "pointer-events": "auto",
            },
            visible=True,
        )

    def _compute_left_panel_width(self) -> int:
        candidate_texts: list[str] = ["Filtres", "Réinitialiser", "Tableaux"]
        for widget in self.widgets_filters.values():
            if widget.title is not None:
                candidate_texts.append(str(widget.title))
            for option in widget.options:
                if isinstance(option, tuple):
                    candidate_texts.append(str(option[1]))
                else:
                    candidate_texts.append(str(option))

        longest = max((len(text) for text in candidate_texts if text), default=20)
        width = int(longest * LEFT_PANEL_PX_PER_CHAR + LEFT_PANEL_CHROME_PADDING_PX)
        return max(LEFT_PANEL_MIN_WIDTH_PX, min(width, LEFT_PANEL_MAX_WIDTH_PX))

    def _build_left_panel(
        self,
        left_panel_width: int,
        default_active_layers: list[int],
        default_active_annotations: list[int],
    ) -> models.Column:
        left_items: list[models.LayoutDOM] = []

        endpoint_toggles = self._build_endpoint_toggle_widgets(left_panel_width)
        if endpoint_toggles:
            left_items.append(
                models.Div(text="<b>Extrémités des tronçons</b>", margin=(8, 5, 0, 5))
            )
            left_items.extend(endpoint_toggles)

        if self.widgets_filters:
            left_items.append(models.Div(text="<b>Filtres</b>", margin=(8, 5, 0, 5)))
            left_items.append(
                models.Div(
                    text="Ctrl/Cmd+clic ou Maj+clic pour sélection multiple",
                    styles={
                        "font-size": f"{FILTER_HELP_FONT_SIZE_PX}px",
                        "color": "#888",
                        "margin": "2px 0 6px 0",
                        "margin-left": "5px",
                    },
                )
            )
            for key, widget in self.widgets_filters.items():
                left_items.append(widget)
                if self.widgets_filter_meta.get(key, {}).get("kind") == "multi":
                    left_items.append(
                        self._build_select_all_none_controls(cast(models.MultiSelect, widget))
                    )
        reset_button_css = models.InlineStyleSheet(
            css="""
            :host button, :host .bk-btn, button, .bk-btn {
                background-color: #ffffff !important;
                color: #415a9c !important;
                border: 1px solid #415a9c !important;
                border-radius: 6px !important;
                font-weight: 500 !important;
                font-size: 13px !important;
                cursor: pointer !important;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
                transition: all 0.15s ease-in-out !important;
            }
            :host button:hover, :host .bk-btn:hover, button:hover, .bk-btn:hover {
                background-color: #f0f4f9 !important;
                border-color: #334880 !important;
                color: #334880 !important;
            }
            :host button:active, :host .bk-btn:active, button:active, .bk-btn:active {
                background-color: #e2e8f0 !important;
            }
            """
        )

        self.reset_button = models.Button(
            label="Réinitialiser",
            width=left_panel_width,
            height=34,
            margin=(12, 0, 0, 0),
            stylesheets=[reset_button_css],
        )
        self.reset_button.js_on_click(
            models.CustomJS.from_file(
                self._js_path("reset_button.js"),
                layers={
                    name: {
                        "src_geo": layer.src_geo,
                        "filtre": layer.filtre,
                        "indicators": layer.indicator_specs,
                    }
                    for name, layer in self.layers.items()
                },
                widgets=self.widgets_filters,
                widgetMeta=self.widgets_filter_meta,
                layer_widget=self.layer_toggle_widget,
                default_active=default_active_layers,
                annotation_widget=self.annotation_toggle_widget,
                default_active_annotations=default_active_annotations,
                geometry_renderers={name: layer.renderer for name, layer in self.layers.items()},
                annotation_renderers={
                    name: layer.annotation_renderer
                    for name, layer in self.layers.items()
                    if layer.annotation_renderer is not None
                },
                layer_labels=list(self.layers.keys()),
                annotation_labels=[
                    name
                    for name, layer in self.layers.items()
                    if layer.annotation_renderer is not None
                ],
                indicatorDiv=self.indicators_widget,
                colIndexStr=COL_INDEX_STR,
            )
        )
        left_items.append(self.reset_button)

        return column(
            *left_items,
            width=left_panel_width,
            styles={"max-height": "100vh", "overflow-y": "auto", "padding-right": "4px"},
        )

    def _build_map_stack(self) -> models.Column:
        map_children: list[models.LayoutDOM] = [self.fig]
        if self.indicators_widget is not None:
            map_children.append(self.indicators_widget)

        self.layer_visibility_overlay = self._build_layer_visibility_overlay()
        self.toggle_layers_button = models.Button(
            label="Couches",
            button_type="default",
            height=OVERLAY_BUTTON_HEIGHT_PX,
            width=LAYER_VISIBILITY_BUTTON_WIDTH_PX,
            styles={
                "position": "absolute",
                "left": f"{OVERLAY_EDGE_OFFSET_PX}px",
                "bottom": f"{OVERLAY_EDGE_OFFSET_PX}px",
                "z-index": "1001",
            },
        )
        self.toggle_layers_button.js_on_click(
            models.CustomJS.from_file(
                self._js_path("toggle_legend.js"),
                legend=self.layer_visibility_overlay,
            )
        )

        map_children.append(self.layer_visibility_overlay)
        map_children.append(self.toggle_layers_button)

        legend_button_style, tables_button_style, _ = self._overlay_control_styles()
        self.toggle_tables_button = models.Button(
            label="Tables",
            button_type="default",
            height=OVERLAY_BUTTON_HEIGHT_PX,
            width=TABLES_BUTTON_WIDTH_PX,
            styles=tables_button_style,
        )
        self.toggle_tables_button.js_on_click(
            models.CustomJS.from_file(
                self._js_path("toggle_tables.js"),
                tables=self.tables_widget,
                plot=self.fig,
            )
        )
        map_children.append(self.toggle_tables_button)

        if self.legend_widget is not None:
            self.toggle_legend_button = models.Button(
                label="Légende",
                button_type="default",
                height=OVERLAY_BUTTON_HEIGHT_PX,
                width=LEGEND_BUTTON_WIDTH_PX,
                styles=legend_button_style,
            )
            self.toggle_legend_button.js_on_click(
                models.CustomJS.from_file(
                    self._js_path("toggle_legend.js"),
                    legend=self.legend_widget,
                )
            )
            map_children.append(self.legend_widget)
            map_children.append(self.toggle_legend_button)

        map_children.append(self._build_attribution_widget())

        stack_style: dict[str, str | None] = {"position": "relative"}
        return column(*map_children, sizing_mode="stretch_both", styles=stack_style)

    def _build_layer_visibility_overlay(self) -> models.Column:
        children: list[models.LayoutDOM] = [
            models.Div(text="<b>Couches</b>", margin=(0, 0, 4, 0)),
            self.layer_toggle_widget,
        ]
        if self.annotation_toggle_widget is not None:
            children.append(models.Div(text="<b>Annotations</b>", margin=(8, 0, 4, 0)))
            children.append(self.annotation_toggle_widget)

        return column(
            *children,
            width=LAYER_VISIBILITY_PANEL_WIDTH_PX,
            styles=self._layer_visibility_overlay_style(),
            visible=False,
        )

    def _layer_visibility_overlay_style(self) -> dict[str, str | None]:
        bottom = OVERLAY_EDGE_OFFSET_PX + OVERLAY_BUTTON_HEIGHT_PX + LAYER_VISIBILITY_PANEL_GAP_PX
        return {
            "position": "absolute",
            "left": f"{OVERLAY_EDGE_OFFSET_PX}px",
            "bottom": f"{bottom}px",
            "z-index": "1000",
            "background": "rgba(255, 255, 255, 0.88)",
            "padding": "8px 10px",
            "border-radius": "6px",
            "box-shadow": "0 1px 4px rgba(0, 0, 0, 0.22)",
            "font-size": "12px",
            "line-height": "1.35",
            "max-height": "42vh",
            "overflow-y": "auto",
            "pointer-events": "auto",
        }

    def _build_select_all_none_controls(self, widget: models.MultiSelect) -> models.Row:
        button_css = models.InlineStyleSheet(
            css=f"""
            :host, :host button, :host .bk-btn, button, .bk-btn {{
                font-size: {SELECT_BTN_FONT_SIZE_PX}px !important;
                padding: 0px !important;
                line-height: {SELECT_BTN_LINE_HEIGHT_PX}px !important;
                min-height: 0 !important;
                box-sizing: border-box !important;
                text-align: center !important;
                background-color: #eef0f3 !important;
                color: #6b7280 !important;
                border-color: #d5d9df !important;
            }}
            """
        )
        btn_all = models.Button(
            label="Tout",
            button_type="light",
            width=SELECT_BTN_ALL_WIDTH_PX,
            height=SELECT_BTN_HEIGHT_PX,
            stylesheets=[button_css],
        )
        btn_none = models.Button(
            label="Aucun",
            button_type="light",
            width=SELECT_BTN_NONE_WIDTH_PX,
            height=SELECT_BTN_HEIGHT_PX,
            stylesheets=[button_css],
        )

        btn_all.js_on_click(
            models.CustomJS.from_file(
                self._js_path("select_all_none.js"), select=widget, mode="all"
            )
        )
        btn_none.js_on_click(
            models.CustomJS.from_file(
                self._js_path("select_all_none.js"), select=widget, mode="none"
            )
        )

        return row(btn_all, btn_none, spacing=SELECT_BTN_SPACING_PX)

    def _build_export_csv_button(
        self, name: str, layer: LayerState, display_columns: list[str]
    ) -> models.Button:
        float_cols = [
            col
            for col in display_columns
            if col in layer.raw_data.columns and pd.api.types.is_float_dtype(layer.raw_data[col])
        ]
        safe_name = re.sub(r"[^\w\-]+", "_", name).strip("_") or "layer"

        export_button_css = models.InlineStyleSheet(
            css="""
            :host button, :host .bk-btn, button, .bk-btn {
                background-color: #ffffff !important;
                color: #415a9c !important;
                border: 1px solid #415a9c !important;
                border-radius: 5px !important;
                font-weight: 500 !important;
                font-size: 12px !important;
                line-height: 26px !important;
                padding: 0 10px !important;
                min-height: 0 !important;
                cursor: pointer !important;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
                transition: all 0.15s ease-in-out !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            :host button:hover, :host .bk-btn:hover, button:hover, .bk-btn:hover {
                background-color: #f0f4f9 !important;
                border-color: #334880 !important;
                color: #334880 !important;
            }
            :host button:active, :host .bk-btn:active, button:active, .bk-btn:active {
                background-color: #e2e8f0 !important;
            }
            """
        )

        button = models.Button(
            label="⤓ Exporter CSV",
            height=28,
            width=self.map_config.tables_panel_width,
            margin=(4, 0, 4, 0),
            stylesheets=[export_button_css],
        )
        button.js_on_click(
            models.CustomJS.from_file(
                self._js_path("export_csv.js"),
                source=layer.src_geo,
                filtre=layer.filtre,
                cols=display_columns,
                float_cols=float_cols,
                filename=f"{safe_name}.csv",
            )
        )
        return button

    def _build_tables_tabs(self) -> models.Tabs:
        panels = []
        for name, layer in self.layers.items():
            if layer.cfg.has_table:
                display_columns = layer.cfg.columns_to_show or self._default_display_columns(
                    layer.raw_data
                )
                columns = [models.TableColumn(field=col, title=col) for col in display_columns]

                if _BOKEH_SUPPORTS_IGNORE_VIEWPORT:
                    table = models.DataTable(
                        source=layer.src_geo,
                        view=layer.view,
                        columns=columns,
                        sizing_mode="stretch_height",
                        width=self.map_config.tables_panel_width,
                        autosize_mode="ignore_viewport",
                    )
                else:
                    table = models.DataTable(
                        source=layer.src_geo,
                        view=layer.view,
                        columns=columns,
                        sizing_mode="stretch_height",
                        width=self.map_config.tables_panel_width,
                    )
                export_button = self._build_export_csv_button(name, layer, display_columns)
                panel_content = column(
                    export_button,
                    table,
                    sizing_mode="stretch_height",
                    width=self.map_config.tables_panel_width,
                )
                panels.append(models.TabPanel(child=panel_content, title=name))
        tabs = models.Tabs(
            tabs=panels,
            sizing_mode="stretch_height",
            width=self.map_config.tables_panel_width,
            visible=False,
        )
        return tabs

    def _build_endpoint_toggle_widgets(self, width: int) -> list[models.Toggle]:
        toggles: list[models.Toggle] = []
        for name, layer in self.layers.items():
            if layer.endpoint_renderers is None:
                continue
            renderer_start, renderer_end = layer.endpoint_renderers
            toggle = models.Toggle(
                label=f"Extr. : {name}",
                active=False,
                width=width,
                height=28,
                margin=(2, 0, 2, 0),
            )
            toggle.js_on_change(
                "active",
                models.CustomJS.from_file(
                    self._js_path("toggle_endpoints.js"),
                    renderer_start=renderer_start,
                    renderer_end=renderer_end,
                ),
            )
            toggles.append(toggle)
        return toggles

    def _js_path(self, filename: str) -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parent / "js" / filename)
