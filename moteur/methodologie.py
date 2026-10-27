# -*- coding: utf-8 -*-
"""
Méthodologie détaillée (PDF) pour relecture scientifique
========================================================
Document produit à la demande (bouton de l'onglet Références > Méthode) à partir de l'état courant
du référentiel (paramètres des cultures, références) et des résultats de validation
(``validation/comparaison.csv``). Police Marianne : les symboles absents de la police (somme,
delta, thêta) sont écrits en toutes lettres.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from . import climat
from .rapport import BLEU, GRIS, Rapport, nombre
from .referentiel import Referentiel


def _f(v: Optional[float], dec: int = 2) -> str:
    return "–" if v is None else nombre(v, dec)


def methodologie_pdf(ref: Referentiel, validation: Optional[Dict[str, Any]], catalogue: Dict[str, Any]) -> bytes:
    pdf = Rapport(time.strftime("%d/%m/%Y", time.localtime(ref.date_modification)))
    pdf.add_page()
    T, P = pdf.titre, pdf.texte

    def formule(t: str):
        pdf.set_fill_color(240, 240, 250)
        pdf.set_font("Marianne", "", 8.5)
        pdf.multi_cell(0, 4.6, t, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def puces(liste):
        for t in liste:
            P("•  " + t, 8.8)

    # ------------------------------------------------------------------ En-tête
    pdf.set_font("Marianne", "B", 8)
    pdf.cell(0, 4, "RÉPUBLIQUE FRANÇAISE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Marianne", "", 7.5)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 4, "Secrétariat général à la planification écologique", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Marianne", "B", 16)
    pdf.set_text_color(*BLEU)
    pdf.multi_cell(0, 8, "Analyse financière d'un système d'irrigation – méthodologie détaillée",
                   new_x="LMARGIN", new_y="NEXT")
    P(f"Document de relecture scientifique, généré le {time.strftime('%d/%m/%Y')} à partir du référentiel du "
      f"{time.strftime('%d/%m/%Y', time.localtime(ref.date_modification))}.", 9, couleur=GRIS)

    # ------------------------------------------------------------------ 1. Objet
    T("1. Objet et périmètre")
    P("L'application estime, pour une parcelle située dans une commune de France "
      "métropolitaine, le coût annuel d'un système d'irrigation et le gain de production qu'il procure, en année "
      "climatique moyenne. Le gain repose sur deux grandeurs agronomiques : le besoin net en eau d'irrigation de "
      "la culture (mm) et l'écart entre rendement irrigué et rendement sans irrigation (q/ha). Ce document décrit "
      "comment elles sont calculées, comment la méthode retenue est choisie, et les résultats de la validation.")

    # ------------------------------------------------------------------ 2. Données
    T("2. Données d'entrée")
    pdf.tableau([
        ["Climat (ETP, pluie)", "DRIAS, EURO-CORDEX 2020, ALADIN63_CNRM-CM5, RCP4.5 ; cumuls mensuels",
         "Grille 8 km ; point le plus proche du centre de la commune"],
        ["Réserve utile du sol", "Román Dobarco et al. (2021), sommée sur la profondeur de sol (au plus 2 m)",
         "90 m, moyennée à 1 km ; moyenne communale"],
        ["Profondeur de sol", "BDGSF 1/1 000 000 (INRA, 1998), classes 0,3 / 0,5 / 1 / 2 m",
         "Rasterisée à 1 km ; moyenne communale"],
        ["Cartes MAELIA", "MAELIA 1.4.31 / AqYield, Explore2 narratif « violet », RCP4.5, 2020-2040",
         "Mailles de 8 km touchant la commune"],
        ["Paramètres des cultures", "Référentiel : Kc mensuels, enracinement, fraction p, Ky, rendements, besoins",
         "National"],
    ], (38, 86, 54), entete=["Donnée", "Source", "Résolution / agrégation"], aligne=["LEFT"] * 3, taille=8)

    # ------------------------------------------------------------------ 3. Choix de la méthode
    T("3. Choix automatique de la méthode")
    P("Pour chaque grandeur, l'application retient la première méthode disponible dans l'ordre ci-dessous. Les "
      "valeurs des autres méthodes restent consultables (bouton « i » à côté du résultat), ce qui donne une mesure "
      "simple de l'incertitude. Une valeur saisie par l'utilisateur prime toujours.")
    pdf.tableau([
        ["Besoin net en eau", "1. SGPE  2. MAELIA  3. Référentiel",
         "SGPE : validée contre CropWat, sensible au sol et au climat local, 21 cultures"],
        ["Rendements irrigué et pluvial", "1. MAELIA  2. Référentiel",
         "Modèle de culture calé en France ; statistiques observées à défaut"],
        ["Rendement pluvial (option)", "SGPE (Ky), case « exploratoire »",
         "Non calé sur des rendements observés : pessimiste pour le maïs"],
    ], (44, 52, 82), entete=["Grandeur", "Ordre de préférence", "Justification"], aligne=["LEFT"] * 3, taille=8)
    seuil = ref.valeur("Cultures", "Général", "besoin_plausible_max", None, 450)
    P(f"Un avertissement s'affiche lorsque le besoin retenu dépasse {nombre(seuil)} mm (seuil du référentiel).", 8.8)

    # ------------------------------------------------------------------ 4. SGPE
    T("4. Besoin en eau : méthode SGPE (bilan hydrique type CROPWAT)")
    P("Bilan hydrique journalier de la zone racinaire, sur le modèle du calendrier d'irrigation de CROPWAT "
      "(Smith, 1992) et du chapitre 8 de FAO-56 (Allen et al., 1998). Le climat mensuel est réparti uniformément "
      "sur les jours du mois ; la saison culturale commence au premier mois où Kc > 0 après un mois où Kc = 0 "
      "(une culture d'hiver commence ainsi en octobre).")
    formule("Dr(j) = max(0 ; Dr(j−1) − Peff(j)) + ETc(j) − I(j)        épuisement de la réserve (mm)\n"
            "ETc(j) = Kc(mois) × ETP(j)\n"
            "TAW(j) = RU × min(Zr(j) ; D) ÷ D        RU : réserve utile (mm) sur la profondeur de sol D (m)\n"
            "RAW(j) = p(j) × TAW(j),   p(j) = p_FAO + 0,04 × (5 − ETc(j)), borné à [0,1 ; 0,8]   (FAO-56, éq. 81)\n"
            "I(j) = Dr(j) si Dr(j) > RAW(j)        retour à la capacité au champ\n"
            "Besoin net (mm) = somme des I(j) sur la saison")
    puces([
        "Pluie efficace, méthode USDA S.C.S. de CROPWAT sur le cumul mensuel : Peff = P × (125 − 0,2 P) ÷ 125 si "
        "P ≤ 250 mm, 125 + 0,1 P au-delà ; l'excédent au-delà de la capacité au champ est perdu par drainage.",
        "Profondeur racinaire : de Zr_ini (" + _f(ref.valeur("Cultures", "Général", "zr_ini"), 2) + " m) au semis à "
        "Zr_max au pic de Kc, proportionnellement à la montée du Kc ; le sol nouvellement colonisé est à l'état "
        "hydrique initial.",
        "État initial : épuisement de " + _f((ref.valeur("Cultures", "Général", "depletion_initiale") or 0) * 100, 0)
        + " % de la réserve au semis (0 % = capacité au champ, défaut de CROPWAT). Cultures pérennes (Kc > 0 toute "
        "l'année) : une année de mise en route, la seconde est comptée.",
        "Fin de cycle : l'apport est limité à ce qu'il faut pour atteindre la récolte sans stress, soit "
        "I = min(Dr ; Dr + M − RAW), où M est le plus fort déficit cumulé (ETc − Peff) à venir jusqu'à la récolte. "
        "Sans cette règle (comportement de CROPWAT), l'eau apportée en fin de cycle et laissée dans le sol est "
        "comptée dans le besoin ; l'écart moyen est d'environ 20 mm.",
        "RU nulle (mailles d'eau ou urbaines) : traitée comme une absence de donnée, la valeur par défaut du "
        "référentiel s'applique.",
    ])

    # Paramètres des cultures
    lignes = []
    for c in ref.cultures:
        kc = climat.kc_mensuels(ref, c)
        if kc is None:
            continue
        p_kc = ref.param("Cultures", c, "kc_06") or ref.param("Cultures", c, "kc_01")
        source = ref.reference(p_kc.ref_id).courte if p_kc and ref.reference(p_kc.ref_id) else "–"
        mois = [m + 1 for m in range(12) if kc[m] > 0]
        lignes.append([c, " ".join(nombre(k, 2) if k else "0" for k in kc), _f(ref.valeur("Cultures", c, "zr_max")),
                       _f(ref.valeur("Cultures", c, "p_fao")), _f(ref.valeur("Cultures", c, "ky")), source,
                       "oui" if catalogue.get(c, {}).get("complet") else "–"])
    P("Paramètres des cultures (Kc de janvier à décembre) :", 8.8, gras=True)
    pdf.tableau(lignes, (25, 70, 13, 11, 11, 34, 14),
                entete=["Culture", "Kc mensuels", "Zr max", "p", "Ky", "Source des Kc", "MAELIA"], taille=7)
    P("Choix des paramètres : pour le tournesol, le soja et le colza, les jeux SB2023 du package CropWat (calés pour "
      "MAELIA sur le bassin de l'Aveyron, Kc journaliers moyennés par mois) ; pour les autres cultures, FAO-56. Le "
      "jeu retenu est celui dont le besoin moyen sur l'échantillon de validation est le plus proche de la moyenne "
      "MAELIA / référentiel. Les jeux SB2023 du maïs (135 mm contre 178 mm, MAELIA 195 mm, référentiel 180 mm) et "
      "des céréales à paille (13 mm contre 65 mm, MAELIA 73 mm) n'ont pas été retenus.", 8.5)

    # ------------------------------------------------------------------ 5. Autres méthodes
    T("5. Autres méthodes : MAELIA et référentiel")
    puces([
        "MAELIA : valeur moyenne des mailles de 8 km qui touchent le contour de la commune (repli : maille du centre, "
        "puis maille valide la plus proche). Les cartes de rendement donnent un pourcentage du rendement potentiel, "
        "converti en q/ha : rendement = % ÷ 100 × rendement optimal de l'espèce (especesCultivees.csv), à défaut le "
        "rendement irrigué du référentiel. Horizons moyen et lointain : cartes 2040-2060.",
        "Référentiel : une valeur nationale par culture (Agreste, instituts techniques, DRAAF), source et précision "
        "dans le classeur.",
    ])

    # ------------------------------------------------------------------ 6. Rendements
    T("6. Rendements")
    P("Le gain lié à l'irrigation est proportionnel à l'écart entre rendement irrigué et rendement pluvial :")
    formule("Gain (€/an) = (rendement irrigué − rendement pluvial) (q/ha) × 0,1 × prix de vente (€/t) × surface (ha)")
    P("Option exploratoire SGPE : rendement irrigué (Ym) du référentiel ; rendement pluvial tiré de la relation de la "
      "FAO (Doorenbos & Kassam, 1979), avec le rapport ETa/ETc d'un bilan hydrique sans irrigation (même sol, même "
      "climat ; ETa = Ks × ETc, Ks = (TAW − Dr) ÷ ((1 − p) × TAW) lorsque Dr > RAW, FAO-56 éq. 84) :")
    formule("Rendement pluvial = Ym × max(0 ; 1 − Ky × (1 − somme ETa ÷ somme ETc))")
    P("Ky saisonniers de FAO-33 ; valeurs estimées pour les cultures que FAO-33 ne tabule pas (abricotier, amandier, "
      "pommier, olivier, colza), signalées dans le référentiel. La relation saisonnière ignore la sensibilité "
      "différente des stades : elle surestime les pertes du maïs par rapport à MAELIA et aux statistiques.", 8.8)

    # ------------------------------------------------------------------ 7. Économie
    T("7. Volume et modèle économique")
    formule("Volume prélevé (m³) = besoin net (mm) × 10 × surface (ha) ÷ efficience d'application du matériel\n"
            "Annuité = CAPEX × (1 − subvention) × i(1+i)^n ÷ ((1+i)^n − 1)      (1/n si i = 0)\n"
            "Coût = énergie + redevance + équipement (annuité + maintenance) + main-d'œuvre + accès à la ressource\n"
            "Énergie = (volume prélevé + remplissage pompé d'une retenue) × prix (€/m³)\n"
            "Redevance = volume prélevé × taux de l'agence (catégorie, origine de l'eau) si le seuil est dépassé\n"
            "Bilan = gain − coût ; coût sans subvention : annuités recalculées sur le CAPEX brut")
    P("Les paramètres économiques (CAPEX, durées de vie, maintenance, main-d'œuvre, tarifs, redevances, prix de "
      "l'énergie) et leurs sources sont détaillés dans le référentiel et l'onglet Références de l'application.", 8.8)

    # ------------------------------------------------------------------ 8. Validation
    T("8. Validation")
    if not validation:
        P("Résultats de validation absents : lancer « python outils/comparer_modeles.py ».")
    else:
        P(f"{validation['n_cas']} cas : {validation['n_points']} points de grille DRIAS régulièrement répartis × "
          f"{len(validation['cultures'])} cultures disposant de cartes MAELIA. Même sol et même climat pour SGPE et "
          "CropWat (package R CropWat 0.3.0, INRAE) ; MAELIA a son propre climat (Explore2). Écart = second modèle − "
          "SGPE ; EAM = écart absolu moyen ; r = corrélation entre points.", 8.8)
        for titre, cle_bloc, comparaisons, unite, dec in [
                ("Besoin net (mm)", "besoin", validation["comparaisons_besoin"], "mm", 0),
                ("Rendement relatif sans irrigation (–)", "rendement", validation["comparaisons_rendement"], "", 2)]:
            P(titre, 9, gras=True)
            for cle, libelle in comparaisons:
                lignes = []
                for l in validation[cle_bloc]:
                    s = l.get(cle)
                    if s:
                        lignes.append([l["culture"], str(s["n"]), _f(s["moy_1"], dec), _f(s["moy_2"], dec),
                                       ("+" if s["ecart"] >= 0 else "") + _f(s["ecart"], dec), _f(s["eam"], dec),
                                       _f(s["r"], 2)])
                P(libelle, 8.5, couleur=BLEU)
                pdf.tableau(lignes, (40, 14, 26, 26, 24, 24, 24),
                            entete=["Culture", "n", "SGPE", "Autre", "Écart", "EAM", "r"], taille=7.5)
        P("Lecture : avec les mêmes entrées, le bilan hydrique de l'application reproduit exactement le moteur de "
          "CropWat (écart nul, r = 1), ce qui valide son implémentation. Les écarts avec CropWat paramétré "
          "différemment et avec MAELIA viennent du paramétrage des cultures (calendrier, Kc, enracinement) et du "
          "climat. L'accord avec MAELIA est correct pour les cultures d'été (maïs, sorgho, soja) et faible pour les "
          "cultures d'hiver (blé, orge, colza), la betterave et la pomme de terre : pour celles-ci, la valeur "
          "retenue doit être lue avec les autres méthodes affichées.", 8.8)

    # ------------------------------------------------------------------ 9. Limites
    T("9. Limites")
    puces([
        "Année climatique moyenne, climat mensuel réparti uniformément : ni séquence réelle de pluies, ni année sèche "
        "(quinquennale sèche) qui dimensionne en pratique les installations.",
        "Un seul modèle climatique (ALADIN63) et un seul narratif pour MAELIA : l'incertitude climatique n'est pas "
        "représentée.",
        "Calendriers culturaux nationaux (Kc mensuels) ; réserve utile et profondeur moyennes de la commune.",
        "Rendement SGPE : relation saisonnière, non calée sur des rendements observés (option exploratoire).",
        "Couverture partielle du besoin (comparaison de trajectoires) : gain supposé proportionnel au volume apporté.",
        "Pistes : calendriers régionaux ; calage de Ky sur les rendements irrigués et non irrigués observés "
        "(Agreste) ; climat journalier DRIAS et année sèche ; ensemble de modèles climatiques.",
    ])

    # ------------------------------------------------------------------ 10. Références
    T("10. Références")
    for r in sorted(ref.references.values(), key=lambda r: r.complete):
        P(r.complete + (f" {r.url}" if r.url else ""), 7.8)
    return bytes(pdf.output())
