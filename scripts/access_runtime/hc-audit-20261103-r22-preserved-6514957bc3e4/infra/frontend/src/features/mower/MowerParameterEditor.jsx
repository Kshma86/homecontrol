import React, { useRef } from "react";
import { Download, FileInput, History, RefreshCw, Save, SlidersHorizontal } from "lucide-react";
import { IconButton } from "../../uiPrimitives";
import useMowerParameters from "./useMowerParameters";
import { FIELD_LABELS, PARAMETER_GROUPS, fieldUnit } from "./mowerParametersModel.mjs";

export default function MowerParameterEditor({ operator }) {
  const editor = useMowerParameters(operator.authenticated);
  const fileRef = useRef(null);
  const issues = [...editor.clientErrors, ...(editor.report?.errors || [])];

  function field(name) {
    const spec = editor.schema.properties[name], value = editor.form[name];
    const errors = issues.filter((item) => item.field === name || item.field.startsWith(`${name}[`));
    const scalar = (raw, item, index = null) => <input type="text" inputMode={item.type === "integer" ? "numeric" : undefined}
      value={raw} disabled={editor.busy} readOnly={name === "parameters_version"} placeholder="Ismeretlen" maxLength={item.type === "string" ? 32 : 16}
      aria-label={`${FIELD_LABELS[name] || name}${index === null ? "" : ` · ${index + 1}. elem`}`} aria-invalid={errors.length > 0}
      onChange={(event) => editor.edit(name, event.target.value, index)} />;
    const bounds = spec.type === "array" ? spec.items : spec;
    return <div className="mower-param-field" key={name}>
      <div className="mower-param-label">{FIELD_LABELS[name] || name}<span>{fieldUnit(name)}</span></div>
      <code>{name}</code>
      {spec.type === "boolean" ? <select aria-label={FIELD_LABELS[name]} value={value} disabled={editor.busy} onChange={(event) => editor.edit(name, event.target.value)}>
        <option value="">Ismeretlen</option><option value="false">Nem</option><option value="true">Igen (csak draftadat)</option></select>
        : spec.type === "array" ? <div className="mower-param-array">{value.map((item, index) => <div key={index}><small>{index + 1}. elem</small>{scalar(item, spec.items, index)}</div>)}</div>
          : scalar(value, spec)}
      {bounds.enum && <small>Megengedett: {bounds.enum.join(" / ")}</small>}
      {bounds.minimum !== undefined && <small>Határ: {bounds.minimum.toLocaleString("hu-HU")}…{bounds.maximum.toLocaleString("hu-HU")}</small>}
      {errors.map((error, index) => <small className="mower-param-error" key={index}>{error.message}</small>)}
    </div>;
  }

  return <article className="panel mower-v3-parameters"><div className="panel-head"><h2><SlidersHorizontal size={18} />Roverparaméterek · RCP1</h2><span>HC draft · nem aktív konfiguráció</span></div>
    <p>A szerkesztő rover nélkül is használható. Az üres érték ismeretlen. A helyes JSON és a CRC nem minősíti a fizikailag mért fékezést, geometriát vagy kalibrációt.</p>
    <div className="mower-param-target">
      <label>HC roverazonosító<input type="text" value={editor.keyInput} maxLength={32} placeholder="Saját HC-azonosító" disabled={editor.busy || !!editor.pending}
        onChange={(event) => editor.setKeyInput(event.target.value)} list="mower-param-rovers" /></label>
      <datalist id="mower-param-rovers">{editor.drafts.map((draft) => <option key={draft.rover_key} value={draft.rover_key}>HC r{draft.draft_revision}</option>)}</datalist>
      <IconButton icon={RefreshCw} disabled={!editor.schema || editor.busy || !!editor.pending || !/^[A-Za-z0-9_-]{1,32}$/.test(editor.keyInput)} onClick={editor.load}>Draft betöltése / új rover</IconButton>
      <span>{editor.key ? `${editor.key} · HC r${editor.revision}${editor.dirty ? " · helyi módosítás" : ""}` : "Még nincs HC roverhez rendelve"}</span>
    </div>
    <p className="mower-safety-note">A HC roverazonosító helyi tárolási kulcs, nem bizonyítja a fizikai STM azonosságát. A paramétercsomag robotazonosítója külön mező.</p>
    <div className={`mower-param-status ${editor.status.error ? "warning" : ""}`} role="status">{editor.status.message}</div>
    {editor.pending && <div className="mower-param-pending"><p>Mentésazonosító: <code>{editor.pending.request_id}</code> · Egyeztetés kizárólag GET visszaolvasással.</p>
      <IconButton icon={RefreshCw} disabled={editor.busy} onClick={editor.reconcile}>Mentés egyeztetése</IconButton></div>}
    <div className="mower-v3-command-buttons">
      <IconButton icon={Save} disabled={!editor.canSave} onClick={editor.save}>Draft mentése HC-ba</IconButton>
      <IconButton icon={FileInput} disabled={!editor.schema || editor.busy} onClick={() => fileRef.current?.click()}>JSON / RCP1 import</IconButton>
      <input ref={fileRef} type="file" accept=".json,.rcp1,application/json" hidden onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; editor.importFile(file); }} />
      <IconButton icon={Download} disabled={!editor.schema || editor.clientErrors.length > 0} onClick={editor.exportJson}>Helyi JSON export</IconButton>
      {editor.rcp1Export ? <a className="mower-param-export" href={editor.rcp1Export}><Download size={16} />Mentett RCP1 export</a>
        : <IconButton icon={Download} disabled title="Teljes, valid és HC-ba mentett draft szükséges.">Mentett RCP1 export</IconButton>}
      <button type="button" disabled title="Nincs egyeztetett roveroldali paraméter-API; a firmware OTA nem helyettesíti.">Alkalmazás a roveren — nem elérhető</button>
    </div>
    {!operator.authenticated && <p className="mower-safety-note">Szerkesztés, ellenőrzés és import/export bejelentkezés nélkül is elérhető. A tartós HC-mentéshez kezelői belépés kell, roverkapcsolat nem.</p>}
    <div className="mower-param-validation" aria-live="polite">
      <strong>{editor.clientErrors.length || editor.report?.errors.length ? "Hibás értékek" : editor.report?.valid ? "Formátum szerint teljes és valid — nem minősített / nem alkalmazott" : editor.report ? `Hiányos draft · ${editor.report.missing.length} hiányzó érték` : "Ellenőrzésre vár"}</strong>
      {editor.report && <><span>Draft SHA256: <code>{editor.report.draft_sha256 || "Nincs valid draft-hash"}</code></span>
        <span>RCP1 adat-CRC32: <code>{editor.report.rcp1_crc32 || "Csak teljes, valid adatnál számolható"}</code></span></>}
      <small>Az RCP1 adat-CRC nem firmware profile_crc. A HC draftverzió nem a rover aktív paraméterrevisionje.</small>
      <small>Aktív roverkonfiguráció: nincs visszaolvasott adat; összehasonlítás jelenleg nem elérhető.</small>
    </div>
    {editor.schema && editor.form && <div className="mower-param-groups">{PARAMETER_GROUPS.map((group) => <details key={group.title} open={group.title === "Azonosítás"}>
      <summary>{group.title}</summary><div className="mower-param-fields">{group.fields.map(field)}</div></details>)}</div>}
    {editor.changes.length > 0 && <details className="mower-param-history"><summary>Eltérések a betöltött HC r{editor.revision} drafthoz · {editor.changes.length} mező</summary>
      <table className="mower-param-diff"><thead><tr><th>Mező</th><th>Betöltött HC-adat</th><th>Helyi szerkesztés</th></tr></thead><tbody>
        {editor.changes.map((change) => <tr key={change.field}><td>{FIELD_LABELS[change.field] || change.field}</td>
          <td>{change.before === null ? "Ismeretlen" : JSON.stringify(change.before)}</td><td>{change.after === null ? "Ismeretlen" : JSON.stringify(change.after)}</td></tr>)}
      </tbody></table></details>}
    {editor.history.length > 0 && <details className="mower-param-history"><summary><History size={16} />Mentett HC-előzmények (utolsó 20)</summary>
      {editor.history.map((row) => <div key={row.draft_revision}><span>HC r{row.draft_revision} · {new Date(row.saved_at).toLocaleString("hu-HU")} · {row.validation.valid ? "Teljes draft" : "Hiányos draft"}</span>
        <IconButton icon={History} disabled={editor.busy || !!editor.pending} onClick={() => editor.useHistory(row)}>Adatok szerkesztésbe</IconButton>
        <a href={`/api/mower/v3/parameters/drafts/${editor.key}/revisions/${row.draft_revision}/export.json`}>JSON</a></div>)}</details>}
  </article>;
}
