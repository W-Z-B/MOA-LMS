#!/usr/bin/env node
// Page-weight budget for the application shell, checked in CI after `npm run build`.
//
// The gold standard asks that common pages weigh under 500 KB on a 3G connection. The shell (HTML,
// scripts and styles, compressed as Caddy serves them) is the fixed part of every page; this keeps it
// under SHELL_BUDGET so the rest of the allowance is left for data. Raise the budget only with a reason
// recorded in the pull request.
//
// The shell is what index.html loads: its scripts, the modules it preloads and its styles. Parts fetched
// only when a screen needs them (the page editor, KaTeX for maths, the PDF viewer and its worker; see
// docs/adr/0012-new-components.md) are not part of every page: they are listed apart, each under
// PART_BUDGET, so no single screen can quietly grow without limit either.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { gzipSync } from "node:zlib";

const SHELL_BUDGET_KB = 160;
const PART_BUDGET_KB = 400;
const dist = join(import.meta.dirname, "..", "dist");

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

const code = files(dist).filter((path) => /\.(html|m?js|css)$/.test(path) && !path.endsWith("sw.js"));
if (code.length === 0) {
  console.error("No build output in web/dist. Run `npm run build` first.");
  process.exit(1);
}

// What every page loads: index.html and the files it names.
const html = readFileSync(join(dist, "index.html"), "utf8");
const named = new Set([...html.matchAll(/(?:src|href)="\/([^"]+\.(?:m?js|css))"/g)].map((m) => join(dist, m[1])));
const inShell = (path) => path.endsWith("index.html") || named.has(path);

const kb = (path) => gzipSync(readFileSync(path), { level: 9 }).length / 1024;
const line = (size, label) => console.log(`${size.toFixed(1).padStart(7)} KB  ${label}`);

let total = 0;
console.log("Shell (every page):");
for (const path of code.filter(inShell).sort()) {
  const size = kb(path);
  total += size;
  line(size, relative(dist, path));
}
line(total, `total, compressed (budget ${SHELL_BUDGET_KB} KB)`);

const over = [];
console.log(`\nLoaded only when a screen needs it (budget ${PART_BUDGET_KB} KB each):`);
for (const path of code.filter((p) => !inShell(p)).sort((a, b) => kb(b) - kb(a))) {
  const size = kb(path);
  line(size, relative(dist, path));
  if (size > PART_BUDGET_KB) over.push(`${relative(dist, path)} by ${(size - PART_BUDGET_KB).toFixed(1)} KB`);
}

if (total > SHELL_BUDGET_KB) {
  console.error(`The application shell is over its page-weight budget by ${(total - SHELL_BUDGET_KB).toFixed(1)} KB.`);
  process.exit(1);
}
if (over.length > 0) {
  console.error(`Over the budget for a part loaded on demand: ${over.join("; ")}.`);
  process.exit(1);
}
