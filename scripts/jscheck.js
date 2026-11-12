// The browser code's static check (D-286): for each ES module given, names used but never
// declared or imported, imports never used, and imports of names the other module doesn't
// export. There is no bundler, npm or type checker here (AGENTS.md), so without this a
// wrong name fails only when its line runs in the browser.
//
// Run by `make jslint` (part of `make lint` and the pre-commit hook) with the node that
// Playwright ships in the dev image, using node's own copy of the acorn parser:
//   scripts/jscheck.sh                 every module under web/ (not web/vendor/)
//   scripts/jscheck.sh web/app.js ...  only these
// Prints `file:line: message` per finding and exits 1 if there are any.

"use strict";
const fs = require("fs");
const path = require("path");
const acorn = require("internal/deps/acorn/acorn/dist/acorn");

// What a page has without importing it. A new browser API used for the first time is
// added here; a typo never should be.
const GLOBALS = new Set(`
  globalThis window document navigator location history console performance localStorage
  fetch setTimeout clearTimeout setInterval clearInterval requestAnimationFrame cancelAnimationFrame
  queueMicrotask structuredClone getComputedStyle matchMedia alert confirm prompt
  Object Array Map Set WeakMap WeakSet Promise Symbol Proxy Reflect JSON Math Number String Boolean
  BigInt Date RegExp Error TypeError RangeError Function Intl Infinity NaN undefined
  parseFloat parseInt isNaN isFinite encodeURIComponent decodeURIComponent encodeURI decodeURI
  Float32Array Float64Array Int8Array Int16Array Int32Array Uint8Array Uint8ClampedArray Uint16Array
  Uint32Array ArrayBuffer DataView TextEncoder TextDecoder
  URL URLSearchParams Blob File FileReader FormData Headers Request Response AbortController
  Event CustomEvent KeyboardEvent MouseEvent PointerEvent WheelEvent InputEvent EventTarget
  Node Element Option Image Audio DOMParser XMLSerializer DOMRect CSS devicePixelRatio TextDecoderStream
  MutationObserver ResizeObserver IntersectionObserver
  AudioContext OfflineAudioContext AudioBuffer AudioWorkletNode MediaRecorder Worker
  uPlot arguments
`.split(/\s+/).filter(Boolean));
/** A DOM element class: `HTMLSelectElement`, `SVGSVGElement`. */
const ELEMENT = /^(HTML|SVG)[A-Za-z]*Element$/;

/** The names a pattern declares (a parameter, a `const {a, b: [c]} = …`). */
function patternNames(node, out = []) {
  if (!node) return out;
  if (node.type === "Identifier") out.push(node);
  else if (node.type === "ObjectPattern") for (const p of node.properties) patternNames(p.type === "RestElement" ? p.argument : p.value, out);
  else if (node.type === "ArrayPattern") for (const e of node.elements) patternNames(e, out);
  else if (node.type === "RestElement") patternNames(node.argument, out);
  else if (node.type === "AssignmentPattern") patternNames(node.left, out);
  return out;
}

/** The expressions inside a declaring pattern: defaults and computed keys (they are uses). */
function patternUses(node, out = []) {
  if (!node) return out;
  if (node.type === "ObjectPattern") {
    for (const p of node.properties) {
      if (p.type === "RestElement") continue;
      if (p.computed) out.push(p.key);
      patternUses(p.value, out);
    }
  } else if (node.type === "ArrayPattern") for (const e of node.elements) patternUses(e, out);
  else if (node.type === "AssignmentPattern") {
    out.push(node.right);
    patternUses(node.left, out);
  }
  return out;
}

const isFunction = (n) => n.type === "FunctionDeclaration" || n.type === "FunctionExpression" || n.type === "ArrowFunctionExpression";

/** What a list of statements declares in its own block: let, const, class, function, imports. */
function declaredIn(statements, names) {
  for (let s of statements) {
    if ((s.type === "ExportNamedDeclaration" || s.type === "ExportDefaultDeclaration") && s.declaration) s = s.declaration;
    if (s.type === "VariableDeclaration" && s.kind !== "var") for (const d of s.declarations) for (const id of patternNames(d.id)) names.add(id.name);
    else if ((s.type === "FunctionDeclaration" || s.type === "ClassDeclaration") && s.id) names.add(s.id.name);
    else if (s.type === "ImportDeclaration") for (const sp of s.specifiers) names.add(sp.local.name);
  }
}

/** Every `var` under a function's body (they belong to the function, wherever they are). */
function varsIn(node, names) {
  if (!node || typeof node.type !== "string") return;
  if (node.type === "VariableDeclaration" && node.kind === "var") for (const d of node.declarations) for (const id of patternNames(d.id)) names.add(id.name);
  for (const [k, v] of Object.entries(node)) {
    if (k === "type" || k === "loc" || !v || typeof v !== "object") continue;
    for (const child of Array.isArray(v) ? v : [v]) if (child && typeof child.type === "string" && !isFunction(child)) varsIn(child, names);
  }
}

/**
 * The findings for one module's source.
 * @param {string} source @param {string} file @param {(spec: string) => Set<string> | null} exportsOf
 *   the names the module at `spec` (as imported from `file`) exports, or null to skip that check
 * @returns {Array<{line: number, message: string}>}
 */
function check(source, file, exportsOf) {
  const findings = [];
  let tree;
  try {
    tree = acorn.parse(source, { ecmaVersion: "latest", sourceType: "module", locations: true });
  } catch (err) {
    return [{ line: err.loc?.line ?? 1, message: `doesn't parse: ${err.message}` }];
  }
  const used = new Set(); // imported names that were used
  const imported = new Map(); // local name → its import specifier node

  /** @param {any} node @param {Set<string>[]} scopes innermost last */
  function walk(node, scopes) {
    if (!node || typeof node.type !== "string") return;
    const visit = (child, inner = scopes) => {
      for (const c of Array.isArray(child) ? child : [child]) walk(c, inner);
    };
    const declare = (pattern, inner = scopes) => {
      for (const id of patternNames(pattern)) inner[inner.length - 1].add(id.name);
      visit(patternUses(pattern), inner);
    };
    switch (node.type) {
      case "Identifier": {
        if (scopes.some((s) => s.has(node.name))) {
          if (imported.has(node.name) && !scopes.slice(1).some((s) => s.has(node.name))) used.add(node.name);
        } else if (!GLOBALS.has(node.name) && !ELEMENT.test(node.name)) findings.push({ line: node.loc.start.line, message: `${node.name} is not defined (not declared or imported in this file)` });
        return;
      }
      case "Program": {
        const top = new Set();
        declaredIn(node.body, top);
        varsIn(node, top);
        return visit(node.body, [top]);
      }
      case "ImportDeclaration": {
        const theirs = exportsOf(node.source.value);
        for (const sp of node.specifiers) {
          imported.set(sp.local.name, sp);
          if (theirs && sp.type === "ImportSpecifier" && !theirs.has(sp.imported.name)) findings.push({ line: sp.loc.start.line, message: `${node.source.value} doesn't export ${sp.imported.name}` });
          if (theirs && sp.type === "ImportDefaultSpecifier" && !theirs.has("default")) findings.push({ line: sp.loc.start.line, message: `${node.source.value} has no default export` });
        }
        return;
      }
      case "ExportNamedDeclaration":
        if (node.declaration) return visit(node.declaration);
        if (!node.source) for (const sp of node.specifiers) visit(sp.local);
        return;
      case "ExportAllDeclaration":
        return;
      case "FunctionDeclaration":
      case "FunctionExpression":
      case "ArrowFunctionExpression": {
        const own = new Set();
        if (node.type === "FunctionExpression" && node.id) own.add(node.id.name);
        const inner = [...scopes, own];
        for (const p of node.params) declare(p, inner);
        if (node.body.type === "BlockStatement") {
          declaredIn(node.body.body, own);
          varsIn(node.body, own);
          return visit(node.body.body, inner);
        }
        return visit(node.body, inner);
      }
      case "BlockStatement":
      case "StaticBlock": {
        const own = new Set();
        declaredIn(node.body, own);
        return visit(node.body, [...scopes, own]);
      }
      case "SwitchStatement": {
        visit(node.discriminant);
        const own = new Set();
        for (const c of node.cases) declaredIn(c.consequent, own);
        for (const c of node.cases) {
          visit(c.test, [...scopes, own]);
          visit(c.consequent, [...scopes, own]);
        }
        return;
      }
      case "ForStatement":
      case "ForInStatement":
      case "ForOfStatement": {
        const own = new Set();
        const head = node.type === "ForStatement" ? node.init : node.left;
        if (head?.type === "VariableDeclaration" && head.kind !== "var") declaredIn([head], own);
        const inner = [...scopes, own];
        visit(head, inner);
        visit(node.type === "ForStatement" ? [node.test, node.update] : node.right, inner);
        return visit(node.body, inner);
      }
      case "CatchClause": {
        const own = new Set();
        const inner = [...scopes, own];
        if (node.param) declare(node.param, inner);
        return visit(node.body, inner);
      }
      case "VariableDeclaration":
        for (const d of node.declarations) {
          visit(patternUses(d.id));
          visit(d.init);
        }
        return;
      case "ClassDeclaration":
      case "ClassExpression": {
        const own = new Set(node.id ? [node.id.name] : []);
        visit(node.superClass);
        return visit(node.body.body, [...scopes, own]);
      }
      case "MethodDefinition":
      case "PropertyDefinition":
      case "Property":
        if (node.computed) visit(node.key);
        return visit(node.value);
      case "MemberExpression":
        visit(node.object);
        if (node.computed) visit(node.property);
        return;
      case "LabeledStatement":
        return visit(node.body);
      case "BreakStatement":
      case "ContinueStatement":
      case "MetaProperty":
      case "PrivateIdentifier":
        return;
      default:
        for (const [k, v] of Object.entries(node)) {
          if (k === "type" || k === "loc" || !v || typeof v !== "object") continue;
          visit(v);
        }
    }
  }

  walk(tree, []);
  for (const [name, sp] of imported) if (!used.has(name)) findings.push({ line: sp.loc.start.line, message: `${name} is imported but never used` });
  return findings.sort((a, b) => a.line - b.line);
}

/** The names a module's source exports (`default` for a default export). */
function exportedNames(source) {
  const names = new Set();
  const tree = acorn.parse(source, { ecmaVersion: "latest", sourceType: "module" });
  for (const s of tree.body) {
    if (s.type === "ExportDefaultDeclaration") names.add("default");
    if (s.type !== "ExportNamedDeclaration") continue;
    for (const sp of s.specifiers) names.add(sp.exported.name);
    const d = s.declaration;
    if (d?.type === "VariableDeclaration") for (const v of d.declarations) for (const id of patternNames(v.id)) names.add(id.name);
    else if (d?.id) names.add(d.id.name);
  }
  return names;
}

function main(files) {
  /** @type {Map<string, Set<string> | null>} */
  const cache = new Map();
  let count = 0;
  for (const file of files) {
    const exportsOf = (spec) => {
      if (!spec.startsWith(".")) return null; // not one of ours
      const target = path.resolve(path.dirname(file), spec);
      if (!cache.has(target)) {
        let names = null;
        try {
          const text = fs.readFileSync(target, "utf8");
          // a vendored script made into a module by hand may re-export everything: skip it
          names = /^export \*/m.test(text) ? null : exportedNames(text);
        } catch {
          names = new Set(["\u0000missing"]);
        }
        cache.set(target, names);
      }
      return cache.get(target) ?? null;
    };
    for (const f of check(fs.readFileSync(file, "utf8"), file, exportsOf)) {
      console.log(`${file}:${f.line}: ${f.message}`);
      count++;
    }
  }
  if (count) console.log(`${count} problem${count > 1 ? "s" : ""} in the browser code (scripts/jscheck.js).`);
  process.exit(count ? 1 : 0);
}

main(process.argv.slice(2));
