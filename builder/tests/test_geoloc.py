import json

import geopandas as gpd
import pandas as pd
import pytest
from cartes_builder import ajoute_geo
from shapely.geometry import LineString


@pytest.fixture
def tronloc():
    # Ligne droite de 10 km vers l'est, découpée en deux tronçons de 5 km (PK en km).
    return gpd.GeoDataFrame(
        {
            "code_ligne": [1000, 1000],
            "pkmd": [0.0, 5.0],
            "pkmf": [5.0, 10.0],
        },
        geometry=[
            LineString([(600000, 6800000), (605000, 6800000)]),
            LineString([(605000, 6800000), (610000, 6800000)]),
        ],
        crs="EPSG:2154",
    ).to_crs(3857)


def test_troncon_unite_km(tronloc):
    tron = pd.DataFrame({"code_ligne": [1000], "pkmd": [2.0], "pkmf": [7.0]})
    res = ajoute_geo(
        tron, tronloc, on="code_ligne", pk_lbls=("pkmd", "pkmf"), tronloc_pk_lbls=("pkmd", "pkmf")
    )
    assert res.crs == "EPSG:3857"
    length = res.to_crs(2154).geometry.iloc[0].length
    assert length == pytest.approx(5000, rel=1e-3)


def test_marker_utilise_unite_pk(tronloc):
    tron = pd.DataFrame({"code_ligne": [1000], "pkmd": [3], "pkmf": [None]})
    res = ajoute_geo(
        tron,
        tronloc,
        on="code_ligne",
        pk_lbls=("pkmd", "pkmf"),
        tronloc_pk_lbls=("pkmd", "pkmf"),
        pk_unit_m=1000.0,
    )
    point = res.to_crs(2154).geometry.iloc[0]
    assert point.geom_type == "Point"
    assert point.x == pytest.approx(603005, abs=1)


def test_pk_en_entiers_et_colonnes_preservees(tronloc):
    tron = pd.DataFrame({"code_ligne": [1000], "pkmd": [1], "pkmf": [2], "v": ["x"]})
    res = ajoute_geo(
        tron, tronloc, on="code_ligne", pk_lbls=("pkmd", "pkmf"), tronloc_pk_lbls=("pkmd", "pkmf")
    )
    assert list(res.columns) == ["code_ligne", "pkmd", "pkmf", "v", "geometry"]
    assert res["pkmd"].tolist() == [1]


def test_json_serialisable_sans_erreur(tronloc):
    tron = pd.DataFrame({"code_ligne": [1000], "pkmd": [0.0], "pkmf": [1.0]})
    res = ajoute_geo(
        tron, tronloc, on="code_ligne", pk_lbls=("pkmd", "pkmf"), tronloc_pk_lbls=("pkmd", "pkmf")
    )
    json.loads(res.to_json())
