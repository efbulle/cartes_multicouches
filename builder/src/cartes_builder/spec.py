"""Interprétation d'une spec JSON en carte cartes_multicouches.

Un seul format de spec, partagé entre les agents qui la rédigent, la CLI du
skill et les pages générées par cartes_builder (bouton « Configuration »).

Le module est injecté tel quel dans les pages PyScript (voir
generator.gen_carte) : il ne doit contenir ni `from __future__ import ...`
ni d'import au niveau du module — tout est importé paresseusement dans les
fonctions. Les erreurs sont des SpecError (ValueError) ; l'appelant choisit
leur affichage (message console, panneau de la page).

Format de la spec (JSON) :

{
  "version": 1,
  "titre": "Ma carte",
  "fond_de_carte": "EsriGrayCanvas",   # fournisseur sans clé API par défaut
  "filtres": ["categorie"],            # filtres globaux (toutes les couches)
  "referentiels": {                     # optionnel, géolocalisation par PK
    "rfn": {
      "donnees": "tronloc",            # nom du jeu de données de la page (manifest)
      "colonnes": {"ligne": "code_ligne", "pk_debut": "pkmd", "pk_fin": "pkmf"},
      "unite_pk": "km"                  # unité des PK du référentiel
    }
  },
  "couches": [
    {
      "fichier": "principal",           # fichier principal ou nom d'un fichier complémentaire
      "feuille": "Ma feuille",          # optionnel (défaut : première)
      "geometrie": {                    # obligatoire
        "lat": "colonne", "lon": "colonne",          # points
        # ou lat_debut/lon_debut/lat_fin/lon_fin,     # lignes droites
        # ou {"pk": {"ligne": ..., "pk_debut": ..., "pk_fin": ...,
        #           "unite_pk": "km", "referentiel": "rfn"}}
        "crs": "EPSG:2154"              # optionnel (défaut : EPSG:4326)
      },
      "nom_couche": "Tronçons",
      "couleur": "categorie",           # colonne catégorielle, couleur fixe ou null
      "taille": 5,
      "tooltips": ["code_ligne", "valeur"],
      "colonnes_tableau": ["code_ligne", "valeur"],
      "filtres": ["categorie"]          # filtres propres à la couche
    }
  ]
}

Sans "couches", la spec elle-même décrit l'unique couche. Les noms de couches
doivent être uniques ; points et tronçons d'une même couche sont séparés
automatiquement en deux couches distinctes.
"""

from dataclasses import dataclass


class SpecError(ValueError):
    """Erreur de spec ou de données, avec un message destiné à l'utilisateur."""


UNITE_PK = {"km": 1000.0, "m": 1.0}


@dataclass
class Referentiel:
    """Référentiel de lignes pour la géolocalisation par PK."""

    gdf: object  # GeoDataFrame des tronçons référents
    colonne_ligne: str
    colonne_pk_debut: str
    colonne_pk_fin: str
    unite_m: float  # 1000.0 si les PK du référentiel sont en kilomètres


def referentiels_depuis_spec(spec, resolver):
    """Construit les référentiels nommés déclarés au premier niveau de la spec.

    `resolver(nom_jeu)` retourne le GeoDataFrame associé au nom de jeu de
    données : dans une page PyScript, une variable globale issue du manifest ;
    dans la CLI, un GeoDataFrame chargé depuis un fichier. Un référentiel
    inconnu ou mal déclaré lève SpecError.
    """
    refs = {}
    for nom, decl in (spec.get("referentiels") or {}).items():
        if "donnees" not in decl:
            raise SpecError(f"Référentiel {nom!r} : clé 'donnees' manquante.")
        gdf = resolver(decl["donnees"])
        if gdf is None:
            raise SpecError(f"Référentiel {nom!r} : jeu de données {decl['donnees']!r} inconnu.")
        cols = decl.get("colonnes") or {}
        cle, pkd, pkf = cols.get("ligne"), cols.get("pk_debut"), cols.get("pk_fin")
        if not (cle and pkd and pkf):
            raise SpecError(
                f"Référentiel {nom!r} : 'colonnes' doit donner 'ligne', 'pk_debut' et 'pk_fin' "
                f"(colonnes disponibles : {list(gdf.columns)})."
            )
        unite = decl.get("unite_pk", "km")
        if unite not in UNITE_PK:
            raise SpecError(f"Référentiel {nom!r} : 'unite_pk' doit valoir 'km' ou 'm'.")
        refs[nom] = Referentiel(gdf, cle, pkd, pkf, UNITE_PK[unite])
    return refs


class SourceFichiers:
    """Feuilles de données de l'utilisateur.

    `principal` : octets du fichier Excel principal chargé par la page.
    `charges` : {nom: octets} des fichiers complémentaires (xlsx ou csv)
    chargés via le bouton « Données complémentaires ».
    """

    def __init__(self, principal, charges=None):
        self.principal = principal
        self.charges = dict(charges or {})

    def feuille(self, nom=None, feuille=None):
        import io

        import pandas as pd

        if nom in (None, "principal"):
            brut = self.principal
        elif nom in self.charges:
            brut = self.charges[nom]
        else:
            disponibles = ", ".join(["principal", *sorted(self.charges)])
            raise SpecError(
                f"Fichier de données {nom!r} inconnu. Fichiers disponibles : {disponibles}."
            )
        if feuille is None:
            feuille = 0
        elif isinstance(feuille, str) and feuille.isdigit():
            feuille = int(feuille)
        if brut[:2] == b"PK":  # un xlsx est une archive zip : signature PK
            try:
                return pd.read_excel(io.BytesIO(brut), sheet_name=feuille)
            except ValueError as exc:
                raise SpecError(
                f"Feuille {feuille!r} introuvable dans le fichier '{nom}'."
            ) from exc
        return pd.read_csv(io.BytesIO(brut))


def _num(serie):
    import pandas as pd

    if not pd.api.types.is_numeric_dtype(serie):  # virgule décimale éventuelle
        serie = serie.astype(str).str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(serie, errors="coerce")


def _ajoute_geo():
    """ajoute_geo : global injecté dans la page, sinon cartes_builder (CLI)."""
    f = globals().get("ajoute_geo")
    if f is not None:
        return f
    try:
        from cartes_builder import ajoute_geo
    except ImportError as exc:
        raise SpecError("Géolocalisation par PK indisponible (ajoute_geo introuvable).") from exc
    return ajoute_geo


def geodataframe_pk(df, pk, referentiel):
    """Géolocalise code ligne + PK début (+ PK fin) sur un référentiel."""
    ajoute_geo = _ajoute_geo()

    ligne, deb = pk.get("ligne"), pk.get("pk_debut")
    fin = pk.get("pk_fin")
    for col in (ligne, deb):
        if not col or col not in df.columns:
            raise SpecError(f"Colonne absente du fichier : {col!r}. Colonnes : {list(df.columns)}")
    if fin and fin not in df.columns:
        raise SpecError(f"Colonne absente du fichier : {fin!r}. Colonnes : {list(df.columns)}")

    unite = pk.get("unite_pk", "km")
    if unite not in UNITE_PK:
        raise SpecError("'unite_pk' doit valoir 'km' ou 'm'.")

    import pandas as pd

    ref = referentiel.gdf.rename(
        columns={
            referentiel.colonne_ligne: ligne,
            referentiel.colonne_pk_debut: "pkmd",
            referentiel.colonne_pk_fin: "pkmf",
        }
    )

    work = df.copy()
    work["_pkd"] = _num(work[deb]) * UNITE_PK[unite] / referentiel.unite_m
    work["_pkf"] = _num(work[fin]) * UNITE_PK[unite] / referentiel.unite_m if fin else float("nan")
    cle_num = _num(work[ligne])
    # le code ligne du référentiel est souvent entier : on aligne le type quand c'est possible
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
        raise SpecError("Aucune ligne n'a de code ligne et de PK exploitables.")

    gdf = ajoute_geo(
        sous[[ligne + "_jointure", "_pkd", "_pkf"]],
        ref,
        on=ligne + "_jointure",
        pk_lbls=("_pkd", "_pkf"),
        tronloc_pk_lbls=("pkmd", "pkmf"),
        pk_unit_m=referentiel.unite_m,
    )
    gdf = gdf[["geometry"]].join(df.loc[sous.index])
    trouve = ~gdf.geometry.isna() & ~gdf.geometry.is_empty
    n_non_trouvees = int((~trouve).sum())
    gdf = gdf[trouve].reset_index(drop=True)
    if gdf.empty:
        raise SpecError(
            "Aucune ligne n'a pu être placée sur le référentiel "
            "(codes ligne ou unité des PK à vérifier)."
        )
    return gdf, n_invalides + n_non_trouvees


def geodataframe(df, geo):
    """Points (lat/lon) ou lignes droites (début/fin)."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    crs = geo.get("crs", "EPSG:4326")

    def _col(cle):
        if cle not in df.columns:
            raise SpecError(f"Colonne absente du fichier : {cle!r}. Colonnes : {list(df.columns)}")
        return _num(df[cle])

    if {"lat", "lon"} <= geo.keys():
        lat, lon = _col(geo["lat"]), _col(geo["lon"])
        ok = lat.notna() & lon.notna()
        geom = [Point(x, y) if o else None for x, y, o in zip(lon, lat, ok)]
    elif {"lat_debut", "lon_debut", "lat_fin", "lon_fin"} <= geo.keys():
        la1, lo1 = _col(geo["lat_debut"]), _col(geo["lon_debut"])
        la2, lo2 = _col(geo["lat_fin"]), _col(geo["lon_fin"])
        ok = la1.notna() & lo1.notna() & la2.notna() & lo2.notna()
        geom = [
            LineString([(a, b), (c, d)]) if o else None
            for a, b, c, d, o in zip(lo1, la1, lo2, la2, ok)
        ]
    else:
        raise SpecError(
            "'geometrie' doit contenir lat+lon (points), "
            "lat_debut+lon_debut+lat_fin+lon_fin (lignes) ou pk (référentiel)."
        )

    n_perdues = int((~ok).sum())
    gdf = gpd.GeoDataFrame(df.copy(), geometry=geom, crs=crs)
    gdf = gdf[ok].reset_index(drop=True)
    if gdf.empty:
        raise SpecError("Aucune ligne n'a de coordonnées valides.")
    return gdf, n_perdues


def _referentiel_couche(geo, referentiels):
    pk = geo["pk"]
    nom = pk.get("referentiel")
    if nom is None:
        if len(referentiels) == 1:
            nom = next(iter(referentiels))
        elif not referentiels:
            raise SpecError(
                "Géométrie par PK : aucun référentiel disponible (déclarer 'referentiels')."
            )
        else:
            noms = ", ".join(sorted(referentiels))
            raise SpecError(f"Clé 'referentiel' requise (référentiels disponibles : {noms}).")
    if nom not in referentiels:
        noms = ", ".join(sorted(referentiels)) or "aucun"
        raise SpecError(f"Référentiel {nom!r} inconnu. Référentiels déclarés : {noms}.")
    return referentiels[nom]


def couches_depuis_spec(spec_couche, source, referentiels):
    """Construit les LayerConfig d'une couche (deux si points et lignes sont mêlés)."""
    from cartes_multicouches import LayerConfig, StyleConfig

    if not isinstance(spec_couche, dict) or "geometrie" not in spec_couche:
        raise SpecError("Chaque couche doit être un objet JSON avec une clé 'geometrie'.")

    df = source.feuille(spec_couche.get("fichier"), spec_couche.get("feuille"))
    geo = spec_couche["geometrie"]
    if "pk" in geo:
        gdf, n_perdues = geodataframe_pk(df, geo["pk"], _referentiel_couche(geo, referentiels))
    else:
        gdf, n_perdues = geodataframe(df, geo)

    for cle in ("filtres", "tooltips", "colonnes_tableau"):
        for col in spec_couche.get(cle, []) or []:
            if col not in gdf.columns:
                raise SpecError(
                    f"Colonne {col!r} (clé {cle!r}) absente. Colonnes : {list(gdf.columns)}"
                )

    nom = spec_couche.get("nom_couche", "Données")
    tooltips = (
        [(c, f"@{c}") for c in spec_couche["tooltips"]] if spec_couche.get("tooltips") else None
    )
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
                color=spec_couche.get("couleur", "navy"),
                size_or_width=spec_couche.get("taille", 5),
            ),
            tooltips=tooltips,
            columns_to_show=spec_couche.get("colonnes_tableau"),
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


def carte_from_spec(spec, source, referentiels=None):
    """Construit la carte décrite par une spec complète (une ou plusieurs couches).

    `source` : SourceFichiers (données de l'utilisateur).
    `referentiels` : {nom: Referentiel} déjà résolus (referentiels_depuis_spec).

    Retourne (CarteDynMulti, rapport) — jamais un fichier : la CLI appelle
    carte.save(...), la page PyScript embarque le layout avec json_item.
    """
    from cartes_multicouches import CarteDynMulti, GlobalDataConfig, MapConfig

    if not isinstance(spec, dict):
        raise SpecError("La spec doit être un objet JSON.")
    if spec.get("version", 1) != 1:
        raise SpecError(f"Version de spec non supportée : {spec.get('version')!r} (attendu : 1).")

    referentiels = referentiels or {}
    multi = "couches" in spec
    specs = spec["couches"] if multi else [spec]
    if not specs:
        raise SpecError("La liste 'couches' est vide.")

    couches, rapports = [], []
    filtres_specifiques: dict[str, list] = {}
    for s in specs:
        c, r = couches_depuis_spec(s, source, referentiels)
        couches += c
        rapports.append(r)
        if s.get("filtres"):
            for lc in c:
                filtres_specifiques[lc.name] = s["filtres"]

    noms = [lc.name for lc in couches]
    doublons = sorted({n for n in noms if noms.count(n) > 1})
    if doublons:
        raise SpecError(
            f"Noms de couches en double : {doublons}. Donner un 'nom_couche' distinct à chacune."
        )

    filtres_globaux = list(spec.get("filtres", [])) if multi else []
    # Le fond CartoDB par défaut de la bibliothèque exige désormais une clé API :
    # on prend Esri World Gray Canvas, qui n'en demande pas.
    carte = CarteDynMulti(
        couches,
        map_config=MapConfig(
            title=spec.get("titre", "Carte"),
            tile_provider=spec.get("fond_de_carte", "EsriGrayCanvas"),
        ),
        data_config=GlobalDataConfig(
            global_filters=filtres_globaux, specific_filters=filtres_specifiques
        ),
    )
    rapport = {
        "couches": rapports,
        "lignes_cartographiees": sum(r["lignes_cartographiees"] for r in rapports),
        "lignes_sans_coordonnees": sum(r["lignes_sans_coordonnees"] for r in rapports),
    }
    return carte, rapport
