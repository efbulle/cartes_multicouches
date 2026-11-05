# Changelog

Toutes les modifications notables de ce projet sont documentees dans ce fichier.

Le format suit Keep a Changelog et SemVer.

## [0.4.0] - 2026-11-05

### Changed

- La CLI du skill (`xlsx_vers_carte.py`) réutilise `cartes_builder.spec` : un seul format de spec JSON pour les agents, la CLI et les pages du builder (#38).
- Les erreurs de spec sont des `SpecError`, affichées sans traceback par la CLI.

### Added

- CLI : `export-spec` (spec au format commun) et `import-spec` (configuration exportée par une page), référentiels nommés, légende et attribution déclaratives.
- Tests de non-régression de la CLI.

## [0.3.1] - 2026-10-30

### Added

- Configuration JSON multi-couches, multi-fichiers et multi-référentiels dans le builder (#32).

## [0.3.0] - 2026-09-08

### Added

- Release initiale du projet en l'etat actuel.
- API publique pour construire des cartes Bokeh interactives multi-couches a partir de GeoDataFrame.
- Exemples, tests automatises, documentation et fichiers de packaging pour la distribution Python.

### Infrastructure

- Licence MIT.
- Configuration CI (lint, tests, build) pour la validation continue.
