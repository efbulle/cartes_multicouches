"""Génération de pages HTML PyScript qui construisent des cartes cartes_multicouches.

Une page générée contient un sélecteur de fichier Excel, des sélecteurs de
paramètres et une fonction `mafunc` (extraite du code Python de l'appelant)
qui produit la carte dans le navigateur.

Deux modes de livraison :

- `standalone=True` : wheel de cartes_multicouches et jeux de données sont
  embarqués en base64 dans le HTML (un seul fichier, utilisable hors ligne
  hormis les CDN) ;
- `standalone=False` : le HTML est léger et charge le wheel et les jeux de
  données par `pyfetch` depuis un dossier d'assets (GitHub Pages). Ce mode
  refuse les jeux de données privés et les clés d'API.
"""

import ast
import base64
import gzip
import hashlib
import html
import inspect
import json
import os
import subprocess
import tomllib
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version as pkg_version
from pathlib import Path
from textwrap import dedent
from typing import Literal

import geopandas as gpd
import pandas as pd
import shapely
from jinja2 import Environment, PackageLoader, StrictUndefined

PYSCRIPT_VERSION = "2026.7.3"
TILE_API_KEY_ENV = "CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY"
BUILTIN_GEOLOC = Path(__file__).with_name("geoloc.py")

# Variables globales toujours définies dans la page, en plus des jeux de données.
BASE_TEMPLATE_GLOBALS = frozenset({"attribution_config", "tile_provider_api_key"})

_GEO_SUFFIXES = {".geojson", ".gpkg", ".shp", ".json"}


@dataclass(frozen=True)
class Dataset:
    """Jeu de données injecté dans la page sous le nom de sa clé dans `datasets`.

    Args:
        path: fichier source (parquet, geojson, gpkg, csv...).
        kind: "geo" (GeoDataFrame), "table" (DataFrame) ou "auto" (selon le
            fichier ; un parquet avec métadonnées géographiques est "geo").
        cols: colonnes conservées (la géométrie l'est toujours pour "geo").
        private: si True, le jeu ne peut pas être publié (`standalone=False`).
        crs: CRS EPSG des jeux "geo" dans la page (3857 par défaut).
        precision: grille d'arrondi des coordonnées (unités du CRS) pour
            alléger les jeux "geo" ; None pour ne pas arrondir.
    """

    path: Path
    kind: Literal["auto", "geo", "table"] = "auto"
    cols: Sequence[str] | None = None
    private: bool = False
    crs: int = 3857
    precision: float | None = 0.1


def find_wheel(repo_dir: Path | str) -> Path:
    """Retourne le wheel correspondant à la version du pyproject.toml.

    Recherche dans <repo>/dist. Lève FileNotFoundError si aucun wheel
    correspondant n'est trouvé.
    """
    repo_dir = Path(repo_dir)
    with (repo_dir / "pyproject.toml").open("rb") as f:
        pyproject = tomllib.load(f)

    package_name = pyproject["project"]["name"].replace("-", "_")
    version = pyproject["project"]["version"]
    dist_dir = repo_dir / "dist"
    matches = list(dist_dir.glob(f"{package_name}-{version}-*.whl"))

    if not matches:
        raise FileNotFoundError(
            f"Aucun wheel trouvé pour {package_name}=={version} dans {dist_dir}"
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"Plusieurs wheels trouvés pour {package_name}=={version}: "
            f"{', '.join(p.name for p in matches)}"
        )
    return matches[0]


def build_wheel(repo_dir: Path | str) -> Path:
    """Construit le wheel du dépôt avec `uv build` et retourne son chemin."""
    repo_dir = Path(repo_dir)
    subprocess.run(["uv", "build", "--wheel"], cwd=repo_dir, check=True)
    return find_wheel(repo_dir)


def _as_dataset(value: Dataset | Path | str) -> Dataset:
    return value if isinstance(value, Dataset) else Dataset(Path(value))


def _read_geo(ds: Dataset) -> gpd.GeoDataFrame:
    if ds.path.suffix.lower() == ".parquet":
        return gpd.read_parquet(ds.path)
    return gpd.read_file(ds.path)


def _encode_dataset(ds: Dataset) -> tuple[str, bytes]:
    """Sérialise un jeu de données en JSON gzippé. Retourne (kind, octets)."""
    kind = ds.kind
    if kind == "auto":
        suffix = ds.path.suffix.lower()
        if suffix in _GEO_SUFFIXES:
            kind = "geo"
        elif suffix == ".parquet":
            try:
                gpd.read_parquet(ds.path)
                kind = "geo"
            except ValueError:
                kind = "table"
        else:
            kind = "table"

    if kind == "geo":
        gdf = _read_geo(ds)
        if gdf.crs is None:
            raise ValueError(f"'{ds.path}' doit avoir un CRS défini.")
        gdf = gdf.to_crs(epsg=ds.crs)
        if ds.cols is not None:
            gdf = gdf[[*ds.cols, gdf.geometry.name]]
        if ds.precision is not None:
            gdf = gdf.set_geometry(shapely.set_precision(gdf.geometry.values, ds.precision))
        payload = gdf.to_json(drop_id=True, separators=(",", ":"))
    else:
        suffix = ds.path.suffix.lower()
        if suffix == ".parquet":
            df = pd.read_parquet(ds.path)
        elif suffix in {".xlsx", ".xls"}:
            df = pd.read_excel(ds.path)
        else:
            df = pd.read_csv(ds.path, encoding="utf-8-sig")
        if ds.cols is not None:
            df = df[list(ds.cols)]
        payload = df.to_json(orient="records", force_ascii=False)

    return kind, gzip.compress(payload.encode("utf-8"), mtime=0)


def _prepare_mafunc_source(mafunc, template_globals: frozenset[str] | set[str]) -> str:
    """Prépare le code source de mafunc pour l'injection dans le template.

    Renomme la fonction en 'mafunc' et retire de sa signature les paramètres
    finaux qui correspondent à des variables globales déjà définies dans la
    page (jeux de données, attribution_config, tile_provider_api_key), dans
    n'importe quel ordre — sans toucher au corps de la fonction.
    """
    source = dedent(inspect.getsource(mafunc))
    tree = ast.parse(source)
    func_def = tree.body[0]
    if not isinstance(func_def, ast.FunctionDef):
        raise TypeError(f"{mafunc!r} ne correspond pas à une simple définition de fonction.")

    args = func_def.args.args
    while args and args[-1].arg in template_globals:
        args.pop()

    func_def.name = "mafunc"
    func_def.decorator_list = []
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _selectors_html(select: Mapping[str, Literal["xl_sheetnames", "xl_cols"] | list[str]]) -> str:
    groups = []
    for nid, (key, val) in enumerate(select.items()):
        if isinstance(val, list):
            options = "".join(
                f'<option value="{html.escape(str(o))}">{html.escape(str(o))}</option>' for o in val
            )
            classe = ""
        elif val == "xl_sheetnames":
            options, classe = "", "sheetname"
        elif val == "xl_cols":
            options, classe = "", "xlcols"
        else:
            raise ValueError(f"valeur non reconnue pour selecteur : {val}")
        title = html.escape(key)
        groups.append(
            '<div class="selecteur-group">'
            f'<label class="selecteur" for="sel_{nid}">{title}</label>'
            f'<select class="selecteur {classe}" id="sel_{nid}" title="{title}">'
            f"{options}</select></div>"
        )
    return "\n".join(groups)


def _json_for_script(obj) -> str:
    """JSON insérable dans une balise <script> (neutralise '</')."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _write_asset(assets_dir: Path, stem: str, suffix: str, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()[:10]
    name = f"{stem}.{digest}{suffix}"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / name).write_bytes(data)
    return name


def gen_carte(
    mafunc,
    filepath: Path | str = Path("output/gen_cartes.html"),
    *,
    datasets: Mapping[str, Dataset | Path | str] | None = None,
    select: Mapping[str, Literal["xl_sheetnames", "xl_cols"] | list[str]] | None = None,
    geoloc_modules: Sequence[Path | str] | None = None,
    standalone: bool = True,
    wheel_path: Path | str | None = None,
    repo_dir: Path | str | None = None,
    attribution_config: Mapping | None = None,
    tile_provider_api_key: str | None = None,
    assets_dir: Path | str | None = None,
    title: str = "Générateur de cartes",
    zip: bool = False,
    bokeh_version: str | None = None,
    xyzservices_version: str | None = None,
    pyscript_version: str = PYSCRIPT_VERSION,
) -> Path:
    """Génère une page HTML PyScript qui construit une carte à partir d'un Excel.

    Args:
        mafunc: fonction `(xl, *valeurs_des_selecteurs, <globales>) -> CarteDynMulti`.
            Les paramètres finaux nommés comme une clé de `datasets`,
            `attribution_config` ou `tile_provider_api_key` sont fournis par la page.
        filepath: fichier HTML produit (suffixe forcé à .html).
        datasets: jeux de données accessibles dans `mafunc` sous le nom de leur clé.
        select: sélecteurs de paramètres (un par argument de `mafunc` après `xl`).
        geoloc_modules: fichiers Python injectés dans la page (fonctions utilisables
            par `mafunc`, ex. `ajoute_geo`). Par défaut : `cartes_builder.geoloc`.
        standalone: True pour embarquer wheel et données, False pour les charger
            depuis `assets_dir` (refuse jeux privés et clé d'API).
        wheel_path / repo_dir: wheel de cartes_multicouches, ou dépôt où le chercher.
        attribution_config: arguments de `AttributionConfig` (défaut : valeurs par défaut).
        tile_provider_api_key: clé des tuiles ; sinon variable d'environnement
            `CARTES_MULTICOUCHES_TILE_PROVIDER_API_KEY`. Injectée seulement si
            `mafunc` l'utilise.
        assets_dir: dossier des assets en mode non autonome (défaut : `<dossier du html>/assets`).

    Returns:
        Le chemin du fichier HTML écrit.
    """
    datasets = {name: _as_dataset(ds) for name, ds in (datasets or {}).items()}
    template_globals = BASE_TEMPLATE_GLOBALS | set(datasets)
    filepath = Path(filepath).with_suffix(".html")

    if wheel_path is None:
        if repo_dir is None:
            raise ValueError("Indiquer `wheel_path` ou `repo_dir` (dépôt de cartes_multicouches).")
        wheel_path = find_wheel(Path(repo_dir))
    wheel_path = Path(wheel_path)

    mafunc_sig = inspect.signature(mafunc)
    mafunc_tree = ast.parse(dedent(inspect.getsource(mafunc)))
    uses_api_key = "tile_provider_api_key" in mafunc_sig.parameters or any(
        isinstance(node, ast.Name) and node.id == "tile_provider_api_key"
        for node in ast.walk(mafunc_tree)
    )
    api_key = None
    if uses_api_key:
        api_key = tile_provider_api_key or os.environ.get(TILE_API_KEY_ENV) or None

    if not standalone:
        private = sorted(name for name, ds in datasets.items() if ds.private)
        if private:
            raise ValueError(
                f"Jeux de données privés refusés avec standalone=False : {', '.join(private)}."
            )
        if api_key:
            raise ValueError(
                "Une clé d'API de tuiles serait publiée en clair : utiliser standalone=True "
                "ou un fournisseur de tuiles sans clé."
            )

    mafunc_code = _prepare_mafunc_source(mafunc, template_globals)
    modules = [
        Path(m) for m in (geoloc_modules if geoloc_modules is not None else [BUILTIN_GEOLOC])
    ]
    modules_code = "\n\n".join(m.read_text(encoding="utf-8") for m in modules)
    if any("</script" in block.lower() for block in (mafunc_code, modules_code)):
        raise ValueError("Le code Python injecté ne doit pas contenir '</script'.")

    wheel_bytes = wheel_path.read_bytes()
    if standalone:
        manifest: dict = {
            "wheel": {
                "name": wheel_path.name,
                "b64": base64.b64encode(wheel_bytes).decode("ascii"),
            },
            "datasets": {},
        }
    else:
        assets = Path(assets_dir) if assets_dir is not None else filepath.parent / "assets"
        rel = Path(os.path.relpath(assets, filepath.parent)).as_posix()
        manifest = {
            "wheel": {"name": wheel_path.name, "url": f"{rel}/{wheel_path.name}"},
            "datasets": {},
        }
        assets.mkdir(parents=True, exist_ok=True)
        (assets / wheel_path.name).write_bytes(wheel_bytes)

    for name, ds in datasets.items():
        kind, data = _encode_dataset(ds)
        entry: dict = {"kind": kind, "crs": ds.crs}
        if standalone:
            entry["b64"] = base64.b64encode(data).decode("ascii")
        else:
            entry["url"] = f"{rel}/{_write_asset(assets, name, '.json.gz', data)}"
        manifest["datasets"][name] = entry

    env = Environment(
        loader=PackageLoader("cartes_builder", "templates"),
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        comment_start_string="{##",
        comment_end_string="##}",
    )
    page = env.get_template("template.html.j2").render(
        title=html.escape(title),
        pyscript_version=pyscript_version,
        bokeh_version=bokeh_version or pkg_version("bokeh"),
        xyzservices_version=xyzservices_version or pkg_version("xyzservices"),
        selecteurs=_selectors_html(select or {}),
        manifest_json=_json_for_script(manifest),
        attribution_json=_json_for_script(dict(attribution_config or {})),
        api_key_literal=repr(api_key),
        mafunc_code=mafunc_code,
        modules_code=modules_code,
    )

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(page, encoding="utf-8")

    if zip:
        with zipfile.ZipFile(filepath.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(filepath, filepath.name)
    return filepath
