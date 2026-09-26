/* =========================================================================
   Graphique en cascade : du gain lié à l'irrigation au bilan, poste par poste.
   Les couleurs sont imposées par le référentiel de l'application (moteur/calcul.py)
   et transmises par l'API : gain vert, énergie violet, redevance bleu,
   équipement orange, main-d'œuvre rose, accès à la ressource jaune, bilan noir.
   ========================================================================= */
(function (global) {
  "use strict";

  var GRIS = "#929292", TEXTE = "#3a3a3a";

  function fmt(v, dec) {
    return new Intl.NumberFormat("fr-FR", {
      minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0
    }).format(v);
  }

  function Cascade(canvas) {
    this.canvas = canvas;
    this.chart = null;
    this.donnees = [];
  }

  /* res : réponse de /api/simulation */
  Cascade.prototype.maj = function (res) {
    var self = this;
    var gain = res.gain.total, cumul = gain, lignes = [];
    lignes.push({
      libelle: "Gain lié à l'irrigation", intervalle: [0, gain],
      couleur: res.couleurs.gain, montant: gain, type: "gain"
    });
    res.couts.postes.forEach(function (p) {
      var debut = cumul;
      cumul -= p.montant;
      lignes.push({
        libelle: p.libelle, intervalle: [cumul, debut],
        couleur: p.couleur, montant: -p.montant, type: "cout", part: p.part
      });
    });
    lignes.push({
      libelle: "Bilan", intervalle: [0, cumul],
      couleur: res.couleurs.bilan, montant: cumul, type: "bilan"
    });
    this.donnees = lignes;

    var libelles = lignes.map(function (l) {
      return l.libelle.length > 26 ? l.libelle.slice(0, 24).split(" (")[0] + "…" : l.libelle;
    });
    var config = {
      type: "bar",
      data: {
        labels: libelles,
        datasets: [{
          label: "€/an",
          data: lignes.map(function (l) { return l.intervalle; }),
          backgroundColor: lignes.map(function (l) { return l.couleur; }),
          borderColor: lignes.map(function (l) { return l.couleur; }),
          borderWidth: 1, borderSkipped: false, barPercentage: 0.72, categoryPercentage: 0.9
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
        layout: { padding: { top: 8 } },
        scales: {
          x: {
            ticks: { color: TEXTE, font: { size: 11 }, maxRotation: 40, minRotation: 0, autoSkip: false },
            grid: { display: false }
          },
          y: {
            title: { display: true, text: "€/an", color: TEXTE, font: { size: 11 } },
            ticks: { color: TEXTE, font: { size: 11 }, callback: function (v) { return fmt(v); } },
            grid: { color: "#e5e5e5" },
            border: { color: GRIS }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false }
        }
      },
      plugins: [{
        /* Étiquettes de valeur au bout de chaque barre + ligne de zéro */
        id: "etiquettes",
        beforeDraw: function (c) {
          var ctx = c.ctx;
          ctx.save();
          ctx.fillStyle = "#ffffff";
          ctx.fillRect(c.chartArea.left, c.chartArea.top,
            c.chartArea.right - c.chartArea.left, c.chartArea.bottom - c.chartArea.top);
          ctx.restore();
        },
        afterDatasetsDraw: function (c) {
          var ctx = c.ctx, meta = c.getDatasetMeta(0), y0 = c.scales.y.getPixelForValue(0);
          var donnees = self.donnees;
          ctx.save();
          ctx.strokeStyle = GRIS; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(c.chartArea.left, y0); ctx.lineTo(c.chartArea.right, y0); ctx.stroke();
          ctx.font = "600 11px Marianne, Arial, sans-serif";
          ctx.textAlign = "center";
          meta.data.forEach(function (barre, i) {
            var l = donnees[i], haut = Math.min(barre.y, barre.base), bas = Math.max(barre.y, barre.base);
            var texte = (l.montant >= 0 ? "+" : "−") + fmt(Math.abs(l.montant)) + " €";
            ctx.fillStyle = l.type === "bilan" ? (l.montant >= 0 ? "#18753C" : "#CE0500") : TEXTE;
            if (l.montant >= 0) {
              ctx.textBaseline = "bottom";
              ctx.fillText(texte, barre.x, Math.max(haut - 4, c.chartArea.top + 11));
            } else {
              ctx.textBaseline = "top";
              ctx.fillText(texte, barre.x, Math.min(bas + 4, c.chartArea.bottom - 12));
            }
          });
          ctx.restore();
        }
      }]
    };

    if (this.chart) {
      this.chart.data = config.data;
      this.chart.options = config.options;
      this.chart.update();
    } else {
      this.chart = new global.Chart(this.canvas, config);
    }
  };

  /* Export PNG sur fond blanc (le canvas est déjà peint en blanc par le greffon) */
  Cascade.prototype.exporterPNG = function (nom) {
    if (!this.chart) { return; }
    var a = document.createElement("a");
    a.href = this.chart.toBase64Image("image/png", 1);
    a.download = (nom || "cascade-irrigation") + ".png";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  Cascade.prototype.exporterCSV = function (nom, entetes) {
    var lignes = [["Poste", "Montant (€/an)", "Cumul (€/an)"]];
    (entetes || []).forEach(function (l) { lignes.unshift(l); });
    this.donnees.forEach(function (l) {
      lignes.push([l.libelle, Math.round(l.montant), Math.round(l.intervalle[1] === 0 ? l.intervalle[0] : l.intervalle[0])]);
    });
    var csv = "\ufeff" + lignes.map(function (l) {
      return l.map(function (c) {
        var t = String(c).replace(/"/g, '""');
        return /[";\n]/.test(t) ? '"' + t + '"' : t;
      }).join(";");
    }).join("\r\n");
    var url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    var a = document.createElement("a");
    a.href = url;
    a.download = (nom || "cascade-irrigation") + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  global.Cascade = Cascade;
})(window);
