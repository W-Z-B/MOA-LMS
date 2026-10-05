#!/usr/bin/env node
// Page-weight budget for the application shell, checked in CI after `npm run build`.
//
// The gold standard asks that common pages weigh under 500 KB on a 3G connection. The shell (HTML,
// scripts and styles, compressed as Caddy serves them) is the fixed part of every page; this keeps it
// under SHELL_BUDGET so the rest of the allowance is left for data. Raise the budget only with a reason
// recorded in the pull request.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { gzipSync } from "node:zlib";

const SHELL_BUDGET_KB = 160;
const dist = join(import.meta.dirname, "..", "dist");

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

const shell = files(dist).filter((path) => /\.(html|js|css)$/.test(path) && !path.endsWith("sw.js"));
if (shell.length === 0) {
  console.error("No build output in web/dist. Run `npm run build` first.");
  process.exit(1);
}

let total = 0;
for (const path of shell.sort()) {
  const size = gzipSync(readFileSync(path), { level: 9 }).length;
  total += size;
  console.log(`${(size / 1024).toFixed(1).padStart(7)} KB  ${relative(dist, path)}`);
}
const totalKb = total / 1024;
console.log(`${totalKb.toFixed(1).padStart(7)} KB  total, compressed (budget ${SHELL_BUDGET_KB} KB)`);
if (totalKb > SHELL_BUDGET_KB) {
  console.error(`The application shell is over its page-weight budget by ${(totalKb - SHELL_BUDGET_KB).toFixed(1)} KB.`);
  process.exit(1);
}
