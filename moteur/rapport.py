# -*- coding: utf-8 -*-
"""
Rapport PDF d'une simulation de parcelle (volet « Cas personnel »)
==================================================================
Une à deux pages : la parcelle et ses hypothèses, le bilan agronomique, le coût avec et
sans subvention (charges fixes et variables), la décomposition par poste, les variables
modifiées et les limites de lecture. Police Marianne (DSFR).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from fpdf import FPDF

from .referentiel import CLE_LIBRE, Referentiel

DOSSIER_POLICES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "fonts")
BLEU = (0, 0, 145)
GRIS = (102, 102, 102)
GRIS_CLAIR = (238, 238, 238)
VERT, ROUGE = (24, 117, 60), (206, 5, 0)

LIMITES = [
    "Ordre de grandeur pour une année climatique moyenne : les années sèches et humides ne sont pas simulées.",
    "Le bilan n'est pas une marge nette : il ne déduit pas les charges induites par l'irrigation "
    "(fertilisation, récolte, séchage) ni les aides PAC.",
    "Échelle de la parcelle : la rotation, l'assolement et la sécurisation du système ne sont pas valorisés.",
    "La disponibilité de l'eau (volumes autorisés, restrictions) n'est pas évaluée.",
]


def nombre(v: Optional[float], dec: int = 0) -> str:
    if v is None:
        return "–"
    txt = f"{float(v):,.{dec}f}"
    return txt.replace(",", " ").replace(".", ",").replace("-", "−")


def _rvb(hexa: str):
    h = hexa.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Rapport(FPDF):
    def __init__(self, date_ref: str):
        super().__init__(format="A4")
        self.date_ref = date_ref
        self.add_font("Marianne", "", os.path.join(DOSSIER_POLICES, "Marianne-Regular.ttf"))
        self.add_font("Marianne", "B", os.path.join(DOSSIER_POLICES, "Marianne-Bold.ttf"))
        self.set_margins(16, 14, 16)
        self.set_auto_page_break(True, margin=18)

    def footer(self):
        self.set_y(-13)
        self.set_font("Marianne", "", 7.5)
        self.set_text_color(*GRIS)
        self.cell(0, 4, f"Analyse financière d'un système d'irrigation – SGPE · référentiel du {self.date_ref} · "
                        f"page {self.page_no()}/{{nb}}", align="C")

    def titre(self, texte: str):
        self.ln(3)
        self.set_font("Marianne", "B", 11.5)
        self.set_text_color(*BLEU)
        self.cell(0, 7, texte, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BLEU)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def texte(self, t: str, taille: float = 9, gras: bool = False, couleur=(0, 0, 0)):
        self.set_font("Marianne", "B" if gras else "", taille)
        self.set_text_color(*couleur)
        self.multi_cell(0, taille * 0.5, t, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def tableau(self, lignes, largeurs, entete=None, aligne=None, taille=8.5):
        self.set_font("Marianne", "", taille)
        self.set_fill_color(255, 255, 255)
        aligne = aligne or ["LEFT"] + ["RIGHT"] * (len(largeurs) - 1)
        with self.table(col_widths=largeurs, text_align=aligne, line_height=taille * 0.55,
                        first_row_as_headings=bool(entete), borders_layout="HORIZONTAL_LINES",
                        headings_style=_style_entete(), padding=1.2) as t:
            for ligne in ([entete] if entete else []) + lignes:
                r = t.row()
                for c in ligne:
                    r.cell(str(c))

    def encadre(self, x, y, l, h, titre, lignes, couleur):
        self.set_fill_color(*GRIS_CLAIR)
        self.rect(x, y, l, h, style="F")
        self.set_fill_color(*couleur)
        self.rect(x, y, 1.4, h, style="F")
        self.set_xy(x + 4, y + 2.5)
        self.set_font("Marianne", "B", 8.5)
        self.set_text_color(*GRIS)
        self.cell(l - 6, 4.5, titre, new_x="LEFT", new_y="NEXT")
        for i, (t, gras) in enumerate(lignes):
            self.set_x(x + 4)
            self.set_font("Marianne", "B" if gras else "", 14 if i == 0 else 8.5)
            self.set_text_color(*(couleur if i == 0 else (0, 0, 0)))
            self.cell(l - 6, 7 if i == 0 else 4.4, t, new_x="LEFT", new_y="NEXT")
        self.set_text_color(0, 0, 0)


def _style_entete():
    from fpdf.fonts import FontFace
    return FontFace(family="Marianne", emphasis="BOLD", color=(255, 255, 255), fill_color=BLEU)


def rapport_parcelle(ref: Referentiel, e: Dict[str, Any], res: Dict[str, Any], commune: Optional[Dict[str, Any]],
                     surcharges: Dict[str, Any], date_ref) -> bytes:
    pdf = Rapport(time.strftime("%d/%m/%Y", date_ref))
    pdf.add_page()
    a, c, cap = res["agro"], res["couts"], res["capex"]
    sans = c["sans_subvention"]

    # ---------------------------------------------------------------- En-tête
    pdf.set_font("Marianne", "B", 8)
    pdf.cell(0, 4, "RÉPUBLIQUE FRANÇAISE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Marianne", "", 7.5)
    pdf.set_text_color(*GRIS)
    pdf.cell(0, 4, "Secrétariat général à la planification écologique", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Marianne", "B", 16)
    pdf.set_text_color(*BLEU)
    pdf.cell(0, 8, "Coût et rentabilité de l'irrigation de ma parcelle", new_x="LMARGIN", new_y="NEXT")
    lieu = f"{commune['nom']} ({commune.get('departement', '')})" if commune and commune.get("nom") else "commune non renseignée"
    pdf.texte(f"{e['culture']} · {nombre(e.get('surface'), 1)} ha · {lieu} · simulation du "
              f"{time.strftime('%d/%m/%Y')}", 9.5, couleur=GRIS)

    # ---------------------------------------------------------------- Parcelle
    pdf.titre("Ma parcelle et mes choix")
    an = res["annualisation"]
    lignes = [
        ["Culture", e["culture"], "Prix de vente retenu", f"{nombre(res['gain']['prix'])} €/t"],
        ["Surface irriguée", f"{nombre(e.get('surface'), 1)} ha", "Équipement",
         f"{e['equipement']}" + (f" ({res['dimensionnement']['nb_unites']} unité(s))"
                                 if res["dimensionnement"].get("nb_unites") else "")],
        ["Source de l'eau", e["source"], "Agence de l'eau",
         (res["redevance"]["agence"] or "non déterminée") + (" · ZRE" if e.get("zre") else "")],
        ["Subvention au matériel", f"{nombre(an['equipement']['subvention'] * 100)} %",
         "Subvention à l'accès à l'eau", f"{nombre(an['acces']['subvention'] * 100)} %"],
        ["Besoin en eau (méthode)", {"sgpe": f"SGPE (bilan hydrique, RU {nombre((a.get('sol') or {}).get('ru'))} mm)",
                                     "carte": "Carte MAELIA", "saisie": "valeur saisie"}
         .get(a.get("methode_besoin"), "Référentiel"),
         "Rendements (origine)", {"carte": "Cartes MAELIA", "saisie": "valeurs saisies",
                                  "sgpe": "SGPE (Ky, FAO-33)"}.get(a.get("origine"), "Référentiel")],
    ]
    pdf.tableau(lignes, (42, 49, 44, 47), aligne=["LEFT"] * 4)

    # ---------------------------------------------------------------- Agronomie
    pdf.titre("Bilan agronomique")
    pdf.tableau([[f"{nombre(a['rdt_irrigue'], 1)} q/ha", f"{nombre(a['rdt_pluvial'], 1)} q/ha",
                  f"{nombre(a['besoin_mm'])} mm", f"{nombre(a['volume_preleve'])} m³",
                  f"{nombre(a['efficience'] * 100)} %"]],
                (36, 36, 36, 38, 36),
                entete=["Rendement irrigué", "Rendement pluvial", "Besoin en eau", "Volume prélevé", "Efficience"],
                aligne=["CENTER"] * 5)

    # ---------------------------------------------------------------- Économie
    pdf.titre("Bilan économique annuel")
    y, l, h, g = pdf.get_y() + 1, 57, 33, 5.5
    x0 = pdf.l_margin
    b = res["bilan"]
    pdf.encadre(x0, y, l, h, "Bilan avec subvention",
                [(f"{'+' if b['total'] >= 0 else ''}{nombre(b['total'])} €/an", True),
                 (f"Sans subvention : {nombre(b['sans_subvention']['total'])} €/an", False),
                 (f"Gain lié à l'irrigation : {nombre(res['gain']['total'])} €/an", False)],
                VERT if b["total"] >= 0 else ROUGE)
    pdf.encadre(x0 + l + g, y, l, h, "Coût avec subvention",
                [(f"{nombre(c['total'])} €/an", True),
                 (f"{nombre(c['c_par_m3'], 1)} c€/m³ · {nombre(c['par_ha'])} €/ha", False),
                 (f"Charges fixes : {nombre(c['fixes'])} € ({nombre(c['part_fixes'] * 100)} %)", False),
                 (f"Charges variables : {nombre(c['variables'])} €", False)], BLEU)
    pdf.encadre(x0 + 2 * (l + g), y, l, h, "Coût sans subvention",
                [(f"{nombre(sans['total'])} €/an", True),
                 (f"{nombre(sans['c_par_m3'], 1)} c€/m³ · {nombre(sans['par_ha'])} €/ha", False),
                 (f"Aide publique : {nombre(c['aide_publique_annuelle'])} €/an", False)], GRIS)
    pdf.set_y(y + h + 3)
    pdf.texte(f"Investissement initial : {nombre(cap['total'])} €, dont agriculteur {nombre(cap['reste_a_charge'])} € "
              f"et aide publique {nombre(cap['total'] - cap['reste_a_charge'])} €.", 8.5)
    pdf.texte("Charges fixes : annuités du matériel et de l'ouvrage, maintenance, part fixe du tarif ; elles sont dues "
              "chaque année, même sans irriguer. Charges variables : énergie, redevance, part volumétrique, "
              "main-d'œuvre.", 7.5, couleur=GRIS)

    # ---------------------------------------------------------------- Postes
    pdf.titre("Décomposition du coût annuel (avec subvention)")
    total = c["total"] or 1.0
    x_barre, l_max = pdf.l_margin + 70, pdf.w - pdf.r_margin - (pdf.l_margin + 70) - 40
    for p in c["postes"]:
        y = pdf.get_y()
        pdf.set_font("Marianne", "", 8.5)
        pdf.set_fill_color(*_rvb(p["couleur"]))
        pdf.rect(pdf.l_margin, y + 1.2, 2.6, 2.6, style="F")
        pdf.set_x(pdf.l_margin + 4)
        pdf.cell(64, 5, p["libelle"].split(" (")[0])
        pdf.rect(x_barre, y + 0.8, max(l_max * p["montant"] / total, 0.3), 3.4, style="F")
        pdf.set_x(pdf.w - pdf.r_margin - 38)
        pdf.cell(38, 5, f"{nombre(p['montant'])} € · {nombre(p['part'] * 100)} %", align="R",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Marianne", "B", 8.5)
    pdf.cell(0, 5.5, f"Coût total : {nombre(c['total'])} €/an", align="R", new_x="LMARGIN", new_y="NEXT")

    # ---------------------------------------------------------------- Variables modifiées
    modifs = [k for k in surcharges if k != CLE_LIBRE and k in ref.params
              and ref.params[k].code not in ("prix_vente", "prix_masaa")]
    pdf.titre("Variables modifiées par rapport au référentiel")
    if modifs:
        lignes = []
        for k in modifs:
            p = ref.params[k]
            f = 100.0 if p.est_pourcentage else 1.0
            unite = "%" if p.est_pourcentage else p.unite
            v = ref.valeur(p.feuille, p.objet, p.code, surcharges)
            lignes.append([f"{p.objet} – {p.libelle}", f"{nombre(p.valeur * f, 2) if p.valeur is not None else '–'} {unite}",
                           f"{nombre(v * f, 2)} {unite}"])
        pdf.tableau(lignes, (110, 36, 36), entete=["Variable", "Référentiel", "Ma valeur"])
    else:
        pdf.texte("Aucune : toutes les valeurs sont celles du référentiel.", 8.5)

    # ---------------------------------------------------------------- Avertissements et limites
    avert = [w["texte"] for w in res.get("avertissements", []) if w["niveau"] != "info"] + list(a.get("notes") or [])
    if avert:
        pdf.titre("Points d'attention")
        for t in avert:
            pdf.texte("• " + t, 8.5)
    pdf.titre("Limites de lecture")
    for t in LIMITES:
        pdf.texte("• " + t, 8)
    return bytes(pdf.output())
