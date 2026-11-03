import { useEffect, useRef, useState } from "react";
import { readJsonResponse } from "../../apiClient";

export default function useMowerV3Snapshot() {
  const [snapshot, setSnapshot] = useState(null);
  const [receivedAt, setReceivedAt] = useState(null);
  const [now, setNow] = useState(() => performance.now());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const refreshRef = useRef(() => {});

  useEffect(() => {
    let alive = true, pending = false, hasSnapshot = false;
    let controller = null, poll = null;
    async function refresh(explicit = false) {
      if (!alive || pending || document.visibilityState !== "visible") return;
      window.clearTimeout(poll);
      pending = true;
      if (explicit) setLoading(true);
      controller = new AbortController();
      const deadline = window.setTimeout(() => controller.abort(), 5000);
      const started = performance.now();
      let delay = 5000;
      try {
        const response = await fetch("/api/mower/v3/snapshot", {
          cache: "no-store", signal: controller.signal,
        });
        const payload = await readJsonResponse(response);
        if (!response.ok || payload.ok !== true) throw new Error("A HC roverállapot-szolgáltatása nem érhető el.");
        if (!alive) return;
        const status = payload.connection?.status;
        delay = status === "LIVE" ? 500 : status === "BUSY" ? 200 : status === "STALE" ? 1000 : 5000;
        // Contention is not new STM evidence. Preserve the last sample with its
        // original receipt time: the local 1500 ms deadline still closes controls.
        if (status === "BUSY" && hasSnapshot) return;
        const at = performance.now(), age = payload.freshness?.effective_age_ms;
        const timing = /(?:^|,)\s*rover;dur=([0-9]+(?:\.[0-9]+)?)/.exec(response.headers.get("Server-Timing") || "");
        const duration = at - started, serverMs = timing ? Number(timing[1]) : 0;
        const transit = Math.max(0, duration - Math.min(duration, serverMs));
        setSnapshot({ ...payload, freshness: { ...payload.freshness,
          effective_age_ms: Number.isInteger(age) ? age + Math.ceil(transit) : null,
        } });
        hasSnapshot = status !== "BUSY";
        setReceivedAt(at);
        setNow(at);
        setError("");
      } catch (failure) {
        if (alive) setError(failure.name === "AbortError" ? "A roverállapot lekérése túllépte az időkorlátot." : failure.message);
      } finally {
        window.clearTimeout(deadline);
        pending = false;
        if (alive) {
          setLoading(false);
          // Schedule after completion; slow/offline requests never pile up.
          if (document.visibilityState === "visible") poll = window.setTimeout(() => refresh(), delay);
        }
      }
    }
    refreshRef.current = () => refresh(true);
    const visibility = () => {
      if (document.visibilityState === "visible") void refresh();
      else window.clearTimeout(poll);
    };
    void refresh();
    const ageTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") setNow(performance.now());
    }, 250);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      alive = false;
      controller?.abort();
      window.clearTimeout(poll);
      window.clearInterval(ageTimer);
      document.removeEventListener("visibilitychange", visibility);
      refreshRef.current = () => {};
    };
  }, []);

  return { snapshot, receivedAt, now, loading, error, refresh: () => refreshRef.current() };
}
