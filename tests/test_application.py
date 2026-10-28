# -*- coding: utf-8 -*-
"""
Tests de non-régression
=======================
Exécution depuis la racine de l'application :

    python -m unittest discover -s tests -v

Les tests ne dépendent ni de rasterio ni du réseau : les valeurs agronomiques
sont injectées directement dans le moteur, comme le fait l'application lorsque
la culture n'a pas de carte.
"""

import os
import sys
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import config  # noqa: E402
from moteur import cartes  # noqa: E402
from moteur.calcul import (POSTES, cout_maintenance_ha, facteur_annualisation,  # noqa: E402
                           simuler, type_source, valeurs_derivees)
from moteur.referentiel import CLE_LIBRE, GestionnaireReferentiel, slug  # noqa: E402

REF = GestionnaireReferentiel(config.REFERENTIEL).get()

AGRO = {"rdt_irrigue": 107.0, "rdt_pluvial": 78.0, "besoin_mm": 180.0}


def entrees(**kw):
    base = {"culture": "Maïs", "surface": 30.0, "source": "Forage individuel", "equipement": "Pivot",
            "agence": "Adour-Garonne", "zre": False, "type_retenue": "individuelle", "nb_adherents": 1,
            "capacite_auto": True, "deja_amorti": False}
    base.update(kw)
    return base


class TestReferentiel(unittest.TestCase):
    def test_lecture(self):
        self.assertGreater(len(REF.params), 200)
        self.assertEqual(len(REF.cultures), 24)
        self.assertEqual(len(REF.equipements), 6)
        self.assertEqual(len(REF.sources), 5)
        self.assertEqual(len(REF.agences), 6)
        self.assertEqual(len(REF.exemples), 6)

    def test_pas_d_anomalie(self):
        self.assertEqual(REF.anomalies, [], "\n".join(REF.anomalies))

    def test_toutes_les_references_existent(self):
        manquantes = {p.ref_id for p in REF.params.values() if p.ref_id and p.ref_id not in REF.references}
        self.assertEqual(manquantes, set())

    def test_colonnes_lues_par_entete(self):
        # Colonnes repérées par leur en-tête : unité, variable, bornes et référence bien lues
        p = REF.param("Cultures", "Maïs", "rdt_irrigue")
        self.assertEqual(p.unite, "q/ha")
        self.assertFalse(p.variable)
        self.assertIsNotNone(p.vmax)
        self.assertTrue(p.ref_id)
        self.assertTrue(any(q.variable for q in REF.params.values()))

    def test_rendements_cartes_en_pourcentage(self):
        # Les cartes de rendement MAELIA sont en % du rendement potentiel : converties en q/ha
        # (% × potentiel ÷ 100), bornées par le potentiel, et irrigué ≥ pluvial en moyenne.
        cat = cartes.catalogue(REF, config.DOSSIER_CARTES)
        info = cat.get("Maïs")
        if not (info and info["complet"] and cartes.disponible()):
            self.skipTest("cartes du maïs ou rasterio indisponibles sur ce poste")
        u = cartes.unites_culture(REF, "Maïs", info, config.ESPECES_CULTIVEES)
        self.assertEqual(u["rdt"][0], cartes.POURCENT)
        pot = u["potentiel"]["valeur"]
        x = cartes.extraire(REF, "Maïs", info, None, (1.44, 43.60), config.ESPECES_CULTIVEES)
        for var in ("rdt_irrigue", "rdt_pluvial"):
            self.assertAlmostEqual(x[var], x["brut"][var]["valeur"] * pot / 100.0, places=6)
            self.assertLessEqual(x[var], pot + 1e-9)
        self.assertGreaterEqual(x["rdt_irrigue"], x["rdt_pluvial"])

    def test_rendement_optimal_especes(self):
        # RENDEMENT_OPTIMAL (t/ha) de especesCultivees.csv prioritaire sur le référentiel
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("ESPECE;maisT;BTH\nRENDEMENT_MOYEN;NA;NA\nRENDEMENT_OPTIMAL;13;NA\n")
        try:
            self.assertEqual(cartes.rendements_optimaux(f.name), {"maist": 13.0})
            pot = cartes.rendement_potentiel(REF, "Maïs", {"code": "MAIST"}, f.name)
            self.assertEqual(pot["valeur"], 130.0)
            pot = cartes.rendement_potentiel(REF, "Blé tendre", {"code": "BTH"}, f.name)
            self.assertEqual(pot["valeur"], REF.valeur("Cultures", "Blé tendre", "rdt_irrigue"))
        finally:
            os.unlink(f.name)

    def test_departements(self):
        # 96 départements métropolitains (Corse comprise) ; les DOM relèvent des offices de l'eau
        self.assertEqual(len(REF.departements), 96)
        self.assertIn("2A", REF.departements)
        self.assertIn("2B", REF.departements)
        self.assertEqual(REF.agence_du_departement("40"), "Adour-Garonne")
        self.assertEqual(REF.agence_du_departement("76"), "Seine-Normandie")
        for d in REF.departements.values():
            self.assertIn(d["agence"], REF.agences)

    def test_surcharge_bornee_et_reservee_aux_variables(self):
        variable = next(p for p in REF.params.values() if p.variable and p.vmax is not None)
        fige = next(p for p in REF.params.values() if not p.variable)
        trop = variable.vmax * 10 + 1
        self.assertEqual(REF.valeur(variable.feuille, variable.objet, variable.code, {variable.cle: trop}),
                         variable.vmax)
        self.assertEqual(REF.valeur(fige.feuille, fige.objet, fige.code, {fige.cle: 12345.0}), fige.valeur)

    def test_exemples_coherents(self):
        for x in REF.exemples:
            self.assertIn(x["culture"], REF.cultures, x["titre"])
            self.assertIn(x["source"], REF.sources, x["titre"])
            self.assertIn(x["equipement"], REF.equipements, x["titre"])
            self.assertIn(x["departement"], REF.departements, x["titre"])
            self.assertTrue(x["enjeu"], x["titre"])


class TestOutils(unittest.TestCase):
    def test_facteur_annualisation(self):
        self.assertAlmostEqual(facteur_annualisation(0.0, 20), 0.05)
        self.assertAlmostEqual(facteur_annualisation(0.03, 15), 0.083767, places=5)
        self.assertEqual(facteur_annualisation(0.03, 0), 0.0)
        # Le facteur décroît avec la durée et croît avec le taux
        self.assertGreater(facteur_annualisation(0.03, 10), facteur_annualisation(0.03, 30))
        self.assertGreater(facteur_annualisation(0.06, 20), facteur_annualisation(0.02, 20))

    def test_type_source(self):
        attendus = {"Forage individuel": "forage", "Pompage sur cours d'eau": "cours_eau",
                    "Réseau collectif alimenté par canal": "asa", "Retenue collinaire": "retenue_collinaire",
                    "Retenue par pompage": "retenue_pompage", "ASA": "asa"}
        for nom, t in attendus.items():
            self.assertEqual(type_source(nom), t, nom)


class TestMoteur(unittest.TestCase):
    def test_matrice_culture_source_equipement(self):
        """Aucune combinaison ne doit produire d'erreur ni de valeur aberrante."""
        for culture in REF.cultures:
            for source in REF.sources:
                for equipement in REF.equipements:
                    e = entrees(culture=culture, source=source, equipement=equipement)
                    agro = {"rdt_irrigue": REF.valeur("Cultures", culture, "rdt_irrigue"),
                            "rdt_pluvial": REF.valeur("Cultures", culture, "rdt_pluvial"),
                            "besoin_mm": REF.valeur("Cultures", culture, "besoin_irrigation")}
                    r = simuler(REF, e, {}, agro)
                    cle = f"{culture}/{source}/{equipement}"
                    self.assertGreater(r["couts"]["total"], 0, cle)
                    self.assertAlmostEqual(sum(p["montant"] for p in r["couts"]["postes"]),
                                           r["couts"]["total"], places=6, msg=cle)
                    self.assertAlmostEqual(sum(p["part"] for p in r["couts"]["postes"]), 1.0, places=6, msg=cle)
                    self.assertAlmostEqual(r["bilan"]["total"], r["gain"]["total"] - r["couts"]["total"],
                                           places=6, msg=cle)
                    for p in r["couts"]["postes"]:
                        self.assertGreaterEqual(p["montant"], 0, cle + " / " + p["cle"])

    def test_volume_et_efficience(self):
        r = simuler(REF, entrees(equipement="Goutte-à-goutte enterré"), {}, AGRO)
        self.assertAlmostEqual(r["agro"]["volume_applique"], 180 * 10 * 30)
        self.assertAlmostEqual(r["agro"]["volume_preleve"],
                               r["agro"]["volume_applique"] / r["agro"]["efficience"])
        # Une meilleure efficience prélève moins qu'un enrouleur, à surface constante
        enrouleur = simuler(REF, entrees(equipement="Enrouleur-canon"), {}, AGRO)
        self.assertLess(r["agro"]["volume_preleve"], enrouleur["agro"]["volume_preleve"])

    def test_effet_de_seuil_des_machines(self):
        """Le CAPEX du matériel unitaire progresse par paliers, pas linéairement."""
        s = REF.valeur("Equipement", "Pivot", "surface_unitaire")
        capex = {}
        for surface in (s - 1, s, s + 1, 2 * s, 2 * s + 1):
            r = simuler(REF, entrees(surface=surface, equipement="Pivot"), {}, AGRO)
            capex[surface] = (r["dimensionnement"]["nb_unites"], r["capex"]["equipement"])
        self.assertEqual(capex[s - 1][0], 1)
        self.assertEqual(capex[s][0], 1)
        self.assertEqual(capex[s + 1][0], 2)
        self.assertEqual(capex[2 * s][0], 2)
        self.assertEqual(capex[2 * s + 1][0], 3)
        self.assertEqual(capex[s - 1][1], capex[s][1])
        self.assertAlmostEqual(capex[s + 1][1], 2 * capex[s][1])

    def test_maintenance_equipement_unite_coherente(self):
        """La maintenance ne doit pas mélanger un taux en €/ha/an avec un pourcentage du CAPEX total.

        Régression : « maintenance_pct » est exprimé en €/ha/an pour la plupart des équipements
        (voir unité dans le référentiel) et ne doit alors PAS être multiplié par le CAPEX total,
        sous peine de coûts de maintenance aberrants (facteur ~1000).
        """
        for eq in REF.equipements:
            p = REF.param("Equipement", eq, "maintenance_pct")
            attendu = (REF.valeur("Equipement", eq, "capex_ha", {}, 0.0) * p.valeur) if p.est_pourcentage else p.valeur
            self.assertAlmostEqual(cout_maintenance_ha(REF, {}, eq), attendu, msg=eq)
        r = simuler(REF, entrees(equipement="Pivot", surface=30.0), {}, AGRO)
        maintenance_attendue = cout_maintenance_ha(REF, {}, "Pivot") * 30.0
        self.assertAlmostEqual(r["annualisation"]["equipement"]["maintenance"], maintenance_attendue)
        # Le coût total doit rester d'un ordre de grandeur raisonnable (pas de facteur ~1000 par erreur d'unité)
        self.assertLess(r["couts"]["total"], 50000)

    def test_gain_et_seuils(self):
        r = simuler(REF, entrees(), {}, AGRO)
        prix = r["gain"]["prix"]
        self.assertAlmostEqual(r["gain"]["total"], 29.0 * 0.1 * prix * 30)
        # Au prix minimal, le bilan s'annule
        equilibre = simuler(REF, entrees(), {"Cultures|Maïs|prix_vente": r["seuil"]["prix_min"]}, AGRO)
        self.assertAlmostEqual(equilibre["bilan"]["total"], 0.0, places=4)
        # Au gain de rendement minimal également
        agro2 = dict(AGRO, rdt_irrigue=AGRO["rdt_pluvial"] + r["seuil"]["delta_min"])
        equilibre2 = simuler(REF, entrees(), {}, agro2)
        self.assertAlmostEqual(equilibre2["bilan"]["total"], 0.0, places=4)

    def test_deux_jeux_de_prix(self):
        """Prix de marché (référentiel) ou barème MASAA de l'assurance récolte, au choix."""
        for c in REF.cultures:
            self.assertIsNotNone(REF.param("Cultures", c, "prix_masaa"), c)
        marche = simuler(REF, entrees(), {}, AGRO)
        masaa = simuler(REF, entrees(source_prix="masaa"), {}, AGRO)
        self.assertEqual(marche["gain"]["prix"], REF.valeur("Cultures", "Maïs", "prix_vente"))
        self.assertEqual(masaa["gain"]["prix"], REF.valeur("Cultures", "Maïs", "prix_masaa"))
        self.assertNotEqual(marche["gain"]["prix"], masaa["gain"]["prix"])

    def test_subvention_et_capital_rembourse(self):
        # Le forage a un taux de subvention documenté propre (défaut 45 %) : on surcharge cette clé.
        plein = simuler(REF, entrees(), {"Acces_ressource|Forage individuel|taux_subvention": 0.0}, AGRO)
        aide = simuler(REF, entrees(), {"Acces_ressource|Forage individuel|taux_subvention": 0.7}, AGRO)
        amorti = simuler(REF, entrees(deja_amorti=True), {}, AGRO)
        cout = lambda r: dict((p["cle"], p["montant"]) for p in r["couts"]["postes"])["acces"]  # noqa: E731
        self.assertGreater(cout(plein), cout(aide))
        self.assertLess(cout(amorti), cout(aide))
        self.assertEqual(amorti["capex"]["acces_brut"], 0.0)
        # La subvention d'accès à la ressource ne porte pas sur le matériel d'irrigation
        self.assertEqual(plein["capex"]["equipement"], aide["capex"]["equipement"])

    def test_subvention_equipement(self):
        # La subvention du matériel réduit l'annuité mais pas le CAPEX brut affiché
        sans = simuler(REF, entrees(), {"Equipement|Général|taux_subvention": 0.0}, AGRO)
        avec = simuler(REF, entrees(), {"Equipement|Général|taux_subvention": 0.4}, AGRO)
        self.assertEqual(sans["capex"]["equipement"], avec["capex"]["equipement"])
        self.assertAlmostEqual(avec["capex"]["equipement_net"], avec["capex"]["equipement"] * 0.6)
        self.assertAlmostEqual(avec["capex"]["subvention_equipement"], avec["capex"]["equipement"] * 0.4)
        self.assertLess(avec["annualisation"]["equipement"]["annuite"], sans["annualisation"]["equipement"]["annuite"])
        cout = lambda r: dict((p["cle"], p["montant"]) for p in r["couts"]["postes"])["equipement"]  # noqa: E731
        self.assertLess(cout(avec), cout(sans))
        # Elle ne s'applique pas si le matériel est déjà amorti (l'annuité n'est de toute façon pas comptée)
        amorti_eq = simuler(REF, entrees(deja_amorti_equipement=True), {"Equipement|Général|taux_subvention": 0.4}, AGRO)
        self.assertEqual(amorti_eq["capex"]["subvention_equipement"], 0.0)
        self.assertEqual(amorti_eq["capex"]["equipement_net"], 0.0)

    def test_subvention_equipement_hors_maintenance_et_main_oeuvre(self):
        """La subvention ne porte que sur le CAPEX : maintenance et main-d'œuvre sont inchangées."""
        sans = simuler(REF, entrees(subvention_equipement_pct=0), {}, AGRO)
        avec = simuler(REF, entrees(subvention_equipement_pct=60), {}, AGRO)
        self.assertAlmostEqual(sans["annualisation"]["equipement"]["maintenance"],
                               avec["annualisation"]["equipement"]["maintenance"])
        mo = lambda r: dict((p["cle"], p["montant"]) for p in r["couts"]["postes"])["main_oeuvre"]  # noqa: E731
        self.assertAlmostEqual(mo(sans), mo(avec))
        an = avec["annualisation"]["equipement"]
        self.assertAlmostEqual(an["annuite"], an["capex"] * 0.4 * an["facteur"])

    def test_annuite_brute_onglet_equipement(self):
        """Le tableau de l'onglet Équipement affiche l'annuité brute, quel que soit le taux de subvention."""
        for taux in (0.0, 0.4, 0.8):
            d = valeurs_derivees(REF, {"Equipement|Général|taux_subvention": taux}, {"equipement": "Pivot"})
            for eq in REF.equipements:
                s = slug(eq)
                capex_ha = REF.valeur("Equipement", eq, "capex_ha", {}, 0.0)
                self.assertAlmostEqual(d[f"d-eq-{s}-annuite"], capex_ha * d[f"d-eq-{s}-taux"], msg=eq)
                self.assertAlmostEqual(d[f"d-eq-{s}-total"], d[f"d-eq-{s}-annuite"] + d[f"d-eq-{s}-maint"]
                                       + REF.valeur("Equipement", eq, "mo_eur_ha", {}, 0.0), msg=eq)

    def test_equipement_deja_amorti(self):
        neuf = simuler(REF, entrees(), {}, AGRO)
        amorti_eq = simuler(REF, entrees(deja_amorti_equipement=True), {}, AGRO)
        cout = lambda r: dict((p["cle"], p["montant"]) for p in r["couts"]["postes"])["equipement"]  # noqa: E731
        # Le poste « équipement » disparaît entièrement du bilan et de la décomposition (ni annuité, ni maintenance)
        self.assertGreater(cout(neuf), 0.0)
        self.assertEqual(cout(amorti_eq), 0.0)
        self.assertEqual(amorti_eq["capex"]["equipement"], 0.0)
        self.assertEqual(amorti_eq["bilan"]["total"], amorti_eq["gain"]["total"] - amorti_eq["couts"]["total"])
        # Les valeurs théoriques (annuité, maintenance) restent disponibles pour la légende, non zérotées
        self.assertGreater(amorti_eq["annualisation"]["equipement"]["annuite"], 0.0)
        self.assertGreater(amorti_eq["annualisation"]["equipement"]["maintenance"], 0.0)
        # Cumulé avec l'accès déjà amorti, on isole le coût de l'eau sans aucun CAPEX ni coût d'équipement
        sans_capex = simuler(REF, entrees(deja_amorti=True, deja_amorti_equipement=True), {}, AGRO)
        self.assertEqual(sans_capex["capex"]["total"], 0.0)
        self.assertEqual(cout(sans_capex), 0.0)
        self.assertGreater(sans_capex["couts"]["total"], 0.0)

    def test_subvention_saisie_dans_la_simulation(self):
        """Les taux saisis sous « Subvention publique » priment, y compris sur le taux propre au forage."""
        cout = lambda r: r["couts"]["total"]  # noqa: E731
        for source in ("Forage individuel", "Retenue collinaire"):
            r0 = simuler(REF, entrees(source=source, subvention_acces_pct=0), {}, AGRO)
            r50 = simuler(REF, entrees(source=source, subvention_acces_pct=50), {}, AGRO)
            self.assertAlmostEqual(r50["annualisation"]["acces"]["subvention"], 0.5, msg=source)
            self.assertLess(cout(r50), cout(r0), source)
            self.assertAlmostEqual(r50["bilan"]["total"], r50["gain"]["total"] - cout(r50))
        m0 = simuler(REF, entrees(subvention_equipement_pct=0), {}, AGRO)
        m100 = simuler(REF, entrees(subvention_equipement_pct=100), {}, AGRO)
        self.assertAlmostEqual(m100["annualisation"]["equipement"]["subvention"], 1.0)  # pas de plafond caché
        self.assertLess(cout(m100), cout(m0))
        self.assertAlmostEqual(m100["capex"]["equipement_net"], 0.0)
        # Sans saisie : taux du référentiel (45 % pour le forage)
        self.assertAlmostEqual(simuler(REF, entrees(), {}, AGRO)["annualisation"]["acces"]["subvention"], 0.45)

    def test_subvention_par_defaut_selon_la_source(self):
        forage = simuler(REF, entrees(source="Forage individuel"), {}, AGRO)
        retenue = simuler(REF, entrees(source="Retenue collinaire"), {}, AGRO)
        self.assertAlmostEqual(forage["annualisation"]["acces"]["subvention"], 0.45)
        self.assertAlmostEqual(retenue["annualisation"]["acces"]["subvention"], 0.7)

    def test_redevance_categorie_et_seuil(self):
        hors = simuler(REF, entrees(zre=False, agence="Loire-Bretagne"), {}, AGRO)
        zre = simuler(REF, entrees(zre=True, agence="Loire-Bretagne"), {}, AGRO)
        self.assertGreater(zre["redevance"]["taux_c_m3"], hors["redevance"]["taux_c_m3"])
        self.assertEqual(zre["redevance"]["categorie"], 2)
        # Sous le seuil d'assujettissement, la redevance n'est pas due
        petit = simuler(REF, entrees(surface=1.0), {}, AGRO)
        self.assertFalse(petit["redevance"]["due"])
        self.assertEqual(dict((p["cle"], p["montant"]) for p in petit["couts"]["postes"])["redevance"], 0.0)
        # Le forage est facturé au taux des eaux souterraines
        self.assertEqual(hors["redevance"]["origine"], "souterraine")
        self.assertEqual(simuler(REF, entrees(source="Retenue collinaire"), {}, AGRO)["redevance"]["origine"],
                         "superficielle")

    def test_redevance_retenue_collinaire_categorie_1(self):
        """Art. L213-10-9 : retenue collinaire taxée au tarif de catégorie 1, même en ZRE, pour toutes les agences."""
        for agence in REF.agences:
            zre = simuler(REF, entrees(source="Retenue collinaire", zre=True, agence=agence), {}, AGRO)
            self.assertEqual(zre["redevance"]["categorie"], 1, agence)
            self.assertEqual(zre["redevance"]["taux_c_m3"],
                             REF.valeur("Ressources", agence, "cat1_superficielle"), agence)
            self.assertEqual(zre["redevance"]["regle_retenue"], "collinaire")
        # Le forage en ZRE reste en catégorie 2
        self.assertEqual(simuler(REF, entrees(zre=True, agence="Loire-Bretagne"), {}, AGRO)["redevance"]["categorie"], 2)

    def test_retenue_collective(self):
        seul = simuler(REF, entrees(source="Retenue collinaire"), {}, AGRO)
        partage = simuler(REF, entrees(source="Retenue collinaire", type_retenue="collective",
                                       nb_adherents=10), {}, AGRO)
        # La retenue collective est dimensionnée pour dix exploitations, la quote-part est celle d'une seule
        self.assertAlmostEqual(partage["dimensionnement"]["capacite"], 10 * seul["dimensionnement"]["capacite"],
                               delta=10000)
        self.assertAlmostEqual(partage["capex"]["acces_brut"], seul["capex"]["acces_brut"], delta=10000)
        self.assertTrue(partage["dimensionnement"]["collectif"])

    def test_energie_sous_pression(self):
        """Sur un réseau sous pression, l'énergie n'est pas facturée séparément (comprise dans la part volumétrique)."""
        reseau = simuler(REF, entrees(source="ASA"), {}, AGRO)
        forage = simuler(REF, entrees(source="Forage individuel"), {}, AGRO)
        self.assertTrue(reseau["energie"]["pression_fournie"])
        couts_reseau = dict((p["cle"], p["montant"]) for p in reseau["couts"]["postes"])
        couts_forage = dict((p["cle"], p["montant"]) for p in forage["couts"]["postes"])
        self.assertEqual(couts_reseau["energie"], 0.0)
        self.assertGreater(couts_forage["energie"], 0.0)

    def test_energie_des_retenues(self):
        """Collinaire : seule la reprise vers la parcelle est pompée ; par pompage : remplissage hivernal en plus."""
        collinaire = simuler(REF, entrees(source="Retenue collinaire"), {}, AGRO)
        pompage = simuler(REF, entrees(source="Retenue par pompage"), {}, AGRO)
        v = collinaire["agro"]["volume_preleve"]
        self.assertAlmostEqual(collinaire["energie"]["volume_facture"], v)
        self.assertEqual(collinaire["energie"]["volume_remplissage"], 0.0)
        part = REF.valeur("Acces_ressource", "Retenue par pompage", "part_remplissage_pompe")
        self.assertGreater(part, 0.0)
        self.assertAlmostEqual(pompage["energie"]["volume_facture"], v * (1 + part))

    def test_redevance_incluse_dans_le_tarif_asa(self):
        asa = simuler(REF, entrees(source="ASA", agence="Loire-Bretagne"), {}, AGRO)
        forage = simuler(REF, entrees(source="Forage individuel", agence="Loire-Bretagne"), {}, AGRO)
        self.assertTrue(asa["redevance"]["incluse"])
        self.assertEqual(dict((p["cle"], p["montant"]) for p in asa["couts"]["postes"])["redevance"], 0.0)
        self.assertGreater(dict((p["cle"], p["montant"]) for p in forage["couts"]["postes"])["redevance"], 0.0)
        # Eau livrée sous pression en bord de parcelle : ni énergie, ni réseau d'amenée par défaut
        self.assertEqual(asa["energie"]["volume_facture"], 0.0)
        self.assertEqual(asa["annualisation"]["acces"]["capex_reseau_net"], 0.0)

    def test_forage_deux_durees_de_vie(self):
        """Forage (40 ans) et station de pompage (20 ans) sont amortis séparément (CDAF, 2025)."""
        e = entrees(source="Forage individuel")
        cle_d = "Acces_ressource|Général|distance_amenee"
        r = simuler(REF, e, {cle_d: 0}, AGRO)
        an = r["annualisation"]["acces"]
        pompe = REF.valeur("Acces_ressource", "Forage individuel", "pompe_abri")
        s = an["subvention"]
        attendu = ((an["capex_brut"] - pompe) * an["facteur_ouvrage"] + pompe * an["facteur_pompe"]) * (1 - s)
        self.assertAlmostEqual(an["annuite"], attendu)
        self.assertAlmostEqual(an["facteur_pompe"], facteur_annualisation(an["taux"], 20))
        self.assertAlmostEqual(an["facteur_ouvrage"], facteur_annualisation(an["taux"], 40))
        self.assertAlmostEqual(an["capex_brut"], 87500)

    def test_distance_amenee_commune(self):
        cle = "Acces_ressource|Général|distance_amenee"
        pres = simuler(REF, entrees(), {cle: 100}, AGRO)
        loin = simuler(REF, entrees(), {cle: 1000}, AGRO)
        cout_ml = REF.valeur("Acces_ressource", "Général", "cout_tuyau_ml")
        self.assertAlmostEqual(loin["capex"]["acces_brut"] - pres["capex"]["acces_brut"], 900 * cout_ml)

    def test_couleurs_imposees(self):
        couleurs = dict((c, col) for c, _, col in POSTES)
        self.assertEqual(couleurs["energie"], "#6A3D9A")      # violet
        self.assertEqual(couleurs["redevance"], "#1F5FAD")    # bleu
        self.assertEqual(couleurs["equipement"], "#E4794A")   # orange
        self.assertEqual(couleurs["main_oeuvre"], "#D6589A")  # rose
        self.assertEqual(couleurs["acces"], "#E9C229")        # jaune

    def test_valeurs_derivees(self):
        d = valeurs_derivees(REF, {}, {"equipement": "Pivot"})
        for eq in REF.equipements:
            for suffixe in ("maint", "taux", "annuite"):
                self.assertIn(f"d-eq-{slug(eq)}-{suffixe}", d)
        for src in REF.sources:
            self.assertIn(f"d-acc-{slug(src)}-taux", d)
        self.assertIn("d-res-capex", d)
        self.assertIn("d-forage-total", d)
        self.assertGreater(d["d-forage-total"], 0)


class TestCharges(unittest.TestCase):
    def test_charges_fixes_variables_et_sans_subvention(self):
        for source in REF.sources:
            r = simuler(REF, entrees(source=source), {}, AGRO)
            c = r["couts"]
            self.assertAlmostEqual(c["fixes"] + c["variables"], c["total"], places=6, msg=source)
            self.assertGreaterEqual(c["sans_subvention"]["total"], c["total"] - 1e-9, source)
            self.assertAlmostEqual(c["sans_subvention"]["total"] - c["total"], c["aide_publique_annuelle"], places=6)
            self.assertAlmostEqual(r["bilan"]["sans_subvention"]["total"],
                                   r["gain"]["total"] - c["sans_subvention"]["total"], places=6)
        # Sans subvention saisie, les deux coûts sont égaux
        r = simuler(REF, entrees(subvention_equipement_pct=0, subvention_acces_pct=0), {}, AGRO)
        self.assertAlmostEqual(r["couts"]["sans_subvention"]["total"], r["couts"]["total"], places=6)
        # Capital déjà amorti : plus d'annuité, donc plus d'aide publique annuelle
        r = simuler(REF, entrees(deja_amorti=True, deja_amorti_equipement=True), {}, AGRO)
        self.assertAlmostEqual(r["couts"]["aide_publique_annuelle"], 0.0, places=6)

    def test_taux_de_couverture(self):
        plein = simuler(REF, entrees(), {}, AGRO)
        moitie = simuler(REF, entrees(taux_couverture=50), {}, AGRO)
        self.assertAlmostEqual(moitie["agro"]["volume_preleve"], plein["agro"]["volume_preleve"] / 2, places=6)
        self.assertAlmostEqual(moitie["agro"]["delta_rdt"], plein["agro"]["delta_rdt"] / 2, places=6)
        self.assertLess(moitie["couts"]["variables"], plein["couts"]["variables"])

    def test_saisie_libre(self):
        fige = REF.param("Equipement", "Pivot", "capex_unitaire")
        self.assertFalse(fige.variable)
        s = {fige.cle: fige.valeur * 2}
        self.assertEqual(REF.valeur("Equipement", "Pivot", "capex_unitaire", s), fige.valeur)
        s[CLE_LIBRE] = True
        self.assertEqual(REF.valeur("Equipement", "Pivot", "capex_unitaire", s), fige.valeur * 2)



class TestRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as application
        application.app.config["TESTING"] = True
        cls.client = application.app.test_client()

    def test_pages(self):
        for url in ("/", "/parcelle", "/exemples", "/exemples?exemple=2", "/exemples?onglet=exemples",
                    "/trajectoires", "/references", "/references?onglet=methode",
                    "/projet", "/projet?exemple=1"):
            r = self.client.get(url, follow_redirects=True)
            self.assertEqual(r.status_code, 200, url)
            self.assertIn("Analyse financière", r.data.decode("utf-8"), url)

    def test_mode_exploitation_supprime(self):
        r = self.client.get("/exploitation")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/parcelle"))
        self.assertEqual(self.client.post("/api/exploitation", json={}).status_code, 404)
        self.assertNotIn("Mode exploitation", self.client.get("/parcelle").data.decode("utf-8"))

    def test_rapport_pdf_et_classeur_des_variables(self):
        import io
        corps = {"entrees": entrees(), "libre": True,
                 "surcharges": {"Equipement|Pivot|capex_unitaire": 91000.0,
                                "Acces_ressource|Général|taux_remplissage": 0.9}}
        r = self.client.post("/api/rapport-pdf", json=corps)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:5], b"%PDF-")
        r = self.client.post("/api/variables-excel", json=corps)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:2], b"PK")
        r = self.client.post("/api/variables-import", data={"fichier": (io.BytesIO(r.data), "variables.xlsx")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertAlmostEqual(d["surcharges"]["Equipement|Pivot|capex_unitaire"], 91000.0)
        self.assertAlmostEqual(d["surcharges"]["Acces_ressource|Général|taux_remplissage"], 0.9)
        self.assertEqual(d["entrees"]["culture"], "Maïs")
        self.assertEqual(self.client.post("/api/variables-import").status_code, 400)

    def test_saisie_libre_par_l_api(self):
        e = entrees(methode_besoin="reference")
        cle = "Equipement|Pivot|capex_unitaire"
        base = self.client.post("/api/simulation", json={"entrees": e}).get_json()
        fige = self.client.post("/api/simulation", json={"entrees": e, "surcharges": {cle: 1.0}}).get_json()
        libre = self.client.post("/api/simulation", json={"entrees": e, "surcharges": {cle: 1.0}, "libre": True}).get_json()
        self.assertAlmostEqual(fige["capex"]["equipement"], base["capex"]["equipement"])
        self.assertAlmostEqual(libre["capex"]["equipement"], 1.0)
        # Rendement saisi : prime sur la carte et le référentiel
        r = self.client.post("/api/simulation", json={"entrees": e, "libre": True,
                                                      "surcharges": {"Cultures|Maïs|rdt_irrigue": 150.0}}).get_json()
        self.assertEqual(r["agro"]["rdt_irrigue"], 150.0)
        self.assertEqual(r["agro"]["origine"], "saisie")

    def test_saisies_directes_du_cas_personnel(self):
        """Réserve utile et redevance saisies : remplacent la valeur calculée, rendue comme valeur par défaut."""
        commune = {"code": "40192", "nom": "Mont-de-Marsan", "departement": "40", "centre": [-0.5, 43.89],
                   "contour": None}
        e = entrees(methode_besoin="sgpe", agence="Adour-Garonne")
        base = self.client.post("/api/simulation", json={"entrees": e, "commune": commune, "libre": True}).get_json()
        saisi = self.client.post("/api/simulation", json={
            "entrees": dict(e, ru_mm=250, redevance_c_m3=5), "commune": commune, "libre": True,
            "surcharges": {"Cultures|Maïs|besoin_irrigation": 123.0}}).get_json()
        self.assertEqual(saisi["agro"]["sol"]["ru"], 250)
        self.assertEqual(saisi["agro"]["sol"]["origine"], "saisie")
        self.assertAlmostEqual(saisi["agro"]["sol"]["ru_defaut"], base["agro"]["sol"]["ru_defaut"])
        self.assertEqual(saisi["redevance"]["taux_c_m3"], 5)
        self.assertEqual(saisi["redevance"]["taux_defaut"], base["redevance"]["taux_c_m3"])
        self.assertEqual(saisi["agro"]["besoin_mm"], 123.0)
        self.assertEqual(saisi["agro"]["methode_besoin"], "saisie")
        self.assertIn("besoin_mm", saisi["agro"]["defauts"])

    def test_diagnostic_du_territoire(self):
        """Indicateurs de la commune (territoire/indicateurs_communes.csv) : agence du bassin, ZRE, quatre fiches,
        types d'accès du référentiel classés ; commune inconnue : diagnostic indisponible, sans erreur."""
        if not os.path.exists(config.TERRITOIRE):
            self.skipTest("territoire/indicateurs_communes.csv absent (outils/preparer_territoire.py)")
        t = self.client.get("/api/territoire/45252").get_json()  # Pithiviers : Beauce, ZRE souterraine
        self.assertTrue(t["disponible"])
        self.assertIn(t["agence"], REF.agences)
        self.assertGreaterEqual(t["zre"]["sout"], t["zre"]["seuil"])
        commune = {"code": "45252", "nom": "Pithiviers", "departement": "45", "centre": [2.25, 48.17], "contour": None}
        r = self.client.post("/api/simulation", json={"entrees": entrees(), "commune": commune}).get_json()
        d = r["territoire"]
        self.assertEqual([f["id"] for f in d["fiches"]], ["tension", "usages", "sol", "projections", "acces"])
        projections = {x["libelle"]: x["valeur"] for x in d["fiches"][3]["indicateurs"]}
        self.assertIn("Débit d'étiage (QMNA)", projections)  # station Explore2 de l'Œuf, à 2 km
        self.assertTrue(any(k.startswith("Besoin en eau") for k in projections))  # SGPE, trois horizons
        self.assertEqual(projections["Débit d'étiage (QMNA)"].count("→"), 2)
        self.assertTrue(projections["Recharge des nappes"].endswith("% (+2 → +2,7 → +4 °C)"))  # craie et Beauce
        acces = d["fiches"][-1]
        self.assertEqual({o["source"] for o in acces["options"]}, set(REF.sources))
        self.assertEqual(sum(o["retenue"] for o in acces["options"]), 1)
        for f in d["fiches"]:
            for x in f["indicateurs"]:
                self.assertIn(x["niveau"], ("favorable", "vigilance", "defavorable", "info"), x["libelle"])
                self.assertTrue(x["bulle"], x["libelle"])
        self.assertFalse(self.client.get("/api/territoire/00000").get_json()["disponible"])
        r = self.client.post("/api/simulation", json={"entrees": entrees()}).get_json()
        self.assertFalse(r["territoire"]["disponible"])

    def test_rendement_sgpe_et_profondeur_de_sol(self):
        """Rendement pluvial SGPE = Ym × (1 − Ky (1 − ETa/ETc)) ; profondeur de sol de la carte ou saisie."""
        commune = {"code": "40192", "nom": "Mont-de-Marsan", "departement": "40", "centre": [-0.5, 43.89],
                   "contour": None}
        e = entrees(methode_besoin="sgpe", methode_rendement="sgpe")
        r = self.client.post("/api/simulation", json={"entrees": e, "commune": commune, "libre": True}).get_json()
        a = r["agro"]
        self.assertEqual(a["origine"], "sgpe")
        self.assertTrue(a["methodes_rendement"]["sgpe"])
        self.assertEqual(a["rdt_irrigue"], REF.valeur("Cultures", "Maïs", "rdt_irrigue"))
        self.assertAlmostEqual(a["rdt_pluvial"], a["rdt_irrigue"] * a["sgpe"]["rendement_relatif_sec"], places=6)
        self.assertLess(a["rdt_pluvial"], a["rdt_irrigue"])
        superficiel = self.client.post("/api/simulation", json={
            "entrees": dict(e, profondeur_sol_m=0.5), "commune": commune, "libre": True}).get_json()
        self.assertEqual(superficiel["agro"]["sol"]["profondeur"], 0.5)
        self.assertEqual(superficiel["agro"]["sol"]["profondeur_defaut"], a["sol"]["profondeur_defaut"])

    def test_choix_automatique_et_autres_methodes(self):
        """Besoin : SGPE en priorité ; rendements : MAELIA sinon référentiel ; autres valeurs pour le bouton « i »."""
        commune = {"code": "40192", "nom": "Mont-de-Marsan", "departement": "40", "centre": [-0.5, 43.89],
                   "contour": None}
        r = self.client.post("/api/simulation", json={"entrees": entrees(methode_besoin="auto"),
                                                      "commune": commune}).get_json()
        a = r["agro"]
        self.assertEqual(a["sources"]["besoin_mm"], "sgpe")
        self.assertIn(a["sources"]["rdt_pluvial"], ("carte", "reference"))
        for champ in ("besoin_mm", "rdt_irrigue", "rdt_pluvial"):
            retenues = [x for x in a["alternatives"][champ] if x["retenue"]]
            self.assertEqual(len(retenues), 1, champ)
            self.assertAlmostEqual(retenues[0]["valeur"], a["besoin_mm" if champ == "besoin_mm" else champ])
        self.assertIn("reference", [x["code"] for x in a["alternatives"]["besoin_mm"]])
        # Sans commune : SGPE impossible, repli sur le référentiel
        r = self.client.post("/api/simulation", json={"entrees": entrees(methode_besoin="auto")}).get_json()
        self.assertEqual(r["agro"]["sources"]["besoin_mm"], "reference")
        # Besoin hors de la plage plausible : avertissement
        r = self.client.post("/api/simulation", json={"entrees": entrees(), "libre": True,
                                                      "surcharges": {"Cultures|Maïs|besoin_irrigation": 600}}).get_json()
        self.assertTrue(any("Besoin en eau élevé" in w["texte"] for w in r["avertissements"]))

    def test_methodologie(self):
        r = self.client.get("/api/methodologie-pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:5], b"%PDF-")
        page = self.client.get("/references?onglet=methode").data.decode("utf-8")
        self.assertIn("Télécharger la méthodologie", page)
        self.assertIn("methodologie-pdf", page)
        self.assertNotIn("tab-validation", page)
        # L'ancienne adresse de l'onglet Validation ouvre la méthodologie
        page = self.client.get("/references?onglet=validation").data.decode("utf-8")
        self.assertIn('id="tab-methode" class="fr-tabs__tab fr-icon-file-text-line fr-tabs__tab--icon-left" tabindex="0"', page)

    def test_404(self):
        self.assertEqual(self.client.get("/inexistant").status_code, 404)
        self.assertEqual(self.client.get("/api/inexistant").status_code, 404)

    def test_api_simulation(self):
        corps = {"entrees": entrees(), "surcharges": {},
                 "commune": {"code": "40036", "nom": "Benquet", "departement": "40",
                             "centre": [-0.53, 43.83], "contour": None}}
        r = self.client.post("/api/simulation", json=corps)
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        for cle in ("agro", "couts", "capex", "gain", "bilan", "seuil", "derives", "annualisation"):
            self.assertIn(cle, d)
        self.assertEqual(len(d["couts"]["postes"]), len(POSTES))

    def test_api_simulation_entrees_invalides(self):
        r = self.client.post("/api/simulation", json={"entrees": {"culture": "Quinoa des Andes",
                                                                  "surface": "trente"}})
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.get_json()["entrees"]["culture"], REF.cultures)

    def test_api_departement(self):
        self.assertEqual(self.client.get("/api/departement/40").get_json()["agence"], "Adour-Garonne")
        self.assertEqual(self.client.get("/api/departement/999").get_json(), {})

    def test_api_carte_variable(self):
        import base64
        # Culture sans carte (ou inconnue) : réponse « indisponible », jamais d'erreur HTTP
        r = self.client.get("/api/carte-variable/Quinoa des Andes/besoin")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["disponible"])
        cat = cartes.catalogue(REF, config.DOSSIER_CARTES)
        cultures_completes = [c for c, i in cat.items() if i["complet"]]
        if not cultures_completes:
            self.skipTest("aucune culture avec carte complète sur ce poste")
        for variable in ("rdt_irrigue", "rdt_pluvial", "besoin"):
            r = self.client.get("/api/carte-variable/" + cultures_completes[0] + "/" + variable)
            self.assertEqual(r.status_code, 200)
            d = r.get_json()
            if not d["disponible"]:
                self.skipTest("lecture des cartes indisponible sur ce poste (rasterio)")
            for cle in ("png_base64", "bounds", "min", "max", "unite", "couleur_basse", "couleur_haute"):
                self.assertIn(cle, d)
            png = base64.b64decode(d["png_base64"])
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            (sud, ouest), (nord, est) = d["bounds"]
            self.assertLess(sud, nord)
            self.assertLess(ouest, est)


if __name__ == "__main__":
    unittest.main(verbosity=2)
