# -*- coding: utf-8 -*-
"""
Chaîne de calcul du coût et de la rentabilité de l'irrigation
=============================================================
Module sans dépendance d'interface : il reçoit le référentiel, les choix de
l'utilisateur, ses surcharges de paramètres et les valeurs agronomiques
(issues des cartes ou du référentiel), et renvoie un dictionnaire de résultats.

    besoin (mm) ─► volume appliqué = besoin × 10 × surface
                ─► volume prélevé  = volume appliqué ÷ efficience du matériel
    énergie      = (volume prélevé + volume de remplissage pompé d'une retenue) × prix forfaitaire (CGEDD, 2020)
                   remplissage pompé = volume prélevé × part du remplissage assurée par pompage
                   (0 pour une retenue collinaire, alimentée par ruissellement et précipitations)
                   (nul si l'eau est livrée sous pression : compris dans la part volumétrique de l'accès)
    redevance    = volume prélevé × taux de l'agence (catégorie, origine de l'eau)
                   (non ajoutée pour l'ASA : incluse dans le tarif du gestionnaire)
    équipement   = CAPEX net de subvention × facteur d'annualisation + maintenance
    main-d'œuvre = coût main-d'œuvre (€/ha/an, propre à l'équipement) × surface
    accès        = CAPEX net de subvention × facteur d'annualisation
                   + part fixe + part volumétrique
    gain         = (rendement irrigué − rendement pluvial) × 0,1 × prix × surface
    bilan        = gain − coût total
"""

from __future__ import annotations

from math import ceil
from typing import Any, Dict, Optional

from .referentiel import Referentiel, slug

# Couleurs de la cascade (ordre d'affichage)
POSTES = [
    ("energie", "Énergie", "#6A3D9A"),
    ("redevance", "Redevance agence de l'eau", "#1F5FAD"),
    ("equipement", "Équipement (CAPEX + maintenance)", "#E4794A"),
    ("main_oeuvre", "Main-d'œuvre", "#D6589A"),
    ("acces", "Accès à la ressource (stockage, forage, ASA…)", "#E9C229"),
]
COULEUR_GAIN = "#18753C"
COULEUR_BILAN = "#161616"


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def facteur_annualisation(taux: float, duree: float) -> float:
    """Facteur d'annualisation (ou de recouvrement du capital).

    a = i(1+i)^n / ((1+i)^n − 1) ; si i = 0, a = 1/n (amortissement linéaire).
    """
    if not duree or duree <= 0:
        return 0.0
    if not taux:
        return 1.0 / duree
    k = (1 + taux) ** duree
    return taux * k / (k - 1)


def type_source(nom: str) -> str:
    s = slug(nom)
    if "forage" in s:
        return "forage"
    if "cours" in s:
        return "cours_eau"
    if "collinaire" in s:
        return "retenue_collinaire"
    if "retenue" in s:
        return "retenue_pompage"
    if s == "asa" or s.startswith("asa") or "reseau" in s or "canal" in s:
        return "asa"  # réseau collectif sous pression (ASA ou autre gestionnaire)
    return "autre"


def code_prix(source_prix: Optional[str]) -> str:
    """Code du paramètre de prix : prix de marché (référentiel) ou barème MASAA de l'assurance récolte."""
    return "prix_masaa" if source_prix == "masaa" else "prix_vente"


def est_retenue(nom: str) -> bool:
    return type_source(nom).startswith("retenue")


def est_collective(nom: str, type_retenue: str) -> bool:
    t = type_source(nom)
    return t == "asa" or (t.startswith("retenue") and type_retenue == "collective")


def _f(x, defaut=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return defaut


def cout_maintenance_ha(ref: Referentiel, surcharges: Dict[str, Any], equip: str) -> float:
    """Coût de maintenance annuel d'un équipement, ramené à l'hectare (€/ha/an).

    Le paramètre « maintenance_pct » est exprimé soit en % du CAPEX/an (à multiplier par le
    CAPEX à l'hectare), soit directement en €/ha/an selon l'équipement (voir unité en colonne E
    du référentiel) : les deux ne doivent pas être mélangés dans le même calcul.
    """
    p = ref.param("Equipement", equip, "maintenance_pct")
    taux = ref.valeur("Equipement", equip, "maintenance_pct", surcharges, 0.0)
    if p is not None and p.est_pourcentage:
        return ref.valeur("Equipement", equip, "capex_ha", surcharges, 0.0) * taux
    return taux


# ---------------------------------------------------------------------------
# Calcul principal
# ---------------------------------------------------------------------------
def simuler(ref: Referentiel, e: Dict[str, Any], surcharges: Dict[str, Any], agro: Dict[str, Any]) -> Dict[str, Any]:
    """Exécute la chaîne de calcul.

    e : choix de l'utilisateur (culture, surface, source, equipement, agence, zre,
        type_retenue, nb_adherents, capacite, deja_amorti, deja_amorti_equipement, nb_unites).
    agro : {rdt_irrigue, rdt_pluvial, besoin_mm, origine, ...}.
    """
    V = lambda f, o, c, d=0.0: ref.valeur(f, o, c, surcharges, d)  # noqa: E731
    avert = []

    culture = e["culture"]
    surface = max(_f(e.get("surface"), 0.0), 0.0)
    equip = e["equipement"]
    source = e["source"]
    tsrc = type_source(source)
    type_ret = (e.get("type_retenue") or "individuelle").lower()
    collectif = est_collective(source, type_ret)
    nb_adh = max(int(_f(e.get("nb_adherents"), 1)), 1) if (tsrc.startswith("retenue") and type_ret == "collective") else 1
    deja_amorti = bool(e.get("deja_amorti"))
    deja_amorti_equip = bool(e.get("deja_amorti_equipement"))

    # ============================ BILAN AGRONOMIQUE ========================
    rdt_irr = _f(agro.get("rdt_irrigue"))
    rdt_plu = _f(agro.get("rdt_pluvial"))
    besoin = max(_f(agro.get("besoin_mm")), 0.0)
    prix = V("Cultures", culture, code_prix(e.get("source_prix")))
    if not prix:  # culture absente du barème MASAA : repli sur le prix de marché
        prix = V("Cultures", culture, "prix_vente")
    efficience = max(V("Equipement", equip, "efficience", 1.0), 0.05)

    dose = besoin * 10.0
    v_app = dose * surface
    v_prel = v_app / efficience
    delta_rdt = rdt_irr - rdt_plu

    # ============================ ÉQUIPEMENT ==============================
    capex_u = V("Equipement", equip, "capex_unitaire", 0.0)
    surf_u = V("Equipement", equip, "surface_unitaire", 0.0)
    nb_unites = nb_auto = None
    if capex_u > 0 and surf_u > 0:
        nb_auto = max(1, ceil(surface / surf_u - 1e-9)) if surface > 0 else 1
        nb_unites = int(_f(e.get("nb_unites"), 0)) or nb_auto
        capex_equip = nb_unites * capex_u
        if surface > nb_unites * surf_u * 1.0001:
            avert.append({"niveau": "warning", "texte":
                          f"{nb_unites} unité(s) de {equip.lower()} pour {surface:g} ha : la surface de référence "
                          f"est de {surf_u:g} ha par unité. Le dimensionnement est à vérifier (tours d'eau, débit)."})
    else:
        capex_equip = V("Equipement", equip, "capex_ha") * surface

    i_eq = V("Equipement", "Général", "taux_actualisation", 0.03)
    n_eq = V("Equipement", equip, "duree_vie", 15)
    a_eq = facteur_annualisation(i_eq, n_eq)
    subv_eq = max(min(V("Equipement", "Général", "taux_subvention", 0.0), 1.0), 0.0)
    subvention_equip = capex_equip * subv_eq
    capex_equip_net = capex_equip - subvention_equip
    annuite_equip = capex_equip_net * a_eq
    maintenance = cout_maintenance_ha(ref, surcharges, equip) * surface
    # Matériel déjà amorti : ni l'annuité ni la maintenance ne sont comptées dans le bilan et
    # la décomposition du coût (l'objectif est d'isoler le coût de l'eau seule, sans équipement).
    cout_equipement = 0.0 if deja_amorti_equip else (annuite_equip + maintenance)

    # ============================ MAIN-D'ŒUVRE ============================
    mo_eur_ha = V("Equipement", equip, "mo_eur_ha", 0.0)
    cout_mo = mo_eur_ha * surface

    # ============================ ACCÈS À LA RESSOURCE ====================
    remplissage = max(min(V("Acces_ressource", "Général", "taux_remplissage", 0.85), 1.0), 0.01)
    subv_defaut = V("Acces_ressource", "Général", "taux_subvention", 0.7)
    subv = max(min(V("Acces_ressource", source, "taux_subvention", subv_defaut), 1.0), 0.0)
    i_acc = V("Acces_ressource", "Général", "taux_actualisation", 0.03)
    n_ouvrage = V("Acces_ressource", source, "duree_vie", 30)
    n_reseau = V("Acces_ressource", "Général", "duree_vie_reseau", 30)

    detail_capex = []
    capacite = capacite_auto = volume_dispo = None
    v_rempl = 0.0
    capex_pompe = 0.0  # station de pompage amortie sur sa propre durée de vie (forage)
    n_pompe = V("Acces_ressource", source, "duree_vie_pompe", n_ouvrage)
    if tsrc == "forage":
        prof = V("Acces_ressource", source, "profondeur", 50)
        capex_pompe = V("Acces_ressource", source, "pompe_abri")
        postes_f = [
            ("Dossier, étude et abri", V("Acces_ressource", source, "dossier_etude")),
            ("Raccordement électrique", V("Acces_ressource", source, "raccordement_electrique")),
            (f"Forage ({prof:g} m)", V("Acces_ressource", source, "foration_ml") * prof),
            ("Station de pompage", capex_pompe),
        ]
        detail_capex += postes_f
        capex_ouvrage = sum(x for _, x in postes_f)
    elif tsrc == "cours_eau":
        capex_ouvrage = V("Acces_ressource", source, "capex_station")
        detail_capex.append(("Station de pompage", capex_ouvrage))
    elif tsrc == "asa":
        capex_ouvrage = V("Acces_ressource", source, "capex_branchement")
        detail_capex.append(("Adhésion et branchement", capex_ouvrage))
    elif tsrc.startswith("retenue"):
        capacite_auto = ceil(v_prel * nb_adh / remplissage / 1000.0) * 1000.0 if v_prel > 0 else 0.0
        cap_saisie = _f(e.get("capacite"), 0.0)
        capacite = cap_saisie if (cap_saisie > 0 and not e.get("capacite_auto", True)) else capacite_auto
        cout_ouvrage_total = capacite * V("Acces_ressource", source, "cout_stockage")
        capex_ouvrage = cout_ouvrage_total / nb_adh
        detail_capex.append((f"Retenue de {capacite:,.0f} m³".replace(",", "\u202f"), cout_ouvrage_total))
        if nb_adh > 1:
            detail_capex.append((f"Quote-part ({nb_adh} adhérents)", capex_ouvrage))
        volume_dispo = capacite * remplissage / nb_adh
        # Remplissage hivernal pompé : seule la part non apportée par le ruissellement et la pluie
        part_pompe = max(min(V("Acces_ressource", source, "part_remplissage_pompe", 0.0), 1.0), 0.0)
        v_rempl = min(v_prel, volume_dispo) * part_pompe
        if volume_dispo + 1e-6 < v_prel:
            avert.append({"niveau": "error", "texte":
                          f"Capacité insuffisante : la retenue mobilise {volume_dispo:,.0f} m³ pour "
                          f"{v_prel:,.0f} m³ nécessaires. Le calcul suppose néanmoins le besoin couvert."
                          .replace(",", "\u202f")})
    else:
        capex_ouvrage = 0.0

    distance = V("Acces_ressource", source, "distance_amenee", 0)
    capex_reseau = distance * V("Acces_ressource", "Général", "cout_tuyau_ml")
    if capex_reseau:
        detail_capex.append((f"Réseau d'amenée ({distance:,.0f} m)".replace(",", "\u202f"), capex_reseau))

    capex_acces_brut = capex_ouvrage + capex_reseau
    subvention = capex_acces_brut * subv
    capex_acces_net = capex_acces_brut - subvention
    a_ouv = facteur_annualisation(i_acc, n_ouvrage)
    a_res = facteur_annualisation(i_acc, n_reseau)
    a_pompe = facteur_annualisation(i_acc, n_pompe)
    if deja_amorti:
        annuite_acces = 0.0
    else:
        annuite_acces = ((capex_ouvrage - capex_pompe) * a_ouv + capex_pompe * a_pompe
                         + capex_reseau * a_res) * (1 - subv)
    part_fixe = V("Acces_ressource", source, "part_fixe", 0.0) * surface
    part_vol = V("Acces_ressource", source, "part_volumetrique", 0.0) * v_prel
    cout_acces = annuite_acces + part_fixe + part_vol

    # ============================ ÉNERGIE =================================
    # Prix forfaitaire, commun à tous les équipements et à toutes les sources (CGEDD, 2020).
    prix_energie_m3 = V("Ressources", "Énergie", "prix_energie_m3", 0.07)
    # L'ASA livre l'eau sous pression : l'énergie est comprise dans sa part volumétrique
    pression_fournie = tsrc == "asa"
    volume_energie = 0.0 if pression_fournie else (v_prel + v_rempl)
    cout_energie = volume_energie * prix_energie_m3

    # ============================ REDEVANCE ===============================
    agence = e.get("agence") or ""
    zre = bool(e.get("zre"))
    origine = "souterraine" if tsrc == "forage" else "superficielle"
    categorie = 2 if zre else 1
    regle_retenue = False
    if zre and tsrc.startswith("retenue") and V("Ressources", agence, "retenue_hors_zre", 0) >= 0.5:
        categorie, regle_retenue = 1, True
    taux_c = V("Ressources", agence, f"cat{categorie}_{origine}", 0.0) if agence else 0.0
    seuil = V("Ressources", agence, f"seuil_cat{categorie}", 7000.0) if agence else 7000.0
    redevance_due = (collectif or v_prel >= seuil) and bool(agence)
    # ASA : la redevance est acquittée par le gestionnaire et répercutée dans son tarif
    redevance_incluse = tsrc == "asa"
    cout_redevance = v_prel * taux_c / 100.0 if (redevance_due and not redevance_incluse) else 0.0
    if not agence:
        avert.append({"niveau": "info", "texte": "Agence de l'eau non déterminée : la redevance n'est pas calculée."})
    elif redevance_incluse:
        avert.append({"niveau": "info", "texte":
                      "Redevance de prélèvement acquittée par le gestionnaire et comprise dans son tarif "
                      "(part fixe et part volumétrique) : elle n'est pas ajoutée une seconde fois."})
    elif not redevance_due:
        avert.append({"niveau": "info", "texte":
                      f"Prélèvement inférieur au seuil d'assujettissement ({seuil:,.0f} m³/an) : redevance non due."
                      .replace(",", "\u202f")})

    # ============================ TOTAUX ==================================
    montants = {"energie": cout_energie, "redevance": cout_redevance, "equipement": cout_equipement,
                "main_oeuvre": cout_mo, "acces": cout_acces}
    total = sum(montants.values())
    postes = [{"cle": k, "libelle": lib, "couleur": col, "montant": montants[k],
               "part": (montants[k] / total if total else 0.0)} for k, lib, col in POSTES]

    gain_ha = delta_rdt * 0.1 * prix
    gain = gain_ha * surface
    bilan = gain - total

    denom_prix = delta_rdt * 0.1 * surface
    prix_min = total / denom_prix if denom_prix > 0 else None
    delta_min = total / (0.1 * prix * surface) if (prix > 0 and surface > 0) else None

    capex_total = (0.0 if deja_amorti_equip else capex_equip) + (0.0 if deja_amorti else capex_acces_brut)
    reste_charge = (0.0 if deja_amorti_equip else capex_equip_net) + (0.0 if deja_amorti else capex_acces_net)

    if delta_rdt <= 0:
        avert.append({"niveau": "warning", "texte": "Le gain de rendement est nul ou négatif : l'irrigation ne peut pas "
                                                   "être rentabilisée par le seul différentiel de rendement."})

    res = {
        "agro": {
            "rdt_irrigue": rdt_irr, "rdt_pluvial": rdt_plu, "delta_rdt": delta_rdt, "besoin_mm": besoin,
            "dose_m3_ha": dose, "volume_applique": v_app, "volume_preleve": v_prel, "efficience": efficience,
        },
        "couts": {"postes": postes, "total": total, "par_ha": total / surface if surface else 0.0,
                  "c_par_m3": total / v_prel * 100.0 if v_prel else 0.0},
        "capex": {"equipement": 0.0 if deja_amorti_equip else capex_equip,
                  "subvention_equipement": 0.0 if deja_amorti_equip else subvention_equip,
                  "equipement_net": 0.0 if deja_amorti_equip else capex_equip_net,
                  "acces_brut": 0.0 if deja_amorti else capex_acces_brut,
                  "subvention": 0.0 if deja_amorti else subvention,
                  "acces_net": 0.0 if deja_amorti else capex_acces_net, "total": capex_total,
                  "reste_a_charge": reste_charge, "deja_amorti": deja_amorti,
                  "deja_amorti_equipement": deja_amorti_equip,
                  "detail_acces": [{"poste": a, "montant": b} for a, b in detail_capex]},
        "gain": {"total": gain, "par_ha": gain_ha, "prix": prix},
        "bilan": {"total": bilan, "par_ha": bilan / surface if surface else 0.0},
        "seuil": {"prix_min": prix_min, "prix": prix, "ecart": (prix - prix_min) if prix_min is not None else None,
                  "delta_min": delta_min, "delta_actuel": delta_rdt},
        "dimensionnement": {"nb_unites": nb_unites, "nb_auto": nb_auto, "capacite": capacite,
                            "capacite_auto": capacite_auto, "volume_disponible": volume_dispo,
                            "nb_adherents": nb_adh, "collectif": collectif},
        "energie": {"prix_m3": prix_energie_m3, "pression_fournie": pression_fournie,
                    "volume_facture": volume_energie, "volume_remplissage": 0.0 if pression_fournie else v_rempl,
                    "cout_m3": cout_energie / v_prel if v_prel else 0.0},
        "redevance": {"agence": agence, "categorie": categorie, "origine": origine, "taux_c_m3": taux_c,
                      "seuil": seuil, "due": redevance_due, "incluse": redevance_incluse,
                      "collectif": collectif, "regle_retenue": regle_retenue},
        "annualisation": {
            "equipement": {"capex": capex_equip, "subvention": subv_eq, "capex_net": capex_equip_net,
                           "taux": i_eq, "duree": n_eq, "facteur": a_eq, "annuite": annuite_equip,
                           "maintenance": maintenance},
            "acces": {"capex_brut": capex_acces_brut, "subvention": subv, "capex_net": capex_acces_net,
                      "capex_ouvrage_net": capex_ouvrage * (1 - subv), "capex_reseau_net": capex_reseau * (1 - subv),
                      "capex_pompe_net": capex_pompe * (1 - subv), "duree_pompe": n_pompe, "facteur_pompe": a_pompe,
                      "taux": i_acc, "duree_ouvrage": n_ouvrage, "duree_reseau": n_reseau, "facteur_ouvrage": a_ouv,
                      "facteur_reseau": a_res, "annuite": annuite_acces,
                      "part_fixe": part_fixe, "part_volumetrique": part_vol},
        },
        "avertissements": avert,
        "couleurs": {"gain": COULEUR_GAIN, "bilan": COULEUR_BILAN},
    }
    res["derives"] = valeurs_derivees(ref, surcharges, e, res)
    return res


# ---------------------------------------------------------------------------
# Valeurs dérivées affichées dans les onglets « en coulisse »
# ---------------------------------------------------------------------------
def valeurs_derivees(ref: Referentiel, surcharges: Dict[str, Any], e: Dict[str, Any],
                     res: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Valeurs calculées à partir des paramètres courants (clé = identifiant HTML de la cellule)."""
    V = lambda f, o, c, d=0.0: ref.valeur(f, o, c, surcharges, d)  # noqa: E731
    d: Dict[str, float] = {}
    i_eq = V("Equipement", "Général", "taux_actualisation", 0.03)
    subv_eq = max(min(V("Equipement", "Général", "taux_subvention", 0.0), 1.0), 0.0)
    for eq in ref.equipements:
        s = slug(eq)
        capex_ha = V("Equipement", eq, "capex_ha")
        a = facteur_annualisation(i_eq, V("Equipement", eq, "duree_vie", 15))
        maintenance_ha = cout_maintenance_ha(ref, surcharges, eq)
        mo_ha = V("Equipement", eq, "mo_eur_ha", 0.0)
        annuite_ha = capex_ha * (1 - subv_eq) * a
        d[f"d-eq-{s}-maint"] = maintenance_ha
        d[f"d-eq-{s}-taux"] = a
        d[f"d-eq-{s}-annuite"] = annuite_ha
        d[f"d-eq-{s}-total"] = annuite_ha + maintenance_ha + mo_ha

    i_acc = V("Acces_ressource", "Général", "taux_actualisation", 0.03)
    for src in ref.sources:
        s = slug(src)
        d[f"d-acc-{s}-taux"] = facteur_annualisation(i_acc, V("Acces_ressource", src, "duree_vie", 30))
        if ref.param("Acces_ressource", src, "duree_vie_pompe"):
            d[f"d-acc-{s}-taux-pompe"] = facteur_annualisation(i_acc, V("Acces_ressource", src, "duree_vie_pompe", 20))
        if type_source(src) == "forage":
            prof = V("Acces_ressource", src, "profondeur", 50)
            forage = V("Acces_ressource", src, "foration_ml") * prof
            d["d-forage-foration"] = forage
            d["d-forage-total"] = (V("Acces_ressource", src, "dossier_etude") + forage
                                   + V("Acces_ressource", src, "raccordement_electrique")
                                   + V("Acces_ressource", src, "pompe_abri"))
    a_res = facteur_annualisation(i_acc, V("Acces_ressource", "Général", "duree_vie_reseau", 30))
    cout_ml = V("Acces_ressource", "Général", "cout_tuyau_ml")
    subv_defaut = V("Acces_ressource", "Général", "taux_subvention", 0.7)
    d["d-acc-reseau-taux"] = a_res
    for src in ref.sources:
        s = slug(src)
        capex = V("Acces_ressource", src, "distance_amenee", 0) * cout_ml
        subv = max(min(V("Acces_ressource", src, "taux_subvention", subv_defaut), 1.0), 0.0)
        d[f"d-res-{s}-capex"] = capex
        d[f"d-res-{s}-annuite"] = capex * (1 - subv) * a_res
    return d
