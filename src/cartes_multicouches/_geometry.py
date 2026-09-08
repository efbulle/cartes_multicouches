from shapely.geometry import LineString, MultiLineString


def _extract_line_coords(
    geom: LineString | MultiLineString | None,
) -> tuple[list[float], list[float]]:
    """Extrait les coordonnées d'une ligne pour multi_line."""
    if geom is None or geom.is_empty:
        return [], []
    if isinstance(geom, MultiLineString):
        xs: list[float] = []
        ys: list[float] = []
        for i, part in enumerate(geom.geoms):
            if i > 0:
                xs.append(float("nan"))
                ys.append(float("nan"))
            px, py = part.coords.xy
            xs.extend(px)
            ys.extend(py)
        return xs, ys
    if isinstance(geom, LineString):
        px, py = geom.coords.xy
        return list(px), list(py)
    raise TypeError(f"Attendu LineString ou MultiLineString, reçu {type(geom).__name__}")


def _line_start_end(
    geom: LineString | MultiLineString | None,
) -> tuple[float, float, float, float] | None:
    """Extrémités globales (début, fin) d'une géométrie ligne."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, MultiLineString):
        parts = list(geom.geoms)
        if not parts:
            return None
        start_coords = list(parts[0].coords)
        end_coords = list(parts[-1].coords)
    elif isinstance(geom, LineString):
        start_coords = end_coords = list(geom.coords)
    else:
        raise TypeError(f"Attendu LineString ou MultiLineString, reçu {type(geom).__name__}")

    if not start_coords or not end_coords:
        return None

    x_start, y_start = start_coords[0]
    x_end, y_end = end_coords[-1]
    return x_start, y_start, x_end, y_end


def _line_label_point(
    geom: LineString | MultiLineString | None,
) -> tuple[float, float] | None:
    """Point de label stable pour une géométrie ligne."""
    if geom is None or geom.is_empty:
        return None

    if not isinstance(geom, (LineString, MultiLineString)):
        raise TypeError(f"Attendu LineString ou MultiLineString, reçu {type(geom).__name__}")

    try:
        point = geom.interpolate(0.5, normalized=True)
    except ValueError:
        point = geom.representative_point()

    return float(point.x), float(point.y)
