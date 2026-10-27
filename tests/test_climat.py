# -*- coding: utf-8 -*-
"""Le cache climatique suit le contenu du classeur, pas sa date de modification ; bilan hydrique SGPE."""

import os
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from moteur import climat  # noqa: E402


def _classeur(chemin, etp):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append([f"pt1;48.5;2.3;x;H1;1;40;{etp}"])
    wb.save(chemin)


class TestCacheClimat(unittest.TestCase):
    def setUp(self):
        self._sauve = dict(climat._donnees)
        self._tmp = tempfile.TemporaryDirectory()
        self.chemin = os.path.join(self._tmp.name, "climate_data.xlsx")
        _classeur(self.chemin, 80)
        self.lectures = 0
        self._reel = climat._lire_classeur

        def compte(chemin):
            self.lectures += 1
            return self._reel(chemin)

        climat._lire_classeur = compte

    def tearDown(self):
        climat._lire_classeur = self._reel
        with climat._verrou:
            climat._donnees.clear()
            climat._donnees.update(self._sauve)
        self._tmp.cleanup()

    def _oublier_memoire(self):
        with climat._verrou:
            climat._donnees.clear()

    def test_mtime_ne_relit_pas_le_classeur(self):
        climat._charger(self.chemin)
        self.assertEqual(self.lectures, 1)
        plus_tard = os.path.getmtime(self.chemin) + 3600
        os.utime(self.chemin, (plus_tard, plus_tard))
        self._oublier_memoire()
        d = climat._charger(self.chemin)
        self.assertEqual(self.lectures, 1)
        self.assertEqual(len(d["coords"]), 1)

    def test_contenu_modifie_relit_le_classeur(self):
        climat._charger(self.chemin)
        _classeur(self.chemin, 120)
        self._oublier_memoire()
        d = climat._charger(self.chemin)
        self.assertEqual(self.lectures, 2)
        self.assertEqual(float(d["etp"][0, 0, 0]), 120.0)


class TestBilanHydrique(unittest.TestCase):
    """Bilan hydrique journalier de la méthode SGPE (type CROPWAT)."""
    KC_MAIS = [0, 0, 0, 0, 0.4, 0.9, 1.2, 1.05, 0.8, 0, 0, 0]
    ETP = [10, 20, 45, 70, 100, 130, 150, 130, 85, 45, 15, 10]
    PLUIE = [90, 75, 70, 70, 70, 50, 40, 45, 65, 85, 95, 95]

    def bilan(self, ru=100.0, **kw):
        prm = dict(profondeur_sol=2.0, zr_max=1.2, zr_ini=0.25, p_fao=0.55, epuisement_initial=0.0)
        prm.update(kw)
        return climat.bilan_hydrique(self.KC_MAIS, self.ETP, self.PLUIE, ru, **prm)

    def test_pluie_efficace_usda(self):
        self.assertAlmostEqual(climat.pluie_efficace(100), 100 * (125 - 20) / 125)
        self.assertAlmostEqual(climat.pluie_efficace(300), 155)
        self.assertEqual(climat.pluie_efficace(0), 0)

    def test_besoin_borne_par_le_deficit_climatique(self):
        b = self.bilan()
        deficit = sum(max(0.0, e * k - climat.pluie_efficace(p)) for e, k, p in zip(self.ETP, self.KC_MAIS, self.PLUIE))
        self.assertGreater(b["valeur"], 0)
        self.assertLessEqual(b["valeur"], deficit + 1e-6)
        self.assertGreater(b["n_apports"], 0)
        self.assertEqual(b["mois_saison"], [4, 5, 6, 7, 8])

    def test_reserve_utile_et_etat_initial(self):
        # Plus de réserve utile : moins d'irrigation ; sol sec au semis : plus d'irrigation
        self.assertLess(self.bilan(ru=250)["valeur"], self.bilan(ru=60)["valeur"])
        self.assertGreater(self.bilan(epuisement_initial=0.8)["valeur"], self.bilan()["valeur"])
        # Sol superficiel : la même réserve, concentrée, est plus accessible aux racines
        self.assertLess(self.bilan(profondeur_sol=0.8)["valeur"], self.bilan(profondeur_sol=2.0)["valeur"])

    def test_culture_d_hiver_et_perenne(self):
        kc_ble = [0.4, 0.5, 0.75, 0.95, 1.15, 1.0, 0.25, 0, 0, 0.4, 0.4, 0.4]
        b = climat.bilan_hydrique(kc_ble, self.ETP, self.PLUIE, 100, 2.0, 1.5, 0.25, 0.55, 0.0)
        self.assertEqual(b["mois_saison"][0], 9)   # semis en octobre
        vigne = climat.bilan_hydrique([0.3] * 3 + [0.5, 0.7, 0.8, 0.85, 0.8, 0.6] + [0.3] * 3, self.ETP, self.PLUIE,
                                      100, 2.0, 1.5, 0.25, 0.45, 0.0)
        self.assertTrue(vigne["perenne"])
        self.assertGreater(vigne["valeur"], 0)   # les pluies d'automne ne compensent pas le déficit d'été
