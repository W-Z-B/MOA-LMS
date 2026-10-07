/*
 * The LMS's H5P player page (api/packages/play.py writes the page; this runs in it, inside the sandboxed frame).
 * It opens the package with h5p-standalone and passes each xAPI statement H5P makes to the LMS's page at the
 * top, which sends it to the LMS's statement store as the learner (web/src/features/packages/player.ts).
 */
(function () {
  "use strict";
  // A sandboxed page may not use the browser's storage, and reading it throws. H5P reads it all the same (for
  // its queue of results to send later), so it gets a store kept in memory for as long as the page is open.
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
  var config = JSON.parse((script && script.getAttribute("data-config")) || "{}");

  function tell(message) {
    if (window.top !== window && config.lmsOrigin) window.top.postMessage(message, config.lmsOrigin);
  }

  function start() {
    var holder = document.getElementById("h5p-container");
    var library = window.H5PStandalone;
    var Player = library && (library.H5P || (library.default && library.default.H5P));
    if (!holder || typeof Player !== "function") {
      if (holder) holder.textContent = "The H5P player could not be loaded.";
      return;
    }
    new Player(holder, {
      h5pJsonPath: config.jsonPath,
      frameJs: config.players + "/h5p/frame.bundle.js",
      frameCss: config.players + "/h5p/styles/h5p.css",
      xAPIObjectIRI: config.activity,
      // In the page itself, not a frame of its own: a frame inside the sandbox would have an origin of its own
      // too, which h5p-standalone could not write into.
      embedType: "div",
      frame: false,
      copyright: false,
      export: false,
      icon: false,
      fullScreen: false,
    })
      .then(function () {
        window.H5P.externalDispatcher.on("xAPI", function (event) {
          tell({ type: "gsa-xapi", statement: event.data.statement });
        });
        tell({ type: "gsa-h5p-ready" });
      })
      .catch(function (error) {
        if (window.console) console.error("H5P could not start:", error && error.stack ? error.stack : error);
        holder.textContent = "This H5P content could not be opened. It may need libraries the file does not include.";
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
