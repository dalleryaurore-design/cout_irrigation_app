/* =========================================================================
   Recherche de commune (API Découpage administratif) et agence de l'eau
   déduite du département, pour le volet Comparaison de trajectoires. Même comportement que le formulaire de simulation d'une
   parcelle (static/js/projet.js).
   Champs attendus : #commune-recherche, #commune-bouton, #commune-suggestions,
   #commune-etat et la liste #agence.
   ========================================================================= */
(function (global) {
  "use strict";

  var API_GEO = "https://geo.api.gouv.fr/communes";
  var CHAMPS = "nom,code,codeDepartement,codesPostaux,centre";
  var $ = function (id) { return document.getElementById(id); };

  function chercher(saisie) {
    var q = saisie.trim();
    if (q.length < 2) { return Promise.resolve([]); }
    var url = /^\d{4,5}$/.test(q)
      ? API_GEO + "?codePostal=" + encodeURIComponent(q) + "&fields=" + CHAMPS + "&limit=10"
      : API_GEO + "?nom=" + encodeURIComponent(q) + "&fields=" + CHAMPS + "&boost=population&limit=10";
    return fetch(url).then(function (r) {
      if (!r.ok) { throw new Error("service indisponible"); }
      return r.json();
    });
  }

  /* surChoix(commune) est appelé quand une commune est retenue (après mise à jour de l'agence) */
  function RechercheCommune(surChoix) {
    var self = this;
    this.commune = null;
    this.surChoix = surChoix || function () {};
    var champ = $("commune-recherche"), ul = $("commune-suggestions"), minuterie = null;

    function afficher(liste) {
      ul.innerHTML = "";
      ul.hidden = !liste.length;
      champ.setAttribute("aria-expanded", liste.length ? "true" : "false");
      liste.forEach(function (c) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.innerHTML = c.nom + ' <span class="suggestion__dep">(' + c.codeDepartement +
          (c.codesPostaux && c.codesPostaux.length ? " – " + c.codesPostaux[0] : "") + ")</span>";
        li.addEventListener("click", function () { self.choisir(c); });
        ul.appendChild(li);
      });
    }
    function indisponible() {
      $("commune-etat").textContent = "Recherche de commune indisponible (accès à geo.api.gouv.fr). " +
        "Les calculs restent possibles avec les valeurs du référentiel.";
    }
    champ.addEventListener("input", function () {
      clearTimeout(minuterie);
      minuterie = setTimeout(function () { chercher(champ.value).then(afficher).catch(indisponible); }, 250);
    });
    champ.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { ul.hidden = true; }
      if (ev.key === "Enter") {
        ev.preventDefault();
        var premier = ul.querySelector("li");
        if (premier && !ul.hidden) { premier.click(); }
      }
    });
    $("commune-bouton").addEventListener("click", function () {
      chercher(champ.value).then(function (l) {
        if (l.length === 1) { self.choisir(l[0]); } else { afficher(l); }
      }).catch(indisponible);
    });
    document.addEventListener("click", function (ev) {
      if (!ev.target.closest || !ev.target.closest(".recherche-commune")) { ul.hidden = true; }
    });
  }

  RechercheCommune.prototype.choisir = function (c) {
    var self = this;
    this.commune = { code: c.code, nom: c.nom, departement: c.codeDepartement,
                     centre: c.centre ? c.centre.coordinates : null, contour: null };
    $("commune-recherche").value = c.nom + " (" + c.codeDepartement + ")";
    $("commune-suggestions").hidden = true;
    $("commune-etat").textContent = "";
    return fetch("/api/departement/" + c.codeDepartement).then(function (r) { return r.json(); })
      .then(function (d) { if (d && d.agence) { $("agence").value = d.agence; } })
      .catch(function () { })
      .then(function () { self.surChoix(self.commune); });
  };

  /* Pré-sélection d'une commune par son nom ou son code postal (premier résultat du département) */
  RechercheCommune.prototype.preselectionner = function (saisie, departement) {
    var self = this;
    return chercher(saisie).then(function (l) {
      var c = l.filter(function (v) { return !departement || v.codeDepartement === departement; })[0] || l[0];
      if (c) { return self.choisir(c); }
      self.surChoix(null);
    }).catch(function () { self.surChoix(null); });
  };

  global.RechercheCommune = RechercheCommune;
})(window);
