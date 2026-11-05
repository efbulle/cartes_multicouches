#!/usr/bin/env python3
"""Construit une carte HTML cartes_multicouches à partir d'un Excel/CSV.

Sous-commandes :
  doctor                           diagnostique l'environnement (aucune dépendance requise)
  inspect FICHIER [--feuille NOM]  décrit le fichier (feuilles, colonnes, extrait)
  init-spec FICHIER [--feuille NOM] [--sortie spec.json]
                                   propose un brouillon de spec d'après les colonnes
  build SPEC.json                  construit la carte décrite par la spec, puis la vérifie
  export-spec SPEC.json [--sortie config.json]
                                   convertit une spec au format commun (celui du bouton
                                   « Configuration » des pages cartes_builder) : à charger
                                   dans une page, ou à relire telle quelle
  import-spec CONFIG.json [--principal FICHIER] [--donnees NOM=FICHIER ...] [--sortie spec.json]
                                   reprend une configuration exportée par une page : associe
                                   "principal" et les fichiers complémentaires à des chemins
  verify CARTE.html [--couche NOM ...] [--titre T]
                                   contrôle statique du HTML produit

Le format de spec est celui de cartes_builder.spec (voir l'en-tête de ce module, la doc
builder/README.md et le bouton « Configuration » des pages générées) : un seul format
pour les agents, la CLI et le builder. La CLI y ajoute :
  sortie       chemin du HTML                                 (défaut : carte.html)
  fichier      chemin du .xlsx / .csv de la couche (dans une page : "principal" ou un nom)

Résumé des clés (une couche, ou "couches": [ {...}, {...} ] pour plusieurs) :
  fichier      chemin du .xlsx / .csv                         (obligatoire)
  feuille      nom ou numéro de feuille (Excel)               (défaut : première)
  geometrie    voir ci-dessous                                (obligatoire)
  nom_couche   libellé de la couche, unique                   (défaut : "Données")
  couleur      nom de colonne (couleurs par catégorie) ou couleur fixe (défaut : "navy")
  taille       taille des points / épaisseur des lignes       (défaut : 5)
  tooltips     liste de colonnes affichées au survol          (défaut : 6 premières)
  colonnes_tableau  colonnes du tableau lié                   (défaut : toutes)
  filtres      liste de colonnes -> sélecteurs multiples      (défaut : aucun)
  Premier niveau : titre, fond_de_carte ("EsriGrayCanvas" par défaut, sans clé API), sortie,
  filtres (globaux), referentiels, legende, attribution.

geometrie :
  {"lat": "colonne", "lon": "colonne"}                        -> points
  {"lat_debut": ..., "lon_debut": ..., "lat_fin": ..., "lon_fin": ...}  -> lignes droites
  {"crs": "EPSG:2154"}  optionnel : CRS des coordonnées (défaut EPSG:4326)
  {"pk": {"ligne": "colonne", "pk_debut": "colonne", "pk_fin": "colonne", "unite_pk": "km"}}
        -> lignes (pk_fin présent) ou points (pk_fin absent ou vide) placés par PK sur un référentiel.
        "unite_pk" : "km" (défaut) ou "m", unité des PK du fichier.
        Référentiel : par défaut le réseau ferré national public (clé code_ligne, PK en km).
        Référentiel propre, format commun : au premier niveau
          "referentiels": {"rfn": {"donnees": "tronloc.parquet",
                                   "colonnes": {"ligne": ..., "pk_debut": ..., "pk_fin": ...},
                                   "unite_pk": "km"}}
        puis "referentiel": "rfn" dans pk (facultatif s'il n'y en a qu'un). "donnees" est un
        chemin .parquet/.geojson/.gpkg, ou "rfn" pour le référentiel public.
        Ancienne forme, toujours acceptée : "referentiel": "fichier.parquet",
        "referentiel_colonnes": {...} et "referentiel_unite_pk" directement dans pk.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import importlib.metadata
import json
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path

EXT_TEXTE = {".csv", ".tsv", ".txt"}
EXT_EXCEL = {".xlsx", ".xlsm", ".xls"}
MAX_MODALITES = 20  # au-delà, une colonne n'est pas proposée comme catégorie
REF_PUBLIC = "rfn"  # nom du jeu de données « référentiel public » dans une spec


# --------------------------------------------------------------------------- lecture


def _lire(fichier: str, feuille=None):
    import pandas as pd

    chemin = Path(fichier)
    if not chemin.exists():
        sys.exit(f"Erreur : fichier introuvable : {chemin}")
    if chemin.suffix.lower() in EXT_TEXTE:
        sep = "\t" if chemin.suffix.lower() == ".tsv" else None
        return pd.read_csv(chemin, sep=sep, engine="python")
    if feuille is None:
        feuille = 0
    elif isinstance(feuille, str) and feuille.isdigit():
        feuille = int(feuille)
    return pd.read_excel(chemin, sheet_name=feuille)


def _detecter(df) -> dict:
    """Repère les colonnes de coordonnées d'après leur nom."""
    noms = {c: str(c).strip().lower() for c in df.columns}

    def est_lat(n):
        return n.startswith(("lat", "y_")) or n == "y"

    def est_lon(n):
        return n.startswith(("lon", "lng", "x_")) or n == "x"

    def est_debut(n):
        return any(k in n for k in ("deb", "start", "orig"))

    def est_fin(n):
        return any(k in n for k in ("fin", "end", "dest"))

    lats = [c for c, n in noms.items() if est_lat(n)]
    lons = [c for c, n in noms.items() if est_lon(n)]
    pk = [c for c, n in noms.items() if n.startswith("pk")]

    geometrie = None
    la_d = [c for c in lats if est_debut(noms[c])]
    la_f = [c for c in lats if est_fin(noms[c])]
    lo_d = [c for c in lons if est_debut(noms[c])]
    lo_f = [c for c in lons if est_fin(noms[c])]
    if len(la_d) == len(la_f) == len(lo_d) == len(lo_f) == 1:
        geometrie = {
            "lat_debut": la_d[0],
            "lon_debut": lo_d[0],
            "lat_fin": la_f[0],
            "lon_fin": lo_f[0],
        }
    elif len(lats) == 1 and len(lons) == 1:
        geometrie = {"lat": lats[0], "lon": lons[0]}
    return {"lat": lats, "lon": lons, "pk": pk, "geometrie": geometrie}


def _colonnes_categorielles(df, exclure) -> list:
    import pandas as pd

    out = []
    for c in df.columns:
        if c in exclure:
            continue
        s = df[c].dropna()
        if s.empty or pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        n = s.nunique()
        # une colonne dont toutes les valeurs sont distinctes est un identifiant, pas une catégorie
        if 2 <= n <= MAX_MODALITES and n < len(df):
            out.append(c)
    return out


# --------------------------------------------------------------------------- doctor


def _joignable(url: str) -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=5)
        return True
    except Exception:  # noqa: BLE001 - diagnostic : toute erreur réseau compte comme échec
        return False


def cmd_doctor(args) -> None:
    def ligne(ok: bool, msg: str, detail: str = "") -> None:
        print(f"{'OK    ' if ok else 'ECHEC '} {msg}" + (f" — {detail}" if detail else ""))

    v = sys.version_info
    py_ok = v >= (3, 13)
    ligne(py_ok, f"Python {v.major}.{v.minor}.{v.micro}", "" if py_ok else "3.13 minimum requis")

    uv = shutil.which("uv")
    ligne(bool(uv), "uv", uv or "absent (essayer : pip install uv)")

    paquets_ok = True
    for module, dist in [
        ("pandas", "pandas"),
        ("openpyxl", "openpyxl"),
        ("geopandas", "geopandas"),
        ("polars", "polars"),
        ("pyarrow", "pyarrow"),
        ("cartes_multicouches", "cartes-multicouches"),
        ("cartes_builder", "cartes-multicouches-builder"),
    ]:
        try:
            importlib.import_module(module)
            ligne(True, f"paquet {dist}", importlib.metadata.version(dist))
        except Exception as exc:  # noqa: BLE001
            paquets_ok = False
            ligne(False, f"paquet {dist}", type(exc).__name__)

    for nom, url in [("github.com", "https://github.com"), ("pypi.org", "https://pypi.org")]:
        ligne(_joignable(url), f"réseau {nom}")

    pret = py_ok and paquets_ok
    print()
    if pret:
        print("Verdict : environnement courant prêt, lancer le script directement avec python.")
    elif uv:
        print(
            "Verdict : utiliser uv (voir SKILL.md, commande CMD) ; il fournit Python 3.13 "
            "et installe les paquets manquants, à condition que le réseau soit joignable."
        )
    else:
        print(
            "Verdict : ni environnement prêt ni uv. Installer uv, sinon renvoyer vers le constructeur en ligne."
        )
        sys.exit(1)


# --------------------------------------------------------------------------- inspect


def cmd_inspect(args) -> None:
    import pandas as pd

    chemin = Path(args.fichier)
    if chemin.suffix.lower() in EXT_EXCEL:
        print(f"Feuilles : {pd.ExcelFile(chemin).sheet_names}")
    df = _lire(args.fichier, args.feuille)
    print(f"Dimensions : {df.shape[0]} lignes x {df.shape[1]} colonnes\n")
    print("Colonnes (type, valeurs manquantes, exemples) :")
    for col in df.columns:
        exemples = df[col].dropna().unique()[:3].tolist()
        print(f"  - {col!r}: {df[col].dtype}, {int(df[col].isna().sum())} NA, ex. {exemples}")
    det = _detecter(df)
    print(f"\nCandidats latitude : {det['lat'] or 'aucun'}")
    print(f"Candidats longitude : {det['lon'] or 'aucun'}")
    print(f"Candidats PK : {det['pk'] or 'aucun'}")
    for c in det["lat"] + det["lon"]:
        if not pd.api.types.is_numeric_dtype(df[c]):
            print(f"Attention : {c!r} n'est pas numérique (virgule décimale ? texte ?)")


def _geometrie_pk(df, pks) -> dict | None:
    """Propose une géométrie par PK d'après les noms de colonnes (à confirmer avec l'utilisateur)."""
    if not pks:
        return None

    def norm(c):
        sans_accent = unicodedata.normalize("NFD", str(c).lower())
        return "".join(ch for ch in sans_accent if unicodedata.category(ch) != "Mn")

    ligne = [c for c in df.columns if "ligne" in norm(c)]
    deb = [c for c in pks if any(k in norm(c) for k in ("deb", "start", "pkd", "pkmd"))]
    fin = [c for c in pks if any(k in norm(c) for k in ("fin", "end", "pkf", "pkmf"))]
    if not deb and len(pks) == 1:
        deb = pks
    if not ligne or not deb:
        return None
    pk = {"ligne": ligne[0], "pk_debut": deb[0], "unite_pk": "A_CONFIRMER"}
    if fin:
        pk["pk_fin"] = fin[0]
    return {"pk": pk}


# --------------------------------------------------------------------------- init-spec


def cmd_init_spec(args) -> None:
    df = _lire(args.fichier, args.feuille)
    det = _detecter(df)
    geo = det["geometrie"]
    cols_geo = set(geo.values()) if geo else set()

    spec: dict = {"fichier": args.fichier}
    if args.feuille is not None:
        spec["feuille"] = args.feuille
    spec["geometrie"] = (
        geo or _geometrie_pk(df, det["pk"]) or {"lat": "A_REMPLIR", "lon": "A_REMPLIR"}
    )
    cols_geo = set(geo.values()) if geo else set()
    if "pk" in spec["geometrie"]:
        cols_geo = {v for k, v in spec["geometrie"]["pk"].items() if k != "unite_pk"}

    base = Path(args.fichier).stem
    spec["nom_couche"] = base
    cats = _colonnes_categorielles(df, cols_geo)
    spec["couleur"] = cats[0] if cats else "navy"
    spec["tooltips"] = [str(c) for c in df.columns if c not in cols_geo][:4]
    if cats:
        spec["filtres"] = [str(c) for c in cats[:3]]
    spec["titre"] = base
    spec["sortie"] = "carte.html"

    sortie = Path(args.sortie)
    sortie.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Brouillon écrit : {sortie}")
    print(json.dumps(spec, ensure_ascii=False, indent=2))
    if "pk" in spec["geometrie"]:
        print(
            "\nGéolocalisation par PK proposée : confirmer avec l'utilisateur les colonnes et "
            "l'unité des PK (remplacer 'A_CONFIRMER' par 'km' ou 'm')."
        )
    elif geo is None:
        print(
            "\nATTENTION : colonnes de coordonnées non identifiées (voir 'inspect'). "
            "Renseigner 'geometrie' ; si le fichier n'a ni latitude/longitude ni PK avec "
            "code ligne, le script ne peut pas le cartographier."
        )
    if det["pk"] and geo is None and "pk" not in spec["geometrie"]:
        print(
            f"Colonnes PK repérées : {det['pk']} (code ligne introuvable : demander à l'utilisateur)."
        )


# --------------------------------------------------------------------------- verify


def _verifier_html(chemin: Path, couches=(), titre: str | None = None) -> list[str]:
    """Contrôle statique du HTML ; retourne la liste des problèmes (vide si tout va bien)."""
    if not chemin.exists():
        return [f"fichier absent : {chemin}"]
    texte = chemin.read_text(encoding="utf-8", errors="replace")
    bas = texte.lower()
    problemes = []
    if len(texte) < 2000:
        problemes.append(f"fichier anormalement petit ({len(texte)} caractères)")
    if "<html" not in bas:
        problemes.append("balise <html> absente")
    if "bokeh" not in bas:
        problemes.append("aucune référence à Bokeh")

    def present(valeur: str) -> bool:
        formes = {valeur, json.dumps(valeur)[1:-1], json.dumps(valeur, ensure_ascii=False)[1:-1]}
        return any(f in texte for f in formes)

    for couche in couches:
        if not present(couche):
            problemes.append(f"couche introuvable dans le HTML : {couche!r}")
    if titre and not present(titre):
        problemes.append(f"titre introuvable dans le HTML : {titre!r}")
    return problemes


def cmd_verify(args) -> None:
    problemes = _verifier_html(Path(args.html), args.couche or [], args.titre)
    if problemes:
        print("Vérification : ECHEC")
        for p in problemes:
            print(f"  - {p}")
        sys.exit(1)
    print("Vérification : OK (contrôle statique ; l'affichage réel se juge dans un navigateur)")


# --------------------------------------------------------------------------- spec (format commun)

_EXT_REFERENTIEL = {".parquet", ".geojson", ".gpkg", ".json", ".shp"}


def _couches_de(spec: dict) -> list:
    return spec.get("couches", [spec])


def _est_ancien_referentiel(pk: dict) -> bool:
    """Ancienne forme : fichier de référentiel directement dans la géométrie PK."""
    ref = pk.get("referentiel")
    return "referentiel_colonnes" in pk or (
        isinstance(ref, str) and Path(ref).suffix.lower() in _EXT_REFERENTIEL
    )


def _vers_format_commun(spec: dict) -> dict:
    """Copie de la spec au format commun (referentiels nommés au premier niveau).

    Convertit l'ancienne forme de la CLI (référentiel dans `geometrie.pk`) et
    déclare le référentiel public quand une géométrie PK n'en nomme aucun.
    Une spec déjà au format commun est retournée à l'identique.
    """
    from cartes_builder.spec import SpecError

    if not isinstance(spec, dict):
        raise SpecError("La spec doit être un objet JSON.")
    spec = copy.deepcopy(spec)
    referentiels = spec.setdefault("referentiels", {})
    couches = _couches_de(spec)
    for couche in couches:
        geo = couche.get("geometrie") if isinstance(couche, dict) else None
        if not isinstance(geo, dict) or not isinstance(geo.get("pk"), dict):
            continue
        pk = geo["pk"]
        if _est_ancien_referentiel(pk):
            chemin = pk.pop("referentiel", None)
            if not chemin:
                raise SpecError(
                    "'referentiel_colonnes' sans 'referentiel' (fichier du référentiel)."
                )
            nom = next((n for n, d in referentiels.items() if d.get("donnees") == chemin), None)
            if nom is None:
                nom = f"referentiel_{len(referentiels) + 1}"
                referentiels[nom] = {
                    "donnees": chemin,
                    "colonnes": pk.pop("referentiel_colonnes", None) or {},
                    "unite_pk": pk.pop("referentiel_unite_pk", "km"),
                }
            pk.pop("referentiel_colonnes", None)
            pk.pop("referentiel_unite_pk", None)
            pk["referentiel"] = nom
        elif not referentiels:
            referentiels[REF_PUBLIC] = {
                "donnees": REF_PUBLIC,
                "colonnes": {"ligne": "code_ligne", "pk_debut": "pkmd", "pk_fin": "pkmf"},
                "unite_pk": "km",
            }
    if not referentiels:
        del spec["referentiels"]
    return spec


class _SourceCLI:
    """Données de la spec : le champ `fichier` de chaque couche est un chemin."""

    def feuille(self, nom=None, feuille=None):
        from cartes_builder.spec import SpecError

        if not nom:
            raise SpecError("Clé obligatoire manquante dans la spec : 'fichier'.")
        return _lire(nom, feuille)


def _charger_referentiel(donnees: str):
    """Référentiel d'après son jeu de données : chemin de fichier, ou référentiel public."""
    import geopandas as gpd
    from cartes_builder.spec import SpecError

    chemin = Path(donnees)
    if chemin.exists():
        ref = (
            gpd.read_parquet(chemin)
            if chemin.suffix.lower() == ".parquet"
            else gpd.read_file(chemin)
        )
    elif donnees == REF_PUBLIC:
        cache = Path(tempfile.gettempdir()) / "cartes_multicouches_referentiel_rfn.parquet"
        if not cache.exists():
            from cartes_builder.data import build_tronloc_file

            print("Téléchargement du référentiel public (une seule fois, environ une minute)...")
            build_tronloc_file(cache)
        ref = gpd.read_parquet(cache)
    else:
        raise SpecError(f"Référentiel introuvable : {chemin}")
    if ref.crs is None:
        raise SpecError("Le référentiel n'a pas de système de coordonnées (CRS).")
    return ref


def _lire_spec(chemin: str) -> dict:
    from cartes_builder.spec import SpecError

    p = Path(chemin)
    if not p.exists():
        raise SpecError(f"Spec introuvable : {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecError(f"Spec JSON invalide ({p}) : {exc}") from exc


def _ecrire_spec(spec: dict, sortie: str | None) -> None:
    texte = json.dumps(spec, ensure_ascii=False, indent=2)
    if sortie:
        Path(sortie).write_text(texte, encoding="utf-8")
        print(f"Spec écrite : {sortie}")
    else:
        print(texte)


def cmd_export_spec(args) -> None:
    _ecrire_spec(_vers_format_commun(_lire_spec(args.spec)), args.sortie)


def cmd_import_spec(args) -> None:
    """Associe les noms de fichiers d'une configuration de page à des chemins locaux."""
    from cartes_builder.spec import SpecError

    spec = _vers_format_commun(_lire_spec(args.config))
    chemins = {}
    if args.principal:
        chemins["principal"] = args.principal
    for item in args.donnees or []:
        nom, sep, chemin = item.partition("=")
        if not sep or not nom or not chemin:
            raise SpecError(f"--donnees attend NOM=FICHIER, reçu : {item!r}")
        chemins[nom] = chemin
    for couche in _couches_de(spec):
        nom = couche.get("fichier", "principal")
        if nom in chemins:
            couche["fichier"] = chemins[nom]
    for decl in (spec.get("referentiels") or {}).values():
        if decl.get("donnees") in chemins:
            decl["donnees"] = chemins[decl["donnees"]]
    manquants = sorted(
        {
            c.get("fichier", "principal")
            for c in _couches_de(spec)
            if not Path(c.get("fichier", "principal")).exists()
        }
    )
    _ecrire_spec(spec, args.sortie)
    if manquants:
        print(
            f"Fichiers à renseigner (--principal / --donnees NOM=FICHIER) : {manquants}",
            file=sys.stderr,
        )


# --------------------------------------------------------------------------- build


def cmd_build(args) -> None:
    from cartes_builder.spec import carte_from_spec, referentiels_depuis_spec

    spec = _vers_format_commun(_lire_spec(args.spec))
    referentiels = referentiels_depuis_spec(spec, _charger_referentiel)
    carte, rapport = carte_from_spec(spec, _SourceCLI(), referentiels)

    sortie = Path(spec.get("sortie", "carte.html"))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    carte.save(sortie)

    noms = [n for r in rapport["couches"] for n in r["couches"]]
    problemes = _verifier_html(sortie, noms, spec.get("titre", "Carte"))
    print(
        json.dumps(
            {
                "sortie": str(sortie.resolve()),
                "taille_octets": sortie.stat().st_size,
                "couches": rapport["couches"],
                "lignes_cartographiees": rapport["lignes_cartographiees"],
                "lignes_sans_coordonnees": rapport["lignes_sans_coordonnees"],
                "verification": "ok" if not problemes else problemes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if problemes:
        sys.exit(1)


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="diagnostiquer l'environnement").set_defaults(func=cmd_doctor)

    pi = sub.add_parser("inspect", help="décrire un fichier Excel/CSV")
    pi.add_argument("fichier")
    pi.add_argument("--feuille")
    pi.set_defaults(func=cmd_inspect)

    ps = sub.add_parser("init-spec", help="proposer un brouillon de spec")
    ps.add_argument("fichier")
    ps.add_argument("--feuille")
    ps.add_argument("--sortie", default="spec.json")
    ps.set_defaults(func=cmd_init_spec)

    pb = sub.add_parser("build", help="construire la carte depuis une spec JSON")
    pb.add_argument("spec")
    pb.set_defaults(func=cmd_build)

    pe = sub.add_parser("export-spec", help="convertir une spec au format commun (page builder)")
    pe.add_argument("spec")
    pe.add_argument("--sortie")
    pe.set_defaults(func=cmd_export_spec)

    pm = sub.add_parser("import-spec", help="reprendre une configuration exportée par une page")
    pm.add_argument("config")
    pm.add_argument("--principal", help="fichier de données correspondant à « principal »")
    pm.add_argument("--donnees", action="append", metavar="NOM=FICHIER")
    pm.add_argument("--sortie")
    pm.set_defaults(func=cmd_import_spec)

    pv = sub.add_parser("verify", help="contrôler un HTML produit")
    pv.add_argument("html")
    pv.add_argument("--couche", action="append")
    pv.add_argument("--titre")
    pv.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except ImportError as exc:
        if "cartes_builder" not in str(exc) and "cartes_multicouches" not in str(exc):
            raise
        sys.exit(f"Erreur : paquet manquant ({exc}) ; voir SKILL.md, commande CMD.")
    except Exception as exc:
        if type(exc).__name__ != "SpecError":
            raise
        sys.exit(f"Erreur : {exc}")


if __name__ == "__main__":
    main()
