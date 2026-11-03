import { useEffect, useRef, useState } from "react";
import { readJsonResponse } from "../../apiClient";
import { commandPayload, newRequestId, TERMINAL_RESULTS, validCommandResult } from "./mowerV3Controls.mjs";

export default function useMowerCommands({ identity, state, authenticated, refresh, maintenanceBlocked = false, resetKey = null }) {
  const [records, setRecords] = useState([]);
  const [busy, setBusy] = useState(false);
  const recordsRef = useRef(records);
  const activeRef = useRef(0);
  const aliveRef = useRef(true);
  useEffect(() => { aliveRef.current = true; return () => { aliveRef.current = false; }; }, []);
  useEffect(() => { try { sessionStorage.removeItem("hc-mower-v3-requests"); } catch {} }, []);
  useEffect(() => {
    if (!identity?.stm_boot) return;
    setRecords((previous) => previous.filter((record) => record.stm_boot === identity.stm_boot && record.result !== "UNKNOWN"));
  }, [identity?.stm_boot, identity?.esp_boot]);
  useEffect(() => { if (resetKey) { recordsRef.current = []; setRecords([]); } }, [resetKey]);
  useEffect(() => {
    recordsRef.current = records;

  }, [records]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (recordsRef.current.some((record) => record.result === "UNKNOWN" && Date.now() - record.sent_at > 10000)) setRecords((previous) => previous.filter((record) => record.result !== "UNKNOWN" || Date.now() - record.sent_at <= 10000));
      if (!recordsRef.current.some((record) => record.result === "PENDING" && Date.now() - record.sent_at > 1500)) return;
      setRecords((previous) => previous.map((record) => record.result === "PENDING" && Date.now() - record.sent_at > 1500
        ? { ...record, result: "UNKNOWN", code: "TIMEOUT" } : record));
    }, 100);
    return () => window.clearInterval(timer);
  }, []);
  function update(id, payload) {
    if (!aliveRef.current) return;
    setRecords((previous) => previous.map((record) => record.request_id === id
      ? { ...record, ...payload, ...(payload.result === "PENDING" && Date.now() - record.sent_at > 1500 ? { result: "UNKNOWN", code: "TIMEOUT" } : {}) } : record));
  }
  async function reconcile(id) {
    try {
      const response = await fetch(`/api/mower/v3/command/${id}`, { cache: "no-store" });
      const payload = await readJsonResponse(response);
      const record = recordsRef.current.find((item) => item.request_id === id);
      if (!response.ok || !record || !validCommandResult(payload, record)) throw new Error();
      update(id, payload);
      refresh();
    } catch { update(id, { result: "UNKNOWN", code: "LINK_LOST" }); }
  }
  useEffect(() => {
    if (!authenticated || maintenanceBlocked) return undefined;
    let pending = false;
    const timer = window.setInterval(async () => {
      if (pending) return;
      const unresolved = recordsRef.current.filter((record) => !TERMINAL_RESULTS.has(record.result) && Date.now() - record.sent_at < 10000);
      if (!unresolved.length) return;
      pending = true;
      try {
        for (const record of unresolved) {
          if (Date.now() - record.sent_at > 1500) update(record.request_id, { result: "UNKNOWN", code: "TIMEOUT" });
          await reconcile(record.request_id);
        }
      } finally { pending = false; }
    }, 500);
    return () => window.clearInterval(timer);
  }, [authenticated, maintenanceBlocked]);
  async function submit(command, value = null) {
    if (!authenticated || (activeRef.current || maintenanceBlocked) && command !== "stop") return;
    const id = newRequestId();
    let payload;
    try { payload = commandPayload(command, value, identity, state, id); }
    catch { return; }
    const record = { request_id: id, command, stm_boot: command === "stop" ? null : identity.stm_boot, result: "PENDING", code: "PENDING", sent_at: Date.now() };
    setRecords((previous) => [record, ...previous].slice(0, 16));
    activeRef.current += 1; setBusy(true);
    try {
      const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 5000);
      let response;
      try { response = await fetch(`/api/mower/v3/${command === "stop" ? "stop" : "command"}`, {
        method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      }); } finally { window.clearTimeout(timeout); }
      const result = await readJsonResponse(response);
      if (!response.ok) update(id, { result: response.status < 500 || ["UNCONFIGURED", "AUTH_UNCONFIGURED"].includes(result.code) ? "REJECTED" : "UNKNOWN", code: result.code || `HTTP_${response.status}` });
      else if (!validCommandResult(result, record)) update(id, { result: "UNKNOWN", code: "INVALID_RESPONSE" });
      else update(id, result);
    } catch { update(id, { result: "UNKNOWN", code: "REPLY_LOST" }); }
    finally { activeRef.current -= 1; if (aliveRef.current) setBusy(activeRef.current > 0); refresh(); }
  }
  return { records, busy, submit, reconcile,
    unresolved: false };
}
