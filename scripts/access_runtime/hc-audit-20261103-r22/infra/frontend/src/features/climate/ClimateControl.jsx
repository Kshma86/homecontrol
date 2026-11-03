import React, { useEffect, useMemo, useState } from "react";
import { Activity, BatteryCharging, CalendarDays, Clock, Gauge, Lightbulb, Plus, Power, RefreshCw, Save, Square, Thermometer, Trash2, Wind, Zap } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { StatBarChart, TimeLineChart } from "../../chartPrimitives";
import { findYardSensor } from "../../entityHelpers";
import { dateText, displayEntityName, metricNumber, optionLabel, shortValue, unitValue } from "../../formatters";
import { SensorRangeSwitch, SensorSnapshotTable } from "../../houseSensors";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { climateFanOptions, climateModeOptions } from "./climateOptions";
import { climateDraftFromState } from "./climateState";
import { dayLabels } from "../scheduler/schedulerOptions";
import { powerWallMetricText, PowerWallPowerMetric, powerWallValue, switchOn } from "../powerWall/powerWallCommon";
import { tuyaValueText } from "../tuya/tuyaMetrics";

export default function ClimateControl({ setToast }) {
  const [draft, setDraft] = useState(() => climateDraftFromState(null));
  const [draftDirty, setDraftDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const { data: state, setData: setState, loading, error, setError, refresh: loadClimate } = usePolledContext("/api/context/climate", {
    intervalMs: 10000,
  });
  const { data: localSensorsPayload } = usePolledContext("/api/context/home_statistics", {
    intervalMs: 30000,
    refreshPaths: ["/api/context/home_statistics"],
    mapPayload: (payload) => payload?.temp_humidity_sensors || [],
  });

  useEffect(() => {
    if (!state) return;
    if (draftDirty || busy) return;
    setDraft(climateDraftFromState(state));
  }, [state, draftDirty, busy]);

  function updateDraft(key, value) {
    setDraftDirty(true);
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function sendClimate(payload, busyKey = "command", message = "Climate command sent") {
    setBusy(busyKey);
    try {
      const data = await api("/api/climate/gree/command", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const nextState = data.state || data;
      setState(nextState);
      setDraft({ ...climateDraftFromState(nextState), extra_fan: payload.extra_fan || draft.extra_fan });
      setDraftDirty(false);
      setError("");
      setToast(message);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function applyDraft() {
    await sendClimate({
      power: draft.power,
      mode: draft.mode,
      target_temperature: Number(draft.target_temperature),
      fan_speed: draft.fan_speed,
      extra_fan: draft.extra_fan,
    }, "apply", "Climate settings applied");
  }

  const online = state?.bridge_online && !error;
  const modeLabel = optionLabel(climateModeOptions, state?.mode);
  const fanLabel = optionLabel(climateFanOptions, state?.fan_speed);
  const powerMeter = state?.power_meter || {};
  const powerMeterState = powerMeter.state || {};
  const powerMeterDaily = powerMeter.daily || {};
  const localSensors = Array.isArray(localSensorsPayload) ? localSensorsPayload : [];
  const yardSensor = findYardSensor(localSensors);
  const yardTemperature = metricNumber(yardSensor, "latest_temperature");

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading climate...</span>
      </section>
    );
  }

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>{state?.name || "Gree Climate"}</h2>
          <span>{error || `${state?.ip || "192.168.1.72"}:${state?.port || 7000} | bridge ${online ? "online" : "offline"} | ${state?.base_topic || "homecontrol/gree_climate"}`}</span>
        </div>
        <IconButton
          icon={RefreshCw}
          onClick={async () => {
            setDraftDirty(false);
            await loadClimate();
          }}
          disabled={loading}
        >
          {loading ? "Refreshing" : "Refresh"}
        </IconButton>
      </section>

      <section className="tile-grid stats-tiles climate-tiles">
        <Card
          title="Power"
          value={String(state?.power || "-").toUpperCase()}
          meta={`${unitValue(powerMeterState.power_w, "W", 0)} | target ${unitValue(state?.target_temperature, "C", 0)} | current ${unitValue(state?.current_temperature, "C", 1)}`}
          icon={Power}
          tone={state?.power === "off" ? "warn" : ""}
        />
        <Card title="Target/Current TEMP" value={`${unitValue(state?.target_temperature, "C", 0)} / ${unitValue(state?.current_temperature, "C", 1)}`} meta={state?.updated_at ? dateText(state.updated_at) : "-"} icon={Thermometer} tone={state?.power === "off" ? "warn" : ""} />
        <Card title="Yard Temp" value={unitValue(yardTemperature, "C", 1)} meta={yardSensor?.latest_ts ? dateText(yardSensor.latest_ts) : "-"} icon={Thermometer} />
        <Card title="Mode" value={modeLabel} meta={`fan ${fanLabel}`} icon={Wind} />
        <Card title="Today Use" value={unitValue(powerMeterDaily.energy_kwh, "kWh", 2)} meta={`${powerMeterDaily.sample_count || 0} samples | ${powerMeter.status || "unknown"}`} icon={BatteryCharging} tone={powerMeter.ok ? "" : "warn"} />
        <Card title="Total Energy" value={unitValue(powerMeterState.energy_kwh, "kWh", 2)} meta={unitValue(powerMeterState.voltage_v, "V", 1)} icon={BatteryCharging} />
      </section>

      <WindowGuardPanel guard={state?.window_guard} setToast={setToast} refresh={loadClimate} />

      <section className="grid two climate-grid">
        <div className="climate-stack">
          <article className="panel">
            <div className="panel-head">
              <h2>Quick Control</h2>
              <span>{busy ? `sending ${busy}` : "direct Gree API"}</span>
            </div>
            <div className="button-grid climate-power-grid">
              <IconButton icon={Power} disabled={Boolean(busy)} onClick={() => sendClimate({ power: "on", extra_fan: draft.extra_fan }, "power_on", "Climate turned on")}>On</IconButton>
              <IconButton icon={Square} className="secondary" disabled={Boolean(busy)} onClick={() => sendClimate({ power: "off" }, "power_off", "Climate turned off")}>Off</IconButton>
              <IconButton icon={Lightbulb} disabled={Boolean(busy)} onClick={() => sendClimate({ light: state?.light === "on" ? "off" : "on" }, "light", "Light toggled")}>Light</IconButton>
              <IconButton
                icon={RefreshCw}
                className="secondary"
                disabled={Boolean(busy)}
                onClick={async () => {
                  setDraftDirty(false);
                  await loadClimate();
                }}
              >
                Refresh
              </IconButton>
            </div>
            <div className="button-grid climate-extra-grid">
              <IconButton
                icon={Wind}
                className={state?.quiet === "on" ? "" : "secondary"}
                disabled={Boolean(busy)}
                onClick={() => sendClimate(
                  state?.quiet === "on" ? { quiet: "off" } : { quiet: "on", turbo: "off" },
                  "quiet",
                  state?.quiet === "on" ? "Quiet turned off" : "Quiet turned on"
                )}
              >
                Quiet
              </IconButton>
              <IconButton
                icon={Zap}
                className={state?.turbo === "on" ? "" : "secondary"}
                disabled={Boolean(busy)}
                onClick={() => sendClimate(
                  state?.turbo === "on" ? { turbo: "off" } : { turbo: "on", quiet: "off" },
                  "turbo",
                  state?.turbo === "on" ? "Turbo turned off" : "Turbo turned on"
                )}
              >
                Turbo
              </IconButton>
              <IconButton
                icon={Clock}
                className={state?.sleep === "on" ? "" : "secondary"}
                disabled={Boolean(busy)}
                onClick={() => sendClimate({ sleep: state?.sleep === "on" ? "off" : "on" }, "sleep", "Sleep toggled")}
              >
                Sleep
              </IconButton>
              <IconButton
                icon={RefreshCw}
                className={state?.xfan === "on" ? "" : "secondary"}
                disabled={Boolean(busy)}
                onClick={() => sendClimate({ xfan: state?.xfan === "on" ? "off" : "on" }, "xfan", "XFan toggled")}
              >
                XFan
              </IconButton>
              <IconButton
                icon={Gauge}
                className={state?.power_save === "on" ? "" : "secondary"}
                disabled={Boolean(busy)}
                onClick={() => sendClimate({ power_save: state?.power_save === "on" ? "off" : "on" }, "power_save", "Power save toggled")}
              >
                Save
              </IconButton>
              <label className="climate-buzzer-toggle">
                <input
                  type="checkbox"
                  role="switch"
                  checked={state?.buzzer === "off"}
                  disabled={Boolean(busy) || !online || !["on", "off"].includes(state?.buzzer)}
                  onChange={(event) => sendClimate({ buzzer: event.target.checked ? "off" : "on" }, "buzzer", "Csipogás beállítása elküldve")}
                />
                <span>Csipogás némítása</span>
              </label>
            </div>

            <div className="climate-form">
              <label>
                Power
                <select value={draft.power} onChange={(event) => updateDraft("power", event.target.value)}>
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
              <label>
                Mode
                <select value={draft.mode} onChange={(event) => updateDraft("mode", event.target.value)}>
                  {climateModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                Target
                <input
                  type="number"
                  min="8"
                  max="30"
                  step="1"
                  value={draft.target_temperature}
                  onChange={(event) => updateDraft("target_temperature", event.target.value)}
                />
              </label>
              <label>
                Fan
                <select value={draft.fan_speed} onChange={(event) => updateDraft("fan_speed", event.target.value)}>
                  {climateFanOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                Extra fan
                <select value={draft.extra_fan} onChange={(event) => updateDraft("extra_fan", event.target.value)}>
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
              <IconButton icon={Save} disabled={Boolean(busy)} onClick={applyDraft}>{busy === "apply" ? "Applying" : "Apply"}</IconButton>
            </div>
          </article>
          <ClimatePowerWallPlug setToast={setToast} />
        </div>

        <article className="panel">
          <div className="panel-head">
            <h2>Device State</h2>
            <span>{state?.updated_at || "-"}</span>
          </div>
          <div className="meter-list">
            <div className="meter-row">
              <strong>Endpoint</strong>
              <span>{state?.ip || "-"}:{state?.port || "-"}</span>
              <b>{state?.mac || "-"}</b>
            </div>
            <div className="meter-row">
              <strong>Current</strong>
              <span>{unitValue(state?.current_temperature, "C", 1)} | power {state?.power || "-"}</span>
              <b>{state?.power || "-"}</b>
            </div>
            <div className="meter-row">
              <strong>Target</strong>
              <span>{unitValue(state?.target_temperature, "C", 0)} | mode {modeLabel}</span>
              <b>{fanLabel}</b>
            </div>
            <div className="meter-row">
              <strong>Extras</strong>
              <span>sleep {state?.sleep || "-"} | xfan {state?.xfan || "-"} | save {state?.power_save || "-"}</span>
              <b>{state?.quiet === "on" ? "Quiet" : state?.turbo === "on" ? "Turbo" : state?.light === "on" ? "Light" : "-"}</b>
            </div>
            <div className="meter-row">
              <strong>Current Use</strong>
              <span>{powerMeter.ok ? unitValue(powerMeterState.voltage_v, "V", 1) : powerMeter.error || "-"}</span>
              <b>{unitValue(powerMeterState.power_w, "W", 0)}</b>
            </div>
            <div className="meter-row">
              <strong>Today Use</strong>
              <span>{powerMeterDaily.sample_count || 0} samples</span>
              <b>{unitValue(powerMeterDaily.energy_kwh, "kWh", 2)}</b>
            </div>
            <div className="meter-row">
              <strong>Total Energy</strong>
              <span>{powerMeter.entity_name || "-"} | {unitValue(powerMeterState.voltage_v, "V", 1)}</span>
              <b>{unitValue(powerMeterState.energy_kwh, "kWh", 2)}</b>
            </div>
          </div>
          <div className="panel-subhead">
            <h3>Raw Properties</h3>
            <span>{Object.keys(state?.raw_properties || {}).length} values</span>
          </div>
          <pre className="json-box climate-raw">{shortValue(state?.raw_properties || {}, 1200)}</pre>
        </article>
      </section>

      <ClimatePowerCharts />
      <ClimateScheduleRules setToast={setToast} />
      <ClimateSensorSnapshot />
    </>
  );
}

function ClimatePowerWallPlug({ setToast }) {
  const [delayDraft, setDelayDraft] = useState(null);
  const [busy, setBusy] = useState("");
  const [policyBusy, setPolicyBusy] = useState("");
  const [historyByEntity, setHistoryByEntity] = useState({});
  const { data: state, loading, error, setError, refresh: loadPlug } = usePolledContext("/api/context/power_wall", { intervalMs: 10000 });

  async function setPlugSwitch(device, value) {
    const busyKey = `${device.entity_id}:${value ? "on" : "off"}`;
    setBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/command", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, value }),
      });
      setToast(value ? "Climate plug turned on" : "Climate plug turned off");
      window.setTimeout(() => loadPlug(true), 1200);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function setPlugAlwaysOn(device, alwaysOn) {
    const busyKey = `${device.entity_id}:always-on`;
    setPolicyBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, always_on: alwaysOn }),
      });
      setToast(alwaysOn ? "Climate plug always-on enabled" : "Climate plug always-on disabled");
      await loadPlug(true);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setPolicyBusy("");
    }
  }

  async function setPlugAutoClimate(device, autoClimate) {
    const busyKey = `${device.entity_id}:auto-climate`;
    setPolicyBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, auto_climate: autoClimate }),
      });
      setToast(autoClimate ? "Climate plug auto mode enabled" : "Climate plug auto mode disabled");
      await loadPlug(true);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setPolicyBusy("");
    }
  }

  async function saveFanDelay(device) {
    const minutes = Number(delayDraft ?? device.auto_climate_delay_minutes ?? 0);
    if (delayDraft === "" || !Number.isInteger(minutes) || minutes < 0 || minutes > 120) {
      setToast("A késleltetés 0 és 120 közötti egész perc lehet.");
      return;
    }
    setPolicyBusy(`${device.entity_id}:delay`);
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, auto_climate_delay_minutes: minutes }),
      });
      await loadPlug(true);
      setDelayDraft(null);
      setToast("Venti késleltetése mentve");
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setPolicyBusy("");
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

  const device = (state?.devices || []).find((item) => String(item.entity_name || "").toLowerCase() === "felső előszoba konnektor");
  if (loading && !state) {
    return (
      <article className="panel tuya-device">
        <div className="panel-head">
          <h2 className="panel-title"><Power size={17} aria-hidden="true" /> Upstairs Hallway Plug</h2>
          <span className="status-pill warn">loading</span>
        </div>
        <div className="chart-empty diff-empty">Loading plug...</div>
      </article>
    );
  }
  if (!device) {
    return (
      <article className="panel tuya-device warn">
        <div className="panel-head">
          <h2 className="panel-title"><Power size={17} aria-hidden="true" /> Upstairs Hallway Plug</h2>
          <span className="status-pill warn">missing</span>
        </div>
        <div className="muted-text">{error || "Plug not found in Power Wall state"}</div>
      </article>
    );
  }

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
  const autoClimate = Boolean(device.auto_climate);

  return (
    <article className={`panel tuya-device climate-plug-device ${alwaysOn ? "always-on" : ""} ${isOffline ? "bad" : isDegraded ? "warn" : ""}`}>
      <div className="panel-head">
        <h2 className="panel-title"><Power size={17} aria-hidden="true" /> {displayEntityName(device.entity_name)}</h2>
        <div className="climate-plug-toggles">
          <label className="always-on-toggle" title="Keep this socket switched on">
            <input
              type="checkbox"
              checked={alwaysOn}
              disabled={policyBusy === `${device.entity_id}:always-on`}
              onChange={(event) => setPlugAlwaysOn(device, event.target.checked)}
            />
            <span>Always on</span>
          </label>
          <label className="always-on-toggle" title="Follow climate power on/off commands">
            <input
              type="checkbox"
              checked={autoClimate}
              disabled={policyBusy === `${device.entity_id}:auto-climate`}
              onChange={(event) => setPlugAutoClimate(device, event.target.checked)}
            />
            <span>Auto</span>
          </label>
        </div>
        <div className="power-wall-badges">
          <span className={`platform-pill ${device.platform}`}>{device.platform}</span>
          <span className={`status-pill ${status === "online" ? "ok" : isDegraded ? "warn" : "bad"}`}>{status}</span>
        </div>
      </div>
      <div className="tuya-device-meta">
        <span>{error || device.topic_base}</span>
        <span>{device.ext_id || "-"}</span>
        <span>{device.last_seen_ts ? `seen ${dateText(device.last_seen_ts)}` : "not seen yet"}</span>
        <div className="climate-fan-delay">
          <label htmlFor="climate-fan-delay">Venti késleltetés (perc)</label>
          <input id="climate-fan-delay" type="number" min="0" max="120" step="1"
            value={delayDraft ?? device.auto_climate_delay_minutes ?? 0}
            disabled={Boolean(policyBusy)}
            onChange={(event) => setDelayDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter") saveFanDelay(device); }} />
          <IconButton icon={Save} disabled={Boolean(policyBusy) || delayDraft === null}
            onClick={() => saveFanDelay(device)}>Mentés</IconButton>
        </div>
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
      <div className="tuya-actions">
        <IconButton
          icon={Power}
          className={switchStateOn === true ? "secondary" : ""}
          disabled={!canCommand || Boolean(busy)}
          onClick={() => setPlugSwitch(device, true)}
        >
          {busy === `${device.entity_id}:on` ? "Turning on" : "ON"}
        </IconButton>
        <IconButton
          icon={Power}
          className={switchStateOn === false ? "secondary" : ""}
          disabled={!canCommand || Boolean(busy)}
          onClick={() => setPlugSwitch(device, false)}
        >
          {busy === `${device.entity_id}:off` ? "Turning off" : "OFF"}
        </IconButton>
      </div>
    </article>
  );
}

function ClimatePowerCharts() {
  const { data: history, loading, error } = usePolledContext("/api/context/climate_power_history", { intervalMs: 30000 });

  const powerRows = history?.power_24h || [];
  const dailyRows = history?.daily_30d || [];
  const summary = history?.summary || {};
  const extraFan = history?.extra_fan || {};
  const extraFanPowerRows = extraFan.power_24h || [];
  const extraFanDailyRows = extraFan.daily_30d || [];
  const extraFanSummary = extraFan.summary || {};
  const extraFanTitle = extraFan.device?.display_name || extraFan.device?.entity_name || "Extra Fan";

  return (
    <section className="grid two climate-grid">
      <article className="panel">
        <div className="panel-head">
          <h2>Climate Power / 24h</h2>
          <span>{error || `${summary.power_samples || powerRows.length} samples`}</span>
        </div>
        {loading && !history ? <div className="chart-empty">Loading...</div> : <TimeLineChart rows={powerRows} valueKey="power_w" unit="W" digits={0} color="blue" />}
      </article>

      <article className="panel">
        <div className="panel-head">
          <h2>Daily Climate Use / 30d</h2>
          <span>{unitValue(summary.today_energy_kwh, "kWh", 2)} today</span>
        </div>
        {loading && !history ? <div className="chart-empty">Loading...</div> : <StatBarChart rows={dailyRows} valueKey="energy_kwh" unit="kWh" digits={2} color="green" />}
      </article>

      <article className="panel">
        <div className="panel-head">
          <h2>{extraFanTitle} Power / 24h</h2>
          <span>{extraFan.ok === false ? extraFan.error : `${unitValue(extraFanSummary.current_power_w, "W", 0)} now | ${extraFanSummary.power_samples || extraFanPowerRows.length} samples`}</span>
        </div>
        {loading && !history ? <div className="chart-empty">Loading...</div> : <TimeLineChart rows={extraFanPowerRows} valueKey="power_w" unit="W" digits={0} color="yellow" />}
      </article>

      <article className="panel">
        <div className="panel-head">
          <h2>Daily {extraFanTitle} Use / 30d</h2>
          <span>{extraFan.ok === false ? extraFan.error : `${unitValue(extraFanSummary.today_energy_kwh, "kWh", 3)} today`}</span>
        </div>
        {loading && !history ? <div className="chart-empty">Loading...</div> : <StatBarChart rows={extraFanDailyRows} valueKey="energy_kwh" unit="kWh" digits={3} color="yellow" />}
      </article>
    </section>
  );
}

function ClimateScheduleRules({ setToast }) {
  const [busy, setBusy] = useState("");
  const [seasonProfile, setSeasonProfile] = useState("summer");
  const { data: schedulesPayload, setData: setSchedules, loading, error, refresh: loadSchedules } = usePolledContext("/api/context/climate_schedules", {
    mapPayload: (payload) => payload?.schedules || [],
    onError: (err) => setToast(err.message),
  });
  const schedules = Array.isArray(schedulesPayload) ? schedulesPayload : [];
  const schedulesByDay = useMemo(() => dayLabels.map((label, dayIndex) => ({
    label,
    dayIndex,
    rows: schedules
      .filter((row) => Number(row.day_of_week) === dayIndex)
      .sort((a, b) => String(a.start_time || "").localeCompare(String(b.start_time || ""))),
  })), [schedules]);

  useEffect(() => {
    api("/api/admin/season-profiles")
      .then((data) => setSeasonProfile(data?.domains?.climate?.active_profile || "summer"))
      .catch((err) => setToast(err.message));
  }, []);

  function updateSchedule(id, key, value) {
    setSchedules((current) => current.map((item) => (
      item.id === id ? { ...item, [key]: value } : item
    )));
  }

  async function saveSchedule(row) {
    setBusy(String(row.id));
    try {
      const payload = { ...row, light: row.light || "keep" };
      const data = await api(`/api/climate/gree/schedules/${row.id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setSchedules(data.schedules || []);
      setToast("Climate schedule saved");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function addSchedule(dayIndex) {
    setBusy(`new-${dayIndex}`);
    try {
      const data = await api("/api/climate/gree/schedules", {
        method: "POST",
        body: JSON.stringify({
          label: "Climate event",
          day_of_week: dayIndex,
          start_time: "06:30",
          is_enabled: false,
          power: "on",
          mode: "heat",
          target_temperature: 23,
          fan_speed: "auto",
          light: "keep",
          extra_fan: "keep",
          rule_engine: { rule_engine: "manual_schedule" },
          season_profile: seasonProfile,
        }),
      });
      setSchedules(data.schedules || []);
      setToast("Climate event added");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function addHotDayPair(dayIndex) {
    setBusy(`hot-day-${dayIndex}`);
    const base = {
      day_of_week: dayIndex,
      is_enabled: false,
      power: "keep",
      mode: "keep",
      target_temperature: 23,
      light: "keep",
      rule_engine: { rule_engine: "hot_day_comfort" },
      season_profile: seasonProfile,
    };
    try {
      await api("/api/climate/gree/schedules", {
        method: "POST",
        body: JSON.stringify({
          ...base,
          label: "Hot day morning boost",
          start_time: "08:00",
          fan_speed: "medium",
          extra_fan: "on",
        }),
      });
      const data = await api("/api/climate/gree/schedules", {
        method: "POST",
        body: JSON.stringify({
          ...base,
          label: "Hot day evening quiet",
          start_time: "22:00",
          fan_speed: "quiet",
          extra_fan: "off",
        }),
      });
      setSchedules(data.schedules || []);
      setToast("Hot day climate pair added");
    } catch (err) {
      setToast(err.message);
      await loadSchedules(true);
    } finally {
      setBusy("");
    }
  }

  async function deleteSchedule(row) {
    setBusy(`delete-${row.id}`);
    try {
      const data = await api(`/api/climate/gree/schedules/${row.id}`, {
        method: "DELETE",
      });
      setSchedules(data.schedules || []);
      setToast("Climate event deleted");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="panel climate-schedule-panel">
      <div className="panel-head">
        <div>
          <h2>Climate Schedule</h2>
          <span>{error || `${schedules.length} events | ${seasonProfile} scheduler`}</span>
        </div>
        <span>Aktív profil: {seasonProfile === "winter" ? "Winter" : "Summer"} · váltás a HC Adminban</span>
        <IconButton icon={RefreshCw} onClick={() => loadSchedules()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </div>
      <div className="climate-schedule-list">
        {schedulesByDay.map((day) => (
          <div className="climate-schedule-day" key={day.dayIndex}>
            <div className="climate-schedule-day-head">
              <div>
                <strong>{day.label}</strong>
                <span>{day.rows.length} events</span>
              </div>
              <IconButton icon={Plus} onClick={() => addSchedule(day.dayIndex)} disabled={busy === `new-${day.dayIndex}`}>
                {busy === `new-${day.dayIndex}` ? "Adding" : "Add event"}
              </IconButton>
              <IconButton icon={CalendarDays} className="secondary" onClick={() => addHotDayPair(day.dayIndex)} disabled={busy === `hot-day-${day.dayIndex}`}>
                {busy === `hot-day-${day.dayIndex}` ? "Adding" : "Hot day pair"}
              </IconButton>
            </div>
            <div className="climate-schedule-day-rows">
              {day.rows.map((row) => (
                <div className={`climate-schedule-row ${row.is_enabled ? "active" : ""}`} key={row.id}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={Boolean(row.is_enabled)}
                      onChange={(event) => updateSchedule(row.id, "is_enabled", event.target.checked)}
                    />
                    Enabled
                  </label>
                  <label>
                    Label
                    <input type="text" value={row.label || ""} onChange={(event) => updateSchedule(row.id, "label", event.target.value)} />
                  </label>
                  <label>
                    Time
                    <input type="time" value={row.start_time || "06:30"} onChange={(event) => updateSchedule(row.id, "start_time", event.target.value)} />
                  </label>
                  <label>
                    Power
                    <select value={row.power || "on"} onChange={(event) => updateSchedule(row.id, "power", event.target.value)}>
                      <option value="keep">Keep</option>
                      <option value="on">On</option>
                      <option value="off">Off</option>
                    </select>
                  </label>
                  <label>
                    Mode
                    <select value={row.mode || "heat"} onChange={(event) => updateSchedule(row.id, "mode", event.target.value)}>
                      <option value="keep">Keep</option>
                      {climateModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    Target
                    <input type="number" min="8" max="30" value={row.target_temperature ?? 23} onChange={(event) => updateSchedule(row.id, "target_temperature", event.target.value)} />
                  </label>
                  <label>
                    Fan
                    <select value={row.fan_speed || "auto"} onChange={(event) => updateSchedule(row.id, "fan_speed", event.target.value)}>
                      <option value="keep">Keep</option>
                      {climateFanOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    Extra fan
                    <select value={row.extra_fan || "keep"} onChange={(event) => updateSchedule(row.id, "extra_fan", event.target.value)}>
                      <option value="keep">Keep</option>
                      <option value="on">On</option>
                      <option value="off">Off</option>
                    </select>
                  </label>
                  <div className="climate-schedule-actions">
                    <IconButton icon={Save} disabled={busy === String(row.id)} onClick={() => saveSchedule(row)}>{busy === String(row.id) ? "Saving" : "Save"}</IconButton>
                    <IconButton icon={Trash2} disabled={busy === `delete-${row.id}`} onClick={() => deleteSchedule(row)}>{busy === `delete-${row.id}` ? "Deleting" : "Delete"}</IconButton>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ClimateSensorSnapshot() {
  const [chartRange, setChartRange] = useState("24h");
  const statsPath = `/api/homecontrol/statistics?range=${chartRange}`;
  const { data: stats, loading, error, refresh: loadStats } = usePolledContext(statsPath, {
    intervalMs: 30000,
    refreshPaths: [statsPath],
  });

  const sensors = stats?.temp_humidity_sensors || [];
  const openingSensors = stats?.opening_sensors || [];

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Sensor Snapshot</h2>
          <span>{error || `${sensors.length} temp/humidity sensors | ${stats?.range || chartRange}`}</span>
        </div>
        <SensorRangeSwitch value={chartRange} onChange={setChartRange} />
        <IconButton icon={RefreshCw} onClick={() => loadStats()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </div>
      <SensorSnapshotTable sensors={sensors} openingSensors={openingSensors} />
    </section>
  );
}


function WindowGuardPanel({ guard, setToast, refresh }) {
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const values = draft || guard || {};
  async function save() {
    setSaving(true);
    try {
      await api("/api/climate/gree/window-guard", { method: "POST", body: JSON.stringify({
        open_delay_seconds: Number(values.open_delay_seconds), close_delay_seconds: Number(values.close_delay_seconds),
      }) });
      await refresh();
      setDraft(null);
      setToast("Ablakfigyelés késleltetései elmentve");
    } catch (err) { setToast(err.message); }
    finally { setSaving(false); }
  }
  return <article className="panel">
    <div className="panel-head"><h2>Klíma ablakfigyelés</h2><span>{!guard ? "Állapot betöltése…" : guard.blocked ? "Ablak miatt tiltva" : guard.suspended ? "Visszaindításra vár" : "Klíma engedélyezve"}</span></div>
    {guard?.blockers?.length > 0 && <p>{guard.blockers.map(row => `${row.label}${row.unknown ? " (ismeretlen / nem elérhető)" : " (nyitva)"}`).join(", ")}</p>}
    {guard?.open_remaining_seconds > 0 && <p>Leállításig: kb. {guard.open_remaining_seconds} mp. Új indítás már tiltva.</p>}
    {guard?.close_remaining_seconds > 0 && <p>Ablakzárás utáni várakozás: kb. {guard.close_remaining_seconds} mp.</p>}
    {guard?.exempt?.length > 0 && <p>Elszívó miatti ablak-kivétel: {guard.exempt.join(", ")}</p>}
    <p>Csak a klíma releváns érzékelők számítanak. Az elsődleges légutánpótlási ablak működő elszívónál kivétel. Ismeretlen szenzorállapot tiltja az indítást.</p>
    <div className="form-grid">
      <label>Nyitás utáni leállítás (másodperc)<input type="number" min="0" max="3600" step="1" value={values.open_delay_seconds ?? 60} onChange={e => setDraft({ ...values, open_delay_seconds: e.target.value })} /></label>
      <label>Zárás utáni visszaindítás (másodperc)<input type="number" min="0" max="3600" step="1" value={values.close_delay_seconds ?? 60} onChange={e => setDraft({ ...values, close_delay_seconds: e.target.value })} /></label>
    </div>
    <button onClick={save} disabled={saving || !guard}>{saving ? "Mentés…" : "Késleltetések mentése"}</button>
  </article>;
}
