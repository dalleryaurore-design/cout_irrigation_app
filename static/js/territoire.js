/* =========================================================================
   Diagnostic du territoire : affichage de la vue synthétique renvoyée par la
   simulation (moteur/territoire.py, clé « vue ») — eaux superficielles et
   souterraines, sol, usages, potentiel des types d'accès à l'eau et
   projections hydroclimatiques, avec leurs graphiques (Chart.js).
   ========================================================================= */
(function (global) {
  "use strict";

  var TEXTE = "#3a3a3a", GRILLE = "#e5e5e5", GRIS = "#929292";
  var COULEURS = {
    alerte: "#FFB224", alerte_renforcee: "#E4572E", crise: "#8E1B1B",
    besoin: "#000091", bilan_ete: "#E4572E", excedent: "#0063CB",
    qmna: "#000091", debit_ete: "#E4572E", debit_hiver: "#6A9FD8", sau: "#18753C", reste: "#E5E5E5"
  };
  var ETATS = { favorable: "Favorable", defavorable: "Défavorable", vigilance: "Vigilance" };
  var graphiques = [], compteur = 0;

  function fmt(v, dec) {
    if (v === null || v === undefined || isNaN(v)) { return "–"; }
    return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: dec === undefined ? 0 : dec }).format(v);
  }
  function signe(v) { return (v > 0 ? "+" : "") + fmt(v); }
  function echapper(t) {
    return String(t === undefined || t === null ? "" : t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  /* Valeur soulignée avec info-bulle DSFR (source et méthode) */
  function sourcee(valeur, bulle, classe) {
    if (!bulle) { return '<span class="' + (classe || "") + '">' + echapper(valeur) + "</span>"; }
    var id = "diag-tt-" + (++compteur);
    return '<span class="valeur-sourcee' + (classe ? " " + classe : "") + '" tabindex="0" aria-describedby="' + id + '">' + echapper(valeur) +
      '</span><span class="fr-tooltip fr-placement" id="' + id + '" role="tooltip" aria-hidden="true">' +
      echapper(bulle) + "</span>";
  }
  function canevas(id, libelle, classe) {
    return '<div class="diag-graphe' + (classe ? " " + classe : "") + '"><canvas id="' + id +
      '" role="img" aria-label="' + echapper(libelle) + '"></canvas></div>';
  }
  function carre(titre, corps, classe) {
    return '<div class="diag-carre' + (classe ? " " + classe : "") + '"><h3 class="diag-carre__titre">' +
      echapper(titre) + "</h3>" + corps + "</div>";
  }
  function zre(z) {
    return '<p class="diag-ligne">Zone de répartition des eaux : ' +
      sourcee(ETATS[z.niveau], z.bulle + " Part de la commune : " + fmt(z.part * 100) + " %.", "diag-etat diag-etat--" + z.niveau) + "</p>";
  }

  /* ------------------------------------------------------------- Graphiques */
  /* Valeur affichée au bout de chaque barre (barres non empilées) */
  var etiquettes = {
    id: "etiquettesDiag",
    afterDatasetsDraw: function (c) {
      if (c.config.options.empile) { return; }
      var ctx = c.ctx;
      ctx.save();
      ctx.font = "600 10px Marianne, Arial, sans-serif";
      ctx.fillStyle = TEXTE;
      ctx.textAlign = "center";
      c.data.datasets.forEach(function (ds, i) {
        var meta = c.getDatasetMeta(i);
        if (meta.hidden) { return; }
        meta.data.forEach(function (barre, j) {
          var v = ds.data[j];
          if (v === null || v === undefined) { return; }
          var positif = v >= 0;
          ctx.textBaseline = positif ? "bottom" : "top";
          ctx.fillText((c.config.options.unitePct ? signe(v) : fmt(v)), barre.x, barre.y + (positif ? -2 : 2));
        });
      });
      ctx.restore();
    }
  };

  function barres(id, libelles, series, unite, options) {
    var el = document.getElementById(id);
    if (!el || !global.Chart) { return; }
    options = options || {};
    var empile = !!options.empile;
    graphiques.push(new global.Chart(el, {
      type: "bar",
      data: {
        labels: libelles,
        datasets: series.map(function (s) {
          return { label: s.libelle, data: s.valeurs, backgroundColor: s.couleur, borderColor: s.couleur,
                   borderWidth: 0, barPercentage: 0.8, categoryPercentage: series.length > 1 && !empile ? 0.8 : 0.6 };
        })
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 200 },
        empile: empile, unitePct: unite === "%",
        layout: { padding: { top: empile ? 4 : 16 } },
        scales: {
          x: { stacked: empile, ticks: { color: TEXTE, font: { size: 10 }, maxRotation: 0, autoSkip: false }, grid: { display: false } },
          y: { stacked: empile, beginAtZero: true, grace: empile ? 0 : "12%",
               title: { display: true, text: options.titreY || unite, color: TEXTE, font: { size: 10 } },
               ticks: { color: TEXTE, font: { size: 10 }, precision: 0, callback: function (v) { return fmt(v); } },
               grid: { color: GRILLE }, border: { color: GRIS } }
        },
        plugins: {
          legend: { display: series.length > 1, position: "bottom",
                    labels: { color: TEXTE, font: { size: 10 }, boxWidth: 10, boxHeight: 10 } },
          tooltip: { callbacks: { label: function (ctx) {
            return ctx.dataset.label + " : " + (unite === "%" ? signe(ctx.parsed.y) : fmt(ctx.parsed.y, 1)) + " " + unite;
          } } }
        }
      },
      plugins: [etiquettes]
    }));
  }

  function graphiqueRestrictions(id, r) {
    barres(id, r.annees, [
      { libelle: "Alerte", valeurs: r.alerte, couleur: COULEURS.alerte },
      { libelle: "Alerte renforcée", valeurs: r.alerte_renforcee, couleur: COULEURS.alerte_renforcee },
      { libelle: "Crise", valeurs: r.crise, couleur: COULEURS.crise }
    ], "jours", { empile: true, titreY: r.moyenne ? "jours par an" : "jours" });
  }

  function anneau(id, part) {
    var el = document.getElementById(id);
    if (!el || !global.Chart) { return; }
    graphiques.push(new global.Chart(el, {
      type: "doughnut",
      data: { labels: ["SAU irriguée", "SAU non irriguée"],
              datasets: [{ data: [part, Math.max(100 - part, 0)], backgroundColor: [COULEURS.sau, COULEURS.reste], borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "68%", animation: { duration: 200 },
                 plugins: { legend: { display: false },
                            tooltip: { callbacks: { label: function (c) { return c.label + " : " + fmt(c.parsed, 1) + " %"; } } } } }
    }));
  }

  /* --------------------------------------------------------------- Blocs */
  function blocRestrictions(r, id, nom) {
    if (!r) { return '<p class="diag-ligne">Restrictions sécheresse, ' + nom + " : non renseigné.</p>"; }
    return '<p class="diag-sous-titre">' + sourcee("Restrictions sécheresse, " + nom, r.bulle) +
      (r.moyenne ? ' <span class="texte-mention">(moyenne 2016-2025)</span>' : "") + "</p>" +
      canevas(id, "Jours de restriction sécheresse par année, " + nom + " : alerte, alerte renforcée, crise");
  }

  function blocSuperficielle(v) {
    var liste = v.cours_eau.map(function (x) {
      return "<li>" + echapper(x.libelle) + " : " + sourcee(x.valeur, x.bulle, "diag-valeur") + "</li>";
    }).join("");
    return carre("Eau superficielle",
      '<ul class="diag-liste">' + liste + "</ul>" + zre(v.zre) + blocRestrictions(v.restrictions, "diag-restr-sup", "eaux superficielles"),
      "diag-carre--eau");
  }

  function blocSouterraine(v) {
    return carre("Eau souterraine",
      '<ul class="diag-liste"><li>Première nappe : ' + sourcee(v.nappe.valeur, v.nappe.bulle, "diag-valeur") + "</li></ul>" +
      zre(v.zre) + blocRestrictions(v.restrictions, "diag-restr-sou", "eaux souterraines"),
      "diag-carre--eau");
  }

  function blocSol(v) {
    var corps = "";
    if (v.ru) {
      var classe = v.ru.classe || "";
      corps += '<p class="diag-ligne">Réserve utile du sol : ' + sourcee(v.ru.mm ? v.ru.mm + " mm" : v.ru.valeur, v.ru.bulle, "diag-valeur") +
        (classe ? ' = <strong class="diag-classe diag-classe--' + (classe === "élevée" ? "elevee" : classe) + '">' + echapper(classe) + "</strong>" : "") +
        (v.profondeur ? ' <span class="texte-mention">(profondeur = ' + sourcee(v.profondeur.valeur, v.profondeur.bulle) + ")</span>" : "") + "</p>";
    } else {
      corps += '<p class="diag-ligne">Réserve utile du sol : non disponible.</p>';
    }
    if (v.formation) {
      corps += '<p class="diag-ligne">Formation géologique affleurante : ' +
        sourcee(v.formation.nom || v.formation.valeur, v.formation.bulle, "diag-valeur") +
        ' <span class="texte-mention">(' + echapper(v.formation.valeur) + ")</span></p>" +
        (v.formation.signification ? '<p class="diag-explication">Ce que cela signifie : ' + echapper(v.formation.signification) + "</p>" : "");
    }
    return carre("Sol", corps);
  }

  function blocUsages(v) {
    var gauche;
    if (v.sau_irriguee !== null && v.sau_irriguee !== undefined) {
      gauche = '<div class="diag-anneau">' + canevas("diag-sau", "Part de la SAU irriguée en 2020 : " + fmt(v.sau_irriguee, 1) + " %", "diag-graphe--anneau") +
        '<span class="diag-anneau__valeur">' + fmt(v.sau_irriguee, 1) + " %</span></div>";
    } else {
      gauche = '<p class="diag-ligne">' + (v.secret ? "Secret statistique" : "Non renseignée") + "</p>";
    }
    var ouvrages = v.ouvrages.map(function (x) {
      return "<li>" + echapper(x.libelle) + " : " + sourcee(x.valeur, x.bulle, "diag-valeur") + "</li>";
    }).join("");
    return carre("Usages",
      '<div class="diag-usages"><div class="diag-usages__sau"><p class="diag-sous-titre">' +
      sourcee("Part de la SAU irriguée (2020)", v.bulle) + "</p>" + gauche + "</div>" +
      '<div class="diag-usages__ouvrages"><p class="diag-sous-titre">Ouvrages dans la commune</p><ul class="diag-liste">' +
      ouvrages + "</ul></div></div>");
  }

  function blocAcces(v) {
    var liste = v.options.map(function (o) {
      return '<li><strong class="diag-acces diag-acces--' + o.niveau + '">' + echapper(o.source) + "</strong>" +
        (o.retenue ? " <em>(simulé)</em>" : "") + ' <span class="diag-motifs">— ' + echapper(o.motifs.join(" ; ")) + "</span></li>";
    }).join("");
    var simule = v.options.filter(function (o) { return o.retenue && o.source === v.proposee; }).length;
    return carre("Potentiel des types d'accès à l'eau",
      '<ul class="diag-liste diag-liste--acces">' + liste + "</ul>" +
      '<p class="diag-legende"><span class="diag-acces--favorable">■ favorable</span> <span class="diag-acces--vigilance">■ à vérifier</span> ' +
      '<span class="diag-acces--defavorable">■ défavorable</span></p>' +
      (v.proposee && !simule ? '<button type="button" class="fr-btn fr-btn--sm fr-btn--secondary fr-mt-1w" id="territoire-appliquer" data-source="' +
        echapper(v.proposee) + '">Simuler avec « ' + echapper(v.proposee) + " »</button>" : "") +
      '<p class="fr-text--xs texte-mention fr-mt-1w fr-mb-0">' + echapper(v.avertissement) + "</p>");
  }

  function aDesValeurs(serie) { return serie && serie.some(function (x) { return x !== null && x !== undefined; }); }

  function blocProjections(p) {
    var cases = [];
    function cas(id, titre, bulle, libelle) {
      cases.push('<div class="diag-projection"><p class="diag-sous-titre">' + sourcee(titre, bulle) + "</p>" + canevas(id, libelle) + "</div>");
    }
    if (aDesValeurs(p.besoin)) { cas("diag-besoin", "Besoin en eau" + (p.culture ? ", " + p.culture.toLowerCase() : ""), p.bulles.besoin, "Évolution du besoin en eau de la culture par horizon (mm)"); }
    if (aDesValeurs(p.bilan_ete)) { cas("diag-bilan-ete", "Bilan climatique avril-septembre (P − ETP)", p.bulles.bilan_ete, "Bilan climatique d'avril à septembre par horizon (mm)"); }
    if (aDesValeurs(p.excedent_hiver)) { cas("diag-excedent", "Excédent hivernal (octobre-mars)", p.bulles.excedent_hiver, "Excédent hivernal par horizon (mm)"); }
    if (p.debits) { cas("diag-debits", "Débits d'étiage, d'été et d'hiver", p.bulles.debits, "Évolution des débits d'étiage, d'été et d'hiver par horizon (%)"); }
    if (!cases.length) { return carre("Projections hydroclimatiques", '<p class="diag-ligne">Aucune projection disponible pour cette commune.</p>'); }
    return carre("Projections hydroclimatiques",
      '<div class="diag-projections">' + cases.join("") + "</div>" +
      '<p class="fr-text--xs texte-mention fr-mt-1w fr-mb-0">' + echapper(p.avertissement) + "</p>");
  }

  function dessinerProjections(p) {
    var h = p.horizons;
    if (aDesValeurs(p.besoin)) { barres("diag-besoin", h, [{ libelle: "Besoin en eau", valeurs: p.besoin, couleur: COULEURS.besoin }], "mm"); }
    if (aDesValeurs(p.bilan_ete)) { barres("diag-bilan-ete", h, [{ libelle: "P − ETP avril-septembre", valeurs: p.bilan_ete, couleur: COULEURS.bilan_ete }], "mm"); }
    if (aDesValeurs(p.excedent_hiver)) { barres("diag-excedent", h, [{ libelle: "Excédent hivernal", valeurs: p.excedent_hiver, couleur: COULEURS.excedent }], "mm"); }
    if (p.debits) {
      barres("diag-debits", h, [
        { libelle: "Étiage (QMNA)", valeurs: p.debits.qmna, couleur: COULEURS.qmna },
        { libelle: "Été (juin-août)", valeurs: p.debits.ete, couleur: COULEURS.debit_ete },
        { libelle: "Hiver (déc.-févr.)", valeurs: p.debits.hiver, couleur: COULEURS.debit_hiver }
      ], "%", { titreY: "% vs 1976-2005" });
    }
  }

  /* ------------------------------------------------------------- Entrée */
  /* t : diagnostic de /api/simulation ; appliquer(source) : simuler avec le type d'accès proposé */
  function afficher(conteneur, t, appliquer) {
    graphiques.forEach(function (g) { g.destroy(); });
    graphiques = [];
    var el = document.getElementById(conteneur);
    if (!el) { return; }
    if (!t || !t.disponible || !t.vue) {
      el.innerHTML = '<p class="fr-text--sm">' + echapper(t && t.message ? t.message : "Sélectionnez une commune.") + "</p>";
      return;
    }
    var v = t.vue;
    el.innerHTML =
      '<div class="diag-grille">' + blocSuperficielle(v.superficielle) + blocSouterraine(v.souterraine) + "</div>" +
      (v.zre_noms ? '<p class="fr-text--xs texte-mention diag-zre-noms">ZRE concernées : ' + echapper(v.zre_noms) + "</p>" : "") +
      '<div class="diag-grille">' + blocSol(v.sol) + blocUsages(v.usages) + "</div>" +
      blocAcces(v.acces) + blocProjections(v.projections);

    if (v.superficielle.restrictions) { graphiqueRestrictions("diag-restr-sup", v.superficielle.restrictions); }
    if (v.souterraine.restrictions) { graphiqueRestrictions("diag-restr-sou", v.souterraine.restrictions); }
    if (v.usages.sau_irriguee !== null && v.usages.sau_irriguee !== undefined) { anneau("diag-sau", v.usages.sau_irriguee); }
    dessinerProjections(v.projections);

    var bouton = document.getElementById("territoire-appliquer");
    if (bouton && appliquer) {
      bouton.addEventListener("click", function () { appliquer(bouton.dataset.source); });
    }
  }

  global.Territoire = { afficher: afficher };
})(window);
