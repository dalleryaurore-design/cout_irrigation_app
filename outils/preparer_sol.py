# -*- coding: utf-8 -*-
"""
Carte de réserve utile allégée
==============================
La carte AWCr_mm_0_200.tif (réserve utile en eau des sols de France sur 0-200 cm, mm,
maille de 90 m, Lambert-93) pèse 640 Mo : trop pour être déployée avec l'application.
Ce script la ramène à la maille de 1 km environ (moyenne des pixels valides de chaque bloc
de FACTEUR × FACTEUR pixels) dans ``sol/ru_sol_1km.tif`` (quelques Mo).

    python outils/preparer_sol.py [source.tif] [destination.tif]

À relancer si la carte source change. La valeur communale lue par l'application est ensuite
la moyenne des mailles de 1 km qui touchent la commune : la perte de résolution est sans effet
à cette échelle.
"""

from __future__ import annotations

import os
import sys
import warnings

import numpy as np

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(RACINE, "AWCr_mm_0_200.tif")
DESTINATION = os.path.join(RACINE, "sol", "ru_sol_1km.tif")
FACTEUR = 11          # 11 × 90 m ≈ 1 km
LIGNES_PAR_LOT = 40   # lignes de sortie traitées à la fois (≈ 50 Mo lus)
NODATA = -9999.0


def reduire(source: str = SOURCE, destination: str = DESTINATION, facteur: int = FACTEUR) -> str:
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(source) as src:
        h, l = src.height, src.width
        nl, nc = -(-h // facteur), -(-l // facteur)
        sortie = np.full((nl, nc), np.nan, dtype="float32")
        for i0 in range(0, nl, LIGNES_PAR_LOT):
            i1 = min(nl, i0 + LIGNES_PAR_LOT)
            r0, r1 = i0 * facteur, min(h, i1 * facteur)
            bloc = src.read(1, window=Window(0, r0, l, r1 - r0)).astype("float64")
            invalide = ~np.isfinite(bloc) | (bloc < 0) | (bloc > 1000)
            if src.nodata is not None:
                invalide |= bloc == src.nodata
            bloc[invalide] = np.nan
            plein = np.full(((i1 - i0) * facteur, nc * facteur), np.nan)
            plein[:bloc.shape[0], :bloc.shape[1]] = bloc
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)  # blocs entièrement vides
                sortie[i0:i1] = np.nanmean(plein.reshape(i1 - i0, facteur, nc, facteur), axis=(1, 3))
            print(f"\r{i1}/{nl} lignes", end="", flush=True)
        profil = {"driver": "GTiff", "height": nl, "width": nc, "count": 1, "dtype": "float32",
                  "crs": src.crs, "transform": src.transform * src.transform.scale(facteur, facteur),
                  "nodata": NODATA, "compress": "deflate", "predictor": 3, "tiled": True,
                  "blockxsize": 256, "blockysize": 256}
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    with rasterio.open(destination, "w", **profil) as dst:
        dst.write(np.where(np.isfinite(sortie), sortie, NODATA).astype("float32"), 1)
        dst.update_tags(1, UNITS="mm", SOURCE=os.path.basename(source),
                        DESCRIPTION="Réserve utile en eau du sol 0-200 cm, moyenne à la maille de 1 km")
    print(f"\n{destination} : {os.path.getsize(destination) / 1e6:.1f} Mo")
    return destination


if __name__ == "__main__":
    reduire(*(sys.argv[1:3]))
