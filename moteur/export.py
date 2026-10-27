# -*- coding: utf-8 -*-
"""
Variables du volet « Cas personnel » : regroupement par catégorie et classeur Excel
====================================================================================
L'agriculteur télécharge un classeur qui contient ses choix (feuille « Simulation ») et la
valeur de chaque variable (feuille « Variables » : valeur du référentiel, valeur retenue).
Il peut le modifier dans Excel puis le recharger dans l'application : seule la colonne
« Ma valeur » est relue, avec la clé Feuille|Objet|code de la colonne A.
"""

from __future__ import annotations

import io
import time
from typing import Any, Dict, List, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .referentiel import CLE_LIBRE, Referentiel, _nombre

# Feuilles du référentiel présentées dans l'onglet Variables, dans cet ordre
CATEGORIES = [
    ("Cultures", "Culture", "Rendements, besoin en eau et coefficients culturaux de la culture choisie."),
    ("Equipement", "Équipement d'irrigation", "Investissement, durée de vie, maintenance, main-d'œuvre et "
                                              "efficience du matériel choisi ; taux d'actualisation."),
    ("Acces_ressource", "Accès à la ressource en eau", "Coût de l'ouvrage, tarif, distance d'amenée et durées "
                                                       "de vie du type d'accès choisi."),
    ("Ressources", "Redevance et énergie", "Taux de redevance de l'agence de l'eau et prix de l'énergie de pompage."),
]
# Saisis ailleurs dans le formulaire (prix de vente, subventions) : ils n'apparaissent pas une seconde fois
CODES_EXCLUS = {"taux_subvention", "prix_vente", "prix_masaa"}

# Tableau « Mes hypothèses de coûts » du volet Cas personnel : groupes de paramètres saisissables
# directement sous le formulaire. La durée de vie et le taux de remplissage sont saisis dans le
# formulaire, la réserve utile et la redevance à part (valeur par défaut calculée).
GROUPES_HYPOTHESES = [
    ("Equipement", "Matériel d'irrigation", {"duree_vie", "taux_subvention"}),
    ("Acces_ressource", "Accès à la ressource en eau", {"duree_vie", "taux_subvention", "taux_remplissage"}),
    ("Cultures", "Sol et bilan hydrique (méthode SGPE)", {"ru_defaut", "profondeur_sol"}),
]
CODES_BILAN_HYDRIQUE = {"zr_max", "p_fao", "ky", "zr_ini", "depletion_initiale"}

# Choix de la feuille « Simulation » : clé, libellé
CHAMPS_SIMULATION = [
    ("commune_code", "Commune (code INSEE)"), ("commune_nom", "Commune"), ("departement", "Département"),
    ("culture", "Culture"), ("surface", "Surface irriguée (ha)"), ("prix_vente", "Prix de vente (€/t)"),
    ("source", "Source de l'eau"),
    ("type_retenue", "Gestion de la retenue (individuelle ou collective)"), ("nb_adherents", "Nombre d'adhérents"),
    ("capacite_auto", "Capacité dimensionnée sur le besoin (oui/non)"), ("capacite", "Capacité de stockage (m³)"),
    ("deja_amorti", "Infrastructure déjà amortie (oui/non)"), ("equipement", "Équipement"),
    ("nb_unites", "Nombre d'unités"), ("deja_amorti_equipement", "Matériel déjà amorti (oui/non)"),
    ("subvention_equipement_pct", "Subvention au matériel (%)"),
    ("subvention_acces_pct", "Subvention à l'accès à la ressource (%)"), ("agence", "Agence de l'eau"),
    ("zre", "Zone de répartition des eaux (oui/non)"), ("methode_besoin", "Méthode du besoin en eau (auto, sgpe, carte, reference)"),
    ("methode_rendement", "Méthode des rendements (auto, ou sgpe pour l'option exploratoire)"),
    ("ru_mm", "Réserve utile du sol saisie (mm ; vide = carte des sols)"),
    ("profondeur_sol_m", "Profondeur de sol saisie (m ; vide = carte BDGSF)"),
    ("redevance_c_m3", "Redevance saisie (c€/m³ ; vide = taux de l'agence)"),
]
BOOLEENS = {"capacite_auto", "deja_amorti", "deja_amorti_equipement", "zre", "sans_carte"}
ENTIERS = {"nb_adherents", "nb_unites"}
NOMBRES = {"surface", "prix_vente", "capacite", "subvention_equipement_pct", "subvention_acces_pct", "ru_mm",
           "profondeur_sol_m", "redevance_c_m3"}

BLEU = PatternFill("solid", fgColor="000091")
BLEU_CLAIR = PatternFill("solid", fgColor="E3E3FD")


def hypotheses_couts(ref: Referentiel) -> List[Dict[str, Any]]:
    """Paramètres du tableau « Mes hypothèses » (volet Cas personnel), par groupe puis par objet.

    Seules les lignes de l'objet choisi dans le formulaire (et de l'objet « Général ») sont
    affichées dans la page ; les autres sont présentes mais masquées."""
    sortie = []
    for feuille, titre, exclus in GROUPES_HYPOTHESES:
        objets = []
        for objet in ref.objets(feuille, exclure_general=False):
            pp = ref.params_objet(feuille, objet)
            params = [p for p in pp.values() if p.code not in exclus and p.code not in CODES_EXCLUS]
            if feuille == "Cultures":
                params = [p for p in params if p.code in CODES_BILAN_HYDRIQUE]
            if "capex_unitaire" in pp:  # CAPEX calculé par unité : le CAPEX à l'hectare ne sert pas
                params = [p for p in params if p.code != "capex_ha"]
            if params:
                objets.append({"objet": objet, "params": params})
        sortie.append({"feuille": feuille, "titre": titre, "objets": objets})
    return sortie


def _objets_utilises(e: Dict[str, Any]) -> Dict[str, set]:
    return {"Cultures": {e.get("culture"), "Général"}, "Equipement": {e.get("equipement"), "Général"},
            "Acces_ressource": {e.get("source"), "Général"}, "Ressources": {e.get("agence"), "Énergie"}}


def _en_affichage(p, v: Optional[float]) -> Optional[float]:
    """Valeur dans l'unité affichée : les pourcentages en %, comme dans l'application."""
    if v is None:
        return None
    return round(v * 100, 6) if p.est_pourcentage else v


def _largeurs(ws, largeurs):
    for i, l in enumerate(largeurs, start=1):
        ws.column_dimensions[get_column_letter(i)].width = l


def _entete(ws, titres):
    ws.append(titres)
    for c in ws[ws.max_row]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = BLEU
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(row=ws.max_row + 1, column=1)


def classeur_variables(ref: Referentiel, e: Dict[str, Any], surcharges: Dict[str, Any],
                       commune: Optional[Dict[str, Any]], res: Optional[Dict[str, Any]] = None) -> bytes:
    """Classeur des choix et des variables de la simulation."""
    wb = Workbook()
    lisez = wb.active
    lisez.title = "Lisez-moi"
    for ligne in [
        ["Analyse financière d'un système d'irrigation – mes variables"],
        [f"Classeur produit le {time.strftime('%d/%m/%Y à %H:%M')} ; référentiel du "
         f"{time.strftime('%d/%m/%Y', time.localtime(ref.date_modification))}."],
        [],
        ["Feuille « Simulation » : vos choix (commune, culture, surface, ressource, équipement, subventions)."],
        ["Feuille « Variables » : chaque variable, la valeur du référentiel et votre valeur (colonne « Ma valeur »)."],
        ["Feuille « Résultats » : les principaux résultats de la simulation au moment du téléchargement."],
        [],
        ["Pour réutiliser ce classeur : modifiez la colonne « Ma valeur » ou les valeurs de la feuille Simulation,"],
        ["enregistrez, puis rechargez-le dans le volet « Cas personnel – parcelle » (bouton « Importer mes variables »)."],
        ["Ne modifiez pas la colonne « Clé » : elle identifie la variable. Les pourcentages se saisissent en % (ex. 85)."],
    ]:
        lisez.append(ligne)
    lisez["A1"].font = Font(bold=True, size=14, color="000091")
    lisez.column_dimensions["A"].width = 110

    ws = wb.create_sheet("Simulation")
    _entete(ws, ["Clé", "Choix", "Valeur"])
    valeurs = dict(e)
    valeurs.setdefault("capacite_auto", True)
    valeurs["commune_code"] = (commune or {}).get("code", "")
    valeurs["commune_nom"] = (commune or {}).get("nom", "")
    valeurs["departement"] = (commune or {}).get("departement", "")
    valeurs["prix_vente"] = res["gain"]["prix"] if res else None
    for cle, libelle in CHAMPS_SIMULATION:
        v = valeurs.get(cle)
        if cle in BOOLEENS:
            v = "oui" if v else "non"
        ws.append([cle, libelle, v])
    _largeurs(ws, [26, 52, 32])

    ws = wb.create_sheet("Variables")
    _entete(ws, ["Clé", "Catégorie", "Objet", "Variable", "Unité", "Valeur du référentiel", "Ma valeur",
                 "Modifiée", "Source"])
    utilises = _objets_utilises(e)
    for feuille, titre, _ in CATEGORIES:
        for objet in ref.objets(feuille, exclure_general=False):
            if objet not in utilises[feuille]:
                continue
            for p in ref.params_objet(feuille, objet).values():
                if p.code in CODES_EXCLUS:
                    continue
                modifiee = p.cle in surcharges
                v = ref.valeur(feuille, objet, p.code, surcharges)
                unite = "%" if p.est_pourcentage else p.unite
                ws.append([p.cle, titre, objet, p.libelle, unite, _en_affichage(p, p.valeur), _en_affichage(p, v),
                           "oui" if modifiee else "", ref.infobulle(p)])
                ws.cell(row=ws.max_row, column=7).fill = BLEU_CLAIR
    _largeurs(ws, [40, 26, 26, 46, 12, 18, 14, 10, 80])
    ws.column_dimensions["A"].hidden = False

    if res:
        ws = wb.create_sheet("Résultats")
        _entete(ws, ["Indicateur", "Valeur", "Unité"])
        c, a = res["couts"], res["agro"]
        for ligne in [
            ("Rendement irrigué", a["rdt_irrigue"], "q/ha"), ("Rendement pluvial", a["rdt_pluvial"], "q/ha"),
            ("Besoin en eau d'irrigation", a["besoin_mm"], "mm"), ("Volume prélevé", a["volume_preleve"], "m³/an"),
            ("Gain lié à l'irrigation", res["gain"]["total"], "€/an"),
            ("Coût de l'irrigation, avec subvention", c["total"], "€/an"),
            ("  dont charges fixes", c["fixes"], "€/an"), ("  dont charges variables", c["variables"], "€/an"),
            ("Coût de l'eau, avec subvention", c["c_par_m3"], "c€/m³"),
            ("Coût de l'irrigation, sans subvention", c["sans_subvention"]["total"], "€/an"),
            ("Coût de l'eau, sans subvention", c["sans_subvention"]["c_par_m3"], "c€/m³"),
            ("Bilan (gain − coût), avec subvention", res["bilan"]["total"], "€/an"),
            ("Bilan (gain − coût), sans subvention", res["bilan"]["sans_subvention"]["total"], "€/an"),
            ("Investissement total", res["capex"]["total"], "€"),
            ("Investissement à la charge de l'agriculteur", res["capex"]["reste_a_charge"], "€"),
            ("Aide publique à l'investissement", res["capex"]["total"] - res["capex"]["reste_a_charge"], "€"),
            ("Réserve utile du sol", res["agro"].get("sol", {}).get("ru"), "mm"),
            ("Profondeur de sol", res["agro"].get("sol", {}).get("profondeur"), "m"),
        ] + [(f"Poste – {p['libelle']}", p["montant"], "€/an") for p in c["postes"]]:
            ws.append([ligne[0], round(ligne[1], 2) if isinstance(ligne[1], (int, float)) else ligne[1], ligne[2]])
        _largeurs(ws, [48, 16, 10])

    flux = io.BytesIO()
    wb.save(flux)
    return flux.getvalue()


def _booleen(v) -> bool:
    return str(v).strip().lower() in ("oui", "o", "vrai", "true", "1", "yes")


def lire_classeur_variables(flux, ref: Referentiel) -> Dict[str, Any]:
    """Choix, commune et surcharges d'un classeur produit par classeur_variables."""
    wb = load_workbook(flux, data_only=True, read_only=True)
    entrees: Dict[str, Any] = {}
    commune: Dict[str, Any] = {}
    if "Simulation" in wb.sheetnames:
        for ligne in wb["Simulation"].iter_rows(min_row=2, values_only=True):
            if not ligne or not ligne[0]:
                continue
            cle, v = str(ligne[0]).strip(), ligne[2] if len(ligne) > 2 else None
            if cle in ("commune_code", "commune_nom", "departement"):
                commune[cle] = "" if v is None else str(v).strip()
            elif cle in BOOLEENS:
                entrees[cle] = _booleen(v)
            elif cle in ENTIERS:
                n = _nombre(v)
                entrees[cle] = int(n) if n else None
            elif cle in NOMBRES:
                entrees[cle] = _nombre(v)
            elif v is not None:
                entrees[cle] = str(v).strip()
    surcharges: Dict[str, Any] = {}
    if "Variables" in wb.sheetnames:
        lignes = wb["Variables"].iter_rows(values_only=True)
        entete = [str(x or "").strip().lower() for x in next(lignes, ())]
        i_cle = entete.index("clé") if "clé" in entete else 0
        i_val = entete.index("ma valeur") if "ma valeur" in entete else 6
        for ligne in lignes:
            if not ligne or len(ligne) <= max(i_cle, i_val):
                continue
            p = ref.params.get(str(ligne[i_cle] or "").strip())
            v = _nombre(ligne[i_val])
            if p is None or v is None or p.code in CODES_EXCLUS:
                continue
            if p.est_pourcentage:
                v = v / 100.0
            if p.valeur is None or abs(v - p.valeur) > 1e-9:
                surcharges[p.cle] = v
    wb.close()
    surcharges.pop(CLE_LIBRE, None)
    return {"entrees": entrees, "surcharges": surcharges,
            "commune": {"code": commune.get("commune_code", ""), "nom": commune.get("commune_nom", ""),
                        "departement": commune.get("departement", "")}}
