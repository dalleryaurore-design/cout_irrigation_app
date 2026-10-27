# -*- coding: utf-8 -*-
"""
Réserve utile et profondeur du sol à la commune
===============================================
- ``sol/ru_sol_1km.tif`` : réservoir utile des sols de France métropolitaine (mm), sommé sur la
  profondeur de sol estimée, au plus 2 m (Román Dobarco et al., 2021), ramené à la maille de 1 km
  par ``outils/preparer_sol.py`` depuis ``AWCr_mm_0_200.tif`` (90 m). À défaut de la carte allégée,
  la carte d'origine est lue directement.
- ``sol/profondeur_sol_1km.tif`` : profondeur de sol (m), classes 0,3 / 0,5 / 1 / 2 m de la BDGSF
  (couche bdgsf_classe_prof), rasterisée par ``outils/preparer_profondeur.R``.

La valeur communale est la moyenne des mailles qui touchent le contour de la commune, avec
repli sur la maille du centre puis la maille valide la plus proche : même règle que pour les
cartes MAELIA (``moteur/cartes.py``), dont les fonctions de lecture sont reprises.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from . import cartes

_cache: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()


def fichier_ru(*chemins: str) -> Optional[str]:
    """Premier fichier présent parmi ceux proposés."""
    return next((c for c in chemins if c and os.path.exists(c)), None)


def valeur_commune(chemin: Optional[str], geometrie: Optional[dict], lonlat: Optional[Tuple[float, float]],
                   code_commune: str = "") -> Dict[str, Any]:
    """Valeur communale d'une carte de sol : {"valeur", "n", "methode", "fichier"} ; valeur None si
    la carte est absente, illisible ou ne couvre pas la commune."""
    vide = {"valeur": None, "n": 0, "methode": "", "fichier": os.path.basename(chemin or "")}
    if not chemin or not os.path.exists(chemin) or (geometrie is None and lonlat is None) or not cartes.disponible():
        return vide
    cle = (chemin, os.path.getmtime(chemin), code_commune, lonlat)
    if cle in _cache:
        return _cache[cle]
    try:
        with cartes._verrou:  # GDAL n'est pas thread-safe
            e = cartes.entete(chemin)
            z = cartes._valeur_zone(chemin, e, geometrie, lonlat)
    except Exception as exc:
        return dict(vide, methode=f"lecture impossible ({exc})")
    res = {"valeur": z["valeur"], "n": z["n"], "methode": z["methode"], "fichier": e["fichier"]}
    _cache[cle] = res
    while len(_cache) > 1000:
        _cache.popitem(last=False)
    return res


ru_commune = valeur_commune
