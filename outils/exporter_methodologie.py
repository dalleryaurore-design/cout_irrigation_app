# -*- coding: utf-8 -*-
"""
Export PDF de la note méthodologique
====================================
La note est rédigée et modifiée dans Word (``docs/methodologie_irrigation.docx``) ; l'application
sert son export PDF (``docs/methodologie_irrigation.pdf``, bouton « Télécharger la méthodologie »).

Après chaque modification du Word, lancer :

    python outils/exporter_methodologie.py

Le PDF est produit par Microsoft Word (Windows) s'il est installé, sinon par LibreOffice. On peut aussi
l'enregistrer directement depuis Word (Fichier > Enregistrer sous > PDF) au même emplacement.
"""

import os
import shutil
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import config  # noqa: E402


def par_word(docx: str, pdf: str) -> bool:
    """Export par Word via COM (PowerShell), sans dépendance Python supplémentaire."""
    if os.name != "nt":
        return False
    script = (
        "$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
        f"$d = $w.Documents.Open('{docx}', $false, $true); "
        f"$d.ExportAsFixedFormat('{pdf}', 17); "  # 17 = wdExportFormatPDF
        "$d.Close($false); $w.Quit()"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and os.path.exists(pdf)


def par_libreoffice(docx: str, pdf: str) -> bool:
    soffice = shutil.which("soffice") or next(
        (p for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                     "/usr/bin/soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice")
         if os.path.exists(p)), None)
    if not soffice:
        return False
    r = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", os.path.dirname(pdf), docx],
                       capture_output=True, text=True, timeout=180)
    produit = os.path.splitext(os.path.join(os.path.dirname(pdf), os.path.basename(docx)))[0] + ".pdf"
    if r.returncode == 0 and os.path.exists(produit) and produit != pdf:
        os.replace(produit, pdf)
    return r.returncode == 0 and os.path.exists(pdf)


def main():
    docx, pdf = os.path.abspath(config.METHODOLOGIE_DOCX), os.path.abspath(config.METHODOLOGIE_PDF)
    if not os.path.exists(docx):
        sys.exit(f"Note introuvable : {docx}")
    avant = os.path.getmtime(pdf) if os.path.exists(pdf) else 0
    if not (par_word(docx, pdf) or par_libreoffice(docx, pdf)) or os.path.getmtime(pdf) <= avant:
        sys.exit("Export impossible (ni Word ni LibreOffice) : enregistrer le PDF depuis Word à l'emplacement "
                 f"{pdf}. Fermer le document dans Word s'il est ouvert.")
    print(f"PDF mis à jour : {pdf}")


if __name__ == "__main__":
    main()
