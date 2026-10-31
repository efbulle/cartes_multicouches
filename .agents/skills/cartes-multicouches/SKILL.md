---
name: cartes-multicouches
description: Créer pour un utilisateur non-programmeur des cartes HTML interactives à partir de fichiers Excel ou CSV avec le dépôt GitHub cartes_multicouches. Convient aux points GPS, lignes définies par coordonnées, tronçons ferroviaires définis par code de ligne et PK, plusieurs couches, filtres, infobulles, tableaux. Sans agent capable d'exécuter des commandes, oriente vers le constructeur en ligne.
license: MIT
compatibility: "Voie 1 (constructeur en ligne) : aucun prérequis, un navigateur suffit. Voie 2 (script) : agent capable de lire/écrire des fichiers et d'exécuter des commandes, avec uv et un accès réseau."
metadata:
  author: efbulle
  version: "1.1.0"
---

# Cartes interactives sans programmation — cartes_multicouches

L'utilisateur décrit en langage courant la carte souhaitée. Il ne programme pas, n'installe rien. Tu inspectes ses données, construis la carte HTML, la vérifies et la lui remets.

## Règles de comportement

- Parle comme à un collègue non informaticien : pas de code ni de commandes sauf demande. Dis « coordonnées GPS », « points kilométriques (PK) », « couche », « infobulle » et explique brièvement ces mots.
- Ne pose que des questions sur les données ou le rendu, une à la fois (ou une seule question courte si plusieurs ambiguïtés bloquantes).
- Ne devine jamais une colonne, une unité de PK, un système de coordonnées, une catégorie.
- Ne modifie jamais le fichier source ; écris dans des fichiers distincts.
- Ne téléverse pas les données vers un service externe (le constructeur en ligne les traite dans le navigateur de l'utilisateur ; les téléchargements de fond de carte ou du référentiel PK sont distincts).
- N'annonce jamais une carte créée si la génération a échoué ou si le fichier n'existe pas.
- Préfère les valeurs par défaut documentées et une carte simple ; ajoute les personnalisations demandées sans multiplier les questions.

## 1. Choisir la voie

**Voie 1 — constructeur en ligne (par défaut si tu ne peux pas exécuter de commandes, ou si la voie 2 échoue).**
Indique https://efbulle.github.io/cartes_multicouches/ : l'utilisateur y dépose son fichier Excel et suit les étapes. Aide-le avec des consignes courtes (quelle feuille, quelles colonnes) d'après ce que tu peux lire de son fichier. Le constructeur couvre les classeurs ferroviaires (code de ligne + PK) ; pour des points GPS ou des CSV, utilise la voie 2.

**Voie 2 — script local** (agent avec shell, fichiers et réseau). Une seule tentative de préparation ; en cas d'échec, bascule sur la voie 1 sans bricoler d'autre installation ni installer quoi que ce soit globalement.

Repère `SKILL_DIR` (dossier de ce fichier) et `REPO_DIR` (copie du dépôt `https://github.com/efbulle/cartes_multicouches`, à cloner dans l'espace de travail si absente). Utilise des chemins absolus.

Le script demande Python 3.13+, souvent absent : utilise toujours `uv` depuis `REPO_DIR`. **CMD** désigne `cd "$REPO_DIR" && uv run python`. Préparation unique : `cd "$REPO_DIR" && uv sync --group dev`.

## 2. Construire avec le script (voie 2)

Sous-commandes de `CMD "$SKILL_DIR/scripts/xlsx_vers_carte.py"` :

1. `doctor` — diagnostic ; doit finir par « environnement courant prêt ». Sinon `uv sync --group dev` puis une seule relance.
2. `inspect FICHIER [--feuille NOM]` — feuilles, colonnes, types, valeurs manquantes, candidats lat/lon/PK.
3. `init-spec FICHIER [--feuille NOM] --sortie spec.json` — brouillon de configuration, à relire et ajuster.
4. `build spec.json` — construit et vérifie la carte ; rapport JSON.
5. `verify carte.html [--couche NOM] [--titre T]` — contrôle statique.

Les clés de la spec (une couche ou `couches: [...]` pour plusieurs) sont décrites en tête du script : `CMD "$SKILL_DIR/scripts/xlsx_vers_carte.py" --help`. Pour une carte à plusieurs couches, fais un `inspect` par fichier/feuille et une entrée par couche, avec un `nom_couche` unique ; un `filtres` au premier niveau s'applique à toutes les couches qui ont la colonne.

Cas non couverts (légende personnalisée, indicateurs, annotations, mapping de couleurs explicite) : lis `api.md` et écris un court script avec l'API ; n'invente pas d'options. Les polygones ne sont pas pris en charge : dis-le plutôt que de les dessiner comme des lignes.

## 3. Comprendre la géométrie

- Latitude + longitude : points. Latitude/longitude de début et de fin : lignes droites.
- Coordonnées projetées : utilise le CRS documenté ; si les valeurs évoquent Lambert 93 (X ≈ 600 000, Y ≈ 6 800 000) sans confirmation, demande.
- Code de ligne + PK début (+ fin) : positionnement sur le réseau ferré. Confirme les colonnes et l'**unité des PK (km ou m)**. Un PK fin vide ou égal au début = point ; points et tronçons sont placés dans des couches distinctes. Référentiel par défaut : réseau ferré national public, à citer « extras-opendata-sncf-reseau (N. Wurtz), licence ODbL » ; un référentiel propre est possible (voir l'en-tête du script).
- Adresses seules : ne pas les convertir arbitrairement ; expliquer qu'il faut des coordonnées.
- Lignes non géolocalisées : garde les autres, signale le nombre. Un résultat vide indique souvent une mauvaise unité de PK, un autre code de ligne ou un référentiel inadapté.

## 4. Choisir le rendu

- Titre clair, noms de couches explicites et uniques.
- Couleur fixe par défaut ; couleur par catégorie si l'utilisateur veut comparer. Pas plus de 20 modalités : sinon autre variable ou conseil demandé.
- Filtres, infobulles et tableau n'utilisent que des colonnes présentes dans l'inspection ; les sommes, que des colonnes numériques.
- Fond de carte sans clé API (`EsriGrayCanvas`) sauf besoin explicite et clé disponible. Ne prétends pas que le HTML fonctionne hors ligne : le fond de carte demande internet.

## 5. Vérifier avant de livrer

- Le script s'est terminé sans erreur ; le rapport indique `verification: "ok"` ; le HTML existe, non vide, créé pendant cette exécution (pas un résidu d'un essai précédent).
- Nombre d'objets cartographiés plausible ; couches attendues présentes.
- Si un navigateur contrôlable est disponible, ouvre la carte ; sinon ne prétends pas l'avoir fait.
- Carte partielle : dis clairement ce qui manque.

## 6. Restituer

En français, simplement : emplacement exact (ou téléchargement) du fichier ; résumé des couches, filtres, infobulles et tableau réellement créés ; nombre d'objets cartographiés et non placés ; « double-cliquez pour ouvrir dans un navigateur, internet requis pour le fond de carte » ; une proposition d'ajustement concrète. Ne révèle pas les détails internes sauf demande.

## Exemples de dialogue

**Points GPS**
> Utilisateur : « Voici mes chantiers, fais-moi une carte colorée par statut. »
> Agent : inspecte, repère `Latitude`/`Longitude` et `Statut` (4 valeurs). Construit directement sans question. « Votre carte est prête : 120 chantiers, colorés selon leur statut, avec un filtre par statut. 2 lignes sans coordonnées n'ont pas pu être placées (lignes 14 et 87). Voulez-vous aussi un filtre par année ? »

**PK ferroviaires (question bloquante)**
> Utilisateur : « Carte de mes interventions, j'ai la ligne et les PK. »
> Agent : « Vos PK sont-ils exprimés en kilomètres (ex. 12,450) ou en mètres (ex. 12450) ? » — une fois la réponse reçue, construit.

**Deux couches**
> Utilisateur : « Mets les tronçons à ralentir et les gares sur la même carte. »
> Agent : inspecte les deux feuilles, construit une couche « Ralentissements » (lignes) et une couche « Gares » (points), puis résume : « Deux couches, que vous pouvez afficher ou masquer séparément. »

**Environnement sans exécution**
> Agent : « Je ne peux pas fabriquer le fichier moi-même ici. Ouvrez https://efbulle.github.io/cartes_multicouches/, déposez votre Excel et choisissez la feuille « Tronçons » ; je vous guide à chaque étape. »
