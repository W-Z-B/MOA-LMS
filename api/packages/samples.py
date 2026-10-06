"""Small, fictional packages made in code, for the browser journeys (seed_journeys) and the demonstration.

A SCORM 1.2 package of one page whose button reports a pass with a score through the SCORM API, and an H5P
file whose content type ("H5P.GSATest", written here, MIT like the rest of the LMS) asks one question and
reports the answer as an xAPI statement, as real H5P content types do. Neither copies anyone's material.
"""

import io
import json
import zipfile

SCORM_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="gsa-seed-spacing" version="1" xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata><schema>ADL SCORM</schema><schemaversion>1.2</schemaversion></metadata>
  <organizations default="org"><organization identifier="org"><title>Seed spacing check</title>
    <item identifier="lesson" identifierref="page"><title>Seed spacing check</title></item>
  </organization></organizations>
  <resources><resource identifier="page" type="webcontent" adlcp:scormtype="sco" href="index.html">
    <file href="index.html"/><file href="lesson.js"/></resource></resources>
</manifest>
"""

SCORM_PAGE = """<!doctype html>
<html lang="en-GB">
<head><meta charset="utf-8"><title>Seed spacing check</title>
<style>body { font: 18px/1.5 sans-serif; margin: 1rem; } button { min-height: 44px; font-size: 1rem; }</style>
</head>
<body>
<h1>Seed spacing check</h1>
<p>How far apart are the rows when maize is sown by hand?</p>
<button id="answer" type="button">75 cm between rows</button>
<p id="said" role="status"></p>
<script src="lesson.js"></script>
</body>
</html>
"""

SCORM_SCRIPT = """(function () {
  var api = window.API;
  var said = document.getElementById("said");
  if (!api) { said.textContent = "No SCORM API was found."; return; }
  api.LMSInitialize("");
  document.getElementById("answer").addEventListener("click", function () {
    api.LMSSetValue("cmi.core.score.raw", "90");
    api.LMSSetValue("cmi.core.lesson_status", "passed");
    api.LMSCommit("");
    api.LMSFinish("");
    said.textContent = "Right: saved as passed, with 90.";
  });
})();
"""

H5P_LIBRARY = {
    "title": "GSA test question",
    "machineName": "H5P.GSATest",
    "majorVersion": 1,
    "minorVersion": 0,
    "patchVersion": 0,
    "runnable": 1,
    "license": "MIT",
    "preloadedJs": [{"path": "gsa-test.js"}],
}

H5P_SCRIPT = """var H5P = H5P || {};
H5P.GSATest = (function () {
  function GSATest(params, contentId) {
    H5P.EventDispatcher.call(this);
    this.params = params || {};
    this.contentId = contentId;
  }
  GSATest.prototype = Object.create(H5P.EventDispatcher.prototype);
  GSATest.prototype.constructor = GSATest;
  GSATest.prototype.attach = function ($container) {
    var self = this;
    var root = $container.get(0);
    root.innerHTML = "";
    var question = document.createElement("p");
    question.textContent = self.params.question;
    var answer = document.createElement("button");
    answer.type = "button";
    answer.textContent = self.params.answer;
    answer.style.minHeight = "44px";
    answer.addEventListener("click", function () {
      var event = self.createXAPIEventTemplate("answered");
      event.setScoredResult(1, 1, self, true, true);
      self.trigger(event);
      answer.disabled = true;
      question.textContent = self.params.feedback;
    });
    root.appendChild(question);
    root.appendChild(answer);
  };
  return GSATest;
})();
"""


def _zip(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as made:
        for name, data in files.items():
            made.writestr(name, data)
    return buffer.getvalue()


def scorm_package() -> bytes:
    return _zip({"imsmanifest.xml": SCORM_MANIFEST, "index.html": SCORM_PAGE, "lesson.js": SCORM_SCRIPT})


def h5p_file() -> bytes:
    meta = {
        "title": "Crop pests quiz",
        "language": "en",
        "mainLibrary": "H5P.GSATest",
        "embedTypes": ["iframe"],
        "license": "U",
        "preloadedDependencies": [{"machineName": "H5P.GSATest", "majorVersion": "1", "minorVersion": "0"}],
    }
    content = {
        "question": "Which soil holds the most water?",
        "answer": "Clay",
        "feedback": "Right: clay holds the most water.",
    }
    return _zip(
        {
            "h5p.json": json.dumps(meta),
            "content/content.json": json.dumps(content),
            "H5P.GSATest-1.0/library.json": json.dumps(H5P_LIBRARY),
            "H5P.GSATest-1.0/gsa-test.js": H5P_SCRIPT,
        }
    )
