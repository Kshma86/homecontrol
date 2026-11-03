import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import Module from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { serviceView } from "../src/features/mower/mowerServiceModel.mjs";

function snapshot() {
  return { ok: true, read_only: true, configured: true, connection: { status: "SERVICE_CONNECTED" },
    freshness: { fresh: true, effective_age_ms: 100, timeout_ms: 3000 },
    service: { mode: "FIRST_INSTALL_SERVICE", service_abi: 1, motion_permitted: false, applied: false,
      commissioned: false, stm_connected: true, can_parked: true, disarmed: true, outputs_inhibited: true,
      esp_firmware: "esp-service-20261010-lan2", stm_firmware: "service-20261010",
      stm_uid: "004C00333131511431333732", ip: "192.168.1.119", storage: "EMPTY", revision: 0, code: "EMPTY" }, parameters: null };
}

test("service freshness expires locally at 3000 ms and never grants operational evidence", () => {
  assert.equal(serviceView(snapshot(), 1000, 2000).fresh, true);
  const view = serviceView(snapshot(), 1000, 3901);
  assert.equal(view.fresh, false); assert.equal(view.current, null);
  for (const update of [
    { connection: { status: "STM_UNAVAILABLE" } },
    { freshness: { fresh: true, effective_age_ms: null } },
    { freshness: { fresh: true, effective_age_ms: -1 } },
    { service: { ...snapshot().service, applied: true } },
    { service: { ...snapshot().service, motion_permitted: true } },
    { service: { ...snapshot().service, service_abi: true } },
  ]) assert.equal(serviceView({ ...snapshot(), ...update }, 1000, 1100).current, null);
  assert.equal(serviceView(snapshot(), null, 1100).fresh, false);
  assert.equal(serviceView(snapshot(), 1000, 1100, "offline").current, null);
});

async function renderView(value, error = "", now = 1100) {
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/MowerServicePanel.jsx", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", external: ["react", "react-dom/server", "lucide-react"] });
  const filename = fileURLToPath(new URL("./mower-service-ui-test.cjs", import.meta.url));
  const compiled = new Module(filename); compiled.paths = Module._nodeModulePaths(dirname(filename));
  compiled._compile(bundled.outputFiles[0].text, filename);
  return renderToStaticMarkup(React.createElement(compiled.exports.MowerServiceView,
    { reader: { snapshot: value, error, now, receivedAt: 1000, loading: false } }));
}

test("service view shows real peer/network and empty revision zero without operational buttons", async () => {
  const html = await renderView(snapshot());
  for (const text of ["Szervizkapcsolat él", "004C00333131511431333732", "192.168.1.119", "esp-service-20261010-lan2",
    "hajtás/kés tiltva", "Tárolási revízió", "<strong>0</strong>", "EMPTY", "CAN parkolva", "nem bizonyít fizikai"])
    assert.ok(html.includes(text), text);
  const buttons = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g);
  assert.equal(buttons.length, 1); assert.ok(buttons[0].includes("Frissítés"));
  assert.doesNotMatch(html, /<input\b|<form\b|type="file"|>ARM</);
});

test("unconfigured service shows missing private token and stale evidence never asserts a current inhibition", async () => {
  const html = await renderView({ ok: true, connection: { status: "UNCONFIGURED" },
    configuration: { origin_configured: true, token_configured: false }, freshness: {} });
  assert.ok(html.includes("LAN-cím: beállítva"));
  assert.ok(html.includes("hiányzik vagy nem olvasható"));
  const stale = await renderView(snapshot(), "", 5000);
  assert.ok(stale.includes("Ismeretlen / elavult"));
  assert.ok(stale.includes("Az utolsó megfigyelés nem igazolja"));
  assert.ok(stale.includes("Kimenetek szoftveresen tiltva</span><strong>Ismeretlen"));
});

test("saved readback is labelled not applied and is never auto-imported into a HC draft", async () => {
  const value = snapshot(); value.parameters = { robot_id: "test-only" };
  value.service.storage = "STAGED"; value.service.code = "STAGED_NOT_APPLIED"; value.service.revision = 1;
  const html = await renderView(value);
  assert.ok(html.includes("STAGED_NOT_APPLIED"));
  assert.ok(html.includes("nem ACTIVE/APPLIED"));
  assert.ok(html.includes("nem töltjük automatikusan az editorba"));
});

test("retired LAN2 service stays unmounted and its diagnostic hook remains readonly", async () => {
  const main = await readFile(new URL("../src/features/mower/MowerV3.jsx", import.meta.url), "utf8");
  const hook = await readFile(new URL("../src/features/mower/useMowerServiceRead.js", import.meta.url), "utf8");
  assert.ok(main.includes("return <MowerOperational motorTest />;"));
  assert.ok(!main.includes("<MowerServicePanel"));
  assert.ok(hook.includes('endpoint = "/api/mower/v3/service/snapshot"'));
  assert.ok(hook.includes('fetch(endpoint, { cache: "no-store"'));
  assert.ok(hook.includes("pending || document.visibilityState"));
  assert.ok(hook.includes("setInterval(refresh, 1000)"));
  assert.ok(hook.includes("controller?.abort()"));
  assert.doesNotMatch(hook, /\bPOST\b|WebSocket|localStorage|sessionStorage|\/api\/v3\//);
});
