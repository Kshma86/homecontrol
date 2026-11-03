import React, { useState } from "react";
import { Lock, Power, Shield, Square, Radio, RefreshCw } from "lucide-react";
import { IconButton } from "../../uiPrimitives";
import { commandLabel, TERMINAL_RESULTS } from "./mowerV3Controls.mjs";

export function OperatorPanel({ operator, disconnect }) {
  const [password, setPassword] = useState("");
  return <article className="panel mower-v3-operator"><div className="panel-head"><h2><Lock size={18} />Kezelői hozzáférés</h2>
    <span>{operator.authenticated ? "Bejelentkezve" : "Állapotnézet"}</span></div>
    {!operator.configured ? <p>A vezérléshez a backend kezelői hitelesítésének beállítása szükséges.</p>
      : operator.authenticated ? <div><p>A vezérlés egy óráig érvényes kezelői munkamenethez kötött.</p>
        <IconButton icon={Lock} onClick={() => { disconnect(); operator.logout(); }}>Kijelentkezés</IconButton></div>
        : <form className="mower-v3-login" onSubmit={(event) => { event.preventDefault(); const input = password; setPassword(""); operator.login(input); }}>
          <label>Kezelői jelszó<input type="password" value={password} autoComplete="current-password" maxLength={256} onChange={(event) => setPassword(event.target.value)} /></label>
          <IconButton icon={Lock} type="submit" disabled={operator.busy || !password}>Bejelentkezés</IconButton>
        </form>}
    {operator.error && <p role="alert">{operator.error}</p>}
  </article>;
}

export function CommandPanel({ commands, state, identity, fresh, operator, manual, configured, motorTest = false, armAllowed = true }) {
  const [heading, setHeading] = useState("");
  const ready = fresh && operator.authenticated && !commands.busy && !commands.unresolved && (!identity?.update_locked || motorTest);
  function submit(command, value = null) {
    if (["arm", "start", "resume", "reset_fault"].includes(command)
        && !window.confirm(`${commandLabel(command)}? Ellenőrizd a rovert és a környezetét.`)) return;
    manual.zero();
    commands.submit(command, value);
  }
  return <article className="panel mower-v3-command-panel"><div className="panel-head"><h2><Shield size={18} />Vezérlés</h2><span>STM-visszaigazolással</span></div>
    <div className="mower-emergency"><button className="mower-stop" type="button" disabled={!operator.authenticated || !configured}
      onClick={() => { manual.disconnect(); commands.submit("stop"); }}><Square size={19} />STOP</button>
      <div><strong>Globális leállítás</strong><span>A STOP friss STM-állapot nélkül is kérhető. A befogadás még nem igazolja a megállást.</span></div></div>
    {!operator.authenticated ? <p>A vezérlőgombokhoz kezelői bejelentkezés szükséges.</p>
      : !fresh ? <p>A vezérléshez friss, igazolt roverállapot szükséges.</p>
      : !armAllowed && <p>Az élesítéshez előbb alkalmazd és egyeztesd a tesztkonfigurációt.</p>}
    <div className="mower-v3-command-buttons">
      {identity?.manual_claim_from_disarmed !== true && <IconButton icon={Power} disabled={!ready || !armAllowed || state?.state !== "DISARMED" || state?.stopped !== true} onClick={() => submit("arm")}>Élesítés</IconButton>}
      <IconButton icon={Power} disabled={!fresh || !operator.authenticated || identity?.update_locked && !motorTest || state?.state === "MAINTENANCE" || commands.busy} onClick={() => submit("disarm")}>Hatástalanítás</IconButton>
      {!motorTest && <IconButton icon={Square} disabled={!ready || state?.state !== "AUTO"} onClick={() => submit("pause")}>Szünet</IconButton>}
      <IconButton icon={Shield} disabled={!ready || state?.state !== "FAULT" || state?.stopped !== true} onClick={() => submit("reset_fault")}>Hiba törlése</IconButton>
      {!motorTest && <IconButton icon={Power} disabled={!ready || state?.ready_for_start !== true || state?.state !== "IDLE"} onClick={() => submit("start", { mission_id: state.mission_id, revision: state.revision, crc32: state.crc32 })}>Küldetés indítása</IconButton>}
      {!motorTest && <IconButton icon={Power} disabled={!ready || state?.ready_for_resume !== true || state?.state !== "PAUSED"} onClick={() => submit("resume", { mission_id: state.mission_id, revision: state.revision, crc32: state.crc32 })}>Folytatás</IconButton>}
    </div>
    {!motorTest && <div className="mower-v3-heading"><label>Álló rover ismert északi iránya <span>fok</span>
      <input type="number" min="0" max="359.999" step="0.001" value={heading} onChange={(event) => setHeading(event.target.value)} /></label>
      <IconButton icon={Shield} disabled={!ready || !["DISARMED", "IDLE"].includes(state?.state) || state?.stopped !== true || heading === "" || !Number.isFinite(Number(heading)) || Number(heading) < 0 || Number(heading) >= 360}
        onClick={() => submit("heading_set", { heading_mdeg: Math.round(Number(heading) * 1000) })}>Referencia beállítása</IconButton></div>}
    <div className="mower-v3-results" aria-live="polite">{commands.records.slice(0, 5).map((record) => <div key={record.request_id}>
      <strong>{commandLabel(record.command)}</strong><span className={record.result === "APPLIED" ? "applied" : ""}>{record.result === "APPLIED" ? "STM visszaigazolta" : record.result === "PENDING" ? "Visszaigazolásra vár" : record.result === "REJECTED" ? "Elutasítva" : "Eredmény ismeretlen"} · {record.code}</span>
      {!TERMINAL_RESULTS.has(record.result) && <IconButton icon={RefreshCw} disabled={!operator.authenticated} onClick={() => commands.reconcile(record.request_id)}>Egyeztetés</IconButton>}
      {record.command === "stop" && record.code === "NOT_READY" && <small>A rover frissítési útvonala nem fogadott STOP-ot; a megállás nem igazolt.</small>}
    </div>)}</div>
  </article>;
}

export function ManualPanel({ manual, canClaim, unavailableReason = "" }) {
  const active = manual.phase === "ACTIVE";
  const lease = manual.lease;
  return <article className="panel mower-v3-manual"><div className="panel-head"><h2><Radio size={18} />Kézi vezérlés</h2><span>{active ? `Lease ${lease.lease_id}` : "Backend WebSocket"}</span></div>
    <p role="status">{manual.message}</p>
    {!canClaim && unavailableReason && <p role="status">{unavailableReason}</p>}
    <div className="mower-v3-command-buttons"><IconButton icon={Radio} disabled={!canClaim || manual.phase !== "DISCONNECTED"} onClick={manual.connect}>Kézi mód</IconButton>
      <IconButton icon={Square} disabled={!active} onClick={() => manual.disconnect()}>Kézi kapcsolat lezárása</IconButton></div>
    {lease?.drive_mode === "ERPM" ? <div className="mower-v3-manual-inputs">
      {["left", "right", "third"].map((field, index) => <label key={field}>{["Bal motor · CAN 1", "Jobb motor · CAN 2", "Harmadik motor · CAN 3"][index]} <span>eRPM</span>
        <input type="range" disabled={!active || index === 2 && !manual.intent.thirdEnabled} min={-lease.motor_erpm_limits[index]} max={lease.motor_erpm_limits[index]} step="1" value={manual.intent[field] || 0}
          onChange={(event) => manual.setIntent({ ...manual.intent, [field]: Number(event.target.value) })} /><output>{manual.intent[field] || 0} eRPM</output></label>)}
      <label><input type="checkbox" disabled={!active || !lease.motor_erpm_limits[2]} checked={manual.intent.thirdEnabled === true}
        onChange={(event) => { manual.zero(); manual.setIntent({ ...manual.intent, left: 0, right: 0, third: 0, thirdEnabled: event.target.checked }); }} />Harmadik motor engedélyezése · kés nélküli próba</label>
    </div> : <div className="mower-v3-manual-inputs">
      <label>Haladás <span>mm/s</span><input type="range" disabled={!active} min={-(lease?.max_linear_mm_s || 0)} max={lease?.max_linear_mm_s || 0} step="1" value={manual.intent.linear}
        onChange={(event) => manual.setIntent({ ...manual.intent, linear: Number(event.target.value) })} /><output>{manual.intent.linear} mm/s</output></label>
      <label>Fordulás <span>millifok/s</span><input type="range" disabled={!active} min={-(lease?.max_yaw_mdeg_s || 0)} max={lease?.max_yaw_mdeg_s || 0} step="1" value={manual.intent.yaw}
        onChange={(event) => manual.setIntent({ ...manual.intent, yaw: Number(event.target.value) })} /><output>{manual.intent.yaw} millifok/s</output></label>
    </div>}
    <button className={`mower-v3-deadman ${manual.held ? "held" : ""}`} type="button" disabled={!active}
      onPointerDown={(event) => { if (event.button !== 0 || !event.isPrimary) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); manual.hold(); }}
      onPointerUp={manual.zero} onPointerCancel={manual.zero} onLostPointerCapture={manual.zero}
      onKeyDown={(event) => { if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); if (!event.repeat) manual.hold(); } }}
      onKeyUp={(event) => { if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); manual.zero(); } }} onBlur={manual.zero}>
      {manual.held ? "DEADMAN NYOMVA — vezérlés küldése" : "TARTSD NYOMVA A MOZGÁSHOZ"}
    </button>
    <IconButton icon={Square} disabled={!active} onClick={() => { manual.zero(); manual.setIntent({ linear: 0, yaw: 0 }); }}>Kézi célértékek nullázása</IconButton>
    <p className="mower-safety-note">{lease?.drive_mode === "ERPM" ? "Kés nélküli, felügyelt motorpróba. Elengedéskor mindhárom cél nulla; a harmadik motor külön engedélyt igényel." : "A kés célfordulata ebben a változatban mindig nulla."} Elengedés, fókuszvesztés és kapcsolatvesztés nem folytatja a mozgást.</p>
    <p>STM megfigyelés: {manual.observed ? `${manual.observed.state} · ${manual.observed.stopped ? "megállt" : "nincs megállva"} · input ${manual.observed.last_input_seq}` : "Még nincs igazolt kézi állapot."}</p>
  </article>;
}
