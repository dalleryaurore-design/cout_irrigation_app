# Analyse financière de l'irrigation

Application web locale (Flask + Système de Design de l'État) qui estime, à l'échelle
d'une commune, le **coût annuel** et la **rentabilité** d'un projet d'irrigation :
bilan agronomique, décomposition du coût par poste, graphique en cascade et seuil de
rentabilité. Chaque hypothèse est sourcée : la source apparaît en info-bulle au survol
de la valeur, la référence complète au format APA dans le volet **Références**.

---

## 1. Installation

Python 3.10 ou plus récent.

```bash
cd app_cout_irrigation
python -m venv .venv
# Windows :        .venv\Scripts\activate
# macOS / Linux :  source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

L'application s'ouvre sur <http://127.0.0.1:5000>.

`rasterio` ne sert qu'à lire les cartes .tif. Si son installation échoue (compilation
de GDAL sous Windows), l'application démarre quand même : les valeurs agronomiques
proviennent alors du référentiel. En cas de difficulté :
`pip install rasterio --only-binary :all:`.

L'import de `rasterio` n'a lieu qu'au premier besoin réel de lecture : sans carte dans
le dossier `carte-violet/` (voir § 4), il n'est jamais chargé et le démarrage est immédiat.

### Système de Design de l'État

Le DSFR 1.15.3 est déjà présent dans `static/dsfr/` (feuille de style, scripts,
polices Marianne, icônes utilisées). Pour le remplacer par la version téléchargée sur
votre poste, copiez le contenu du dossier `dist` de l'archive dans `static/dsfr/`, ou
indiquez son emplacement :

```bash
# Windows
set IRRIG_DSFR=C:\chemin\vers\dsfr-1.15.3\dist && python app.py
# macOS / Linux
IRRIG_DSFR=/chemin/vers/dsfr-1.15.3/dist python app.py
```

Si aucun DSFR local n'est trouvé, l'application bascule sur le CDN jsDelivr (accès
internet requis) et le signale en pied de page.

### Accès réseau

Deux services publics sont appelés depuis le navigateur :

| Service | Usage | Conséquence en cas de blocage |
|---|---|---|
| `geo.api.gouv.fr` | recherche de commune, contour, département | saisie de commune indisponible ; les calculs restent possibles, sans lecture des cartes |
| `data.geopf.fr` | fond de carte Plan IGN | carte en fond gris, tout le reste fonctionne |

Tout le reste (DSFR, Leaflet, Chart.js) est servi localement.

**Si l'application paraît lente, la cause est presque toujours là.** Les calculs
s'exécutent en moins d'une milliseconde sur le poste ; ce sont les appels réseau qui
attendent. Derrière un proxy lent, lancez l'application sans fond de tuiles — la commune
reste localisée par son contour :

```bash
# Windows
set IRRIG_FOND_CARTE=0 && python app.py
# macOS / Linux
IRRIG_FOND_CARTE=0 python app.py
```

Pour désactiver en plus la lecture des cartes .tif, ajoutez `IRRIG_LECTURE_CARTES=0`.

---

## 2. Utilisation

### Volet Projet

**Onglet Simulation.** Renseignez la commune, la culture, la surface, la ressource en
eau et l'équipement : les résultats se recalculent à chaque modification. Au chargement
de la page (hors exemple pré-rempli), la commune et la culture sont pré-remplies avec les
valeurs de `COMMUNE_DEFAUT` / `DEPARTEMENT_DEFAUT` / `CULTURE_DEFAUT` de `config.py`
(par défaut : Saint-Ouen-du-Breuil, 76890, blé tendre), modifiable via les variables
d'environnement `IRRIG_COMMUNE_DEFAUT`, `IRRIG_DEPARTEMENT_DEFAUT`, `IRRIG_CULTURE_DEFAUT`.

- *Prix de vente* : deux jeux de valeurs au choix — **prix de marché** (`prix_vente` :
  prix payés aux producteurs FranceAgriMer, moyenne olympique 2020/21-2024/25, pour les
  grandes cultures) ou **barème MASAA** de l'assurance récolte 2026 (`prix_masaa`, valeur
  centrale du barème de prix assuré). Modifiable ; le bouton « Valeur par défaut » rétablit
  la valeur du jeu choisi.
- *Utiliser les rendements par défaut du référentiel (sans carte)* : n'est actif que pour
  les cultures disposant de cartes ; permet de comparer la lecture cartographique aux
  valeurs par défaut.
- *Méthode d'estimation* du besoin en eau (sous le résultat) : **Carte** (modèle
  agronomique), **SGPE** ou **Référence** (valeur par défaut du référentiel). La méthode
  SGPE calcule Σ max(0, ETP × Kc − P) sur les mois où Kc > 0 : Kc mensuels du référentiel
  (codes `kc_01` à `kc_12`, feuille Cultures), ETP et P de `climate_data.xlsx` au point de
  grille le plus proche du centre de la commune (horizon `IRRIG_HORIZON_CLIMAT`, H1 par
  défaut). En l'absence de Kc ou de donnée climatique, la valeur du référentiel s'applique.
  La lecture du classeur étant lente, un cache `climate_data.cache.npz` est créé à côté.
- *Infrastructure déjà amortie* (case à droite du titre « Source de l'eau ») et *Matériel
  déjà amorti* (à droite du titre « Équipement ») : le capital est réputé remboursé.
  L'annuité et le CAPEX d'accès à la ressource tombent à zéro ; l'entretien, l'énergie,
  la redevance, la part fixe et la part volumétrique restent comptés.
- *Retenue* : la capacité est dimensionnée sur le besoin (volume à prélever ÷ taux de
  remplissage, multiplié par le nombre d'adhérents si la retenue est collective) ; vous
  pouvez la saisir en désactivant le dimensionnement automatique.
- *Nombre d'unités* : proposé d'après la surface couverte par machine (enrouleur, pivot,
  rampe), modifiable. Le CAPEX progresse par paliers, d'où l'effet de seuil visible sur
  le bilan quand la surface dépasse la capacité d'une machine.
- *Modifier la durée d'amortissement de…* : option à dérouler sous le choix de
  l'équipement, et sous les champs de la retenue lorsque la ressource choisie en est
  une (bassine collinaire ou par pompage). Elle écrase, pour la simulation, la durée de
  vie documentée dans le référentiel pour l'objet actuellement sélectionné ; laissée
  vide, la valeur par défaut de cet objet s'applique. Elle ne se modifie plus ligne par
  ligne dans les tableaux des onglets Équipement / Accès à la ressource (colonnes
  « Durée de vie » devenues lecture seule).
- *Subvention* : deux curseurs distincts — l'un pour le matériel d'irrigation (subvention
  de l'État, 40 % par défaut), l'autre pour l'ouvrage d'accès à l'eau et le
  réseau d'amenée (70 % pour une retenue, 45 % pour un forage, par défaut).
- *Rendement potentiel irrigué / Rendement potentiel pluvial / Besoin en eau
  d'irrigation* : trois cases à cocher indépendantes, chacune superpose au fond de carte
  une image couleur de la variable choisie, pour la culture sélectionnée — dégradé rouge
  (faible) → vert (fort) pour un rendement, jaune (faible) → bleu (fort) pour le besoin en
  eau. Chaque case n'est activable que si la carte correspondante existe pour la culture ;
  plusieurs couches peuvent être affichées en même temps. La normalisation des couleurs
  (min–max) est propre à chaque carte, indiquée dans la légende sous la carte. Calculée
  côté serveur (`GET /api/carte-variable/<culture>/<variable>`, image PNG reprojetée en
  EPSG:4326, mise en cache tant que le fichier ne change pas) — voir
  `moteur/cartes.py::carte_variable`.

**Onglets Équipement, Accès à la ressource, Ressources.** Les hypothèses en coulisse.
Les valeurs marquées « Variable » dans le référentiel sont des champs de saisie : leur
modification s'applique immédiatement à la simulation et le champ se souligne en bleu.
Le bouton « Rétablir les valeurs du référentiel » annule toutes les surcharges. Les
cellules grisées avec le badge **C** sont calculées à partir des autres.

Le tableau de l'onglet Équipement affiche, par équipement : CAPEX (€/ha), durée de vie,
taux d'amortissement annuel, annuité (€/ha/an, nette de la subvention au matériel),
coût de main-d'œuvre (€/ha/an), coût de maintenance (€/ha/an), coût annuel total
(€/ha/an, somme des trois précédents) et efficience d'application.

Badges de fiabilité : **D** documenté (chiffre publié par une source nommée), **C**
calculé à partir de données documentées, **E** estimé (ordre de grandeur, source
secondaire ou hypothèse de travail).

### Volet Exemples

Six situations types. Un clic ouvre le projet pré-rempli, modifiable ensuite.

### Volet Références

Bibliographie complète au format APA, convention de fiabilité, méthode de calcul,
limites de lecture, et hypothèses des cartes (scénario RCP4.5 et narratif « violet »
d'Explore2).

---

## 3. Référentiel des hypothèses

Toutes les valeurs de l'application viennent de
`referentiel/referentiel_irrigation.xlsx`. **Ce classeur est la source unique : aucune
valeur n'est écrite en dur dans le code.**

Il suffit d'ouvrir le fichier, de modifier une cellule, d'enregistrer puis de rafraîchir
la page : l'application détecte le changement et relit le classeur. Si le fichier est
ouvert en écriture au moment de la lecture, la dernière version valide est conservée et
un bandeau d'avertissement s'affiche.

### Feuilles

| Feuille | Contenu |
|---|---|
| `Lisez-moi` | conventions de saisie |
| `Cultures` | 24 cultures × rendement irrigué, rendement pluvial, besoin d'irrigation, prix de vente, condition d'existence |
| `Equipement` | 6 matériels × CAPEX, efficience, main-d'œuvre, maintenance, durée de vie ; paramètres généraux (taux d'actualisation, taux de subvention du matériel) |
| `Acces_ressource` | 5 types d'accès (forage, cours d'eau, retenue collinaire, retenue par pompage, ASA) × investissement, part fixe et volumétrique, distance d'amenée, durées de vie ; paramètres généraux (subvention, réseau d'amenée, taux d'actualisation) |
| `Ressources` | redevances des 6 agences de l'eau, seuils d'assujettissement, prix de l'énergie |
| `Cartes` | déclaration des fichiers .tif par culture |
| `Exemples` | les six exemples pré-remplis |
| `Departements` | rattachement département → agence de l'eau |
| `References` | bibliographie APA (identifiant, citation courte, référence complète, URL, statut) |

### Colonnes des feuilles de paramètres

`Objet | Code paramètre | Libellé | Valeur | Unité | Fiabilité | Variable | Min | Max | Réf. | Précision`

- **Valeur** : seule colonne à modifier couramment. Les pourcentages se saisissent en
  décimal (0,85 pour 85 %).
- **Fiabilité** : `D`, `C` ou `E`.
- **Variable** : `oui` rend le paramètre modifiable depuis l'interface, entre `Min` et `Max`.
- **Réf.** : identifiant présent dans la feuille `References`. Une référence inconnue est
  signalée comme anomalie dans le volet Références.
- **Précision** : complément affiché en fin d'info-bulle (fourchette, date, mise en garde).

Pour ajouter une culture, un équipement ou une ressource, dupliquez le bloc de lignes
d'un objet existant et changez la colonne `Objet` : l'application le reprend
automatiquement dans les listes déroulantes.

---

## 4. Cartes .tif

Déposez les fichiers dans `carte-violet/` (dossier lu par défaut ; voir `DOSSIER_CARTES`
dans `config.py` ou la variable d'environnement `IRRIG_CARTES`) puis renseignez leur nom
dans la feuille `Cartes` du référentiel (colonne `Culture` correspondante). Convention de
nommage reconnue automatiquement si la colonne est laissée vide mais que le code carte
est renseigné :

```
culture_<CODE>_<conduite>_<variable>_<contexte>.tif
```

| Variable | Motif | Contenu |
|---|---|---|
| besoin en eau | `irrigue_irr` | besoin d'irrigation |
| rendement irrigué | `irrigue_pot` | rendement potentiel en conduite irriguée |
| rendement pluvial | `rainfed_pot` | rendement potentiel en conduite pluviale |

Exemple pour le blé tendre :
`culture_BTH_irrigue_irr_explore2-violet_rcp45_2020-2040_8km.tif`

Le dossier `cartes/` (narratif « jaune », RCP8.5, blé tendre seul) reste sur le disque
mais n'est plus lu par défaut.

Les trois fichiers d'une culture doivent être présents pour que la carte soit utilisée.

**Unités.** Les colonnes `Unité rendement` et `Unité besoin` acceptent `auto`, `t/ha`,
`q/ha`, `kg/ha`, `mm`, `m3/ha`. En mode `auto`, l'unité est déduite par comparaison avec
la valeur de référence de la culture ; l'info-bulle du résultat indique alors
« unité déduite ». **Confirmez les unités auprès du producteur des cartes avant tout
usage en production** et renseignez-les explicitement.

**Système de coordonnées.** Il est lu dans le fichier. S'il est absent, il est deviné
(WGS 84, Lambert-93, Lambert II étendu) et l'écart est signalé sous la carte ; la colonne
`SCR` permet de l'imposer (`EPSG:2154`, par exemple).

**Extraction communale.** La valeur retenue est la moyenne des mailles qui touchent le
contour de la commune ; à défaut, la maille du centre, puis la maille valide la plus
proche. Le nombre de mailles utilisées figure dans l'info-bulle. Seule la fenêtre du
raster qui recouvre la commune est lue : le temps de lecture ne dépend pas de l'étendue
de la carte.

Les cartes brutes ne sont pas affichées telles quelles : l'application les lit pour
alimenter le bilan agronomique. Une image couleur dérivée de chaque variable (rendement
irrigué, rendement pluvial, besoin en eau) peut toutefois être superposée au fond de
carte, une à une — voir § 2, « Rendement potentiel irrigué / Rendement potentiel pluvial
/ Besoin en eau d'irrigation ». Les hypothèses du scénario sont rappelées dans le volet
Références.

---

## 5. Méthode de calcul

```
volume appliqué (m³) = besoin (mm) × 10 × surface (ha)
volume prélevé  (m³) = volume appliqué ÷ efficience d'application

énergie      = (volume prélevé + volume prélevé × part du remplissage pompée) × prix forfaitaire (€/m³)
               part pompée : 0 pour une retenue collinaire (ruissellement + pluie),
               95 % par défaut pour une retenue par pompage ; sans objet hors retenue
redevance    = volume prélevé × taux de l'agence (catégorie 1 ou 2, eaux superficielles
               ou souterraines), si le prélèvement dépasse le seuil d'assujettissement ;
               non ajoutée pour l'ASA (comprise dans son tarif)
équipement   = CAPEX × (1 − subvention) × a + maintenance
main-d'œuvre = coût de main-d'œuvre de l'équipement (€/ha/an) × surface
accès        = ouvrage × (1 − subvention) × a_ouvrage
               + distance d'amenée (commune, sauf ASA) × coût des tuyaux × (1 − subvention) × a_réseau
               + part fixe + part volumétrique

a = i (1 + i)ⁿ / [(1 + i)ⁿ − 1]        facteur d'annualisation ; a = 1/n si i = 0

gain  = (rendement irrigué − rendement pluvial) × 0,1 × prix (€/t) × surface
bilan = gain − coût total

prix minimal   = coût total ÷ [(Δ rendement) × 0,1 × surface]
Δ rendement minimal à prix constant = coût total ÷ (0,1 × prix × surface)
```

Le type d'accès « ASA » représente tout réseau collectif sous pression, quel que soit son
gestionnaire (ASA d'irrigants, société d'aménagement régional, concessionnaire d'un canal) :
même tarification binomiale, seule la gouvernance diffère. L'énergie de mise en pression
et la redevance de prélèvement, acquittées par le gestionnaire, sont réputées comprises
dans son tarif et ne sont pas facturées séparément (règle appliquée d'office).
Pour une retenue collective, la redevance est due par la structure quel que soit le
volume individuel. Pour une retenue collinaire, la redevance est due au tarif de
catégorie 1 quelle que soit la localisation, y compris en ZRE (art. L213-10-9 du Code de
l'environnement) ; le paramètre d'agence `retenue_hors_zre` ne vise que la retenue par pompage.
L'eau de l'ASA est livrée en bord de parcelle : pas de réseau d'amenée. Pour les autres types d'accès, une distance unique (500 m par défaut) s'applique.
Pour les retenues, la station de reprise vers la parcelle est réputée comprise dans le
coût de construction au m³ stocké.

---

## 6. Limites connues

- **Le bilan n'est pas une marge nette.** Il ne déduit pas les surcoûts de production
  induits par l'irrigation (fertilisation, récolte, séchage) ni les aides couplées.
- **Cultures dont l'irrigation conditionne l'existence** (tomate d'industrie, légumes,
  agrumes, amandier, pommier) : le gain correspond à la quasi-totalité du produit, non à
  un différentiel d'optimisation. Le seuil de rentabilité se lit alors différemment.
- **Redevances des agences de l'eau** : seules Loire-Bretagne et Seine-Normandie portent
  des taux documentés [D]. Adour-Garonne est partiellement renseignée ; Artois-Picardie,
  Rhin-Meuse et Rhône-Méditerranée-Corse portent des valeurs alignées sur Loire-Bretagne,
  taguées [E] et signalées « à remplacer ». À reprendre sur les délibérations 2025 des
  agences avant tout usage en réunion.
- **Taux de subvention** : 70 % par défaut, conformément à la commande. C'est un niveau
  élevé au regard des aides documentées (10 à 40 % du montant HT pour les agences et le
  PCAE). Le curseur permet de tester d'autres hypothèses.
- **Rendements et prix** : documentés pour le maïs, les céréales à paille et la pomme de
  terre ; estimés [E] pour la plupart des autres cultures. Les prix sont volatils et
  doivent être actualisés.
- **Coefficients des matériels** : issus d'un cas type de 30 ha de maïs (Lacroix et al.,
  2015). Le coût à l'hectare varie fortement avec la surface.
- **Durées de vie** : 15 ans pour les équipements et 30 ans pour l'accès à la ressource,
  conformément à la commande, alors que la source d'origine amortit les matériels sur 9 à
  13 ans. L'écart est mentionné dans les info-bulles.
- **Agence de l'eau** : déduite du département, alors que les circonscriptions suivent les
  bassins versants. Corrigeable dans la liste déroulante. Le classement en ZRE est saisi
  par l'utilisateur, faute de couche de référence embarquée.
- **Cartes** : un seul narratif climatique ne représente pas l'incertitude. Les valeurs
  communales sont des moyennes de mailles de 8 km et ne valent pas à l'échelle parcellaire.
- **Effet rebond** : l'amélioration de l'efficience réduit le volume prélevé à surface
  constante, mais peut conduire à étendre les surfaces irriguées ; un plafonnement des
  volumes reste la condition d'une économie d'eau effective (Grafton et al., 2018).

---

## 7. Structure des fichiers

```
app_cout_irrigation/
├── app.py                  routes Flask et API
├── config.py               chemins et options (surchargeables par variables IRRIG_*)
├── requirements.txt
├── moteur/
│   ├── referentiel.py      lecture du classeur, rechargement à chaud, surcharges
│   ├── calcul.py           chaîne de calcul (sans dépendance d'interface)
│   ├── cartes.py           lecture des .tif, extraction communale, rendu PNG
│   └── climat.py           besoin en eau par la méthode SGPE (ETP × Kc − P)
├── referentiel/
│   └── referentiel_irrigation.xlsx
├── carte-violet/            cartes .tif lues par défaut (narratif violet, RCP4.5)
├── cartes/                 ancien jeu de cartes (narratif jaune, RCP8.5), non lu par défaut
├── templates/              gabarits Jinja (DSFR)
├── static/
│   ├── css/app.css
│   ├── js/{projet,carte-commune,cascade}.js
│   ├── vendor/             Leaflet 1.9.4, Chart.js 4.5.1
│   └── dsfr/               Système de Design de l'État 1.15.3
└── tests/
    └── test_application.py
```

Tests de non-régression :

```bash
python -m unittest discover -s tests -v
```

Ils couvrent l'intégrité du référentiel (aucune anomalie, références résolues), la
cohérence du moteur sur toutes les combinaisons culture × ressource × équipement,
l'effet de seuil des machines, le seuil de rentabilité, la subvention, le capital déjà
remboursé, la redevance et les routes de l'application.

---

## 8. Variables d'environnement

| Variable | Défaut | Usage |
|---|---|---|
| `IRRIG_REFERENTIEL` | `referentiel/referentiel_irrigation.xlsx` | autre classeur d'hypothèses |
| `IRRIG_CARTES` | `carte-violet/` | autre dossier de cartes |
| `IRRIG_CLIMAT` | `climate_data.xlsx` | données ETP / précipitations de la méthode SGPE |
| `IRRIG_HORIZON_CLIMAT` | `H1` | horizon climatique de la méthode SGPE (`H1`, `H2` ou `H3`) |
| `IRRIG_COMMUNE_DEFAUT` | `76890` | code postal/INSEE pré-rempli à l'ouverture de la page Projet |
| `IRRIG_DEPARTEMENT_DEFAUT` | `76` | département pré-rempli (départage les homonymes) |
| `IRRIG_CULTURE_DEFAUT` | `Blé tendre` | culture pré-remplie à l'ouverture de la page Projet |
| `IRRIG_DSFR` | `static/dsfr/` | DSFR téléchargé ailleurs |
| `IRRIG_LECTURE_CARTES` | `1` | `0` désactive la lecture des .tif (référentiel seul) |
| `IRRIG_FOND_CARTE` | `1` | `0` supprime les tuiles Plan IGN (aucun appel réseau pour la carte) |
| `IRRIG_HOTE` | `127.0.0.1` | `0.0.0.0` pour exposer sur le réseau local |
| `IRRIG_PORT` | `5000` | port d'écoute |

L'application n'est pas authentifiée : en ligne, toute personne disposant de l'URL y
accède. Elle ne permet que des consultations et des simulations (aucune écriture sur le
serveur).

---

## 9. Déploiement en ligne (accès par URL)

Fichiers prévus pour un hébergeur de type PaaS (Render, Scalingo, Clever Cloud…) :

| Fichier | Rôle |
|---|---|
| `Procfile` | commande de lancement : `gunicorn app:app` sur le port fourni par l'hébergeur |
| `requirements.txt` | dépendances, dont `gunicorn` (installé uniquement sous Linux) |
| `.python-version` | version de Python (3.12) |
| `.gitignore` | fichiers exclus de l'envoi (documentation, classeur de travail, sauvegardes) |

Le référentiel, `climate_data.xlsx` et `carte-violet/` font partie de l'envoi : après
une modification du référentiel, il faut redéployer pour que la version en ligne la prenne
en compte. Au premier démarrage, la lecture de `climate_data.xlsx` prend quelques
secondes (le cache `.npz` est régénéré).
