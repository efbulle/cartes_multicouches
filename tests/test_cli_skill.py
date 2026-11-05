"""Non-régression de la CLI du skill (xlsx_vers_carte.py) sur le format de spec commun."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

CLI = (
    Path(__file__).resolve().parent.parent
    / ".agents"
    / "skills"
    / "cartes-multicouches"
    / "scripts"
    / "xlsx_vers_carte.py"
)


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("xlsx_vers_carte", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def donnees(tmp_path):
    csv = tmp_path / "villes.csv"
    pd.DataFrame(
        {
            "nom": ["A", "B", "C"],
            "cat": ["x", "x", "y"],
            "lat": ["48,85", "45.76", "43.30"],
            "lon": [2.35, 4.83, 5.37],
        }
    ).to_csv(csv, index=False)
    return csv


def _ecrire(chemin: Path, spec: dict) -> str:
    chemin.write_text(json.dumps(spec), encoding="utf-8")
    return str(chemin)


def test_build_une_couche(cli, donnees, tmp_path, capsys):
    sortie = tmp_path / "out" / "carte.html"
    spec = _ecrire(
        tmp_path / "spec.json",
        {
            "fichier": str(donnees),
            "geometrie": {"lat": "lat", "lon": "lon"},
            "nom_couche": "Villes",
            "couleur": "cat",
            "tooltips": ["nom"],
            "filtres": ["cat"],
            "titre": "Ma carte",
            "sortie": str(sortie),
        },
    )
    cli.main(["build", spec])
    rapport = json.loads(capsys.readouterr().out)
    assert rapport["verification"] == "ok"
    assert rapport["lignes_cartographiees"] == 3
    assert rapport["couches"][0]["couches"] == ["Villes"]
    assert sortie.exists()


def test_build_multicouches_et_legende(cli, donnees, tmp_path, capsys):
    sortie = tmp_path / "carte.html"
    spec = _ecrire(
        tmp_path / "spec.json",
        {
            "titre": "Multi",
            "sortie": str(sortie),
            "filtres": ["cat"],
            "legende": {"entrees": [{"libelle": "Ville", "couleur": "#1f77b4"}]},
            "couches": [
                {
                    "fichier": str(donnees),
                    "geometrie": {"lat": "lat", "lon": "lon"},
                    "nom_couche": "L1",
                },
                {
                    "fichier": str(donnees),
                    "geometrie": {"lat": "lat", "lon": "lon"},
                    "nom_couche": "L2",
                },
            ],
        },
    )
    cli.main(["build", spec])
    rapport = json.loads(capsys.readouterr().out)
    assert [r["couches"] for r in rapport["couches"]] == [["L1"], ["L2"]]
    assert rapport["lignes_cartographiees"] == 6


def test_erreurs_de_spec_sans_traceback(cli, donnees, tmp_path):
    spec = _ecrire(
        tmp_path / "spec.json",
        {"fichier": str(donnees), "geometrie": {"lat": "absente", "lon": "lon"}},
    )
    with pytest.raises(SystemExit) as exc:
        cli.main(["build", spec])
    assert "Colonne absente" in str(exc.value)

    doublons = _ecrire(
        tmp_path / "doublons.json",
        {
            "couches": [
                {"fichier": str(donnees), "geometrie": {"lat": "lat", "lon": "lon"}},
                {"fichier": str(donnees), "geometrie": {"lat": "lat", "lon": "lon"}},
            ]
        },
    )
    with pytest.raises(SystemExit) as exc:
        cli.main(["build", doublons])
    assert "double" in str(exc.value)

    sans_fichier = _ecrire(tmp_path / "nofile.json", {"geometrie": {"lat": "lat", "lon": "lon"}})
    with pytest.raises(SystemExit) as exc:
        cli.main(["build", sans_fichier])
    assert "fichier" in str(exc.value)


def test_export_ancienne_forme_referentiel(cli, tmp_path, capsys):
    ancienne = {
        "fichier": "donnees.csv",
        "geometrie": {
            "pk": {
                "ligne": "l",
                "pk_debut": "d",
                "referentiel": "ref.parquet",
                "referentiel_colonnes": {"ligne": "cl", "pk_debut": "a", "pk_fin": "b"},
                "referentiel_unite_pk": "m",
            }
        },
    }
    sortie = tmp_path / "config.json"
    cli.main(["export-spec", _ecrire(tmp_path / "spec.json", ancienne), "--sortie", str(sortie)])
    commun = json.loads(sortie.read_text(encoding="utf-8"))
    assert commun["referentiels"] == {
        "referentiel_1": {
            "donnees": "ref.parquet",
            "colonnes": {"ligne": "cl", "pk_debut": "a", "pk_fin": "b"},
            "unite_pk": "m",
        }
    }
    assert commun["geometrie"]["pk"] == {
        "ligne": "l",
        "pk_debut": "d",
        "referentiel": "referentiel_1",
    }
    # idempotent : le format commun est retourné à l'identique
    sortie2 = tmp_path / "config2.json"
    cli.main(["export-spec", str(sortie), "--sortie", str(sortie2)])
    assert json.loads(sortie2.read_text(encoding="utf-8")) == commun


def test_export_referentiel_public_par_defaut(cli, tmp_path, capsys):
    spec = {"fichier": "d.csv", "geometrie": {"pk": {"ligne": "l", "pk_debut": "d"}}}
    cli.main(["export-spec", _ecrire(tmp_path / "s.json", spec)])
    commun = json.loads(capsys.readouterr().out)
    assert commun["referentiels"]["rfn"]["donnees"] == "rfn"
    assert commun["referentiels"]["rfn"]["colonnes"]["ligne"] == "code_ligne"


def test_import_spec_associe_les_fichiers(cli, donnees, tmp_path, capsys):
    config = {
        "version": 1,
        "titre": "Page",
        "sortie": str(tmp_path / "page.html"),
        "couches": [
            {"fichier": "principal", "geometrie": {"lat": "lat", "lon": "lon"}, "nom_couche": "P"}
        ],
    }
    sortie = tmp_path / "spec.json"
    cli.main(
        [
            "import-spec",
            _ecrire(tmp_path / "config.json", config),
            "--principal",
            str(donnees),
            "--sortie",
            str(sortie),
        ]
    )
    assert json.loads(sortie.read_text(encoding="utf-8"))["couches"][0]["fichier"] == str(donnees)
    capsys.readouterr()
    cli.main(["build", str(sortie)])
    assert json.loads(capsys.readouterr().out)["verification"] == "ok"


def test_import_spec_donnees_invalide(cli, tmp_path):
    config = _ecrire(tmp_path / "c.json", {"fichier": "principal", "geometrie": {}})
    with pytest.raises(SystemExit) as exc:
        cli.main(["import-spec", config, "--donnees", "pas_de_egal"])
    assert "NOM=FICHIER" in str(exc.value)
