import { useEffect, useRef, useState } from "react";
import { fileProblem, preflightBody, validReport } from "./mowerFirmwareModel.mjs";

const ROOT = "/api/mower/v3/firmware";

export default function useMowerFirmware() {
  const [image, setImage] = useState(null), [elf, setElf] = useState(null), [releaseId, setReleaseId] = useState("");
  const [releases, setReleases] = useState([]), [catalogError, setCatalogError] = useState("");
  const [report, setReport] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const flight = useRef(null), mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    let timedOut = false;
    const controller = new AbortController(), timer = window.setTimeout(() => { timedOut = true; controller.abort(); }, 8000);
    fetch(`${ROOT}/releases`, { cache: "no-store", signal: controller.signal }).then(async (response) => {
      const result = await response.json();
      if (!response.ok || result.ok !== true || !Array.isArray(result.releases) || result.upload_available !== false) throw new Error();
      if (mounted.current && !controller.signal.aborted) setReleases(result.releases);
    }).catch(() => { if (mounted.current && (!controller.signal.aborted || timedOut)) setCatalogError("A szerveroldali kiadási lista nem tölthető be."); })
      .finally(() => window.clearTimeout(timer));
    return () => { mounted.current = false; controller.abort(); flight.current?.abort(); };
  }, []);

  function choose(kind, next) {
    if (flight.current) return;
    setReport(null); setError("");
    if (kind === "image") setImage(next); else if (kind === "elf") setElf(next); else setReleaseId(next);
  }

  async function inspect() {
    if (flight.current) return;
    const problem = fileProblem(image, elf);
    if (problem) { setError(problem); return; }
    const controller = new AbortController(); flight.current = controller; setBusy(true); setReport(null); setError("");
    const timer = window.setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(`${ROOT}/preflight`, { method: "POST", cache: "no-store", signal: controller.signal,
        headers: { "Content-Type": "application/octet-stream", ...(releaseId ? { "X-HC-Release": releaseId } : {}) }, body: preflightBody(image, elf) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "A HC előellenőrzés elutasította a fájlpárt.");
      if (!validReport(result, releaseId) || result.metadata.image_bytes !== image.size) throw new Error("Nem egyeztethető előellenőrzési válasz; nincs igazolt eredmény.");
      if (mounted.current && !controller.signal.aborted) setReport(result);
    } catch (problem) {
      if (mounted.current) setError(controller.signal.aborted ? "Az előellenőrzés nem fejeződött be igazoltan. Nem történt roverfeltöltés." : problem.message);
    } finally {
      window.clearTimeout(timer);
      if (flight.current === controller) flight.current = null;
      if (mounted.current) setBusy(false);
    }
  }
  return { image, elf, releaseId, releases, catalogError, report, error, busy, choose, inspect, problem: fileProblem(image, elf) };
}
