import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import Module from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileProblem, preflightBody, validReport, IMAGE_LIMIT, ELF_LIMIT } from "../src/features/mower/mowerFirmwareModel.mjs";

const report = { ok: true, scope: "HC_LOCAL_PREFLIGHT", elf_verified: true, release_verified: false, release_id: null,
  upload_available: false, persisted: false, hardware_qualified: false, rover_contacted: false, elf_sha256: "b".repeat(64),
  warning: "Nincs kiadásjóváhagyás.", metadata: { layout: "H743_1M_QSPI_REC2", slot: "APP", target: "STM32H743VG", service_abi: 2,
    link_address: "08100000", image_bytes: 1536, image_sha256: "a".repeat(64), profile_crc: "AABBCCDD", fw_id: "synthetic-test-only" } };

test("preflight input requires bounded aligned RFU2 and ELF without fabricated defaults", () => {
  assert.ok(fileProblem(null, null));
  assert.equal(fileProblem({ size: 1536 }, { size: 52 }), null);
  for (const size of [0, 1279, 1281, IMAGE_LIMIT+32, true, NaN]) assert.ok(fileProblem({ size }, { size: 52 }));
  for (const size of [0, 51, ELF_LIMIT+1, true, Infinity]) assert.ok(fileProblem({ size: 1536 }, { size }));
  assert.equal(fileProblem({ size: IMAGE_LIMIT }, { size: ELF_LIMIT }), null);
});

test("HC envelope preserves exact bytes with a little-endian image-length prefix", async () => {
  const image = new Blob([new Uint8Array(1536).fill(42)]), elf = new Blob([new Uint8Array(52).fill(17)]);
  const raw = await preflightBody(image, elf).arrayBuffer(), bytes = new Uint8Array(raw);
  assert.equal(new DataView(raw).getUint32(0, true), 1536);
  assert.equal(bytes.length, 4+1536+52);
  assert.deepEqual(bytes.slice(4, 1540), new Uint8Array(1536).fill(42));
  assert.deepEqual(bytes.slice(1540), new Uint8Array(52).fill(17));
});

test("preflight result cannot imply upload, approval, persistence or qualification", () => {
  assert.equal(validReport(report, ""), true);
  for (const update of [{ upload_available: true }, { persisted: true }, { hardware_qualified: true }, { rover_contacted: true },
    { elf_verified: false }, { release_verified: true }, { release_id: "other" }, { scope: "ROVER" }]) assert.equal(validReport({ ...report, ...update }, ""), false);
  for (const update of [{ layout: "H743_1M_QSPI2" }, { slot: "A" }, { service_abi: true }, { image_bytes: 1281 },
    { profile_crc: "00000000" }, { image_sha256: "A".repeat(64) }, { fw_id: "bad,token" }]) assert.equal(validReport({ ...report, metadata: { ...report.metadata, ...update } }, ""), false);
  assert.equal(validReport({ ...report, release_verified: true, release_id: "reviewed" }, "reviewed"), true);
  assert.equal(validReport(report, "reviewed"), false);
});

test("firmware UI exposes inspection but rover upload stays disabled even with release verification", async () => {
  const filename = fileURLToPath(new URL("./mower-firmware-ui-test.cjs", import.meta.url));
  const value = { image: null, elf: null, releaseId: "reviewed", releases: [], catalogError: "", report: { ...report, release_verified: true, release_id: "reviewed" }, error: "", busy: false, problem: null };
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/MowerFirmwarePreflight.jsx", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", external: ["react", "lucide-react"],
    plugins: [{ name: "mock-preflight", setup(builder) {
      builder.onResolve({ filter: /useMowerFirmware$/ }, () => ({ path: "mock-preflight", namespace: "mock" }));
      builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: `export default function() { return ${JSON.stringify(value)}; }`, loader: "js" }));
    } }] });
  const compiled = new Module(filename); compiled.paths = Module._nodeModulePaths(dirname(filename));
  compiled._compile(bundled.outputFiles[0].text, filename);
  const html = renderToStaticMarkup(React.createElement(compiled.exports.default));
  assert.match(html, /<button[^>]*disabled=""[^>]*>.*?<span>Feltöltés a roverre — még nem elérhető<\/span>/);
  for (const text of ["RFU2", "ELF", "nem hoz létre", "Teljes kép SHA-256", "ELF SHA-256", "nincs igazolva"]) assert.ok(html.toLowerCase().includes(text.toLowerCase()), text);
  assert.ok(!html.includes("/api/v3/update"));
});

async function hookHarness({ malformed = false, lost = false } = {}) {
  let cursor = 0, needsRender = false, state;
  const slots = [], effects = [], calls = [];
  const hooks = {
    useState(initial) { const index = cursor++; if (!slots[index]) slots[index] = { value: initial }; return [slots[index].value, (value) => { slots[index].value = value; needsRender = true; }]; },
    useRef(initial) { const index = cursor++; if (!slots[index]) slots[index] = { current: initial }; return slots[index]; },
    useEffect(callback, deps) { const index = cursor++; if (!slots[index]) effects.push(() => { slots[index] = { cleanup: callback() }; }); },
  };
  const originals = { window: globalThis.window, fetch: globalThis.fetch, hooks: globalThis.__firmwareHooks };
  globalThis.__firmwareHooks = hooks;
  globalThis.window = { setTimeout: () => 1, clearTimeout: () => {} };
  globalThis.fetch = async (path, options = {}) => {
    calls.push({ path, method: options.method || "GET", body: options.body });
    if (path.endsWith("/preflight") && lost) throw new Error("Synthetic lost reply");
    return { ok: true, json: async () => path.endsWith("/releases") ? { ok: true, releases: [], upload_available: false } : malformed ? { ...report, upload_available: true } : report };
  };
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/useMowerFirmware.js", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", plugins: [{ name: "mock-hooks", setup(builder) {
      builder.onResolve({ filter: /^react$/ }, () => ({ path: "mock-hooks", namespace: "mock" }));
      builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: "export const {useState,useRef,useEffect} = globalThis.__firmwareHooks;", loader: "js" }));
    } }] });
  const compiled = new Module("firmware-hooks"); compiled._compile(bundled.outputFiles[0].text, "firmware-hooks.cjs");
  function render() { do { needsRender = false; cursor = 0; state = compiled.exports.default(); while (effects.length) effects.shift()(); } while (needsRender); }
  async function settle() { for (let index = 0; index < 12; index++) { await Promise.resolve(); if (needsRender) render(); } }
  render(); await settle();
  return { calls, get editor() { return state; }, async act(callback) { await callback(state); await settle(); },
    close() { for (const slot of slots) slot?.cleanup?.(); globalThis.window = originals.window; globalThis.fetch = originals.fetch; globalThis.__firmwareHooks = originals.hooks; } };
}

test("firmware hook never auto-submits and selecting new artifacts invalidates old proof", async () => {
  const runner = await hookHarness();
  try {
    assert.equal(runner.calls.length, 1); assert.equal(runner.calls[0].method, "GET");
    await runner.act((editor) => editor.choose("image", new Blob([new Uint8Array(1536)])));
    await runner.act((editor) => editor.choose("elf", new Blob([new Uint8Array(52)])));
    assert.equal(runner.calls.length, 1);
    await runner.act((editor) => editor.inspect());
    assert.equal(runner.editor.report.elf_verified, true);
    await runner.act((editor) => editor.choose("release", "reviewed"));
    assert.equal(runner.editor.report, null);
    assert.equal(runner.calls.filter((call) => call.method === "POST").length, 1);
    assert.ok(runner.calls.every((call) => call.path.startsWith("/api/mower/v3/firmware/") && !call.path.includes("/update")));
  } finally { runner.close(); }
});

test("lost or malformed inspection never reports verified or automatically retries", async () => {
  for (const options of [{ lost: true }, { malformed: true }]) {
    const runner = await hookHarness(options);
    try {
      await runner.act((editor) => editor.choose("image", new Blob([new Uint8Array(1536)])));
      await runner.act((editor) => editor.choose("elf", new Blob([new Uint8Array(52)])));
      await runner.act((editor) => editor.inspect());
      assert.equal(runner.editor.report, null); assert.ok(runner.editor.error);
      assert.equal(runner.calls.filter((call) => call.method === "POST").length, 1);
    } finally { runner.close(); }
  }
});
