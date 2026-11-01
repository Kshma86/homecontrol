import React, { useState } from "react";
import { Shield, RefreshCw, Upload } from "lucide-react";
import { IconButton } from "../../uiPrimitives";
import { displayBoolean } from "./mowerV3Model.mjs";

export default function MowerFirmwareSession({ updates, jobs = [], busy, onBeforeCreate }) {
  const [jobId, setJobId] = useState("");
  if (!updates) return null;
  const result = updates.result, attempt = result?.attempt, observed = result?.observation || updates.lastObservation;
  const effectiveAge = result?.observation ? updates.effectiveAge : updates.lastAge;
  const selected = jobs.find((job) => job.hc_job_id === jobId);
  const matching = selected && selected.metadata.profile_crc === result?.identity?.profile_crc;
  function create() {
    if (!window.confirm("Natív frissítési session előkészítése? Ez törli a rover futó küldetését, checkpointját, heading referenciáját és kézi lease-ét, és karbantartási módba viszi. Visszatéréshez explicit FINISH és külön HC-ellenőrzés kell. Folytatod?")) return;
    onBeforeCreate?.();
    void updates.create(jobId);
  }
  function perform(action) {
    const warnings = { IMAGE:"A HC-ban megőrzött, újraellenőrzött RFU2-kép egyszeri feltöltése? Nincs automatikus újraküldés, FINISH vagy ARM.",
      ABORT:"A natív frissítés megszakítása? A zárolás megmarad; a már megerősített telepítést az ABORT nem vonja vissza.",
      FINISH:"Kilépés a karbantartásból? A rover újraindítja a normál szolgáltatásokat. Ez nem ARM vagy START; a HC-zárolás külön visszatérési ellenőrzésig megmarad.",
      VERIFY_EXIT:"A normál visszatérés ellenőrzése és a HC-zárolás feloldása? Csak friss új boot/EMPTY állapot és natív IDLE engedi. Nem indít mozgást." };
    if (!warnings[action] || !window.confirm(warnings[action])) return;
    onBeforeCreate?.(); void updates.perform(action);
  }
  return <section className="mower-firmware-storage mower-firmware-session" aria-label="Natív frissítési session">
    <h3><Shield size={18} />Natív STM frissítés — előkészítés, feltöltés és lezárás</h3>
    <p>A create törli a rover futó küldetését, checkpointját, heading referenciáját és kézi lease-ét. A képfeltöltés, ABORT, FINISH és a HC-visszatérési ellenőrzés külön, explicit lépés. Nincs automatikus ARM vagy START.</p>
    <label>Mentett HC-feladat<select value={jobId} disabled={busy || updates.busy || updates.blocked} onChange={(event) => setJobId(event.target.value)}>
      <option value="">Válassz ellenőrzött HC-mentést</option>{jobs.map((job) => <option key={job.hc_job_id} value={job.hc_job_id}>{job.release_id} · {job.hc_job_id}</option>)}
    </select></label>
    {selected && !matching && <p className="mower-firmware-preflight-warning">A mentés profilja nem egyeztethető a jelenlegi roverazonossággal.</p>}
    <div className="mower-v3-command-buttons">
      <IconButton icon={Shield} disabled={busy || updates.busy || updates.blocked || !updates.canCreate || !matching} onClick={create}>Session létrehozása — runtime törléssel</IconButton>
      <IconButton icon={RefreshCw} disabled={updates.busy || !updates.canRead} onClick={updates.refresh}>Session egyeztetése — csak GET</IconButton>
      <IconButton icon={Upload} disabled={updates.busy || !!updates.pending || !updates.canUpload} onClick={() => perform("IMAGE")}>RFU2-kép feltöltése — egyszer</IconButton>
      <IconButton icon={Shield} disabled={updates.busy || !!updates.pending || !updates.canAbort} onClick={() => perform("ABORT")}>ABORT — zárolás megmarad</IconButton>
      <IconButton icon={Shield} disabled={updates.busy || !!updates.pending || !updates.canFinish} onClick={() => perform("FINISH")}>FINISH — explicit kilépés</IconButton>
      <IconButton icon={Shield} disabled={updates.busy || !!updates.pending || !updates.canVerifyExit} onClick={() => perform("VERIFY_EXIT")}>Normál visszatérés ellenőrzése</IconButton>
    </div>
    {!updates.canRead && <p className="mower-safety-note">A natív session megfigyeléséhez és előkészítéséhez kezelői bejelentkezés szükséges.</p>}
    {updates.pending && <p className="mower-firmware-preflight-warning" role="status">ISMERETLEN frissítési kérés · nincs újraküldés. Az üzemi vezérlés letiltva.</p>}
    {updates.error && <div className="inline-alert error" role="alert">{updates.error}</div>}
    <p role="status">Session-kapcsolat: {result?.connection?.status || "Még nincs igazolt megfigyelés"} · {updates.blocked ? "Üzemi vezérlés zárolva" : "Nincs ismert HC frissítési zárolás"}</p>
    {attempt && <div className="mower-data-list">
      <div className="mower-data-row"><span>HC create eredmény</span><strong>{attempt.state} · {attempt.code}</strong></div>
      <div className="mower-data-row"><span>Kérésazonosító</span><strong>{attempt.request_id}</strong></div>
      <div className="mower-data-row"><span>Natív update_id</span><strong>{attempt.update_id || "ISMERETLEN — nem vehető át másik session"}</strong></div>
    </div>}
    {result?.operations?.map((operation) => <p key={operation.request_id}>{operation.action} · {operation.state} · {operation.code} · {operation.request_id}</p>)}
    {updates.lastAction?.exit && <p role="status">A HC-visszatérési ellenőrzés tartósan mentve: {updates.lastAction.exit.proof.state} / EMPTY · boot {updates.lastAction.exit.proof.stm_boot}. Új művelet csak új, friss üzemi állapottal és explicit kezelői kéréssel indulhat.</p>}
    {observed && <div className="mower-firmware-preflight-report">
      <strong>{!result?.observation ? "Utolsó megfigyelés — nem aktuális session-igazolás" : result.bound ? "Megőrzött natív session megfigyelése" : "Nem kötött megfigyelés — nem HC session-igazolás"}</strong>
      <span>{updates.fresh ? "Friss STM service-forrás" : "Elavult / nem igazolt STM service-forrás"}</span>
      <div className="mower-data-list">{[
        ["Megfigyelt fázis", observed.phase], ["Hiba / részlet", `${observed.error} / ${observed.detail}`],
        ["Forrás / service boot", `${observed.source} / ${observed.stm_service_boot || "ismeretlen"}`],
        ["Forráskor", effectiveAge === null ? "Ismeretlen" : `${Math.ceil(effectiveAge)} ms · határ: 2000 ms`],
        ["HTTP befogadott bájt", `${observed.http_received_bytes} / ${observed.image_bytes}`],
        ["STM írt bájt", observed.stm_written_bytes === null ? "Ismeretlen" : `${observed.stm_written_bytes} / ${observed.image_bytes}`],
        ["CAN aktív", displayBoolean(updates.fresh ? observed.can_active : null, "Igen", "Nem")],
        ["Kimeneti tiltás", displayBoolean(updates.fresh ? observed.outputs_inhibited : null, "Igazolt", "Nincs igazolva")],
        ["Megállási bizonyíték / kor", `${observed.stop_evidence} / ${observed.stop_evidence_age_ms ?? "ismeretlen"} ms`],
      ].map(([label, value]) => <div className="mower-data-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <p>{updates.ready ? "A megőrzött session loader READY állapota friss és igazolt. A feltöltés külön gombbal indítható, ha nincs korábbi küldési szándék." : "Nincs friss, kötött loader READY igazolás."}</p>
      {updates.installed && <p>Friss loader COMPLETE és a mentett képpel egyező metadata figyelhető meg. Ez nem hardveres minősítés vagy üzemi visszatérés.</p>}
      <p>A HTTP 202, a bájtszámlálók vagy a TRIAL/APP ACK nem telepítési siker. A megállás, kilépés és normál üzem nem következtethető a kapcsolat hiányából.</p>
    </div>}
  </section>;
}
