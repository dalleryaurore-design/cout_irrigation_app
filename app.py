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

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, url_for

import config
from moteur import cartes, climat
from moteur.calcul import (POSTES, COULEUR_BILAN, COULEUR_GAIN, code_prix, simuler, taux_subvention_acces,
                           type_source, valeurs_derivees)
from moteur.referentiel import GestionnaireReferentiel, slug

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
        if d and os.path.exists(os.path.join(d, "dsfr.min.css")):
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
    return redirect(url_for("projet"))


@app.route("/projet")
def projet():
    ref = REF.get()
    cat = cartes.catalogue(ref, config.DOSSIER_CARTES)
    # Sans paramètre, la simulation s'ouvre sur l'exemple 1 (maïs) ; ?exemple=0 donne un formulaire vierge.
    exemple = None
    n = request.args.get("exemple", default=1, type=int)
    if n:
        exemple = next((x for x in ref.exemples if x["id"] == n), None)
    derives = valeurs_derivees(ref, {}, {"equipement": ref.equipements[0] if ref.equipements else ""})
    prix_cultures = {"referentiel": {c: ref.valeur("Cultures", c, "prix_vente") for c in ref.cultures},
                     "masaa": {c: ref.valeur("Cultures", c, "prix_masaa") for c in ref.cultures}}
    surface_unitaire = {eq: ref.valeur("Equipement", eq, "surface_unitaire")
                        for eq in ref.equipements if ref.param("Equipement", eq, "surface_unitaire")}
    duree_vie_equipements = {eq: ref.valeur("Equipement", eq, "duree_vie") for eq in ref.equipements}
    duree_vie_sources = {s: ref.valeur("Acces_ressource", s, "duree_vie") for s in ref.sources}
    # Taux de subvention par défaut (en %) pré-remplis dans l'onglet Simulation
    subventions = {"equipement": round(100 * ref.valeur("Equipement", "Général", "taux_subvention", None, 0.0), 1),
                   "acces": {s: round(100 * taux_subvention_acces(ref, {}, s), 1) for s in ref.sources}}
    # rasterio n'est sollicité que si des cartes complètes sont effectivement présentes.
    cartes_presentes = any(i["complet"] for i in cat.values())
    lecture_cartes = bool(config.LECTURE_CARTES and cartes_presentes and cartes.disponible())
    cartes_completes = {c: bool(cat.get(c) and cat[c]["complet"]) for c in ref.cultures}
    cartes_variables = {c: {v: bool(cat[c]["fichiers"].get(v)) for v in cartes.VARIABLES}
                        for c in ref.cultures if c in cat}
    return render_template("projet.html", page="projet", catalogue=cat, exemple=exemple, derives=derives,
                           prix_cultures=prix_cultures, surface_unitaire=surface_unitaire,
                           duree_vie_equipements=duree_vie_equipements, duree_vie_sources=duree_vie_sources,
                           subventions=subventions,
                           cartes_completes=cartes_completes, cartes_variables=cartes_variables,
                           postes=POSTES, couleur_gain=COULEUR_GAIN, couleur_bilan=COULEUR_BILAN,
                           cartes_presentes=cartes_presentes, lecture_cartes=lecture_cartes,
                           fond_carte=config.FOND_CARTE,
                           erreur_rasterio=cartes.erreur(), type_source=type_source)


@app.route("/exemples")
def exemples():
    return render_template("exemples.html", page="exemples")


@app.route("/references")
def references():
    ref = REF.get()
    usage = {}
    for p in ref.params.values():
        usage.setdefault(p.ref_id, 0)
        usage[p.ref_id] += 1
    return render_template("references.html", page="references", usage=usage,
                           postes=POSTES)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
METHODES_BESOIN = ("carte", "sgpe", "reference")


def _valeurs_agro(ref, e, commune):
    """Rendements : cartes si disponibles et demandées, sinon référentiel.
    Besoin en eau : méthode choisie (carte, SGPE ou référence), repli sur le référentiel."""
    culture = e["culture"]
    cat = cartes.catalogue(ref, config.DOSSIER_CARTES)
    info = cat.get(culture)
    carte_dispo = bool(config.LECTURE_CARTES and info and info["complet"] and cartes.disponible())
    methode = e.get("methode_besoin") if e.get("methode_besoin") in METHODES_BESOIN else "sgpe"
    rdt_carte = carte_dispo and not e.get("sans_carte", False)
    utiliser = rdt_carte or (carte_dispo and methode == "carte")
    lonlat = tuple(commune["centre"]) if commune and commune.get("centre") else None
    agro = {"origine": "referentiel", "carte_disponible": carte_dispo, "notes": [], "infobulles": {}, "brut": {},
            "methode_besoin": "reference",
            "methodes_besoin": {"carte": carte_dispo, "sgpe": climat.kc_mensuels(ref, culture) is not None,
                                "reference": True}}
    extr = None
    if utiliser:
        geom = commune.get("contour") if commune else None
        if lonlat is None and geom is None:
            agro["notes"].append("Sélectionnez une commune pour lire les cartes : valeurs du référentiel utilisées.")
        else:
            especes = config.ESPECES_CULTIVEES
            cle = (culture, (commune or {}).get("code"), lonlat,
                   tuple(os.path.getmtime(f) for f in info["fichiers"].values() if f), ref.date_modification,
                   os.path.getmtime(especes) if os.path.exists(especes) else 0)
            extr = _cache_extraction.get(cle)
            if extr is None:
                try:
                    extr = cartes.extraire(ref, culture, info, geom, lonlat, especes)
                except Exception as exc:
                    agro["notes"].append(f"Lecture des cartes impossible ({exc}) : valeurs du référentiel utilisées.")
                    extr = None
                if extr is not None:
                    _cache_extraction[cle] = extr
                    while len(_cache_extraction) > 500:
                        _cache_extraction.popitem(last=False)
    corresp = {"rdt_irrigue": "rdt_irrigue", "rdt_pluvial": "rdt_pluvial", "besoin_mm": "besoin_irrigation"}
    cle_carte = {"rdt_irrigue": "rdt_irrigue", "rdt_pluvial": "rdt_pluvial", "besoin_mm": "besoin"}
    ref_carte, ref_aqyield = ref.reference("MODELE_CARTES"), ref.reference("AQYIELD_2015")
    citation_cartes = ("MAELIA " + (ref_carte.citation if ref_carte else "")
                       + (", modèle de culture AqYield " + ref_aqyield.citation if ref_aqyield else "")).strip()
    for champ, code in corresp.items():
        p = ref.param("Cultures", culture, code)
        v_ref = ref.valeur("Cultures", culture, code, e.get("surcharges"))
        v = None
        depuis_carte = (methode == "carte") if champ == "besoin_mm" else rdt_carte
        if champ == "besoin_mm" and methode == "sgpe":
            sg = climat.besoin_sgpe(ref, culture, lonlat, config.CLIMAT, config.HORIZON_CLIMAT)
            if sg["valeur"] is not None:
                v = sg["valeur"]
                dt = sg["detail"]
                r_fao, r_drias = ref.reference("FAO_56"), ref.reference("DRIAS_2020")
                agro["infobulles"][champ] = (
                    f"Méthode SGPE : Σ max(0, ETP × Kc − P) sur les mois où Kc > 0 · Kc "
                    f"{r_fao.citation if r_fao else '(FAO)'} ; ETP et P {r_drias.citation if r_drias else '(DRIAS)'}, "
                    f"RCP4.5, {dt['libelle_horizon']}, point de grille {dt['point']} à {dt['distance_km']:.1f} km "
                    "du centre de la commune")
                agro["sgpe"] = dt
                agro["methode_besoin"] = "sgpe"
            else:
                agro["notes"].append(sg["note"] + " Besoin en eau : valeur du référentiel utilisée.")
        elif champ == "besoin_mm" and methode == "carte" and not carte_dispo:
            agro["notes"].append("Pas de carte de besoin en eau pour cette culture : valeur du référentiel utilisée.")
        if depuis_carte and extr is not None and extr.get(cle_carte[champ]) is not None:
            v = extr[cle_carte[champ]]
            b = extr["brut"][cle_carte[champ]]
            if b["unite_source"] == cartes.POURCENT:
                pot = extr.get("potentiel") or {}
                conversion = (f"{b['valeur']:.1f} % du rendement potentiel × {pot.get('valeur', 0):.0f} q/ha "
                              f"({pot.get('source', '')})")
            else:
                conversion = "unité source " + b["unite_source"] + (" (unité déduite)" if b["unite_deduite"] else "")
            agro["infobulles"][champ] = (f"{citation_cartes} · "
                                         f"{info['scenario'] or 'carte'} — {b['methode']} ({b['n_mailles']} maille(s)) ; "
                                         f"fichier {b['fichier']} ; {conversion}")
            agro["brut"][champ] = b
            if champ == "besoin_mm":
                agro["methode_besoin"] = "carte"
            else:
                agro["origine"] = "carte"
        elif depuis_carte and extr is not None:
            agro["notes"].append(f"Pas de valeur de carte pour « {p.libelle if p else champ} » sur cette commune : "
                                 "valeur du référentiel utilisée.")
        if v is None:
            v = v_ref
            agro["infobulles"][champ] = ref.infobulle(p) if p else "Référentiel"
        agro[champ] = v
    if extr is not None:
        agro["notes"] += extr.get("notes", [])
    return agro


@app.post("/api/simulation")
def api_simulation():
    ref = REF.get()
    corps = request.get_json(force=True, silent=True) or {}
    e = corps.get("entrees", {})
    surcharges = corps.get("surcharges", {}) or {}
    commune = corps.get("commune") or None
    if e.get("culture") not in ref.cultures:
        e["culture"] = ref.cultures[0]
    if e.get("equipement") not in ref.equipements:
        e["equipement"] = ref.equipements[0]
    if e.get("source") not in ref.sources:
        e["source"] = ref.sources[0]
    if not e.get("agence") and commune and commune.get("departement"):
        e["agence"] = ref.agence_du_departement(commune["departement"]) or ""
    # Le prix de vente saisi dans le formulaire est traité comme une surcharge du référentiel.
    if e.get("source_prix") not in ("referentiel", "masaa"):
        e["source_prix"] = "referentiel"
    prix = e.pop("prix_vente", None)
    if prix not in (None, ""):
        try:
            surcharges[f"Cultures|{e['culture']}|{code_prix(e['source_prix'])}"] = float(prix)
        except (TypeError, ValueError):
            pass
    e["surcharges"] = surcharges
    agro = _valeurs_agro(ref, e, commune)
    res = simuler(ref, e, surcharges, agro)
    res["agro"].update({"origine": agro["origine"], "carte_disponible": agro["carte_disponible"],
                        "notes": agro["notes"], "infobulles": agro["infobulles"], "brut": agro["brut"],
                        "methode_besoin": agro["methode_besoin"], "methodes_besoin": agro["methodes_besoin"],
                        "sgpe": agro.get("sgpe")})
    res["entrees"] = {k: v for k, v in e.items() if k != "surcharges"}
    res["referentiel"] = {"date": ref.date_modification, "anomalies": ref.anomalies[:20],
                          "erreur": REF.derniere_erreur}
    return jsonify(res)


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
