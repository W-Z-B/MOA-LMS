#!/usr/bin/env node
// Licence gate for the web packages the product ships (ADR 0002).
//
// Reads web/package-lock.json. Packages that reach the browser bundle (everything not marked dev) must
// carry a permissive licence or be a named exception in scripts/licence-policy.json. Development and
// test tools never ship; they are counted and listed only when their licence is not permissive.
//
// Usage, from the repository root:  node scripts/check_npm_licences.mjs
// No dependencies; exit status 1 lists every package that fails. Tests: node --test scripts/

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

/**
 * Whether an SPDX licence expression can be met using permitted licences only. Follows SPDX precedence:
 * brackets, then WITH, AND, OR. An expression that cannot be parsed is refused, so a person reviews it.
 * Same rules as spdx_ok in scripts/check_licences.py.
 */
export function spdxOk(expression, permitted) {
  const tokens = expression.match(/\(|\)|[^\s()]+/g) ?? [];
  let pos = 0;
  const peek = () => tokens[pos];
  const take = () => tokens[pos++];
  const keyword = (...words) => peek() !== undefined && words.includes(peek().toUpperCase());
  const operand = () => peek() !== undefined && peek() !== "(" && peek() !== ")";

  function factor() {
    if (peek() === "(") {
      take();
      const value = either();
      if (peek() !== ")") throw new Error("unbalanced brackets");
      take();
      return value;
    }
    const words = [];
    while (operand() && !keyword("AND", "OR", "WITH")) words.push(take());
    if (words.length === 0) throw new Error("missing licence");
    const value = permitted.has(words.join(" "));
    if (keyword("WITH")) {
      take(); // an exception widens what the licence allows; it never makes it permissive
      while (operand() && !keyword("AND", "OR")) take();
    }
    return value;
  }
  function both() {
    let value = factor();
    while (keyword("AND")) {
      take();
      value = factor() && value;
    }
    return value;
  }
  function either() {
    let value = both();
    while (keyword("OR")) {
      take();
      value = both() || value;
    }
    return value;
  }
  try {
    return either() && pos === tokens.length;
  } catch {
    return false;
  }
}

/** Sort every package in the lockfile into shipped and development-only, and judge the shipped ones. */
export function review(lock, policy) {
  const permitted = new Set(policy.permissive);
  const result = { shipped: [], failures: [], devCount: 0, devNotPermissive: [] };
  for (const [path, info] of Object.entries(lock.packages ?? {})) {
    if (path === "") continue; // the web app itself
    const name = info.name ?? path.replace(/^.*node_modules\//, "");
    const licence = typeof info.license === "string" ? info.license : "";
    if (info.dev === true || info.devOptional === true) {
      result.devCount += 1;
      if (!licence || !spdxOk(licence, permitted)) result.devNotPermissive.push(`${name} ${info.version}: ${licence || "none declared"}`);
      continue;
    }
    const exception = policy.exceptions.npm?.[name];
    if (exception) {
      result.shipped.push(`ok   ${name} ${info.version}: exception ${exception.licence} (${exception.reason})`);
    } else if (licence && spdxOk(licence, permitted)) {
      result.shipped.push(`ok   ${name} ${info.version}: ${licence}`);
    } else {
      const why = licence || "no licence declared";
      result.shipped.push(`FAIL ${name} ${info.version}: ${why}`);
      result.failures.push(`${name} ${info.version}: ${why}`);
    }
  }
  return result;
}

function main() {
  const policy = JSON.parse(readFileSync(join(root, "scripts", "licence-policy.json"), "utf8"));
  const lock = JSON.parse(readFileSync(join(root, "web", "package-lock.json"), "utf8"));
  const { shipped, failures, devCount, devNotPermissive } = review(lock, policy);
  console.log(shipped.join("\n"));
  console.log(`\nDevelopment and test tools (not shipped): ${devCount} packages.`);
  if (devNotPermissive.length) {
    console.log("Of those, not permissive (allowed because they never reach the product):");
    console.log("  " + devNotPermissive.join("\n  "));
  }
  if (failures.length) {
    console.error(`\nLicence policy (ADR 0002) not met by shipped web packages:\n  ${failures.join("\n  ")}`);
    process.exit(1);
  }
  console.log(`\n${shipped.length} shipped web packages meet the licence policy.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
