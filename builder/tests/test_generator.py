import base64
import gzip
import json
import re
import zipfile

import geopandas as gpd
import pandas as pd
import pytest
from cartes_builder import Dataset, gen_carte
from shapely.geometry import LineString


def macarte(xl, feuille, tronloc, villes, attribution_config, tile_provider_api_key):
    return None


def macarte_cle(xl, tronloc, tile_provider_api_key):
    return tile_provider_api_key


def macarte_pk(xl):
    from pktools.pandas import ext_to_m  # pyright: ignore[reportMissingImports]

    return ext_to_m(pd.read_excel(xl)["pk"])


@pytest.fixture(autouse=True)
def _sans_cle_env(monkeypatch):
    # La CI exporte la vraie clé de tuiles : les tests ne doivent pas en dépendre.
    monkeypatch.delenv("CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY", raising=False)


@pytest.fixture
def wheel(tmp_path):
    path = tmp_path / "pkg-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("pkg/__init__.py", "")
    return path


@pytest.fixture
def pktools_wheel(tmp_path):
    path = tmp_path / "pktools-0.12.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("pktools/__init__.py", "")
    return path


@pytest.fixture
def datasets(tmp_path):
    gdf = gpd.GeoDataFrame(
        {"code_ligne": [1], "pkmd": [0.0], "pkmf": [1.0]},
        geometry=[LineString([(0.0, 0.0), (1000.123456, 0.0)])],
        crs=3857,
    )
    gdf.to_parquet(tmp_path / "tronloc.parquet")
    pd.DataFrame({"name": ["Paris"], "x": [1.0], "y": [2.0]}).to_csv(tmp_path / "villes.csv")
    return {"tronloc": tmp_path / "tronloc.parquet", "villes": tmp_path / "villes.csv"}


def _manifest(html: str) -> dict:
    m = re.search(r'id="assets-manifest">\s*(.*?)\s*</script>', html, re.DOTALL)
    assert m is not None
    return json.loads(m.group(1))


def test_standalone_inline_sans_placeholder(tmp_path, wheel, datasets):
    out = gen_carte(
        macarte,
        tmp_path / "out" / "carte",
        datasets=datasets,
        select={"Feuille": "xl_sheetnames"},
        wheel_path=wheel,
        attribution_config={"text": "t"},
    )
    page = out.read_text(encoding="utf-8")
    assert "{{" not in page.replace("{{{", "")
    assert "def mafunc(xl, feuille):" in page
    assert "def ajoute_geo" in page
    assert 'id="sel_0"' in page

    manifest = _manifest(page)
    assert "pktools_wheel" not in manifest
    assert base64.b64decode(manifest["wheel"]["b64"]) == wheel.read_bytes()
    tronloc = json.loads(gzip.decompress(base64.b64decode(manifest["datasets"]["tronloc"]["b64"])))
    assert manifest["datasets"]["tronloc"]["kind"] == "geo"
    # Coordonnées arrondies à la grille de 0.1
    assert tronloc["features"][0]["geometry"]["coordinates"][1][0] == 1000.1
    assert manifest["datasets"]["villes"]["kind"] == "table"


def test_pages_ecrit_assets(tmp_path, wheel, datasets):
    out = gen_carte(
        macarte,
        tmp_path / "site" / "app",
        datasets=datasets,
        wheel_path=wheel,
        standalone=False,
    )
    manifest = _manifest(out.read_text(encoding="utf-8"))
    assert "pktools_wheel" not in manifest
    assert "b64" not in manifest["wheel"]
    for spec in [manifest["wheel"], *manifest["datasets"].values()]:
        assert (out.parent / spec["url"]).is_file()


@pytest.mark.parametrize("standalone", [True, False])
def test_wheel_pktools_optionnel(tmp_path, wheel, pktools_wheel, standalone):
    out = gen_carte(
        macarte_pk,
        tmp_path / "site" / "app.html",
        wheel_path=wheel,
        pktools_wheel_path=pktools_wheel,
        standalone=standalone,
    )
    page = out.read_text(encoding="utf-8")
    manifest = _manifest(page)
    assert "from pktools.pandas import ext_to_m" in page
    for spec, expected in (
        (manifest["wheel"], wheel),
        (manifest["pktools_wheel"], pktools_wheel),
    ):
        assert spec["name"] == expected.name
        if standalone:
            assert base64.b64decode(spec["b64"]) == expected.read_bytes()
        else:
            assert (out.parent / spec["url"]).read_bytes() == expected.read_bytes()


def test_wheel_pktools_invalide_ou_absent(tmp_path, wheel):
    with pytest.raises(ValueError, match="wheel pktools"):
        gen_carte(macarte_pk, tmp_path / "a", wheel_path=wheel, pktools_wheel_path=wheel)
    with pytest.raises(ValueError, match="invalide"):
        gen_carte(macarte_pk, tmp_path / "a", wheel_path=wheel, pktools_wheel_path="pktools.whl")
    with pytest.raises(FileNotFoundError):
        gen_carte(
            macarte_pk,
            tmp_path / "a",
            wheel_path=wheel,
            pktools_wheel_path=tmp_path / "pktools-0.12.0-py3-none-any.whl",
        )


def test_wheels_de_meme_nom_refuses(tmp_path, pktools_wheel):
    with pytest.raises(ValueError, match="distincts"):
        gen_carte(
            macarte_pk,
            tmp_path / "a",
            wheel_path=pktools_wheel,
            pktools_wheel_path=pktools_wheel,
            standalone=False,
        )


def test_pages_refuse_dataset_prive(tmp_path, wheel, datasets):
    datasets["tronloc"] = Dataset(datasets["tronloc"], private=True)
    with pytest.raises(ValueError, match="privés"):
        gen_carte(macarte, tmp_path / "a", datasets=datasets, wheel_path=wheel, standalone=False)


def test_pages_refuse_cle_api(tmp_path, wheel, datasets):
    with pytest.raises(ValueError, match="clé d'API"):
        gen_carte(
            macarte_cle,
            tmp_path / "a",
            datasets=datasets,
            wheel_path=wheel,
            standalone=False,
            tile_provider_api_key="secret",
        )


def test_cle_injectee_seulement_si_utilisee(tmp_path, wheel, datasets, monkeypatch):
    monkeypatch.setenv("CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY", "secret-env")
    sans = gen_carte(macarte_sans_cle, tmp_path / "s", datasets=datasets, wheel_path=wheel)
    assert "secret-env" not in sans.read_text(encoding="utf-8")
    avec = gen_carte(macarte_cle, tmp_path / "c", datasets=datasets, wheel_path=wheel)
    assert "tile_provider_api_key = 'secret-env'" in avec.read_text(encoding="utf-8")


def macarte_sans_cle(xl, tronloc):
    return None


def test_wheel_requis(tmp_path, datasets):
    with pytest.raises(ValueError, match="wheel_path"):
        gen_carte(macarte, tmp_path / "a", datasets=datasets)
