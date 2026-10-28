# Analyse financière d'un système d'irrigation

Application web locale (Flask + Système de Design de l'État) qui estime, à l'échelle
d'une commune, le **coût annuel** et la **rentabilité** d'un projet d'irrigation :
bilan agronomique, décomposition du coût par poste et graphique en cascade. Chaque hypothèse est sourcée : la source apparaît en info-bulle au survol
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

### Icône de l'onglet du navigateur

L'icône (favicon) est lue dans `static/favicon/` : `favicon.svg` (navigateurs récents),
`favicon.ico` (32 × 32, anciens navigateurs) et `apple-touch-icon.png` (180 × 180, iOS). Pour la
changer, remplacez ces trois fichiers en gardant leurs noms, puis rechargez la page
(Ctrl + F5 : les navigateurs gardent l'icône en cache).

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

L'application compte quatre volets (menu principal) :

| Volet | Onglets | Usage |
|---|---|---|
| **Simulations exemples** (`/exemples`) | Simulation · Exemples | simulation pré-remplie sur l'un des six exemples du référentiel (`?exemple=N`) ; l'ancienne adresse `/projet` y redirige |
| **Cas personnel – parcelle** (`/parcelle`, accueil) | — | simulation d'une parcelle où rendements, besoin en eau, réserve utile du sol, coûts, énergie et redevance se saisissent directement ; boutons « Télécharger le rapport (PDF) », « Télécharger mes variables (Excel) », « Importer mes variables » |
| **Comparaison de trajectoires** (`/trajectoires`, en construction) | — | deux ou trois scénarios pour un même lieu et une même surface (culture, équipement, ressource, horizon climatique H1/H2/H3, couverture du besoin) |
| **Références** (`/references`) | Cultures · Équipement · Accès à la ressource en eau · Ressources · Références · Méthodologie | hypothèses du référentiel en lecture seule (sources au survol), bibliographie, méthode résumée et téléchargement de la méthodologie détaillée (`?onglet=methode`) |

**Encadrés du bilan économique.** Bilan avec subvention (et sans, en ligne secondaire) ;
coût de l'irrigation avec subvention, décomposé en **charges fixes** (annuités, maintenance du
matériel, part fixe du tarif : dues chaque année) et **charges variables** (énergie, redevance,
part volumétrique, main-d'œuvre) ; coût sans subvention et aide publique annualisée ;
investissement initial, réparti entre l'agriculteur et l'aide publique.

**Saisie directe (Cas personnel).** Les rendements et le besoin en eau sont des champs de saisie
dans les encadrés du bilan agronomique : ils affichent la valeur calculée (carte, méthode SGPE ou
référentiel) tant qu'on ne les modifie pas. Le tableau « Mes hypothèses », sous le formulaire,
regroupe les coûts d'investissement et charges opérationnelles du matériel et de l'accès à la
ressource choisis, un prix unique de l'énergie (€/m³), un taux unique de redevance (c€/m³, par
défaut celui de l'agence, de la catégorie et de l'origine de l'eau) et les paramètres du bilan
hydrique (réserve utile du sol, profondeur de sol, enracinement, fraction p, épuisement initial).
Toute valeur est modifiable, sans les bornes Min/Max du référentiel (clé `*libre` des surcharges,
`moteur/referentiel.py::CLE_LIBRE`) ; vider un champ rétablit sa valeur par défaut.
Le classeur téléchargé (`moteur/export.py`) contient les choix (feuille Simulation), les variables
(valeur du référentiel et « Ma valeur ») et les résultats ; modifié dans Excel, il se réimporte.
Le rapport PDF (`moteur/rapport.py`, police Marianne de `static/fonts/`) reprend la parcelle, les
bilans avec et sans subvention, la décomposition et les variables modifiées.

**Couverture partielle du besoin (Comparaison de trajectoires).** Volume et gain de rendement réduits
dans la même proportion (hypothèse simplificatrice).

L'ancien mode exploitation (plusieurs parcelles, ressource partagée) a été supprimé ; l'adresse
`/exploitation` redirige vers le cas personnel.

### Formulaire de simulation d'une parcelle

**Onglet Simulation.** Renseignez la commune, la culture, la surface, la ressource en
eau et l'équipement : les résultats se recalculent à chaque modification. Au chargement
de la page (hors exemple pré-rempli), la commune et la culture sont pré-remplies avec les
valeurs de `COMMUNE_DEFAUT` / `DEPARTEMENT_DEFAUT` / `CULTURE_DEFAUT` de `config.py`
(par défaut : Saint-Ouen-du-Breuil, 76890, blé tendre), modifiable via les variables
d'environnement `IRRIG_COMMUNE_DEFAUT`, `IRRIG_DEPARTEMENT_DEFAUT`, `IRRIG_CULTURE_DEFAUT`.

- *Prix de vente* : **prix de marché** du référentiel (`prix_vente` : prix payés aux
  producteurs FranceAgriMer, moyenne olympique 2020/21-2024/25, pour les grandes cultures),
  dans tous les volets. Modifiable ; le bouton « Valeur par défaut » le rétablit. Le barème
  MASAA de l'assurance récolte (`prix_masaa`) reste dans le référentiel mais n'est plus proposé.
- *Choix automatique de la méthode* (`app.py::_valeurs_agro`) : besoin en eau par **SGPE**,
  sinon **MAELIA**, sinon **référentiel** ; rendements par **MAELIA**, sinon **référentiel**.
  La source retenue est indiquée sous le résultat ; le bouton « i » à côté de la valeur ouvre
  une bulle avec la méthode retenue, sa source et les valeurs des autres méthodes. La case
  *Rendement pluvial par la méthode SGPE (exploratoire)* applique la relation de la FAO (Ky).
  Un avertissement s'affiche si le besoin dépasse `besoin_plausible_max` (450 mm). L'API
  accepte encore `methode_besoin` / `methode_rendement` = `sgpe`, `carte` ou `reference`
  pour imposer une méthode (placée en tête de l'ordre). La méthode
  SGPE est un bilan hydrique journalier du sol de type CROPWAT (voir § 5) : Kc mensuels du
  référentiel (codes `kc_01` à `kc_12`, feuille Cultures), ETP et P de `climate_data.xlsx` au
  point de grille le plus proche du centre de la commune (horizon `IRRIG_HORIZON_CLIMAT`, H1 par
  défaut), réserve utile du sol de `sol/ru_sol_1km.tif`. En l'absence de Kc ou de donnée
  climatique, la valeur du référentiel s'applique.
  La lecture du classeur étant lente, un cache `climate_data.cache.npz` est créé à côté,
  reconnu par l'empreinte du fichier (pas par sa date de modification).
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
- Les couches couleur des cartes MAELIA ne sont plus proposées sur la carte de la
  simulation ; l'API `GET /api/carte-variable/<culture>/<variable>` (image PNG, voir
  `moteur/cartes.py::carte_variable`) reste disponible.

**Diagnostic du territoire** (sous le formulaire, `moteur/territoire.py`). Quatre fiches d'indicateurs pour la
commune, classés favorable / vigilance / défavorable d'après les seuils de la feuille `Territoire` du référentiel,
source au survol :
- *Tension sur la ressource* : part de la commune en ZRE (Sandre), jours de restriction sécheresse par an
  (moyenne 2016-2025, VigiEau), SAGE ;
- *Usages concurrents et ouvrages* : ouvrages hydroélectriques, d'eau potable et d'irrigation (ROE), part de la
  SAU irriguée en 2020 (Agreste) ;
- *Sol et sous-sol* : réserve utile et profondeur de la simulation, formation affleurante (BDLISA) ;
- *Projections hydroclimatiques* (RCP4.5, 2021-2050 → 2041-2070 → 2071-2100) : besoin en eau de la culture
  (méthode SGPE) et bilan P − ETP d'avril à septembre et excédent hivernal (`climate_data.xlsx`, DRIAS) ;
  changement du débit d'étiage (QMNA), d'été et d'hiver par rapport à 1976-2005 à la station Explore2 la plus
  proche (médiane et fourchette 10-90 % des simulations, chaînes aberrantes exclues). Les débits sont classés à
  l'horizon 2041-2070 (durée d'amortissement des ouvrages) et pèsent sur le classement du pompage en cours
  d'eau (étiage) et de la retenue par pompage (hiver) ; recharge potentielle annuelle de la masse d'eau
  souterraine (Explore2, modèle RECHARGE, 17 projections) aux niveaux de réchauffement de la TRACC +2 / +2,7 /
  +4 °C par rapport à 1976-2005, classée à +2,7 °C et prise en compte pour le forage ;
- *Accès à l'eau* : cours d'eau permanent, cours d'eau de plus de 5 m et canal les plus proches (BD TOPAGE),
  première nappe (BDLISA), puis classement des types d'accès du référentiel ; le bouton « Simuler avec… »
  applique le mieux classé. Distances mesurées depuis un point intérieur de la commune ; relief non pris en compte.

Au choix de la commune, l'agence de l'eau est déduite du **bassin** (circonscriptions Sandre), et non plus du
département, et la case ZRE est cochée si la commune est en ZRE pour l'origine de l'eau prélevée (souterraine pour
un forage, superficielle sinon), tant que l'utilisateur ne l'a pas modifiée. Une ZRE souterraine peut ne viser
qu'une nappe captive profonde (Albien) : son nom est rappelé sous la case.

Les indicateurs sont lus dans `territoire/indicateurs_communes.csv` (déployé), produit à partir des données brutes
de `territoire/brut/` (non déployées, liste dans l'en-tête du script) par :

    python outils/preparer_territoire.py            # toutes les étapes (une dizaine de minutes)
    python outils/preparer_territoire.py nappes     # une étape, puis l'assemblage

(dépendances de préparation seulement : `pip install geopandas pyogrio pandas`). La feuille `Territoire` et les
références des données ont été ajoutées par `outils/ajouter_parametres_territoire.py` (script ponctuel).

**Onglets Équipement, Accès à la ressource, Ressources.** Les hypothèses en coulisse.
Les valeurs marquées « Variable » dans le référentiel sont des champs de saisie : leur
modification s'applique immédiatement à la simulation et le champ se souligne en bleu.
Le bouton « Rétablir les valeurs du référentiel » annule toutes les surcharges. Les
cellules grisées sont calculées à partir des autres.

Le tableau de l'onglet Équipement affiche, par équipement : CAPEX (€/ha), durée de vie,
taux d'amortissement annuel, annuité brute (€/ha/an, avant subvention),
coût de main-d'œuvre (€/ha/an), coût de maintenance (€/ha/an), coût annuel total
(€/ha/an, somme des trois précédents, avant subvention) et efficience d'application.
La subvention au matériel n'est appliquée que dans la simulation, au seul CAPEX
(taux saisi sous « Subvention publique ») ; la maintenance et la main-d'œuvre n'en
bénéficient pas.

### Volet Exemples

Six situations types. Un clic ouvre le projet pré-rempli, modifiable ensuite.

### Volet Références

Valeurs par défaut des cultures (onglet Cultures), hypothèses des équipements, de l'accès à
la ressource et des redevances, bibliographie complète au format APA, méthode de calcul et
limites de lecture.

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
| `Cultures` | 24 cultures × rendement irrigué, rendement pluvial, besoin d'irrigation, prix de vente, Kc mensuels, profondeur d'enracinement maximale (`zr_max`) et fraction p (`p_fao`) ; objet `Général` : réserve utile par défaut, profondeur de sol, enracinement au semis, épuisement initial |
| `Equipement` | 6 matériels × CAPEX, efficience, main-d'œuvre, maintenance, durée de vie ; paramètres généraux (taux d'actualisation, taux de subvention du matériel) |
| `Acces_ressource` | 5 types d'accès (forage, cours d'eau, retenue collinaire, retenue par pompage, ASA) × investissement, part fixe et volumétrique, distance d'amenée, durées de vie ; paramètres généraux (subvention, réseau d'amenée, taux d'actualisation) |
| `Ressources` | redevances des 6 agences de l'eau, seuils d'assujettissement, prix de l'énergie |
| `Cartes` | déclaration des fichiers .tif par culture |
| `Exemples` | les six exemples pré-remplis |
| `Departements` | rattachement département → agence de l'eau |
| `References` | bibliographie APA (identifiant, citation courte, référence complète, URL, statut) |

### Colonnes des feuilles de paramètres

`Objet | Code paramètre | Libellé | Valeur | Unité | Variable | Min | Max | Réf. | Précision`

Les colonnes sont repérées par leur en-tête (et non par leur position) : en ajouter ou en
déplacer une ne perturbe pas la lecture.

- **Valeur** : seule colonne à modifier couramment. Les pourcentages se saisissent en
  décimal (0,85 pour 85 %).
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

**Unités.** Les colonnes `Unité rendement` et `Unité besoin` acceptent `auto`, `%`, `t/ha`,
`q/ha`, `kg/ha`, `mm`, `m3/ha`. En mode `auto`, l'unité inscrite dans le fichier
(étiquette `UNITS` du GeoTIFF) est retenue ; à défaut, elle est déduite par comparaison
avec la valeur de référence de la culture, et l'info-bulle indique « unité déduite ».

**Rendements en %.** Les cartes de rendement MAELIA (`*_pot_*.tif`, `UNITS = %`) donnent
un pourcentage du rendement potentiel (modèle AqYield : rendement = effet du stress
hydrique × rendement optimal). Elles sont converties en q/ha :
`rendement = % ÷ 100 × rendement potentiel`. Le rendement potentiel est la ligne
`RENDEMENT_OPTIMAL` (t/ha) de `especesCultivees.csv` pour le code de la carte (colonne
`maisT`, `BTH`…, comparaison insensible à la casse ; chemin modifiable par `IRRIG_ESPECES`),
et à défaut le rendement irrigué de la feuille `Cultures`.

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
```

**Besoin en eau, méthode SGPE** (`moteur/climat.py::bilan_hydrique`) : bilan hydrique journalier
de la zone racinaire, sur le modèle du calendrier d'irrigation de CROPWAT (FAO-56, chapitre 8) :

```
Dr(j)  = Dr(j−1) − Peff(j) + Kc × ETP(j) − I(j)            épuisement de la réserve (mm)
TAW(j) = RU × min(Zr(j), profondeur de sol) ÷ profondeur de sol
RAW(j) = p × TAW(j),  p = p_FAO + 0,04 × (5 − ETc), borné à [0,1 ; 0,8]
I(j)   = Dr(j) si Dr(j) > RAW(j)   (en fin de cycle : limité au strict nécessaire jusqu'à la récolte)
besoin net (mm) = Σ I(j)
Peff   = P × (125 − 0,2 P) ÷ 125 si P ≤ 250 mm, sinon 125 + 0,1 P    (USDA S.C.S., mensuel)
Zr     : de zr_ini (0,25 m) au semis à zr_max au pic de Kc, proportionnellement au Kc
```

RU : réservoir utile de la commune, sommé sur la profondeur de sol estimée, au plus 2 m
(Román Dobarco et al., 2021, doi:10.15454/9IRARJ ; `sol/ru_sol_1km.tif`), sinon `ru_defaut` ;
profondeur de sol : classes BDGSF 0,3 / 0,5 / 1 / 2 m (`sol/profondeur_sol_1km.tif`, produite par
`Rscript outils/preparer_profondeur.R`), sinon `profondeur_sol` ; état initial : `depletion_initiale`
(0 % = capacité au champ). Cultures pérennes : une année de mise en route. Climat mensuel réparti
uniformément sur les jours du mois. RU et profondeur sont saisissables dans « Mes hypothèses ».

**Rendements, méthode SGPE** : rendement irrigué (Ym) du référentiel ; rendement pluvial
`Ym × (1 − Ky × (1 − ETa/ETc))` (FAO-33, `ky` de la feuille Cultures), ETa/ETc venant du même bilan
hydrique conduit sans irrigation. Les rendements comme le besoin en eau proposent trois méthodes :
SGPE, MAELIA (cartes), Référence ; la méthode SGPE des rendements est une option exploratoire.

**Paramètres des cultures** : FAO-56 par défaut ; jeux SB2023 du package CropWat (calés pour MAELIA) pour
le tournesol, le soja et le colza (`outils/kc_sb2023.R` puis `outils/appliquer_kc_sb2023.py`), retenus
parce que leur besoin moyen est le plus proche de la moyenne MAELIA / référentiel ; le triticale reprend
les paramètres du blé tendre.

**Note méthodologique** : rédigée dans Word, `docs/methodologie_irrigation.docx` (Garamond, format
article). L'application sert son export PDF, `docs/methodologie_irrigation.pdf`, par
`GET /api/methodologie-pdf` (bouton « Télécharger la méthodologie » en tête de l'onglet Références > Méthodologie). Après
chaque modification du Word, régénérer le PDF :

    python outils/exporter_methodologie.py

(export par Word, sinon LibreOffice ; on peut aussi faire Fichier > Enregistrer sous > PDF dans Word, au
même emplacement). Les tableaux du Word (Kc, rendements, prix, validation…) ne sont pas mis à jour
automatiquement : les reporter à la main si le référentiel change. Si le PDF est absent, l'application
génère à la place la méthodologie de `moteur/methodologie.py` à partir du référentiel et de
`validation/comparaison.csv`.

**Validation** (`python outils/comparer_modeles.py [n points]`, R et package CropWat d'INRAE requis :
`install.packages("CropWat", repos = "https://inrae.r-universe.dev")`) : compare, sur un échantillon de
points DRIAS × cultures ayant des cartes MAELIA, la méthode SGPE au moteur CropWat alimenté par les
mêmes entrées, à CropWat avec ses propres paramètres de culture, et aux cartes MAELIA. Résultats dans
`validation/synthese.md` et `validation/comparaison.csv`.

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
  un différentiel d'optimisation. Le bilan se lit alors différemment.
- **Redevances des agences de l'eau** : seules Loire-Bretagne et Seine-Normandie portent
  des taux documentés. Adour-Garonne est partiellement renseignée ; Artois-Picardie,
  Rhin-Meuse et Rhône-Méditerranée-Corse portent des valeurs alignées sur Loire-Bretagne,
  signalées « à remplacer ». À reprendre sur les délibérations 2025 des
  agences avant tout usage en réunion.
- **Taux de subvention** : 70 % par défaut, conformément à la commande. C'est un niveau
  élevé au regard des aides documentées (10 à 40 % du montant HT pour les agences et le
  PCAE). Le curseur permet de tester d'autres hypothèses.
- **Rendements et prix** : documentés pour le maïs, les céréales à paille et la pomme de
  terre ; estimés pour la plupart des autres cultures. Les prix sont volatils et
  doivent être actualisés.
- **Coefficients des matériels** : issus d'un cas type de 30 ha de maïs (Lacroix et al.,
  2015). Le coût à l'hectare varie fortement avec la surface.
- **Durées de vie** : 15 ans pour les équipements et 30 ans pour l'accès à la ressource,
  conformément à la commande, alors que la source d'origine amortit les matériels sur 9 à
  13 ans. L'écart est mentionné dans les info-bulles.
- **Agence de l'eau et ZRE** : déduites de la commune (bassin et zones de répartition des eaux du Sandre,
  voir « Diagnostic du territoire ») ; à défaut de données pour la commune, agence déduite du département.
  Corrigeables dans le formulaire.
- **Diagnostic du territoire** : échelle communale (point intérieur de la commune pour les distances), relief
  et périmètres des ASA non pris en compte ; restrictions au niveau le plus sévère des zones d'alerte qui
  touchent la commune.
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
│   ├── calcul.py           chaîne de calcul d'une parcelle (simuler)
│   ├── cartes.py           lecture des .tif, extraction communale, rendu PNG
│   ├── climat.py           besoin en eau par la méthode SGPE (bilan hydrique type CROPWAT)
│   ├── sol.py              réserve utile du sol à la commune
│   ├── export.py           variables par catégorie, classeur Excel des variables (export et import)
│   └── rapport.py          rapport PDF d'une parcelle (fpdf2)
├── referentiel/
│   └── referentiel_irrigation.xlsx
├── carte-violet/            cartes .tif lues par défaut (narratif violet, RCP4.5)
├── sol/ru_sol_1km.tif       réserve utile 0-200 cm à 1 km (produite depuis AWCr_mm_0_200.tif)
├── sol/profondeur_sol_1km.tif profondeur de sol (m, BDGSF), produite depuis bdgsf_classe_prof/
├── outils/                 preparer_sol.py, preparer_profondeur.R (cartes de sol), ajouter_parametres_sol.py,
│                           ajouter_ky.py (ponctuels), comparer_modeles.py + cropwat_comparaison.R (validation)
├── validation/             résultats de la comparaison SGPE / CropWat / MAELIA (synthese.md)
├── cartes/                 ancien jeu de cartes (narratif jaune, RCP8.5), non lu par défaut
├── templates/              gabarits Jinja (DSFR) : parcelle, exemples, trajectoires,
│                           references ; _simulation.html (formulaire partagé), _localisation.html
├── static/
│   ├── css/app.css
│   ├── fonts/              Marianne en TTF (rapport PDF)
│   ├── js/{projet,carte-commune,cascade}.js   simulation d'une parcelle
│   ├── js/{trajectoires,commune,tableaux}.js
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
l'effet de seuil des machines, le seuil de rentabilité (calcul moteur), le bilan hydrique SGPE,
les saisies directes du volet Cas personnel, la subvention, le capital déjà
remboursé, la redevance et les routes de l'application.

---

## 8. Variables d'environnement

| Variable | Défaut | Usage |
|---|---|---|
| `IRRIG_REFERENTIEL` | `referentiel/referentiel_irrigation.xlsx` | autre classeur d'hypothèses |
| `IRRIG_CARTES` | `carte-violet/` | autre dossier de cartes |
| `IRRIG_CLIMAT` | `climate_data.xlsx` | données ETP / précipitations de la méthode SGPE |
| `IRRIG_SOL_RU` | `sol/ru_sol_1km.tif` | carte de réserve utile du sol (mm) ; à défaut, `AWCr_mm_0_200.tif` |
| `IRRIG_TERRITOIRE` | `territoire/indicateurs_communes.csv` | indicateurs du diagnostic du territoire |
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

Le référentiel, `climate_data.xlsx`, `carte-violet/` et `sol/ru_sol_1km.tif` font partie de
l'envoi (la carte d'origine `AWCr_mm_0_200.tif`, 640 Mo, est exclue par `.gitignore`) : après
une modification du référentiel, il faut redéployer pour que la version en ligne la prenne
en compte. Le cache `climate_data.cache.npz` est réutilisé tant que le contenu du
classeur ne change pas ; un simple redéploiement ne relance pas sa lecture.
