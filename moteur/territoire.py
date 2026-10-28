# -*- coding: utf-8 -*-
"""
Diagnostic du territoire
========================
Indicateurs de contexte d'une commune, lus dans ``territoire/indicateurs_communes.csv`` (produit par
``outils/preparer_territoire.py``) et classés d'après les seuils de la feuille « Territoire » du
référentiel :

- tension sur la ressource : zones de répartition des eaux (ZRE), jours de restriction sécheresse ;
- usages concurrents : ouvrages hydroélectriques, d'eau potable et d'irrigation (ROE) ;
- sol : réserve utile et profondeur (carte des sols de la simulation), formation affleurante (BDLISA) ;
- projections hydroclimatiques (RCP4.5, 2021-2050 à 2071-2100) : besoin en eau de la culture et bilan
  P − ETP (DRIAS, méthode SGPE), débits d'étiage, d'été et d'hiver à la station Explore2 la plus proche ;
- accès à l'eau : cours d'eau permanent et canal les plus proches (BD TOPAGE), première nappe
  (BDLISA), irrigation existante (RA 2020), et classement des types d'accès du référentiel, qui tient
  compte de l'évolution projetée des débits d'étiage et d'hiver.

Les distances sont mesurées depuis un point intérieur de la commune : elles situent la commune,
pas la parcelle.
"""

from __future__ import annotations

import csv
import os
import threading
from typing import Any, Dict, List, Optional

from .calcul import type_source

_verrou = threading.Lock()
_cache: Dict[str, Any] = {"chemin": None, "mtime": None, "lignes": {}}

FAVORABLE, VIGILANCE, DEFAVORABLE, INFO = "favorable", "vigilance", "defavorable", "info"
SCORE = {FAVORABLE: 2, VIGILANCE: 1, DEFAVORABLE: 0}

NATURE = {"5": "unité aquifère", "6": "formation semi-perméable", "7": "formation imperméable"}
ETAT = {"1": "nappe captive", "2": "nappe libre", "3": "nappe libre et captive"}
MILIEU = {"1": "milieu poreux", "2": "milieu fissuré", "3": "milieu karstique"}
THEME = {"1": "alluvial", "2": "sédimentaire", "3": "socle", "4": "montagne plissée", "5": "volcanique"}

# Ordre de préférence à score égal : du moins coûteux au plus coûteux
ORDRE_ACCES = ("asa", "cours_eau", "forage", "retenue_pompage", "retenue_collinaire")


def _lire(chemin: str) -> Dict[str, Dict[str, str]]:
    with open(chemin, encoding="utf-8", newline="") as f:
        return {l["code"]: l for l in csv.DictReader(f)}


def donnees(chemin: Optional[str], code: str) -> Optional[Dict[str, str]]:
    """Ligne du fichier d'indicateurs pour une commune (code INSEE), ou None."""
    if not chemin or not code or not os.path.exists(chemin):
        return None
    with _verrou:
        mtime = os.path.getmtime(chemin)
        if _cache["chemin"] != chemin or _cache["mtime"] != mtime:
            _cache.update(chemin=chemin, mtime=mtime, lignes=_lire(chemin))
        return _cache["lignes"].get(str(code))


def _f(ligne: Dict[str, str], cle: str) -> Optional[float]:
    try:
        v = float(ligne.get(cle) or "")
    except ValueError:
        return None
    return v if v == v else None


def _code(ligne: Dict[str, str], cle: str) -> str:
    v = _f(ligne, cle)
    return str(int(v)) if v is not None else (ligne.get(cle) or "")


def _nb(v: Optional[float], dec: int = 0) -> str:
    if v is None:
        return "–"
    return f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")


def _distance(m: Optional[float]) -> str:
    if m is None:
        return "aucun recensé"
    return f"{_nb(m)} m" if m < 1000 else f"{_nb(m / 1000, 1)} km"


def _ind(libelle: str, valeur: str, niveau: str, bulle: str) -> Dict[str, str]:
    return {"libelle": libelle, "valeur": valeur, "niveau": niveau, "bulle": bulle}


class _Seuils:
    """Seuils de la feuille Territoire, avec la source de chacun pour les info-bulles."""

    def __init__(self, ref, surcharges):
        self.ref, self.surcharges = ref, surcharges

    def __call__(self, objet: str, code: str, defaut: float) -> float:
        return self.ref.valeur("Territoire", objet, code, self.surcharges, defaut)

    def source(self, objet: str, code: str) -> str:
        p = self.ref.param("Territoire", objet, code)
        return self.ref.infobulle(p) if p else ""

    def citation(self, ref_id: str) -> str:
        r = self.ref.reference(ref_id)
        return r.citation if r else ""


# ---------------------------------------------------------------------------
# Fiches
# ---------------------------------------------------------------------------
def _niveau_restrictions(jours: Optional[float], annees_crise: Optional[float], s: _Seuils) -> str:
    if jours is None:
        return INFO
    if jours >= s("Tension", "jours_restriction_defavorable", 30) or \
            (annees_crise or 0) >= s("Tension", "annees_crise_defavorable", 3):
        return DEFAVORABLE
    if jours >= s("Tension", "jours_restriction_vigilance", 10) or (annees_crise or 0) >= 1:
        return VIGILANCE
    return FAVORABLE


def _fiche_tension(l, s: _Seuils) -> Dict[str, Any]:
    seuil = s("Tension", "part_zre", 0.5)
    sup, sout = _f(l, "zre_sup_part") or 0, _f(l, "zre_sout_part") or 0
    noms = l.get("zre_noms") or ""
    zre = _ind("Zone de répartition des eaux (ZRE)",
               f"superficielle {_nb(sup * 100)} % · souterraine {_nb(sout * 100)} % de la commune",
               # Une ZRE souterraine peut ne viser qu'une nappe captive profonde (Albien…) : vigilance seulement
               DEFAVORABLE if sup >= seuil else (VIGILANCE if max(sup, sout) > 0 else FAVORABLE),
               f"Part de la surface communale en ZRE {s.citation('SANDRE_ZRE')}"
               + (f" : {noms}" if noms else "") + ". En ZRE, l'insuffisance de la ressource par rapport aux "
               "besoins est chronique : les autorisations de prélèvement sont plafonnées et la redevance relève de "
               "la catégorie 2. Une ZRE souterraine peut ne concerner qu'une nappe (souvent captive et profonde) : "
               "à rapprocher de la nappe effectivement captée.")
    indicateurs = [zre]
    for t, nom in (("sup", "eaux superficielles"), ("sou", "eaux souterraines")):
        j_ar, j_al, j_cr = (_f(l, f"{t}_j_alerte_renforcee"), _f(l, f"{t}_j_alerte"), _f(l, f"{t}_j_crise"))
        a_cr = _f(l, f"{t}_annees_crise")
        indicateurs.append(_ind(
            f"Restrictions sécheresse, {nom}",
            "non renseigné" if j_ar is None else
            f"{_nb(j_ar)} j/an en alerte renforcée ou crise · crise {_nb(a_cr)} année(s) sur 10",
            _niveau_restrictions(j_ar, a_cr, s),
            f"Moyenne 2016-2025 {s.citation('VIGIEAU_2026')} des jours où la commune était au moins au niveau "
            f"indiqué (niveau le plus sévère des zones d'alerte qui la touchent) : alerte ou plus {_nb(j_al)} j/an, "
            f"alerte renforcée ou plus {_nb(j_ar)} j/an, crise {_nb(j_cr)} j/an. L'alerte renforcée réduit "
            "fortement les prélèvements d'irrigation ; la crise les interdit, sauf usages prioritaires. "
            f"Seuils : {s.source('Tension', 'jours_restriction_vigilance')}"))
    sage = l.get("sage") or ""
    indicateurs.append(_ind("Schéma d'aménagement et de gestion des eaux (SAGE)", sage or "aucun", INFO,
                            f"Périmètres des SAGE {s.citation('SANDRE_SAGE')}. Le règlement du SAGE peut encadrer "
                            "les prélèvements et la création de retenues."))
    return {"id": "tension", "titre": "Tension sur la ressource", "indicateurs": indicateurs}


def _fiche_usages(l, s: _Seuils) -> Dict[str, Any]:
    n = {k: int(_f(l, k) or 0) for k in ("roe_total", "roe_barrages", "roe_hydro", "roe_aep", "roe_irrigation")}
    src = (f"Ouvrages existants du référentiel des obstacles à l'écoulement {s.citation('ROE_OFB')} situés dans "
           "la commune, d'après leur usage déclaré.")
    sau, secret = _f(l, "sau_irr_pct"), _f(l, "sau_irr_secret")
    return {"id": "usages", "titre": "Usages concurrents et ouvrages", "indicateurs": [
        _ind("Ouvrages hydroélectriques", _nb(n["roe_hydro"]), VIGILANCE if n["roe_hydro"] else FAVORABLE,
             src + " Un prélèvement en amont réduit le débit turbiné : conflit d'usage possible en étiage."),
        _ind("Ouvrages liés à l'eau potable", _nb(n["roe_aep"]), VIGILANCE if n["roe_aep"] else FAVORABLE,
             src + " L'alimentation en eau potable est prioritaire sur l'irrigation en période de crise."),
        _ind("Ouvrages liés à l'irrigation", _nb(n["roe_irrigation"]), INFO,
             src + " Prises d'eau et seuils existants : indice d'une irrigation déjà organisée."),
        _ind("Barrages et seuils recensés", f"{_nb(n['roe_barrages'])} barrage(s) · {_nb(n['roe_total'])} ouvrage(s)",
             INFO, src),
        _ind("Part de la SAU irriguée en 2020",
             "secret statistique" if secret and sau is None else f"{_nb(sau, 1)} %", INFO,
             f"Recensement agricole 2020 {s.citation('AGRESTE_RA2020')} : superficie irriguée rapportée à la "
             "surface agricole utile de la commune. Une part élevée signale des usages agricoles déjà en "
             "concurrence pour la ressource, mais aussi des infrastructures et des savoir-faire existants."),
    ]}


def _fiche_sol(l, s: _Seuils, sol: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    indicateurs = []
    if sol and sol.get("ru") is not None:
        ru = sol["ru"]
        faible, elevee = s("Sol", "ru_faible", 80), s("Sol", "ru_elevee", 150)
        classe, niveau = (("faible", VIGILANCE) if ru < faible else ("élevée", FAVORABLE) if ru >= elevee
                          else ("moyenne", INFO))
        origine = {"carte": "carte des sols", "saisie": "valeur saisie", "referentiel": "valeur par défaut"}
        indicateurs.append(_ind(
            "Réserve utile du sol", f"{_nb(ru)} mm ({classe})", niveau,
            f"Réserve utile retenue pour le bilan hydrique ({origine.get(sol.get('origine'), '')}). Faible "
            f"(< {_nb(faible)} mm) : le sol retient peu l'eau, les apports doivent être fréquents et le besoin "
            f"d'irrigation est plus élevé ; élevée (≥ {_nb(elevee)} mm) : le sol tamponne les déficits. "
            + s.source("Sol", "ru_faible")))
        if sol.get("profondeur") is not None:
            indicateurs.append(_ind("Profondeur de sol", f"{_nb(sol['profondeur'], 1)} m", INFO,
                                    "Profondeur de sol de la simulation (BDGSF ou valeur saisie)."))
    nature, theme = _code(l, "eh_nature"), _code(l, "eh_theme")
    if l.get("eh_libelle"):
        indicateurs.append(_ind(
            "Formation géologique affleurante",
            f"{NATURE.get(nature, 'nature inconnue')}" + (f", {THEME[theme]}" if theme in THEME else ""), INFO,
            f"{l['eh_libelle']} {s.citation('BDLISA')}. Une formation imperméable ou semi-perméable limite "
            "l'infiltration (ruissellement, retenue plus facile à rendre étanche) ; une formation aquifère "
            "affleurante infiltre et recharge la nappe."))
    return {"id": "sol", "titre": "Sol et sous-sol", "indicateurs": indicateurs}


HORIZONS = (("H1", "2021-2050"), ("H2", "2041-2070"), ("H3", "2071-2100"))
NIVEAUX_TRACC = (("2c", "+2 °C"), ("27c", "+2,7 °C"), ("4c", "+4 °C"))


def _niveau_debit(v: Optional[float], s: _Seuils) -> str:
    """Classement d'un changement de débit (%) à l'horizon moyen, durée d'amortissement des ouvrages."""
    if v is None:
        return INFO
    if v <= s("Projections", "baisse_debit_defavorable", -30):
        return DEFAVORABLE
    return VIGILANCE if v <= s("Projections", "baisse_debit_vigilance", -10) else FAVORABLE


def _fiche_projections(l, s: _Seuils, proj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    indicateurs = []
    if proj:
        h = proj["horizons"]
        serie = lambda cle, dec=0: " → ".join(f"{_nb(h[k][cle], dec)}" for k, _ in HORIZONS)  # noqa: E731
        drias = s.citation("DRIAS_2020")
        b1, b3 = h["H1"].get("besoin_mm"), h["H3"].get("besoin_mm")
        if b1 is not None and b3 is not None:
            hausse = (b3 - b1) / b1 if b1 else 0.0
            indicateurs.append(_ind(
                f"Besoin en eau, {proj['culture'].lower()}", serie("besoin_mm") + " mm",
                VIGILANCE if hausse >= s("Projections", "hausse_besoin_vigilance", 0.1) else INFO,
                f"Besoin d'irrigation de la méthode SGPE pour 2021-2050, 2041-2070 et 2071-2100 (RCP4.5, ETP et "
                f"pluie {drias}), avec le sol de la simulation : {'+' if hausse >= 0 else '−'}"
                f"{_nb(abs(hausse) * 100)} % entre l'horizon proche et l'horizon lointain."))
        indicateurs.append(_ind(
            "Bilan climatique d'avril à septembre (P − ETP)", serie("bilan_ete") + " mm", INFO,
            f"Pluie moins évapotranspiration potentielle cumulées d'avril à septembre, par horizon {drias}, point de "
            f"grille à {_nb(proj['distance_km'], 1)} km. Plus il est négatif, plus la saison est sèche."))
        indicateurs.append(_ind(
            "Excédent hivernal (octobre à mars)", serie("excedent_hiver") + " mm", INFO,
            f"Somme des excédents mensuels P − ETP d'octobre à mars {drias} : eau disponible pour la recharge des "
            "nappes, le ruissellement et le remplissage des retenues."))
    station = l.get("e2_station")
    if station:
        src = (f"Projections hydrologiques Explore2 {s.citation('EXPLORE2_2025')}, RCP4.5, changement par rapport à "
               f"1976-2005 : médiane de {_nb(_f(l, 'e2_n'))} simulations (modèles climatiques × 9 modèles "
               f"hydrologiques, chaînes aberrantes exclues) à la station « {station} »"
               + (f" ({_nb(_f(l, 'e2_surface_km2'))} km² de bassin)" if _f(l, "e2_surface_km2") else "")
               + f", à {_nb(_f(l, 'e2_dist_km'), 1)} km de la commune. Classement à l'horizon 2041-2070, durée "
               "d'amortissement des ouvrages.")
        for cle, libelle, explication in (
                ("qmna", "Débit d'étiage (QMNA)", "Plus bas débit mensuel de l'année : ressource disponible pour "
                                                 "un pompage en été."),
                ("ete", "Débit d'été (juin-août)", "Débit moyen de juin à août."),
                ("hiver", "Débit d'hiver (décembre-février)", "Débit moyen de décembre à février : remplissage "
                                                             "des retenues par pompage.")):
            med = [_f(l, f"e2_{cle}_{k.lower()}") for k, _ in HORIZONS]
            if all(v is None for v in med):
                continue
            bas, haut = _f(l, f"e2_{cle}_h2_bas"), _f(l, f"e2_{cle}_h2_haut")
            valeur = " → ".join(("+" if v is not None and v > 0 else "") + _nb(v) for v in med) + " %"
            indicateurs.append(_ind(
                libelle, valeur, _niveau_debit(med[1], s),
                f"{explication} {src} Fourchette 2041-2070 (10 % - 90 % des simulations) : {_nb(bas)} à "
                f"{_nb(haut)} %."))
    if l.get("rech_meso"):
        med = [_f(l, f"rech_{n}") for n, _ in NIVEAUX_TRACC]
        if any(v is not None for v in med):
            indicateurs.append(_ind(
                "Recharge des nappes", " → ".join(("+" if v is not None and v > 0 else "") + _nb(v) for v in med)
                + " % (+2 → +2,7 → +4 °C)", _niveau_debit(med[1], s),
                f"Recharge potentielle annuelle de la masse d'eau souterraine « {l['rech_meso']} » (modèle RECHARGE, "
                f"Explore2 {s.citation('EXPLORE2_2025')}) : {_nb(_f(l, 'rech_ref_mm'))} mm/an en 1976-2005, puis "
                "changement aux niveaux de réchauffement de la France de la trajectoire de référence pour "
                "l'adaptation (TRACC : +2,7 °C vers 2050, +4 °C vers 2100). Médiane de "
                f"{_nb(_f(l, 'rech_n'))} projections climatiques ; fourchette à +2,7 °C (10 % - 90 %) : "
                f"{_nb(_f(l, 'rech_27c_bas'))} à {_nb(_f(l, 'rech_27c_haut'))} %. Classement à +2,7 °C. "
                "Recharge annuelle : elle ne dit rien des niveaux d'été, dont dépend le débit d'un forage."))
    return {"id": "projections", "titre": "Projections hydroclimatiques", "indicateurs": indicateurs,
            "horizons": [libelle for _, libelle in HORIZONS],
            "avertissement": "Valeurs par horizon : 2021-2050 → 2041-2070 → 2071-2100 (scénario d'émissions "
                             "modérées RCP4.5) ; recharge des nappes par niveau de réchauffement de la TRACC. La "
                             "dispersion des simulations est un résultat en soi : voir les fourchettes au survol."}


def _fiche_acces(l, s: _Seuils, ref, source_courante: str) -> Dict[str, Any]:
    d_perm, d_large, d_canal = _f(l, "d_ce_perm_m"), _f(l, "d_ce_large_m"), _f(l, "d_canal_m")
    canal = (_f(l, "canal_commune") or 0) >= 1
    sau = _f(l, "sau_irr_pct")
    aq_etat, aq_milieu, aq_theme = _code(l, "aq_etat"), _code(l, "aq_milieu"), _code(l, "aq_theme")
    aq_rang = _f(l, "aq_rang")
    max_ce, max_large = s("Acces", "distance_cours_eau", 1000), s("Acces", "distance_cours_eau_large", 3000)
    max_canal, sau_coll = s("Acces", "distance_canal", 1000), s("Acces", "sau_irriguee_collectif", 0.2)
    rang_max = s("Acces", "rang_aquifere_max", 2)
    topage = s.citation("BDTOPAGE")

    indicateurs = [
        _ind("Cours d'eau permanent le plus proche", _distance(d_perm),
             FAVORABLE if d_perm is not None and d_perm <= max_ce else VIGILANCE,
             f"Distance au tronçon permanent le plus proche (écoulement naturel, hors intermittents) {topage}, "
             "mesurée depuis un point intérieur de la commune : elle situe la commune, pas la parcelle."),
        _ind("Cours d'eau de plus de 5 m de large",
             _distance(d_large) + (f" ({l['nom_ce_large']})" if l.get("nom_ce_large") else ""),
             FAVORABLE if d_large is not None and d_large <= max_large else INFO,
             f"Tronçon permanent des classes de largeur 5-15 m et plus {topage} : débit d'étiage en général plus "
             "soutenu que celui d'un petit cours d'eau."),
        _ind("Canal", "dans la commune" if canal else _distance(d_canal),
             FAVORABLE if canal or (d_canal is not None and d_canal <= max_canal) else INFO,
             f"Tronçons de nature « canal » {topage} : canaux de navigation, d'irrigation ou de drainage, à "
             "distinguer sur place."),
    ]
    if l.get("aq_libelle"):
        desc = ", ".join(x for x in (ETAT.get(aq_etat), MILIEU.get(aq_milieu), THEME.get(aq_theme)) if x)
        rang = int(aq_rang or 1)
        indicateurs.append(_ind(
            "Première nappe", f"{desc}" + (" — affleurante" if rang == 1 else f" — {rang}e formation"),
            (VIGILANCE if aq_theme in ("3", "4") or aq_etat == "1" or rang > rang_max else FAVORABLE),
            f"{l['aq_libelle']} {s.citation('BDLISA')} : première unité aquifère sous la commune "
            f"(rang {rang} depuis la surface). Socle et montagne : productivité faible et aléatoire des forages ; "
            "nappe captive : forage plus profond, ressource souvent réservée à l'eau potable."))
    else:
        indicateurs.append(_ind("Première nappe", "aucune unité aquifère identifiée", DEFAVORABLE,
                                f"Aucune unité aquifère au droit de la commune dans le référentiel BDLISA, niveau "
                                f"local {s.citation('BDLISA')}."))

    tension = {t: _niveau_restrictions(_f(l, f"{t}_j_alerte_renforcee"), _f(l, f"{t}_annees_crise"), s)
               for t in ("sup", "sou")}
    zre = {"sup": (_f(l, "zre_sup_part") or 0) >= s("Tension", "part_zre", 0.5),
           "sou": (_f(l, "zre_sout_part") or 0) >= s("Tension", "part_zre", 0.5)}

    etiage, hiver = _niveau_debit(_f(l, "e2_qmna_h2"), s), _niveau_debit(_f(l, "e2_hiver_h2"), s)
    recharge = _niveau_debit(_f(l, "rech_27c"), s)

    def evaluer(t: str):
        motifs: List[str] = []
        proche = d_perm is not None and d_perm <= max_ce
        if t == "cours_eau":
            niveau = FAVORABLE if proche else DEFAVORABLE
            motifs.append(f"cours d'eau permanent à {_distance(d_perm)}")
            if niveau == FAVORABLE and (tension["sup"] == DEFAVORABLE or zre["sup"]):
                niveau = VIGILANCE
                motifs.append("restrictions estivales fréquentes" if tension["sup"] == DEFAVORABLE else "ZRE")
            if niveau == FAVORABLE and etiage == DEFAVORABLE:
                niveau = VIGILANCE
            if etiage in (VIGILANCE, DEFAVORABLE):
                motifs.append(f"étiages en baisse de {_nb(-(_f(l, 'e2_qmna_h2') or 0))} % en 2041-2070")
        elif t == "forage":
            if not l.get("aq_libelle"):
                niveau = DEFAVORABLE
                motifs.append("pas de nappe identifiée")
            else:
                niveau = FAVORABLE
                if aq_theme in ("3", "4"):
                    niveau = VIGILANCE
                    motifs.append("socle : débit aléatoire")
                if aq_etat == "1" or (aq_rang or 1) > rang_max:
                    niveau = VIGILANCE
                    motifs.append("nappe captive ou profonde")
                if tension["sou"] == DEFAVORABLE or zre["sou"]:
                    niveau = VIGILANCE
                    motifs.append("ZRE ou restrictions fréquentes")
                if recharge in (VIGILANCE, DEFAVORABLE):
                    niveau = VIGILANCE
                    motifs.append(f"recharge en baisse de {_nb(-(_f(l, 'rech_27c') or 0))} % à +2,7 °C")
                if not motifs:
                    motifs.append(ETAT.get(aq_etat, "nappe") + " affleurante ou proche")
        elif t == "retenue_pompage":
            niveau = FAVORABLE if proche else DEFAVORABLE
            motifs.append(f"remplissage hivernal depuis un cours d'eau à {_distance(d_perm)}")
            if hiver in (VIGILANCE, DEFAVORABLE):
                niveau = min(niveau, VIGILANCE, key=SCORE.get)
                motifs.append(f"débits d'hiver en baisse de {_nb(-(_f(l, 'e2_hiver_h2') or 0))} % en 2041-2070")
        elif t == "retenue_collinaire":
            niveau = VIGILANCE
            motifs.append("relief non évalué : site et bassin versant à vérifier")
            if _code(l, "eh_nature") in ("6", "7"):
                motifs.append("sol peu perméable favorable au ruissellement")
        elif t == "asa":
            reseau = canal or (d_canal is not None and d_canal <= max_canal)
            irrigation = sau is not None and sau / 100 >= sau_coll
            niveau = FAVORABLE if reseau and irrigation else VIGILANCE if reseau or irrigation else DEFAVORABLE
            motifs.append(("canal proche" if reseau else "pas de canal proche") + ", " +
                          (f"{_nb(sau)} % de la SAU irriguée" if sau is not None else "SAU irriguée inconnue"))
            motifs.append("périmètres des ASA non disponibles : à vérifier auprès de la DDT")
        else:
            return None
        return niveau, motifs

    options = []
    for nom in ref.sources:
        t = type_source(nom)
        r = evaluer(t)
        if r is None:
            continue
        options.append({"source": nom, "type": t, "niveau": r[0], "motifs": r[1], "retenue": nom == source_courante})
    options.sort(key=lambda o: (-SCORE[o["niveau"]], ORDRE_ACCES.index(o["type"]) if o["type"] in ORDRE_ACCES else 99))
    return {"id": "acces", "titre": "Accès à l'eau", "indicateurs": indicateurs, "options": options,
            "proposee": options[0]["source"] if options and options[0]["niveau"] != DEFAVORABLE else None,
            "avertissement": "Indications à l'échelle de la commune, à confirmer sur la parcelle : distances "
                             "mesurées depuis un point intérieur de la commune, relief non pris en compte."}


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def diagnostic(ref, chemin: Optional[str], code: str, sol: Optional[Dict[str, Any]] = None,
               source: str = "", surcharges=None, projections: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Diagnostic du territoire d'une commune : {"disponible", "agence", "zre", "fiches": [...]}."""
    l = donnees(chemin, code)
    if l is None:
        return {"disponible": False,
                "message": "Diagnostic indisponible : commune non sélectionnée, hors métropole ou fichier "
                           "territoire/indicateurs_communes.csv absent (outils/preparer_territoire.py)."}
    s = _Seuils(ref, surcharges)
    agence = l.get("agence") or None
    return {
        "disponible": True, "code": code, "nom": l.get("nom", ""),
        "agence": agence if agence in ref.agences else None,
        "agence_source": f"circonscription de bassin {s.citation('SANDRE_BASSINS')}",
        "zre": {"sup": _f(l, "zre_sup_part") or 0, "sout": _f(l, "zre_sout_part") or 0,
                "seuil": s("Tension", "part_zre", 0.5), "noms": l.get("zre_noms") or ""},
        "fiches": [_fiche_tension(l, s), _fiche_usages(l, s), _fiche_sol(l, s, sol), _fiche_projections(l, s, projections),
                   _fiche_acces(l, s, ref, source)],
    }
