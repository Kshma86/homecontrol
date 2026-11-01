import React, { useEffect, useMemo, useState } from "react";
import { RefreshCw, RotateCcw, Search, SlidersHorizontal } from "lucide-react";
import { api } from "../../apiClient";
import { IconButton } from "../../uiPrimitives";

function displayValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function Parameters() {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [page, setPage] = useState(1);
  const [containers, setContainers] = useState([]);
  const [containerMessage, setContainerMessage] = useState("");
  const [restarting, setRestarting] = useState("");
  const pageSize = 150;

  async function load() {
    setLoading(true);
    setError("");
    try {
      setPayload(await api("/api/admin/parameters"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadContainers() {
    try {
      const data = await api("/api/admin/containers");
      setContainers(data.containers || []);
    } catch (err) {
      setContainerMessage(err.message);
    }
  }

  async function restartContainer(container) {
    if (!window.confirm(`Restart ${container.name}?`)) return;
    setRestarting(container.key);
    setContainerMessage(`${container.name}: restart in progress…`);
    try {
      await api(`/api/admin/containers/${encodeURIComponent(container.key)}/restart`, { method: "POST" });
      setContainerMessage(`${container.name}: restart requested`);
      window.setTimeout(loadContainers, 2500);
    } catch (err) {
      setContainerMessage(`${container.name}: ${err.message}`);
    } finally {
      setRestarting("");
    }
  }

  useEffect(() => {
    load();
    loadContainers();
  }, []);

  const items = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("hu");
    return (payload?.items || []).filter((item) => {
      if (category !== "all" && item.category !== category) return false;
      if (!needle) return true;
      return [item.name, item.key, item.source, item.description, displayValue(item.value)]
        .some((value) => String(value || "").toLocaleLowerCase("hu").includes(needle));
    });
  }, [payload, query, category]);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const visibleItems = items.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    setPage(1);
  }, [query, category]);

  return (
    <section className="parameters-page">
      <div className="stats-head">
        <div>
          <span className="eyebrow">Read-only inventory</span>
          <h2>HomeControl Parameters</h2>
          <p>A máshol nem szerkeszthető rendszer-, polling-, cache-, timeout- és frissítési paraméterek katalógusa.</p>
        </div>
        <IconButton icon={RefreshCw} className="secondary" onClick={load} disabled={loading}>Refresh</IconButton>
      </div>

      <div className="parameter-summary-grid">
        <article className="card"><SlidersHorizontal size={18} /><strong>{payload?.summary?.parameters || 0}</strong><span>parameter</span></article>
        <article className="card"><strong>{payload?.summary?.categories || 0}</strong><span>category</span></article>
        <article className="card"><strong>{payload?.summary?.sources || 0}</strong><span>source</span></article>
        <article className="card"><strong>Read only</strong><span>no value can be changed here</span></article>
      </div>

      <section className="panel container-restart-panel">
        <div className="panel-head">
          <h2>Container restart</h2>
          <span>{containerMessage || "A restart briefly interrupts the selected service."}</span>
        </div>
        <div className="container-restart-row">
          {containers.map((container) => (
            <button
              className={container.state === "running" ? "secondary container-restart-button" : "container-restart-button warn"}
              type="button"
              disabled={Boolean(restarting) || container.state === "not found"}
              onClick={() => restartContainer(container)}
              title={`${container.name} · ${container.status || container.state}`}
              key={container.key}
            >
              <RotateCcw size={14} aria-hidden="true" />
              <span>{container.key}</span>
              <i className={container.state === "running" ? "online" : "offline"} />
            </button>
          ))}
        </div>
      </section>

      <section className="panel parameter-catalog-panel">
        <div className="parameter-toolbar">
          <label className="parameter-search">
            <Search size={17} aria-hidden="true" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, key, value or description…" />
          </label>
          <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Parameter category">
            <option value="all">All categories</option>
            {(payload?.categories || []).map((item) => <option value={item} key={item}>{item}</option>)}
          </select>
          <span>{items.length} result · page {page}/{pageCount}</span>
        </div>

        {error && <div className="error">{error}</div>}
        {loading && <div className="loading">Loading parameters…</div>}
        {!loading && !error && (
          <div className="table-wrap parameter-table-wrap">
            <table>
              <thead><tr><th>Parameter</th><th>Current value</th><th>Source</th><th>Description</th></tr></thead>
              <tbody>
                {visibleItems.map((item) => (
                  <tr key={item.key}>
                    <td><strong>{item.name}</strong><code>{item.key}</code><small>{item.category} · {item.value_type}</small></td>
                    <td><code className="parameter-value">{displayValue(item.value)}</code></td>
                    <td>{item.source}</td>
                    <td>{item.description}</td>
                  </tr>
                ))}
                {!items.length && <tr><td colSpan="4">No matching parameter.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !error && pageCount > 1 && (
          <div className="parameter-pagination">
            <button className="secondary" type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</button>
            <span>{page}/{pageCount}</span>
            <button className="secondary" type="button" disabled={page >= pageCount} onClick={() => setPage((current) => current + 1)}>Next</button>
          </div>
        )}
      </section>
    </section>
  );
}
