/* =========================================================================
   Analyse financière de l'irrigation — logique de la page « Projet ».
   Enchaînement : saisie ► POST /api/simulation ► affichage des résultats,
   mise à jour des cellules calculées des onglets et du graphique en cascade.
   Les rendements et le besoin en eau proviennent des cartes lorsque la culture en
   dispose ; des couches facultatives (cases à cocher) superposent au fond de carte
   le rendement irrigué, le rendement pluvial ou le besoin en eau, issus de
   /api/carte-variable/<culture>/<variable>.
   ========================================================================= */
(function () {
  "use strict";

  var PAGE = JSON.parse(document.getElementById("donnees-page").textContent || "{}");
  var $ = function (id) { return document.getElementById(id); };
  var etat = { commune: null, surcharges: {}, dernier: null, nbUnitesManuel: false };
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
  /* Info-bulle au survol d'une méthode (Carte, SGPE, Référence) : description de la
     méthode, complétée du motif d'indisponibilité le cas échéant */
  function aideMethode(radio, motif) {
    var groupe = radio.closest(".fr-radio-group");
    if (!groupe) { return; }
    var aide = groupe.getAttribute("data-aide") || "";
    groupe.title = motif ? motif + " " + aide : aide;
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
    var methode = document.querySelector('input[name="methode-besoin"]:checked');
    return {
      methode_besoin: methode ? methode.value : "sgpe",
      culture: $("culture").value,
      surface: parseFloat($("surface").value) || 0,
      source: $("source").value,
      equipement: $("equipement").value,
      agence: $("agence").value,
      zre: $("zre").checked,
      sans_carte: !!document.querySelector('input[name="methode-rendement"][value="reference"]:checked'),
      type_retenue: retenue ? retenue.value : "individuelle",
      nb_adherents: parseInt($("nb-adherents").value, 10) || 1,
      capacite_auto: $("capacite-auto").checked,
      capacite: $("capacite-auto").checked ? null : (parseFloat($("capacite").value) || null),
      deja_amorti: $("deja-amorti").checked,
      deja_amorti_equipement: $("deja-amorti-equipement").checked,
      nb_unites: (etat.nbUnitesManuel && $("nb-unites").value) ? parseInt($("nb-unites").value, 10) : null,
      prix_vente: parseFloat($("prix-vente").value) || null,
      source_prix: sourcePrix(),
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
    if (isNaN(v)) { delete etat.surcharges[cle]; }
    else { etat.surcharges[cle] = champ.dataset.pct === "1" ? v / 100 : v; }
    var defaut = parseFloat(champ.dataset.defaut);
    champ.classList.toggle("champ-param--modifie", !isNaN(defaut) && Math.abs(v - defaut) > 1e-9);
  }

  function brancherParametres() {
    document.querySelectorAll(".champ-param").forEach(function (champ) {
      if (champ.dataset.defaut === undefined) { champ.dataset.defaut = champ.value; }
      var ev = champ.type === "range" ? "input" : "change";
      champ.addEventListener(ev, function () {
        surchargeDepuisChamp(champ);
        planifier();
      });
    });
    $("reinitialiser").addEventListener("click", function () {
      etat.surcharges = {};
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
      planifier();
    }

    champValeur.addEventListener("change", appliquer);
    selecteur.addEventListener("change", majAffichage);
    majAffichage();
    return majAffichage;
  }

  /* Prix de vente : valeur du référentiel pour la culture choisie */
  /* Deux jeux de prix : prix de marché du référentiel, ou barème du prix assuré MASAA (assurance récolte) */
  var PRIX = PAGE.prix_cultures || {};

  function sourcePrix() {
    var r = document.querySelector('input[name="source-prix"]:checked');
    return r ? r.value : "referentiel";
  }

  function prixParDefaut() {
    var src = sourcePrix();
    var p = (PRIX[src] || {})[$("culture").value];
    if (p === undefined || p === null) { p = (PRIX.referentiel || {})[$("culture").value]; }
    if (p !== undefined && p !== null) { $("prix-vente").value = p; }
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
    majEtatCasesCartesVariables();
  }

  /* ==========================================================================
     3 bis. Couches couleur : rendement irrigué / pluvial / besoin en eau
     ========================================================================== */
  var CARTES_VARIABLES = PAGE.cartes_variables || {};
  var VARIABLES_CARTE = [
    { id: "rdt_irrigue", libelle: "rendement potentiel irrigué" },
    { id: "rdt_pluvial", libelle: "rendement potentiel pluvial (non irrigué)" },
    { id: "besoin", libelle: "besoin en eau d'irrigation" }
  ];
  var couchesVariables = {};   // id de variable -> { couche: L.ImageOverlay, donnees: {...} }

  function rgb(c) { return "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")"; }

  function majLegendesVariables() {
    var conteneur = $("legendes-cartes-variables");
    var actifs = VARIABLES_CARTE.filter(function (v) { return couchesVariables[v.id]; });
    if (!actifs.length) { conteneur.hidden = true; conteneur.innerHTML = ""; return; }
    conteneur.hidden = false;
    conteneur.innerHTML = actifs.map(function (v) {
      var d = couchesVariables[v.id].donnees;
      return '<div class="legende-var"><span class="legende-var__libelle">' + d.libelle + '</span>' +
        '<span class="legende-var__barre" style="background:linear-gradient(to right,' +
        rgb(d.couleur_basse) + ',' + rgb(d.couleur_haute) + ')"></span>' +
        '<span class="legende-var__valeurs">' + fmtS(d.min, 1) + ' à ' + fmtS(d.max, 1) + ' ' + d.unite +
        (d.scenario ? ' · ' + d.scenario : '') + '</span></div>';
    }).join("");
  }

  function retirerCoucheVariable(id) {
    var c = couchesVariables[id];
    if (c && c.couche && carteSimulation) { carteSimulation.carte.removeLayer(c.couche); }
    delete couchesVariables[id];
    majLegendesVariables();
  }

  function majEtatCasesCartesVariables() {
    var culture = $("culture").value;
    var dispo = CARTES_VARIABLES[culture] || {};
    VARIABLES_CARTE.forEach(function (v) {
      var case_ = $("carte-var-" + v.id);
      var ok = !!dispo[v.id];
      case_.disabled = !ok;
      case_.title = ok ? "" : "« " + culture + " » n'a pas de carte de " + v.libelle + ".";
      if (!ok && case_.checked) { case_.checked = false; retirerCoucheVariable(v.id); }
    });
  }

  function rafraichirCoucheVariable(id) {
    var case_ = $("carte-var-" + id);
    if (!case_.checked) { retirerCoucheVariable(id); return; }
    var culture = $("culture").value;
    fetch("/api/carte-variable/" + encodeURIComponent(culture) + "/" + encodeURIComponent(id))
      .then(function (r) { return r.json(); }).then(function (d) {
        retirerCoucheVariable(id);
        if (!d.disponible || !carteSimulation) {
          case_.checked = false;
          case_.title = "Lecture de la carte impossible" + (d.erreur ? " (" + d.erreur + ")" : "") + ".";
          return;
        }
        var couche = L.imageOverlay("data:image/png;base64," + d.png_base64, d.bounds, { opacity: 1 })
          .addTo(carteSimulation.carte);
        couchesVariables[id] = { couche: couche, donnees: d };
        majLegendesVariables();
      }).catch(function () {
        case_.checked = false;
        retirerCoucheVariable(id);
      });
  }

  function rafraichirCartesVariablesActives() {
    VARIABLES_CARTE.forEach(function (v) {
      if ($("carte-var-" + v.id).checked) { rafraichirCoucheVariable(v.id); }
    });
  }

  /* ==========================================================================
     4. Simulation
     ========================================================================== */
  var minuterie = null;
  function planifier() {
    clearTimeout(minuterie);
    minuterie = setTimeout(simuler, 220);
  }

  function simuler() {
    majBlocs();
    var section = $("resultats");
    section.setAttribute("aria-busy", "true");
    fetch("/api/simulation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entrees: entrees(), surcharges: etat.surcharges, commune: etat.commune })
    }).then(function (r) { return r.json(); }).then(function (res) {
      etat.dernier = res;
      afficher(res);
      section.setAttribute("aria-busy", "false");
    }).catch(function (e) {
      section.setAttribute("aria-busy", "false");
      html("avertissements", '<div class="fr-alert fr-alert--error fr-alert--sm"><p>Calcul impossible : ' +
        e.message + "</p></div>");
    });
  }

  /* ==========================================================================
     5. Affichage des résultats
     ========================================================================== */
  function afficher(res) {
    var a = res.agro, c = res.couts, s = res.seuil, d = res.dimensionnement;

    /* --- Bilan agronomique */
    texte("agro-rdt-irr", fmt(a.rdt_irrigue, 1));
    texte("agro-rdt-plu", fmt(a.rdt_pluvial, 1));
    texte("agro-besoin", fmt(a.besoin_mm, 0));
    texte("agro-volume", fmt(a.volume_preleve, 0));
    /* Rendements : « Carte » indisponible (grisé) si la culture n'a pas de carte */
    /* (bascule automatique sur « Référence », annulée dès qu'une culture avec carte est choisie) */
    var radioCarte = $("methode-rendement-carte");
    radioCarte.disabled = !a.carte_disponible;
    if (!a.carte_disponible && radioCarte.checked) {
      $("methode-rendement-reference").checked = true;
      etat.rendementBascule = true;
    } else if (a.carte_disponible && etat.rendementBascule) {
      etat.rendementBascule = false;
      radioCarte.checked = true;
      planifier();
    }
    aideMethode(radioCarte, a.carte_disponible ? "" : "Pas de carte de rendement pour cette culture.");
    var dispoMethodes = a.methodes_besoin || {};
    var indisponibles = [];
    document.querySelectorAll('input[name="methode-besoin"]').forEach(function (r) {
      r.disabled = dispoMethodes[r.value] === false;
      if (r.disabled) { indisponibles.push(r.value); }
      aideMethode(r, r.disabled ? "Indisponible pour cette culture." : "");
    });
    /* Besoin en eau : méthode cochée indisponible → bascule sur la première disponible
       (SGPE, Carte, Référence), et retour à la méthode choisie dès qu'elle redevient disponible */
    var cochee = document.querySelector('input[name="methode-besoin"]:checked');
    if (cochee && cochee.disabled) {
      etat.besoinChoisi = etat.besoinChoisi || cochee.value;
      var repli = document.querySelector('input[name="methode-besoin"]:not(:disabled)');
      if (repli) { repli.checked = true; planifier(); }
    } else if (etat.besoinChoisi && dispoMethodes[etat.besoinChoisi] !== false) {
      var choisi = etat.besoinChoisi;
      etat.besoinChoisi = null;
      if (!cochee || cochee.value !== choisi) { $("methode-besoin-" + choisi).checked = true; planifier(); }
    }
    var culture = res.entrees.culture;
    texte("methode-besoin-aide", [
      indisponibles.indexOf("sgpe") >= 0
        ? "SGPE indisponible pour « " + culture + " » : coefficients culturaux (Kc) non renseignés." : "",
      indisponibles.indexOf("carte") >= 0 ? "Carte indisponible pour « " + culture + " »." : ""
    ].filter(Boolean).join(" "));
    texte("agro-volume-cpl", "Efficience du matériel : " + pct(a.efficience, 0));
    var bulles = a.infobulles || {};
    texte("agro-rdt-irr-tt", bulles.rdt_irrigue || "");
    texte("agro-rdt-plu-tt", bulles.rdt_pluvial || "");
    texte("agro-besoin-tt", bulles.besoin_mm || "");
    texte("agro-volume-tt", "Besoin (mm) × 10 × surface ÷ efficience d'application du matériel");

    var notes = a.notes || [];
    html("notes-agro", notes.length
      ? '<div class="fr-alert fr-alert--info fr-alert--sm"><p>' + notes.join("<br>") + "</p></div>" : "");

    /* --- Bilan économique */
    var tuile = $("tuile-bilan");
    tuile.classList.toggle("indicateur--positif", res.bilan.total >= 0);
    tuile.classList.toggle("indicateur--negatif", res.bilan.total < 0);
    texte("eco-bilan", (res.bilan.total >= 0 ? "+" : "−") + fmt(Math.abs(res.bilan.total), 0));
    texte("eco-cout", fmt(c.total, 0));
    texte("eco-cout-m3", fmt(c.c_par_m3, 1));
    texte("eco-cout-ha", fmt(c.par_ha, 0));
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
      "<tr class=\"ligne-reste-a-charge\"><th scope=\"row\"><strong>Reste à charge pour l'agriculteur</strong></th>" +
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

    /* --- Seuil de rentabilité */
    var phrase;
    if (s.prix_min === null || s.prix_min === undefined) {
      phrase = "Le gain de rendement étant nul, aucun prix de vente ne permet de rentabiliser l'irrigation " +
        "par le seul différentiel de rendement.";
    } else {
      var ecart = s.ecart, sens = ecart >= 0 ? "au-dessous du" : "au-dessus du";
      phrase = "<strong>Prix de vente minimal : " + fmtS(s.prix_min) + " €/t</strong>, soit " +
        fmtS(Math.abs(ecart)) + " €/t " + sens + " prix retenu (" + fmtS(s.prix) + " €/t)" +
        (s.prix ? ", un écart de " + fmt(Math.abs(ecart) / s.prix * 100, 0) + " %" : "") + ". ";
      if (s.delta_min !== null && s.delta_min !== undefined) {
        phrase += "Lecture inverse : à prix de vente constant, il faut un gain de rendement d'au moins <strong>" +
          fmtS(s.delta_min) + " q/ha</strong> (contre actuellement " + fmtS(s.delta_actuel) + " q/ha).";
      }
    }
    html("seuil-texte", phrase);

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
     9. Démarrage
     ========================================================================== */
  document.addEventListener("DOMContentLoaded", function () {
    carteSimulation = new Cartographie.CarteCommune("carte-simulation", PAGE.fond_carte !== false);
    cascade = new Cascade($("cascade"));
    preparerRecherche();
    brancherParametres();
    brancherOnglets();
    brancherExportsTableaux();
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
          if (id === "culture") {
            prixParDefaut();
            majEtatCasesCartesVariables();
            rafraichirCartesVariablesActives();
          }
          if (id === "surface") { etat.nbUnitesManuel = false; }
          planifier();
        });
      });
    VARIABLES_CARTE.forEach(function (v) {
      $("carte-var-" + v.id).addEventListener("change", function () { rafraichirCoucheVariable(v.id); });
    });
    ["zre", "deja-amorti", "deja-amorti-equipement", "capacite-auto"].forEach(function (id) {
      $(id).addEventListener("change", planifier);
    });
    document.querySelectorAll('input[name="type-retenue"], input[name="methode-besoin"], input[name="methode-rendement"]').forEach(function (r) {
      r.addEventListener("change", function () {
        if (r.name === "methode-rendement") { etat.rendementBascule = false; }
        if (r.name === "methode-besoin") { etat.besoinChoisi = null; }
        planifier();
      });
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
    document.querySelectorAll('input[name="source-prix"]').forEach(function (r) {
      r.addEventListener("change", function () { prixParDefaut(); planifier(); });
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
