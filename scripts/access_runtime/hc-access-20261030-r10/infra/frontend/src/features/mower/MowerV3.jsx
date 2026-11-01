import { canClaimManual } from "./mowerV3Controls.mjs";
import React, { useEffect, useRef, useState } from "react";
import { Activity, Archive, Cpu, Gauge, Leaf, Radio, RefreshCw, Route, Shield, Upload } from "lucide-react";
import { Card, IconButton } from "../../uiPrimitives";
import useMowerV3Snapshot from "./useMowerV3Snapshot";
import useMowerOperator from "./useMowerOperator";
import useMowerCommands from "./useMowerCommands";
import useMowerManual from "./useMowerManual";
import { CommandPanel, ManualPanel } from "./MowerV3Controls";
import RtkEditor from "./RtkEditor";
import MowerMotorTestConfig from "./MowerMotorTestConfig";
import { currentState, displayBoolean, displayMask } from "./mowerV3Model.mjs";
import "./mowerV3.css";

const CONNECTION_LABELS = {
  UNCONFIGURED: "Nincs beállítva", LIVE: "Élő kapcsolat", STALE: "Elavult STM-adat",
  UPDATE_MODE: "Frissítési mód", AUTH_FAILED: "Hitelesítési hiba", UNREACHABLE: "Rover nem érhető el",
  INCOMPATIBLE_VERSION: "Eltérő protokoll", INVALID_RESPONSE: "Hibás roverválasz",
  REDIRECT_BLOCKED: "Átirányítás elutasítva", HTTP_ERROR: "Rover API-hiba", BUSY: "Lekérés folyamatban",
  HC_UPDATE_PENDING: "HC frissítési zárolás", UPDATE_STORAGE_UNAVAILABLE: "Frissítési zárolás nem ellenőrizhető",
};

function Row({ label, value }) {
  return <div className="mower-data-row"><span>{label}</span><strong>{value ?? "Ismeretlen"}</strong></div>;
}

function Capability({ supported }) {
  return <span className={`mower-v3-capability ${supported ? "supported" : ""}`}>
    {supported ? "Rover támogatja" : "Roveren nem elérhető"}
  </span>;
}

function MowerOperational({ motorTest = false }) {
  const [projectMessage, setProjectMessage] = useState("");
  const { snapshot, receivedAt, now, loading, error, refresh } = useMowerV3Snapshot();
  const view = currentState(snapshot, receivedAt, now);
  const operator = useMowerOperator();
  const identity = snapshot?.identity;
  const fresh = view.fresh && !error;
  const state = fresh ? view.state : null;
  const capabilities = snapshot?.capabilities;
  const commands = useMowerCommands({ identity, state, authenticated: true, refresh });
  const manual = useMowerManual({ snapshot, receivedAt, error, authenticated: true, refresh });
  useEffect(() => {
    for (const key of ["hc.mower.v3.update.pending-create.v1", "hc.mower.v3.update.pending-action.v1", "hc-motor-test-draft-v2"]) {
      try { sessionStorage.removeItem(key); } catch {}
    }
  }, []);
  const connection = error ? "HC nem érhető el" : CONNECTION_LABELS[snapshot?.connection?.status] || "Kapcsolódás…";
  const observed = snapshot?.state;
  const progress = state && Number.isInteger(state.segment_count) && state.segment_count > 0
    ? Math.min(100, state.segment_index / state.segment_count * 100) : null;

  return <section className="page-stack mower-page mower-v3-page">
    <div className="page-heading mower-heading">
      <div><span className="eyebrow">Rover · HC superuser</span><h1>Mower</h1>
        <p>Az STM által jelentett állapot, kapcsolatok és roverfunkciók.</p></div>
      <div className="mower-heading-actions">
        <span className={`mower-pill ${fresh ? "ok" : "warn"}`}>{connection}</span>
        <IconButton icon={RefreshCw} disabled={loading} aria-busy={loading} onClick={refresh}>Frissítés</IconButton>
      </div>
    </div>

    <div className="mower-v3-stage"><Leaf size={19} aria-hidden="true" /><div>
      <strong>Rover vezérlés</strong>
      <span>{motorTest ? "HC superuser · közvetlen vezérlés · egyetlen szerkeszthető konfiguráció." : "Kézi rovervezérlés, konfiguráció és projekt-előkészítés."}</span>
    </div><a href="#mower-legacy"><Archive size={15} />Legacy</a></div>

    {(error || snapshot?.connection?.detail && !fresh) && <div className="inline-alert warning" role="status">
      <Radio size={18} aria-hidden="true" />{error || snapshot.connection.detail}
    </div>}


    <div className="card-grid mower-v3-overview">
      <Card title="STM állapot" value={state?.state || "ISMERETLEN"} meta={fresh ? "STM-forrásból" : "Nincs friss, igazolt állapot"} icon={Cpu} />
      <Card title="Mozgás" value={displayBoolean(state?.stopped, "MEGÁLLT", "NINCS MEGÁLLVA")}
        meta={`Élesítés: ${displayBoolean(state?.armed, "élesítve", "nincs élesítve")}`} icon={Gauge} />
      <Card title="Küldetés" value={state?.store || "ISMERETLEN"} meta={state?.outcome || "Nincs friss küldetésállapot"} icon={Route} />
      <Card title="Adatfrissesség" value={fresh ? "FRISS" : "NEM IGAZOLT"}
        meta={view.effectiveAge === null ? "Forráskora ismeretlen" : `Forráskor: ${Math.ceil(view.effectiveAge)} ms · határ: 1500 ms`} icon={Activity} />
    </div>

    <div className="mower-v3-grid">
      <CommandPanel commands={commands} state={state} identity={identity} fresh={fresh} operator={operator} manual={manual} motorTest={identity?.autonomous_enabled !== true} armAllowed={true} configured={snapshot?.configured === true} />
      <article className="panel"><div className="panel-head"><h2><Shield size={18} />Üzemi állapot</h2>
        <span>{fresh ? "Élő STM" : "Ismeretlen / elavult"}</span></div>
        <div className="mower-data-list">
          <Row label="Állapot" value={state?.state} /><Row label="Végrehajtási fázis" value={state?.phase} />
          <Row label="Ok" value={state?.reason} /><Row label="Hibamaszk" value={displayMask(state?.fault_mask)} />
          <Row label="Telepített biztonsági bemenetek" value={displayMask(state?.safety_installed_mask)} />
          <Row label="Aktív biztonsági bemenetek" value={displayMask(state?.safety_active_mask)} />
          <Row label="Vezérlési epoch" value={state?.control_epoch} />
        </div>
        {!fresh && observed && <p className="mower-safety-note">Utolsó megfigyelt állapot: {observed.state ?? "ismeretlen"}. Ez nem igazolja a rover jelenlegi állapotát.</p>}
      </article>

      <article className="panel"><div className="panel-head"><h2><Cpu size={18} />Roverazonosság</h2><span>3.1.0</span></div>
        <div className="mower-data-list">
          <Row label="UART kapcsolat" value={snapshot?.health ? snapshot.health.uart_recovering ? "Helyreállítás folyamatban" : snapshot.health.uart_rx_closed ? "Zárt" : "Nyitott" : "—"} />
          <Row label="UART helyreállítások" value={snapshot?.health ? `${snapshot.health.uart_recovery_completed} kész / ${snapshot.health.uart_recovery_attempts} kísérlet` : "—"} />
          <Row label="Kézi WS minimum veremtartalék" value={Number.isInteger(snapshot?.health?.esp_stack_min_bytes?.manual_ws) ? `${snapshot.health.esp_stack_min_bytes.manual_ws} bájt` : "Még nincs mérés"} />
          <Row label="ESP firmware" value={identity?.esp_fw} /><Row label="STM firmware" value={identity?.stm_fw} />
          <Row label="ESP boot" value={identity?.esp_boot} /><Row label="STM boot" value={identity?.stm_boot} />
          <Row label="Profil CRC" value={identity?.profile_crc} /><Row label="Flash-kiosztás" value={identity?.stm_flash_layout} />
          <Row label="Protokoll-kompatibilitás" value={displayBoolean(identity?.compatible, "Kompatibilis", "Nem kompatibilis")} />
          <Row label="Teljes v3.1 megfelelőség" value={displayBoolean(identity?.conformant, "Rover igazolja", "Rover nem igazolja")} />
        </div>
      </article>

      <article className="panel"><div className="panel-head"><h2><Route size={18} />Küldetésállapot</h2><span>RVM3</span></div>
        <div className="mower-data-list">
          <Row label="Tárolási állapot" value={state?.store} /><Row label="Küldetésazonosító" value={state?.mission_id} />
          <Row label="Revision" value={state?.revision} /><Row label="CRC" value={state?.crc32} />
          <Row label="Szegmens" value={state && state.segment_count !== null ? `${state.segment_index} / ${state.segment_count}` : null} />
          <Row label="Indításra kész" value={displayBoolean(state?.ready_for_start, "STM szerint igen", "STM szerint nem")} />
          <Row label="Folytatásra kész" value={displayBoolean(state?.ready_for_resume, "STM szerint igen", "STM szerint nem")} />
        </div>
        {progress !== null && <progress className="mower-v3-progress" max="100" value={progress} aria-label="Küldetés szegmenselőrehaladása" />}
        <p className="mower-safety-note">Az RTK editor egyelőre a korábbi változatban maradt. Az RVM3 feltöltés még nincs bekötve.</p>
      </article>

      <ManualPanel manual={manual} unavailableReason={snapshot?.health?.uart_recovering ? "A rover UART kapcsolatot állít helyre." : identity?.test_manual_control === false && identity?.mode === "MOTOR_TEST" ? `A rover még nem enged kézi módot: ${snapshot?.parameters?.code || "natív feltételek nem teljesülnek"}.` : ""} canClaim={fresh && operator.authenticated && canClaimManual(snapshot, state)
        && !commands.busy} />

      <article className="panel"><div className="panel-head"><h2><Upload size={18} />Firmware-frissítés</h2>
        <Capability supported={capabilities?.stm_update === true} /></div>
        <div className="mower-data-list">
          <Row label="Frissítési zárolás" value={displayBoolean(identity?.update_locked, "Zárolva", "Nincs zárolva")} />
          <Row label="STM service ABI" value={identity?.update_service_abi} />
          <Row label="STM képméret maximum" value={identity ? `${identity.stm_image_max_bytes.toLocaleString("hu-HU")} bájt` : null} />
          <Row label="ESP OTA kapacitás" value={identity ? `${identity.esp_ota_max_bytes.toLocaleString("hu-HU")} bájt` : null} />
        </div><p className="mower-safety-note">A MOTOR_TEST firmware távoli frissítést nem támogat. Ez a visszajelzés nem tiltja a kézi vezérlést.</p>
      </article>

    </div>

    <MowerMotorTestConfig snapshot={snapshot} fresh={fresh} refresh={refresh} />
    <details className="panel" onToggle={(event) => { if (event.currentTarget.open) window.dispatchEvent(new Event("resize")); }}><summary>Térkép és kaszálási projekt szerkesztése</summary>
      <p>A projekt importálható, szerkeszthető és menthető. {identity?.autonomous_enabled === false ? "A jelenlegi MOTOR_TEST firmware autonóm végrehajtást nem támogat." : "A rover küldetésformátumának megfelelő végrehajtási firmware szükséges."}</p>
      <RtkEditor planningOnly setToast={setProjectMessage} />
      {projectMessage && <p role="status">{projectMessage}</p>}
    </details>

    <details className="panel mower-v3-diagnostics"><summary>Integrációs diagnosztika</summary>
      <p>A legutóbbi ellenőrzött lekérés adatai. A pillanatnyi érvényességet az adatfrissesség jelzi.</p>
      <pre>{JSON.stringify(snapshot ? { connection: snapshot.connection, identity, state: observed, freshness: snapshot.freshness } : { status: "WAITING" }, null, 2)}</pre>
    </details>
  </section>;
}

export default function MowerV3() {
  return <MowerOperational motorTest />;
}
