import React, { useEffect, useRef, useState } from "react";
import { newRequestId } from "./mowerV3Controls.mjs";

const ROOT = "/api/mower/v3/";
async function api(path, body) {
  const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(ROOT + path, { cache: "no-store", signal: controller.signal,
      ...(body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body }) });
    const result = await response.json();
    if (!response.ok || result.ok !== true) {
      const error = new Error(result.error || result.code || "A kérés nem fejeződött be.");
      error.httpStatus = response.status; error.code = result.code; throw error;
    }
    return result;
  } finally { window.clearTimeout(timeout); }
}

export default function MowerMotorTestConfig({ snapshot, fresh, refresh }) {
  const [text, setText] = useState(""), [report, setReport] = useState(null);
  const [applying, setApplying] = useState(false), [remote, setRemote] = useState(null), [base, setBase] = useState(null);
  const [fullParameters, setFullParameters] = useState(null);
  const [message, setMessage] = useState("A rover mentett konfigurációjának betöltése…"), [receipt, setReceipt] = useState(null);
  const alive = useRef(true), applyingRef = useRef(false), dirtyRef = useRef(false), textRef = useRef("");
  const baseRef = useRef(null), reportRef = useRef(null);
  reportRef.current = report;
  function edit(value) { dirtyRef.current = true; textRef.current = value; setText(value); }
  function load(result) {
    const value = JSON.stringify(result.parameters, null, 2);
    dirtyRef.current = false; textRef.current = value;
    baseRef.current = result; setBase(result); setText(value); setFullParameters(result.parameters);
    setReport({ text: value, parameters: result.parameters, validation: result.validation, canonical_rcp: result.canonical_rcp });
  }
  function observe(result) {
    if (!alive.current) return;
    setRemote(result);
    if (!result.parameters) return; // Temporary null never erases the displayed values.
    if (!textRef.current) setMessage(result.source?.startsWith("rover_") ? "A rover mentett konfigurációja beolvasva. Változatlan értékekre nincs új mentés." : "Korábbi HC-értékek láthatók; rover-visszaigazolás szükséges.");
    if (!dirtyRef.current && (result.source !== "hc_cache" || !textRef.current)) load(result);
    else if (dirtyRef.current && reportRef.current?.text === textRef.current && reportRef.current?.canonical_rcp === result.canonical_rcp) {
      dirtyRef.current = false; baseRef.current = result; setBase(result);
    }
  }
  useEffect(() => {
    alive.current = true;
    let timer;
    async function poll() {
      try { observe(await api("motor-test/config")); }
      catch (error) { if (alive.current) setMessage(error.message); }
      finally { if (alive.current) timer = window.setTimeout(poll, 3000); }
    }
    poll();
    return () => { alive.current = false; window.clearTimeout(timer); };
  }, []);
  useEffect(() => {
    if (!text || report?.text === text) return;
    let current = true;
    const timer = window.setTimeout(async () => {
      try {
        const result = await api("parameters/validate", text);
        if (current && alive.current) setReport({ ...result, text });
      } catch { if (current && alive.current) setReport(null); }
    }, 350);
    return () => { current = false; window.clearTimeout(timer); };
  }, [text]);
  const valid = report?.text === text && report.validation?.valid === true;
  const changed = valid && (!remote?.source?.startsWith("rover_") || report.canonical_rcp !== remote?.canonical_rcp);
  const conflict = dirtyRef.current && base && remote?.source?.startsWith("rover_")
    && (base.canonical_rcp !== remote.canonical_rcp || base.rover_status?.revision !== remote.rover_status?.revision);
  const native = remote?.rover_status || snapshot?.parameters;

  async function apply() {
    if (!valid || !changed || conflict || applyingRef.current) return;
    applyingRef.current = true; setApplying(true);
    const candidate = report.parameters, canonical = report.canonical_rcp, originalBase = baseRef.current;
    try {
      const current = await api("motor-test/config");
      observe(current);
      if (current.canonical_rcp === canonical && current.source?.startsWith("rover_")) {
        setMessage("Az értékek változatlanok; nem küldtünk mentést és nem nőtt a revízió."); return;
      }
      if (originalBase && current.source?.startsWith("rover_") && (originalBase.canonical_rcp !== current.canonical_rcp || originalBase.rover_status?.revision !== current.rover_status?.revision)) {
        setMessage("A rover konfigurációja közben megváltozott. Hasonlítsd össze a helyi szerkesztéssel."); return;
      }
      const status = await api("motor-test/status"), live = status.snapshot;
      if (!live?.freshness?.fresh || live.parameters?.can_apply !== true || live.parameters?.revision !== current.rover_status?.revision) {
        setMessage(`A rover most nem fogad mentést: ${live?.parameters?.code || "nincs friss állapot"}.`); return;
      }
      const identity = live.identity, state = live.state, revision = live.parameters.revision, requestId = newRequestId();
      setReceipt({ request_id: requestId, esp_boot: identity.esp_boot, stm_boot: identity.stm_boot,
        expected_revision: revision + 1, parameters_crc: report.validation.parameters_crc });
      const result = await api("motor-test/apply", JSON.stringify({ v: 3, request_id: requestId,
        esp_boot: identity.esp_boot, stm_boot: identity.stm_boot, control_epoch: state.control_epoch,
        expected_revision: revision, parameters: candidate }));
      if (!alive.current) return;
      if (result.result === "UNCHANGED") {
        setReceipt(null);
        setMessage("Az értékek változatlanok; a roverre nem történt írás."); return;
      }
      if (result.result === "REJECTED") { setReceipt(null); setMessage(`A rover elutasította: ${result.code}.`); return; }
      setMessage(result.result === "UNKNOWN" ? "A válasz elveszett. Csak GET-tel ellenőrizzük az eredményt; nincs újraküldés."
        : "A rover befogadta a mentést; a tartós alkalmazás visszaigazolására várunk.");
    } catch (error) {
      if (alive.current) {
        if (error.httpStatus >= 400 && error.httpStatus < 500) setReceipt(null);
        setMessage(error.message);
        try { observe(await api("motor-test/config")); } catch {}
      }
    } finally { applyingRef.current = false; if (alive.current) setApplying(false); refresh(); }
  }
  async function readback(target = receipt) {
    if (!target) return;
    try {
      const result = await api(`motor-test/reconcile?${new URLSearchParams(target)}`);
      if (!alive.current) return;
      if (result.result === "APPLIED") {
        setReceipt(null);
        setMessage("Mentés igazolva: a rover tartós konfigurációja ACTIVE/APPLIED.");
        observe(await api("motor-test/config"));
      }
      refresh();
    } catch (error) { if (alive.current) setMessage(error.message); }
  }
  useEffect(() => {
    if (!receipt) return;
    let current = true, timer, attempts = 0;
    async function poll() {
      if (!current || !alive.current) return;
      await readback(receipt);
      if (current && alive.current && ++attempts < 20) timer = window.setTimeout(poll, 1000);
    }
    timer = window.setTimeout(poll, 500);
    return () => { current = false; window.clearTimeout(timer); };
  }, [receipt]);
  return <article className="panel mower-motor-test-config">
    <div className="panel-head"><h2>Rover konfiguráció</h2><span>{applying ? "Mentés…" : "A roverben tárolva"}</span></div>
    <p>A rover mentett értékeit szerkeszted. Megnyitás és újraindulás csak olvasást indít; változtatást a Mentés roverre gomb küld.</p>
    {remote?.source === "hc_cache" && <p>Korábbi HC-gyorsítótár látható; ez nem igazolt roverkonfiguráció.</p>}
    {conflict && <div role="alert"><p>A rover konfigurációja megváltozott. A helyi szerkesztésed megmaradt.</p>
      <p>Új rover revízió: {remote.rover_status?.revision}, CRC: {remote.rover_status?.parameters_crc}.</p>
      <details><summary>Roverben tárolt értékek összehasonlításhoz</summary><pre>{JSON.stringify(remote.parameters, null, 2)}</pre></details>
      <button type="button" onClick={() => { baseRef.current = remote; setBase(remote); }}>Helyi szerkesztés megtartása az új alaphoz</button>
    </div>}
    {remote?.parameters && <button type="button" onClick={() => load(remote)}>Rover értékeinek betöltése</button>}
    {snapshot?.identity?.minimal_erpm_parameters === true && <div className="mower-v3-command-buttons">
      <button type="button" onClick={() => {
        try {
          const p = JSON.parse(text), enabled = p.blade_enabled;
          if (p.drive_mode !== "ERPM") return;
          if (Object.keys(p).length === 31) setFullParameters(p);
          const keys = ["parameters_version", "robot_id", "drive_mode", "blade_enabled", "wheel_direction", "wheel_erpm_limit", "wheel_brake_ma", "motor_accel_erpm_s", "imu_mount_q_ppm", "tilt_limit_mdeg", ...(enabled ? ["blade_direction", "blade_erpm_limit", "blade_brake_ma"] : [])];
          const compact = Object.fromEntries(keys.map(key => [key, p[key]]));
          compact.motor_accel_erpm_s = p.motor_accel_erpm_s.slice(0, enabled ? 3 : 2);
          edit(JSON.stringify(compact, null, 2));
        } catch {}
      }}>Csak szükséges ERPM mezők</button>
      {fullParameters && Object.keys(fullParameters).length === 31 && <button type="button" onClick={() => {
        try {
          const p = JSON.parse(text), full = { ...fullParameters, ...p };
          if (p.motor_accel_erpm_s.length === 2) full.motor_accel_erpm_s = [...p.motor_accel_erpm_s, fullParameters.motor_accel_erpm_s[2]];
          edit(JSON.stringify(full, null, 2));
        } catch {}
      }}>Teljes konfiguráció</button>}
    </div>}
    <p>A kompakt ERPM 10/13 mező teljes csere: a kihagyott geometriai és kalibrációs adatok nullázódnak. Megőrzésükhöz a teljes konfigurációt használd.</p>
    <label>Konfiguráció<textarea rows={18} style={{ width: "100%", fontFamily: "monospace" }} value={text} maxLength={16384}
      onChange={(event) => edit(event.target.value)} /></label>
    <p>{valid ? `Érvényes konfiguráció · CRC ${report.validation.parameters_crc}${changed ? " · módosítva" : " · változatlan"}` : "A szerkesztett konfiguráció még hiányos vagy hibás."}</p>
    <div className="mower-v3-command-buttons">
      <button type="button" disabled={!valid || !changed || conflict || !fresh || native?.can_apply !== true || applying} aria-busy={applying} onClick={apply}>Mentés roverre</button>
      {receipt && <button type="button" onClick={() => readback()}>Eredmény visszaolvasása</button>}
    </div>
    <p>Rover visszajelzés: {native ? `${native.applied ? "alkalmazott" : "még nem alkalmazott"} · ${native.code || native.storage} · rev ${native.revision} · CRC ${native.parameters_crc || "—"}` : "Nincs konfigurációs visszajelzés."}</p>
    <p role="status">{message}</p>
  </article>;
}
