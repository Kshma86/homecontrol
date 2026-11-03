import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import Module from "node:module";
import { build } from "esbuild";

const schema = JSON.parse(await readFile(new URL("./fixtures/mower-parameters-schema.json", import.meta.url), "utf8"));
const template = Object.fromEntries(Object.keys(schema.properties).map((name) => [name, name === "parameters_version" ? 1 : null]));

// Deterministic hook/effect harness: no DOM, timers or real HTTP/device writes.
async function harness(mode = "ok") {
  let cursor = 0, renderNeeded = false, result;
  const slots = [], effects = [], timers = new Map(), cache = new Map(), calls = [], saved = new Map();
  let timerId = 0;
  const same = (left, right) => left && right && left.length === right.length && left.every((item, index) => Object.is(item, right[index]));
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: typeof initial === "function" ? initial() : initial };
      return [slots[index].value, (next) => { slots[index].value = typeof next === "function" ? next(slots[index].value) : next; renderNeeded = true; }];
    },
    useRef(initial) { const index = cursor++; if (!slots[index]) slots[index] = { current: initial }; return slots[index]; },
    useMemo(factory, deps) { const index = cursor++; if (!same(slots[index]?.deps, deps)) slots[index] = { deps, value: factory() }; return slots[index].value; },
    useEffect(callback, deps) {
      const index = cursor++;
      if (!same(slots[index]?.deps, deps)) effects.push(() => { slots[index]?.cleanup?.(); slots[index] = { deps, cleanup: callback() }; });
    },
  };
  const originals = { window: globalThis.window, sessionStorage: globalThis.sessionStorage, fetch: globalThis.fetch, harness: globalThis.__mowerHooks };
  globalThis.__mowerHooks = hooks;
  globalThis.window = { confirm: () => true, setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout: (id) => timers.delete(id) };
  globalThis.sessionStorage = { getItem: (key) => cache.get(key), setItem: (key, value) => cache.set(key, value) };
  globalThis.fetch = async (path, options = {}) => {
    calls.push({ path, method: options.method || "GET", body: options.body });
    const response = (payload, status = 200) => ({ ok: status < 400, status, json: async () => structuredClone(payload) });
    if (path.endsWith("/schema")) return response({ schema, template });
    if (path.endsWith("/history")) return response({ revisions: [] });
    if (path.endsWith("/drafts")) return response({ drafts: [] });
    if (path.endsWith("/validate")) return response({ validation: { saveable: true, valid: false, missing: ["robot_id"], errors: [], draft_sha256: "test-only", rcp1_crc32: null } });
    if (path.includes("/requests/")) return response(saved.get(path.split("/").at(-1)), saved.has(path.split("/").at(-1)) ? 200 : 404);
    if (options.method === "POST") {
      if (mode === "conflict") return response({ code: "REVISION_CONFLICT", error: "Conflict", current_revision: 2 }, 409);
      const body = JSON.parse(options.body);
      const row = { source: "HC_DRAFT", apply_available: false, rover_key: "hc-test", draft_revision: body.expected_revision + 1, request_id: body.request_id, parameters: body.parameters };
      saved.set(body.request_id, row);
      if (mode === "lost") throw new Error("Synthetic lost reply after save");
      return response(row);
    }
    return response({ rover_key: "hc-test", draft_revision: 0, parameters: template });
  };
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/useMowerParameters.js", import.meta.url))], bundle: true, write: false, platform: "node", format: "cjs",
    plugins: [{ name: "hook-harness", setup(builder) {
      builder.onResolve({ filter: /^react$/ }, () => ({ path: "react-test-hooks", namespace: "mock" }));
      builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: "export const {useState,useRef,useMemo,useEffect} = globalThis.__mowerHooks;", loader: "js" }));
    } }] });
  const compiled = new Module("mower-hook-test"); compiled._compile(bundled.outputFiles[0].text, "mower-hook-test.cjs");
  function render() {
    let remaining = 30;
    do {
      renderNeeded = false; cursor = 0; result = compiled.exports.default(true);
      while (effects.length) effects.shift()();
      assert.ok(--remaining > 0, "Effect/render loop must settle");
    } while (renderNeeded);
  }
  async function settle() { for (let index = 0; index < 12; index++) { await Promise.resolve(); if (renderNeeded) render(); } }
  render(); await settle();
  return {
    get editor() { return result; }, calls, cache,
    async flushValidation() { for (const [id, timer] of [...timers]) if (timer.delay === 350) { timers.delete(id); timer.fn(); } await settle(); },
    async act(fn) { await fn(result); await settle(); },
    close() { for (const slot of slots) slot?.cleanup?.(); globalThis.window = originals.window; globalThis.sessionStorage = originals.sessionStorage; globalThis.fetch = originals.fetch; globalThis.__mowerHooks = originals.harness; },
  };
}

test("loading an unchanged empty draft keeps validation and can save revision zero", async () => {
  const runner = await harness();
  try {
    await runner.flushValidation();
    await runner.act((editor) => editor.setKeyInput("hc-test"));
    await runner.act((editor) => editor.load());
    assert.equal(runner.editor.report.saveable, true);
    assert.equal(runner.editor.canSave, true);
    await runner.act((editor) => editor.save());
    assert.equal(runner.editor.revision, 1);
    assert.equal(runner.editor.pending, null);
    assert.equal(runner.calls.filter((call) => call.method === "POST" && call.path.includes("/drafts/")).length, 1);
  } finally { runner.close(); }
});

test("lost save persists correlation and reconciliation uses only GET, never POST retry", async () => {
  const runner = await harness("lost");
  try {
    await runner.flushValidation();
    await runner.act((editor) => editor.setKeyInput("hc-test"));
    await runner.act((editor) => editor.load());
    await runner.act((editor) => editor.save());
    assert.ok(runner.editor.status.message.includes("UNKNOWN"));
    const id = runner.editor.pending.request_id;
    assert.ok([...runner.cache.values()].some((raw) => JSON.parse(raw).pending?.request_id === id));
    await runner.act((editor) => editor.save());
    await runner.act((editor) => editor.reconcile());
    assert.equal(runner.editor.revision, 1);
    assert.equal(runner.editor.pending, null);
    assert.equal(runner.calls.filter((call) => call.method === "POST" && call.path.includes("/drafts/")).length, 1);
    assert.ok(runner.calls.some((call) => call.method === "GET" && call.path.endsWith(`/requests/${id}`)));
  } finally { runner.close(); }
});

test("CAS rejection keeps local edits and original expected revision", async () => {
  const runner = await harness("conflict");
  try {
    await runner.flushValidation();
    await runner.act((editor) => editor.setKeyInput("hc-test"));
    await runner.act((editor) => editor.load());
    await runner.act((editor) => editor.edit("wheel_track_mm", "500"));
    await runner.flushValidation();
    await runner.act((editor) => editor.save());
    assert.equal(runner.editor.form.wheel_track_mm, "500");
    assert.equal(runner.editor.revision, 0);
    assert.equal(runner.editor.pending, null);
    assert.ok(runner.editor.status.message.includes("Verzióütközés"));
  } finally { runner.close(); }
});
