"""Géolocalisation de tronçons décrits par PK sur un référentiel linéaire.

Ce module est autonome : il est injecté tel quel (code source) dans les pages
générées par `cartes_builder.gen_carte`, et exécuté dans le navigateur via
PyScript. Il ne doit donc importer que des paquets disponibles dans Pyodide
et aucun import relatif.
"""

import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import linemerge, substring

# Marge utilisée pour localiser un marker (PK ponctuel).
# On recherche une géométrie sur [pkmd, pkmd + marker_padding_m],
# puis on prend le centroïde de la géométrie obtenue.
MARKER_PADDING_M = 10.0

_METRIC_CRS = "EPSG:2154"
_OUTPUT_CRS = "EPSG:3857"


def _validate_columns(df: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    """Vérifie la présence des colonnes requises."""
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{name} ne contient pas les colonnes requises : {', '.join(missing)}.")


def _validate_pk(tron: pd.DataFrame, pk_lbls: tuple[str, str]) -> tuple[pd.Series, pd.Series]:
    """Valide les colonnes PK de `tron` et retourne les masques utiles."""
    pkmd, pkmf = pk_lbls

    for column in pk_lbls:
        series = tron[column]
        valid_values = series.map(
            lambda value: pd.isna(value) or isinstance(value, (int, float, np.integer, np.floating))
        )
        if not valid_values.all():
            raise TypeError(f"La colonne PK '{column}' doit être numérique.")

    pkmd_num = pd.to_numeric(tron[pkmd], errors="coerce")
    pkmf_num = pd.to_numeric(tron[pkmf], errors="coerce")

    if pkmd_num.isna().any():
        indexes = tron.index[pkmd_num.isna()].tolist()
        raise ValueError(
            f"La colonne PK début contient des valeurs manquantes (index concernés : {indexes})."
        )

    if np.isinf(pkmd_num.to_numpy()).any():
        raise ValueError(f"La colonne PK début '{pkmd}' contient des valeurs infinies.")

    if np.isinf(pkmf_num.dropna().to_numpy()).any():
        raise ValueError(f"La colonne PK fin '{pkmf}' contient des valeurs infinies.")

    is_marker = pkmf_num.isna() | (pkmf_num == pkmd_num)
    invalid = ~is_marker & (pkmf_num < pkmd_num)

    return is_marker, invalid


def _merge_lines(geoms):
    """Fusionne une collection de LineString/MultiLineString."""
    lines = []

    for geom in geoms:
        if geom is None or geom.is_empty:
            continue

        if geom.geom_type == "LineString":
            lines.append(geom)
        elif geom.geom_type == "MultiLineString":
            lines.extend(geom.geoms)

    return linemerge(lines) if lines else None


def _localise(
    tronloc: gpd.GeoDataFrame,
    tron: pd.DataFrame,
    on: str,
    pk_lbls: tuple[str, str],
    tronloc_pk_lbls: tuple[str, str],
) -> gpd.GeoDataFrame:
    """
    Géolocalise des tronçons par intersection d'intervalles PK.

    `tronloc` doit contenir :
      - la colonne `on`,
      - les colonnes PK indiquées par `tronloc_pk_lbls`,
      - des géométries de type LineString ou MultiLineString.

    `tron` doit contenir :
      - la colonne `on`,
      - les colonnes PK indiquées par `pk_lbls`.

    Pour chaque ligne de `tron`, les intervalles PK qui se recouvrent
    dans `tronloc` sont découpés puis fusionnés.

    Le référencement linéaire est calculé en distance cumulée sur
    l'ensemble des parties d'un même tronçon `tronloc`. Cela évite de
    traiter indépendamment les différentes parties d'un MultiLineString.

    Le calcul géométrique est effectué en EPSG:2154. Le résultat est
    retourné dans le CRS de `tronloc`.

    Cette fonction ne gère pas directement les markers : l'appelant doit
    fournir un intervalle PK strictement positif.
    """
    pkmd, pkmf = pk_lbls
    tronloc_pkmd, tronloc_pkmf = tronloc_pk_lbls

    _validate_columns(tron, (on, pkmd, pkmf), "tron")
    _validate_columns(tronloc, (on, tronloc_pkmd, tronloc_pkmf, "geometry"), "tronloc")

    if tronloc.crs is None:
        raise ValueError("Le GeoDataFrame 'tronloc' doit posséder un CRS.")

    if tron.empty:
        result = tron.copy()
        result["geometry"] = gpd.GeoSeries(index=result.index, dtype="geometry", crs=tronloc.crs)
        return gpd.GeoDataFrame(result, geometry="geometry", crs=tronloc.crs)

    # Identifiant temporaire indépendant de l'index utilisateur.
    t = tron.copy()
    t["_temp_id"] = np.arange(len(t))

    # Les colonnes PK de `tron` peuvent utiliser des libellés différents,
    # mais le calcul interne s'appuie sur les noms standard `pkmd`/`pkmf`.
    t = t.rename(columns={pkmd: "pkmd", pkmf: "pkmf"})

    # Les tronçons de référence ponctuels ne peuvent pas être découpés
    # comme des intervalles.
    tl = tronloc.loc[tronloc[tronloc_pkmd] != tronloc[tronloc_pkmf]].copy()

    # Identifiant du tronçon avant explosion.
    tl["_tl_gid"] = np.arange(len(tl))

    # On travaille partie par partie, tout en conservant un identifiant
    # permettant de reconstruire la distance cumulée sur le MultiLineString.
    tl = tl.explode(index_parts=False)

    # Calcul des longueurs physiques en mètres.
    tl = tl.to_crs(_METRIC_CRS)

    tl["_part_len"] = tl.geometry.length

    # Les géométries de longueur nulle ne peuvent pas être paramétrées
    # par une distance curviligne.
    tl = tl.loc[tl["_part_len"] > 0].copy()

    tl["_cum_start"] = tl.groupby("_tl_gid")["_part_len"].cumsum() - tl["_part_len"]

    tl["_total_len"] = tl.groupby("_tl_gid")["_part_len"].transform("sum")

    if tl.empty:
        result = t.drop(columns="_temp_id").copy()
        result["geometry"] = None
        return gpd.GeoDataFrame(result, geometry="geometry", crs=tronloc.crs)

    # Jointure sur l'identifiant de ligne.
    merged = tl.merge(
        t[[on, "pkmd", "pkmf", "_temp_id"]].rename(
            columns={"pkmd": f"{pkmd}_t", "pkmf": f"{pkmf}_t"}
        ),
        on=on,
        suffixes=("", "_t"),
    )

    # Intersection des intervalles PK.
    merged["int_start"] = merged[["pkmd", f"{pkmd}_t"]].max(axis=1)
    merged["int_end"] = merged[["pkmf", f"{pkmf}_t"]].min(axis=1)

    geo_seg = merged.loc[merged["int_start"] < merged["int_end"]].copy()

    if geo_seg.empty:
        agg_results = pd.DataFrame(columns=["geometry", on])
    else:
        # Position de l'intersection en mètres le long du tronçon complet.
        denom = geo_seg["pkmf"] - geo_seg["pkmd"]

        dist_start = (geo_seg["int_start"] - geo_seg["pkmd"]) / denom * geo_seg["_total_len"]

        dist_end = (geo_seg["int_end"] - geo_seg["pkmd"]) / denom * geo_seg["_total_len"]

        # Conversion vers les distances locales de la partie courante.
        s_local = (dist_start - geo_seg["_cum_start"]).clip(lower=0, upper=geo_seg["_part_len"])

        e_local = (dist_end - geo_seg["_cum_start"]).clip(lower=0, upper=geo_seg["_part_len"])

        geo_seg["s_norm"] = s_local / geo_seg["_part_len"]
        geo_seg["e_norm"] = e_local / geo_seg["_part_len"]

        # Une partie peut ne pas être traversée par l'intersection.
        geo_seg = geo_seg.loc[geo_seg["s_norm"] < geo_seg["e_norm"]].copy()

        if geo_seg.empty:
            agg_results = pd.DataFrame(columns=["geometry", on])
        else:
            geo_seg["geometry"] = gpd.GeoSeries(
                [
                    substring(geom, s, e, normalized=True)
                    for geom, s, e in zip(
                        geo_seg["geometry"],
                        geo_seg["s_norm"],
                        geo_seg["e_norm"],
                        strict=True,
                    )
                ],
                index=geo_seg.index,
                crs=geo_seg.crs,
            )

            agg_results = geo_seg.groupby("_temp_id").agg(
                geometry=("geometry", _merge_lines), **{on: (on, "first")}
            )

    # Reconstruction dans l'ordre et avec l'index de `tron`.
    t["geometry"] = t["_temp_id"].map(agg_results["geometry"])

    n_missing = t["geometry"].isna().sum()

    if n_missing:
        warnings.warn(
            f"{n_missing}/{len(t)} tronçon(s) n'ont pas pu être "
            f"géolocalisés : aucun segment géographique ne correspond "
            f"à leur intervalle PK sur la colonne '{on}'.",
            stacklevel=2,
        )

    result = gpd.GeoDataFrame(t, geometry="geometry", crs=_METRIC_CRS)

    # Retour dans le CRS original de tronloc.
    result = result.to_crs(tronloc.crs)

    return result.drop(columns="_temp_id")


def ajoute_geo(
    tron: pd.DataFrame,
    tronloc: gpd.GeoDataFrame,
    on: str,
    pk_lbls: tuple[str, str],
    tronloc_pk_lbls: tuple[str, str],
    marker_padding_m: float = MARKER_PADDING_M,
    pk_unit_m: float = 1.0,
) -> gpd.GeoDataFrame:
    """
    Ajoute une géométrie aux tronçons décrits par leurs PK.

    Une ligne est considérée comme un marker si :
      - `pkmf` est manquant, ou
      - `pkmf == pkmd`.

    Pour un marker, une petite fenêtre `[pkmd, pkmd + marker_padding_m]`
    est utilisée pour localiser la géométrie, puis son centroïde est
    retourné.

    Pour les autres lignes, `pkmf` doit être strictement supérieur à
    `pkmd`.

    Parameters
    ----------
    tron:
        DataFrame contenant au minimum `on`, `pkmd` et `pkmf`.

    tronloc:
        GeoDataFrame contenant les géométries de référence. Son CRS doit
        être défini.

    on:
        Colonne identifiant la ligne ou le tronçon de référence.

    pk_lbls:
        Noms des colonnes PK dans `tron`.

    tronloc_pk_lbls:
        Noms des colonnes PK dans `tronloc`. Ces colonnes peuvent être
        différentes de celles de `tron`.

    marker_padding_m:
        Longueur, en mètres, de la fenêtre utilisée pour localiser
        un marker.

    pk_unit_m:
        Valeur d'une unité de PK en mètres : 1.0 si les PK sont en mètres
        (défaut), 1000.0 si les PK sont en kilomètres. Les PK de `tron` et
        de `tronloc` doivent être exprimés dans la même unité.

    Returns
    -------
    geopandas.GeoDataFrame
        Les colonnes originales de `tron`, plus `geometry`, en EPSG:3857.

        Les tronçons sont représentés par des LineString ou MultiLineString.
        Les markers sont représentés par des Points.

    Raises
    ------
    ValueError
        Si les PK sont incohérents, si l'index est dupliqué ou si les
        colonnes requises sont absentes.

    TypeError
        Si les colonnes PK ne sont pas numériques.
    """
    pkmd, pkmf = pk_lbls
    tronloc_pkmd, tronloc_pkmf = tronloc_pk_lbls

    _validate_columns(tron, (on, pkmd, pkmf), "tron")

    if tron.index.has_duplicates:
        raise ValueError("L'index de 'tron' doit être constitué de valeurs uniques.")

    if not isinstance(marker_padding_m, (int, float)):
        raise TypeError("'marker_padding_m' doit être un nombre.")

    if not np.isfinite(marker_padding_m) or marker_padding_m <= 0:
        raise ValueError("'marker_padding_m' doit être strictement positif.")

    if not np.isfinite(pk_unit_m) or pk_unit_m <= 0:
        raise ValueError("'pk_unit_m' doit être strictement positif.")

    is_marker, invalid = _validate_pk(tron, pk_lbls)

    if invalid.any():
        raise ValueError(
            "Le PK fin doit être strictement supérieur au PK début "
            "pour les tronçons non-marker "
            f"(index concernés : {tron.index[invalid].tolist()})."
        )

    # Le chargement peut être évité pour un DataFrame vide.
    if tron.empty:
        result = tron.copy()
        result["geometry"] = gpd.GeoSeries(index=result.index, dtype="geometry", crs=_OUTPUT_CRS)
        return gpd.GeoDataFrame(result, geometry="geometry", crs=_OUTPUT_CRS)

    if not isinstance(tronloc, gpd.GeoDataFrame):
        raise TypeError("'tronloc' doit être un GeoDataFrame.")

    tronloc_comp = tronloc.copy()

    _validate_columns(tronloc_comp, (on, tronloc_pkmd, tronloc_pkmf, "geometry"), "tronloc")

    if tronloc_comp.crs is None:
        raise ValueError("Le GeoDataFrame 'tronloc' doit posséder un CRS.")

    # Les markers doivent temporairement être transformés en petits
    # intervalles afin de pouvoir utiliser le même mécanisme de
    # localisation que pour les tronçons.
    tron_padded = tron.copy()
    tron_padded[pkmd] = tron_padded[pkmd].astype(float)
    tron_padded[pkmf] = tron_padded[pkmf].astype(float)

    tron_padded.loc[is_marker, pkmf] = (
        tron_padded.loc[is_marker, pkmd] + marker_padding_m / pk_unit_m
    )

    geo = _localise(
        tronloc_comp,
        tron_padded,
        on=on,
        pk_lbls=pk_lbls,
        tronloc_pk_lbls=tronloc_pk_lbls,
    )

    # Restaurer les libellés PK originaux avant de reconstruire la sortie.
    geo = geo.rename(columns={"pkmd": pkmd, "pkmf": pkmf})

    # Restaurer exactement les valeurs originales, notamment les NaN.
    geo[pkmd] = tron[pkmd]
    geo[pkmf] = tron[pkmf]

    # Les markers deviennent des points.
    if is_marker.any():
        marker_geometry = geo.loc[is_marker, "geometry"]

        geo.loc[is_marker, "geometry"] = marker_geometry.centroid

    # Ne conserver que les colonnes d'origine, dans leur ordre initial,
    # puis la géométrie.
    result = geo[[*tron.columns, "geometry"]].copy()

    result = gpd.GeoDataFrame(result, geometry="geometry", crs=geo.crs)

    return result.to_crs(_OUTPUT_CRS)
