import { useEffect, useRef, useState } from "react";
import { stageRequestId } from "./mowerFirmwareModel.mjs";
import { validSessionIntent, validUpdateSession, updateView, validActionIntent, validActionResult } from "./mowerUpdateModel.mjs";

const ROOT = "/api/mower/v3/firmware", KEY = "hc.mower.v3.update.pending-create.v1";
const ACTION_KEY = "hc.mower.v3.update.pending-action.v1";

export default function useMowerUpdateSession({ authenticated, configured }) {
  const [result, setResult] = useState(null), [receivedAt, setReceivedAt] = useState(null), [now, setNow] = useState(0);
  const [pending, setPending] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [last, setLast] = useState(null);
  const [actionPending, setActionPending] = useState(null), [lastAction, setLastAction] = useState(null), [exitRevision, setExitRevision] = useState(null);
  const actionIntentRef = useRef(null), mutation = useRef(null);
  const mounted = useRef(false), flight = useRef(null), intentRef = useRef(null), current = useRef({ authenticated, configured });
  current.current = { authenticated, configured };
  function remember(intent) { intentRef.current = intent; setPending(intent); }
  function clearIntent() { window.sessionStorage.removeItem(KEY); remember(null); }
  async function request(path, options = {}) {
    const slot = options.method === "POST" ? mutation : flight;
    const controller = new AbortController(); slot.current = controller; setBusy(true);
    const timer = window.setTimeout(() => controller.abort(), options.method === "POST" ? 15000 : 8000);
    try {
      const response = await fetch(`${ROOT}${path}`, { ...options, cache: "no-store", signal: controller.signal });
      const data = await response.json();
      if (controller.signal.aborted || !mounted.current) throw new Error("A session-kérés nem fejeződött be igazoltan.");
      return { response, data };
    } finally {
      window.clearTimeout(timer); if (slot.current === controller) slot.current = null;
      if (mounted.current) setBusy(!!(flight.current || mutation.current));
    }
  }
  function acceptAction(data, intent) {
    if (!validActionResult(data, intent)) throw new Error("Nem egyeztethető frissítési műveletválasz; nincs újraküldés.");
    if (!data.found) throw new Error("A művelet eredménye ISMERETLEN. Negatív GET nem engedélyez újraküldést.");
    window.sessionStorage.removeItem(ACTION_KEY); actionIntentRef.current = null; setActionPending(null);
    setLastAction(data);
    if (data.exit) setExitRevision(data.exit.request_id);
  }
  function accept(data, intent = null) {
    if (!validUpdateSession(data, intent)) throw new Error("Nem egyeztethető natív session-válasz; nincs igazolt eredmény.");
    if (intent && data.attempt && data.attempt.request_id === intent.requestId) clearIntent();
    if (data.observation) setLast({ observation: data.observation, age: data.freshness.effective_age_ms, at: performance.now() });
    setResult(data); setReceivedAt(performance.now()); setNow(performance.now()); setError("");
  }
  async function refresh() {
    if (!current.current.authenticated || flight.current) return;
    const intent = intentRef.current;
    if (intent && !validSessionIntent(intent)) return;
    try {
      const actionIntent = actionIntentRef.current;
      if (actionIntent) {
        if (!validActionIntent(actionIntent)) return;
        const { response, data } = await request(`/operations/requests/${encodeURIComponent(actionIntent.requestId)}`);
        if (!response.ok) throw new Error(data.error || "A művelet nem egyeztethető.");
        acceptAction(data, actionIntent);
      }
      const path = intent ? `/sessions/requests/${encodeURIComponent(intent.requestId)}` : "/session";
      const { response, data } = await request(path);
      if (!response.ok) throw new Error(data.error || "A natív session állapota nem olvasható.");
      accept(data, intent);
      if (intent && data.found === false) setError("A create eredménye ISMERETLEN. Nincs mentett korreláció; csak visszaolvasás engedélyezett.");
    } catch (problem) { if (mounted.current) setError(problem.message); }
  }
  useEffect(() => {
    mounted.current = true;
    try {
      const raw = window.sessionStorage.getItem(KEY);
      if (raw !== null) {
        const intent = raw.length <= 512 ? JSON.parse(raw) : null;
        if (!validSessionIntent(intent)) throw new Error();
        remember(intent);
      }
    } catch { remember({ invalid: true }); setError("A függő session helyi azonosítója nem olvasható. Üzemi vezérlés és új create letiltva."); }
    try {
      const raw = window.sessionStorage.getItem(ACTION_KEY);
      if (raw !== null) {
        const intent = raw.length <= 512 ? JSON.parse(raw) : null;
        if (!validActionIntent(intent)) throw new Error();
        actionIntentRef.current = intent; setActionPending(intent);
      }
    } catch { actionIntentRef.current = { invalid: true }; setActionPending({ invalid: true }); setError("A függő frissítési művelet azonosítója sérült; új művelet letiltva."); }
    const timer = window.setInterval(() => setNow(performance.now()), 250);
    return () => { mounted.current = false; flight.current?.abort(); mutation.current?.abort(); window.clearInterval(timer); };
  }, []);
  useEffect(() => {
    if (!authenticated) { flight.current?.abort(); mutation.current?.abort(); return undefined; }
    void refresh();
    if (!configured) return undefined;
    const timer = window.setInterval(() => { void refresh(); }, 500);
    return () => { window.clearInterval(timer); flight.current?.abort(); mutation.current?.abort(); };
  }, [authenticated, configured]);

  const view = updateView(result, receivedAt, now, error);
  const blocked = !!pending || !!actionPending || result?.ordinary_blocked === true || !!(authenticated && configured && (!result || error));
  async function create(jobId) {
    if (!current.current.authenticated || !current.current.configured || flight.current || mutation.current || intentRef.current || blocked
      || !updateView(result, receivedAt, performance.now(), error).canCreate) return;
    let intent;
    try {
      intent = { jobId, requestId: stageRequestId(window.crypto) };
      if (!validSessionIntent(intent)) throw new Error();
      window.sessionStorage.setItem(KEY, JSON.stringify(intent));
    } catch { setError("A create azonosítója nem őrizhető meg; nem indult natív kérés."); return; }
    remember(intent); setError("");
    try {
      const { response, data } = await request(`/jobs/${jobId}/session`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: intent.requestId, confirm_runtime_discard: true }) });
      if (!response.ok) {
        if (data.ok === false && data.mutation_sent === false && data.code !== "ID_CONFLICT") clearIntent();
        throw new Error(data.error || "A create eredménye ISMERETLEN; nincs automatikus újraküldés.");
      }
      accept(data, intent);
    } catch (problem) { if (mounted.current) setError(problem.message); }
  }
  async function perform(action) {
    const permission = { IMAGE:"canUpload", ABORT:"canAbort", FINISH:"canFinish", VERIFY_EXIT:"canVerifyExit" }[action];
    if (!current.current.authenticated || !current.current.configured || !permission || mutation.current || flight.current
      || intentRef.current || actionIntentRef.current || !updateView(result,receivedAt,performance.now(),error)[permission]) return;
    let intent;
    try {
      intent = { action, sessionId:result.attempt.request_id, requestId:stageRequestId(window.crypto) };
      if (!validActionIntent(intent)) throw new Error();
      window.sessionStorage.setItem(ACTION_KEY,JSON.stringify(intent));
    } catch { setError("A műveletazonosító nem őrizhető meg; nem indult kérés."); return; }
    actionIntentRef.current = intent; setActionPending(intent); setError("");
    try {
      const path = action.toLowerCase().replaceAll("_","-");
      const { response, data } = await request(`/sessions/requests/${encodeURIComponent(intent.sessionId)}/${path}`,
        { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({request_id:intent.requestId}) });
      if (!response.ok) {
        if (data.ok === false && data.mutation_sent === false && data.code !== "ID_CONFLICT") {
          window.sessionStorage.removeItem(ACTION_KEY); actionIntentRef.current = null; setActionPending(null);
        }
        throw new Error(data.error || "A frissítési művelet eredménye ISMERETLEN; nincs újraküldés.");
      }
      acceptAction(data,intent); await refresh();
    } catch (problem) { if (mounted.current) setError(problem.message); }
  }
  return { result, ...view, pending:pending || actionPending, blocked, busy, error, refresh, create, perform, lastAction, exitRevision, canRead: authenticated,
    lastObservation: last?.observation || null, lastAge: last && last.age !== null ? last.age + Math.max(0, now - last.at) : null };
}
