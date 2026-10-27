# -*- coding: utf-8 -*-
"""
Résultats de la validation des méthodes (méthodologie PDF)
=========================================================================================
Lit ``validation/comparaison.csv``, produit par ``outils/comparer_modeles.py`` (méthode SGPE,
package R CropWat d'INRAE, cartes MAELIA, sur un échantillon de points de grille DRIAS), et en
calcule les indicateurs par culture. Relu dès que le fichier change.
"""

from __future__ import annotations

import csv
import math
import os
from typing import Any, Dict, List, Optional

_cache: Dict[str, Any] = {}

# Comparaisons présentées : (clé, libellé, colonne de référence, colonne comparée)
COMPARAISONS_BESOIN = [
    ("moteur", "SGPE et CropWat, mêmes entrées (sans réduction de fin de cycle)", "sgpe_besoin_sans_reduction",
     "cw_moteur_besoin"),
    ("cropwat", "SGPE et CropWat, paramètres de culture propres à CropWat (pluie efficace)", "sgpe_besoin",
     "cw_param_besoin_peff"),
    ("maelia", "SGPE et MAELIA", "sgpe_besoin", "maelia_besoin"),
]
COMPARAISONS_RDT = [
    ("moteur", "SGPE et CropWat, mêmes entrées", "sgpe_rel_sec", "cw_moteur_rel_sec"),
    ("maelia", "SGPE et MAELIA", "sgpe_rel_sec", "maelia_rel_sec"),
]


def _nombre(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _stats(paires) -> Optional[Dict[str, float]]:
    paires = [(a, b) for a, b in paires if a is not None and b is not None]
    n = len(paires)
    if n < 3:
        return None
    a = [p[0] for p in paires]
    b = [p[1] for p in paires]
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    cov = sum((x - ma) * (y - mb) for x, y in paires)
    return {"n": n, "moy_1": ma, "moy_2": mb, "ecart": mb - ma, "eam": sum(abs(y - x) for x, y in paires) / n,
            "r": cov / (sa * sb) if sa > 0 and sb > 0 else None}


def resultats(chemin: str) -> Optional[Dict[str, Any]]:
    """Indicateurs par culture et pour l'ensemble, ou None si la validation n'a pas été produite."""
    if not os.path.exists(chemin):
        return None
    mtime = os.path.getmtime(chemin)
    if _cache.get("cle") == (chemin, mtime):
        return _cache["valeur"]
    with open(chemin, encoding="utf-8") as f:
        lignes = list(csv.DictReader(f))
    cultures = sorted({l["culture"] for l in lignes})
    points = {l["point"] for l in lignes}

    def bloc(comparaisons):
        sortie = []
        for culture in cultures + ["Ensemble"]:
            sel = [l for l in lignes if culture == "Ensemble" or l["culture"] == culture]
            ligne = {"culture": culture}
            for cle, _, c1, c2 in comparaisons:
                ligne[cle] = _stats((_nombre(l.get(c1)), _nombre(l.get(c2))) for l in sel)
            sortie.append(ligne)
        return sortie

    valeur = {"n_cas": len(lignes), "n_points": len(points), "cultures": cultures,
              "besoin": bloc(COMPARAISONS_BESOIN), "rendement": bloc(COMPARAISONS_RDT),
              "comparaisons_besoin": [(c, l) for c, l, _, _ in COMPARAISONS_BESOIN],
              "comparaisons_rendement": [(c, l) for c, l, _, _ in COMPARAISONS_RDT],
              "date": mtime}
    _cache.update({"cle": (chemin, mtime), "valeur": valeur})
    return valeur
