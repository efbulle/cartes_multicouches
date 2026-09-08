import os
import tomllib
from pathlib import Path
from typing import Any


def load_personal_config() -> dict[str, Any]:
    """Charge la configuration : valeurs de pyproject.toml, surchargées par la
    configuration personnelle si elle existe."""

    config: dict[str, Any] = _load_pyproject_config()
    config.update(_load_appdata_config())
    return config


def _load_pyproject_config(start: Path | None = None) -> dict[str, Any]:
    """Cherche [tool.cartes_multicouches] dans le pyproject.toml du projet."""

    root = (start or Path(__file__)).resolve()
    if root.is_file():
        root = root.parent

    for parent in [root, *root.parents]:
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.is_file():
            with pyproject_path.open("rb") as pyproject_file:
                data = tomllib.load(pyproject_file)
            tool_section = data.get("tool", {})
            if not isinstance(tool_section, dict):
                return {}
            cartes_section = tool_section.get("cartes_multicouches", {})
            return cartes_section if isinstance(cartes_section, dict) else {}
    return {}


def _load_appdata_config() -> dict[str, Any]:
    """Charge la configuration personnelle dans APPDATA, ou {} si absente."""

    appdata = os.getenv("APPDATA")
    if not appdata:
        return {}

    config_path = Path(appdata) / "cartes_multicouches" / "config.toml"
    if not config_path.is_file():
        return {}

    with config_path.open("rb") as config_file:
        return tomllib.load(config_file)
