import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import Module from "node:module";
import { build } from "esbuild";
import { validStaged, validStageIntent, stageRequestId } from "../src/features/mower/mowerFirmwareModel.mjs";

const KEY = "hc.mower.v3.firmware.pending-save.v1";
const intent = { requestId: "1".repeat(32), releaseId: "reviewed", imageHash: "a".repeat(64), elfHash: "b".repeat(64), imageBytes: 1536 };
const metadata = { layout: "H743_1M_QSPI_REC2", slot: "APP", target: "STM32H743VG", service_abi: 2,
  link_address: "08100000", image_bytes: 1536, image_sha256: intent.imageHash, profile_crc: "AABBCCDD", fw_id: "synthetic-test-only" };
const job = { ok: true, scope: "HC_LOCAL_STAGING", state: "HC_STAGED", persisted: true,
  hc_job_id: "2".repeat(32), request_id: intent.requestId, artifact_id: "c".repeat(64), release_id: intent.releaseId,
  metadata, elf_sha256: intent.elfHash, elf_verified_at_staging: true, release_verified_at_staging: true,
  saved_at: "2026-10-10T11:00:00+00:00", update_id: null, upload_available: false, hardware_qualified: false, rover_contacted: false };
const report = { ...job, scope: "HC_LOCAL_PREFLIGHT", persisted: false, elf_verified: true, release_verified: true };

test("staging descriptors cannot imply a native session, current approval or hardware evidence", () => {
  assert.equal(validStaged(job, intent), true); assert.equal(validStageIntent(intent), true);
  for (const change of [{ state: "READY" }, { scope: "ROVER" }, { update_id: "3".repeat(32) }, { persisted: false },
    { upload_available: true }, { hardware_qualified: true }, { rover_contacted: true }, { release_verified_at_staging: false },
    { elf_verified_at_staging: false }, { request_id: "other" }, { release_id: "other" }, { hc_job_id: "0".repeat(32) },
    { elf_sha256: "d".repeat(64) }, { saved_at: "invalid" }, { metadata: { ...metadata, image_sha256: "d".repeat(64) } }]) {
    assert.equal(validStaged({ ...job, ...change }, intent), false, JSON.stringify(change));
  }
  for (const change of [{ requestId: "../bad" }, { imageBytes: true }, { imageHash: "A".repeat(64) }, { secret: "must not be stored" }])
    assert.equal(validStageIntent({ ...intent, ...change }), false);
});

test("firmware correlation uses 128-bit random bytes without requiring randomUUID or weak fallback", () => {
  assert.equal(stageRequestId({ getRandomValues: (bytes) => bytes.fill(0x11) }), intent.requestId);
  assert.throws(() => stageRequestId(undefined));
  assert.throws(() => stageRequestId({ randomUUID: () => "unused" }));
  assert.throws(() => stageRequestId({ getRandomValues() { throw new Error("Unavailable"); } }));
});

async function harness({ authenticated = true, initial = null, saveMode = "ok", lookupMode = "found", storageFails = false, approved = true } = {}) {
  let cursor = 0, needsRender = false, state, auth = authenticated;
  const slots = [], effects = [], calls = [], storage = new Map(initial === null ? [] : [[KEY, initial]]);
  const editor = { image: new Blob([new Uint8Array(1536)]), elf: new Blob([new Uint8Array(52)]), releaseId: "reviewed", report: approved ? report : null };
  const hooks = {
    useState(initial) { const index = cursor++; if (!slots[index]) slots[index] = { value: initial }; return [slots[index].value, (value) => { slots[index].value = typeof value === "function" ? value(slots[index].value) : value; needsRender = true; }]; },
    useRef(initial) { const index = cursor++; if (!slots[index]) slots[index] = { current: initial }; return slots[index]; },
    useEffect(callback, deps) { const index = cursor++; const previous = slots[index];
      if (!previous || deps.some((value, position) => value !== previous.deps[position])) effects.push(() => { previous?.cleanup?.(); slots[index] = { deps, cleanup: callback() }; }); },
  };
  const originals = { window: globalThis.window, fetch: globalThis.fetch, hooks: globalThis.__storageHooks };
  globalThis.__storageHooks = hooks;
  globalThis.window = { crypto: { getRandomValues: (bytes) => bytes.fill(0x11) }, setTimeout: () => 1, clearTimeout: () => {}, sessionStorage: {
    getItem: (key) => storage.get(key) ?? null,
    setItem(key, value) { if (storageFails) throw new Error("No storage"); storage.set(key, value); },
    removeItem: (key) => storage.delete(key),
  } };
  globalThis.fetch = async (path, options = {}) => {
    calls.push({ path, method: options.method || "GET", options });
    if (options.method === "POST") {
      assert.ok(storage.has(KEY), "Durable browser intent must precede POST");
      if (saveMode === "lost") throw new Error("Synthetic lost reply");
      if (saveMode === "known-reject") return { ok: false, status: 409, json: async () => ({ ok: false, code: "STORAGE_QUOTA", error: "Quota" }) };
      if (saveMode === "unknown-reject") return { ok: false, status: 503, json: async () => ({ ok: false, code: "SAVE_UNKNOWN", error: "Unknown" }) };
      return { ok: true, status: 200, json: async () => saveMode === "malformed" ? { ...job, rover_contacted: true } : job };
    }
    return { ok: true, status: 200, json: async () => path.includes("/requests/")
      ? lookupMode === "missing" ? { ok: true, found: false } : { ...job, found: true, ...(lookupMode === "mismatch" ? { request_id: "other" } : {}) }
      : { ok: true, scope: "HC_LOCAL_STAGING", jobs: [], upload_available: false, rover_contacted: false } };
  };
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/useMowerFirmwareStorage.js", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", plugins: [{ name: "mock-storage-hooks", setup(builder) {
      builder.onResolve({ filter: /^react$/ }, () => ({ path: "mock-hooks", namespace: "mock" }));
      builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: "export const {useState,useRef,useEffect} = globalThis.__storageHooks;", loader: "js" }));
    } }] });
  const compiled = new Module("storage-hooks"); compiled._compile(bundled.outputFiles[0].text, "storage-hooks.cjs");
  function render() { do { needsRender = false; cursor = 0; state = compiled.exports.default(editor, auth); while (effects.length) effects.shift()(); } while (needsRender); }
  async function settle() { for (let index = 0; index < 15; index++) { await Promise.resolve(); if (needsRender) render(); } }
  render(); await settle();
  return { calls, storage, get value() { return state; }, async act(callback) { await callback(state); await settle(); },
    async setAuth(value) { auth = value; render(); await settle(); },
    close() { for (const slot of slots) slot?.cleanup?.(); globalThis.window = originals.window; globalThis.fetch = originals.fetch; globalThis.__storageHooks = originals.hooks; } };
}

test("HC staging is explicit, authenticated, reviewed and cannot double-send", async () => {
  const runner = await harness();
  try {
    assert.deepEqual(runner.calls.map((call) => call.method), ["GET"]);
    await runner.act(async (value) => { const first = value.stage(); await value.stage(); await first; });
    assert.equal(runner.calls.filter((call) => call.method === "POST").length, 1);
    assert.equal(runner.value.pending, null); assert.equal(runner.storage.has(KEY), false);
    assert.equal(runner.value.saved.hc_job_id, job.hc_job_id); assert.equal(runner.value.jobs.length, 1);
    assert.equal(runner.calls[1].options.headers["X-HC-Request-ID"], intent.requestId);
    assert.ok(runner.calls.every((call) => !call.path.includes("/api/v3/update")));
  } finally { runner.close(); }
  for (const options of [{ authenticated: false }, { approved: false }, { storageFails: true }]) {
    const runner = await harness(options);
    try { await runner.act((value) => value.stage()); assert.equal(runner.calls.filter((call) => call.method === "POST").length, 0); }
    finally { runner.close(); }
  }
});

test("lost/malformed/unknown save replies retain intent and reconciliation is GET only", async () => {
  for (const saveMode of ["lost", "malformed", "unknown-reject"]) {
    const runner = await harness({ saveMode });
    try {
      await runner.act((value) => value.stage());
      assert.ok(runner.value.pending); assert.equal(runner.value.saved, null); assert.ok(runner.value.error);
      await runner.act((value) => value.stage());
      assert.equal(runner.calls.filter((call) => call.method === "POST").length, 1);
      await runner.act((value) => value.reconcile());
      assert.equal(runner.value.pending, null); assert.equal(runner.value.saved.hc_job_id, job.hc_job_id);
      assert.equal(runner.calls.at(-1).method, "GET"); assert.equal(runner.calls.filter((call) => call.method === "POST").length, 1);
    } finally { runner.close(); }
  }
});

test("restored intent is never replayed and negative or mismatched lookup does not clear UNKNOWN", async () => {
  for (const lookupMode of ["found", "missing", "mismatch"]) {
    const runner = await harness({ initial: JSON.stringify(intent), lookupMode });
    try {
      assert.equal(runner.calls.length, 1); assert.match(runner.calls[0].path, /\/requests\//);
      if (lookupMode === "found") { assert.equal(runner.value.pending, null); assert.ok(runner.value.saved); }
      else {
        assert.ok(runner.value.pending); assert.equal(runner.value.saved, null);
        await runner.act((value) => value.stage()); await runner.act((value) => value.reconcile());
        assert.ok(runner.value.pending); assert.ok(runner.storage.has(KEY));
      }
      assert.equal(runner.calls.filter((call) => call.method === "POST").length, 0);
    } finally { runner.close(); }
  }
});

test("logout blocks staging and recognized pre-write rejection alone clears intent", async () => {
  const runner = await harness({ saveMode: "known-reject" });
  try {
    await runner.act((value) => value.stage()); assert.equal(runner.value.pending, null); assert.equal(runner.storage.has(KEY), false);
    await runner.setAuth(false); await runner.act((value) => value.stage());
    assert.equal(runner.calls.filter((call) => call.method === "POST").length, 1);
  } finally { runner.close(); }
  const broken = await harness({ initial: "{broken" });
  try { await broken.act((value) => value.stage()); assert.equal(broken.value.pending.invalid, true); assert.equal(broken.calls.filter((call) => call.method === "POST").length, 0); }
  finally { broken.close(); }
});
