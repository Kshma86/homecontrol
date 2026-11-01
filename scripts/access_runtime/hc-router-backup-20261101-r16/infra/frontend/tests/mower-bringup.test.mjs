import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import Module from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { bringupView } from "../src/features/mower/mowerBringupModel.mjs";

function snapshot() {
  return { ok: true, mode: "HC_BRINGUP", read_only: true, configured: true,
    connection: { status: "BRINGUP_CONNECTED" }, freshness: { fresh: true, effective_age_ms: 100 },
    health_freshness: { fresh: true, effective_age_ms: 500 },
    identity: { mode: "HC_BRINGUP", motion_permitted: false, commissioned: false, esp_fw: "esp-hc-bringup-20261010",
      stm_fw: "stm-hc-bringup-20261010", esp_boot: "3079538D8965CA51", stm_boot: "5FF20D5146FDAD55", profile_crc: "00000000" },
    state: { state: "DISARMED", source_seq: 3630, state_seq: 1386, control_epoch: 1, armed: false, store: "EMPTY",
      fault_mask: "00000000", stopped: false, safety_installed_mask: null },
    health: { wifi_connected: true, rssi_dbm: -71, stm_peer_alive: true, ntrip_state: "DISCONNECTED", rtcm_age_ms: null },
    update: { locked: true, phase: "ERROR", error: "METADATA_ERROR", can_finish: false, detail: "AWAITING_SERVICE_STATUS" } };
}

test("bringup state and health expire locally, outage or wrong mode never proves current state", () => {
  const value = snapshot();
  assert.equal(bringupView(value, 1000, 1100).fresh, true);
  const old = bringupView(value, 1000, 2600);
  assert.equal(old.state, null); assert.equal(old.fresh, false);
  assert.equal(bringupView(value, 1000, 3600).health, null);
  for (const change of [{ mode: "OTHER" }, { read_only: false }, { identity: { ...value.identity, commissioned: true } },
    { freshness: { fresh: true, effective_age_ms: null } }, { freshness: { fresh: true, effective_age_ms: -1 } },
    { connection: { status: "AUTH_FAILED" } }])
    assert.equal(bringupView({ ...value, ...change }, 1000, 1100).state, null);
  assert.equal(bringupView(value, 1000, 1100, "offline").state, null);
  assert.equal(bringupView(value, null, 1100).state, null);
});

async function renderView(value, error = "", now = 1100) {
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/MowerBringupPanel.jsx", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", external: ["react", "react-dom/server", "lucide-react"] });
  const filename = fileURLToPath(new URL("./mower-bringup-ui-test.cjs", import.meta.url));
  const compiled = new Module(filename); compiled.paths = Module._nodeModulePaths(dirname(filename));
  compiled._compile(bundled.outputFiles[0].text, filename);
  return renderToStaticMarkup(React.createElement(compiled.exports.MowerBringupView,
    { reader: { snapshot: value, error, now, receivedAt: 1000, loading: false } }));
}

test("native diagnostics show real seq and ERROR lock, no control buttons or false physical-stop proof", async () => {
  const html = await renderView(snapshot());
  for (const text of ["HC kapcsolat működik", "HC_BRINGUP", "esp-hc-bringup-20261010", "3630", "DISARMED", "EMPTY",
    "METADATA_ERROR", "NEM IGAZOLT", "nem mozgásmérés", "Biztonsági bemenetek</span><strong>Ismeretlen", "nem üzembe helyezett"])
    assert.ok(html.includes(text), text);
  const buttons = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g);
  assert.equal(buttons.length, 1); assert.ok(buttons[0].includes("Frissítés"));
  assert.doesNotMatch(html, /<input\b|<form\b|type="file"|>MEGÁLLT</);
});

test("expired and unreachable current rows are unknown, historical snapshot is explicitly labelled", async () => {
  for (const [error, now] of [["", 5000], ["offline", 1100]]) {
    const html = await renderView(snapshot(), error, now);
    assert.ok(html.includes("Állapot</span><strong>Ismeretlen"));
    assert.ok(html.includes("Az utolsó megfigyelés nem igazolja"));
    assert.ok(html.includes("Wi-Fi</span>") || html.includes("Wi-Fi</"));
    assert.ok(html.includes("RSSI ismeretlen"));
  }
});

test("retired bringup view stays readonly and the main Mower page opens MOTOR_TEST", async () => {
  const main = await readFile(new URL("../src/features/mower/MowerV3.jsx", import.meta.url), "utf8");
  const panel = await readFile(new URL("../src/features/mower/MowerBringupPanel.jsx", import.meta.url), "utf8");
  assert.ok(main.includes("return <MowerOperational motorTest />;"));
  assert.ok(!main.includes("<MowerBringupPanel"));
  assert.ok(!main.includes("Mower integrációs nézet"));
  assert.ok(main.includes("authenticated: true"));
  assert.ok(main.includes('configured={snapshot?.configured === true}'));
  assert.ok(panel.includes('endpoint: "/api/mower/v3/bringup/snapshot"'));
  assert.doesNotMatch(panel, /\bfetch\(|WebSocket|useMowerManual|useMowerCommands|\/api\/v3\/|localStorage/);
});
