/*! DSFR v1.15.3 | SPDX-License-Identifier: Etalab-2.0 | License-Filename: LICENSE.md | restricted use (see terms and conditions) */

(function () {
  'use strict';

  var config = {
    prefix: 'fr',
    namespace: 'dsfr',
    organisation: '@gouvfr',
    version: '1.15.3'
  };

  var api = window[config.namespace];

  var TooltipSelector = {
    TOOLTIP: api.internals.ns.selector('tooltip'),
    SHOWN: api.internals.ns.selector('tooltip--shown'),
    HIDDING: api.internals.ns.selector('tooltip--hidding'),
    BUTTON: api.internals.ns.selector('btn--tooltip')
  };

  var TooltipReferentState = {
    FOCUS: 1 << 0,
    HOVER: 1 << 1
  };

  var TooltipReferent = /*@__PURE__*/(function (superclass) {
    function TooltipReferent () {
      superclass.call(this);
      this._state = 0;
      this._isShownOnInteraction = null;
    }

    if ( superclass ) TooltipReferent.__proto__ = superclass;
    TooltipReferent.prototype = Object.create( superclass && superclass.prototype );
    TooltipReferent.prototype.constructor = TooltipReferent;

    var prototypeAccessors = { state: { configurable: true } };
    var staticAccessors = { instanceClassName: { configurable: true } };

    staticAccessors.instanceClassName.get = function () {
      return 'TooltipReferent';
    };

    TooltipReferent.prototype.init = function init () {
      var this$1$1 = this;

      superclass.prototype.init.call(this);
      this.listen('focusin', this.focusIn.bind(this));
      this.listen('focusout', function (e) { return this$1$1.focusOut(e); });
      if (!this.matches(TooltipSelector.BUTTON)) {
        var mouseover = this.mouseover.bind(this);
        this.listen('mouseover', mouseover);
        this.placement.listen('mouseover', mouseover);
        var mouseout = this.mouseout.bind(this);
        this.listen('mouseout', mouseout);
        this.placement.listen('mouseout', mouseout);
      }
      this.addEmission(api.core.RootEmission.KEYDOWN, this._keydown.bind(this));
      this.listen('pointerdown', this._interactionStart.bind(this));
      this.listen('mousedown', this._interactionStart.bind(this));
      this.listen('touchstart', this._interactionStart.bind(this));
      this.listen('click', this._click.bind(this));
      this.addEmission(api.core.RootEmission.CLICK, this._clickOut.bind(this));
      this.addEmission(api.core.RootEmission.INTERACTION, this._clickOut.bind(this)); // IOS
    };

    TooltipReferent.prototype._interactionStart = function _interactionStart () {
      this._isShownOnInteraction = this.state > 0;
    };

    TooltipReferent.prototype._click = function _click () {
      var isButtonTooltip = this.matches(TooltipSelector.BUTTON);

      if (isButtonTooltip && (this._isShownOnInteraction === true || (this._isShownOnInteraction === null && this.state > 0))) {
        this.close();
        this._isShownOnInteraction = null;
        return;
      }

      if (!isButtonTooltip) {
        this.focusOut();
        this._isShownOnInteraction = null;
        return;
      }

      this.focusIn();
      this._isShownOnInteraction = null;
    };

    TooltipReferent.prototype._clickOut = function _clickOut (target) {
      if (this.node.contains(target) || this.placement.node.contains(target)) { return; }
      this.focusOut();
    };

    TooltipReferent.prototype._keydown = function _keydown (keyCode) {
      switch (keyCode) {
        case api.core.KeyCodes.ESCAPE:
          this.close();
          break;

        case api.core.KeyCodes.TAB:
          this.request(this._tab.bind(this));
          break;
      }
    };

    TooltipReferent.prototype._tab = function _tab () {
      if (this.node.contains(document.activeElement) || this.placement.node.contains(document.activeElement)) { return; }
      this.focusOut();
    };

    TooltipReferent.prototype.close = function close () {
      this.state = 0;
    };

    prototypeAccessors.state.get = function () {
      return this._state;
    };

    prototypeAccessors.state.set = function (value) {
      if (this._state === value) { return; }
      this.isShown = value > 0;
      this._state = value;
    };

    TooltipReferent.prototype.focusIn = function focusIn () {
      this.state |= TooltipReferentState.FOCUS;
    };

    TooltipReferent.prototype.focusOut = function focusOut (event) {
      if ( event === void 0 ) event = null;

      var relatedTarget = event ? event.relatedTarget : null;
      if (relatedTarget && (this.node.contains(relatedTarget) || this.placement.node.contains(relatedTarget))) { return; }
      this.state &= ~TooltipReferentState.FOCUS;
    };

    TooltipReferent.prototype.mouseover = function mouseover () {
      this.state |= TooltipReferentState.HOVER;
    };

    TooltipReferent.prototype.mouseout = function mouseout () {
      this.state &= ~TooltipReferentState.HOVER;
    };

    Object.defineProperties( TooltipReferent.prototype, prototypeAccessors );
    Object.defineProperties( TooltipReferent, staticAccessors );

    return TooltipReferent;
  }(api.core.PlacementReferent));

  var ns = function (name) { return ((config.prefix) + "-" + name); };

  ns.selector = function (name, notation) {
    if (notation === undefined) { notation = '.'; }
    return ("" + notation + (ns(name)));
  };

  ns.attr = function (name) { return ("data-" + (ns(name))); };

  ns.attr.selector = function (name, value) {
    var result = ns.attr(name);
    if (value !== undefined) { result += "=\"" + value + "\""; }
    return ("[" + result + "]");
  };

  ns.event = function (type) { return ((config.namespace) + "." + type); };

  ns.emission = function (domain, type) { return ("emission:" + domain + "." + type); };

  var TooltipEvent = {
    SHOW: ns.event('show'),
    HIDE: ns.event('hide')
  };

  var TooltipState = {
    HIDDEN: 'hidden',
    SHOWN: 'shown',
    HIDING: 'hiding'
  };

  var Tooltip = /*@__PURE__*/(function (superclass) {
    function Tooltip () {
      superclass.call(this, api.core.PlacementMode.AUTO, [api.core.PlacementPosition.TOP, api.core.PlacementPosition.BOTTOM], [api.core.PlacementAlign.CENTER, api.core.PlacementAlign.START, api.core.PlacementAlign.END]);
      this.modifier = '';
      this._state = TooltipState.HIDDEN;
    }

    if ( superclass ) Tooltip.__proto__ = superclass;
    Tooltip.prototype = Object.create( superclass && superclass.prototype );
    Tooltip.prototype.constructor = Tooltip;

    var prototypeAccessors = { isShown: { configurable: true } };
    var staticAccessors = { instanceClassName: { configurable: true } };

    staticAccessors.instanceClassName.get = function () {
      return 'Tooltip';
    };

    Tooltip.prototype.init = function init () {
      superclass.prototype.init.call(this);
      this.register(("[aria-describedby=\"" + (this.id) + "\"]"), TooltipReferent);
      this.listen('transitionend', this.transitionEnd.bind(this));
      this.setAttribute('tabindex', '-1');
    };

    Tooltip.prototype.transitionEnd = function transitionEnd () {
      if (this._state === TooltipState.HIDING) {
        this.removeClass(TooltipSelector.SHOWN);
        this.removeClass(TooltipSelector.HIDDING);
        this._state = TooltipState.HIDDEN;
        this.isShown = false;
      }
    };

    prototypeAccessors.isShown.get = function () {
      return superclass.prototype.isShown;
    };

    prototypeAccessors.isShown.set = function (value) {
      if (!this.isEnabled) { return; }
      switch (true) {
        case value:
          this._state = TooltipState.SHOWN;
          this.addClass(TooltipSelector.SHOWN);
          this.removeClass(TooltipSelector.HIDDING);
          this.dispatch(TooltipEvent.SHOW);
          superclass.prototype.isShown = true;
          break;

        case this.isShown && !value && this._state === TooltipState.SHOWN:
          this._state = TooltipState.HIDING;
          this.addClass(TooltipSelector.HIDDING);
          break;

        case this.isShown && !value && this._state === TooltipState.HIDDEN:
          this.dispatch(TooltipEvent.HIDE);
          this.removeClass(TooltipSelector.HIDDING);
          superclass.prototype.isShown = false;
          break;
      }
    };

    Tooltip.prototype.render = function render () {
      superclass.prototype.render.call(this);
      this.rect = this.getRect();
      var x = this.referentRect.center - this.rect.center;
      var limit = this.rect.width * 0.5 - 8;
      if (x < -limit) { x = -limit; }
      if (x > limit) { x = limit; }
      this.setProperty('--arrow-x', ((x.toFixed(2)) + "px"));
    };

    Object.defineProperties( Tooltip.prototype, prototypeAccessors );
    Object.defineProperties( Tooltip, staticAccessors );

    return Tooltip;
  }(api.core.Placement));

  api.tooltip = {
    Tooltip: Tooltip,
    TooltipSelector: TooltipSelector,
    TooltipEvent: TooltipEvent
  };

  api.internals.register(api.tooltip.TooltipSelector.TOOLTIP, api.tooltip.Tooltip);

})();
//# sourceMappingURL=tooltip.nomodule.js.map
