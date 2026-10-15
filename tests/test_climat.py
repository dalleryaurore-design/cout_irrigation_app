# -*- coding: utf-8 -*-
"""Le cache climatique suit le contenu du classeur, pas sa date de modification."""

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
