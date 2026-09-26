/* =========================================================================
   Carte de localisation : fond Plan IGN (Géoplateforme) et contour communal.
   L'application n'affiche plus de rasters ; ce module ne sert qu'à situer la
   commune retenue pour la simulation.
   ========================================================================= */
(function (global) {
  "use strict";

  var URL_IGN = "https://data.geopf.fr/wmts?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile" +
    "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM" +
    "&FORMAT=image/png&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}";
  var ATTRIB = '<a href="https://geoservices.ign.fr/" target="_blank" rel="noopener">IGN</a> — Plan IGN';
  var FRANCE = [[41.3, -5.2], [51.2, 9.6]];

  function CarteCommune(id, fond) {
    this.carte = L.map(id, { attributionControl: true, keyboard: true });
    /* Le fond de tuiles peut être désactivé (IRRIG_FOND_CARTE=0) : derrière un proxy
       lent, la commune reste localisable sans attendre le chargement des tuiles. */
    if (fond !== false) {
      L.tileLayer(URL_IGN, { minZoom: 5, maxZoom: 18, attribution: ATTRIB }).addTo(this.carte);
    }
    this.carte.attributionControl.setPrefix("");
    this.carte.fitBounds(FRANCE);
    this.contour = null;
    this.marqueur = null;
  }

  CarteCommune.prototype.montrer = function (commune) {
    if (this.contour) { this.carte.removeLayer(this.contour); this.contour = null; }
    if (this.marqueur) { this.carte.removeLayer(this.marqueur); this.marqueur = null; }
    if (!commune) { this.carte.fitBounds(FRANCE); return; }
    if (commune.contour) {
      this.contour = L.geoJSON(commune.contour, {
        className: "contour-commune",
        style: { color: "#000091", weight: 2, fillColor: "#6A6AF4", fillOpacity: 0.18 }
      }).addTo(this.carte);
      this.carte.fitBounds(this.contour.getBounds(), { padding: [24, 24], maxZoom: 13 });
    }
    if (commune.centre) {
      this.marqueur = L.circleMarker([commune.centre[1], commune.centre[0]], {
        radius: 6, color: "#000091", weight: 2, fillColor: "#ffffff", fillOpacity: 1
      }).addTo(this.carte);
      this.marqueur.bindTooltip(commune.nom + " (" + commune.departement + ")", { direction: "top" });
      if (!commune.contour) { this.carte.setView([commune.centre[1], commune.centre[0]], 12); }
    }
  };

  CarteCommune.prototype.rafraichir = function () {
    var c = this.carte;
    setTimeout(function () { c.invalidateSize(); }, 60);
  };

  global.Cartographie = { CarteCommune: CarteCommune, FRANCE: FRANCE };
})(window);
