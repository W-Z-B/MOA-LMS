// The web licence gate must refuse what the policy forbids. Run with:  node --test scripts/

import assert from "node:assert/strict";
import { test } from "node:test";
import { review, spdxOk } from "./check_npm_licences.mjs";

const permitted = new Set(["MIT", "ISC", "Apache-2.0", "BSD-3-Clause"]);
const policy = { permissive: [...permitted], exceptions: { npm: { "odd-lib": { licence: "MPL-2.0", reason: "named" } } } };

test("reads SPDX expressions with brackets and precedence", () => {
  assert.equal(spdxOk("MIT", permitted), true);
  assert.equal(spdxOk("(MIT OR CC0-1.0)", permitted), true);
  assert.equal(spdxOk("Apache-2.0 OR GPL-2.0-only", permitted), true);
  assert.equal(spdxOk("MIT AND GPL-3.0-only", permitted), false);
  assert.equal(spdxOk("(MIT OR AGPL-3.0-only) AND LGPL-2.1-only", permitted), false);
  assert.equal(spdxOk("GPL-2.0-only WITH Classpath-exception-2.0", permitted), false);
  assert.equal(spdxOk("(MIT", permitted), false);
  assert.equal(spdxOk("", permitted), false);
});

test("judges only what ships, and lists development tools apart", () => {
  const lock = {
    packages: {
      "": { name: "web" },
      "node_modules/react": { version: "19.0.0", license: "MIT" },
      "node_modules/copyleft-widget": { version: "1.0.0", license: "GPL-3.0-only" },
      "node_modules/no-licence": { version: "0.1.0" },
      "node_modules/odd-lib": { version: "2.0.0", license: "MPL-2.0" },
      "node_modules/vite": { version: "8.0.0", license: "MIT", dev: true },
      "node_modules/lightningcss": { version: "1.0.0", license: "MPL-2.0", dev: true },
    },
  };
  const result = review(lock, policy);
  assert.deepEqual(result.failures, ["copyleft-widget 1.0.0: GPL-3.0-only", "no-licence 0.1.0: no licence declared"]);
  assert.equal(result.devCount, 2);
  assert.deepEqual(result.devNotPermissive, ["lightningcss 1.0.0: MPL-2.0"]);
  assert.ok(result.shipped.some((line) => line.startsWith("ok   odd-lib 2.0.0: exception")));
});
