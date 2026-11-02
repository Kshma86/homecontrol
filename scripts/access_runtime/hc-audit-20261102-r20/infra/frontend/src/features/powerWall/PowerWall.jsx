import React, { useState } from "react";
import { Activity, BatteryCharging, Database, Gauge, Power, RefreshCw, Save, Settings } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { dateText, displayEntityName, numberText, unitValue, valueText } from "../../formatters";
import { Card, IconButton, Table, V2KpiRow, V2Page, V2SectionGrid, V2Toolbar } from "../../uiPrimitives";
import { tuyaValueText } from "../tuya/tuyaMetrics";
import { powerWallDisplayName, PowerWallPowerMetric, powerWallMetricText, powerWallValue, switchOn } from "./powerWallCommon";

export default function PowerWall({ variant = "v1" }) {
  const [busy, setBusy] = useState("");
  const [policyBusy, setPolicyBusy] = useState("");
  const [displayNameBusy, setDisplayNameBusy] = useState("");
  const [displayNameEditor, setDisplayNameEditor] = useState(null);
  const [historyByEntity, setHistoryByEntity] = useState({});
  const { data: state, loading, error, setError, refresh: loadPowerWall } = usePolledContext("/api/context/power_wall", { intervalMs: 10000 });

  async function setPowerWallSwitch(device, value) {
    const busyKey = `${device.entity_id}:${value ? "on" : "off"}`;
    setBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/command", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, value }),
      });
      window.setTimeout(() => loadPowerWall(true), 1200);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function setPowerWallAlwaysOn(device, alwaysOn) {
    const busyKey = `${device.entity_id}:always-on`;
    setPolicyBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, always_on: alwaysOn }),
      });
      await loadPowerWall(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setPolicyBusy("");
    }
  }

  function editPowerWallDisplayName(device) {
    setDisplayNameEditor({
      entityId: device.entity_id,
      value: device.power_wall_display_name || device.display_name || device.entity_name || "",
    });
  }

  async function savePowerWallDisplayName(device) {
    const busyKey = `${device.entity_id}:display-name`;
    const value = String(displayNameEditor?.value || "").trim();
    setDisplayNameBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/display-name", {
        method: "PUT",
        body: JSON.stringify({ entity_id: device.entity_id, display_name: value || null }),
      });
      setDisplayNameEditor(null);
      await loadPowerWall(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setDisplayNameBusy("");
    }
  }

  async function loadPowerWallHistory(entityId) {
    if (!entityId || historyByEntity[entityId]?.data || historyByEntity[entityId]?.loading) return;
    setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: true, error: "", data: null } }));
    try {
      const data = await api(`/api/power-wall/history?entity_id=${encodeURIComponent(entityId)}`);
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: "", data } }));
    } catch (err) {
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: err.message, data: null } }));
    }
  }

  const devices = state?.devices || [];
  const batteryDevices = state?.battery_devices || [];
  const summary = state?.summary || {};
  const stateRows = state?.state_rows || [];
  const measurementRows = state?.recent_measurements || [];
  const totalPower = devices.reduce((sum, device) => sum + (Number(powerWallValue(device, ["power_w", "power"])) || 0), 0);
  const onlineCount = Number(summary.online || 0);
  const degradedCount = Number(summary.degraded || 0);
  const isV2 = variant === "v2";

  const content = (
    <>
      {isV2 ? (
        <V2Toolbar>
          <div>
            <h2>Power Wall</h2>
            <span>{error || `${devices.length} socket | ${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya | ${onlineCount} online`}</span>
          </div>
          <IconButton icon={RefreshCw} onClick={loadPowerWall} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
        </V2Toolbar>
      ) : (
        <section className="stats-head">
          <div>
            <h2>Power Wall</h2>
            <span>{error || `${devices.length} socket | ${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya | ${onlineCount} online`}</span>
          </div>
          <IconButton icon={RefreshCw} onClick={loadPowerWall} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
        </section>
      )}

      {isV2 ? (
        <V2KpiRow className="power-wall-summary">
          <Card title="Sockets" value={String(summary.total ?? devices.length)} meta={`${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya`} icon={Power} />
          <Card title="Online" value={String(onlineCount)} meta={`${degradedCount} degraded`} tone={degradedCount ? "warn" : ""} icon={Activity} />
          <Card title="Current Power" value={`${tuyaValueText(totalPower, 1)} W`} meta="sum of latest power" icon={Gauge} />
          <Card title="Samples" value={String(measurementRows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0))} meta="last 6 hours" icon={Database} />
          <Card title="Battery Devices" value={String(summary.battery_total ?? batteryDevices.length)} meta={`${summary.battery_low || 0} low`} tone={summary.battery_low ? "warn" : ""} icon={BatteryCharging} />
        </V2KpiRow>
      ) : (
        <section className="tile-grid stats-tiles tuya-summary power-wall-summary">
          <Card title="Sockets" value={String(summary.total ?? devices.length)} meta={`${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya`} icon={Power} />
          <Card title="Online" value={String(onlineCount)} meta={`${degradedCount} degraded`} tone={degradedCount ? "warn" : ""} icon={Activity} />
          <Card title="Current Power" value={`${tuyaValueText(totalPower, 1)} W`} meta="sum of latest power" icon={Gauge} />
          <Card title="Samples" value={String(measurementRows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0))} meta="last 6 hours" icon={Database} />
          <Card title="Battery Devices" value={String(summary.battery_total ?? batteryDevices.length)} meta={`${summary.battery_low || 0} low`} tone={summary.battery_low ? "warn" : ""} icon={BatteryCharging} />
        </section>
      )}

      <section className={isV2 ? "tuya-device-grid power-wall-v2-devices" : "tuya-device-grid"}>
        {devices.map((device) => {
          const status = device.status || "unknown";
          const isDegraded = status === "degraded";
          const isOffline = status === "offline";
          const switchState = powerWallValue(device, ["switch_state", "state"]);
          const switchStateOn = switchOn(switchState);
          const canCommand = ["zigbee", "tuya"].includes(device.platform) && status === "online";
          const powerValue = powerWallValue(device, ["power_w", "power"]);
          const currentValue = powerWallValue(device, ["current_a", "current"]);
          const voltageValue = powerWallValue(device, ["voltage_v", "mains_voltage_v"]);
          const energyValue = powerWallValue(device, ["energy_kwh"]);
          const lagValue = powerWallValue(device, ["lag_sec"]);
          const alwaysOn = Boolean(device.always_on);
          const isEditingDisplayName = displayNameEditor?.entityId === device.entity_id;
          return (
            <article className={`panel tuya-device ${alwaysOn ? "always-on" : ""} ${isOffline ? "bad" : isDegraded ? "warn" : ""}`} key={device.entity_id}>
              <div className="panel-head">
                <div className="power-wall-title-wrap">
                  {isEditingDisplayName ? (
                    <div className="power-wall-name-editor">
                      <Power size={17} aria-hidden="true" />
                      <input
                        value={displayNameEditor.value}
                        maxLength={80}
                        autoFocus
                        onChange={(event) => setDisplayNameEditor((current) => ({ ...current, value: event.target.value }))}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") savePowerWallDisplayName(device);
                          if (event.key === "Escape") setDisplayNameEditor(null);
                        }}
                      />
                      <IconButton
                        icon={Save}
                        className="secondary compact-icon-button"
                        disabled={displayNameBusy === `${device.entity_id}:display-name`}
                        onClick={() => savePowerWallDisplayName(device)}
                      >
                        Save
                      </IconButton>
                    </div>
                  ) : (
                    <h2 className="panel-title"><Power size={17} aria-hidden="true" /> {powerWallDisplayName(device)}</h2>
                  )}
                  {!isEditingDisplayName && (
                    <IconButton
                      icon={Settings}
                      className="secondary compact-icon-button"
                      title="Edit Power Wall display name"
                      onClick={() => editPowerWallDisplayName(device)}
                    >
                      Rename
                    </IconButton>
                  )}
                </div>
                <label className="always-on-toggle" title="Keep this socket switched on">
                  <input
                    type="checkbox"
                    checked={alwaysOn}
                    disabled={policyBusy === `${device.entity_id}:always-on`}
                    onChange={(event) => setPowerWallAlwaysOn(device, event.target.checked)}
                  />
                  <span>Always on</span>
                </label>
                <div className="power-wall-badges">
                  <span className={`platform-pill ${device.platform}`}>{device.platform}</span>
                  <span className={`status-pill ${status === "online" ? "ok" : isDegraded ? "warn" : "bad"}`}>{status}</span>
                </div>
              </div>
              <div className="tuya-device-meta">
                <span>{device.topic_base}</span>
                <span>{device.ext_id || "-"}</span>
                <span>{device.last_seen_ts ? `seen ${dateText(device.last_seen_ts)}` : "not seen yet"}</span>
              </div>
              <div className="tuya-metrics">
                <div><span>Switch</span><strong>{tuyaValueText(switchState)}</strong></div>
                <PowerWallPowerMetric
                  device={device}
                  value={powerValue}
                  history={historyByEntity[device.entity_id]}
                  loadHistory={loadPowerWallHistory}
                />
                <div><span>Voltage</span><strong>{powerWallMetricText(voltageValue, " V", 1)}</strong></div>
                <div><span>Current</span><strong>{powerWallMetricText(currentValue, " A", 3)}</strong></div>
                <div><span>Energy</span><strong>{powerWallMetricText(energyValue, " kWh", 2)}</strong></div>
                <div><span>Lag</span><strong>{powerWallMetricText(lagValue, " s", 0)}</strong></div>
              </div>
              {["zigbee", "tuya"].includes(device.platform) && (
                <div className="tuya-actions">
                  <IconButton
                    icon={Power}
                    className={switchStateOn === true ? "secondary" : ""}
                    disabled={!canCommand || Boolean(busy)}
                    onClick={() => setPowerWallSwitch(device, true)}
                  >
                    {busy === `${device.entity_id}:on` ? "Turning on" : "ON"}
                  </IconButton>
                  <IconButton
                    icon={Power}
                    className={switchStateOn === false ? "secondary" : ""}
                    disabled={!canCommand || Boolean(busy)}
                    onClick={() => setPowerWallSwitch(device, false)}
                  >
                    {busy === `${device.entity_id}:off` ? "Turning off" : "OFF"}
                  </IconButton>
                </div>
              )}
            </article>
          );
        })}
      </section>

      <section className={isV2 ? "panel power-wall-v2-battery" : "panel"}>
        <div>
          <div className="panel-head">
            <h2>Battery Devices</h2>
            <span>{batteryDevices.length} device | low threshold 30%</span>
          </div>
          <Table
            rows={batteryDevices}
            columns={[
              { key: "entity_name", label: "Device", render: (row) => displayEntityName(row.entity_name) },
              { key: "location", label: "Location", render: (row) => displayEntityName(row.location) },
              { key: "platform", label: "Type" },
              {
                key: "battery_percent",
                label: "Battery",
                render: (row) => {
                  const rawValue = row.battery_percent;
                  const hasValue = rawValue !== undefined && rawValue !== null && rawValue !== "";
                  const value = Number(rawValue);
                  const isKnown = hasValue && Number.isFinite(value);
                  const low = row.battery_low === true || (isKnown && value <= 30);
                  const bad = row.battery_low === true || (isKnown && value <= 15);
                  return (
                    <span className={`status-pill ${bad ? "bad" : low ? "warn" : "ok"}`}>
                      {isKnown ? unitValue(value, "%", 0) : row.battery_low === true ? "LOW" : "-"}
                    </span>
                  );
                },
              },
              { key: "battery_low", label: "Low Flag", render: (row) => (row.battery_low === true ? "Low" : row.battery_low === false ? "OK" : "-") },
              { key: "linkquality", label: "LQI", render: (row) => numberText(row.linkquality, 0) },
              { key: "battery_ts", label: "Battery Updated", render: (row) => dateText(row.battery_ts || row.battery_low_ts) },
              { key: "last_seen_ts", label: "Last Seen", render: (row) => dateText(row.last_seen_ts) },
            ]}
          />
        </div>
      </section>

      {isV2 ? (
        <V2SectionGrid className="power-wall-v2-tables">
          <article className="panel v2-span-6">
            <div className="panel-head">
              <h2>Current Socket State</h2>
              <span>{stateRows.length} rows</span>
            </div>
            <Table
              rows={stateRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
              columns={[
                { key: "platform", label: "Type" },
                { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
                { key: "key", label: "Metric" },
                { key: "value", label: "Value", render: valueText },
                { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
              ]}
            />
          </article>
          <article className="panel v2-span-6">
            <div className="panel-head">
              <h2>Recent Socket Measurements</h2>
              <span>last 6 hours</span>
            </div>
            <Table
              rows={measurementRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
              columns={[
                { key: "platform", label: "Type" },
                { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
                { key: "key", label: "Metric" },
                { key: "sample_count", label: "Samples" },
                { key: "avg_num", label: "Avg", render: (row) => tuyaValueText(row.avg_num, 2) },
                { key: "max_num", label: "Max", render: (row) => tuyaValueText(row.max_num, 2) },
                { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
              ]}
            />
          </article>
        </V2SectionGrid>
      ) : (
        <section className="grid two">
          <article className="panel">
          <div className="panel-head">
            <h2>Current Socket State</h2>
            <span>{stateRows.length} rows</span>
          </div>
          <Table
            rows={stateRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "platform", label: "Type" },
              { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "value", label: "Value", render: valueText },
              { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Recent Socket Measurements</h2>
            <span>last 6 hours</span>
          </div>
          <Table
            rows={measurementRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "platform", label: "Type" },
              { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "sample_count", label: "Samples" },
              { key: "avg_num", label: "Avg", render: (row) => tuyaValueText(row.avg_num, 2) },
              { key: "max_num", label: "Max", render: (row) => tuyaValueText(row.max_num, 2) },
              { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
            ]}
          />
          </article>
        </section>
      )}
    </>
  );

  return isV2 ? <V2Page className="power-wall-v2">{content}</V2Page> : content;
}
