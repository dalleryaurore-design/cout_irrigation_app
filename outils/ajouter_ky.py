# -*- coding: utf-8 -*-
"""
Ajout au référentiel du coefficient de réponse du rendement à l'eau (Ky) et des références
=========================================================================================
Script ponctuel : insère ``ky`` (FAO-33, saison entière) après ``p_fao`` pour chaque culture,
renomme la référence de la carte de réserve utile (jeu de données Recherche Data Gouv, 2021),
ajoute les références FAO-33 et BDGSF (profondeur de sol). Sauvegarde préalable du classeur.
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

# Ky saisonnier, Doorenbos & Kassam (1979, FAO-33, tableau 24) ; « estimé » quand FAO-33 ne donne pas la culture.
KY = {
    "Abricot": (1.0, "Non tabulé par FAO-33 : valeur neutre retenue pour les fruitiers (estimation)."),
    "Betterave": (1.0, "Betterave sucrière : 1,0 (FAO-33)."),
    "Agrumes": (1.1, "Agrumes : 1,1-1,3 (FAO-33), borne basse."),
    "Luzerne": (1.1, "Luzerne : 1,1 (FAO-33)."),
    "Amande": (1.0, "Non tabulé par FAO-33 : valeur neutre retenue pour les fruitiers (estimation)."),
    "Tomates industrielles": (1.05, "Tomate : 1,05 (FAO-33)."),
    "Sorgho": (0.9, "Sorgho : 0,9 (FAO-33)."),
    "Blé dur": (1.05, "Blé : 1,05 (FAO-33)."),
    "Blé tendre": (1.0, "Blé d'hiver : 1,0 (FAO-33)."),
    "Maïs": (1.25, "Maïs : 1,25 (FAO-33)."),
    "Colza": (1.0, "Non tabulé par FAO-33 : assimilé aux céréales d'hiver (estimation)."),
    "Orge": (1.0, "Assimilée au blé d'hiver : 1,0 (FAO-33)."),
    "Légumes frais": (1.1, "Légumes (poivron, oignon, pastèque) : 1,1 (FAO-33)."),
    "Olive": (0.8, "Non tabulé par FAO-33 : espèce tolérante à la sécheresse (estimation)."),
    "Soja": (0.85, "Soja : 0,85 (FAO-33)."),
    "Pomme de terre": (1.1, "Pomme de terre : 1,1 (FAO-33)."),
    "Pomme": (1.0, "Non tabulé par FAO-33 : valeur neutre retenue pour les fruitiers (estimation)."),
    "Tournesol": (0.95, "Tournesol : 0,95 (FAO-33)."),
    "Vigne": (0.85, "Vigne : 0,85 (FAO-33)."),
    "Légumes d'industrie": (1.15, "Haricot, pois : 1,15 (FAO-33)."),
}

REFERENCES = {
    "RU_FRANCE_2021": ("Román Dobarco et al., 2021",
                       "Román Dobarco, M., Bourennane, H., Arrouays, D., Saby, N., Cousin, I., & Martin, M. P. (2021). "
                       "Réservoir utile des sols de la France métropolitaine [Jeu de données]. Recherche Data Gouv.",
                       "https://doi.org/10.15454/9IRARJ"),
    "FAO_33": ("Doorenbos & Kassam, 1979",
               "Doorenbos, J., & Kassam, A. H. (1979). Yield response to water (FAO Irrigation and Drainage Paper "
               "No. 33). Food and Agriculture Organization of the United Nations.", ""),
    "BDGSF_1998": ("INRA, 1998",
                   "INRA. (1998). Base de données géographique des sols de France à 1/1 000 000 (version 3.2.8.0). "
                   "INRA, US InfoSol.", ""),
}


def main(chemin: str = CLASSEUR) -> None:
    shutil.copy2(chemin, chemin.replace(".xlsx", f".backup-{time.strftime('%Y%m%d-%H%M')}.xlsx"))
    wb = load_workbook(chemin)
    ws = wb["Cultures"]
    ncol = 10
    lignes = [[ws.cell(r, c) for c in range(1, ncol + 1)] for r in range(2, ws.max_row + 1)]
    if any(l[1].value == "ky" for l in lignes):
        sys.exit("Ky déjà présent : rien à faire.")
    sortie = []
    for l in lignes:
        v, s = [c.value for c in l], [copy(c._style) for c in l]
        if v[8] == "RU_FRANCE_2019":
            v[8] = "RU_FRANCE_2021"
        if v[0] == "Général" and v[1] == "profondeur_sol":
            v[8] = "BDGSF_1998"
            v[9] = ("Utilisée si la commune n'est pas couverte par la carte de profondeur (BDGSF, classes 30, 50, 100 "
                    "et 200 cm). La réserve utile est supposée répartie uniformément sur cette profondeur.")
        sortie.append((v, s))
        if v[1] == "p_fao" and v[0] in KY:
            ky, precision = KY[v[0]]
            sortie.append(([v[0], "ky", "Coefficient de réponse du rendement à l'eau (Ky)", ky, "–", "non", 0, 2,
                            "FAO_33", precision + " Rendement pluvial SGPE = rendement irrigué × (1 − Ky × (1 − ETa/ETc))."],
                           s))
    for r, (v, s) in enumerate(sortie, start=2):
        for c in range(ncol):
            cell = ws.cell(r, c + 1)
            cell.value = v[c]
            cell._style = copy(s[c])
    derniere = len(sortie) + 1
    for t in ws.tables.values():
        t.ref = f"A1:{t.ref.split(':')[1].rstrip('0123456789')}{derniere}"
    for dv in ws.data_validations.dataValidation:
        dv.sqref = type(dv.sqref)(" ".join(str(rg).rstrip("0123456789") + str(derniere) if ":" in str(rg) else str(rg)
                                           for rg in dv.sqref.ranges))

    wr = wb["References"]
    lignes_ref = {wr.cell(r, 1).value: r for r in range(2, wr.max_row + 1)}
    modele = [wr.cell(wr.max_row, c) for c in range(1, 5)]
    if "RU_FRANCE_2019" in lignes_ref:
        wr.cell(lignes_ref["RU_FRANCE_2019"], 1).value = "RU_FRANCE_2021"
        lignes_ref["RU_FRANCE_2021"] = lignes_ref.pop("RU_FRANCE_2019")
    for ident, (courte, complete, url) in REFERENCES.items():
        r = lignes_ref.get(ident) or wr.max_row + 1
        for c, val in enumerate((ident, courte, complete, url or None), start=1):
            wr.cell(r, c).value = val
            wr.cell(r, c)._style = copy(modele[c - 1]._style)
    for t in wr.tables.values():
        t.ref = f"A1:{t.ref.split(':')[1].rstrip('0123456789')}{wr.max_row}"
    wb.save(chemin)
    print(f"{len(sortie) - len(lignes)} lignes Ky ajoutées")


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
