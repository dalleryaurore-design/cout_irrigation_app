# -*- coding: utf-8 -*-
"""
Analyse financière de l'irrigation
==================================
Application web (Flask) habillée avec le Système de Design de l'État (DSFR).

Lancement :
    pip install -r requirements.txt
    python app.py                 puis ouvrir http://127.0.0.1:5000

Architecture :
    config.py              chemins et options
    moteur/referentiel.py  lecture du référentiel Excel (source unique des hypothèses)
    moteur/calcul.py       chaîne de calcul, sans dépendance d'interface
    moteur/cartes.py       lecture des cartes .tif et extraction à la commune
    templates/, static/    interface DSFR
"""

from __future__ import annotations

import os
import sys
import time
from collections import OrderedDict

# Le dossier de l'application est ajouté au chemin d'import : l'application démarre
# ainsi depuis n'importe quel répertoire courant et depuis un environnement de
# développement qui ne le ferait pas automatiquement.
RACINE_APP = os.path.dirname(os.path.abspath(__file__))
if RACINE_APP not in sys.path:
    sys.path.insert(0, RACINE_APP)

# PROJ télécharge parfois une grille Lambert-93 au premier calcul de carte.
# Sur Render cet appel réseau ne revient pas : le thread meurt, et avec un seul
# process les autres requêtes finissent par ne plus avoir de thread libre.
os.environ["PROJ_NETWORK"] = "OFF"
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "5")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "3")

if not os.path.exists(os.path.join(RACINE_APP, "config.py")):
    raise SystemExit(
        "Fichier « config.py » introuvable dans " + RACINE_APP + ".\n"
        "L'application ne fonctionne qu'avec l'arborescence complète : app.py, config.py, "
        "requirements.txt, et les dossiers moteur/, templates/, static/, referentiel/, cartes/.\n"
        "Téléchargez de nouveau l'archive complète (app_cout_irrigation.zip) et décompressez-la "
        "sans en séparer les fichiers."
    )

from flask import (Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory,
                   url_for)

import config
from moteur import cartes, climat, export, methodologie, rapport, sol, validation
from moteur.calcul import (POSTES, COULEUR_BILAN, COULEUR_GAIN, code_prix, simuler, taux_subvention_acces,
                           type_source, valeurs_derivees)
from moteur.referentiel import CLE_LIBRE, GestionnaireReferentiel, slug

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False
REF = GestionnaireReferentiel(config.REFERENTIEL)
_cache_extraction: "OrderedDict[tuple, dict]" = OrderedDict()
# Les classeurs .xlsx sont des archives zip dont les noms de fichiers se décodent en cp437.
# Ce codec est importé ici, avant le thread de préchauffage : si ce thread et la première
# requête l'importaient en même temps, Python pourrait le déclarer inconnu jusqu'au
# redémarrage (« LookupError: unknown encoding: cp437 », observé sur Render).
import encodings.cp437  # noqa: E402,F401
climat.prechauffer(config.CLIMAT)


# ---------------------------------------------------------------------------
# DSFR : dossier local (téléchargé) ou CDN de repli
# ---------------------------------------------------------------------------
def _dossier_dsfr():
    for d in (config.DSFR_DIR, os.path.join(config.DSFR_DIR, "dist")):
        if d and os.path.exists(os.path.join(d, "dsfr", "dsfr.min.css")):
            return d
    return None


DSFR_LOCAL = _dossier_dsfr()


@app.route("/dsfr/<path:fichier>")
def dsfr(fichier):
    if not DSFR_LOCAL:
        abort(404)
    return send_from_directory(DSFR_LOCAL, fichier)


# ---------------------------------------------------------------------------
# Filtres d'affichage (format français)
# ---------------------------------------------------------------------------
def nombre(v, dec=0):
    if v is None:
        return "–"
    try:
        txt = f"{float(v):,.{dec}f}"
    except (TypeError, ValueError):
        return str(v)
    return txt.replace(",", "\u202f").replace(".", ",")


def valeur_param(p):
    """Valeur affichée d'un paramètre, dans son unité."""
    if p.valeur is None:
        return "–"
    if p.est_pourcentage:
        return nombre(p.valeur * 100, 1 if (p.valeur * 100) % 1 else 0) + " %"
    dec = 0
    if abs(p.valeur) < 10 and p.valeur % 1:
        dec = 3 if abs(p.valeur) < 0.1 else 2
    elif p.valeur % 1:
        dec = 1
    return nombre(p.valeur, dec)


def brut(v):
    """Valeur numérique en écriture brute, pour l'attribut value d'un champ."""
    if v is None or v == "":
        return ""
    f = float(v)
    return str(int(round(f))) if abs(f - round(f)) < 1e-9 else repr(round(f, 6))


app.jinja_env.filters["nombre"] = nombre
app.jinja_env.filters["brut"] = brut
app.jinja_env.filters["valeur_param"] = valeur_param
app.jinja_env.filters["slug"] = slug


@app.context_processor
def contexte():
    ref = REF.get()
    return {
        "TITRE": config.TITRE, "SOUS_TITRE": config.SOUS_TITRE, "OPERATEUR": config.OPERATEUR,
        "DSFR_BASE": url_for("dsfr", fichier="").rstrip("/") if DSFR_LOCAL else config.DSFR_CDN,
        "DSFR_LOCAL": bool(DSFR_LOCAL), "ref": ref,
        "date_referentiel": time.strftime("%d/%m/%Y %H:%M", time.localtime(ref.date_modification)),
        "erreur_referentiel": REF.derniere_erreur,
        "CULTURE_DEFAUT": config.CULTURE_DEFAUT, "COMMUNE_DEFAUT": config.COMMUNE_DEFAUT,
        "DEPARTEMENT_DEFAUT": config.DEPARTEMENT_DEFAUT, "statique": statique,
    }


def statique(fichier: str) -> str:
    """URL d'un fichier statique suffixée de sa date de modification : le navigateur recharge la nouvelle version."""
    try:
        v = int(os.path.getmtime(os.path.join(app.static_folder, fichier)))
    except OSError:
        v = 0
    return url_for("static", filename=fichier, v=v)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.route("/")
def accueil():
    return redirect(url_for("parcelle"))


def _subventions_defaut(ref):
    """Taux de subvention par défaut (en %) pré-remplis dans les formulaires."""
    return {"equipement": round(100 * ref.valeur("Equipement", "Général", "taux_subvention", None, 0.0), 1),
            "acces": {s: round(100 * taux_subvention_acces(ref, {}, s), 1) for s in ref.sources}}


def _prix_cultures(ref):
    """Prix de vente par défaut : prix de marché du référentiel (le barème MASAA reste dans le classeur)."""
    return {"referentiel": {c: ref.valeur("Cultures", c, "prix_vente") for c in ref.cultures}}


def _contexte_simulation(ref, exemple=None):
    """Variables du formulaire de simulation d'une parcelle (volets Cas personnel et Simulations exemples)."""
    cat = cartes.catalogue(ref, config.DOSSIER_CARTES)
    surface_unitaire = {eq: ref.valeur("Equipement", eq, "surface_unitaire")
                        for eq in ref.equipements if ref.param("Equipement", eq, "surface_unitaire")}
    # rasterio n'est sollicité que si des cartes complètes sont effectivement présentes.
    cartes_presentes = any(i["complet"] for i in cat.values())
    return {"catalogue": cat, "exemple": exemple, "prix_cultures": _prix_cultures(ref),
            "surface_unitaire": surface_unitaire,
            "duree_vie_equipements": {eq: ref.valeur("Equipement", eq, "duree_vie") for eq in ref.equipements},
            "duree_vie_sources": {s: ref.valeur("Acces_ressource", s, "duree_vie") for s in ref.sources},
            "subventions": _subventions_defaut(ref),
            "cartes_completes": {c: bool(cat.get(c) and cat[c]["complet"]) for c in ref.cultures},
            "postes": POSTES, "couleur_gain": COULEUR_GAIN, "couleur_bilan": COULEUR_BILAN,
            "cartes_presentes": cartes_presentes,
            "lecture_cartes": bool(config.LECTURE_CARTES and cartes_presentes and cartes.disponible()),
            "fond_carte": config.FOND_CARTE, "erreur_rasterio": cartes.erreur(), "type_source": type_source}


@app.route("/parcelle")
def parcelle():
    """Volet « Cas personnel – parcelle » : toutes les variables modifiables, exports Excel et PDF."""
    ref = REF.get()
    return render_template("parcelle.html", page="parcelle", libre=True,
                           hypotheses=export.hypotheses_couts(ref), **_contexte_simulation(ref))


@app.route("/exemples")
def exemples():
    """Volet « Simulations exemples » : simulation pré-remplie et galerie des exemples."""
    ref = REF.get()
    # Sans paramètre, la simulation s'ouvre sur l'exemple 1 (maïs) ; ?exemple=0 donne un formulaire vierge.
    n = request.args.get("exemple", default=1, type=int)
    exemple = next((x for x in ref.exemples if x["id"] == n), None) if n else None
    onglet = "exemples" if request.args.get("onglet") == "exemples" else "simulation"
    return render_template("exemples.html", page="exemples", libre=False, onglet=onglet,
                           **_contexte_simulation(ref, exemple))


@app.route("/projet")
def projet():
    """Ancienne adresse de la simulation : redirigée vers les simulations exemples."""
    return redirect(url_for("exemples", **request.args))


@app.route("/exploitation")
def exploitation():
    """Ancien mode exploitation (plusieurs parcelles), supprimé : redirigé vers le cas personnel."""
    return redirect(url_for("parcelle"))


@app.route("/trajectoires")
def trajectoires():
    ref = REF.get()
    return render_template("trajectoires.html", page="trajectoires", subventions=_subventions_defaut(ref),
                           prix_cultures=_prix_cultures(ref), type_source=type_source,
                           horizons=climat.LIBELLES_HORIZON)


@app.route("/references")
def references():
    ref = REF.get()
    usage = {}
    for p in ref.params.values():
        usage.setdefault(p.ref_id, 0)
        usage[p.ref_id] += 1
    derives = valeurs_derivees(ref, {}, {"equipement": ref.equipements[0] if ref.equipements else ""})
    onglet = request.args.get("onglet")
    if onglet == "validation":  # ancien onglet, fondu dans la méthodologie
        onglet = "methode"
    if onglet not in ("cultures", "equipement", "acces", "ressources", "references", "methode"):
        onglet = "cultures"
    return render_template("references.html", page="references", usage=usage, postes=POSTES, derives=derives,
                           type_source=type_source, lecture_seule=True, onglet=onglet,
                           catalogue=cartes.catalogue(ref, config.DOSSIER_CARTES))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
# Cartes MAELIA : deux périodes disponibles. Les horizons moyen et lointain lisent la période 2040-2060.
PERIODE_CARTES = {"H1": "2020-2040", "H2": "2040-2060", "H3": "2040-2060"}


def _info_periode(info, horizon):
    """Fichiers de cartes de la période correspondant à l'horizon, s'ils existent (sinon ceux du référentiel)."""
    periode = PERIODE_CARTES.get(horizon, "2020-2040")
    if not info or periode == "2020-2040":
        return info, ""
    fichiers = {}
    for v, f in info["fichiers"].items():
        autre = f.replace("2020-2040", periode) if f else None
        if not autre or not os.path.exists(autre):
            return info, f"Pas de carte {periode} pour cette culture : cartes 2020-2040 utilisées."
        fichiers[v] = autre
    return dict(info, fichiers=fichiers, scenario=(info.get("scenario") or "").replace("2020-2040", periode)), ""


def _nombre_positif(v):
    """Nombre strictement positif saisi dans un champ, sinon None."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


METHODES_SOURCE = ("sgpe", "carte", "reference")
LIBELLES_SOURCE = {"sgpe": "SGPE", "carte": "MAELIA", "reference": "Référentiel", "saisie": "Valeur saisie"}
# Choix automatique de la source, par ordre de préférence (voir Références > Méthode)
ORDRE_AUTO = {"besoin_mm": ("sgpe", "carte", "reference"), "rdt": ("carte", "reference")}


def _extraction_cartes(ref, culture, info, commune, lonlat, agro):
    """Valeurs des cartes MAELIA à la commune (mises en cache), ou None."""
    geom = commune.get("contour") if commune else None
    if lonlat is None and geom is None:
        return None
    especes = config.ESPECES_CULTIVEES
    cle = (culture, (commune or {}).get("code"), lonlat, tuple(info["fichiers"].values()),
           tuple(os.path.getmtime(f) for f in info["fichiers"].values() if f), ref.date_modification,
           os.path.getmtime(especes) if os.path.exists(especes) else 0)
    extr = _cache_extraction.get(cle)
    if extr is None:
        try:
            extr = cartes.extraire(ref, culture, info, geom, lonlat, especes)
        except Exception as exc:
            agro["notes"].append(f"Lecture des cartes MAELIA impossible ({exc}).")
            return None
        _cache_extraction[cle] = extr
        while len(_cache_extraction) > 500:
            _cache_extraction.popitem(last=False)
    return extr


def _sol_commune(ref, culture, e, surcharges, commune, lonlat):
    """Réserve utile et profondeur de sol : saisie, sinon carte, sinon référentiel."""
    geom = commune.get("contour") if commune else None
    code = (commune or {}).get("code", "")
    lire = config.LECTURE_CARTES and (lonlat or geom)
    vide = {"valeur": None}
    ru_carte = (sol.valeur_commune(sol.fichier_ru(config.SOL_RU, config.SOL_RU_ORIGINE), geom, lonlat, code)
                if lire else vide)
    if (ru_carte.get("valeur") or 0) < 1:  # mailles d'eau ou urbaines (RU nulle) : pas de donnée de sol
        ru_carte = vide
    prof_carte = sol.valeur_commune(config.SOL_PROFONDEUR, geom, lonlat, code) if lire else vide
    prm = climat.parametres_bilan(ref, culture, surcharges)
    ru_saisie, prof_saisie = _nombre_positif(e.get("ru_mm")), _nombre_positif(e.get("profondeur_sol_m"))
    ru_defaut = ru_carte["valeur"] if ru_carte.get("valeur") is not None else prm["ru_defaut"]
    prof_defaut = min(prof_carte["valeur"], 2.0) if prof_carte.get("valeur") is not None else prm["profondeur_sol"]
    return {"ru": ru_saisie or ru_defaut, "ru_defaut": ru_defaut,
            "origine": "saisie" if ru_saisie else ("carte" if ru_carte.get("valeur") is not None else "referentiel"),
            "carte": ru_carte, "profondeur": prof_saisie or prof_defaut, "profondeur_defaut": prof_defaut,
            "carte_profondeur": prof_carte}


def _valeurs_agro(ref, e, commune):
    """Rendements et besoin en eau de la parcelle.

    Choix automatique de la source (méthode « auto », par défaut) :
      besoin en eau : SGPE, sinon MAELIA, sinon référentiel ;
      rendements    : MAELIA, sinon référentiel ; SGPE (Ky) sur demande, option exploratoire.
    Une méthode explicite (methode_besoin, methode_rendement) passe en tête de cet ordre.
    Les valeurs de toutes les méthodes disponibles sont renvoyées dans « alternatives » (bouton
    d'information du volet Simulation). En saisie libre (volet Cas personnel), un rendement ou un
    besoin saisi par l'utilisateur prime ; la valeur calculée reste la valeur par défaut."""
    culture = e["culture"]
    surcharges = e.get("surcharges") or {}
    horizon = e.get("horizon") if e.get("horizon") in climat.HORIZONS else config.HORIZON_CLIMAT
    cat = cartes.catalogue(ref, config.DOSSIER_CARTES)
    info, note_periode = _info_periode(cat.get(culture), horizon)
    carte_dispo = bool(config.LECTURE_CARTES and info and info["complet"] and cartes.disponible())
    methode = e.get("methode_besoin") if e.get("methode_besoin") in METHODES_SOURCE else "auto"
    methode_rdt = e.get("methode_rendement")
    if methode_rdt not in METHODES_SOURCE:
        methode_rdt = "reference" if e.get("sans_carte") else "auto"
    lonlat = tuple(commune["centre"]) if commune and commune.get("centre") else None
    sgpe_dispo = climat.kc_mensuels(ref, culture, surcharges) is not None
    agro = {"origine": "referentiel", "carte_disponible": carte_dispo, "notes": [], "alertes": [], "infobulles": {},
            "brut": {}, "methode_besoin": "reference", "horizon": horizon, "defauts": {}, "alternatives": {},
            "sources": {},
            "methodes_besoin": {"carte": carte_dispo, "sgpe": sgpe_dispo, "reference": True},
            "methodes_rendement": {"carte": carte_dispo, "reference": True,
                                   "sgpe": sgpe_dispo and ref.param("Cultures", culture, "ky") is not None}}
    extr = _extraction_cartes(ref, culture, info, commune, lonlat, agro) if carte_dispo else None
    agro["sol"] = _sol_commune(ref, culture, e, surcharges, commune, lonlat)
    sg = None
    if sgpe_dispo:
        sg = climat.besoin_sgpe(ref, culture, lonlat, config.CLIMAT, horizon, surcharges, agro["sol"]["ru"],
                                agro["sol"]["profondeur"])
        if sg["valeur"] is None:
            if methode == "sgpe" or methode_rdt == "sgpe":
                agro["notes"].append(sg["note"])
            sg = None
        else:
            agro["sgpe"] = sg["detail"]

    # --- Valeur de chaque méthode, avec son info-bulle
    ref_carte, ref_aqyield = ref.reference("MODELE_CARTES"), ref.reference("AQYIELD_2015")
    citation_cartes = ("MAELIA " + (ref_carte.citation if ref_carte else "")
                       + (", modèle de culture AqYield " + ref_aqyield.citation if ref_aqyield else "")).strip()
    corresp = {"rdt_irrigue": ("rdt_irrigue", "rdt_irrigue"), "rdt_pluvial": ("rdt_pluvial", "rdt_pluvial"),
               "besoin_mm": ("besoin_irrigation", "besoin")}
    candidats = {}
    for champ, (code, cle_carte) in corresp.items():
        p = ref.param("Cultures", culture, code)
        c = {"reference": (ref.valeur("Cultures", culture, code), ref.infobulle(p) if p else "Référentiel")}
        if extr is not None and extr.get(cle_carte) is not None:
            b = extr["brut"][cle_carte]
            if b["unite_source"] == cartes.POURCENT:
                pot = extr.get("potentiel") or {}
                conversion = (f"{b['valeur']:.1f} % du rendement potentiel × {pot.get('valeur', 0):.0f} q/ha "
                              f"({pot.get('source', '')})")
            else:
                conversion = "unité source " + b["unite_source"] + (" (unité déduite)" if b["unite_deduite"] else "")
            c["carte"] = (extr[cle_carte], f"{citation_cartes} · {info['scenario'] or 'carte'} — {b['methode']} "
                                           f"({b['n_mailles']} maille(s)) ; fichier {b['fichier']} ; {conversion}")
            agro["brut"][champ] = b
        if sg is not None:
            dt = sg["detail"]
            if champ == "besoin_mm":
                r_crw, r_drias = ref.reference("CROPWAT_1992"), ref.reference("DRIAS_2020")
                lib_ru = {"saisie": "saisie", "carte": f"carte des sols, {agro['sol']['carte'].get('n', 0)} maille(s) "
                          "de 1 km", "referentiel": "valeur par défaut"}[agro["sol"]["origine"]]
                c["sgpe"] = (sg["valeur"], (
                    f"Bilan hydrique journalier du sol type CROPWAT {r_crw.citation if r_crw else ''} — réserve utile "
                    f"{dt['ru']:.0f} mm ({lib_ru}) sur {dt['profondeur_sol']:.1f} m de sol, enracinement jusqu'à "
                    f"{dt['zr_max']:.2f} m, p = {dt['parametres']['p_fao']:.2f}, pluie efficace USDA S.C.S. ; "
                    f"{dt['n_apports']} apport(s) de {dt['dose_moyenne']:.0f} mm en moyenne · ETP et P "
                    f"{r_drias.citation if r_drias else '(DRIAS)'}, RCP4.5, {dt['libelle_horizon']}, point de grille "
                    f"{dt['point']} à {dt['distance_km']:.1f} km du centre de la commune"))
            elif dt.get("rendement_relatif_sec") is not None:
                if champ == "rdt_irrigue":
                    c["sgpe"] = (c["reference"][0], "Rendement sans stress hydrique (Ym) = rendement irrigué du "
                                                    "référentiel " + c["reference"][1])
                else:
                    c["sgpe"] = (None, dt)  # calculé après le choix du rendement irrigué
        candidats[champ] = c

    # --- Choix de la source, saisie de l'utilisateur, alternatives
    for champ, (code, _) in corresp.items():
        c = candidats[champ]
        if champ == "rdt_pluvial" and "sgpe" in c:
            dt, ym = c["sgpe"][1], agro.get("rdt_irrigue") or 0.0
            r_fao33 = ref.reference("FAO_33")
            c["sgpe"] = (ym * dt["rendement_relatif_sec"],
                         f"Ym × (1 − Ky × (1 − ETa/ETc)) = {ym:.1f} × (1 − {dt['ky']:g} × (1 − "
                         f"{dt['satisfaction_sec']:.2f})) — Ky {r_fao33.citation if r_fao33 else '(FAO-33)'} ; ETa/ETc "
                         "du bilan hydrique SGPE sans irrigation. Méthode exploratoire, non calée sur des rendements "
                         "observés.")
        choisie = methode if champ == "besoin_mm" else methode_rdt
        ordre = ORDRE_AUTO["besoin_mm" if champ == "besoin_mm" else "rdt"]
        if choisie != "auto":
            ordre = (choisie,) + tuple(m for m in ordre if m != choisie)
            if choisie not in c:
                agro["notes"].append(f"{LIBELLES_SOURCE[choisie]} indisponible pour « {culture} » "
                                     f"({'besoin en eau' if champ == 'besoin_mm' else 'rendements'}) : "
                                     f"{LIBELLES_SOURCE[next(m for m in ordre if m in c)]} utilisé.")
        source = next((m for m in ordre if m in c and c[m][0] is not None), "reference")
        v, bulle = c[source]
        agro["defauts"][champ] = v
        p = ref.param("Cultures", culture, code)
        saisie = (ref.valeur("Cultures", culture, code, surcharges)
                  if surcharges.get(CLE_LIBRE) and p is not None and p.cle in surcharges else None)
        if saisie is not None:
            bulle = f"Valeur saisie (valeur calculée {LIBELLES_SOURCE[source]} : {v:.0f})"
            source, v = "saisie", saisie
        agro[champ] = v
        agro["infobulles"][champ] = bulle
        agro["sources"][champ] = source
        agro["alternatives"][champ] = [{"code": m, "methode": LIBELLES_SOURCE[m], "valeur": c[m][0],
                                        "retenue": m == source} for m in METHODES_SOURCE
                                       if m in c and c[m][0] is not None
                                       and not (champ == "rdt_irrigue" and m == "sgpe" and m != source)]
        if champ == "besoin_mm":
            agro["methode_besoin"] = source
        elif source != "reference":
            agro["origine"] = source if agro["origine"] in ("referentiel", source) else agro["origine"]
    if note_periode and "carte" in agro["sources"].values():
        agro["notes"].append(note_periode)
    if extr is not None and "carte" in agro["sources"].values():
        agro["notes"] += extr.get("notes", [])

    # --- Vigilance : besoin hors de la plage plausible
    seuil = ref.valeur("Cultures", "Général", "besoin_plausible_max", surcharges, 450.0)
    if agro["besoin_mm"] is not None and agro["besoin_mm"] > seuil:
        autres = " · ".join(f"{a['methode']} {a['valeur']:.0f} mm" for a in agro["alternatives"]["besoin_mm"]
                            if not a["retenue"])
        agro["alertes"].append(f"Besoin en eau élevé ({agro['besoin_mm']:.0f} mm, au-delà de {seuil:.0f} mm) : valeur à "
                               "vérifier" + (f" (autres méthodes : {autres})." if autres else "."))
    return agro


def _preparer(ref, corps):
    """Entrées, surcharges et commune d'une requête de simulation, validées et complétées."""
    e = dict(corps.get("entrees") or {})
    surcharges = dict(corps.get("surcharges") or {})
    commune = corps.get("commune") or None
    surcharges.pop(CLE_LIBRE, None)
    if corps.get("libre"):
        surcharges[CLE_LIBRE] = True
    if e.get("culture") not in ref.cultures:
        e["culture"] = ref.cultures[0]
    if e.get("equipement") not in ref.equipements:
        e["equipement"] = ref.equipements[0]
    if e.get("source") not in ref.sources:
        e["source"] = ref.sources[0]
    if not e.get("agence") and commune and commune.get("departement"):
        e["agence"] = ref.agence_du_departement(commune["departement"]) or ""
    # Un seul jeu de prix proposé : le prix de marché du référentiel. Le prix de vente saisi dans
    # le formulaire est traité comme une surcharge du référentiel.
    e["source_prix"] = "referentiel"
    prix = e.pop("prix_vente", None)
    if prix not in (None, ""):
        try:
            surcharges[f"Cultures|{e['culture']}|{code_prix(e['source_prix'])}"] = float(prix)
        except (TypeError, ValueError):
            pass
    e["surcharges"] = surcharges
    return e, surcharges, commune


def _simulation(ref, corps):
    e, surcharges, commune = _preparer(ref, corps)
    agro = _valeurs_agro(ref, e, commune)
    res = simuler(ref, e, surcharges, agro)
    res["agro"].update({"origine": agro["origine"], "carte_disponible": agro["carte_disponible"],
                        "notes": agro["notes"], "infobulles": agro["infobulles"], "brut": agro["brut"],
                        "methode_besoin": agro["methode_besoin"], "methodes_besoin": agro["methodes_besoin"],
                        "methodes_rendement": agro["methodes_rendement"],
                        "sgpe": agro.get("sgpe"), "horizon": agro["horizon"], "defauts": agro["defauts"],
                        "sol": agro["sol"], "alternatives": agro["alternatives"], "sources": agro["sources"]})
    res["avertissements"] = [{"niveau": "warning", "texte": t} for t in agro["alertes"]] + res["avertissements"]
    res["entrees"] = {k: v for k, v in e.items() if k != "surcharges"}
    res["referentiel"] = {"date": ref.date_modification, "anomalies": ref.anomalies[:20],
                          "erreur": REF.derniere_erreur}
    return res, e, surcharges, commune


@app.post("/api/simulation")
def api_simulation():
    ref = REF.get()
    res, _, _, _ = _simulation(ref, request.get_json(force=True, silent=True) or {})
    return jsonify(res)


def _nom_fichier(commune, e, suffixe):
    nom = "-".join(slug(x) for x in ((commune or {}).get("nom") or "parcelle", e["culture"]) if x)
    return f"irrigation-{nom}-{suffixe}"


@app.post("/api/rapport-pdf")
def api_rapport_pdf():
    """Rapport PDF des résultats d'une simulation de parcelle (volet Cas personnel)."""
    ref = REF.get()
    res, e, surcharges, commune = _simulation(ref, request.get_json(force=True, silent=True) or {})
    pdf = rapport.rapport_parcelle(ref, e, res, commune, surcharges, time.localtime(ref.date_modification))
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{_nom_fichier(commune, e, "rapport")}.pdf"'})


@app.get("/api/methodologie-pdf")
def api_methodologie_pdf():
    """Note méthodologique (PDF) : export de docs/methodologie_irrigation.docx (outils/exporter_methodologie.py).

    À défaut de PDF exporté, la méthodologie est générée d'après le référentiel et la validation.
    """
    if os.path.exists(config.METHODOLOGIE_PDF):
        return send_from_directory(os.path.dirname(config.METHODOLOGIE_PDF), os.path.basename(config.METHODOLOGIE_PDF),
                                   mimetype="application/pdf", as_attachment=True,
                                   download_name="methodologie-irrigation.pdf", max_age=0)
    ref = REF.get()
    pdf = methodologie.methodologie_pdf(ref, validation.resultats(config.VALIDATION),
                                        cartes.catalogue(ref, config.DOSSIER_CARTES))
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="methodologie-irrigation-detaillee.pdf"'})


@app.post("/api/variables-excel")
def api_variables_excel():
    """Classeur Excel des variables de la simulation (valeurs du référentiel et valeurs saisies)."""
    ref = REF.get()
    res, e, surcharges, commune = _simulation(ref, request.get_json(force=True, silent=True) or {})
    contenu = export.classeur_variables(ref, e, surcharges, commune, res)
    return Response(contenu, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition":
                             f'attachment; filename="{_nom_fichier(commune, e, "variables")}.xlsx"'})


@app.post("/api/variables-import")
def api_variables_import():
    """Relit un classeur produit par /api/variables-excel : entrées, commune et surcharges."""
    ref = REF.get()
    fichier = request.files.get("fichier")
    if fichier is None:
        return jsonify({"erreur": "Aucun fichier reçu."}), 400
    try:
        return jsonify(export.lire_classeur_variables(fichier.stream, ref))
    except Exception as exc:  # classeur d'un autre format, fichier corrompu…
        return jsonify({"erreur": f"Classeur illisible : {exc}"}), 400


@app.get("/api/departement/<code>")
def api_departement(code):
    ref = REF.get()
    d = ref.departements.get(code.upper().zfill(2))
    return jsonify(d or {})


@app.get("/api/carte-variable/<culture>/<variable>")
def api_carte_variable(culture, variable):
    """Image d'une variable cartographiée (rendement irrigué, rendement pluvial ou besoin en
    eau), pour les couches facultatives de la carte."""
    ref = REF.get()
    cat = cartes.catalogue(ref, config.DOSSIER_CARTES)
    info = cat.get(culture)
    if not info or not (config.LECTURE_CARTES and cartes.disponible()):
        return jsonify({"disponible": False})
    try:
        donnee = cartes.carte_variable(ref, culture, info, variable, config.ESPECES_CULTIVEES)
    except Exception as exc:
        return jsonify({"disponible": False, "erreur": str(exc)})
    if donnee is None:
        return jsonify({"disponible": False})
    donnee["disponible"] = True
    donnee["scenario"] = info.get("scenario", "")
    return jsonify(donnee)


@app.errorhandler(404)
def introuvable(_):
    if request.path.startswith("/api/") or request.path.startswith("/dsfr/"):
        return jsonify({"erreur": "Ressource introuvable"}), 404
    return render_template("404.html", page=""), 404


if __name__ == "__main__":
    if not DSFR_LOCAL:
        print("DSFR local introuvable : chargement depuis le CDN. Copiez le contenu du dossier « dist » du DSFR "
              f"dans {os.path.join(config.RACINE, 'static', 'dsfr')} ou définissez IRRIG_DSFR.")
    print(f"Application disponible sur http://{config.HOTE}:{config.PORT}")
    app.run(host=config.HOTE, port=config.PORT, debug=False)
