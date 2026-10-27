# -*- coding: utf-8 -*-
"""
Ajout au référentiel des paramètres du bilan hydrique (méthode SGPE type CROPWAT)
=================================================================================
Script ponctuel, à ne lancer qu'une fois : il insère dans la feuille « Cultures »

- pour chaque culture ayant des Kc : profondeur d'enracinement maximale ``zr_max`` (m) et
  fraction de la réserve facilement utilisable ``p_fao`` (–), d'après FAO-56, tableau 22 ;
- un objet « Général » : réserve utile par défaut, profondeur de sol, profondeur
  d'enracinement initiale et épuisement initial de la réserve au semis ;

et les références bibliographiques correspondantes. Une copie de sauvegarde du classeur
est faite avant écriture (referentiel/*.backup-AAAAMMJJ.xlsx, ignorée par git).
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

# FAO-56 (Allen et al., 1998), tableau 22 : profondeur d'enracinement maximale (m, milieu de la
# fourchette) et fraction p de la réserve utile épuisable sans stress (ETc ≈ 5 mm/j).
FAO_22 = {
    "Abricot": (1.5, 0.50, "Abricotier, pêcher, fruits à noyau : 1,0-2,0 m ; p = 0,50"),
    "Betterave": (1.0, 0.55, "Betterave sucrière : 0,7-1,2 m ; p = 0,55"),
    "Agrumes": (1.3, 0.50, "Agrumes : 1,2-1,5 m ; p = 0,50"),
    "Luzerne": (1.5, 0.55, "Luzerne (foin) : 1,0-2,0 m ; p = 0,55"),
    "Amande": (1.5, 0.40, "Amandier : 1,0-2,0 m ; p = 0,40"),
    "Tomates industrielles": (1.0, 0.40, "Tomate : 0,7-1,5 m ; p = 0,40"),
    "Sorgho": (1.5, 0.55, "Sorgho grain : 1,0-2,0 m ; p = 0,55"),
    "Blé dur": (1.5, 0.55, "Blé d'hiver : 1,5-1,8 m ; p = 0,55"),
    "Blé tendre": (1.5, 0.55, "Blé d'hiver : 1,5-1,8 m ; p = 0,55"),
    "Maïs": (1.2, 0.55, "Maïs grain : 1,0-1,7 m ; p = 0,55"),
    "Colza": (1.5, 0.60, "Colza : 1,0-2,0 m ; p = 0,60"),
    "Orge": (1.25, 0.55, "Orge : 1,0-1,5 m ; p = 0,55"),
    "Légumes frais": (0.6, 0.40, "Légumes (moyenne des familles) : 0,3-1,0 m ; p = 0,30-0,50"),
    "Olive": (1.5, 0.65, "Olivier : 1,2-1,7 m ; p = 0,65"),
    "Soja": (1.0, 0.50, "Soja : 0,6-1,3 m ; p = 0,50"),
    "Pomme de terre": (0.5, 0.35, "Pomme de terre : 0,4-0,6 m ; p = 0,35"),
    "Pomme": (1.5, 0.50, "Pommier : 1,0-2,0 m ; p = 0,50"),
    "Tournesol": (1.2, 0.45, "Tournesol : 0,8-1,5 m ; p = 0,45"),
    "Vigne": (1.5, 0.45, "Vigne (raisin de cuve) : 1,0-2,0 m ; p = 0,45"),
    "Légumes d'industrie": (0.6, 0.45, "Haricot vert, pois frais : 0,5-0,7 m ; p = 0,45"),
}

GENERAL = [
    ("ru_defaut", "Réserve utile du sol par défaut (sans carte)", 100, "mm", "oui", 10, 400, "RU_FRANCE_2019",
     "Utilisée si la commune n'est pas couverte par la carte de réserve utile (moyenne nationale ≈ 95 mm)."),
    ("profondeur_sol", "Profondeur de sol prospectable par les racines", 2.0, "m", "oui", 0.2, 2.0, "RU_FRANCE_2019",
     "La réserve utile de la carte porte sur 0-200 cm ; elle est supposée répartie uniformément sur cette "
     "profondeur. À réduire pour un sol superficiel (la réserve accessible aux racines augmente alors)."),
    ("zr_ini", "Profondeur d'enracinement au semis", 0.25, "m", "oui", 0.05, 1.0, "FAO_56",
     "FAO-56 : 0,15-0,30 m en début de cycle ; croissance jusqu'à zr_max au pic de Kc."),
    ("depletion_initiale", "Épuisement initial de la réserve utile (au semis)", 0, "%", "oui", 0, 1, "CROPWAT_1992",
     "0 % = sol à la capacité au champ au semis (valeur par défaut de CROPWAT)."),
]

REFERENCES = [
    ("CROPWAT_1992", "Smith, 1992",
     "Smith, M. (1992). CROPWAT: A computer program for irrigation planning and management (FAO Irrigation and "
     "Drainage Paper No. 46). Food and Agriculture Organization of the United Nations.",
     "https://www.fao.org/land-water/databases-and-software/cropwat/en/"),
    ("RU_FRANCE_2019", "Román Dobarco et al., 2019",
     "Román Dobarco, M., Cousin, I., Le Bas, C., & Martin, M. P. (2019). Pedotransfer functions for predicting "
     "available water capacity in French soils, their applicability domain and associated uncertainty. "
     "Geoderma, 336, 81-95.", "https://doi.org/10.1016/j.geoderma.2018.08.022"),
]


def _copier_style(src, dst):
    for a, b in zip(src, dst):
        b._style = copy(a._style)


def main(chemin: str = CLASSEUR) -> None:
    sauvegarde = chemin.replace(".xlsx", f".backup-{time.strftime('%Y%m%d-%H%M')}.xlsx")
    shutil.copy2(chemin, sauvegarde)
    wb = load_workbook(chemin)
    ws = wb["Cultures"]
    ncol = 10
    lignes = [[ws.cell(r, c) for c in range(1, ncol + 1)] for r in range(2, ws.max_row + 1)]
    if any(l[1].value in ("zr_max", "p_fao") for l in lignes):
        sys.exit("Paramètres déjà présents : rien à faire.")
    valeurs = [[c.value for c in l] for l in lignes]
    styles = [[copy(c._style) for c in l] for l in lignes]

    sortie = []   # (valeurs, styles)
    for i, (v, s) in enumerate(zip(valeurs, styles)):
        sortie.append((v, s))
        culture, code = v[0], v[1]
        # Les lignes d'une culture ne sont pas contiguës : insertion après son dernier Kc
        if culture in FAO_22 and code == "kc_12":
            zr, p, precision = FAO_22[culture]
            sortie.append(([culture, "zr_max", "Profondeur d'enracinement maximale", zr, "m", "non", 0.1, 3,
                            "FAO_56", precision], s))
            sortie.append(([culture, "p_fao", "Fraction de la réserve utile facilement utilisable (p)", p, "–",
                            "non", 0.1, 0.8, "FAO_56", precision + " ; corrigée selon ETc (FAO-56, éq. 81)"], s))
    for code, lib, val, unite, var, vmin, vmax, ref, precision in GENERAL:
        sortie.append((["Général", code, lib, val, unite, var, vmin, vmax, ref, precision], styles[-1]))

    for r, (v, s) in enumerate(sortie, start=2):
        for c in range(ncol):
            cell = ws.cell(r, c + 1)
            cell.value = v[c]
            cell._style = copy(s[c])
    derniere = len(sortie) + 1
    for t in ws.tables.values():
        t.ref = f"A1:{t.ref.split(':')[1].rstrip('0123456789')}{derniere}"
    for dv in ws.data_validations.dataValidation:
        dv.sqref = type(dv.sqref)(" ".join(
            str(rg).rstrip("0123456789") + str(derniere) if ":" in str(rg) else str(rg)
            for rg in dv.sqref.ranges))

    wr = wb["References"]
    existants = {wr.cell(r, 1).value for r in range(2, wr.max_row + 1)}
    modele = [wr.cell(wr.max_row, c) for c in range(1, 5)]
    for ident, courte, complete, url in REFERENCES:
        if ident in existants:
            continue
        r = wr.max_row + 1
        for c, v in enumerate((ident, courte, complete, url), start=1):
            wr.cell(r, c).value = v
        _copier_style(modele, [wr.cell(r, c) for c in range(1, 5)])
    for t in wr.tables.values():
        t.ref = f"A1:{t.ref.split(':')[1].rstrip('0123456789')}{wr.max_row}"
    wb.save(chemin)
    print(f"{len(sortie) - len(valeurs)} lignes ajoutées ; sauvegarde : {sauvegarde}")


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
