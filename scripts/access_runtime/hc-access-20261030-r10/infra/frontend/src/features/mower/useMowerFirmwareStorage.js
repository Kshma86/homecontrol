import { useEffect, useRef, useState } from "react";
import { preflightBody, validReport, validStaged, validStageIntent, stageRequestId } from "./mowerFirmwareModel.mjs";

const ROOT = "/api/mower/v3/firmware/jobs", KEY = "hc.mower.v3.firmware.pending-save.v1";

export default function useMowerFirmwareStorage(editor, authenticated) {
  const [pending, setPending] = useState(null), [saved, setSaved] = useState(null), [jobs, setJobs] = useState([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const pendingRef = useRef(null), mounted = useRef(false), flight = useRef(null), authRef = useRef(authenticated);
  authRef.current = authenticated;

  function remember(value) { pendingRef.current = value; setPending(value); }
  function clearIntent() {
    window.sessionStorage.removeItem(KEY);
    remember(null);
  }
  async function fetchResult(path, options = {}) {
    const controller = new AbortController(); flight.current = controller; setBusy(true);
    const timer = window.setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, { ...options, cache: "no-store", signal: controller.signal });
      const result = await response.json();
      if (controller.signal.aborted || !mounted.current) throw new Error("A HC-kérés nem fejeződött be igazoltan.");
      return { response, result };
    } finally {
      window.clearTimeout(timer);
      if (flight.current === controller) flight.current = null;
      if (mounted.current) setBusy(false);
    }
  }
  function accept(job, intent) {
    if (!validStaged(job, intent)) throw new Error("A HC-mentési válasz nem egyeztethető; az eredmény ISMERETLEN.");
    setSaved(job);
    setJobs((previous) => [job, ...previous.filter((row) => row.hc_job_id !== job.hc_job_id)].slice(0, 20));
    clearIntent();
  }
  async function reconcile() {
    const intent = pendingRef.current;
    if (!authRef.current || flight.current || !validStageIntent(intent)) return;
    setError("");
    try {
      const { response, result } = await fetchResult(`${ROOT}/requests/${encodeURIComponent(intent.requestId)}`);
      if (!response.ok) throw new Error(result.error || "A HC mentési állapot nem olvasható.");
      if (result.found !== true) throw new Error("Még nincs egyeztethető mentés. Az eredmény ISMERETLEN marad; nincs újraküldés.");
      accept(result, intent);
    } catch (problem) { if (mounted.current) setError(problem.message); }
  }
  async function refresh() {
    if (!authRef.current || flight.current) return;
    setError("");
    try {
      const { response, result } = await fetchResult(ROOT);
      if (!response.ok) throw new Error(result.error || "A HC firmware-előzmények nem olvashatók.");
      if (result.ok !== true || result.scope !== "HC_LOCAL_STAGING" || result.upload_available !== false || result.rover_contacted !== false
        || !Array.isArray(result.jobs) || result.jobs.length > 20 || !result.jobs.every((row) => validStaged(row))) throw new Error("Hibás HC firmware-előzmény válasz.");
      setJobs(result.jobs);
    } catch (problem) { if (mounted.current) setError(problem.message); }
  }
  useEffect(() => {
    mounted.current = true;
    try {
      const raw = window.sessionStorage.getItem(KEY);
      if (raw !== null) {
        const intent = raw.length <= 2048 ? JSON.parse(raw) : null;
        if (!validStageIntent(intent)) throw new Error();
        remember(intent);
      }
    } catch {
      remember({ invalid: true });
      setError("A függő HC-mentés helyi azonosítója nem olvasható. Új mentés letiltva; adminisztrátori egyeztetés szükséges.");
    }
    return () => { mounted.current = false; flight.current?.abort(); };
  }, []);
  useEffect(() => {
    if (authenticated) {
      if (validStageIntent(pendingRef.current)) void reconcile(); else void refresh();
    } else flight.current?.abort();
  }, [authenticated]);

  async function stage() {
    if (!authRef.current || flight.current || pendingRef.current || !editor.releaseId || !validReport(editor.report, editor.releaseId)) return;
    setError(""); setSaved(null);
    let intent;
    try {
      intent = { requestId: stageRequestId(window.crypto), releaseId: editor.releaseId,
        imageHash: editor.report.metadata.image_sha256, elfHash: editor.report.elf_sha256, imageBytes: editor.image.size };
      if (!validStageIntent(intent)) throw new Error();
      window.sessionStorage.setItem(KEY, JSON.stringify(intent));
    } catch {
      setError("A HC mentésazonosító nem őrizhető meg biztonságosan; nem indult mentés."); return;
    }
    remember(intent);
    try {
      const { response, result } = await fetchResult(ROOT, { method: "POST", headers: { "Content-Type": "application/octet-stream",
        "X-HC-Release": intent.releaseId, "X-HC-Request-ID": intent.requestId }, body: preflightBody(editor.image, editor.elf) });
      if (!response.ok) {
        // Only a recognized HC rejection before a DB write can release the intent.
        const rejected = ["ORIGIN_REJECTED", "AUTH_REQUIRED", "BAD_CONTENT_TYPE", "BAD_LENGTH", "PREFLIGHT_BUSY", "INVALID_REQUEST_ID",
          "RELEASE_REQUIRED", "RELEASE_NOT_APPROVED", "ELF_INVALID", "ELF_HASH_MISMATCH", "BAD_HEADER", "WRONG_TARGET", "WRONG_SLOT",
          "ABI_MISMATCH", "BAD_HASH", "PROFILE_MISMATCH", "STORAGE_QUOTA"];
        if ([400, 401, 403, 409, 413, 429].includes(response.status) && result.ok === false && rejected.includes(result.code)) clearIntent();
        throw new Error(result.error || "A HC-mentés eredménye ISMERETLEN; csak visszaolvasással egyeztethető.");
      }
      accept(result, intent);
    } catch (problem) { if (mounted.current) setError(problem.message); }
  }
  return { pending, saved, jobs, busy, error, stage, reconcile, refresh };
}
