# -*- coding: utf-8 -*-
"""
Paramètres de cultures calés pour MAELIA (jeux SB2023 du package CropWat) dans le référentiel
============================================================================================
Script ponctuel. Remplace, pour les cultures qui ont un jeu SB2023, les Kc mensuels, la profondeur
d'enracinement maximale (zr_max) et la fraction p (p_fao) par ceux du jeu (Kc journaliers moyennés
par mois, voir outils/kc_sb2023.R) ; crée les lignes manquantes (triticale) ; corrige le besoin de
référence du sorgho ; ajoute le seuil de plausibilité du besoin en eau. Sauvegarde préalable.

    Rscript outils/kc_sb2023.R validation/kc_sb2023.csv
    python outils/appliquer_kc_sb2023.py
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import time
from copy import copy

from openpyxl import load_workbook

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSEUR = os.path.join(RACINE, "referentiel", "referentiel_irrigation.xlsx")
KC_CSV = os.path.join(RACINE, "validation", "kc_sb2023.csv")
# Jeux retenus après comparaison (validation/synthese.md) : pour chaque culture, le jeu de paramètres dont
# le besoin moyen est le plus proche de la moyenne MAELIA / référentiel. Les jeux SB2023 du maïs (135 mm
# contre 178 mm en FAO-56, MAELIA 195 mm, référentiel 180 mm) et des céréales à paille (13 mm contre 65 mm,
# MAELIA 73 mm) ne sont pas retenus : FAO-56 est conservé pour ces cultures.
JEUX = {"Tournesol": "SB2023-tour", "Soja": "SB2023-soja", "Colza": "SB2023-colza"}
# Cultures sans Kc qui reprennent les paramètres d'une culture proche
COPIES = {"Triticale": "Blé tendre"}
CODES_COPIES = [f"kc_{m:02d}" for m in range(1, 13)] + ["zr_max", "p_fao", "ky"]
REF_ID = "CROPWAT_R_2025"
REFERENCE = ("Dorchies et al., 2025",
             "Dorchies, D., et al. (2025). CropWat: R implementation of the FAO CropWat model (version 0.3.0) "
             "[Logiciel]. INRAE, UMR G-EAU. Jeux de cultures SB2023 calés pour MAELIA sur le bassin de l'Aveyron "
             "(Soutif-Bellenger et al., 2023).", "https://inrae.r-universe.dev/CropWat")
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def main(chemin: str = CLASSEUR) -> None:
    jeux = {}
    with open(KC_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            j = jeux.setdefault(r["jeu"], {"kc": [0.0] * 12})
            j["kc"][int(r["mois"]) - 1] = float(r["kc"])
            j.update(zr=float(r["zr_max"]), p=float(r["p"]), semis=r["semis"], duree=r["duree"])
    shutil.copy2(chemin, chemin.replace(".xlsx", f".backup-{time.strftime('%Y%m%d-%H%M')}.xlsx"))
    wb = load_workbook(chemin)
    ws = wb["Cultures"]
    ncol = 10
    lignes = [([ws.cell(r, c).value for c in range(1, ncol + 1)], [copy(ws.cell(r, c)._style) for c in range(1, ncol + 1)])
              for r in range(2, ws.max_row + 1)]
    existants = {(v[0], v[1]) for v, _ in lignes}
    modele = next(s for v, s in lignes if v[1] == "kc_01")

    def precision(culture):
        j = jeux[JEUX[culture]]
        return (f"Jeu {JEUX[culture]} du package CropWat (calage MAELIA, Aveyron) : semis {j['semis']}, cycle de "
                f"{j['duree']} jours ; Kc journaliers moyennés par mois.")

    sortie = []
    for v, s in lignes:
        culture, code = v[0], v[1]
        if culture in JEUX:
            j = jeux[JEUX[culture]]
            if code and code.startswith("kc_"):
                v[3], v[8], v[9] = j["kc"][int(code[3:]) - 1], REF_ID, precision(culture)
            elif code == "zr_max":
                v[3], v[8], v[9] = j["zr"], REF_ID, precision(culture)
            elif code == "p_fao":
                v[3], v[8], v[9] = j["p"], REF_ID, precision(culture) + " p au stade de pleine végétation."
        if culture == "Sorgho" and code == "besoin_irrigation":
            v[3] = 150
            v[9] = ("Valeur corrigée le 23/10/2026 (340 mm auparavant, incohérente avec les méthodes SGPE, CropWat "
                    "et MAELIA, qui donnent 120 à 190 mm en moyenne nationale). À confirmer par une source.")
        sortie.append((v, s))
        # Cultures sans Kc (triticale) : lignes de la culture proche, ajoutées après la dernière ligne de la culture
        suivant = next((w for w, _ in lignes[lignes.index((v, s)) + 1:] if w[0] == culture), None)
        if culture in COPIES and suivant is None and (culture, "kc_01") not in existants:
            source = {w[1]: w for w, _ in lignes if w[0] == COPIES[culture]}
            for code_copie in CODES_COPIES:
                w = list(source[code_copie])
                w[0] = culture
                w[9] = f"Assimilé à « {COPIES[culture]} » : {w[9] or ''}".strip()
                sortie.append((w, modele))
    if ("Général", "besoin_plausible_max") not in existants:
        g = next(s for v, s in lignes if v[0] == "Général")
        sortie.append((["Général", "besoin_plausible_max", "Besoin en eau au-delà duquel un avertissement s'affiche",
                        450, "mm", "non", 0, 2000, "",
                        "Seuil de vigilance : au-delà, la valeur calculée est signalée comme à vérifier."], g))
    for r, (v, s) in enumerate(sortie, start=2):
        for c in range(ncol):
            ws.cell(r, c + 1).value = v[c]
            ws.cell(r, c + 1)._style = copy(s[c])
    derniere = len(sortie) + 1
    for t in ws.tables.values():
        t.ref = f"A1:{t.ref.split(':')[1].rstrip('0123456789')}{derniere}"
    for dv in ws.data_validations.dataValidation:
        dv.sqref = type(dv.sqref)(" ".join(str(rg).rstrip("0123456789") + str(derniere) if ":" in str(rg) else str(rg)
                                           for rg in dv.sqref.ranges))
    wr = wb["References"]
    ids = {wr.cell(r, 1).value: r for r in range(2, wr.max_row + 1)}
    if REF_ID not in ids:
        modele_ref = [wr.cell(wr.max_row, c) for c in range(1, 5)]
        r = wr.max_row + 1
        for c, val in enumerate((REF_ID,) + REFERENCE, start=1):
            wr.cell(r, c).value = val
            wr.cell(r, c)._style = copy(modele_ref[c - 1]._style)
        for t in wr.tables.values():
            t.ref = f"A1:{t.ref.split(':')[1].rstrip('0123456789')}{wr.max_row}"
    wb.save(chemin)
    print(f"Référentiel mis à jour : {len(sortie) - len(lignes)} lignes ajoutées")


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
