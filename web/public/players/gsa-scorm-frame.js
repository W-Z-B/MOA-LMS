/*
 * Runs first in every page of a SCORM package, inside the LMS's sandboxed player (api/packages/play.py adds it
 * after scorm-again's cross-frame client). It makes the client this page's SCORM API, for SCORM 1.2 (window.API)
 * and 2004 (window.API_1484_11) alike. Every call goes by postMessage to the LMS's page at the top, which
 * answers only its own player frame (web/src/features/packages/player.ts).
 */
(function () {
  "use strict";
  var script = document.currentScript;
  var lms = script && script.getAttribute("data-lms-origin");
  var Client = window.CrossFrameAPI && (window.CrossFrameAPI.default || window.CrossFrameAPI);
  if (!lms || typeof Client !== "function" || window.top === window) return;
  var api = new Client(lms, window.top);
  window.API = api;
  window.API_1484_11 = api;
})();
