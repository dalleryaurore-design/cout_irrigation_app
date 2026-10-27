/* =========================================================================
   Analyse financière d'un système d'irrigation — simulation d'une parcelle
   (volets « Cas personnel – parcelle » et « Simulations exemples »).
   Enchaînement : saisie ► POST /api/simulation ► affichage des résultats,
   mise à jour des cellules calculées et du graphique en cascade.
   Les rendements et le besoin en eau proviennent des cartes lorsque la culture en
   dispose, le besoin en eau par défaut du bilan hydrique de la méthode SGPE.
   Volet Cas personnel (PAGE.libre) : rendements, besoin en eau, réserve utile du
   sol, redevance et coûts (tableau « Mes hypothèses ») se saisissent directement
   dans la page ; export Excel des variables, import, rapport PDF.
   ========================================================================= */
(function () {
  "use strict";

  var PAGE = JSON.parse(document.getElementById("donnees-page").textContent || "{}");
  var $ = function (id) { return document.getElementById(id); };
  /* saisies : entrées dont la valeur par défaut est calculée (réserve utile ru_mm, redevance_c_m3) */
  var etat = { commune: null, surcharges: {}, saisies: {}, dernier: null, nbUnitesManuel: false };
  var cascade = null, carteSimulation = null;

  /* ------------------------------------------------------------- Formats */
  function fmt(v, dec) {
    if (v === null || v === undefined || isNaN(v)) { return "–"; }
    return new Intl.NumberFormat("fr-FR", {
      minimumFractionDigits: dec === undefined ? 0 : dec,
      maximumFractionDigits: dec === undefined ? 0 : dec
    }).format(v);
  }
  function fmtS(v, dec) {
    if (v === null || v === undefined || isNaN(v)) { return "–"; }
    return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: dec === undefined ? 1 : dec }).format(v);
  }
  function euros(v, dec) { return fmt(v, dec) + " €"; }
  function pct(v, dec) { return fmt(v * 100, dec === undefined ? 1 : dec) + " %"; }
  function texte(id, t) { var e = $(id); if (e) { e.textContent = t; } }
  function html(id, t) { var e = $(id); if (e) { e.innerHTML = t; } }
  /* Bulle « i » d'un résultat agronomique : méthode retenue et sa source, puis valeurs des autres méthodes */
  var LIBELLES_SOURCE = { sgpe: "SGPE", carte: "MAELIA", reference: "Référentiel", saisie: "valeur saisie" };
  function echapper(t) {
    return String(t === undefined || t === null ? "" : t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function bulleMethodes(alternatives, source, detail, unite, dec) {
    var autres = alternatives.filter(function (x) { return !x.retenue; }).map(function (x) {
      return "<li>" + x.methode + " : " + fmt(x.valeur, dec) + " " + unite + "</li>";
    }).join("");
    return "<strong>Méthode retenue : " + (LIBELLES_SOURCE[source] || source) + "</strong><br>" + echapper(detail) +
      (autres ? "<br><strong>Autres méthodes</strong><ul>" + autres + "</ul>" : "<br>Aucune autre méthode disponible.");
  }

  /* ------------------------------------------------------- Export CSV générique */
  function texteCellule(cellule) {
    var champ = cellule.querySelector("input");
    if (champ) { return champ.value; }
    var clone = cellule.cloneNode(true);
    clone.querySelectorAll(".fr-tooltip").forEach(function (t) { t.remove(); });
    return clone.textContent.replace(/\s+/g, " ").trim();
  }

  function telechargerCSV(lignes, nom) {
    var csv = "﻿" + lignes.map(function (l) {
      return l.map(function (c) {
        var t = String(c === undefined || c === null ? "" : c).replace(/"/g, '""');
        return /[";\n]/.test(t) ? '"' + t + '"' : t;
      }).join(";");
    }).join("\r\n");
    var url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    var a = document.createElement("a");
    a.href = url;
    a.download = (nom || "tableau") + ".csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function exporterTableauCSV(table, nom) {
    var lignes = [];
    table.querySelectorAll("thead tr, tbody tr, tfoot tr").forEach(function (tr) {
      lignes.push(Array.prototype.map.call(tr.querySelectorAll("th, td"), texteCellule));
    });
    telechargerCSV(lignes, nom);
  }

  function brancherExportsTableaux() {
    document.addEventListener("click", function (ev) {
      var bouton = ev.target.closest(".bouton-export-tableau");
      if (!bouton) { return; }
      var table = document.getElementById(bouton.dataset.cible);
      if (!table) { return; }
      exporterTableauCSV(table, bouton.dataset.cible);
    });
  }

  /* ==========================================================================
     1. Recherche de commune (API Découpage administratif)
     ========================================================================== */
  var API_GEO = "https://geo.api.gouv.fr/communes";
  var CHAMPS = "nom,code,codeDepartement,codesPostaux,centre,contour,population";
  var minuterieSuggestions = null;

  function chercherCommunes(saisie) {
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

  function afficherSuggestions(liste) {
    var ul = $("commune-suggestions");
    ul.innerHTML = "";
    if (!liste.length) { ul.hidden = true; $("commune-recherche").setAttribute("aria-expanded", "false"); return; }
    liste.forEach(function (c) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.innerHTML = c.nom + ' <span class="suggestion__dep">(' + c.codeDepartement +
        (c.codesPostaux && c.codesPostaux.length ? " – " + c.codesPostaux[0] : "") + ")</span>";
      li.addEventListener("click", function () { choisirCommune(c); });
      ul.appendChild(li);
    });
    ul.hidden = false;
    $("commune-recherche").setAttribute("aria-expanded", "true");
  }

  function choisirCommune(c) {
    etat.commune = {
      code: c.code, nom: c.nom, departement: c.codeDepartement,
      centre: c.centre ? c.centre.coordinates : null, contour: c.contour || null
    };
    $("commune-recherche").value = c.nom + " (" + c.codeDepartement + ")";
    $("commune-suggestions").hidden = true;
    $("commune-recherche").setAttribute("aria-expanded", "false");
    texte("commune-etat", "");
    if (carteSimulation) { carteSimulation.montrer(etat.commune); }
    appliquerAgence(c.codeDepartement).then(simuler);
  }

  /* Agence de l'eau déduite du département (feuille « Departements » du référentiel) */
  function appliquerAgence(dep) {
    if (!dep) { return Promise.resolve(); }
    return fetch("/api/departement/" + dep).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.agence) {
        $("agence").value = d.agence;
        var aide = $("agence-aide");
        if (aide) {
          aide.textContent = "Déduite du département " + dep + (d.nom ? " (" + d.nom + ")" : "") +
            (d.precision ? " — " + d.precision : "") + ". Modifiable si la commune relève d'un autre bassin.";
        }
      }
    }).catch(function () { });
  }

  function preparerRecherche() {
    var champ = $("commune-recherche");
    champ.addEventListener("input", function () {
      clearTimeout(minuterieSuggestions);
      var v = champ.value;
      minuterieSuggestions = setTimeout(function () {
        chercherCommunes(v).then(afficherSuggestions).catch(function () {
          texte("commune-etat", "Recherche de commune indisponible (accès à geo.api.gouv.fr). " +
            "Les calculs restent possibles, sans lecture des cartes.");
        });
      }, 250);
    });
    champ.addEventListener("keydown", function (ev) {
      var ul = $("commune-suggestions");
      if (ev.key === "Escape") { ul.hidden = true; }
      if (ev.key === "Enter") {
        ev.preventDefault();
        var premier = ul.querySelector("li");
        if (premier && !ul.hidden) { premier.click(); }
      }
    });
    $("commune-bouton").addEventListener("click", function () {
      chercherCommunes(champ.value).then(function (l) {
        if (l.length === 1) { choisirCommune(l[0]); } else { afficherSuggestions(l); }
      }).catch(function () {
        texte("commune-etat", "Recherche de commune indisponible (accès à geo.api.gouv.fr).");
      });
    });
    document.addEventListener("click", function (ev) {
      if (!ev.target.closest || !ev.target.closest(".recherche-commune")) { $("commune-suggestions").hidden = true; }
    });
  }

  /* ==========================================================================
     2. Lecture du formulaire et surcharges de paramètres
     ========================================================================== */
  function entrees() {
    var retenue = document.querySelector('input[name="type-retenue"]:checked');
    return {
      ru_mm: etat.saisies.ru_mm === undefined ? null : etat.saisies.ru_mm,
      redevance_c_m3: etat.saisies.redevance_c_m3 === undefined ? null : etat.saisies.redevance_c_m3,
      methode_besoin: "auto",
      culture: $("culture").value,
      surface: parseFloat($("surface").value) || 0,
      source: $("source").value,
      equipement: $("equipement").value,
      agence: $("agence").value,
      zre: $("zre").checked,
      methode_rendement: $("rendement-sgpe") && $("rendement-sgpe").checked ? "sgpe" : "auto",
      profondeur_sol_m: etat.saisies.profondeur_sol_m === undefined ? null : etat.saisies.profondeur_sol_m,
      type_retenue: retenue ? retenue.value : "individuelle",
      nb_adherents: parseInt($("nb-adherents").value, 10) || 1,
      capacite_auto: $("capacite-auto").checked,
      capacite: $("capacite-auto").checked ? null : (parseFloat($("capacite").value) || null),
      deja_amorti: $("deja-amorti").checked,
      deja_amorti_equipement: $("deja-amorti-equipement").checked,
      nb_unites: (etat.nbUnitesManuel && $("nb-unites").value) ? parseInt($("nb-unites").value, 10) : null,
      prix_vente: parseFloat($("prix-vente").value) || null,
      subvention_equipement_pct: nombreOuNull($("subvention-equipement").value),
      subvention_acces_pct: nombreOuNull($("subvention").value)
    };
  }

  function nombreOuNull(v) { var n = parseFloat(v); return isNaN(n) ? null : n; }

  /* Subvention publique (onglet Simulation) : pré-remplie avec le taux par défaut du référentiel, propre au type
     d'accès pour les infrastructures (45 % pour le forage, taux général sinon), tant qu'elle n'a pas été saisie. */
  var SUBVENTIONS = PAGE.subventions || { equipement: 0, acces: {} };

  function subventionsParDefaut(forcer) {
    if (forcer || !etat.subvEquipementManuel) { $("subvention-equipement").value = SUBVENTIONS.equipement; }
    var s = SUBVENTIONS.acces[$("source").value];
    if ((forcer || !etat.subvAccesManuel) && s !== undefined) { $("subvention").value = s; }
    if (forcer) { etat.subvEquipementManuel = etat.subvAccesManuel = false; }
    $("subvention-equipement").classList.toggle("champ-param--modifie", !!etat.subvEquipementManuel);
    $("subvention").classList.toggle("champ-param--modifie", !!etat.subvAccesManuel);
  }

  function surchargeDepuisChamp(champ) {
    var cle = champ.dataset.cle;
    if (!cle) { return; }
    var v = parseFloat(champ.value);
    var defaut = parseFloat(champ.dataset.defaut);
    var modifie = !isNaN(v) && !(!isNaN(defaut) && Math.abs(v - defaut) < 1e-9);
    /* Une valeur égale au référentiel (ou une case vidée) n'est pas une modification */
    if (!modifie) { delete etat.surcharges[cle]; }
    else { etat.surcharges[cle] = champ.dataset.pct === "1" ? v / 100 : v; }
    if (isNaN(v) && !isNaN(defaut)) { champ.value = champ.dataset.defaut; }
    champ.classList.toggle("champ-param--modifie", modifie);
  }

  /* Une même variable peut figurer deux fois (durée de vie de l'accordéon et du tableau) : les autres
     champs de la même clé reprennent la valeur. */
  function synchroniserChamps(source) {
    document.querySelectorAll(".champ-param[data-cle]").forEach(function (champ) {
      if (champ === source || champ === document.activeElement) { return; }
      var cle = champ.dataset.cle, s = etat.surcharges[cle];
      if (s === undefined) {
        champ.value = champ.dataset.defaut;
      } else {
        champ.value = champ.dataset.pct === "1" ? Math.round(s * 1e6) / 1e4 : s;
      }
      champ.classList.toggle("champ-param--modifie", s !== undefined);
    });
  }

  function brancherParametres() {
    document.querySelectorAll(".champ-param").forEach(function (champ) {
      if (champ.dataset.defaut === undefined) { champ.dataset.defaut = champ.value; }
      var ev = champ.type === "range" ? "input" : "change";
      champ.addEventListener(ev, function () {
        surchargeDepuisChamp(champ);
        synchroniserChamps(champ);
        planifier();
      });
    });
    $("reinitialiser").addEventListener("click", function () {
      etat.surcharges = {};
      etat.saisies = {};
      document.querySelectorAll(".champ-param").forEach(function (champ) {
        champ.value = champ.dataset.defaut;
        champ.classList.remove("champ-param--modifie");
        champ.dispatchEvent(new Event("input", { bubbles: true }));
      });
      document.querySelectorAll(".duree-vie-affichee").forEach(function (cellule) {
        cellule.textContent = cellule.dataset.defaut;
        cellule.classList.remove("champ-param--modifie");
      });
      if (majDureeVieEquipementSim) { majDureeVieEquipementSim(); }
      if (majDureeVieBassineSim) { majDureeVieBassineSim(); }
      etat.nbUnitesManuel = false;
      prixParDefaut();
      subventionsParDefaut(true);
      synchroniserChamps(null);
      simuler();
    });
  }

  /* ==========================================================================
     2 bis. Durée de vie (amortissement) sous l'objet sélectionné (équipement,
     bassine) : une option à dérouler dans l'onglet Simulation, plutôt qu'une
     saisie ligne par ligne dans les tableaux des onglets Équipement / Accès.
     ========================================================================== */
  var DUREE_VIE_EQUIPEMENTS = PAGE.duree_vie_equipements || {};
  var DUREE_VIE_SOURCES = PAGE.duree_vie_sources || {};
  var majDureeVieEquipementSim = null, majDureeVieBassineSim = null;

  function brancherDureeVieObjet(opts) {
    var champNom = $(opts.idNom), champValeur = $(opts.idValeur), aide = $(opts.idAide);
    var selecteur = $(opts.idSelecteur);
    if (!champValeur || !selecteur) { return function () {}; }

    function objetCourant() { return opts.objetCourant ? opts.objetCourant() : selecteur.value; }

    /* Une ressource occupe plusieurs lignes du tableau d'accès : on cherche la cellule dans toutes. */
    function celluleDureeVie(nom) {
      var attribut = opts.feuille === "Equipement" ? "equipement" : "source";
      return document.querySelector(opts.selecteurTableau + ' tr[data-' + attribut + '="' + CSS.escape(nom) + '"] .duree-vie-affichee');
    }

    function majAffichage() {
      var nom = objetCourant();
      if (champNom) { champNom.textContent = nom || opts.nomGenerique; }
      var cle = opts.feuille + "|" + nom + "|" + "duree_vie";
      var actuelle = etat.surcharges[cle];
      var defaut = opts.defauts[nom];
      /* La case affiche la valeur par défaut de l'objet tant qu'elle n'a pas été modifiée */
      champValeur.value = actuelle !== undefined ? actuelle : (defaut !== undefined && defaut !== null ? defaut : "");
      champValeur.classList.toggle("champ-param--modifie", actuelle !== undefined);
      if (aide) {
        aide.textContent = defaut !== undefined
          ? "Valeur par défaut de « " + nom + " » : " + defaut + " ans."
          : "";
      }
    }

    function appliquer() {
      var nom = objetCourant();
      if (!nom) { return; }
      var cle = opts.feuille + "|" + nom + "|duree_vie";
      var brut = champValeur.value;
      var v = parseInt(brut, 10);
      var defaut = opts.defauts[nom];
      /* Une valeur égale au défaut (ou une case vidée) n'est pas une modification */
      var actif = brut !== "" && !isNaN(v) && v !== defaut;
      if (actif) { etat.surcharges[cle] = v; } else { delete etat.surcharges[cle]; }
      if (brut === "" && defaut !== undefined) { champValeur.value = defaut; }
      champValeur.classList.toggle("champ-param--modifie", actif);
      var cellule = celluleDureeVie(nom);
      if (cellule) {
        cellule.textContent = actif ? String(v) : cellule.dataset.defaut;
        cellule.classList.toggle("champ-param--modifie", actif);
      }
      synchroniserChamps(null);
      planifier();
    }

    champValeur.addEventListener("change", appliquer);
    selecteur.addEventListener("change", majAffichage);
    majAffichage();
    return majAffichage;
  }

  /* Prix de vente : prix de marché du référentiel pour la culture choisie */
  var PRIX = PAGE.prix_cultures || {};

  function prixParDefaut() {
    var p = (PRIX.referentiel || {})[$("culture").value];
    if (p !== undefined && p !== null) { $("prix-vente").value = p; }
  }

  /* Champs à valeur par défaut calculée (volet Cas personnel) : rendements, besoin en eau (surcharges
     Cultures|<culture>|code), réserve utile du sol et redevance (entrées de la simulation). Le champ
     affiche la valeur calculée tant qu'il n'est pas modifié ; vidé, il revient à cette valeur. */
  var DEFAUTS_CALCULES = {};   // id du champ -> dernière valeur calculée

  function cleChampCalcule(champ) {
    return champ.dataset.feuille ? champ.dataset.feuille + "|" + $("culture").value + "|" + champ.dataset.code : null;
  }

  function saisieChampCalcule(champ) {
    var cle = cleChampCalcule(champ);
    return cle ? etat.surcharges[cle] : etat.saisies[champ.dataset.code];
  }

  function arrondi(v, pas) {
    var dec = pas >= 1 ? 0 : Math.round(-Math.log10(pas));
    return Math.round(v * Math.pow(10, dec)) / Math.pow(10, dec);
  }

  function brancherChampsCalcules() {
    document.querySelectorAll(".champ-calcule").forEach(function (champ) {
      champ.addEventListener("change", function () {
        var v = parseFloat(champ.value), cle = cleChampCalcule(champ);
        var defaut = DEFAUTS_CALCULES[champ.id], pas = parseFloat(champ.dataset.pas) || 1;
        var modifie = !isNaN(v) && v >= 0 && !(defaut !== undefined && defaut !== null &&
          Math.abs(v - arrondi(defaut, pas)) < pas / 2);
        if (cle) {
          if (modifie) { etat.surcharges[cle] = v; } else { delete etat.surcharges[cle]; }
        } else if (modifie) { etat.saisies[champ.dataset.code] = v; } else { delete etat.saisies[champ.dataset.code]; }
        if (!modifie && defaut !== undefined && defaut !== null) { champ.value = arrondi(defaut, pas); }
        champ.classList.toggle("champ-param--modifie", modifie);
        planifier();
      });
    });
  }

  /* Valeur affichée d'un résultat : texte, ou champ de saisie (valeur saisie, sinon valeur calculée) */
  function valeurCalculee(id, defaut, pas) {
    var el = $(id);
    if (!el) { return; }
    if (el.tagName !== "INPUT") { el.textContent = fmt(defaut, pas >= 1 ? 0 : 1); return; }
    DEFAUTS_CALCULES[id] = defaut;
    var s = saisieChampCalcule(el);
    if (el !== document.activeElement) {
      el.value = s !== undefined ? s : (defaut === null || defaut === undefined ? "" : arrondi(defaut, pas));
    }
    el.classList.toggle("champ-param--modifie", s !== undefined);
  }

  /* ==========================================================================
     3. Blocs conditionnels
     ========================================================================== */
  var TYPE_SOURCE = {};
  Array.prototype.forEach.call($("source").options, function (o) { TYPE_SOURCE[o.value] = o.dataset.type; });

  var SURFACE_UNITAIRE = PAGE.surface_unitaire || {};

  function majBlocs() {
    var t = TYPE_SOURCE[$("source").value] || "";
    var estRetenue = t.indexOf("retenue") === 0;
    $("bloc-retenue").hidden = !estRetenue;
    var collective = document.querySelector('input[name="type-retenue"]:checked');
    $("bloc-adherents").hidden = !(estRetenue && collective && collective.value === "collective");
    $("capacite").disabled = $("capacite-auto").checked;

    var su = SURFACE_UNITAIRE[$("equipement").value];
    $("bloc-unites").hidden = !su;
    if (su && !etat.nbUnitesManuel) {
      var surface = parseFloat($("surface").value) || 0;
      $("nb-unites").value = Math.max(1, Math.ceil(surface / su));
      texte("nb-unites-aide", "Proposé pour " + fmt(surface, 0) + " ha, à raison de " + fmt(su, 0) +
        " ha par unité. Modifiable.");
    }
    if (majDureeVieEquipementSim) { majDureeVieEquipementSim(); }
    if (majDureeVieBassineSim) { majDureeVieBassineSim(); }
    majHypothesesVisibles();
  }

  /* Tableau « Mes hypothèses » : lignes de la culture, de l'équipement et de la ressource choisis,
     et paramètres généraux. */
  function majHypothesesVisibles() {
    var choix = { Cultures: $("culture").value, Equipement: $("equipement").value, Acces_ressource: $("source").value };
    document.querySelectorAll(".ligne-hypothese").forEach(function (tr) {
      var o = tr.dataset.objet;
      tr.hidden = !(o === choix[tr.dataset.feuille] || o === "Général");
    });
    document.querySelectorAll(".nom-objet").forEach(function (s) { s.textContent = choix[s.dataset.feuille] || ""; });
  }

  /* ==========================================================================
     4. Simulation
     ========================================================================== */
  var minuterie = null;
  var generationSimulation = 0;

  function indiquerChargement(actif) {
    var el = $("simulation-chargement");
    if (el) { el.hidden = !actif; }
    var section = $("resultats");
    if (section) { section.setAttribute("aria-busy", actif ? "true" : "false"); }
  }

  /* Corps commun à la simulation, au rapport PDF et à l'export Excel */
  function corpsRequete() {
    return { entrees: entrees(), surcharges: etat.surcharges, commune: etat.commune, libre: !!PAGE.libre };
  }

  function planifier() {
    clearTimeout(minuterie);
    generationSimulation += 1;
    indiquerChargement(true);
    minuterie = setTimeout(simuler, 220);
  }

  function simuler() {
    majBlocs();
    var ticket = ++generationSimulation;
    indiquerChargement(true);
    fetch("/api/simulation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpsRequete())
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (ticket !== generationSimulation) { return; }
      etat.dernier = res;
      afficher(res);
      indiquerChargement(false);
    }).catch(function (e) {
      if (ticket !== generationSimulation) { return; }
      indiquerChargement(false);
      html("avertissements", '<div class="fr-alert fr-alert--error fr-alert--sm"><p>Calcul impossible : ' +
        e.message + "</p></div>");
    });
  }

  /* ==========================================================================
     5. Affichage des résultats
     ========================================================================== */
  function afficher(res) {
    var a = res.agro, c = res.couts, d = res.dimensionnement;
    var defauts = a.defauts || {};

    /* --- Bilan agronomique (champs de saisie dans le volet Cas personnel) */
    var champSaisi = function (id) { var el = $(id); return el && el.tagName === "INPUT"; };
    valeurCalculee("agro-rdt-irr", champSaisi("agro-rdt-irr") ? defauts.rdt_irrigue : a.rdt_irrigue, 0.1);
    valeurCalculee("agro-rdt-plu", champSaisi("agro-rdt-plu") ? defauts.rdt_pluvial : a.rdt_pluvial, 0.1);
    valeurCalculee("agro-besoin", champSaisi("agro-besoin") ? defauts.besoin_mm : a.besoin_mm, 1);
    texte("agro-volume", fmt(a.volume_preleve, 0));

    /* --- Mes hypothèses : réserve utile du sol et redevance, valeurs par défaut calculées */
    var solRes = a.sol || {};
    valeurCalculee("saisie-ru", solRes.ru_defaut, 1);
    texte("ru-defaut", fmt(solRes.ru_defaut, 0));
    var carteSol = solRes.carte || {};
    texte("ru-defaut-tt", solRes.carte && carteSol.valeur !== null && carteSol.valeur !== undefined
      ? "Carte de la réserve utile des sols (0-200 cm) : moyenne de " + carteSol.n + " maille(s) de 1 km — " +
        carteSol.methode + "."
      : "Valeur par défaut du référentiel : commune non sélectionnée ou non couverte par la carte des sols.");
    valeurCalculee("saisie-profondeur", solRes.profondeur_defaut, 0.1);
    texte("profondeur-defaut", fmt(solRes.profondeur_defaut, 1));
    var carteProf = solRes.carte_profondeur || {};
    texte("profondeur-defaut-tt", carteProf.valeur !== null && carteProf.valeur !== undefined
      ? "Profondeur de sol de la BDGSF (classes 0,3 / 0,5 / 1 / 2 m) : moyenne de " + carteProf.n +
        " maille(s) de 1 km — " + carteProf.methode + "."
      : "Valeur par défaut du référentiel : commune non sélectionnée ou non couverte par la carte de profondeur.");
    valeurCalculee("saisie-redevance", res.redevance.taux_defaut, 0.01);
    texte("redevance-defaut", fmt(res.redevance.taux_defaut, 2));
    texte("redevance-defaut-tt", res.redevance.agence
      ? res.redevance.agence + ", catégorie " + res.redevance.categorie + " (" + (res.entrees.zre ? "ZRE" : "hors ZRE") +
        "), eaux " + res.redevance.origine + "s" + (res.redevance.incluse ? " — comprise dans le tarif de l'ASA." : ".")
      : "Agence de l'eau non déterminée : sélectionnez une commune.");
    /* Source retenue automatiquement (besoin : SGPE > MAELIA > référentiel ; rendements : MAELIA >
       référentiel, ou SGPE si la case « exploratoire » est cochée) et bulles « i » des autres méthodes */
    var caseSgpe = $("rendement-sgpe");
    if (caseSgpe) {
      caseSgpe.disabled = !(a.methodes_rendement || {}).sgpe;
      caseSgpe.parentNode.title = caseSgpe.disabled ? "Indisponible pour cette culture (Kc ou Ky non renseignés)." : "";
    }
    var sources = a.sources || {};
    var bulles = a.infobulles || {};
    [["agro-rdt-irr", "rdt_irrigue", "q/ha", 1], ["agro-rdt-plu", "rdt_pluvial", "q/ha", 1],
     ["agro-besoin", "besoin_mm", "mm", 0]].forEach(function (x) {
      html(x[0] + "-tt", bulleMethodes((a.alternatives || {})[x[1]] || [], sources[x[1]], bulles[x[1]], x[2], x[3]));
    });
    var libRdt = sources.rdt_irrigue === sources.rdt_pluvial ? LIBELLES_SOURCE[sources.rdt_irrigue]
      : LIBELLES_SOURCE[sources.rdt_irrigue] + " (irrigué), " + LIBELLES_SOURCE[sources.rdt_pluvial] + " (pluvial)";
    texte("agro-rdt-source", "Source : " + libRdt);
    texte("agro-besoin-source", "Source : " + LIBELLES_SOURCE[sources.besoin_mm]);
    texte("agro-volume-cpl", "Efficience du matériel : " + pct(a.efficience, 0));
    texte("agro-volume-tt", "Besoin (mm) × 10 × surface ÷ efficience d'application du matériel");

    var notes = a.notes || [];
    html("notes-agro", notes.length
      ? '<div class="fr-alert fr-alert--info fr-alert--sm"><p>' + notes.join("<br>") + "</p></div>" : "");

    /* --- Bilan économique */
    var tuile = $("tuile-bilan");
    tuile.classList.toggle("indicateur--positif", res.bilan.total >= 0);
    tuile.classList.toggle("indicateur--negatif", res.bilan.total < 0);
    texte("eco-bilan", (res.bilan.total >= 0 ? "+" : "−") + fmt(Math.abs(res.bilan.total), 0));
    var sb = res.bilan.sans_subvention.total;
    texte("eco-bilan-sans", (sb >= 0 ? "+" : "−") + fmt(Math.abs(sb), 0));
    texte("eco-cout", fmt(c.total, 0));
    texte("eco-cout-m3", fmt(c.c_par_m3, 1));
    texte("eco-cout-ha", fmt(c.par_ha, 0));
    texte("eco-fixes", fmt(c.fixes, 0));
    texte("eco-fixes-part", pct(c.part_fixes, 0));
    texte("eco-variables", fmt(c.variables, 0));
    var barre = $("eco-barre-fixes");
    if (barre) { barre.style.width = Math.round(c.part_fixes * 100) + "%"; }
    texte("eco-cout-sans", fmt(c.sans_subvention.total, 0));
    texte("eco-cout-sans-m3", fmt(c.sans_subvention.c_par_m3, 1));
    texte("eco-cout-sans-ha", fmt(c.sans_subvention.par_ha, 0));
    texte("eco-aide", fmt(c.aide_publique_annuelle, 0));
    texte("eco-gain", fmt(res.gain.total, 0));
    /* Δ rendement (q/ha) → t/ha (× 0,1) × prix (€/t) = gain à l'hectare, × surface = gain annuel */
    texte("eco-gain-cpl", fmtS(a.delta_rdt) + " q/ha = " + fmtS(a.delta_rdt * 0.1, 2) + " t/ha × " +
      fmtS(res.gain.prix) + " €/t = " + fmt(res.gain.par_ha, 0) + " €/ha × " +
      fmtS(res.entrees.surface) + " ha");
    texte("eco-gain-tt", "(rendement irrigué − rendement pluvial) × 0,1 × prix de vente × surface");
    texte("eco-rac", fmt(res.capex.reste_a_charge, 0));
    texte("eco-capex", fmt(res.capex.total, 0));
    texte("eco-subv", fmt(res.capex.total - res.capex.reste_a_charge, 0));
    var complementCapex = "";
    if (res.capex.deja_amorti && res.capex.deja_amorti_equipement) {
      complementCapex = "Matériel d'irrigation et accès à la ressource déjà amortis : aucun investissement compté, " +
        "seuls les coûts de fonctionnement subsistent.";
    } else if (res.capex.deja_amorti_equipement) {
      complementCapex = "Matériel d'irrigation déjà amorti : seul l'accès à la ressource est compté en investissement.";
    } else if (res.capex.deja_amorti) {
      complementCapex = "Accès à la ressource déjà amorti : seul le matériel d'irrigation est compté.";
    }
    texte("eco-capex-cpl", complementCapex);
    texte("eco-capex-tt", "Matériel d'irrigation (" + euros(res.capex.equipement, 0) + ") + accès à la ressource (" +
      euros(res.capex.acces_brut, 0) + "), avant subvention");

    /* --- Décomposition */
    c.postes.forEach(function (p) {
      texte("poste-" + p.cle, fmt(p.montant, 0));
      texte("poste-" + p.cle + "-part", pct(p.part, 1));
    });
    texte("poste-total", fmt(c.total, 0));

    var lignes = res.capex.detail_acces.map(function (x) {
      return "<tr><th scope=\"row\">" + x.poste + "</th><td class=\"num\">" + euros(x.montant, 0) + "</td></tr>";
    }).join("");
    var ligneSubvEquip = res.capex.subvention_equipement
      ? "<tr><th scope=\"row\">Subvention publique (matériel d'irrigation)</th><td class=\"num\">− " +
        euros(res.capex.subvention_equipement, 0) + "</td></tr>"
      : "";
    html("detail-capex",
      '<div class="fr-table fr-table--sm fr-table--no-caption">' +
      '<div class="tableau-barre-outils"><button type="button" class="fr-btn fr-btn--tertiary-no-outline ' +
      'fr-btn--sm fr-icon-download-line fr-btn--icon-left bouton-export-tableau" data-cible="detail-capex-tableau">' +
      "Exporter (CSV)</button></div>" +
      '<div class="fr-table__wrapper">' +
      '<div class="fr-table__container"><div class="fr-table__content"><table id="detail-capex-tableau">' +
      "<caption>Détail des investissements</caption><thead><tr><th scope=\"col\">Poste</th>" +
      "<th scope=\"col\" class=\"num\">Montant</th></tr></thead><tbody>" +
      "<tr class=\"ligne-reste-a-charge\"><th scope=\"row\"><strong>À la charge de l'agriculteur</strong></th>" +
      "<td class=\"num\"><strong>" + euros(res.capex.reste_a_charge, 0) + "</strong></td></tr>" +
      "<tr><th scope=\"row\">Matériel d'irrigation" +
      (d.nb_unites ? " (" + d.nb_unites + " unité" + (d.nb_unites > 1 ? "s" : "") + ")" : "") +
      "</th><td class=\"num\">" + euros(res.capex.equipement, 0) + "</td></tr>" + ligneSubvEquip + lignes +
      "<tr><th scope=\"row\">Subvention publique (accès à la ressource)</th><td class=\"num\">− " +
      euros(res.capex.subvention, 0) +
      "</td></tr></tbody><tfoot><tr><th scope=\"row\">Investissement total (avant subvention)</th><td class=\"num\">" +
      euros(res.capex.total, 0) + "</td></tr></tfoot></table></div></div></div></div>");

    /* --- Retenue : capacité retenue par le calcul */
    if (d.capacite !== null && d.capacite !== undefined) {
      if ($("capacite-auto").checked) { $("capacite").value = Math.round(d.capacite); }
      var msg = "Capacité " + fmt(d.capacite, 0) + " m³ · volume mobilisable " +
        fmt(d.volume_disponible, 0) + " m³ pour un besoin de " + fmt(a.volume_preleve, 0) + " m³.";
      var aide = $("capacite-auto-aide");
      if (aide) { aide.textContent = msg; }
    }

    /* --- Cascade */
    cascade.maj(res);

    /* --- Avertissements */
    var classes = { info: "fr-alert--info", warning: "fr-alert--warning", error: "fr-alert--error" };
    html("avertissements", (res.avertissements || []).map(function (x) {
      return '<div class="fr-alert ' + (classes[x.niveau] || "fr-alert--info") +
        ' fr-alert--sm fr-mb-1w"><p>' + x.texte + "</p></div>";
    }).join(""));

    majOnglets(res);
  }

  /* ==========================================================================
     6. Onglets de paramètres : cellules calculées, lignes actives, légendes
     ========================================================================== */
  function majOnglets(res) {
    var derives = res.derives || {};
    Object.keys(derives).forEach(function (id) {
      var el = $(id);
      if (!el) { return; }
      var f = el.dataset.format, v = derives[id];
      el.textContent = f === "pct" ? fmt(v * 100, 2) + " %"
        : (f === "kwh" || f === "eurom3") ? fmt(v, 3) : fmt(v, 0);
    });

    function activer(selecteur, valeur) {
      document.querySelectorAll(selecteur).forEach(function (tr) {
        tr.classList.toggle("ligne-active", tr.dataset.equipement === valeur ||
          tr.dataset.source === valeur || tr.dataset.agence === valeur);
      });
    }
    activer("#panel-equipement tbody tr[data-equipement]", res.entrees.equipement);
    activer("#panel-acces tbody tr[data-source]", res.entrees.source);
    activer("#panel-ressources tbody tr[data-agence]", res.redevance.agence);
    activer("#panel-ressources tbody tr[data-source]", res.entrees.source);

    var r = res.redevance;
    html("redevance-courante", r.agence
      ? "Situation simulée : <strong>" + r.agence + "</strong>, eaux " + r.origine + "s, catégorie " + r.categorie +
        " (" + (res.entrees.zre ? "ZRE" : "hors ZRE") + ") — taux retenu <strong>" + fmt(r.taux_c_m3, 2) +
        " c€/m³</strong>. " + (r.incluse
          ? "Redevance acquittée par le gestionnaire du réseau collectif (ASA) et comprise dans son tarif : elle n'est pas ajoutée."
          : r.due
          ? "Redevance due : " + euros(res.couts.postes.filter(function (p) { return p.cle === "redevance"; })[0].montant, 0) + "/an."
          : "Prélèvement inférieur au seuil d'assujettissement de " + fmt(r.seuil, 0) + " m³/an : redevance non due.") +
        (r.regle_retenue === "collinaire"
          ? " Retenue collinaire : tarif de catégorie 1 quelle que soit la localisation, y compris en ZRE (art. L213-10-9 du Code de l'environnement)."
          : r.regle_retenue === "pompage"
          ? " Retenue par pompage en ZRE : l'agence applique le taux hors ZRE au remplissage hivernal." : "")
      : "Sélectionnez une commune pour déterminer l'agence de l'eau.");

    var an = res.annualisation;
    texte("annuite-equipement-exemple", res.capex.deja_amorti_equipement
      ? "Matériel d'irrigation déjà amorti : ni l'annuité (qui aurait été de " +
        euros(an.equipement.annuite, 0) + "/an) ni la maintenance (" + euros(an.equipement.maintenance, 0) +
        "/an) ne sont comptées dans le bilan et la décomposition du coût."
      : "CAPEX " + euros(an.equipement.capex, 0) + (an.equipement.subvention
          ? " × (1 − " + pct(an.equipement.subvention, 0) + ") = " + euros(an.equipement.capex_net, 0)
          : "") + " × " +
        fmt(an.equipement.facteur * 100, 2) + " % = " + euros(an.equipement.annuite, 0) + "/an (taux " +
        pct(an.equipement.taux, 1) + ", durée " + fmt(an.equipement.duree, 0) + " ans), auxquels s'ajoutent " +
        euros(an.equipement.maintenance, 0) + "/an de maintenance.");
    texte("annuite-acces-exemple", an.acces.capex_brut
      ? "CAPEX " + euros(an.acces.capex_brut, 0) + " × (1 − " + pct(an.acces.subvention, 0) + ") = " +
        euros(an.acces.capex_net, 0) + " ; annuité " + euros(an.acces.annuite, 0) + "/an (taux " +
        pct(an.acces.taux, 1) + ", durée " + fmt(an.acces.duree_ouvrage, 0) + " ans pour l'ouvrage, " +
        (an.acces.capex_pompe_net ? fmt(an.acces.duree_pompe, 0) + " ans pour la station de pompage et " : "") +
        fmt(an.acces.duree_reseau, 0) + " ans pour le réseau)."
      : "Aucun investissement d'accès à la ressource dans la situation simulée (infrastructure déjà amortie ou " +
        "eau facturée au volume).");
  }

  /* ==========================================================================
     7. Onglets DSFR : rafraîchir les cartes quand un panneau devient visible
     ========================================================================== */
  function brancherOnglets() {
    var onglet = document.getElementById("tab-simulation");
    if (!onglet) { return; }
    /* Leaflet doit recalculer ses dimensions lorsque le panneau redevient visible. */
    onglet.addEventListener("click", function () {
      setTimeout(function () { if (carteSimulation) { carteSimulation.rafraichir(); } }, 80);
    });
  }

  /* ==========================================================================
     8. Pré-remplissage depuis un exemple
     ========================================================================== */
  function appliquerExemple(x) {
    if (!x) { return Promise.resolve(); }
    $("culture").value = x.culture;
    prixParDefaut();
    $("surface").value = x.surface;
    $("source").value = x.source;
    subventionsParDefaut(true);
    $("equipement").value = x.equipement;
    $("zre").checked = !!x.zre;
    if (x.retenue === "collective") {
      $("retenue-collective").checked = true;
      $("nb-adherents").value = x.nb_adherents || 10;
    } else {
      $("retenue-individuelle").checked = true;
    }
    majBlocs();
    if (x.nb_unites) { etat.nbUnitesManuel = true; $("nb-unites").value = x.nb_unites; }
    return appliquerAgence(x.departement).then(function () {
      return chercherCommunes(x.commune);
    }).then(function (liste) {
      var c = liste.filter(function (v) { return v.codeDepartement === x.departement; })[0] || liste[0];
      if (c) { choisirCommune(c); } else { simuler(); }
    }).catch(function () {
      if (x.lat && x.lon) {
        etat.commune = { code: "", nom: x.commune, departement: x.departement, centre: [x.lon, x.lat], contour: null };
        $("commune-recherche").value = x.commune + " (" + x.departement + ")";
        if (carteSimulation) { carteSimulation.montrer(etat.commune); }
        texte("commune-etat", "Commune positionnée sur ses coordonnées (service de recherche indisponible).");
      }
      simuler();
    });
  }

  /* ==========================================================================
     8 bis. Pré-remplissage par défaut (hors exemple) : commune et culture
     ========================================================================== */
  function preselectionnerDefaut(d) {
    if (!d || !d.commune) { simuler(); return Promise.resolve(); }
    if (d.culture) { $("culture").value = d.culture; prixParDefaut(); }
    return chercherCommunes(d.commune).then(function (liste) {
      var c = liste.filter(function (v) { return !d.departement || v.codeDepartement === d.departement; })[0] || liste[0];
      if (c) { choisirCommune(c); } else { simuler(); }
    }).catch(function () { simuler(); });
  }

  /* ==========================================================================
     8 ter. Cas personnel : rapport PDF, export et import des variables (Excel)
     ========================================================================== */
  function etatFichiers(t, erreur) {
    var el = $("etat-fichiers");
    if (!el) { return; }
    el.textContent = t || "";
    el.className = "fr-message" + (erreur ? " fr-message--error" : (t ? " fr-message--info" : ""));
  }

  function telechargerDepuisApi(url, nomDefaut, bouton) {
    bouton.disabled = true;
    etatFichiers("Préparation du fichier…");
    fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpsRequete()) })
      .then(function (r) {
        if (!r.ok) { throw new Error("réponse " + r.status); }
        var cd = r.headers.get("Content-Disposition") || "", m = /filename="([^"]+)"/.exec(cd);
        return r.blob().then(function (b) { return { blob: b, nom: m ? m[1] : nomDefaut }; });
      })
      .then(function (f) {
        var a = document.createElement("a"), lien = URL.createObjectURL(f.blob);
        a.href = lien;
        a.download = f.nom;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(lien); }, 1000);
        etatFichiers("");
      })
      .catch(function (e) { etatFichiers("Téléchargement impossible : " + e.message, true); })
      .then(function () { bouton.disabled = false; });
  }

  function cocher(nom, valeur) {
    var r = document.querySelector('input[name="' + nom + '"][value="' + valeur + '"]');
    if (r) { r.checked = true; }
  }

  /* Classeur relu par /api/variables-import : choix, commune et variables modifiées */
  function appliquerImport(d) {
    var x = d.entrees || {};
    var options = function (id, v) {
      return v && Array.prototype.some.call($(id).options, function (o) { return o.value === v; });
    };
    if (options("culture", x.culture)) { $("culture").value = x.culture; }
    prixParDefaut();
    if (x.prix_vente) { $("prix-vente").value = x.prix_vente; }
    if (x.surface) { $("surface").value = x.surface; }
    if (options("source", x.source)) { $("source").value = x.source; }
    if (options("equipement", x.equipement)) { $("equipement").value = x.equipement; }
    if (x.type_retenue) { cocher("type-retenue", x.type_retenue); }
    if (x.nb_adherents) { $("nb-adherents").value = x.nb_adherents; }
    $("capacite-auto").checked = x.capacite_auto !== false;
    if (x.capacite) { $("capacite").value = x.capacite; }
    $("deja-amorti").checked = !!x.deja_amorti;
    $("deja-amorti-equipement").checked = !!x.deja_amorti_equipement;
    $("zre").checked = !!x.zre;
    etat.nbUnitesManuel = !!x.nb_unites;
    if (x.nb_unites) { $("nb-unites").value = x.nb_unites; }
    $("rendement-sgpe").checked = x.methode_rendement === "sgpe";
    subventionsParDefaut(true);
    [["subvention_equipement_pct", "subvention-equipement", "subvEquipementManuel"],
     ["subvention_acces_pct", "subvention", "subvAccesManuel"]].forEach(function (c) {
      if (x[c[0]] !== null && x[c[0]] !== undefined) {
        $(c[1]).value = x[c[0]];
        etat[c[2]] = true;
        $(c[1]).classList.add("champ-param--modifie");
      }
    });
    etat.surcharges = d.surcharges || {};
    etat.saisies = {};
    ["ru_mm", "profondeur_sol_m", "redevance_c_m3"].forEach(function (cle) {
      if (x[cle] !== null && x[cle] !== undefined) { etat.saisies[cle] = x[cle]; }
    });
    synchroniserChamps(null);
    majBlocs();
    var c = d.commune || {};
    if (!c.code) {
      if (options("agence", x.agence)) { $("agence").value = x.agence; }
      simuler();
      return;
    }
    fetch(API_GEO + "/" + encodeURIComponent(c.code) + "?fields=" + CHAMPS)
      .then(function (r) { if (!r.ok) { throw new Error(); } return r.json(); })
      .then(function (g) {
        etat.commune = { code: g.code, nom: g.nom, departement: g.codeDepartement,
                         centre: g.centre ? g.centre.coordinates : null, contour: g.contour || null };
        $("commune-recherche").value = g.nom + " (" + g.codeDepartement + ")";
        if (carteSimulation) { carteSimulation.montrer(etat.commune); }
        return appliquerAgence(g.codeDepartement);
      })
      .catch(function () {
        texte("commune-etat", "Commune du classeur introuvable (" + (c.nom || c.code) + ") : recherchez-la à nouveau.");
      })
      .then(function () {
        /* L'agence enregistrée prime sur celle déduite du département (circonscription corrigée à la main) */
        if (options("agence", x.agence)) { $("agence").value = x.agence; }
        simuler();
      });
  }

  function brancherCasPersonnel() {
    if (!$("telecharger-pdf")) { return; }
    $("telecharger-pdf").addEventListener("click", function () {
      telechargerDepuisApi("/api/rapport-pdf", "irrigation-rapport.pdf", this);
    });
    $("telecharger-variables").addEventListener("click", function () {
      telechargerDepuisApi("/api/variables-excel", "irrigation-variables.xlsx", this);
    });
    $("importer-variables").addEventListener("click", function () { $("fichier-variables").click(); });
    $("fichier-variables").addEventListener("change", function () {
      var f = this.files[0];
      if (!f) { return; }
      var donnees = new FormData();
      donnees.append("fichier", f);
      etatFichiers("Lecture du classeur…");
      fetch("/api/variables-import", { method: "POST", body: donnees })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) { throw new Error(j.erreur); } return j; }); })
        .then(function (d) {
          appliquerImport(d);
          var n = Object.keys(d.surcharges || {}).length;
          etatFichiers("Classeur « " + f.name + " » importé : " + n + " variable" + (n > 1 ? "s" : "") +
            " modifiée" + (n > 1 ? "s" : "") + ".");
        })
        .catch(function (e) { etatFichiers(e.message || "Classeur illisible.", true); })
        .then(function () { $("fichier-variables").value = ""; });
    });
  }

  /* ==========================================================================
     9. Démarrage
     ========================================================================== */
  document.addEventListener("DOMContentLoaded", function () {
    carteSimulation = new Cartographie.CarteCommune("carte-simulation", PAGE.fond_carte !== false);
    cascade = new Cascade($("cascade"));
    preparerRecherche();
    brancherParametres();
    brancherOnglets();
    brancherExportsTableaux();
    brancherCasPersonnel();
    brancherChampsCalcules();
    majDureeVieEquipementSim = brancherDureeVieObjet({
      idNom: "duree-vie-equipement-nom", idValeur: "duree-vie-equipement-sim", idAide: "duree-vie-equipement-sim-aide",
      idSelecteur: "equipement", feuille: "Equipement", selecteurTableau: "#table-equipements",
      defauts: DUREE_VIE_EQUIPEMENTS, nomGenerique: "l'équipement"
    });
    majDureeVieBassineSim = brancherDureeVieObjet({
      idNom: "duree-vie-bassine-nom", idValeur: "duree-vie-bassine-sim", idAide: "duree-vie-bassine-sim-aide",
      idSelecteur: "source", feuille: "Acces_ressource", selecteurTableau: "#table-sources",
      defauts: DUREE_VIE_SOURCES, nomGenerique: "la retenue"
    });

    ["culture", "surface", "source", "equipement", "agence", "nb-adherents", "capacite", "prix-vente"]
      .forEach(function (id) {
        $(id).addEventListener("change", function () {
          if (id === "source") { subventionsParDefaut(false); }
          if (id === "culture") { prixParDefaut(); }
          if (id === "surface") { etat.nbUnitesManuel = false; }
          planifier();
        });
      });
    ["zre", "deja-amorti", "deja-amorti-equipement", "capacite-auto", "rendement-sgpe"].forEach(function (id) {
      $(id).addEventListener("change", planifier);
    });
    document.querySelectorAll('input[name="type-retenue"]').forEach(function (r) {
      r.addEventListener("change", planifier);
    });
    $("nb-unites").addEventListener("change", function () { etat.nbUnitesManuel = true; planifier(); });
    $("prix-retablir").addEventListener("click", function () { prixParDefaut(); planifier(); });
    /* Subvention publique saisie : prise en compte immédiate dans les coûts et le bilan */
    [["subvention-equipement", "subvEquipementManuel"], ["subvention", "subvAccesManuel"]].forEach(function (c) {
      $(c[0]).addEventListener("input", function () {
        etat[c[1]] = $(c[0]).value !== "";
        $(c[0]).classList.toggle("champ-param--modifie", etat[c[1]]);
        planifier();
      });
    });

    $("export-png").addEventListener("click", function () {
      cascade.exporterPNG("cascade-" + (etat.commune ? etat.commune.nom : "irrigation") + "-" + $("culture").value);
    });
    $("export-csv").addEventListener("click", function () {
      var e = entrees();
      cascade.exporterCSV("cascade-" + (etat.commune ? etat.commune.nom : "irrigation") + "-" + e.culture, [
        ["Commune", etat.commune ? etat.commune.nom + " (" + etat.commune.departement + ")" : "non renseignée"],
        ["Culture", e.culture], ["Surface (ha)", e.surface],
        ["Source de l'eau", e.source], ["Équipement", e.equipement], []
      ]);
    });

    prixParDefaut();
    subventionsParDefaut(true);
    majBlocs();
    if (PAGE.exemple) { appliquerExemple(PAGE.exemple); } else { preselectionnerDefaut(PAGE.defaut); }
  });
})();
