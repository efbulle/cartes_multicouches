#!/usr/bin/env python3
"""Construit une carte HTML cartes_multicouches à partir d'un Excel/CSV.

Sous-commandes :
  doctor                           diagnostique l'environnement (aucune dépendance requise)
  inspect FICHIER [--feuille NOM]  décrit le fichier (feuilles, colonnes, extrait)
  init-spec FICHIER [--feuille NOM] [--sortie spec.json]
                                   propose un brouillon de spec d'après les colonnes
  build SPEC.json                  construit la carte décrite par la spec, puis la vérifie
  verify CARTE.html [--couche NOM ...] [--titre T]
                                   contrôle statique du HTML produit

Spec JSON (clés) :
Plusieurs couches : mettre "couches": [ {...}, {...} ] ; chaque couche porte ses propres
  fichier, feuille, geometrie, nom_couche (unique), couleur, taille, tooltips, colonnes_tableau
  et filtres (propres à la couche). Au premier niveau : titre, fond_de_carte, sortie, et
  filtres = filtres globaux, appliqués à toutes les couches qui possèdent la colonne.
  Sans "couches", la spec elle-même décrit l'unique couche, comme ci-dessous.

  fichier      chemin du .xlsx / .csv                         (obligatoire)
  feuille      nom ou numéro de feuille (Excel)               (défaut : première)
  geometrie    voir ci-dessous                                (obligatoire)
  nom_couche   libellé de la couche                           (défaut : "Données")
  couleur      nom de colonne (couleurs par catégorie) ou couleur fixe (défaut : "navy")
  taille       taille des points / épaisseur des lignes       (défaut : 5)
  tooltips     liste de colonnes affichées au survol          (défaut : 6 premières)
  colonnes_tableau  colonnes du tableau lié                   (défaut : toutes)
  filtres      liste de colonnes -> sélecteurs multiples      (défaut : aucun)
  titre        titre de la carte
  fond_de_carte  fournisseur de tuiles                        (défaut : "EsriGrayCanvas", sans clé API)
  sortie       chemin du HTML                                 (défaut : carte.html)

geometrie :
  {"lat": "colonne", "lon": "colonne"}                        -> points
  {"lat_debut": ..., "lon_debut": ..., "lat_fin": ..., "lon_fin": ...}  -> lignes droites
  {"crs": "EPSG:2154"}  optionnel : CRS des coordonnées (défaut EPSG:4326)
  {"pk": {"ligne": "colonne", "pk_debut": "colonne", "pk_fin": "colonne", "unite_pk": "km"}}
        -> lignes (pk_fin présent) ou points (pk_fin absent ou vide) placés par PK sur un référentiel.
        "unite_pk" : "km" (défaut) ou "m", unité des PK du fichier.
        Référentiel : par défaut le réseau ferré national public (clé code_ligne, PK en km).
        Référentiel propre : ajouter "referentiel": "fichier.parquet|.geojson|.gpkg",
        "referentiel_colonnes": {"ligne": ..., "pk_debut": ..., "pk_fin": ...} et
        "referentiel_unite_pk": "km" ou "m".
"""

from __future__ import annotations

import argparse
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


# --------------------------------------------------------------------------- build


def _referentiel(geo: dict):
    """Charge le référentiel de lignes : fichier fourni, sinon référentiel public SNCF (mis en cache)."""
    import geopandas as gpd

    unites = {"km": 1000.0, "m": 1.0}
    chemin = geo.get("referentiel")
    if chemin:
        p = Path(chemin)
        if not p.exists():
            sys.exit(f"Erreur : référentiel introuvable : {p}")
        ref = gpd.read_parquet(p) if p.suffix.lower() == ".parquet" else gpd.read_file(p)
        cols = geo.get("referentiel_colonnes") or {}
        cle, pkd, pkf = cols.get("ligne"), cols.get("pk_debut"), cols.get("pk_fin")
        if not (cle and pkd and pkf):
            sys.exit(
                "Erreur : 'referentiel_colonnes' doit donner 'ligne', 'pk_debut' et 'pk_fin' "
                f"(colonnes du référentiel : {list(ref.columns)})."
            )
        unite = geo.get("referentiel_unite_pk", "km")
    else:
        cache = Path(tempfile.gettempdir()) / "cartes_multicouches_referentiel_rfn.parquet"
        if cache.exists():
            ref = gpd.read_parquet(cache)
        else:
            from cartes_builder.data import build_tronloc_file

            print("Téléchargement du référentiel public (une seule fois, environ une minute)...")
            build_tronloc_file(cache)
            ref = gpd.read_parquet(cache)
        cle, pkd, pkf, unite = "code_ligne", "pkmd", "pkmf", "km"
    if unite not in unites:
        sys.exit("Erreur : l'unité des PK doit être 'km' ou 'm'.")
    if ref.crs is None:
        sys.exit("Erreur : le référentiel n'a pas de système de coordonnées (CRS).")
    return ref, cle, pkd, pkf, unites[unite]


def _geodataframe_pk(df, geo: dict):
    """Géolocalise des lignes décrites par code ligne + PK début (+ PK fin) via ajoute_geo."""
    import pandas as pd

    try:
        from cartes_builder import ajoute_geo
    except ImportError:
        sys.exit(
            "Erreur : le module de géolocalisation (cartes_builder) n'est pas installé (voir SKILL.md, CMD)."
        )

    pk = geo["pk"]
    ligne, deb = pk.get("ligne"), pk.get("pk_debut")
    fin = pk.get("pk_fin")
    for col in (ligne, deb):
        if not col or col not in df.columns:
            sys.exit(
                f"Erreur : colonne absente du fichier : {col!r}. Colonnes : {list(df.columns)}"
            )
    if fin and fin not in df.columns:
        sys.exit(f"Erreur : colonne absente du fichier : {fin!r}. Colonnes : {list(df.columns)}")

    unites = {"km": 1000.0, "m": 1.0}
    unite = pk.get("unite_pk", "km")
    if unite not in unites:
        sys.exit("Erreur : 'unite_pk' doit être 'km' ou 'm'.")

    ref, cle, ref_d, ref_f, ref_unite_m = _referentiel(pk)
    ref = ref.rename(columns={cle: ligne, ref_d: "pkmd", ref_f: "pkmf"})

    def _num(serie):
        if not pd.api.types.is_numeric_dtype(serie):
            serie = serie.astype(str).str.strip().str.replace(",", ".", regex=False)
        return pd.to_numeric(serie, errors="coerce")

    work = df.copy()
    work["_pkd"] = _num(work[deb]) * unites[unite] / ref_unite_m
    work["_pkf"] = _num(work[fin]) * unites[unite] / ref_unite_m if fin else float("nan")
    cle_num = _num(work[ligne])
    # le code ligne du référentiel est entier : on aligne le type quand c'est possible
    if pd.api.types.is_integer_dtype(ref[ligne]):
        work[ligne + "_jointure"] = cle_num.astype("Int64")
        ref[ligne + "_jointure"] = ref[ligne].astype("Int64")
    else:
        work[ligne + "_jointure"] = work[ligne].astype(str).str.strip()
        ref[ligne + "_jointure"] = ref[ligne].astype(str).str.strip()

    ok = work["_pkd"].notna() & work[ligne + "_jointure"].notna()
    if fin:  # un PK fin manquant ou inférieur au début n'est pas un tronçon valide
        ok &= work["_pkf"].isna() | (work["_pkf"] >= work["_pkd"])
    n_invalides = int((~ok).sum())
    sous = work[ok]
    if sous.empty:
        sys.exit("Erreur : aucune ligne n'a de code ligne et de PK exploitables.")

    gdf = ajoute_geo(
        sous[[ligne + "_jointure", "_pkd", "_pkf"]],
        ref,
        on=ligne + "_jointure",
        pk_lbls=("_pkd", "_pkf"),
        tronloc_pk_lbls=("pkmd", "pkmf"),
        pk_unit_m=ref_unite_m,
    )
    gdf = gdf[["geometry"]].join(df.loc[sous.index])
    trouve = ~gdf.geometry.isna() & ~gdf.geometry.is_empty
    n_non_trouvees = int((~trouve).sum())
    gdf = gdf[trouve].reset_index(drop=True)
    if gdf.empty:
        sys.exit(
            "Erreur : aucune ligne n'a pu être placée sur le référentiel "
            "(codes ligne ou unité des PK à vérifier)."
        )
    return gdf, n_invalides + n_non_trouvees


def _geodataframe(df, geo: dict):
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import LineString, Point

    if "pk" in geo:
        return _geodataframe_pk(df, geo)

    crs = geo.get("crs", "EPSG:4326")

    def _num(col):
        if col not in df.columns:
            sys.exit(
                f"Erreur : colonne absente du fichier : {col!r}. Colonnes : {list(df.columns)}"
            )
        serie = df[col]
        if not pd.api.types.is_numeric_dtype(serie):  # virgule décimale éventuelle
            serie = serie.astype(str).str.strip().str.replace(",", ".", regex=False)
        return pd.to_numeric(serie, errors="coerce")

    if {"lat", "lon"} <= geo.keys():
        lat, lon = _num(geo["lat"]), _num(geo["lon"])
        ok = lat.notna() & lon.notna()
        geom = [Point(x, y) if o else None for x, y, o in zip(lon, lat, ok)]
    elif {"lat_debut", "lon_debut", "lat_fin", "lon_fin"} <= geo.keys():
        la1, lo1 = _num(geo["lat_debut"]), _num(geo["lon_debut"])
        la2, lo2 = _num(geo["lat_fin"]), _num(geo["lon_fin"])
        ok = la1.notna() & lo1.notna() & la2.notna() & lo2.notna()
        geom = [
            LineString([(a, b), (c, d)]) if o else None
            for a, b, c, d, o in zip(lo1, la1, lo2, la2, ok)
        ]
    else:
        sys.exit(
            "Erreur : 'geometrie' doit contenir lat+lon (points) ou "
            "lat_debut+lon_debut+lat_fin+lon_fin (lignes)."
        )

    n_perdues = int((~ok).sum())
    gdf = gpd.GeoDataFrame(df.copy(), geometry=geom, crs=crs)
    gdf = gdf[ok].reset_index(drop=True)
    if gdf.empty:
        sys.exit("Erreur : aucune ligne n'a de coordonnées valides.")
    return gdf, n_perdues


def _couches_depuis_spec(spec: dict) -> tuple[list, dict]:
    """Construit les LayerConfig d'une couche de la spec (deux si points et lignes sont mêlés)."""
    from cartes_multicouches import LayerConfig, StyleConfig

    for cle in ("fichier", "geometrie"):
        if cle not in spec:
            sys.exit(f"Erreur : clé obligatoire manquante dans la spec : {cle!r}")

    df = _lire(spec["fichier"], spec.get("feuille"))
    gdf, n_perdues = _geodataframe(df, spec["geometrie"])

    for cle in ("filtres", "tooltips", "colonnes_tableau"):
        for col in spec.get(cle, []) or []:
            if col not in gdf.columns:
                sys.exit(
                    f"Erreur : colonne {col!r} (clé {cle!r}) absente. Colonnes : {list(gdf.columns)}"
                )

    nom = spec.get("nom_couche", "Données")
    tooltips = [(c, f"@{c}") for c in spec["tooltips"]] if spec.get("tooltips") else None
    est_point = gdf.geometry.geom_type.eq("Point")
    # une couche ne peut pas mélanger points et lignes (ex. PK ponctuels et tronçons)
    parties = (
        [(nom, gdf)]
        if est_point.all() or not est_point.any()
        else [
            (f"{nom} (tronçons)", gdf[~est_point]),
            (f"{nom} (points)", gdf[est_point]),
        ]
    )
    couches = [
        LayerConfig(
            name=n,
            data=g,
            style=StyleConfig(
                color=spec.get("couleur", "navy"), size_or_width=spec.get("taille", 5)
            ),
            tooltips=tooltips,
            columns_to_show=spec.get("colonnes_tableau"),
        )
        for n, g in parties
    ]
    rapport = {
        "couches": [n for n, _ in parties],
        "lignes_cartographiees": len(gdf),
        "lignes_sans_coordonnees": n_perdues,
        "geometrie": sorted(set(gdf.geometry.geom_type)),
    }
    return couches, rapport


def cmd_build(args) -> None:
    from cartes_multicouches import CarteDynMulti, GlobalDataConfig, MapConfig

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    multi = "couches" in spec
    specs = spec["couches"] if multi else [spec]
    if not specs:
        sys.exit("Erreur : la liste 'couches' est vide.")

    couches, rapports = [], []
    filtres_specifiques: dict[str, list] = {}
    for s in specs:
        c, r = _couches_depuis_spec(s)
        couches += c
        rapports.append(r)
        if s.get("filtres"):
            for lc in c:
                filtres_specifiques[lc.name] = s["filtres"]
    noms = [lc.name for lc in couches]
    doublons = sorted({n for n in noms if noms.count(n) > 1})
    if doublons:
        sys.exit(
            f"Erreur : noms de couches en double : {doublons}. Donner un 'nom_couche' distinct à chacune."
        )

    filtres_globaux = list(spec.get("filtres", [])) if multi else []
    titre = spec.get("titre", "Carte")
    # Le fond CartoDB par défaut de la bibliothèque exige désormais une clé API :
    # on prend Esri World Gray Canvas, qui n'en demande pas.
    carte = CarteDynMulti(
        couches,
        map_config=MapConfig(
            title=titre, tile_provider=spec.get("fond_de_carte", "EsriGrayCanvas")
        ),
        data_config=GlobalDataConfig(
            global_filters=filtres_globaux, specific_filters=filtres_specifiques
        ),
    )
    sortie = Path(spec.get("sortie", "carte.html"))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    carte.save(sortie)

    problemes = _verifier_html(sortie, noms, titre)
    print(
        json.dumps(
            {
                "sortie": str(sortie.resolve()),
                "taille_octets": sortie.stat().st_size,
                "couches": rapports,
                "lignes_cartographiees": sum(r["lignes_cartographiees"] for r in rapports),
                "lignes_sans_coordonnees": sum(r["lignes_sans_coordonnees"] for r in rapports),
                "verification": "ok" if not problemes else problemes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if problemes:
        sys.exit(1)


# --------------------------------------------------------------------------- CLI


def main() -> None:
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

    pv = sub.add_parser("verify", help="contrôler un HTML produit")
    pv.add_argument("html")
    pv.add_argument("--couche", action="append")
    pv.add_argument("--titre")
    pv.set_defaults(func=cmd_verify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
