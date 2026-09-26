# -*- coding: utf-8 -*-
"""
Besoin en eau d'irrigation par la méthode SGPE
==============================================
Déficit hydrique mensuel, sommé sur les mois où la culture est en place :

    BNI (mm) = Σ max(0, ETP(mois) × Kc(culture, mois) − P(mois))   pour Kc(mois) > 0

- Kc mensuels : feuille « Cultures » du référentiel (codes kc_01 à kc_12).
- ETP et P mensuelles : ``climate_data.xlsx`` (DRIAS, EURO-CORDEX 2020, ALADIN63_CNRM-CM5,
  RCP4.5), une ligne par point de grille, horizon et mois. La valeur retenue pour la
  commune est celle du point de grille le plus proche de son centre.

La lecture du classeur prend plusieurs secondes : les données sont mises en cache
dans un fichier ``.npz`` voisin, régénéré dès que le classeur change.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional, Tuple

import numpy as np

HORIZONS = ["H1", "H2", "H3"]
LIBELLES_HORIZON = {"H1": "horizon proche (2021-2050)", "H2": "horizon moyen (2041-2070)",
                    "H3": "horizon lointain (2071-2100)"}
# Distance maximale entre le centre de la commune et le point de grille (grille de 8 km).
DISTANCE_MAX_KM = 12.0

_verrou = threading.Lock()
_donnees: Dict[str, Any] = {}


def _lire_classeur(chemin: str) -> Dict[str, np.ndarray]:
    from openpyxl import load_workbook
    wb = load_workbook(chemin, read_only=True, data_only=True)
    points: Dict[str, int] = {}
    coords: list = []
    valeurs: Dict[Tuple[int, int, int], Tuple[float, float]] = {}
    for ws in wb.worksheets:
        for ligne in ws.iter_rows(values_only=True):
            if not ligne or ligne[0] is None:
                continue
            s = str(ligne[0])
            if s.startswith("#"):
                continue
            p = s.split(";")
            if len(p) < 8 or p[4] not in HORIZONS:
                continue
            try:
                lat, lon, mois, rr, etp = float(p[1]), float(p[2]), int(p[5]), float(p[6]), float(p[7])
            except ValueError:
                continue
            if p[0] not in points:
                points[p[0]] = len(coords)
                coords.append((lat, lon))
            valeurs[(points[p[0]], HORIZONS.index(p[4]), mois - 1)] = (rr, etp)
    wb.close()
    n = len(coords)
    pluie = np.full((n, len(HORIZONS), 12), np.nan)
    etp = np.full((n, len(HORIZONS), 12), np.nan)
    for (i, h, m), (rr, e) in valeurs.items():
        pluie[i, h, m] = rr
        etp[i, h, m] = e
    return {"coords": np.array(coords, dtype="float64").reshape(-1, 2), "pluie": pluie, "etp": etp,
            "ids": np.array(list(points.keys()))}


def _charger(chemin: str) -> Optional[Dict[str, Any]]:
    """Données climatiques en mémoire (depuis le cache .npz si à jour)."""
    if not chemin or not os.path.exists(chemin):
        return None
    mtime = os.path.getmtime(chemin)
    with _verrou:
        if _donnees.get("mtime") == mtime and _donnees.get("chemin") == chemin:
            return _donnees
        cache = os.path.splitext(chemin)[0] + ".cache.npz"
        d = None
        if os.path.exists(cache):
            try:
                with np.load(cache) as z:
                    if float(z["mtime"]) == mtime:
                        d = {k: z[k] for k in ("coords", "pluie", "etp", "ids")}
            except Exception:
                d = None
        if d is None:
            d = _lire_classeur(chemin)
            try:
                np.savez_compressed(cache, mtime=np.array(mtime), **d)
            except OSError:
                pass
        _donnees.clear()
        _donnees.update(d)
        _donnees.update({"mtime": mtime, "chemin": chemin})
        return _donnees


def prechauffer(chemin: str) -> None:
    """Charge les données en arrière-plan pour que la première simulation reste rapide."""
    threading.Thread(target=lambda: _charger(chemin), daemon=True).start()


def kc_mensuels(ref, culture: str) -> Optional[list]:
    """Les 12 Kc de la culture, ou None si le référentiel n'en contient pas."""
    kc = [ref.valeur("Cultures", culture, f"kc_{m:02d}") for m in range(1, 13)]
    if all(k is None for k in kc):
        return None
    return [k or 0.0 for k in kc]


def point_proche(d: Dict[str, Any], lonlat: Tuple[float, float]) -> Tuple[int, float]:
    """Indice du point de grille le plus proche et distance en km."""
    lat0, lon0 = lonlat[1], lonlat[0]
    c = d["coords"]
    dy = (c[:, 0] - lat0) * 111.2
    dx = (c[:, 1] - lon0) * 111.2 * np.cos(np.radians(lat0))
    dist = np.hypot(dx, dy)
    i = int(np.argmin(dist))
    return i, float(dist[i])


def besoin_sgpe(ref, culture: str, lonlat: Optional[Tuple[float, float]], chemin: str,
                horizon: str = "H1") -> Dict[str, Any]:
    """Besoin en eau d'irrigation (mm) par la méthode SGPE.

    Renvoie {"valeur": float|None, "note": str, "detail": {...}} ; valeur None si le calcul
    n'est pas possible (pas de Kc, pas de commune, pas de donnée climatique à proximité).
    """
    kc = kc_mensuels(ref, culture)
    if kc is None:
        return {"valeur": None, "note": f"Méthode SGPE indisponible pour « {culture} » : coefficients culturaux (Kc) "
                                        "non renseignés dans le référentiel."}
    if lonlat is None:
        return {"valeur": None, "note": "Sélectionnez une commune pour appliquer la méthode SGPE."}
    d = _charger(chemin)
    if d is None or not len(d["coords"]):
        return {"valeur": None, "note": "Données climatiques (climate_data.xlsx) introuvables."}
    i, dist = point_proche(d, lonlat)
    if dist > DISTANCE_MAX_KM:
        return {"valeur": None, "note": "Pas de donnée climatique (ETP, P) à proximité de la commune "
                                        f"(point le plus proche à {dist:.0f} km)."}
    h = HORIZONS.index(horizon) if horizon in HORIZONS else 0
    etp, pluie = d["etp"][i, h], d["pluie"][i, h]
    mensuel = []
    for m in range(12):
        if kc[m] > 0 and np.isfinite(etp[m]) and np.isfinite(pluie[m]):
            mensuel.append(max(0.0, float(etp[m]) * kc[m] - float(pluie[m])))
        else:
            mensuel.append(0.0)
    lat, lon = d["coords"][i]
    return {"valeur": float(sum(mensuel)), "note": "",
            "detail": {"point": str(d["ids"][i]), "lat": float(lat), "lon": float(lon), "distance_km": dist,
                       "horizon": HORIZONS[h], "libelle_horizon": LIBELLES_HORIZON[HORIZONS[h]],
                       "kc": kc, "etp": [float(x) for x in etp], "pluie": [float(x) for x in pluie],
                       "deficit": mensuel}}
