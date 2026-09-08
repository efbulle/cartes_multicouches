from pathlib import Path

import platformdirs
import requests

PACKAGE_NAME = "cartes_multicouches"

# Dictionnaire regroupant vos URLs d'exemples pré-configurées
DATASETS_SNCF = {
    # 1. Tracés des lignes du Réseau Ferré National (RFN)
    "lignes_rfn": {
        "filename": "formes_lignes_rfn.geojson",
        "url": (
            "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/"
            "formes-des-lignes-du-rfn/exports/geojson"
        ),
    },
    # 2. Emplacements des gares de voyageurs
    "gares_voyageurs": {
        "filename": "gares_de_voyageurs.geojson",
        "url": (
            "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/"
            "gares-de-voyageurs/exports/geojson"
        ),
    },
}


def get_cache_dir() -> Path:
    """Retourne le chemin du dossier de cache local."""
    cache_dir = Path(platformdirs.user_cache_dir(PACKAGE_NAME))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def load_data_from_url(url: str, filename: str, force_reload: bool = False) -> Path:
    """Télécharge une ressource web vers le cache local si non présente."""
    cache_path = get_cache_dir() / filename

    if cache_path.exists() and not force_reload:
        print(f"[Cache] Fichier chargé depuis le cache : {cache_path}")
        return cache_path

    print(f"[Téléchargement] Récupération de : {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(cache_path, "wb") as f:
            f.writelines(response.iter_content(chunk_size=8192))

        print(f"[Cache] Sauvegardé sous : {cache_path}")
        return cache_path

    except requests.RequestException as e:
        if not cache_path.exists():
            # ✅ 'from e' pour satisfaire les regles de linting (B904)
            raise RuntimeError(
                f"Échec du téléchargement et aucun cache local pour '{filename}'."
            ) from e

        print("[Avertissement] Téléchargement échoué, utilisation de la version en cache.")
        return cache_path


def load_example(dataset_key: str, force_reload: bool = False) -> Path:
    """Fonction utilitaire pour charger facilement un exemple par son nom."""
    if dataset_key not in DATASETS_SNCF:
        raise ValueError(
            f"Jeu de données '{dataset_key}' inconnu. Choix possibles : "
            f"{list(DATASETS_SNCF.keys())}"
        )

    dataset_info = DATASETS_SNCF[dataset_key]
    return load_data_from_url(
        url=dataset_info["url"],
        filename=dataset_info["filename"],
        force_reload=force_reload,
    )
