import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import Module from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { currentState, displayBoolean, displayMask } from "../src/features/mower/mowerV3Model.mjs";
import { commandPayload, fullSetpoint, manualStateInvalid, validCommandResult, validLease } from "../src/features/mower/mowerV3Controls.mjs";

function snapshot() {
  return { identity: { update_locked: false }, connection: { status: "LIVE" },
    freshness: { fresh: true, effective_age_ms: 100 }, state: { state: "IDLE", stopped: true } };
}

test("a live snapshot expires locally even when no further response arrives", () => {
  assert.equal(currentState(snapshot(), 1000, 2000).fresh, true);
  const expired = currentState(snapshot(), 1000, 2501);
  assert.equal(expired.fresh, false);
  assert.equal(expired.state, null);
});

test("unknown age, maintenance and source-invalid snapshots cannot imply stopped", () => {
  for (const update of [
    { freshness: { fresh: true, effective_age_ms: null } },
    { freshness: { fresh: false, effective_age_ms: 100 } },
    { identity: { update_locked: true } },
    { connection: { status: "UNREACHABLE" } },
  ]) assert.equal(currentState({ ...snapshot(), ...update }, 1000, 1100).state, null);
  assert.equal(currentState(snapshot(), null, 1100).fresh, false);
  assert.equal(currentState(null, null, 1100).state, null);
});

test("missing booleans and masks display unknown rather than false or zero", () => {
  for (const value of [null, undefined, "false", 0, 1]) {
    assert.equal(displayBoolean(value, "YES", "NO"), "Ismeretlen");
  }
  assert.equal(displayBoolean(false, "YES", "NO"), "NO");
  assert.equal(displayBoolean(true, "YES", "NO"), "YES");
  assert.equal(displayMask(null), "Ismeretlen");
  assert.equal(displayMask(0), "0x00000000");
});

test("legacy navigation never imports or mounts the operational legacy component", async () => {
  const main = await readFile(new URL("../src/main.jsx", import.meta.url), "utf8");
  const legacy = await readFile(new URL("../src/features/mower/MowerLegacy.jsx", import.meta.url), "utf8");
  assert.ok(main.includes('id: "mower-legacy"'));
  assert.ok(main.includes("<MowerV3 />"));
  assert.ok(!main.includes("MowerControl"));
  assert.ok(!legacy.includes("MowerControl"));
  assert.doesNotMatch(legacy, /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|useEffect|usePolledContext|setInterval|setTimeout)\s*\(/);
  assert.doesNotMatch(legacy, /import\s.*(?:apiClient|Notes|RtkLiveMap)/);
  assert.doesNotMatch(legacy, /\bon(?:Click|Change|Submit|Pointer\w+|Key\w+|Blur)\s*=/);
});

test("legacy preview displays the old sections and fields with all controls disabled", async () => {
  const bundled = await build({
    entryPoints: [fileURLToPath(new URL("../src/features/mower/MowerLegacy.jsx", import.meta.url))],
    bundle: true, write: false, platform: "node", format: "cjs", metafile: true,
    external: ["react", "lucide-react"], loader: { ".css": "empty" },
  });
  assert.doesNotMatch(Object.keys(bundled.metafile.inputs).join("\n"), /MowerControl|apiClient|features\/notes|RtkLiveMap/);
  const filename = fileURLToPath(new URL("./mower-legacy-ui-test.cjs", import.meta.url));
  const compiled = new Module(filename);
  compiled.paths = Module._nodeModulePaths(dirname(filename));
  compiled._compile(bundled.outputFiles[0].text, filename);
  const html = renderToStaticMarkup(React.createElement(compiled.exports.default));
  for (const label of ["Safety &amp; control", "Blade target", "IMU instruments", "Auto North", "Samples",
    "Safety &amp; faults", "Bumper", "Lift", "Perimeter wire", "Manual cruise control", "Drive RPM",
    "Steering correction", "Connect WebSocket", "RTK térkép és waypoint útvonal", "Orientáció", "WGS84",
    "Minták", "Heading error", "Latitude", "Longitude", "HDOP", "STM32 firmware", "STM binary",
    "Upload &amp; verify", "RTK GNSS", "Correction", "Motors", "Left drive", "Right drive", "Blade",
    "Connectivity", "Command ACK", "Request ID", "ESP diagnostics", "Free heap", "Loop time", "MQTT commands",
    "New Mower Note", "Comment", "Created", "EMERGENCY STOP"]) assert.ok(html.includes(label), label);
  const controls = html.match(/<(?:button|input|textarea|select)\b[^>]*>/g);
  assert.ok(controls.length > 40);
  for (const control of controls) assert.match(control, /\bdisabled=""/, control);
  assert.doesNotMatch(html, /<(?:a|form|iframe|img)\b|\bhref=|\bsrc=/);
  // SVG's namespace URI is metadata, not a network request.
  assert.doesNotMatch(html.replaceAll('xmlns="http://www.w3.org/2000/svg"', ""), /https?:\/\//);
  assert.ok(html.includes("nem korábbi mentett vagy élő roveradat"));
  assert.doesNotMatch(html, /Nincs aktív hiba|HEALTHY|READY|CLEAR|STM LOST/);
});

const lease = { type: "claimed", lease_id: 7, control_epoch: 4, lease_ms: 350, max_linear_mm_s: 500, max_yaw_mdeg_s: 90000 };

test("STOP needs no identity or state and contains no legacy fields", () => {
  assert.deepEqual(commandPayload("stop", null, null, null, "stop-1"), { v: 3, request_id: "stop-1" });
  assert.throws(() => commandPayload("arm", null, null, null, "arm-1"));
  assert.deepEqual(commandPayload("arm", null, { esp_boot: "ESP", stm_boot: "STM" }, { control_epoch: 3 }, "arm-1"),
    { v: 3, request_id: "arm-1", esp_boot: "ESP", stm_boot: "STM", control_epoch: 3, command: "arm", value: null });
});

test("held manual frame is full, integer, bounded and always blade zero", () => {
  assert.deepEqual(fullSetpoint(lease, 1, { linear: -200, yaw: 1000 }, true),
    { type: "drive", lease_id: 7, control_epoch: 4, seq: 1, linear_mm_s: -200, yaw_mdeg_s: 1000, blade_rpm: 0, deadman: true });
  for (const intent of [{ linear: 501, yaw: 0 }, { linear: 1.1, yaw: 0 }, { linear: 0, yaw: 90001 }]) {
    assert.throws(() => fullSetpoint(lease, 1, intent, true));
  }
  assert.throws(() => fullSetpoint(lease, true, { linear: 0, yaw: 0 }, true));
  assert.throws(() => fullSetpoint(lease, 1, { linear: 0, yaw: 0 }, "true"));
});

test("deadman release is a full zero frame without retaining motion intent", () => {
  const intent = { linear: 300, yaw: 20000 };
  const frame = fullSetpoint(lease, 2, intent, false);
  assert.equal(frame.deadman, false);
  assert.equal(frame.linear_mm_s, 0);
  assert.equal(frame.yaw_mdeg_s, 0);
  assert.equal(frame.blade_rpm, 0);
  assert.deepEqual(intent, { linear: 300, yaw: 20000 });
});

test("invalid lease duration, bools and overflowing authority cannot enable controls", () => {
  assert.equal(validLease(lease), true);
  for (const update of [{ lease_ms: 500 }, { lease_id: true }, { control_epoch: 0 }, { max_linear_mm_s: 65536 }, { max_yaw_mdeg_s: 360001 }]) {
    assert.equal(validLease({ ...lease, ...update }), false);
  }
});

test("APPLIED must correlate request, command and saved STM boot even after remount", () => {
  const record = { request_id: "arm-1", command: "arm", stm_boot: "FEDCBA9876543210" };
  const ack = { ...record, result: "APPLIED", code: "OK", control_epoch: 4, state_seq: 16, state: "IDLE" };
  assert.equal(validCommandResult(ack, record), true);
  for (const updates of [{ request_id: "other" }, { command: "start" }, { stm_boot: "123456789ABCDEF0" },
    { state_seq: null }, { control_epoch: true }, { state: "UNKNOWN" }, { code: "PENDING" }]) {
    assert.equal(validCommandResult({ ...ack, ...updates }, record), false);
  }
});

test("manual epoch changes invalidate authority including uint32 wrap", () => {
  assert.equal(manualStateInvalid({ control_epoch: 3, state: "IDLE" }, lease), false);
  assert.equal(manualStateInvalid({ control_epoch: 4, state: "MANUAL", manual_lease_id: 7 }, lease), false);
  assert.equal(manualStateInvalid({ control_epoch: 4, state: "IDLE", manual_lease_id: 7 }, lease), true);
  assert.equal(manualStateInvalid({ control_epoch: 4, state: "MANUAL", manual_lease_id: 8 }, lease), true);
  assert.equal(manualStateInvalid({ control_epoch: 5, state: "AUTO" }, lease), true);
  assert.equal(manualStateInvalid({ control_epoch: 1, state: "AUTO" }, { ...lease, control_epoch: 0xffffffff }), true);
});

test("ERPM lease snapshots bind three targets, independent third enable and deadman zero", () => {
  const lease = { type: "claimed", lease_id: 7, control_epoch: 5, lease_ms: 350,
    max_linear_mm_s: 0, max_yaw_mdeg_s: 0, drive_mode: "ERPM", motor_erpm_limits: [1000, 1000, 1000] };
  assert.equal(validLease(lease), true);
  const intent = { left: 100, right: -100, third: 500, thirdEnabled: false };
  assert.deepEqual(fullSetpoint(lease, 1, intent, true), { type: "drive_erpm", lease_id: 7, control_epoch: 5, seq: 1,
    left_erpm: 100, right_erpm: -100, third_erpm: 0, deadman: true });
  assert.equal(fullSetpoint(lease, 2, { ...intent, thirdEnabled: true }, true).third_erpm, 500);
  assert.deepEqual(fullSetpoint(lease, 3, { ...intent, thirdEnabled: true }, false), { type: "drive_erpm", lease_id: 7, control_epoch: 5, seq: 3,
    left_erpm: 0, right_erpm: 0, third_erpm: 0, deadman: false });
  assert.throws(() => fullSetpoint(lease, 4, { ...intent, left: 1001 }, true));
  assert.throws(() => fullSetpoint(lease, 4, { ...intent, third: 1001, thirdEnabled: true }, true));
  for (const motor_erpm_limits of [[1000, 1000], [1000, true, 1000], [6001, 1000, 1000], [1000, 1000, 25001]]) {
    assert.equal(validLease({ ...lease, motor_erpm_limits }), false);
  }
});

test("MOTOR_TEST diagnostics keep real updater lock visible without changing normal admission", () => {
  const testSnapshot = snapshot();
  testSnapshot.identity = { mode: "MOTOR_TEST", esp_fw: "esp-motor-test-20261012", stm_fw: "stm-motor-test-20261012", update_locked: true };
  assert.equal(currentState(testSnapshot, 100, 100).fresh, true);
  assert.equal(testSnapshot.identity.update_locked, true);
  assert.equal(currentState({ ...testSnapshot, identity: { ...testSnapshot.identity, esp_fw: "new-compatible-build" } }, 100, 100).fresh, true);
});
