"""Construit tous les exemples de cartes du répertoire.

Exécute chaque script d'exemple (qui génère une page HTML dans output/) comme
un sous-processus indépendant, afin d'isoler d'éventuelles erreurs.

Usage :
    python build_all_examples.py
"""

import subprocess
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent

# Scripts qui construisent une carte (les utilitaires playwright/gif sont exclus).
EXAMPLE_SCRIPTS = [
    "exemple_simple.py",
    "example_carte_une_couche.py",
    "example_gares.py",
    "villes.py",
]


def main() -> int:
    failures: list[str] = []
    for script_name in EXAMPLE_SCRIPTS:
        script_path = EXAMPLES_DIR / script_name
        print(f"=== {script_name} ===")
        result = subprocess.run([sys.executable, str(script_path)], check=False, cwd=EXAMPLES_DIR)
        if result.returncode != 0:
            failures.append(script_name)

    if failures:
        print(f"\nÉchec pour : {', '.join(failures)}")
        return 1

    print(f"\nTous les exemples ont été construits avec succès ({len(EXAMPLE_SCRIPTS)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
