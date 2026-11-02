import { useEffect, useMemo, useState } from "react";
import { BarChart3, Monitor, RefreshCw, Smartphone } from "lucide-react";
import { api } from "../../apiClient";
import { dateText } from "../../formatters";
import { Card, IconButton, Table } from "../../uiPrimitives";

const pageLabels = {
  home: "Home", "mobile-dashboard": "Mobile", "tablet-dashboard": "Tablet", irrigation: "Irrigation",
  statistics: "Irrigation Stats", solar: "Solar", x10: "X10 Robot", climate: "Climate",
  "power-wall": "Power Wall", "nyest-scheduler": "Marten Deterrent", scheduler: "Scheduler",
  "hc-stat": "House stats", ai: "AI", tuya: "Tuya", "sql-lab": "SQL LAB", performance: "Performance",
  backup: "Backup", "hc-admin": "HC Admin", parameters: "Parameters", notes: "Notes", debug: "DEBUG",
  documentation: "Docs", about: "About", "usage-statistics": "Usage Stats",
};

export default function PageUsageStatistics() {
  const [days, setDays] = useState(30);
  const [payload, setPayload] = useState({ rows: [] });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setPayload(await api(`/api/page-usage/summary?days=${days}`, { skipContextRefresh: true }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [days]);

  const rows = payload.rows || [];
  const totals = useMemo(() => ({
    views: rows.reduce((sum, row) => sum + Number(row.views || 0), 0),
    devices: Math.max(0, ...rows.map((row) => Number(row.total_devices || 0))),
    mobile: rows.filter((row) => row.device_class === "mobile").reduce((sum, row) => sum + Number(row.views || 0), 0),
    desktop: rows.filter((row) => row.device_class === "desktop").reduce((sum, row) => sum + Number(row.views || 0), 0),
  }), [rows]);

  return (
    <>
      <section className="stats-head">
        <div><h2>Page Usage Statistics</h2><span>{error || `Anonymous local usage, last ${days} days`}</span></div>
        <div className="range-switch" aria-label="Usage statistics range">
          {[7, 30, 90].map((value) => <button className={days === value ? "active" : ""} type="button" onClick={() => setDays(value)} key={value}>{value}d</button>)}
          <IconButton icon={RefreshCw} onClick={load} disabled={loading}>{loading ? "Loading" : "Refresh"}</IconButton>
        </div>
      </section>
      <section className="tile-grid stats-tiles">
        <Card title="Page views" value={String(totals.views)} meta={`${days} day window`} icon={BarChart3} />
        <Card title="Devices" value={String(totals.devices)} meta="anonymous browser IDs" icon={Smartphone} />
        <Card title="Mobile views" value={String(totals.mobile)} meta="phone layout" icon={Smartphone} />
        <Card title="Desktop views" value={String(totals.desktop)} meta="desktop layout" icon={Monitor} />
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Pages by platform</h2><span>{rows.length} page/platform combination</span></div>
        <Table rows={rows.map((row, index) => ({ ...row, id: `${row.page_id}-${row.device_class}-${index}` }))} columns={[
          { key: "page_id", label: "Page", render: (row) => pageLabels[row.page_id] || row.page_id },
          { key: "device_class", label: "Platform" },
          { key: "views", label: "Views" },
          { key: "devices", label: "Devices" },
          { key: "last_seen", label: "Last used", render: (row) => dateText(row.last_seen) },
        ]} />
      </section>
    </>
  );
}
