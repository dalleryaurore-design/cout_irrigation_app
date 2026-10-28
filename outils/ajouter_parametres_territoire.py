# -*- coding: utf-8 -*-
"""
Ajout au référentiel de la feuille « Territoire » (diagnostic du territoire)
============================================================================
Script ponctuel : il crée la feuille « Territoire » (ou n'y ajoute que les paramètres absents si elle existe) (seuils de classement
des indicateurs de ``moteur/territoire.py``, même format que les autres feuilles de paramètres) et
ajoute les références des données territoriales à la feuille « References ». Une copie de
sauvegarde du classeur est faite avant écriture (referentiel/*.backup-AAAAMMJJ.xlsx, ignorée par git).
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from copy import copy

from openpyxl import load_workbook

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSEUR = os.path.join(RACINE, "referentiel", "referentiel_irrigation.xlsx")
MODELE = "Acces_ressource"

# Objet, code, libellé, valeur, unité, variable, min, max, réf., précision
PARAMETRES = [
    ("Tension", "part_zre", "Part de la commune en ZRE au-delà de laquelle la case ZRE est cochée", 0.5, "%",
     "oui", 0, 1, "SGPE_2026", "Part de la surface communale en zone de répartition des eaux de l'origine de l'eau "
     "prélevée (souterraine pour un forage, superficielle sinon)."),
    ("Tension", "jours_restriction_vigilance", "Jours de restriction (alerte renforcée ou crise) : seuil de vigilance",
     10, "j/an", "oui", 0, 365, "SGPE_2026", "Moyenne 2016-2025 des jours au moins en alerte renforcée ; une seule "
     "année avec un jour de crise suffit aussi à signaler une vigilance."),
    ("Tension", "jours_restriction_defavorable", "Jours de restriction (alerte renforcée ou crise) : seuil défavorable",
     30, "j/an", "oui", 0, 365, "SGPE_2026", "Environ un mois par an de restrictions fortes en moyenne."),
    ("Tension", "annees_crise_defavorable", "Années avec au moins un jour de crise : seuil défavorable", 3,
     "ans sur 10", "oui", 0, 10, "SGPE_2026", "Sur les dix années 2016-2025."),
    ("Sol", "ru_faible", "Réserve utile faible en deçà de", 80, "mm", "oui", 0, 400, "RU_FRANCE_2021",
     "Moyenne nationale de l'ordre de 95 mm sur 0-200 cm."),
    ("Sol", "ru_elevee", "Réserve utile élevée au-delà de", 150, "mm", "oui", 0, 400, "RU_FRANCE_2021", ""),
    ("Acces", "distance_cours_eau", "Distance maximale à un cours d'eau permanent pour un pompage", 1000, "m", "oui",
     0, 20000, "SGPE_2026", "Mesurée depuis un point intérieur de la commune ; deux fois la distance d'amenée par "
     "défaut."),
    ("Acces", "distance_cours_eau_large", "Distance maximale à un cours d'eau de plus de 5 m de large", 3000, "m",
     "oui", 0, 20000, "SGPE_2026", ""),
    ("Acces", "distance_canal", "Distance maximale à un canal", 1000, "m", "oui", 0, 20000, "SGPE_2026", ""),
    ("Acces", "sau_irriguee_collectif", "Part de la SAU irriguée signalant un réseau collectif probable", 0.2, "%",
     "oui", 0, 1, "SGPE_2026", "Recensement agricole 2020 ; moyenne nationale ≈ 6 % des communes renseignées."),
    ("Acces", "rang_aquifere_max", "Rang maximal de la première nappe pour un forage peu profond", 2, "rang", "oui",
     1, 10, "SGPE_2026", "1 = nappe affleurante, 2 = sous une première formation (BDLISA, niveau local)."),
    ("Projections", "baisse_debit_vigilance", "Baisse du débit (2041-2070) ou de la recharge (+2,7 °C) : seuil de vigilance", -10, "%", "oui",
     -100, 0, "EXPLORE2_2025", "Changement médian par rapport à 1976-2005 (Explore2, RCP4.5) du débit d'étiage, "
     "d'été ou d'hiver à la station la plus proche ; horizon de la durée d'amortissement des ouvrages."),
    ("Projections", "baisse_debit_defavorable", "Baisse du débit (2041-2070) ou de la recharge (+2,7 °C) : seuil défavorable", -30, "%", "oui",
     -100, 0, "EXPLORE2_2025", "Ordre de grandeur de la baisse médiane des étiages projetée dans le sud de la France."),
    ("Projections", "hausse_besoin_vigilance", "Hausse du besoin en eau entre 2021-2050 et 2071-2100 : vigilance",
     0.1, "%", "oui", 0, 1, "SGPE_2026", "Besoin d'irrigation de la méthode SGPE (DRIAS, RCP4.5)."),
]

REFERENCES = [
    ("SANDRE_ZRE", "Sandre, 2025a",
     "Sandre. (2025). Zones de répartition des eaux (ZRE) [Jeu de données géographiques]. Service d'administration "
     "nationale des données et référentiels sur l'eau, Office français de la biodiversité.",
     "https://www.sandre.eaufrance.fr/atlas/srv/fre/catalog.search#/metadata/e5325942-18f6-472c-973a-1f35bb207eb0"),
    ("SANDRE_BASSINS", "Sandre, 2025b",
     "Sandre. (2025). Circonscriptions administratives de bassin [Jeu de données géographiques]. Service "
     "d'administration nationale des données et référentiels sur l'eau.",
     "https://www.sandre.eaufrance.fr/atlas/srv/fre/catalog.search#/home"),
    ("SANDRE_SAGE", "Sandre, 2025c",
     "Sandre. (2025). Schémas d'aménagement et de gestion des eaux (SAGE) [Jeu de données géographiques]. Service "
     "d'administration nationale des données et référentiels sur l'eau.",
     "https://www.sandre.eaufrance.fr/atlas/srv/fre/catalog.search#/home"),
    ("VIGIEAU_2026", "Ministère de la Transition écologique, 2026",
     "Ministère de la Transition écologique. (2026). Donnée sécheresse VigiEau : historique des restrictions par "
     "commune depuis 2010 [Jeu de données]. data.gouv.fr.",
     "https://www.data.gouv.fr/datasets/donnee-secheresse-vigieau"),
    ("AGRESTE_RA2020", "Agreste, 2022",
     "Agreste. (2022). Recensement agricole 2020 : part de la superficie irriguée dans la SAU, par commune "
     "[Jeu de données]. Ministère de l'Agriculture et de la Souveraineté alimentaire.",
     "https://agreste.agriculture.gouv.fr/agreste-web/disaron/RA2020_CARTO/detail/"),
    ("BDTOPAGE", "IGN & OFB, 2026",
     "IGN, & Office français de la biodiversité. (2026). BD TOPAGE : tronçons hydrographiques, France "
     "métropolitaine [Jeu de données géographiques]. Sandre.",
     "https://www.sandre.eaufrance.fr/atlas/srv/fre/catalog.search#/home"),
    ("BDLISA", "BRGM, 2025",
     "BRGM. (2025). BDLISA, référentiel hydrogéologique français : entités hydrogéologiques de niveau local, France "
     "métropolitaine [Jeu de données géographiques].", "https://bdlisa.eaufrance.fr/"),
    ("ROE_OFB", "OFB, 2025",
     "Office français de la biodiversité. (2025). Référentiel des obstacles à l'écoulement (ROE) [Jeu de données "
     "géographiques]. Sandre.", "https://www.sandre.eaufrance.fr/atlas/srv/fre/catalog.search#/home"),
]


def main(chemin: str = CLASSEUR) -> None:
    wb = load_workbook(chemin)
    modele = wb[MODELE]
    ncol = 10
    if "Territoire" in wb.sheetnames:
        # Feuille déjà créée : seuls les paramètres absents sont ajoutés, les valeurs saisies sont conservées
        ws = wb["Territoire"]
        presents = {(ws.cell(r, 1).value, ws.cell(r, 2).value) for r in range(2, ws.max_row + 1)}
        nouveaux = [p for p in PARAMETRES if (p[0], p[1]) not in presents]
    else:
        ws = wb.create_sheet("Territoire", index=wb.sheetnames.index(MODELE) + 1)
        for c in range(1, ncol + 1):
            src, dst = modele.cell(1, c), ws.cell(1, c)
            dst.value, dst._style = src.value, copy(src._style)
            lettre = src.column_letter
            if lettre in modele.column_dimensions:
                ws.column_dimensions[lettre].width = modele.column_dimensions[lettre].width
        ws.freeze_panes = "A2"
        nouveaux = PARAMETRES
    if not nouveaux:
        sys.exit("Paramètres déjà présents : rien à faire.")
    sauvegarde = chemin.replace(".xlsx", f".backup-{time.strftime('%Y%m%d-%H%M')}.xlsx")
    shutil.copy2(chemin, sauvegarde)
    style_ligne = [copy(modele.cell(2, c)._style) for c in range(1, ncol + 1)]
    debut = ws.max_row + 1
    for r, ligne in enumerate(nouveaux, start=debut):
        for c, v in enumerate(ligne, start=1):
            cell = ws.cell(r, c)
            cell.value = v
            cell._style = copy(style_ligne[c - 1])

    wr = wb["References"]
    existants = {wr.cell(r, 1).value for r in range(2, wr.max_row + 1)}
    modele_ref = [wr.cell(wr.max_row, c) for c in range(1, 5)]
    for ident, courte, complete, url in REFERENCES:
        if ident in existants:
            continue
        r = wr.max_row + 1
        for c, v in enumerate((ident, courte, complete, url), start=1):
            wr.cell(r, c).value = v
            wr.cell(r, c)._style = copy(modele_ref[c - 1]._style)
    for t in wr.tables.values():
        t.ref = f"A1:{t.ref.split(':')[1].rstrip('0123456789')}{wr.max_row}"
    wb.save(chemin)
    print(f"Feuille « Territoire » : {len(nouveaux)} paramètre(s) ajouté(s) ; sauvegarde : {sauvegarde}")


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
