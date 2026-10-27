/* =========================================================================
   Outils communs aux volets sans simulation de parcelle (Références,
   Comparaison de trajectoires) : formats français,
   export CSV des tableaux (bouton « Exporter (CSV) » des macros de gabarit)
   et téléchargement d'un fichier renvoyé par l'API.
   ========================================================================= */
(function (global) {
  "use strict";

  function fmt(v, dec) {
    if (v === null || v === undefined || isNaN(v)) { return "–"; }
    return new Intl.NumberFormat("fr-FR", {
      minimumFractionDigits: dec === undefined ? 0 : dec,
      maximumFractionDigits: dec === undefined ? 0 : dec
    }).format(v);
  }

  function texteCellule(cellule) {
    var champ = cellule.querySelector("input, select");
    if (champ) { return champ.type === "checkbox" ? (champ.checked ? "oui" : "non") : champ.value; }
    var clone = cellule.cloneNode(true);
    clone.querySelectorAll(".fr-tooltip").forEach(function (t) { t.remove(); });
    return clone.textContent.replace(/\s+/g, " ").trim();
  }

  function telechargerBlob(blob, nom) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = nom;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function telechargerCSV(lignes, nom) {
    var csv = "﻿" + lignes.map(function (l) {
      return l.map(function (c) {
        var t = String(c === undefined || c === null ? "" : c).replace(/"/g, '""');
        return /[";\n]/.test(t) ? '"' + t + '"' : t;
      }).join(";");
    }).join("\r\n");
    telechargerBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), (nom || "tableau") + ".csv");
  }

  function exporterTableauCSV(table, nom) {
    var lignes = [];
    table.querySelectorAll("thead tr, tbody tr, tfoot tr").forEach(function (tr) {
      lignes.push(Array.prototype.map.call(tr.querySelectorAll("th, td"), texteCellule));
    });
    telechargerCSV(lignes, nom);
  }

  document.addEventListener("click", function (ev) {
    var bouton = ev.target.closest && ev.target.closest(".bouton-export-tableau");
    if (!bouton) { return; }
    var table = document.getElementById(bouton.dataset.cible);
    if (table) { exporterTableauCSV(table, bouton.dataset.cible); }
  });

  global.Tableaux = { fmt: fmt, telechargerBlob: telechargerBlob, telechargerCSV: telechargerCSV };
})(window);
