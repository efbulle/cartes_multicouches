"""Référentiel public de géolocalisation des tronçons du RFN.

Construit à partir des PK de
https://github.com/nicolaswurtz/extras-opendata-sncf-reseau, mis à disposition
sous la licence Open Database (ODbL) : http://opendatacommons.org/licenses/odbl/1.0/

Les PK du référentiel produit sont exprimés en **kilomètres** (colonnes `pkmd`
et `pkmf`) et la clé de jointure est `code_ligne` (entier).
"""

import io
import urllib.request
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely import line_merge, linestrings

PKS_URL = (
    "https://raw.githubusercontent.com/nicolaswurtz/extras-opendata-sncf-reseau/master/pks.csv.zip"
)
PKS_ATTRIBUTION = (
    "Référentiel de PK : extras-opendata-sncf-reseau (N. Wurtz), licence ODbL "
    "http://opendatacommons.org/licenses/odbl/1.0/"
)


def download_and_prepare_tronloc(url: str = PKS_URL, pk_step: float = 1.0) -> gpd.GeoDataFrame:
    """Télécharge les PK et génère des tronçons continus sans trou géométrique.

    Retourne un GeoDataFrame EPSG:3857 de colonnes `code_ligne`, `pkmd`, `pkmf`
    (PK en km) et `geometry`, avec un tronçon par tranche de `pk_step` km.
    """
    import polars as pl  # import différé : dépendance lourde, utile à cette fonction seule

    with urllib.request.urlopen(url, timeout=120) as req:
        payload = req.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf, zf.open(zf.namelist()[0]) as f:
        df_pks = pl.read_csv(f.read())

    cleaned = (
        df_pks.filter(
            pl.col("pk").is_not_null() & pl.col("lat").is_not_null() & pl.col("lon").is_not_null()
        )
        .with_columns(pl.col("code_ligne").cast(pl.Int32))
        .sort(["code_ligne", "pk"])
    )

    # Suppression des doublons et des PK régressifs
    cleaned = cleaned.filter(pl.col("pk").diff().over("code_ligne").fill_null(0.0) >= 0)

    cleaned = cleaned.with_columns(bucket=(pl.col("pk") / pk_step).floor().cast(pl.Int64))

    # Segments unitaires entre le point i et le point i+1
    segments = cleaned.with_columns(
        pk_next=pl.col("pk").shift(-1).over("code_ligne"),
        lon_next=pl.col("lon").shift(-1).over("code_ligne"),
        lat_next=pl.col("lat").shift(-1).over("code_ligne"),
    ).filter(
        pl.col("pk_next").is_not_null() & ((pl.col("pk_next") - pl.col("pk")) <= (pk_step * 2))
    )

    df_pd = segments.to_pandas()

    coords_start = df_pd[["lon", "lat"]].to_numpy()
    coords_end = df_pd[["lon_next", "lat_next"]].to_numpy()
    unit_geoms = linestrings(np.stack([coords_start, coords_end], axis=1))

    gdf_units = gpd.GeoDataFrame(
        df_pd[["code_ligne", "bucket", "pk", "pk_next"]],
        geometry=unit_geoms,
        crs="EPSG:4326",
    )

    gdf_dissolved = gdf_units.dissolve(
        by=["code_ligne", "bucket"],
        aggfunc={"pk": "min", "pk_next": "max"},
        as_index=False,
    )

    # Fusion des morceaux de chaque tranche en une seule LineString continue
    gdf_dissolved["geometry"] = gdf_dissolved["geometry"].apply(line_merge)
    gdf_dissolved = gdf_dissolved.rename(columns={"pk": "pkmd", "pk_next": "pkmf"})

    return gdf_dissolved[["code_ligne", "pkmd", "pkmf", "geometry"]].to_crs(epsg=3857)


def build_tronloc_file(path: Path | str, url: str = PKS_URL, pk_step: float = 1.0) -> Path:
    """Génère le référentiel et l'écrit au format parquet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    download_and_prepare_tronloc(url, pk_step).to_parquet(path)
    return path
