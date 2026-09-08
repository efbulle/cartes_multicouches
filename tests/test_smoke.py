"""Tests de fumée pour cartes_multicouches.

Toujours le même principe qu'un seul test : construire une vraie carte,
la charger dans un navigateur, vérifier qu'aucune erreur JS ne survient.
On élargit juste le nombre de scénarios couverts — pas la profondeur de
chaque vérification.

pip install pytest pytest-playwright bokeh geopandas shapely
playwright install chromium
pytest test_smoke.py -v
"""

import geopandas as gpd
import pytest
from bokeh import io
from bokeh.models import MultiSelect
from bokeh.resources import INLINE
from shapely.geometry import LineString, Point

from cartes_multicouches import (
    AnnotationConfig,
    CarteDynMulti,
    ColorMapping,
    GlobalDataConfig,
    LayerConfig,
    LayerIndicator,
    LegendConfig,
    LegendEntry,
    MapConfig,
    StyleConfig,
    carte_une_couche,
)


def _gdf_troncons() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"mnemo": ["TER", "TGV", "FRET"]},
        geometry=[
            LineString([(700000, 6850000), (715000, 6845000)]),
            LineString([(700000, 6850000), (725000, 6870000)]),
            LineString([(700000, 6850000), (695000, 6820000)]),
        ],
        crs="EPSG:2154",
    )


def _gdf_gares() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"nom": ["Nordeau", "Val-sur-Aine"]},
        geometry=[Point(700000, 6850000), Point(730000, 6840000)],
        crs="EPSG:2154",
    )


def _assert_pas_derreur_js(page, html_path) -> None:
    """Le coeur du test de fumée, factorisé pour ne pas le répéter."""
    erreurs_js = []
    page.on("pageerror", lambda exc: erreurs_js.append(str(exc)))

    page.goto(f"file://{html_path}")
    page.wait_for_function("() => !!window.Bokeh && Bokeh.documents.length > 0")

    assert erreurs_js == []


def test_carte_une_couche_se_charge_sans_erreur(page, tmp_path):
    carte = carte_une_couche(
        _gdf_troncons(),
        color=ColorMapping(column="mnemo", mapping={"TER": "blue", "TGV": "red", "FRET": "green"}),
        filters=["mnemo"],
        legend_config=LegendConfig(
            entries=[LegendEntry(label="TER", color="blue", shape="line")],
        ),
    )
    html_path = tmp_path / "carte_simple.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test simple")

    _assert_pas_derreur_js(page, html_path)


def test_carte_multi_couches_se_charge_sans_erreur(page, tmp_path):
    """Couvre un chemin de code différent : 2 couches + specific_filters,
    plus mélangé (lignes ET points) que le cas à une seule couche."""
    carte = CarteDynMulti(
        layers_config=[
            LayerConfig(name="Tronçons", data=_gdf_troncons(), style=StyleConfig(color="navy")),
            LayerConfig(name="Gares", data=_gdf_gares(), style=StyleConfig(color="black")),
        ],
        map_config=MapConfig(title="Test multi"),
        data_config=GlobalDataConfig(specific_filters={"Tronçons": ["mnemo"]}),
    )
    html_path = tmp_path / "carte_multi.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test multi")

    _assert_pas_derreur_js(page, html_path)


def test_filtre_colonne_booleenne(page, tmp_path):
    gdf = _gdf_troncons()
    gdf["actif"] = [True, False, True]
    carte = CarteDynMulti(
        layers_config=[LayerConfig(name="Tronçons", data=gdf, style=StyleConfig(color="navy"))],
        map_config=MapConfig(title="Test filtre booléen"),
        data_config=GlobalDataConfig(specific_filters={"Tronçons": ["actif"]}),
    )
    html_path = tmp_path / "carte_filtre_booleen.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test filtre booléen")

    erreurs_js = []
    page.on("pageerror", lambda exc: erreurs_js.append(str(exc)))
    page.goto(f"file://{html_path}")
    page.wait_for_function("() => !!window.Bokeh && Bokeh.documents.length > 0")
    page.locator("select").select_option(["True"])

    indices = page.evaluate(
        """() => Bokeh.documents[0].get_model_by_name('Tronçons').view.filter.indices"""
    )
    assert indices == [0, 2]
    assert erreurs_js == []


def test_carte_sans_legende_ni_filtre_se_charge_sans_erreur(page, tmp_path):
    """Le cas le plus minimal possible : aucune option facultative
    activée. Utile car c'est parfois là que les valeurs par défaut
    d'une dataclass posent problème (None non géré, etc.)."""
    carte = carte_une_couche(_gdf_troncons())
    html_path = tmp_path / "carte_minimale.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test minimal")

    _assert_pas_derreur_js(page, html_path)


@pytest.mark.parametrize("color_mode", ["fixe", "categoriel"])
def test_les_deux_modes_de_couleur_se_chargent_sans_erreur(page, tmp_path, color_mode):
    """StyleConfig.color accepte soit une couleur fixe (str) soit un
    mapping catégoriel (dict) — deux chemins de rendu différents dans
    _mixins.py, donc deux occasions distinctes de casser quelque chose."""
    color = (
        "navy"
        if color_mode == "fixe"
        else ColorMapping(column="mnemo", mapping={"TER": "blue", "TGV": "red", "FRET": "green"})
    )
    carte = carte_une_couche(_gdf_troncons(), color=color)
    html_path = tmp_path / f"carte_{color_mode}.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test couleur")

    _assert_pas_derreur_js(page, html_path)


def test_indicators_se_chargent_sans_erreur(page, tmp_path):
    gdf = _gdf_troncons()
    gdf["longueur_fictive"] = [10, 20, 15]

    carte = CarteDynMulti(
        layers_config=[
            LayerConfig(
                name="Tronçons",
                data=gdf,
                style=StyleConfig(color="navy"),
                indicators=[
                    LayerIndicator(label="Nombre de tronçons", kind="count"),
                    LayerIndicator(label="Longueur totale", kind="sum", column="longueur_fictive"),
                ],
            ),
        ],
        map_config=MapConfig(title="Test indicators"),
    )
    html_path = tmp_path / "carte_indicators.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test indicators")

    _assert_pas_derreur_js(page, html_path)


def test_annotation_se_charge_sans_erreur(page, tmp_path):
    """Couvre le chemin AnnotationConfig, y compris un offset par
    colonne (x_offset/y_offset acceptent un nom de colonne)."""
    gdf = _gdf_troncons()
    gdf["label_dy"] = [0, -14, 14]

    carte = CarteDynMulti(
        layers_config=[
            LayerConfig(
                name="Tronçons",
                data=gdf,
                style=StyleConfig(color="navy"),
                annotation=AnnotationConfig(text="mnemo", y_offset="label_dy"),
            ),
        ],
        map_config=MapConfig(title="Test annotation"),
    )
    html_path = tmp_path / "carte_annotation.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test annotation")

    _assert_pas_derreur_js(page, html_path)


def test_show_endpoints_se_charge_sans_erreur(page, tmp_path):
    carte = CarteDynMulti(
        layers_config=[
            LayerConfig(
                name="Tronçons",
                data=_gdf_troncons(),
                style=StyleConfig(color="navy"),
                show_endpoints=True,
            ),
        ],
        map_config=MapConfig(title="Test endpoints"),
    )
    html_path = tmp_path / "carte_endpoints.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test endpoints")

    _assert_pas_derreur_js(page, html_path)


def test_global_et_specific_select_filters_se_chargent_sans_erreur(page, tmp_path):
    """Couvre les 2 variantes de filtres non testées ailleurs :
    global_filters (MultiSelect partagé) et specific_select_filters
    (Select à choix unique, propre à une couche)."""
    carte = CarteDynMulti(
        layers_config=[
            LayerConfig(name="Tronçons", data=_gdf_troncons(), style=StyleConfig(color="navy")),
            LayerConfig(name="Gares", data=_gdf_gares(), style=StyleConfig(color="black")),
        ],
        map_config=MapConfig(title="Test filtres globaux/select"),
        data_config=GlobalDataConfig(
            global_filters=["mnemo"],
            specific_select_filters={"Tronçons": ["mnemo"]},
        ),
    )
    html_path = tmp_path / "carte_filtres_globaux.html"
    io.save(carte.layout_widget, str(html_path), resources=INLINE, title="Test filtres")

    _assert_pas_derreur_js(page, html_path)


def test_multiselect_s_adapte_au_nombre_d_options_et_parametre_la_hauteur():
    gdf = _gdf_troncons()
    carte = CarteDynMulti(
        layers_config=[LayerConfig(name="Tronçons", data=gdf, style=StyleConfig(color="navy"))],
        map_config=MapConfig(title="Test taille multiselect"),
        data_config=GlobalDataConfig(
            specific_filters={"Tronçons": ["mnemo"]},
            multi_select_size=6,
        ),
    )

    widget = carte.widgets_filters["Tronçons__mnemo"]
    assert isinstance(widget, MultiSelect)
    assert widget.size == 3

    carte_rapide = carte_une_couche(
        gdf,
        filters=["mnemo"],
        multi_select_size=2,
    )
    widget_rapide = carte_rapide.widgets_filters["Tronçons__mnemo"]
    assert isinstance(widget_rapide, MultiSelect)
    assert widget_rapide.size == 2


def test_annotation_subset_column_se_charge_sans_erreur(page, tmp_path):
    """Couvre AnnotationConfig.subset_column : seul un sous-ensemble des
    tronçons est annoté (IntersectionFilter entre le sous-ensemble statique
    et le filtre interactif existant), combiné à un vrai widget de filtre
    pour vérifier que l'assemblage JS ne casse rien au chargement."""
    gdf = _gdf_troncons()
    gdf["annoter"] = [True, False, True]

    carte = CarteDynMulti(
        layers_config=[
            LayerConfig(
                name="Tronçons",
                data=gdf,
                style=StyleConfig(color="navy"),
                annotation=AnnotationConfig(text="mnemo", subset_column="annoter"),
            ),
        ],
        map_config=MapConfig(title="Test annotation sous-ensemble"),
        data_config=GlobalDataConfig(specific_filters={"Tronçons": ["mnemo"]}),
    )
    html_path = tmp_path / "carte_annotation_subset.html"
    io.save(
        carte.layout_widget,
        str(html_path),
        resources=INLINE,
        title="Test annotation sous-ensemble",
    )

    _assert_pas_derreur_js(page, html_path)
