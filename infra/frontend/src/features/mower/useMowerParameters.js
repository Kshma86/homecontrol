import { useEffect, useMemo, useRef, useState } from "react";
import { canonicalDraftText, formToParameters, parameterChanges, parametersToForm, savedDraftMatches, usableCachedForm } from "./mowerParametersModel.mjs";
import { newRequestId } from "./mowerV3Controls.mjs";

const ROOT = "/api/mower/v3/parameters", CACHE = "hc-mower-parameter-editor-v1";
function cachedEditor() {
  try { const raw = sessionStorage.getItem(CACHE) || "null"; return raw.length <= 65536 ? JSON.parse(raw) : null; } catch { return null; }
}
async function jsonRequest(path, options = {}) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${ROOT}${path}`, { cache: "no-store", ...options, signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) throw Object.assign(new Error(payload.error || "A HC paraméterszolgáltatás elutasította a kérést."), { code: payload.code, status: response.status, payload });
    return payload;
  } finally { window.clearTimeout(timer); }
}

export default function useMowerParameters(authenticated) {
  const cachedRef = useRef(cachedEditor());
  const [schema, setSchema] = useState(null), [form, setForm] = useState(null);
  const [keyInput, setKeyInput] = useState(""), [key, setKey] = useState("");
  const [base, setBase] = useState(null), [revision, setRevision] = useState(0);
  const [drafts, setDrafts] = useState([]), [history, setHistory] = useState([]);
  const [report, setReport] = useState(null), [status, setStatus] = useState({ message: "A HC szerkesztő betöltése…" });
  const [busy, setBusy] = useState(false), [pending, setPending] = useState(null);
  const flightRef = useRef(false), mountedRef = useRef(true);
  const parsed = useMemo(() => schema && form ? formToParameters(form, schema) : null, [schema, form]);
  const text = parsed ? canonicalDraftText(parsed.parameters) : "";
  const dirty = !!(form && schema && (!base || canonicalDraftText(form) !== canonicalDraftText(parametersToForm(base, schema))));
  const currentReport = report?.text === text && parsed?.errors.length === 0 ? report.validation : null;

  async function refreshDrafts() {
    try { const result = await jsonRequest("/drafts"); if (mountedRef.current) setDrafts(result.drafts); }
    catch { /* Editor/validation still works if PostgreSQL is temporarily unavailable. */ }
  }
  async function refreshHistory(target = key) {
    if (!target) return;
    try { const result = await jsonRequest(`/drafts/${target}/history`); if (mountedRef.current) setHistory(result.revisions); }
    catch { if (mountedRef.current) setHistory([]); }
  }
  useEffect(() => {
    mountedRef.current = true;
    jsonRequest("/schema").then((result) => {
      if (!mountedRef.current) return;
      setSchema(result.schema);
      const cached = cachedRef.current;
      const usable = usableCachedForm(cached, result.schema);
      setForm(usable ? cached.form : parametersToForm(result.template, result.schema));
      setBase(usable ? cached.base : result.template);
      if (usable) {
        setKey(cached.key); setKeyInput(cached.key); setRevision(cached.revision);
        setPending(cached.pending || null);
        if (cached.key) refreshHistory(cached.key);
      }
      setStatus({ message: usable ? "A böngésző helyi szerkesztését visszaállítottam. Ez nem igazol új adatbázis- vagy rovermentést." : "Üres RCP1 draft. A hiányzó értékek ismeretlenek, nem működési alapértékek." });
      refreshDrafts();
    }).catch(() => { if (mountedRef.current) setStatus({ error: true, message: "A paraméterséma nem tölthető be. Frissítsd az oldalt." }); });
    return () => { mountedRef.current = false; };
  }, []);
  useEffect(() => {
    if (!form || !base) return;
    try { sessionStorage.setItem(CACHE, JSON.stringify({ key, revision, base, form, pending })); } catch { /* Storage may be denied. */ }
  }, [key, revision, base, form, pending]);
  useEffect(() => {
    if (!parsed || parsed.errors.length) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const result = await jsonRequest("/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: text });
        if (active && mountedRef.current) setReport({ text, validation: result.validation });
      } catch { if (active && mountedRef.current) setReport(null); }
    }, 350);
    return () => { active = false; window.clearTimeout(timer); };
  }, [text, parsed?.errors.length]);
  function edit(name, value, index = null) {
    if (flightRef.current) return;
    setForm((previous) => ({ ...previous, [name]: index === null ? value : previous[name].map((item, at) => at === index ? value : item) }));
  }
  async function load() {
    if (flightRef.current || pending || !/^[A-Za-z0-9_-]{1,32}$/.test(keyInput)) return;
    if (dirty && !window.confirm("A nem mentett helyi módosításokat lecseréled a kiválasztott HC draftra?")) return;
    flightRef.current = true; setBusy(true);
    try {
      const result = await jsonRequest(`/drafts/${keyInput}`);
      if (!mountedRef.current) return;
      if (result.parameters?.parameters_version !== 1) throw new Error("Az RCP2 draft a MOTOR_TEST nézetben szerkeszthető.");
      setKey(result.rover_key); setRevision(result.draft_revision); setBase(result.parameters);
      setForm(parametersToForm(result.parameters, schema));
      setStatus({ message: result.draft_revision ? `HC draft betöltve: ${result.draft_revision}. verzió. Nem aktív roverkonfiguráció.` : "Új HC rover-draft, még nincs adatbázisba mentve." });
      refreshHistory(result.rover_key);
    } catch (error) { if (mountedRef.current) setStatus({ error: true, message: error.status ? error.message : "A HC draft nem tölthető be; a helyi módosítások megmaradtak." }); }
    finally { flightRef.current = false; if (mountedRef.current) setBusy(false); }
  }
  function acceptSaved(result, attempt) {
    if (!savedDraftMatches(result, attempt)) throw new Error("Uncorrelated HC save");
    if (!mountedRef.current) return;
    setBase(result.parameters); setRevision(result.draft_revision); setPending(null);
    setStatus({ message: `HC-adatbázisba mentve: ${result.draft_revision}. draftverzió. A roveren nem alkalmaztuk.` });
    refreshDrafts(); refreshHistory(attempt.key);
  }
  async function save() {
    if (flightRef.current || pending || !authenticated || !key || keyInput !== key || !currentReport?.saveable || parsed.errors.length) return;
    const attempt = { request_id: newRequestId(), key, expected_revision: revision, parameters: parsed.parameters };
    // Persist correlation *before* sending; recovery only performs GET.
    try { sessionStorage.setItem(CACHE, JSON.stringify({ key, revision, base, form, pending: attempt })); } catch { /* Non-durable browser fallback, still never auto-retry. */ }
    setPending(attempt); flightRef.current = true; setBusy(true);
    try {
      const result = await jsonRequest(`/drafts/${key}`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: attempt.request_id, expected_revision: attempt.expected_revision, parameters: attempt.parameters }) });
      acceptSaved(result, attempt);
    } catch (error) {
      if (!mountedRef.current) return;
      if (error.status && error.status < 500) {
        setPending(null);
        setStatus({ error: true, message: error.code === "REVISION_CONFLICT" ? `Verzióütközés: a HC-ban már ${error.payload.current_revision}. verzió van. A szerkesztésed megmaradt; nincs automatikus felülírás.` : error.message });
      } else setStatus({ error: true, message: "UNKNOWN: a mentés eredménye nem igazolt. Egyeztetés csak visszaolvasással; nincs automatikus újraküldés." });
    } finally { flightRef.current = false; if (mountedRef.current) setBusy(false); }
  }
  async function reconcile() {
    if (!pending || flightRef.current) return;
    const attempt = pending;
    flightRef.current = true; setBusy(true);
    try { acceptSaved(await jsonRequest(`/drafts/${attempt.key}/requests/${attempt.request_id}`), attempt); }
    catch { if (mountedRef.current) setStatus({ error: true, message: "UNKNOWN: a mentés nem olvasható vissza igazoltan. A draft és a mentésazonosító megmaradt." }); }
    finally { flightRef.current = false; if (mountedRef.current) setBusy(false); }
  }
  async function importFile(file) {
    if (!file || !schema || flightRef.current) return;
    if (file.size > 16384) { setStatus({ error: true, message: "Az import legfeljebb 16 KiB lehet." }); return; }
    if (dirty && !window.confirm("Az import lecseréli a helyi szerkesztést. Folytatod?")) return;
    const binary = file.name.toLowerCase().endsWith(".rcp1");
    flightRef.current = true; setBusy(true);
    try {
      const result = await jsonRequest("/import", { method: "POST", headers: { "Content-Type": binary ? "application/octet-stream" : "application/json" },
        body: binary ? await file.arrayBuffer() : await file.text() });
      if (!mountedRef.current) return;
      if (result.parameters?.parameters_version !== 1) throw new Error("RCP2 importhoz használd a MOTOR_TEST nézetet.");
      setForm(parametersToForm(result.parameters, schema));
      setStatus({ message: "Import a helyi draftba kész. Nem mentettük adatbázisba, és nem alkalmaztuk a roveren." });
    } catch (error) { if (mountedRef.current) setStatus({ error: true, message: error.status ? error.message : "Az import nem ellenőrizhető; a korábbi szerkesztés megmaradt." }); }
    finally { flightRef.current = false; if (mountedRef.current) setBusy(false); }
  }
  function exportJson() {
    if (!parsed || parsed.errors.length) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(parsed.parameters, null, 2) + "\n"], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `${key || "unassigned"}-hc-draft.json`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function useHistory(row) {
    if (busy || pending || dirty && !window.confirm("A helyi szerkesztést lecseréled a kiválasztott korábbi draftverzió adataira?")) return;
    if (row.parameters?.parameters_version !== 1) { setStatus({ error: true, message: "RCP2 draftot a MOTOR_TEST nézetben szerkeszthetsz." }); return; }
    setForm(parametersToForm(row.parameters, schema));
    setStatus({ message: `${row.draft_revision}. draftverzió adatait szerkeszted. Mentéskor új HC-verzió készül, az előzmények megmaradnak.` });
  }
  return { schema, form, key, keyInput, setKeyInput, revision, drafts, history, report: currentReport,
    clientErrors: parsed?.errors || [], changes: parsed && !parsed.errors.length ? parameterChanges(base, parsed.parameters) : [], dirty, status, busy, pending, edit, load, save, reconcile, importFile, exportJson, useHistory,
    canSave: authenticated && !!key && keyInput === key && !busy && !pending && (dirty || revision === 0) && currentReport?.saveable === true,
    rcp1Export: key && revision && !dirty && currentReport?.valid ? `${ROOT}/drafts/${key}/revisions/${revision}/export.rcp1` : null };
}
