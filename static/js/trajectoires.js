/* =========================================================================
   Comparaison de trajectoires : deux ou trois scénarios pour un même lieu et
   une même surface ► un POST /api/simulation par scénario ► tableau comparé
   (écart au scénario 1) et graphique coût fixe / variable / gain.
   ========================================================================= */
(function () {
  "use strict";

  var PAGE = JSON.parse(document.getElementById("donnees-page").textContent || "{}");
  var $ = function (id) { return document.getElementById(id); };
  var fmt = Tableaux.fmt;
  var BLEU = "#000091", BLEU_CLAIR = "#6E6EF0", VERT = "#18753C", TEXTE = "#3a3a3a";
  var DEFAUTS = {
    1: { culture: "Maïs", horizon: "H1", equipement: "Pivot", source: "Forage individuel", taux: 100, amorti: true, amorti_equipement: true },
    2: { culture: "Maïs", horizon: "H2", equipement: "Pivot", source: "Forage individuel", taux: 100, amorti: true, amorti_equipement: true },
    3: { culture: "Sorgho", horizon: "H2", equipement: "Pivot", source: "Forage individuel", taux: 60, amorti: true, amorti_equipement: true }
  };
  var recherche = null, graphique = null, minuterie = null, ticket = 0;

  function echapper(t) {
    return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function nombreOuNull(v) { var n = parseFloat(v); return isNaN(n) ? null : n; }
  function signe(v, dec) { return (v >= 0 ? "+" : "−") + fmt(Math.abs(v), dec || 0); }

  function actifs() { return [1, 2, 3].filter(function (n) { return !$("colonne-s" + n).hidden; }); }

  function champ(n, nom) { return $("s" + n + "-" + nom.replace("_", "-")); }

  function initialiser() {
    [1, 2, 3].forEach(function (n) {
      var d = DEFAUTS[n];
      ["culture", "horizon", "equipement", "source"].forEach(function (k) {
        var el = champ(n, k);
        if (Array.prototype.some.call(el.options, function (o) { return o.value === d[k]; })) { el.value = d[k]; }
      });
      champ(n, "taux").value = d.taux;
      champ(n, "amorti").checked = d.amorti;
      champ(n, "amorti_equipement").checked = d.amorti_equipement;
    });
  }

  function entrees(n) {
    return {
      culture: champ(n, "culture").value, surface: parseFloat($("surface").value) || 0,
      source: champ(n, "source").value, equipement: champ(n, "equipement").value,
      agence: $("agence").value, zre: $("zre").checked, horizon: champ(n, "horizon").value,
      taux_couverture: nombreOuNull(champ(n, "taux").value), prix_vente: nombreOuNull(champ(n, "prix").value),
      deja_amorti: champ(n, "amorti").checked,
      deja_amorti_equipement: champ(n, "amorti_equipement").checked, methode_besoin: "auto", capacite_auto: true,
      type_retenue: "individuelle", nb_adherents: 1
    };
  }

  function planifier() {
    clearTimeout(minuterie);
    $("simulation-chargement").hidden = false;
    minuterie = setTimeout(calculer, 250);
  }

  function calculer() {
    var n = ++ticket, liste = actifs();
    Promise.all(liste.map(function (s) {
      return fetch("/api/simulation", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entrees: entrees(s), surcharges: {}, commune: recherche ? recherche.commune : null })
      }).then(function (r) { return r.json(); });
    })).then(function (res) {
      if (n !== ticket) { return; }
      afficher(liste, res);
    }).catch(function (e) {
      $("avertissements").innerHTML = '<div class="fr-alert fr-alert--error fr-alert--sm"><p>Calcul impossible : ' +
        echapper(e.message) + "</p></div>";
    }).then(function () { if (n === ticket) { $("simulation-chargement").hidden = true; } });
  }

  /* Indicateurs du tableau : libellé, valeur, décimales, sens favorable (+1 : plus est mieux, −1 : moins est mieux) */
  var LIGNES = [
    ["Culture", function (r) { return r.entrees.culture; }],
    ["Horizon climatique", function (r) { return (PAGE.horizons[r.agro.horizon] || r.agro.horizon); }],
    ["Équipement · source", function (r) { return r.entrees.equipement + " · " + r.entrees.source; }],
    ["Couverture du besoin (%)", function (r) { return r.agro.taux_couverture * 100; }, 0, 0],
    ["Besoin en eau (mm)", function (r) { return r.agro.besoin_mm; }, 0, -1],
    ["Volume prélevé (m³/an)", function (r) { return r.agro.volume_preleve; }, 0, -1],
    ["Rendement irrigué (q/ha)", function (r) { return r.agro.rdt_irrigue; }, 1, 1],
    ["Rendement pluvial (q/ha)", function (r) { return r.agro.rdt_pluvial; }, 1, 1],
    ["Gain lié à l'irrigation (€/an)", function (r) { return r.gain.total; }, 0, 1],
    ["Coût avec subvention (€/an)", function (r) { return r.couts.total; }, 0, -1],
    ["dont charges fixes (€/an)", function (r) { return r.couts.fixes; }, 0, -1],
    ["dont charges variables (€/an)", function (r) { return r.couts.variables; }, 0, -1],
    ["Coût sans subvention (€/an)", function (r) { return r.couts.sans_subvention.total; }, 0, -1],
    ["Coût de l'eau (c€/m³)", function (r) { return r.couts.c_par_m3; }, 1, -1],
    ["Bilan avec subvention (€/an)", function (r) { return r.bilan.total; }, 0, 1, true],
    ["Bilan sans subvention (€/an)", function (r) { return r.bilan.sans_subvention.total; }, 0, 1, true],
    ["Prix de vente minimal (€/t)", function (r) { return r.seuil.prix_min; }, 0, -1]
  ];

  function nomScenario(n) { return champ(n, "nom").value || "Scénario " + n; }

  function afficher(liste, res) {
    $("entete-trajectoires").innerHTML = '<th scope="col">Indicateur</th>' + liste.map(function (n) {
      return '<th scope="col" class="num">' + echapper(nomScenario(n)) + "</th>";
    }).join("");
    $("corps-trajectoires").innerHTML = LIGNES.map(function (l) {
      var ref0 = l[1](res[0]);
      return '<tr><th scope="row">' + l[0] + "</th>" + res.map(function (r, i) {
        var v = l[1](r);
        if (typeof v !== "number") { return '<td class="num">' + echapper(v) + "</td>"; }
        var cell = (l[4] ? signe(v) : fmt(v, l[2]));
        if (i > 0 && typeof ref0 === "number" && l[3]) {
          var d = v - ref0, favorable = d * l[3] > 0;
          if (Math.abs(d) > 1e-9) {
            cell += '<span class="ecart ' + (favorable ? "ecart--favorable" : "ecart--defavorable") + '">' + signe(d, l[2]) + "</span>";
          } else {
            cell += '<span class="ecart">=</span>';
          }
        }
        return '<td class="num">' + cell + "</td>";
      }).join("") + "</tr>";
    }).join("");

    var meilleur = 0;
    res.forEach(function (r, i) { if (r.bilan.total > res[meilleur].bilan.total) { meilleur = i; } });
    var v0 = res[0].agro.volume_preleve;
    $("synthese-trajectoires").innerHTML = "Meilleur bilan avec subvention : <strong>" + echapper(nomScenario(liste[meilleur])) +
      "</strong> (" + signe(res[meilleur].bilan.total) + " €/an). " + res.slice(1).map(function (r, i) {
        var dv = r.agro.volume_preleve - v0;
        return echapper(nomScenario(liste[i + 1])) + " : " + (dv <= 0 ? "économise " : "prélève ") +
          fmt(Math.abs(dv), 0) + " m³/an " + (dv <= 0 ? "" : "de plus ") + "par rapport à « " + echapper(nomScenario(liste[0])) +
          " » et change le bilan de " + signe(r.bilan.total - res[0].bilan.total) + " €/an.";
      }).join(" ");

    dessinerGraphique(liste, res);

    var classes = { info: "fr-alert--info", warning: "fr-alert--warning", error: "fr-alert--error" };
    var messages = [];
    res.forEach(function (r, i) {
      (r.avertissements || []).filter(function (x) { return x.niveau !== "info"; }).forEach(function (x) {
        messages.push({ niveau: x.niveau, texte: nomScenario(liste[i]) + " : " + x.texte });
      });
      (r.agro.notes || []).forEach(function (t) { messages.push({ niveau: "info", texte: nomScenario(liste[i]) + " : " + t }); });
    });
    $("avertissements").innerHTML = messages.map(function (x) {
      return '<div class="fr-alert ' + classes[x.niveau] + ' fr-alert--sm fr-mb-1w"><p>' + echapper(x.texte) + "</p></div>";
    }).join("");
  }

  /* Coût empilé (fixes + variables) à côté du gain, par scénario ; légende et info-bulles */
  function dessinerGraphique(liste, res) {
    var donnees = {
      labels: liste.map(nomScenario),
      datasets: [
        { label: "Charges fixes", data: res.map(function (r) { return Math.round(r.couts.fixes); }), backgroundColor: BLEU,
          stack: "cout", borderColor: "#ffffff", borderWidth: { top: 2 } },
        { label: "Charges variables", data: res.map(function (r) { return Math.round(r.couts.variables); }), backgroundColor: BLEU_CLAIR,
          stack: "cout", borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: false },
        { label: "Gain lié à l'irrigation", data: res.map(function (r) { return Math.round(r.gain.total); }), backgroundColor: VERT,
          stack: "gain", borderRadius: { topLeft: 4, topRight: 4 } }
      ]
    };
    if (graphique) { graphique.data = donnees; graphique.update(); return; }
    graphique = new Chart($("graphique-trajectoires"), {
      type: "bar", data: donnees,
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
        datasets: { bar: { barPercentage: 0.8, categoryPercentage: 0.6 } },
        scales: {
          x: { stacked: true, ticks: { color: TEXTE }, grid: { display: false } },
          y: { stacked: true, title: { display: true, text: "€/an", color: TEXTE },
               ticks: { color: TEXTE, callback: function (v) { return fmt(v, 0); } }, grid: { color: "#e5e5e5" } }
        },
        plugins: {
          legend: { position: "top", align: "start", labels: { color: TEXTE, boxWidth: 12, boxHeight: 12 } },
          tooltip: { callbacks: { label: function (c) { return c.dataset.label + " : " + fmt(c.parsed.y, 0) + " €/an"; } } }
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initialiser();
    document.getElementById("formulaire-trajectoires").addEventListener("change", function (ev) {
      if (ev.target.id === "commune-recherche") { return; }
      planifier();
    });
    $("ajouter-s3").addEventListener("click", function () {
      $("colonne-s3").hidden = false;
      this.parentElement.hidden = true;
      planifier();
    });
    $("retirer-s3").addEventListener("click", function () {
      $("colonne-s3").hidden = true;
      $("ajouter-s3").parentElement.hidden = false;
      planifier();
    });
    recherche = new RechercheCommune(function () { planifier(); });
    recherche.preselectionner(PAGE.defaut.commune, PAGE.defaut.departement);
  });
})();
