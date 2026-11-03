import React from "react";
import { FileCheck, Upload, Save, RefreshCw } from "lucide-react";
import { IconButton } from "../../uiPrimitives";
import useMowerFirmware from "./useMowerFirmware";
import useMowerFirmwareStorage from "./useMowerFirmwareStorage";
import MowerFirmwareSession from "./MowerFirmwareSession";

export default function MowerFirmwarePreflight({ operator, updates, onBeforeCreate }) {
  const editor = useMowerFirmware();
  const storage = useMowerFirmwareStorage(editor, operator?.authenticated === true);
  const busy = editor.busy || storage.busy;
  const metadata = editor.report?.metadata;
  return <article className="panel mower-firmware-preflight">
    <div className="panel-head"><h2><FileCheck size={18} />Firmware előellenőrzés</h2><span>HC-only · VG / RFU2 / ELF</span></div>
    <p>A fájlpár ellenőrzése rover nélkül is működik. Nem hoz létre frissítési sessiont és nem tölt fel a roverre. A jóváhagyott fájlpár külön kezelői művelettel elmenthető a HC-ba.</p>
    <div className="mower-firmware-preflight-inputs">
      <label>STM RFU2 alkalmazáskép (.bin)<input type="file" accept=".bin,application/octet-stream" disabled={busy} onChange={(event) => editor.choose("image", event.target.files?.[0] || null)} /><small>1280–524288 bájt · 32 bájtra igazítva · APP @ 0x08100000</small></label>
      <label>A képhez tartozó ELF<input type="file" accept=".elf,application/octet-stream" disabled={busy} onChange={(event) => editor.choose("elf", event.target.files?.[0] || null)} /><small>Legfeljebb 16 MiB · tényleges ELF/RAM és bináris egyezés</small></label>
      <label>Szerveroldalon jóváhagyott kiadás<select value={editor.releaseId} disabled={busy} onChange={(event) => editor.choose("release", event.target.value)}>
        <option value="">Csak szerkezeti ellenőrzés — nincs kiadásjóváhagyás</option>
        {editor.releases.map((release) => <option key={release.release_id} value={release.release_id}>{release.release_id} · {release.firmware_id}</option>)}
      </select><small>A fájlból számított hash és egy feltöltött metadata JSON nem kiadási jóváhagyás.</small></label>
    </div>
    {editor.catalogError && <p className="mower-firmware-preflight-warning" role="status">{editor.catalogError}</p>}
    {!editor.releases.length && <p className="mower-firmware-preflight-warning">Nincs betöltött jóváhagyott kiadás. A fájlok vizsgálata nem teszi őket jóváhagyottá.</p>}
    <div className="mower-v3-command-buttons">
      <IconButton icon={FileCheck} disabled={busy || !!editor.problem} onClick={editor.inspect}>{editor.busy ? "Ellenőrzés…" : "Fájlpár ellenőrzése a HC-n"}</IconButton>
      <IconButton icon={Save} disabled={busy || !!storage.pending || operator?.authenticated !== true || editor.report?.release_verified !== true} onClick={storage.stage}>Jóváhagyott fájlpár mentése a HC-ba</IconButton>
      <IconButton icon={Upload} disabled>Feltöltés a roverre — még nem elérhető</IconButton>
    </div>
    {editor.problem && <p className="mower-safety-note">{editor.problem}</p>}
    {editor.error && <div className="inline-alert error" role="alert">{editor.error}</div>}
    {metadata && <div className="mower-firmware-preflight-report" role="status">
      <strong>{editor.report.release_verified ? "A szerveroldali kiadási listával egyező fájlpár" : "Szerkezetileg ellenőrzött fájlpár — NEM jóváhagyott kiadás"}</strong>
      <span>RFU2 / RTE2, ELF és induláskori RAM-ellenőrzés: megfelelt.</span>
      <div className="mower-data-list">{[
        ["Firmware-azonosító", metadata.fw_id], ["Kiosztás / slot", `${metadata.layout} / ${metadata.slot}`],
        ["Képméret", `${metadata.image_bytes} bájt`], ["Kép profil-CRC", metadata.profile_crc],
        ["Teljes kép SHA-256", metadata.image_sha256], ["ELF SHA-256", editor.report.elf_sha256],
      ].map(([label, value]) => <div className="mower-data-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
      <p>{editor.report.warning}</p><p>Az aktív roverprofillal való egyezés, a friss loader READY és a hardveres minősítés nincs igazolva. Az előellenőrzés nem engedélyez mozgást vagy frissítést.</p>
    </div>}
    <section className="mower-firmware-storage" aria-label="HC firmware-tároló">
      <h3>HC-tároló és előkészített feladatok</h3>
      <p>A HC_STAGED csak tartós HC-mentés: nem roverfrissítés, nem natív update_id, és nem telepítési engedély. A jóváhagyás a mentéskori kiadási listára vonatkozik.</p>
      {operator?.authenticated !== true && <p className="mower-safety-note">A mentéshez és az előzményekhez kezelői bejelentkezés szükséges.</p>}
      <div className="mower-v3-command-buttons">
        <IconButton icon={RefreshCw} disabled={busy || operator?.authenticated !== true} onClick={storage.refresh}>HC-előzmények visszaolvasása</IconButton>
        {storage.pending && <IconButton icon={RefreshCw} disabled={busy || operator?.authenticated !== true || storage.pending.invalid} onClick={storage.reconcile}>Ismeretlen mentés egyeztetése — csak GET</IconButton>}
      </div>
      {storage.pending && <p className="mower-firmware-preflight-warning" role="status">ISMERETLEN HC-mentés{storage.pending.requestId ? ` · ${storage.pending.requestId}` : ""}. Új mentés letiltva; nincs automatikus újraküldés.</p>}
      {storage.error && <div className="inline-alert error" role="alert">{storage.error}</div>}
      {storage.saved && <p role="status">Tartós HC-mentés visszaigazolva · {storage.saved.hc_job_id}. A HC-mentés önmagában nem roverfeltöltés.</p>}
      {operator?.authenticated === true && storage.jobs.length > 0 && <ul className="mower-firmware-job-list">{storage.jobs.map((job) => <li key={job.hc_job_id}>
        <strong>{job.release_id} · {job.state}</strong><span>{job.metadata.fw_id} · {job.metadata.image_bytes} bájt</span>
        <span>HC feladatazonosító: {job.hc_job_id}</span><time dateTime={job.saved_at}>{new Date(job.saved_at).toLocaleString("hu-HU")}</time>
      </li>)}</ul>}
    </section>
    <MowerFirmwareSession updates={updates} jobs={storage.jobs} busy={busy || !!storage.pending} onBeforeCreate={onBeforeCreate} />
  </article>;
}
