# -*- coding: utf-8 -*-
"""
Indicateurs territoriaux par commune (diagnostic du territoire)
===============================================================
Calcule, pour chaque commune de France métropolitaine, les indicateurs du « Diagnostic du
territoire » de la simulation (``moteur/territoire.py``) et les écrit dans
``territoire/indicateurs_communes.csv`` (une ligne par code INSEE, quelques Mo, déployé avec
l'application). Les données brutes, volumineuses, restent dans ``territoire/brut/`` (non déployé) :

=========================================  =====================================================
Fichier (territoire/brut/)                 Contenu, producteur
=========================================  =====================================================
communes-100m-2025.geojson.gz              contours des communes 2025 (Etalab, IGN Admin Express)
CircAdminBassin_2025.gpkg/                 circonscriptions des agences de l'eau (Sandre)
ZRE.gpkg/                                  zones de répartition des eaux (Sandre)
Sage.gpkg/                                 périmètres des SAGE (Sandre)
historique-communes.zip                    restrictions sécheresse journalières par commune
                                           depuis 2010 (VigiEau, data.gouv.fr)
sau_irriguee_ra_2020_commune.xlsx          part de la SAU irriguée en 2020 (Agreste, RA 2020)
BD_Topage_FXX_2026-shp/                    tronçons hydrographiques BD TOPAGE 2026 (IGN, OFB)
EntiteHydroGeol_FXX.gpkg/                  entités hydrogéologiques BDLISA niveau 3 (BRGM)
ObstEcoul_all.gpkg/                        référentiel des obstacles à l'écoulement, ROE (OFB)
explore2/                                  Explore2, indicateurs des changements par horizon,
                                           RCP4.5, réf. 1976-2005 : <modèle>_basses_eaux.tar.gz et
                                           <modèle>_moyennes_eaux.tar.gz des 9 modèles hydrologiques,
                                           stations_Explore2.tab, code_Chain_outliers_Explore2.tab
                                           (Recherche Data Gouv, dataverse Explore2)
recharge/RECH_year_TRACC_RWL.zip           Explore2, recharge potentielle annuelle des nappes
                                           par masse d'eau souterraine, 1976-2005 et niveaux de
                                           réchauffement TRACC (doi:10.57745/3PUZVT)
=========================================  =====================================================

    python outils/preparer_territoire.py               toutes les étapes
    python outils/preparer_territoire.py restrictions  une ou plusieurs étapes, puis l'assemblage
    python outils/preparer_territoire.py assembler     l'assemblage seul

Chaque étape écrit son résultat intermédiaire dans ``territoire/brut/_etapes/`` : l'assemblage
reprend les étapes déjà calculées. La lecture des restrictions (fichier JSON de 12 Go) dure
plusieurs minutes ; les autres étapes, une à deux minutes chacune.

Dépendances (préparation seulement, inutiles à l'application) : geopandas, pyogrio, pandas.
"""

from __future__ import annotations

import os
import re
import sys
import time
import zipfile

import numpy as np
import pandas as pd

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRUT = os.path.join(RACINE, "territoire", "brut")
ETAPES = os.path.join(BRUT, "_etapes")
DESTINATION = os.path.join(RACINE, "territoire", "indicateurs_communes.csv")
L93 = "EPSG:2154"
OUTRE_MER = ("97", "98")  # codes INSEE hors métropole : sources (BD TOPAGE, BDLISA…) limitées à la métropole

COMMUNES = os.path.join(BRUT, "communes-100m-2025.geojson.gz")
BASSINS = os.path.join(BRUT, "CircAdminBassin_2025.gpkg", "CircAdminBassin_2025.gpkg")
ZRE = os.path.join(BRUT, "ZRE.gpkg", "ZRE.gpkg")
SAGE = os.path.join(BRUT, "Sage.gpkg", "Sage.gpkg")
RESTRICTIONS = os.path.join(BRUT, "historique-communes.zip")
SAU = os.path.join(BRUT, "sau_irriguee_ra_2020_commune.xlsx")
TOPAGE = os.path.join(BRUT, "BD_Topage_FXX_2026-shp", "TronconHydrographique_FXX-shp.zip")
BDLISA = os.path.join(BRUT, "EntiteHydroGeol_FXX.gpkg", "EntiteHydroGeol_FXX.gpkg")
ROE = os.path.join(BRUT, "ObstEcoul_all.gpkg", "ObstEcoul_all.gpkg")

# Restrictions : moyenne sur les dix dernières années complètes de l'historique
ANNEES_RESTRICTIONS = range(2016, 2026)
NIVEAUX = ("vigilance", "alerte", "alerte_renforcee", "crise")

# Circonscriptions administratives de bassin (Sandre) -> agences du référentiel (feuille Ressources)
AGENCES = {"01": "Artois-Picardie", "02": "Rhin-Meuse", "03": "Seine-Normandie", "04": "Loire-Bretagne",
           "05": "Adour-Garonne", "06": "Rhône-Méditerranée-Corse", "12": "Rhône-Méditerranée-Corse"}

# Explore2 : indicateurs de changement retenus (archives basses_eaux et moyennes_eaux de chaque modèle
# hydrologique) et distance maximale entre la commune et la station de simulation
EXPLORE2 = os.path.join(BRUT, "explore2")
INDICATEURS_EXPLORE2 = {"qmna": "delta-QMNA_yr", "ete": "delta-QS_JJA", "hiver": "delta-QS_DJF"}
DISTANCE_MAX_STATION = 30000  # m

# Explore2, recharge potentielle des nappes par masse d'eau souterraine : niveaux de réchauffement de la TRACC
# (fenêtre du fichier -> suffixe des colonnes) ; les autres champs de la couche ne sont pas des projections
RECHARGE = os.path.join(BRUT, "recharge", "RECH_year_TRACC_RWL.zip")
NIVEAUX_TRACC = {"RWL2": "2c", "RWL27": "27c", "RWL4": "4c"}
CHAMPS_RECHARGE_NON_CHAINE = {"CdEMssD", "ID_MESO", "Altitud", "NomMasseDE", "Non_Aqfr", "SurfMESO", "Mean17Re",
                              "Med17Re", "Q517Re", "Q9517Re", "min17Re", "Max17Re"}

# Cours d'eau « larges » : classes de largeur BD TOPAGE de 5 m et plus (MAJ : lit majeur représenté en surface)
CLASSES_LARGES = ("5_15", "15_50", "50", "MAJ")


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def _etape(nom: str) -> str:
    return os.path.join(ETAPES, f"{nom}.csv")


def _ecrire(df: pd.DataFrame, nom: str) -> None:
    os.makedirs(ETAPES, exist_ok=True)
    df.to_csv(_etape(nom), index=False, encoding="utf-8")
    _log(f"{nom} : {len(df)} lignes -> {_etape(nom)}")


# ---------------------------------------------------------------------------
# Communes
# ---------------------------------------------------------------------------
_communes = None


def communes():
    """Contours des communes de métropole (Lambert-93) et point intérieur de chacune."""
    global _communes
    if _communes is None:
        import geopandas as gpd
        c = gpd.read_file("/vsigzip/" + COMMUNES.replace("\\", "/"), columns=["code", "nom"])
        c = c[~c["code"].str.startswith(OUTRE_MER)].to_crs(L93)
        c["geometry"] = c.geometry.make_valid()
        c["surface"] = c.geometry.area
        c["point"] = c.geometry.representative_point()
        _communes = c.reset_index(drop=True)
        _log(f"{len(_communes)} communes")
    return _communes


def _points():
    import geopandas as gpd
    c = communes()
    return gpd.GeoDataFrame(c[["code"]], geometry=c["point"], crs=L93)


# ---------------------------------------------------------------------------
# Étapes
# ---------------------------------------------------------------------------
def etape_zonages():
    """Agence de l'eau (bassin du point intérieur), part de la commune en ZRE, SAGE."""
    import geopandas as gpd
    c, pts = communes(), _points()
    bas = gpd.read_file(BASSINS).to_crs(L93)
    j = gpd.sjoin(pts, bas[["NumCircAdminBassin", "geometry"]], predicate="within", how="left")
    j = j[~j.index.duplicated()]
    res = pd.DataFrame({"code": c["code"], "nom": c["nom"],
                        "agence": j["NumCircAdminBassin"].map(AGENCES).reindex(c.index).values})

    zre = gpd.read_file(ZRE).to_crs(L93)
    zre["geometry"] = zre.geometry.make_valid()
    paires = gpd.sjoin(c[["code", "geometry", "surface"]], zre[["TypeZRE", "NomZone", "geometry"]],
                       predicate="intersects")
    import shapely
    inter = shapely.intersection(paires.geometry.values, zre.geometry.loc[paires["index_right"]].values)
    paires["part"] = shapely.area(inter) / paires["surface"].values
    paires = paires[paires["part"] > 0.01]
    for type_zre, col in (("ZRESup", "zre_sup_part"), ("ZRESout", "zre_sout_part")):
        p = paires[paires["TypeZRE"] == type_zre].groupby("code")["part"].sum().clip(upper=1)
        res[col] = res["code"].map(p).fillna(0).round(3)
    noms = paires.groupby("code")["NomZone"].agg(lambda s: " ; ".join(sorted(set(s))))
    res["zre_noms"] = res["code"].map(noms).fillna("")

    sage = gpd.read_file(SAGE).to_crs(L93)
    col_nom = next(k for k in sage.columns if k.lower().startswith("nom"))
    j = gpd.sjoin(pts, sage[[col_nom, "geometry"]], predicate="within", how="left")
    j = j.groupby(level=0)[col_nom].agg(lambda s: " ; ".join(sorted(set(s.dropna()))))
    res["sage"] = j.reindex(c.index).fillna("").values
    _ecrire(res, "zonages")


def etape_restrictions():
    """Jours de restriction par an (moyenne 2016-2025) pour les eaux superficielles (SUP) et
    souterraines (SOU), par niveau de gravité minimal, et nombre d'années avec au moins un jour
    de crise. Lecture en flux du JSON (une entrée par commune et par jour)."""
    motif_commune = re.compile(r'\{"commune":\{"code":"([0-9AB]{5})"')
    # Seuls les jours avec restriction sont lus ; la date suit les niveaux dans chaque objet journalier
    motif_jour = re.compile(r'"(SOU|SUP)":"([a-z_]+)"(?:,"(?:SOU|SUP)":(?:null|"[a-z_]+"))?,"date":"(\d{4})')
    motif_double = re.compile(r'"SOU":"([a-z_]+)","SUP":"([a-z_]+)","date":"(\d{4})')
    rang = {n: i for i, n in enumerate(NIVEAUX)}
    annees = set(str(a) for a in ANNEES_RESTRICTIONS)
    lignes = []

    def traiter(code, texte):
        compte = {}   # (type, année) -> [jours par niveau]
        def ajouter(t, niveau, annee):
            if annee in annees and niveau in rang:
                compte.setdefault((t, annee), [0] * len(NIVEAUX))[rang[niveau]] += 1
        for m in motif_double.finditer(texte):
            ajouter("SOU", m.group(1), m.group(3))
            ajouter("SUP", m.group(2), m.group(3))
        for m in motif_jour.finditer(texte):
            # les jours où SOU et SUP sont tous deux restreints sont déjà comptés par motif_double
            if m.group(0).count('":"') == 3:
                continue
            ajouter(m.group(1), m.group(2), m.group(3))
        ligne = {"code": code}
        n = len(ANNEES_RESTRICTIONS)
        for t in ("SUP", "SOU"):
            par_annee = [compte.get((t, str(a)), [0] * len(NIVEAUX)) for a in ANNEES_RESTRICTIONS]
            for i, niveau in enumerate(NIVEAUX[1:], start=1):  # jours au niveau indiqué ou plus grave
                ligne[f"{t.lower()}_j_{niveau}"] = round(sum(sum(j[i:]) for j in par_annee) / n, 1)
            ligne[f"{t.lower()}_annees_crise"] = sum(1 for j in par_annee if j[rang["crise"]] > 0)
        lignes.append(ligne)

    with zipfile.ZipFile(RESTRICTIONS) as z, z.open(z.infolist()[0]) as fh:
        taille = z.infolist()[0].file_size
        reste, lu = "", 0
        while True:
            bloc = fh.read(64 << 20)
            lu += len(bloc)
            texte = reste + bloc.decode("utf-8", errors="replace")
            debuts = list(motif_commune.finditer(texte))
            fins = [m.start() for m in debuts[1:]] + [len(texte)]
            # Le dernier objet commune du bloc peut être incomplet : il est reporté au bloc suivant
            complets = len(debuts) if not bloc else len(debuts) - 1
            for m, fin in list(zip(debuts, fins))[:max(complets, 0)]:
                traiter(m.group(1), texte[m.start():fin])
            if not bloc:
                break
            reste = texte[debuts[-1].start():] if debuts else texte
            print(f"\r  {lu / taille:.0%} — {len(lignes)} communes", end="", flush=True)
    print()
    res = pd.DataFrame(lignes).drop_duplicates("code", keep="last")
    _ecrire(res, "restrictions")


def etape_sau():
    """Part de la SAU irriguée en 2020 (%), vide si secret statistique."""
    df = pd.read_excel(SAU, sheet_name="Data", header=None, skiprows=4, usecols=[0, 2], dtype=str)
    df.columns = ["code", "valeur"]
    df = df[df["code"].str.fullmatch(r"[0-9AB]{5}", na=False)]
    res = pd.DataFrame({"code": df["code"], "sau_irr_pct": pd.to_numeric(df["valeur"], errors="coerce"),
                        "sau_irr_secret": df["valeur"].str.contains("secret", na=False).astype(int)})
    _ecrire(res, "sau")


def etape_cours_eau():
    """Distance du point intérieur de la commune au cours d'eau permanent le plus proche (tous,
    puis de 5 m de large et plus) et au canal le plus proche ; présence d'un canal dans la commune."""
    import geopandas as gpd
    import pyogrio
    c, pts = communes(), _points()
    with zipfile.ZipFile(TOPAGE) as z:
        couches = [n for n in z.namelist() if n.endswith(".shp")]
    cols = ["TopoOH", "NatureTH", "Persistanc", "ClasseLarg", "TronconFic", "PositionPa"]
    res = pd.DataFrame({"code": c["code"]})
    for col in ("d_ce_perm_m", "d_ce_large_m", "d_canal_m"):
        res[col] = np.inf
    res["nom_ce_large"] = ""
    res["canal_commune"] = 0
    for couche in couches:
        t = pyogrio.read_dataframe(f"/vsizip/{TOPAGE.replace(os.sep, '/')}/{couche}", columns=cols)
        t = t[(t["TronconFic"].astype(str) == "0") & (t["PositionPa"] == "surface")].to_crs(L93)
        naturel = t["NatureTH"].isin(["Ecoulement naturel", "Ecoulement canalisé"]) & (t["Persistanc"] == "permanent")
        groupes = {"d_ce_perm_m": t[naturel], "d_ce_large_m": t[naturel & t["ClasseLarg"].isin(CLASSES_LARGES)],
                   "d_canal_m": t[t["NatureTH"] == "Canal"]}
        for col, lignes in groupes.items():
            if lignes.empty:
                continue
            j = gpd.sjoin_nearest(pts, lignes[["TopoOH", "geometry"]], distance_col="d", how="left")
            j = j[~j.index.duplicated()]
            plus_proche = j["d"].values < res[col].values
            res.loc[plus_proche, col] = j["d"].values[plus_proche]
            if col == "d_ce_large_m":
                res.loc[plus_proche, "nom_ce_large"] = j["TopoOH"].fillna("").values[plus_proche]
        canaux = groupes["d_canal_m"]
        if not canaux.empty:
            j = gpd.sjoin(c[["geometry"]], canaux[["geometry"]], predicate="intersects")
            res.loc[res.index.isin(j.index), "canal_commune"] = 1
        _log(f"{couche} : {len(t)} tronçons")
    for col in ("d_ce_perm_m", "d_ce_large_m", "d_canal_m"):
        res[col] = res[col].replace(np.inf, np.nan).round(0)
    _ecrire(res, "cours_eau")


def etape_nappes():
    """BDLISA au point intérieur de la commune : entité affleurante et première unité aquifère
    rencontrée en profondeur (ordre absolu croissant = de la surface vers la profondeur)."""
    import geopandas as gpd
    c, pts = communes(), _points()
    eh = gpd.read_file(BDLISA).to_crs(L93)
    j = gpd.sjoin(pts, eh[["CodeEH", "LibelleEH", "OrdreAbsEH", "NatureEH", "EtatEH", "MilieuEH", "ThemeEH",
                           "geometry"]], predicate="within")
    j = j.sort_values("OrdreAbsEH")
    lignes = []
    for i, g in j.groupby(level=0, sort=False):
        top = g.iloc[0]
        aq = g[g["NatureEH"].astype(str) == "5"]
        ligne = {"code": c.at[i, "code"], "eh_code": top["CodeEH"], "eh_libelle": top["LibelleEH"],
                 "eh_nature": top["NatureEH"], "eh_theme": top["ThemeEH"]}
        if not aq.empty:
            a = aq.iloc[0]
            ligne.update({"aq_code": a["CodeEH"], "aq_libelle": a["LibelleEH"], "aq_etat": a["EtatEH"],
                          "aq_milieu": a["MilieuEH"], "aq_theme": a["ThemeEH"],
                          "aq_rang": int(np.flatnonzero(g["CodeEH"].values == a["CodeEH"])[0]) + 1})
        lignes.append(ligne)
    _ecrire(pd.DataFrame(lignes), "nappes")


def etape_ouvrages():
    """Ouvrages existants du ROE dans la commune, par usage déclaré."""
    import pyogrio
    usages = [f"LbUsageObstEcoul{i}" for i in range(1, 5)]
    roe = pyogrio.read_dataframe(ROE, read_geometry=False,
                                 columns=["CdCommune", "LbEtOuvrage", "CdTypeOuvrage"] + usages)
    roe = roe[roe["LbEtOuvrage"] == "Existant"].copy()
    u = roe[usages].fillna("").agg(" | ".join, axis=1).str.lower()
    roe["roe_hydro"] = u.str.contains("hydro").astype(int)
    roe["roe_irrigation"] = u.str.contains("irrigation").astype(int)
    roe["roe_aep"] = u.str.contains("potable").astype(int)
    roe["roe_barrages"] = roe["CdTypeOuvrage"].fillna("").str.startswith("1.1").astype(int)
    roe["roe_total"] = 1
    res = roe.groupby("CdCommune")[["roe_total", "roe_barrages", "roe_hydro", "roe_irrigation", "roe_aep"]].sum()
    _ecrire(res.reset_index().rename(columns={"CdCommune": "code"}), "ouvrages")


def etape_explore2():
    """Projections hydrologiques Explore2 (RCP4.5, référence 1976-2005) à la station la plus proche de la
    commune : changement (%) du débit d'étiage (QMNA), du débit d'été (juin-août) et du débit d'hiver
    (décembre-février), par horizon. Médiane et quantiles 10 % / 90 % de l'ensemble des chaînes de
    simulation (modèles climatiques × modèles hydrologiques), chaînes aberrantes exclues."""
    import io
    import tarfile
    import geopandas as gpd
    st = pd.read_csv(os.path.join(EXPLORE2, "stations_Explore2.tab"), sep=",", dtype={"code": str})
    st = st[st["n_rcp45"] > 0]
    out = pd.read_csv(os.path.join(EXPLORE2, "code_Chain_outliers_Explore2.tab"), sep=",", dtype={"code": str})
    out = out[out["EXP"] == "historical-rcp45"]
    aberrantes = set(zip(out["code"], out["GCM"], out["RCM"], out["BC"], out["HM"]))
    lots = []
    for archive in sorted(os.listdir(EXPLORE2)):
        if not archive.endswith(".tar.gz"):
            continue
        with tarfile.open(os.path.join(EXPLORE2, archive)) as t:
            for m in t.getmembers():
                nom = m.name.rsplit("/", 1)[-1]
                ind = next((k for k, v in INDICATEURS_EXPLORE2.items() if nom.startswith(v + "_H")), None)
                if ind is None or "historical-rcp45" not in nom:
                    continue
                df = pd.read_parquet(io.BytesIO(t.extractfile(m).read()))
                col = df.columns[-1]
                df = df.rename(columns={col: "valeur"})
                df["indicateur"], df["horizon"] = ind, col.rsplit("_", 1)[-1]
                lots.append(df[["code", "GCM", "RCM", "BC", "HM", "indicateur", "horizon", "valeur"]])
        _log(f"{archive} lu")
    d = pd.concat(lots, ignore_index=True)
    cle = list(zip(d["code"], d["GCM"], d["RCM"], d["BC"], d["HM"]))
    d = d[[c not in aberrantes for c in cle]].dropna(subset=["valeur"])
    g = d.groupby(["code", "indicateur", "horizon"])["valeur"]
    stats = pd.DataFrame({"med": g.median(), "bas": g.quantile(0.1), "haut": g.quantile(0.9), "n": g.size()})
    stats = stats.reset_index()
    large = stats.pivot_table(index="code", columns=["indicateur", "horizon"], values=["med", "bas", "haut"])
    large.columns = [f"e2_{i}_{h.lower()}" + ("" if s == "med" else f"_{s}") for s, i, h in large.columns]
    large["e2_n"] = stats.groupby("code")["n"].max()
    large = large.round(1).reset_index()

    pts = _points()
    stg = gpd.GeoDataFrame(st[["code", "name", "river_name", "surface_km2"]],
                           geometry=gpd.points_from_xy(st["XL93_m"], st["YL93_m"]), crs=L93)
    stg = stg[stg["code"].isin(large["code"])]
    j = gpd.sjoin_nearest(pts, stg, distance_col="d", how="left", max_distance=DISTANCE_MAX_STATION)
    j = j[~j.index.duplicated()]
    res = pd.DataFrame({"code": pts["code"].values, "e2_station_code": j["code_right"].values,
                        "e2_station": j["name"].values, "e2_riviere": j["river_name"].values,
                        "e2_surface_km2": j["surface_km2"].values, "e2_dist_km": (j["d"] / 1000).round(1).values})
    res = res.merge(large.rename(columns={"code": "e2_station_code"}), on="e2_station_code", how="left")
    _ecrire(res, "explore2")


def etape_recharge():
    """Recharge potentielle des nappes (Explore2, modèle RECHARGE) de la masse d'eau souterraine affleurante
    au point intérieur de la commune : recharge 1976-2005 (mm/an, médiane des 17 projections climatiques) et
    changement (%) aux niveaux de réchauffement de la TRACC, calculé projection par projection puis résumé par
    la médiane et les quantiles 10 % / 90 %."""
    import geopandas as gpd
    archive = "/vsizip/" + RECHARGE.replace(os.sep, "/")
    lire = lambda fenetre, **k: gpd.read_file(f"{archive}/RECH_year_TRACC_{fenetre}_2026.shp", **k)  # noqa: E731
    ref = lire("ref7605")
    chaines = [c for c in ref.columns if c not in CHAMPS_RECHARGE_NON_CHAINE and c != "geometry"]
    ref = ref.to_crs(L93)
    pts = _points()
    j = gpd.sjoin(pts, ref[["CdEMssD", "NomMasseDE", "Non_Aqfr", "geometry"]], predicate="within", how="left")
    j = j[~j.index.duplicated()]
    res = pd.DataFrame({"code": pts["code"].values, "rech_meso": j["NomMasseDE"].values,
                        "rech_meso_code": j["CdEMssD"].values, "rech_non_aquifere": j["Non_Aqfr"].round(2).values})
    base = ref.set_index("CdEMssD")[chaines].astype(float)
    res["rech_ref_mm"] = res["rech_meso_code"].map(base.median(axis=1)).round(0)
    for fenetre, nom in NIVEAUX_TRACC.items():
        fut = lire(fenetre, ignore_geometry=True).set_index("CdEMssD")[chaines].astype(float)
        delta = (fut - base) / base.where(base > 1) * 100   # recharge de référence quasi nulle : non calculé
        for col, s in (("", delta.median(axis=1)), ("_bas", delta.quantile(0.1, axis=1)),
                       ("_haut", delta.quantile(0.9, axis=1))):
            res[f"rech_{nom}{col}"] = res["rech_meso_code"].map(s).round(1)
    res["rech_n"] = len(chaines)
    _ecrire(res.drop(columns="rech_meso_code"), "recharge")


ETAPES_DISPONIBLES = {"zonages": etape_zonages, "restrictions": etape_restrictions, "sau": etape_sau,
                      "cours_eau": etape_cours_eau, "nappes": etape_nappes, "ouvrages": etape_ouvrages,
                      "explore2": etape_explore2, "recharge": etape_recharge}


def assembler() -> None:
    """Réunit les étapes calculées dans territoire/indicateurs_communes.csv."""
    base = pd.read_csv(_etape("zonages"), dtype={"code": str})
    base = base[~base["code"].str.startswith(OUTRE_MER)]
    for nom in ETAPES_DISPONIBLES:
        if nom == "zonages":
            continue
        if not os.path.exists(_etape(nom)):
            _log(f"étape « {nom} » absente : ignorée")
            continue
        base = base.merge(pd.read_csv(_etape(nom), dtype={"code": str}), on="code", how="left")
    os.makedirs(os.path.dirname(DESTINATION), exist_ok=True)
    base.to_csv(DESTINATION, index=False, encoding="utf-8")
    _log(f"{DESTINATION} : {len(base)} communes, {base.shape[1]} colonnes, "
         f"{os.path.getsize(DESTINATION) / 1e6:.1f} Mo")


if __name__ == "__main__":
    demandees = [n for n in sys.argv[1:] if n != "assembler"] if sys.argv[1:] else list(ETAPES_DISPONIBLES)
    for nom in demandees:
        if nom not in ETAPES_DISPONIBLES:
            sys.exit(f"Étape inconnue : {nom} (disponibles : {', '.join(ETAPES_DISPONIBLES)})")
    for nom in demandees:
        _log(f"étape {nom}")
        ETAPES_DISPONIBLES[nom]()
    if os.path.exists(_etape("zonages")):
        assembler()
