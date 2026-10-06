/*
 * Runs first in every page of a SCORM package, inside the LMS's sandboxed player (api/packages/play.py adds it
 * after scorm-again's cross-frame client). It makes the client this page's SCORM API, for SCORM 1.2 (window.API)
 * and 2004 (window.API_1484_11) alike. Every call goes by postMessage to the LMS's page at the top, which
 * answers only its own player frame (web/src/features/packages/player.ts).
 */
(function () {
  "use strict";
  // A sandboxed page may not use the browser's storage, and reading it throws. Content written for an ordinary
  // page often reads it all the same, so it gets a store kept in memory for as long as the page is open.
  ["localStorage", "sessionStorage"].forEach(function (name) {
    try {
      void window[name];
    } catch {
      var items = {};
      var store = {
        key: function (i) { return Object.keys(items)[i] || null; },
        getItem: function (k) { return Object.prototype.hasOwnProperty.call(items, k) ? items[k] : null; },
        setItem: function (k, v) { items[k] = String(v); },
        removeItem: function (k) { delete items[k]; },
        clear: function () { items = {}; },
      };
      Object.defineProperty(store, "length", { get: function () { return Object.keys(items).length; } });
      Object.defineProperty(window, name, { value: store, configurable: true });
    }
  });
  var script = document.currentScript;
  var lms = script && script.getAttribute("data-lms-origin");
  var Client = window.CrossFrameAPI && (window.CrossFrameAPI.default || window.CrossFrameAPI);
  if (!lms || typeof Client !== "function" || window.top === window) return;
  var api = new Client(lms, window.top);
  window.API = api;
  window.API_1484_11 = api;
})();
