import React, { useState } from "react";
import { Activity, Database, Gauge, Power, RefreshCw } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { dateText, displayEntityName, valueText } from "../../formatters";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { tuyaMetric, tuyaStateValue, tuyaValueText } from "./tuyaMetrics";

export default function TuyaPlayground() {
  const [busy, setBusy] = useState("");
  const { data: state, loading, error, setError, refresh: loadTuya } = usePolledContext("/api/context/tuya", { intervalMs: 10000 });

  async function setTuyaSwitch(device, value) {
    const busyKey = `${device.entity_id}:${value ? "on" : "off"}`;
    setBusy(busyKey);
    setError("");
    try {
      await api("/api/tuya/command", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, value }),
      });
      window.setTimeout(() => loadTuya(true), 1200);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  const devices = state?.devices || [];
  const batteryDevices = state?.battery_devices || [];
  const summary = state?.summary || {};
  const stateRows = state?.state_rows || [];
  const measurementRows = state?.recent_measurements || [];
  const totalPower = devices.reduce((sum, device) => sum + (Number(tuyaStateValue(device, "power_w")) || 0), 0);
  const onlineCount = Number(summary.online || 0);
  const degradedCount = Number(summary.degraded || 0);

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Tuya</h2>
          <span>{error || `${devices.length} active device | ${onlineCount} online | ${degradedCount} degraded`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadTuya} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles tuya-summary">
        <Card title="Devices" value={String(summary.total ?? devices.length)} meta={`${onlineCount} online`} icon={Power} />
        <Card title="Degraded" value={String(degradedCount)} meta="poller availability" tone={degradedCount ? "warn" : ""} icon={Activity} />
        <Card title="Current Power" value={`${tuyaValueText(totalPower, 1)} W`} meta="sum of latest power_w" icon={Gauge} />
        <Card title="Samples" value={String(measurementRows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0))} meta="last 6 hours" icon={Database} />
      </section>

      <section className="tuya-device-grid">
        {devices.map((device) => {
          const status = device.status || "unknown";
          const isDegraded = status === "degraded";
          const isOffline = status === "offline";
          const switchState = tuyaStateValue(device, "switch_state");
          const canCommand = status === "online";
          return (
            <article className={`panel tuya-device ${isOffline ? "bad" : isDegraded ? "warn" : ""}`} key={device.entity_id}>
              <div className="panel-head">
                <h2 className="panel-title"><Power size={17} aria-hidden="true" /> {displayEntityName(device.entity_name)}</h2>
                <span className={`status-pill ${status === "online" ? "ok" : isDegraded ? "warn" : "bad"}`}>{status}</span>
              </div>
              <div className="tuya-device-meta">
                <span>{device.topic_base}</span>
                <span>{device.ext_id || "-"}</span>
                <span>{device.last_seen_ts ? `seen ${dateText(device.last_seen_ts)}` : "not seen yet"}</span>
              </div>
              <div className="tuya-metrics">
                <div><span>Switch</span><strong>{tuyaMetric(device, "switch_state")}</strong></div>
                <div><span>Power</span><strong>{tuyaMetric(device, "power_w", " W", 1)}</strong></div>
                <div><span>Voltage</span><strong>{tuyaMetric(device, "voltage_v", " V", 1)}</strong></div>
                <div><span>Current</span><strong>{tuyaMetric(device, "current_a", " A", 3)}</strong></div>
                <div><span>Energy</span><strong>{tuyaMetric(device, "energy_kwh", " kWh", 2)}</strong></div>
                <div><span>Lag</span><strong>{tuyaMetric(device, "lag_sec", " s", 0)}</strong></div>
              </div>
              <div className="tuya-actions">
                <IconButton
                  icon={Power}
                  className={switchState === true ? "secondary" : ""}
                  disabled={!canCommand || Boolean(busy)}
                  onClick={() => setTuyaSwitch(device, true)}
                >
                  {busy === `${device.entity_id}:on` ? "Turning on" : "ON"}
                </IconButton>
                <IconButton
                  icon={Power}
                  className={switchState === false ? "secondary" : ""}
                  disabled={!canCommand || Boolean(busy)}
                  onClick={() => setTuyaSwitch(device, false)}
                >
                  {busy === `${device.entity_id}:off` ? "Turning off" : "OFF"}
                </IconButton>
              </div>
            </article>
          );
        })}
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Current State Rows</h2>
            <span>{stateRows.length} rows</span>
          </div>
          <Table
            rows={stateRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "entity_name", label: "Device", render: (row) => displayEntityName(row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "value", label: "Value", render: valueText },
              { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Recent Measurements</h2>
            <span>last 6 hours</span>
          </div>
          <Table
            rows={measurementRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "entity_name", label: "Device", render: (row) => displayEntityName(row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "sample_count", label: "Samples" },
              { key: "avg_num", label: "Avg", render: (row) => tuyaValueText(row.avg_num, 2) },
              { key: "min_num", label: "Min", render: (row) => tuyaValueText(row.min_num, 2) },
              { key: "max_num", label: "Max", render: (row) => tuyaValueText(row.max_num, 2) },
              { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
            ]}
          />
        </article>
      </section>
    </>
  );
}
