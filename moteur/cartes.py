# -*- coding: utf-8 -*-
"""
Cartes du modèle MAELIA (GeoTIFF à la maille 8 km)
==================================================
Trois cartes par culture, déposées dans le dossier ``cartes`` :

    culture_<CODE>_irrigue_irr_<contexte>.tif   besoin en eau d'irrigation
    culture_<CODE>_irrigue_pot_<contexte>.tif   rendement potentiel irrigué
    culture_<CODE>_rainfed_pot_<contexte>.tif   rendement potentiel pluvial

Le module inventorie les cartes déclarées dans la feuille « Cartes » du
référentiel, puis calcule la valeur communale : moyenne des mailles qui touchent
le contour de la commune, avec repli sur la maille du centre puis sur la maille
valide la plus proche.

Trois principes de performance, l'application devant rester réactive à la saisie :

1. ``rasterio`` n'est importé qu'au premier besoin réel de lecture. L'inventaire
   des fichiers ne repose que sur le système de fichiers : une application sans
   carte ne paie jamais le coût de cet import.
2. Seule la fenêtre du raster qui recouvre la commune est lue, jamais le fichier
   entier : le temps de lecture ne dépend plus de l'étendue de la carte.
3. L'en-tête de chaque fichier (géoréférencement et échantillon décimé servant à
   la reconnaissance d'unité) est mis en cache tant que le fichier ne change pas.

Le module ne produit pas d'image des rasters bruts. Il expose cependant, pour les
couches facultatives de la carte (cases à cocher « rendement irrigué / pluvial /
besoin en eau »), une image dérivée par variable — un dégradé de couleur (rouge à
vert pour un rendement, jaune à bleu pour un besoin en eau), voir ``carte_variable``.
"""

from __future__ import annotations

import base64
import fnmatch
import os
import threading
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import numpy as np

VARIABLES = {
    "besoin": {"libelle": "Besoin en eau d'irrigation", "motif": "irrigue_irr", "unite": "mm"},
    "rdt_irrigue": {"libelle": "Rendement potentiel irrigué", "motif": "irrigue_pot", "unite": "q/ha"},
    "rdt_pluvial": {"libelle": "Rendement potentiel pluvial", "motif": "rainfed_pot", "unite": "q/ha"},
}

FACTEURS_RDT = {"t/ha": 10.0, "q/ha": 1.0, "kg/ha": 0.01}
FACTEURS_BESOIN = {"mm": 1.0, "m3/ha": 0.1}
# Cartes de rendement exprimées en % du rendement potentiel (sorties AqYield de MAELIA :
# rendement = effet du stress hydrique × rendement optimal de l'espèce). Le facteur de
# conversion vers q/ha dépend alors de la culture : rendement potentiel ÷ 100.
POURCENT = "%"

# Côté maximal de l'échantillon décimé lu pour reconnaître l'unité d'un fichier.
COTE_ECHANTILLON = 120
# Marge, en mailles, ajoutée autour de l'emprise de la commune.
MARGE_MAILLES = 2

_verrou = threading.Lock()
_rio: Dict[str, Any] = {}          # fonctions rasterio chargées à la demande
_erreur_rio = ""


# ---------------------------------------------------------------------------
# Chargement paresseux de rasterio
# ---------------------------------------------------------------------------
def _charger_rasterio() -> bool:
    """Importe rasterio au premier besoin. Renvoie False si l'import échoue."""
    global _erreur_rio
    if _rio:
        return True
    if _erreur_rio:
        return False
    with _verrou:
        if _rio:
            return True
        try:
            import rasterio
            from rasterio.crs import CRS
            from rasterio.features import geometry_mask
            from rasterio.io import MemoryFile
            from rasterio.warp import (Resampling, calculate_default_transform, reproject,
                                       transform as warp_transform, transform_geom)
            from rasterio.windows import Window, from_bounds
            _rio.update({"rasterio": rasterio, "CRS": CRS, "geometry_mask": geometry_mask,
                         "warp_transform": warp_transform, "transform_geom": transform_geom,
                         "Window": Window, "from_bounds": from_bounds, "MemoryFile": MemoryFile,
                         "calculate_default_transform": calculate_default_transform,
                         "reproject": reproject, "Resampling": Resampling})
            return True
        except Exception as exc:  # pragma: no cover - dépend de l'installation du poste
            _erreur_rio = str(exc)
            return False


def disponible() -> bool:
    """Vrai si la lecture des cartes est possible sur ce poste."""
    return _charger_rasterio()


def erreur() -> str:
    """Message d'erreur de l'import de rasterio ; vide s'il a réussi ou n'a pas été tenté."""
    return _erreur_rio


# ---------------------------------------------------------------------------
# Inventaire des fichiers (aucune dépendance à rasterio)
# ---------------------------------------------------------------------------
def _resoudre(dossier: str, nom: str, code: str, motif: str) -> Optional[str]:
    if nom:
        chemin = nom if os.path.isabs(nom) else os.path.join(dossier, nom)
        return chemin if os.path.exists(chemin) else None
    if not code:
        return None
    # Comparaison insensible à la casse : les codes du référentiel sont en majuscules alors que
    # certains fichiers sont en minuscules, et un serveur Linux distingue les deux.
    if not os.path.isdir(dossier):
        return None
    motifs = [f"culture_{code}_{motif}*.tif".lower(), f"culture_{code}_{motif}*.tiff".lower()]
    candidats = sorted(os.path.join(dossier, f) for f in os.listdir(dossier)
                       if any(fnmatch.fnmatchcase(f.lower(), m) for m in motifs))
    return candidats[0] if candidats else None


def catalogue(ref, dossier: str) -> Dict[str, Dict[str, Any]]:
    """Cartes disponibles par culture, d'après la feuille « Cartes » et le contenu du dossier."""
    cat: Dict[str, Dict[str, Any]] = {}
    for culture, cfg in ref.cartes.items():
        code = cfg.get("code", "")
        if not code and not any(cfg.get(k) for k in VARIABLES):
            continue
        fichiers = {v: _resoudre(dossier, cfg.get(v, ""), code, VARIABLES[v]["motif"]) for v in VARIABLES}
        manquants = [VARIABLES[v]["libelle"] for v, f in fichiers.items() if not f]
        cat[culture] = {"code": code, "fichiers": fichiers, "complet": not manquants, "manquants": manquants,
                        "scenario": cfg.get("scenario", ""), "unite_rdt": cfg.get("unite_rdt", "auto"),
                        "unite_besoin": cfg.get("unite_besoin", "auto"), "crs": cfg.get("crs", "auto")}
    return cat


# ---------------------------------------------------------------------------
# En-tête d'un fichier : géoréférencement et échantillon décimé
# ---------------------------------------------------------------------------
def _crs_deduit(bounds) -> Tuple[Optional[str], str]:
    g, b, d, h = bounds
    if -12 < g < 20 and -12 < d < 20 and 35 < b < 56 and 35 < h < 56:
        return "EPSG:4326", "coordonnées géographiques (WGS 84)"
    if 5.8e6 < h < 7.3e6 and -4e5 < g < 1.4e6:
        return "EPSG:2154", "Lambert-93"
    if 1.5e6 < h < 2.9e6 and -2e5 < g < 1.4e6:
        return "EPSG:27572", "Lambert II étendu (grille SAFRAN)"
    return None, "inconnu"


def _nettoyer(data, nodata) -> np.ndarray:
    """Valeurs manquantes et sentinelles ramenées à NaN."""
    out = np.array(data, dtype="float64")
    if nodata is not None and not (isinstance(nodata, float) and np.isnan(nodata)):
        out[out == nodata] = np.nan
    out[~np.isfinite(out)] = np.nan
    out[(out < -1e6) | (out > 1e7)] = np.nan
    return out


@lru_cache(maxsize=64)
def _entete(chemin: str, mtime: float, crs_force: str) -> Dict[str, Any]:
    """Géoréférencement et échantillon décimé. Ne lit jamais le raster en pleine résolution."""
    rasterio, CRS = _rio["rasterio"], _rio["CRS"]
    with rasterio.open(chemin) as src:
        crs, note_crs = src.crs, ""
        if crs is None:
            if crs_force and crs_force.lower() != "auto":
                crs = CRS.from_user_input(crs_force)
                note_crs = f"SCR absent du fichier : {crs_force} imposé par le référentiel."
            else:
                code, lib = _crs_deduit(src.bounds)
                if code is None:
                    raise ValueError(
                        f"Système de coordonnées absent et non déductible pour {os.path.basename(chemin)}. "
                        "Le préciser dans la feuille Cartes (colonne SCR).")
                crs = CRS.from_user_input(code)
                note_crs = f"SCR absent du fichier : {lib} déduit de l'emprise."
        pas = max(1, int(max(src.height, src.width) / COTE_ECHANTILLON))
        forme = (max(1, src.height // pas), max(1, src.width // pas))
        echantillon = _nettoyer(src.read(1, out_shape=forme, masked=False), src.nodata)
        # Unité inscrite dans les métadonnées du fichier (étiquette GDAL « UNITS »), si présente
        unite_fichier = (src.tags(1).get("UNITS") or src.tags().get("UNITS") or src.units[0] or "").strip()
        return {"transform": src.transform, "crs": crs, "bounds": src.bounds, "nodata": src.nodata,
                "hauteur": src.height, "largeur": src.width, "echantillon": echantillon,
                "note_crs": note_crs, "fichier": os.path.basename(chemin), "unite_fichier": unite_fichier}


def entete(chemin: str, crs_force: str = "auto") -> Dict[str, Any]:
    return _entete(chemin, os.path.getmtime(chemin), crs_force or "auto")


# ---------------------------------------------------------------------------
# Unités
# ---------------------------------------------------------------------------
def _unite(declaree: str, echantillon: np.ndarray, facteurs: Dict[str, float], ancre: Optional[float],
           defaut: str, unite_fichier: str = "") -> Tuple[str, float, bool]:
    """Renvoie (unité, facteur vers l'unité de l'application, unité déduite ?).

    Ordre de priorité : unité déclarée dans la feuille Cartes, puis unité inscrite dans le
    fichier, puis unité déduite de l'ordre de grandeur des valeurs (comparées à « ancre »)."""
    if declaree and declaree != "auto" and declaree in facteurs:
        return declaree, facteurs[declaree], False
    if unite_fichier in facteurs:
        return unite_fichier, facteurs[unite_fichier], False
    v = echantillon[np.isfinite(echantillon) & (echantillon > 0)]
    if v.size == 0 or not ancre or ancre <= 0:
        return defaut, facteurs[defaut], True
    med = float(np.median(v))
    meilleure = min(facteurs, key=lambda u: abs(np.log(med * facteurs[u] / ancre)))
    return meilleure, facteurs[meilleure], True


# ---------------------------------------------------------------------------
# Rendement potentiel (dénominateur des cartes de rendement en %)
# ---------------------------------------------------------------------------
_cache_especes: Dict[str, Any] = {}


def rendements_optimaux(chemin: str) -> Dict[str, float]:
    """RENDEMENT_OPTIMAL (t/ha) par code d'espèce MAELIA, lu dans especesCultivees.csv
    (codes en minuscules ; « NA » et cases vides ignorés)."""
    if not chemin or not os.path.exists(chemin):
        return {}
    mtime = os.path.getmtime(chemin)
    if _cache_especes.get("cle") == (chemin, mtime):
        return _cache_especes["valeurs"]
    valeurs: Dict[str, float] = {}
    entete_csv = None
    with open(chemin, encoding="utf-8-sig", errors="replace") as fic:
        for ligne in fic:
            cases = [c.strip() for c in ligne.rstrip("\r\n").split(";")]
            if entete_csv is None and cases and cases[0].upper() == "ESPECE":
                entete_csv = [c.lower() for c in cases]
            elif entete_csv and cases and cases[0].upper() == "RENDEMENT_OPTIMAL":
                for code, v in zip(entete_csv[1:], cases[1:]):
                    try:
                        x = float(v.replace(",", "."))
                    except ValueError:
                        continue
                    if x > 0:
                        valeurs[code] = x
                break
    _cache_especes.update({"cle": (chemin, mtime), "valeurs": valeurs})
    return valeurs


def rendement_potentiel(ref, culture: str, info: Dict[str, Any], chemin_especes: str = "") -> Dict[str, Any]:
    """Rendement potentiel (q/ha) de la culture : RENDEMENT_OPTIMAL de especesCultivees.csv
    (t/ha × 10) pour le code de carte, sinon rendement irrigué du référentiel."""
    code = (info.get("code") or "").lower()
    opt = rendements_optimaux(chemin_especes).get(code)
    if opt:
        return {"valeur": opt * 10.0, "source": f"rendement optimal MAELIA de l'espèce « {info.get('code')} » "
                                                 f"(especesCultivees.csv : {opt:g} t/ha)"}
    v = ref.valeur("Cultures", culture, "rdt_irrigue")
    p = ref.param("Cultures", culture, "rdt_irrigue")
    r = ref.reference(p.ref_id) if p else None
    return {"valeur": v, "source": "rendement irrigué du référentiel" + (f" {r.citation}" if r else "")}


def unites_culture(ref, culture: str, info: Dict[str, Any],
                   chemin_especes: str = "") -> Dict[str, Tuple[str, float, bool]]:
    """Unité de chaque famille de cartes : déclarée dans le référentiel, inscrite dans le
    fichier, sinon déduite. Pour des rendements en %, le facteur ramène au rendement potentiel."""
    f = info["fichiers"]
    out: Dict[str, Tuple[str, float, bool]] = {}
    if f.get("rdt_irrigue"):
        e = entete(f["rdt_irrigue"], info["crs"])
        facteurs = dict(FACTEURS_RDT)
        pot = rendement_potentiel(ref, culture, info, chemin_especes)
        if pot["valeur"]:
            facteurs[POURCENT] = pot["valeur"] / 100.0
        out["rdt"] = _unite(info["unite_rdt"], e["echantillon"], facteurs,
                            ref.valeur("Cultures", culture, "rdt_irrigue"), "q/ha", e["unite_fichier"])
        out["potentiel"] = pot
    else:
        out["rdt"] = ("q/ha", 1.0, True)
    if f.get("besoin"):
        e = entete(f["besoin"], info["crs"])
        out["besoin"] = _unite(info["unite_besoin"], e["echantillon"], FACTEURS_BESOIN,
                               ref.valeur("Cultures", culture, "besoin_irrigation"), "mm", e["unite_fichier"])
    else:
        out["besoin"] = ("mm", 1.0, True)
    return out


# ---------------------------------------------------------------------------
# Extraction à la commune : lecture de la seule fenêtre utile
# ---------------------------------------------------------------------------
def _sommets(coords, xs, ys):
    """Parcours récursif des coordonnées d'une géométrie GeoJSON."""
    if coords and isinstance(coords[0], (int, float)):
        xs.append(coords[0])
        ys.append(coords[1])
        return
    for c in coords or []:
        _sommets(c, xs, ys)


def _fenetre_geometrie(e: Dict[str, Any], geometrie: dict):
    """Fenêtre du raster couvrant la commune, élargie de quelques mailles."""
    g = _rio["transform_geom"]("EPSG:4326", e["crs"], geometrie)
    xs: list = []
    ys: list = []
    _sommets(g.get("coordinates"), xs, ys)
    if not xs:
        return None, None
    fen = _rio["from_bounds"](min(xs), min(ys), max(xs), max(ys), transform=e["transform"])
    fen = fen.round_offsets(op="floor").round_lengths(op="ceil")
    col, row = int(fen.col_off) - MARGE_MAILLES, int(fen.row_off) - MARGE_MAILLES
    col0, row0 = max(col, 0), max(row, 0)
    col1 = min(col + int(fen.width) + 2 * MARGE_MAILLES, e["largeur"])
    row1 = min(row + int(fen.height) + 2 * MARGE_MAILLES, e["hauteur"])
    if col1 <= col0 or row1 <= row0:
        return None, None                      # commune hors de l'emprise de la carte
    return _rio["Window"](col0, row0, col1 - col0, row1 - row0), g


def _fenetre_point(e: Dict[str, Any], lonlat: Tuple[float, float], rayon: int):
    """Fenêtre carrée centrée sur un point, de demi-côté « rayon » mailles."""
    xs, ys = _rio["warp_transform"]("EPSG:4326", e["crs"], [lonlat[0]], [lonlat[1]])
    col, row = ~e["transform"] * (xs[0], ys[0])
    col, row = int(np.floor(col)), int(np.floor(row))
    col0, row0 = max(col - rayon, 0), max(row - rayon, 0)
    col1, row1 = min(col + rayon + 1, e["largeur"]), min(row + rayon + 1, e["hauteur"])
    if col1 <= col0 or row1 <= row0:
        return None
    return _rio["Window"](col0, row0, col1 - col0, row1 - row0)


def _valeur_zone(chemin: str, e: Dict[str, Any], geometrie: Optional[dict],
                 lonlat: Optional[Tuple[float, float]]) -> Dict[str, Any]:
    """Valeur communale, dans l'unité du fichier. Ne lit que les fenêtres nécessaires."""
    with _rio["rasterio"].open(chemin) as src:
        if geometrie:
            try:
                fen, g = _fenetre_geometrie(e, geometrie)
                if fen is not None:
                    bloc = _nettoyer(src.read(1, window=fen, masked=False), e["nodata"])
                    masque = _rio["geometry_mask"]([g], out_shape=bloc.shape,
                                                   transform=src.window_transform(fen),
                                                   invert=True, all_touched=True)
                    vals = bloc[masque & np.isfinite(bloc)]
                    if vals.size:
                        return {"valeur": float(vals.mean()), "n": int(vals.size),
                                "methode": "mailles touchant la commune"}
            except Exception:
                pass                            # repli sur le centre de la commune
        if lonlat is None:
            return {"valeur": None, "n": 0, "methode": "aucune maille"}
        for rayon in range(0, MARGE_MAILLES + 1):
            fen = _fenetre_point(e, lonlat, rayon)
            if fen is None:
                continue
            bloc = _nettoyer(src.read(1, window=fen, masked=False), e["nodata"])
            vals = bloc[np.isfinite(bloc)]
            if vals.size:
                methode = ("maille du centre de la commune" if rayon == 0
                           else f"maille valide la plus proche (rayon {rayon})")
                return {"valeur": float(vals.mean()), "n": int(vals.size), "methode": methode}
    return {"valeur": None, "n": 0, "methode": "hors emprise ou sans donnée"}


def extraire(ref, culture: str, info: Dict[str, Any], geometrie: Optional[dict],
             lonlat: Optional[Tuple[float, float]], chemin_especes: str = "") -> Dict[str, Any]:
    """Valeurs agronomiques communales, converties dans les unités de l'application (q/ha et mm)."""
    if not _charger_rasterio():
        raise RuntimeError(f"lecture des cartes indisponible : {_erreur_rio}")
    unites = unites_culture(ref, culture, info, chemin_especes)
    sortie: Dict[str, Any] = {"notes": [], "brut": {}, "unites": {}, "potentiel": unites.get("potentiel")}
    for var in VARIABLES:
        chemin = info["fichiers"].get(var)
        if not chemin:
            sortie[var] = None
            continue
        e = entete(chemin, info["crs"])
        z = _valeur_zone(chemin, e, geometrie, lonlat)
        u, fac, deduite = unites["besoin" if var == "besoin" else "rdt"]
        sortie["brut"][var] = {"valeur": z["valeur"], "fichier": e["fichier"], "n_mailles": z["n"],
                               "methode": z["methode"], "unite_source": u, "unite_deduite": deduite,
                               "facteur": fac}
        sortie[var] = None if z["valeur"] is None else z["valeur"] * fac
        sortie["unites"][var] = u
        if e["note_crs"] and e["note_crs"] not in sortie["notes"]:
            sortie["notes"].append(e["note_crs"])
    return sortie


# ---------------------------------------------------------------------------
# Carte de couleur d'une variable (rendement irrigué, rendement pluvial ou besoin en eau)
# ---------------------------------------------------------------------------
# Rendements : rouge (faible) -> vert (fort). Besoin en eau : jaune (faible) -> bleu (fort).
_ROUGE = (214.0, 46.0, 39.0)
_VERT = (24.0, 143.0, 79.0)
_JAUNE = (255.0, 208.0, 0.0)
_BLEU = (0.0, 62.0, 145.0)
_RAMPES = {
    "rdt_irrigue": (_ROUGE, _VERT),
    "rdt_pluvial": (_ROUGE, _VERT),
    "besoin": (_JAUNE, _BLEU),
}
_OPACITE_MAILLE = 200          # sur 255 : laisse deviner le fond de carte sous la couche

_cache_variable: Dict[tuple, Dict[str, Any]] = {}
_verrou_variable = threading.Lock()


def _grille_destination(chemin: str, dst_crs: str):
    rasterio = _rio["rasterio"]
    with rasterio.open(chemin) as src:
        return _rio["calculate_default_transform"](src.crs, dst_crs, src.width, src.height, *src.bounds)


def _reprojeter(chemin: str, dst_crs: str, transform, width: int, height: int) -> np.ndarray:
    rasterio = _rio["rasterio"]
    dest = np.full((height, width), np.nan, dtype="float32")
    with rasterio.open(chemin) as src:
        _rio["reproject"](source=rasterio.band(src, 1), destination=dest,
                          src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                          dst_transform=transform, dst_crs=dst_crs, dst_nodata=np.nan,
                          resampling=_rio["Resampling"].bilinear)
    return dest


def _normaliser(arr: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """Ramène les valeurs finies de arr sur [0, 1] (min-max) ; NaN inchangé."""
    fini = arr[np.isfinite(arr)]
    if fini.size == 0:
        return np.zeros_like(arr), 0.0, 0.0
    lo, hi = float(fini.min()), float(fini.max())
    if hi - lo < 1e-9:
        return np.where(np.isfinite(arr), 0.5, np.nan), lo, hi
    return (arr - lo) / (hi - lo), lo, hi


def _teinte_univariee(t: np.ndarray, valide: np.ndarray, basse: Tuple[float, float, float],
                      haute: Tuple[float, float, float]) -> np.ndarray:
    """Image RGBA (uint8) : dégradé linéaire de « basse » (valeur faible) à « haute » (valeur forte)."""
    tt = np.clip(np.nan_to_num(t), 0.0, 1.0)
    r0, g0, b0 = basse
    r1, g1, b1 = haute
    rgb = np.stack([r0 + (r1 - r0) * tt, g0 + (g1 - g0) * tt, b0 + (b1 - b0) * tt], axis=-1)
    h, w = tt.shape
    rgba = np.zeros((h, w, 4), dtype="uint8")
    rgba[..., :3] = np.clip(rgb, 0, 255).astype("uint8")
    rgba[..., 3] = np.where(valide, _OPACITE_MAILLE, 0).astype("uint8")
    return rgba


def _encoder_png(rgba: np.ndarray) -> bytes:
    h, w, _n = rgba.shape
    profil = {"driver": "PNG", "height": h, "width": w, "count": 4, "dtype": "uint8"}
    with _rio["MemoryFile"]() as mem:
        with mem.open(**profil) as dst:
            for i in range(4):
                dst.write(rgba[:, :, i], i + 1)
        return bytes(mem.read())


def carte_variable(ref, culture: str, info: Dict[str, Any], variable: str,
                   chemin_especes: str = "") -> Optional[Dict[str, Any]]:
    """Image PNG (RGBA, EPSG:4326) d'une variable (rendement irrigué, rendement pluvial ou
    besoin en eau), prête à superposer sur la carte (bornes en [[sud, ouest], [nord, est]]).

    Renvoie None si la variable est inconnue, si sa carte n'est pas présente pour la culture,
    ou si rasterio est indisponible.
    """
    if variable not in VARIABLES or not _charger_rasterio():
        return None
    chemin = info["fichiers"].get(variable)
    if not chemin:
        return None

    especes_mtime = os.path.getmtime(chemin_especes) if chemin_especes and os.path.exists(chemin_especes) else 0
    cle = (culture, variable, os.path.getmtime(chemin), ref.date_modification, especes_mtime)
    with _verrou_variable:
        if cle in _cache_variable:
            return _cache_variable[cle]

    unites = unites_culture(ref, culture, info, chemin_especes)
    _u, fac, _deduite = unites["besoin" if variable == "besoin" else "rdt"]
    u = VARIABLES[variable]["unite"]   # valeurs converties dans l'unité de l'application (q/ha ou mm)

    dst_crs = "EPSG:4326"
    transform, width, height = _grille_destination(chemin, dst_crs)
    valeurs = _reprojeter(chemin, dst_crs, transform, width, height) * fac

    valide = np.isfinite(valeurs)
    norm, v_min, v_max = _normaliser(np.where(valide, valeurs, np.nan))
    basse, haute = _RAMPES[variable]
    rgba = _teinte_univariee(norm, valide, basse, haute)
    png = _encoder_png(rgba)

    ouest, nord = transform * (0, 0)
    est, sud = transform * (width, height)
    resultat = {
        "png_base64": base64.b64encode(png).decode("ascii"),
        "bounds": [[sud, ouest], [nord, est]],
        "min": v_min, "max": v_max, "unite": u,
        "libelle": VARIABLES[variable]["libelle"],
        "couleur_basse": [int(round(c)) for c in basse],
        "couleur_haute": [int(round(c)) for c in haute],
    }
    with _verrou_variable:
        _cache_variable[cle] = resultat
        while len(_cache_variable) > 100:
            _cache_variable.pop(next(iter(_cache_variable)))
    return resultat
