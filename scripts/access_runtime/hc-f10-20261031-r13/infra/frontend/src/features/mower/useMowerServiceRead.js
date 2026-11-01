import { useEffect, useRef, useState } from "react";
import { readJsonResponse } from "../../apiClient";

export default function useMowerServiceRead({ endpoint = "/api/mower/v3/service/snapshot", timeoutMs = 7000 } = {}) {
  const [snapshot, setSnapshot] = useState(null);
  const [receivedAt, setReceivedAt] = useState(null);
  const [now, setNow] = useState(() => performance.now());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const refreshRef = useRef(() => {});
  useEffect(() => {
    let alive = true, pending = false, controller = null;
    async function refresh() {
      if (!alive || pending || document.visibilityState !== "visible") return;
      pending = true;
      controller = new AbortController();
      const started = performance.now();
      const timeout = window.setTimeout(() => controller?.abort(), timeoutMs);
      try {
        const response = await fetch(endpoint, { cache: "no-store", signal: controller.signal });
        const payload = await readJsonResponse(response);
        if (!response.ok || payload.ok !== true || payload.read_only !== true) throw new Error("A HC szervizállapot nem olvasható.");
        if (!alive) return;
        const at = performance.now(), age = payload.freshness?.effective_age_ms;
        setSnapshot({ ...payload, freshness: { ...payload.freshness,
          effective_age_ms: Number.isInteger(age) ? age + Math.ceil(at - started) : null },
          health_freshness: { ...payload.health_freshness, effective_age_ms: Number.isInteger(payload.health_freshness?.effective_age_ms)
            ? payload.health_freshness.effective_age_ms + Math.ceil(at - started) : null } });
        setReceivedAt(at); setNow(at); setError("");
      } catch (failure) {
        if (alive) setError(failure.name === "AbortError" ? "A HC szervizlekérdezés időtúllépett." : "A HC szervizállapot nem érhető el.");
      } finally {
        window.clearTimeout(timeout); pending = false;
        if (alive) setLoading(false);
      }
    }
    refreshRef.current = refresh;
    refresh();
    const poll = window.setInterval(refresh, 1000);
    const ageTimer = window.setInterval(() => setNow(performance.now()), 250);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      alive = false; controller?.abort(); window.clearInterval(poll); window.clearInterval(ageTimer);
      document.removeEventListener("visibilitychange", refresh); refreshRef.current = () => {};
    };
  }, [endpoint, timeoutMs]);
  return { snapshot, receivedAt, now, loading, error, refresh: () => refreshRef.current() };
}
