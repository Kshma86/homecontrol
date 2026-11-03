import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import Module from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PARAMETER_GROUPS, parametersToForm } from "../src/features/mower/mowerParametersModel.mjs";

const schema = JSON.parse(await readFile(new URL("./fixtures/mower-parameters-schema.json", import.meta.url), "utf8"));
const template = Object.fromEntries(Object.keys(schema.properties).map((field) => [field, field === "parameters_version" ? 1 : null]));
const editor = { schema, form: parametersToForm(template, schema), keyInput: "", key: "", revision: 0, drafts: [], history: [],
  clientErrors: [], changes: [], dirty: false, busy: false, pending: null, canSave: false, rcp1Export: null,
  status: { message: "Üres HC draft" }, report: { valid: false, missing: Object.keys(template).filter((field) => field !== "parameters_version"), errors: [], draft_sha256: "test-only", rcp1_crc32: null } };

async function renderEditor(value, operator = { authenticated: false }) {
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/MowerParameterEditor.jsx", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", external: ["react", "react-dom/server", "lucide-react"],
    plugins: [{ name: "mock-editor-state", setup(builder) {
      builder.onResolve({ filter: /useMowerParameters$/ }, () => ({ path: "mock-editor", namespace: "mock" }));
      builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: `export default function() { return ${JSON.stringify(value)}; }`, loader: "js" }));
    } }] });
  const filename = fileURLToPath(new URL("./mower-parameters-ui-test.cjs", import.meta.url));
  const compiled = new Module(filename); compiled.paths = Module._nodeModulePaths(dirname(filename));
  compiled._compile(bundled.outputFiles[0].text, filename);
  return renderToStaticMarkup(React.createElement(compiled.exports.default, { operator }));
}

test("all 27 actual reference fields render, without invented operational defaults", async () => {
  assert.deepEqual(new Set(PARAMETER_GROUPS.flatMap((group) => group.fields)), new Set(Object.keys(schema.properties)));
  const html = await renderEditor(editor);
  for (const field of Object.keys(schema.properties)) assert.ok(html.includes(`<code>${field}</code>`), field);
  assert.ok(html.includes("Ismeretlen"));
  assert.ok(html.includes("nincs visszaolvasott adat"));
  assert.ok(html.includes("nem a rover aktív paraméterrevisionje"));
  assert.match(html, /<button[^>]*disabled=""[^>]*>Alkalmazás a roveren/);
  assert.ok(!html.includes("export.rcp1"));
});

test("valid saved draft offers RCP1 export but never a live-apply control", async () => {
  const html = await renderEditor({ ...editor, key: "hc-test", keyInput: "hc-test", revision: 2,
    rcp1Export: "/api/mower/v3/parameters/drafts/hc-test/revisions/2/export.rcp1", report: { ...editor.report, valid: true, missing: [], rcp1_crc32: "12345678" } }, { authenticated: true });
  assert.ok(html.includes("/revisions/2/export.rcp1"));
  assert.ok(html.includes("nem minősített / nem alkalmazott"));
  assert.match(html, /<button[^>]*disabled=""[^>]*>Alkalmazás a roveren/);
});

test("UNKNOWN save remains visible with GET reconciliation and preserved local differences", async () => {
  const html = await renderEditor({ ...editor, pending: { request_id: "save-test-only" },
    status: { error: true, message: "UNKNOWN: nincs igazolt mentés" }, changes: [{ field: "wheel_track_mm", before: null, after: 500 }] });
  assert.ok(html.includes("save-test-only"));
  assert.ok(html.includes("Egyeztetés kizárólag GET"));
  assert.ok(html.includes("Helyi szerkesztés"));
});
