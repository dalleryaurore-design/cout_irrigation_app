# -*- coding: utf-8 -*-
"""
Configuration de l'application
==============================
Toutes les options peuvent aussi être fixées par variable d'environnement.
"""
import os

RACINE = os.path.dirname(os.path.abspath(__file__))

# Référentiel Excel (source unique des hypothèses)
REFERENTIEL = os.environ.get("IRRIG_REFERENTIEL", os.path.join(RACINE, "referentiel", "referentiel_irrigation.xlsx"))

# Dossier des cartes .tif (besoins en eau et rendements). « carte-violet » couvre
# toutes les cultures disponibles (narratif violet, RCP4.5) ; l'ancien dossier
# « cartes » (narratif jaune, RCP8.5, blé tendre seul) n'est plus utilisé par défaut.
DOSSIER_CARTES = os.environ.get("IRRIG_CARTES", os.path.join(RACINE, "carte-violet"))

# Paramètres des espèces du modèle MAELIA (une colonne par code de culture des cartes).
# Sa ligne RENDEMENT_OPTIMAL (t/ha) donne le rendement potentiel auquel se rapportent les
# cartes de rendement, exprimées en % de ce potentiel ; à défaut (NA), le rendement irrigué
# du référentiel en tient lieu.
ESPECES_CULTIVEES = os.environ.get("IRRIG_ESPECES", os.path.join(RACINE, "especesCultivees.csv"))

# Données climatiques mensuelles (ETP, précipitations) de la méthode SGPE, et horizon
# retenu : H1 (2021-2050, cohérent avec les cartes 2020-2040), H2 (2041-2070) ou H3 (2071-2100).
CLIMAT = os.environ.get("IRRIG_CLIMAT", os.path.join(RACINE, "climate_data.xlsx"))
HORIZON_CLIMAT = os.environ.get("IRRIG_HORIZON_CLIMAT", "H1").strip().upper()

# Réserve utile des sols (mm, 0-200 cm) du bilan hydrique de la méthode SGPE : carte allégée à
# 1 km produite par outils/preparer_sol.py, sinon la carte d'origine à 90 m (640 Mo, non déployée).
SOL_RU = os.environ.get("IRRIG_SOL_RU", os.path.join(RACINE, "sol", "ru_sol_1km.tif"))
SOL_RU_ORIGINE = os.path.join(RACINE, "AWCr_mm_0_200.tif")
# Profondeur de sol (m) : couche BDGSF bdgsf_classe_prof rasterisée à 1 km par outils/preparer_profondeur.R
SOL_PROFONDEUR = os.environ.get("IRRIG_SOL_PROFONDEUR", os.path.join(RACINE, "sol", "profondeur_sol_1km.tif"))

# Résultats de la validation des méthodes (outils/comparer_modeles.py) : onglet Références et méthodologie PDF
VALIDATION = os.environ.get("IRRIG_VALIDATION", os.path.join(RACINE, "validation", "comparaison.csv"))

# Note méthodologique : rédigée dans Word, l'application sert son export PDF (outils/exporter_methodologie.py)
METHODOLOGIE_DOCX = os.path.join(RACINE, "docs", "methodologie_irrigation.docx")
METHODOLOGIE_PDF = os.environ.get("IRRIG_METHODOLOGIE", os.path.join(RACINE, "docs", "methodologie_irrigation.pdf"))

# Localisation et culture pré-sélectionnées à l'ouverture de la page Projet.
COMMUNE_DEFAUT = os.environ.get("IRRIG_COMMUNE_DEFAUT", "76890")
DEPARTEMENT_DEFAUT = os.environ.get("IRRIG_DEPARTEMENT_DEFAUT", "76")
CULTURE_DEFAUT = os.environ.get("IRRIG_CULTURE_DEFAUT", "Blé tendre")

# Lecture des cartes. IRRIG_LECTURE_CARTES=0 la désactive entièrement : les valeurs
# agronomiques proviennent alors du seul référentiel et rasterio n'est jamais chargé.
# À utiliser si la lecture des .tif ralentit l'application sur le poste.
LECTURE_CARTES = os.environ.get("IRRIG_LECTURE_CARTES", "1").strip() not in ("0", "non", "false")

# Fond de carte Plan IGN. IRRIG_FOND_CARTE=0 affiche la commune sans tuiles : utile
# derrière un proxy lent ou bloquant, la localisation restant lisible.
FOND_CARTE = os.environ.get("IRRIG_FOND_CARTE", "1").strip() not in ("0", "non", "false")

# Système de Design de l'État (DSFR) téléchargé sur le poste.
# Indiquer le dossier « dist » de l'archive téléchargée (il contient dsfr/dsfr.min.css,
# fonts/, icons/ et utility/), ou copier ce contenu dans static/dsfr/.
DSFR_DIR = os.environ.get("IRRIG_DSFR", os.path.join(RACINE, "static", "dsfr"))

# Repli si le DSFR local est introuvable (nécessite un accès à internet)
DSFR_CDN = "https://cdn.jsdelivr.net/npm/@gouvfr/dsfr@1.15.3/dist"

# Serveur local
HOTE = os.environ.get("IRRIG_HOTE", "127.0.0.1")
PORT = int(os.environ.get("IRRIG_PORT", "5000"))

# Libellés
TITRE = "Analyse financière d'un système d'irrigation"
SOUS_TITRE = ""
OPERATEUR = "Secrétariat général à la planification écologique"
