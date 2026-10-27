# -*- coding: utf-8 -*-
"""
Robustesse de la méthode SGPE : comparaison avec CropWat (R, INRAE) et avec les cartes MAELIA
==========================================================================================
Pour un échantillon de points de grille DRIAS répartis sur la France et les cultures qui ont des
cartes MAELIA, le script compare :

- SGPE      : besoin net (mm) et rendement relatif en sec (Ky) de l'application (moteur/climat.py) ;
- CW_moteur : le moteur du package R CropWat (Dorchies et al., INRAE) alimenté avec EXACTEMENT les
              mêmes entrées journalières que SGPE (Kc, ETc, pluie efficace, Zr, TAW, RAW) : contrôle
              de l'implémentation du bilan hydrique ;
- CW_param  : CropWat avec ses propres paramètres de culture (courbes de Kc par stades, dates de
              semis, profondeurs racinaires ; jeux SB2023 calés pour MAELIA quand ils existent), pluie
              brute (choix par défaut du package) puis pluie efficace : sensibilité au paramétrage ;
- MAELIA    : valeur des cartes (narratif violet, RCP4.5, 2020-2040) au même point.

Même sol (réserve utile et profondeur des cartes de sol) et même climat (DRIAS, H1) pour SGPE et
CropWat ; MAELIA a son propre climat (Explore2), ce qui explique une part des écarts.

    python outils/comparer_modeles.py [nombre de points]      (40 par défaut)

Sorties dans validation/ : entrees_*.csv, resultats_cropwat.csv, comparaison.csv, synthese.md.
Requiert R (Rscript) avec le package CropWat (install.packages("CropWat",
repos = "https://inrae.r-universe.dev")).
"""

from __future__ import annotations

import csv
import math
import os
import shutil
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import numpy as np  # noqa: E402

import config  # noqa: E402
from moteur import cartes, climat, sol  # noqa: E402
from moteur.referentiel import GestionnaireReferentiel  # noqa: E402

SORTIE = os.path.join(RACINE, "validation")
# Culture de l'application -> (code CropWat, date de semis si le jeu n'en a pas)
CROPWAT = {
    "Maïs": ("SB2023-maisT", None), "Tournesol": ("SB2023-tour", None), "Soja": ("SB2023-soja", None),
    "Colza": ("SB2023-colza", None), "Blé tendre": ("SB2023-CP", None), "Orge": ("SB2023-CP", None),
    "Betterave": ("FAO-SUGARBET", "03-25"), "Pomme de terre": ("FAO-POTATO", "04-15"),
    "Sorgho": ("FAO-SORGHUM", "05-01"),
}


def rscript() -> str:
    for c in (shutil.which("Rscript"), r"C:\Program Files\R\R-4.5.0\bin\Rscript.exe"):
        if c and os.path.exists(c):
            return c
    raise SystemExit("Rscript introuvable : installez R et le package CropWat.")


def points_echantillon(d, n: int):
    """Points de grille régulièrement espacés (tri par latitude puis longitude)."""
    coords = d["coords"]
    ordre = np.lexsort((coords[:, 1], np.round(coords[:, 0], 0)))
    pas = max(1, len(ordre) // n)
    return [int(i) for i in ordre[pas // 2::pas][:n]]


def main(n_points: int = 40) -> None:
    os.makedirs(SORTIE, exist_ok=True)
    ref = GestionnaireReferentiel(config.REFERENTIEL).get()
    d = climat._charger(config.CLIMAT)
    cat = cartes.catalogue(ref, config.DOSSIER_CARTES)
    ru_fic = sol.fichier_ru(config.SOL_RU, config.SOL_RU_ORIGINE)
    lignes, journaux, points = [], [], []
    for i in points_echantillon(d, n_points):
        lat, lon = (float(x) for x in d["coords"][i])
        etp, pluie = d["etp"][i, 0], d["pluie"][i, 0]
        if not (np.all(np.isfinite(etp)) and np.all(np.isfinite(pluie))):
            continue
        ru = sol.valeur_commune(ru_fic, None, (lon, lat))["valeur"]
        prof = sol.valeur_commune(config.SOL_PROFONDEUR, None, (lon, lat))["valeur"]
        if ru is None or ru < 1 or prof is None:   # RU nulle : maille d'eau ou urbaine
            continue
        prof = min(prof, 2.0)
        pid = str(d["ids"][i])
        points.append({"point": pid, "lat": lat, "lon": lon, "ru": ru, "profondeur": prof,
                       **{f"etp_{m + 1:02d}": float(etp[m]) for m in range(12)},
                       **{f"p_{m + 1:02d}": float(pluie[m]) for m in range(12)}})
        for culture, (code_cw, semis) in CROPWAT.items():
            kc = climat.kc_mensuels(ref, culture)
            info = cat.get(culture)
            if kc is None or not info or not info["complet"]:
                continue
            prm = climat.parametres_bilan(ref, culture)
            b = climat.bilan_hydrique(kc, [float(x) for x in etp], [float(x) for x in pluie], ru, prof,
                                      prm["zr_max"], prm["zr_ini"], prm["p_fao"], prm["epuisement_initial"],
                                      journal=True)
            plein = climat.bilan_hydrique(kc, [float(x) for x in etp], [float(x) for x in pluie], ru, prof,
                                          prm["zr_max"], prm["zr_ini"], prm["p_fao"], prm["epuisement_initial"],
                                          reduire_fin_cycle=False)
            ky = ref.valeur("Cultures", culture, "ky", None, 1.0)
            try:
                extr = cartes.extraire(ref, culture, info, None, (lon, lat), config.ESPECES_CULTIVEES)
            except Exception:
                extr = {}
            maelia_rel = (extr["rdt_pluvial"] / extr["rdt_irrigue"]
                          if extr.get("rdt_pluvial") is not None and extr.get("rdt_irrigue") else None)
            cle = f"{pid}|{culture}"
            lignes.append({"cle": cle, "point": pid, "lat": lat, "lon": lon, "culture": culture, "ru": round(ru, 1),
                           "profondeur": prof, "code_cropwat": code_cw, "semis": semis or "", "ky": ky,
                           "sgpe_besoin": round(b["valeur"], 1),
                           "sgpe_besoin_sans_reduction": round(plein["valeur"], 1),
                           "sgpe_rel_sec": round(climat.rendement_relatif(ky, b["satisfaction_sec"]), 3),
                           "maelia_besoin": None if extr.get("besoin") is None else round(extr["besoin"], 1),
                           "maelia_rel_sec": None if maelia_rel is None else round(maelia_rel, 3)})
            for k, j in enumerate(b["journal"], start=1):
                journaux.append({"cle": cle, "jour": k, **{c: round(v, 5) for c, v in j.items()}})
    _ecrire(os.path.join(SORTIE, "entrees_cas.csv"), lignes)
    _ecrire(os.path.join(SORTIE, "entrees_points.csv"), points)
    _ecrire(os.path.join(SORTIE, "entrees_journal.csv"), journaux)
    print(f"{len(lignes)} cas (points × cultures) ; lancement de CropWat (R)…", flush=True)

    script = os.path.join(RACINE, "outils", "cropwat_comparaison.R")
    subprocess.run([rscript(), script, SORTIE], check=True)

    cw = {r["cle"]: r for r in _lire(os.path.join(SORTIE, "resultats_cropwat.csv"))}
    comp = []
    for l in lignes:
        r = cw.get(l["cle"], {})
        comp.append(dict(l, **{k: _nombre(r.get(k)) for k in ("cw_moteur_besoin", "cw_moteur_rel_sec",
                                                               "cw_param_besoin_brute", "cw_param_besoin_peff",
                                                               "cw_param_rel_sec")}))
    _ecrire(os.path.join(SORTIE, "comparaison.csv"), comp)
    synthese(comp, len(points))


def _nombre(v):
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _ecrire(chemin, lignes):
    if not lignes:
        return
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()))
        w.writeheader()
        w.writerows(lignes)


def _lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _stats(x, y):
    paires = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(paires) < 3:
        return None
    a, b = np.array(paires).T
    r = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
    return {"n": len(a), "moy_ref": a.mean(), "moy_autre": b.mean(), "biais": (b - a).mean(),
            "eam": np.abs(b - a).mean(), "r": r}


def synthese(comp, n_points):
    paires = [("SGPE sans réduction de fin de cycle / CropWat même moteur", "sgpe_besoin_sans_reduction",
               "cw_moteur_besoin"),
              ("SGPE / CropWat même moteur", "sgpe_besoin", "cw_moteur_besoin"),
              ("SGPE / CropWat paramètres propres, pluie efficace", "sgpe_besoin", "cw_param_besoin_peff"),
              ("SGPE / CropWat paramètres propres, pluie brute", "sgpe_besoin", "cw_param_besoin_brute"),
              ("SGPE / MAELIA", "sgpe_besoin", "maelia_besoin"),
              ("CropWat paramètres propres (pluie brute) / MAELIA", "cw_param_besoin_brute", "maelia_besoin")]
    paires_rdt = [("SGPE / CropWat même moteur", "sgpe_rel_sec", "cw_moteur_rel_sec"),
                  ("SGPE / CropWat paramètres propres", "sgpe_rel_sec", "cw_param_rel_sec"),
                  ("SGPE / MAELIA", "sgpe_rel_sec", "maelia_rel_sec")]
    cultures = sorted({c["culture"] for c in comp})
    out = [f"# Robustesse de la méthode SGPE\n",
           f"{len(comp)} cas : {n_points} points de grille DRIAS × {len(cultures)} cultures ayant des cartes MAELIA. "
           "Écart = autre modèle − premier modèle ; EAM = écart absolu moyen ; r = corrélation entre points.\n"]

    def tableau(titre, liste, unite, dec):
        out.append(f"\n## {titre}\n")
        out.append(f"| Culture | Comparaison | n | Moyenne 1 | Moyenne 2 | Écart moyen | EAM | r |")
        out.append("|---|---|---|---|---|---|---|---|")
        for c in cultures + ["Toutes"]:
            sel = [x for x in comp if c == "Toutes" or x["culture"] == c]
            for lib, k1, k2 in liste:
                s = _stats([x[k1] for x in sel], [x[k2] for x in sel])
                if s:
                    out.append(f"| {c} | {lib} | {s['n']} | {s['moy_ref']:.{dec}f} | {s['moy_autre']:.{dec}f} | "
                               f"{s['biais']:+.{dec}f} | {s['eam']:.{dec}f} | {s['r']:.2f} |")
        out.append(f"\nUnité : {unite}.")

    tableau("Besoin net d'irrigation", paires, "mm", 0)
    tableau("Rendement relatif sans irrigation (rendement pluvial ÷ rendement irrigué)", paires_rdt, "–", 2)
    with open(os.path.join(SORTIE, "synthese.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:2]))
