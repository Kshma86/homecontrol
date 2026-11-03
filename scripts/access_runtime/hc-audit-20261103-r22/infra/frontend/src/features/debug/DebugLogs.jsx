import { useEffect, useState } from "react";
import { Activity, Bug, RefreshCw } from "lucide-react";
import { IconButton } from "../../uiPrimitives";
import { numberText } from "../../formatters";
import { fetchDebugLog, fetchDebugLogSources } from "./debugApi";

export default function DebugLogs({ setToast }) {
  const [sources, setSources] = useState([]);
  const [openKey, setOpenKey] = useState("");
  const [logs, setLogs] = useState({});
  const [tail, setTail] = useState(300);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  async function loadSources() {
    setLoading(true);
    try {
      const data = await fetchDebugLogSources();
      setSources(data.logs || []);
      setOpenKey((current) => current || data.logs?.[0]?.id || "");
    } catch (err) {
      setToast(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadLog(source, force = false) {
    if (!source?.id) return;
    const key = source.id;
    if (!force && logs[key]?.tail === tail) return;
    setBusy(key);
    try {
      const data = await fetchDebugLog(key, tail);
      setLogs((current) => ({ ...current, [key]: data }));
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function toggleSource(source) {
    const key = source.id;
    const nextOpen = openKey === key ? "" : key;
    setOpenKey(nextOpen);
    if (nextOpen) loadLog(source);
  }

  useEffect(() => {
    loadSources();
  }, []);

  useEffect(() => {
    const source = sources.find((item) => item.id === openKey);
    if (source) loadLog(source, true);
  }, [tail]);

  const openSource = sources.find((item) => item.id === openKey);
  const openLog = openKey ? logs[openKey] : null;

  if (loading && !sources.length) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading debug logs...</span>
      </section>
    );
  }

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>DEBUG</h2>
          <span>{numberText(sources.length, 0)} log sources | tail {tail}</span>
        </div>
        <div className="debug-actions">
          <select value={tail} onChange={(event) => setTail(Number(event.target.value))} aria-label="Log tail">
            {[100, 300, 800, 1500].map((value) => <option value={value} key={value}>{value} lines</option>)}
          </select>
          <IconButton icon={RefreshCw} className="secondary" disabled={loading} onClick={loadSources}>{loading ? "Refreshing" : "Refresh"}</IconButton>
          <IconButton icon={RefreshCw} disabled={!openSource || Boolean(busy)} onClick={() => loadLog(openSource, true)}>{busy ? "Loading" : "Reload log"}</IconButton>
        </div>
      </section>

      <section className="debug-log-layout">
        <aside className="panel debug-log-list">
          <div className="panel-head">
            <h2>Logs</h2>
            <span>{sources.filter((item) => item.state === "running").length} running</span>
          </div>
          <div className="debug-log-links">
            {sources.map((source) => (
              <button className={openKey === source.id ? "active" : ""} type="button" onClick={() => toggleSource(source)} key={source.id || source.name}>
                <Bug size={15} aria-hidden="true" />
                <span>{source.service || source.name}</span>
                <small>{source.name} | {source.state || "-"}</small>
              </button>
            ))}
          </div>
        </aside>

        <article className="panel debug-log-detail">
          <div className="panel-head">
            <h2>{openSource?.service || openSource?.name || "Select log"}</h2>
            <span>{openLog?.line_count ?? 0} lines | {openSource?.status || "-"}</span>
          </div>
          {openLog?.ok === false ? (
            <div className="debug-log-empty">{openLog.error || "Log unavailable"}</div>
          ) : openSource ? (
            <pre className="debug-log-output">{openLog?.text || (busy ? "Loading log..." : "No log lines")}</pre>
          ) : (
            <div className="debug-log-empty">Select a log source</div>
          )}
        </article>
      </section>
    </>
  );
}
