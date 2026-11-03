import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import Module from "node:module";
import { build } from "esbuild";
import { currentState } from "../src/features/mower/mowerV3Model.mjs";

async function harness() {
  const slots = [], effects = [], timers = new Map(), requests = [], listeners = {};
  let cursor = 0, dirty = false, result, time = 100, timerId = 0;
  const original = Object.fromEntries(["window", "document", "performance", "fetch", "__snapshotHooks"].map((key) => [key, globalThis[key]]));
  globalThis.__snapshotHooks = {
    useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: typeof initial === "function" ? initial() : initial }; return [slots[i].value, (value) => { slots[i].value = typeof value === "function" ? value(slots[i].value) : value; dirty = true; }]; },
    useRef(initial) { const i = cursor++; if (!slots[i]) slots[i] = { current: initial }; return slots[i]; },
    useEffect(callback, deps) { const i = cursor++; if (!slots[i] || deps.some((v, at) => !Object.is(v, slots[i].deps[at]))) effects.push(() => { slots[i]?.cleanup?.(); slots[i] = { deps, cleanup: callback() }; }); },
  };
  globalThis.window = { setTimeout(fn, ms) { const id = ++timerId; timers.set(id, { fn, ms }); return id; }, clearTimeout(id) { timers.delete(id); },
    setInterval(fn, ms) { const id = ++timerId; timers.set(id, { fn, ms, repeat: true }); return id; }, clearInterval(id) { timers.delete(id); } };
  globalThis.document = { visibilityState: "visible", addEventListener(name, fn) { listeners[name] = fn; }, removeEventListener() {} };
  globalThis.performance = { now: () => time };
  globalThis.fetch = (path, options) => new Promise((resolve, reject) => {
    requests.push({ path, options, resolve, reject });
    options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/useMowerV3Snapshot.js", import.meta.url))], bundle: true, write: false, platform: "node", format: "cjs",
    plugins: [{ name: "mock-hooks", setup(builder) {
      builder.onResolve({ filter: /^react$/ }, () => ({ path: "react", namespace: "mock" }));
      builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: "export const {useState,useRef,useEffect}=globalThis.__snapshotHooks; export const useMemo=(fn)=>fn(); export const useCallback=(fn)=>fn;" }));
    } }] });
  const compiled = new Module("snapshot-hook"); compiled._compile(bundled.outputFiles[0].text, "snapshot-hook.cjs");
  function render() { do { dirty = false; cursor = 0; result = compiled.exports.default(); while (effects.length) effects.shift()(); } while (dirty); }
  async function settle() { for (let i = 0; i < 12; i++) { await Promise.resolve(); if (dirty) render(); } }
  render(); await settle();
  return { requests, timers, get value() { return result; },
    async respond(payload,timing=null) { requests.at(-1).resolve({ ok: true, status: 200, headers: { get: (name) => name === "Server-Timing" ? timing : "application/json" }, text: async () => JSON.stringify(payload) }); await settle(); },
    async fire(ms) { time += ms; for (const [id, timer] of [...timers]) if (timer.ms === ms) { if (!timer.repeat) timers.delete(id); timer.fn(); } await settle(); },
    async refresh() { result.refresh(); await settle(); },
    async visibility(state) { globalThis.document.visibilityState = state; listeners.visibilitychange(); await settle(); },
    close() { for (const slot of slots) slot?.cleanup?.(); for (const [key, value] of Object.entries(original)) globalThis[key] = value; },
  };
}
const live = () => ({ ok: true, connection: { status: "LIVE" }, identity: { update_locked: false },
  freshness: { fresh: true, effective_age_ms: 10 }, state: { state: "IDLE", stopped: true } });

test("background BUSY preserves original evidence and cannot refresh its local safety deadline", async () => {
  const h = await harness();
  try {
    await h.respond(live()); const first = h.value.snapshot, receivedAt = h.value.receivedAt;
    await h.fire(500); await h.respond({ ok:true,connection:{status:"BUSY"},freshness:{fresh:false} });
    assert.equal(h.value.snapshot, first); assert.equal(h.value.receivedAt, receivedAt); assert.equal(h.value.loading, false);
    assert.equal(currentState(h.value.snapshot, receivedAt, receivedAt + 1501).fresh, false);
    assert.ok([...h.timers.values()].some((timer) => timer.ms === 200));
  } finally { h.close(); }
});

test("hanging requests expire, free the refresh button and back off without overlapping fetches", async () => {
  const h = await harness();
  try {
    assert.equal(h.value.loading,true);
    await h.refresh(); assert.equal(h.requests.length,1);
    await h.fire(5000); assert.equal(h.value.loading,false); assert.match(h.value.error,/időkorlát/);
    assert.equal(h.requests.length,1);
    await h.fire(5000); assert.equal(h.requests.length,2);
    await h.respond({ok:true,connection:{status:"UNREACHABLE"},freshness:{fresh:false}});
    assert.ok([...h.timers.values()].some((timer) => timer.ms === 5000));
  } finally { h.close(); }
});

test("hidden pages pause polling, returning to the page requests fresh evidence explicitly", async () => {
  const h = await harness();
  try {
    await h.respond(live()); await h.visibility("hidden"); await h.fire(500);
    assert.equal(h.requests.length,1);
    await h.visibility("visible"); assert.equal(h.requests.length,2);
    await h.respond(live()); await h.refresh(); assert.equal(h.value.loading,true); assert.equal(h.requests.length,3);
    await h.respond(live()); assert.equal(h.value.loading,false);
  } finally { h.close(); }
});

test("server processing time is not counted twice but network transit still ages evidence",async()=>{
 const h=await harness();try{
  await h.fire(800);const payload=live();payload.freshness.effective_age_ms=300;
  await h.respond(payload,"rover;dur=750.000");
  assert.equal(h.value.snapshot.freshness.effective_age_ms,350);
  assert.equal(currentState(h.value.snapshot,h.value.receivedAt,h.value.receivedAt+1000).fresh,true);
  assert.equal(currentState(h.value.snapshot,h.value.receivedAt,h.value.receivedAt+1200).fresh,false);
 }finally{h.close();}
});
