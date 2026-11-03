import React, { useState } from "react";
import { Activity, BatteryCharging, Clock, Droplets, Gauge, RefreshCw } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { StatBarChart, StatLineChart, StatNormalizedMultiLineChart, TimeLineChart } from "../../chartPrimitives";
import { dayLabel, dateText, metricNumber, shortValue, timestampLabel, unitValue } from "../../formatters";
import { SensorRangeSwitch } from "../../houseSensors";
import { Card, IconButton, Table } from "../../uiPrimitives";
import IrrigationDiagnostics from "./IrrigationDiagnostics";
import { PilotHistory } from "./PilotDashboard";

function numericTrendSummary(rows = [], key, { unit = "", digits = 1, deadband = 0, activeMin = null } = {}) {
  const values = rows
    .map((row) => ({ ...row, value: metricNumber(row, key) }))
    .filter((row) => row.value !== null && (activeMin === null || row.value >= activeMin));
  if (values.length < 2) return "trend pending";
  const windowSize = Math.min(8, Math.max(2, Math.floor(values.length / 3)));
  const firstRows = values.slice(0, windowSize);
  const lastRows = values.slice(-windowSize);
  const avg = (items) => items.reduce((sum, row) => sum + row.value, 0) / items.length;
  const firstAvg = avg(firstRows);
  const lastAvg = avg(lastRows);
  const delta = lastAvg - firstAvg;
  const direction = Math.abs(delta) <= deadband ? "stable" : delta > 0 ? "rising" : "falling";
  const shownDelta = direction === "stable" ? Math.abs(delta) : delta;
  const sign = direction === "rising" ? "+" : "";
  return direction + " " + sign + unitValue(shownDelta, unit, digits);
}

export default function IrrigationStatistics() {
  const statsPath1h = "/api/irrigation/statistics?range=1h";
  const statsPath24h = "/api/irrigation/statistics?range=24h";
  const statsPath7d = "/api/irrigation/statistics?range=7d";
  const { data: stats1h = null, loading: loading1h, error: error1h, refresh: loadStats1h } = usePolledContext(statsPath1h);
  const { data: statsPayload = null, loading: loading24h, error: error24h, refresh: loadStats24h } = usePolledContext(statsPath24h);
  const { data: stats7d = null, loading: loading7d, error: error7d, refresh: loadStats7d } = usePolledContext(statsPath7d);
  const [customHours, setCustomHours] = useState({});
  const [customStats, setCustomStats] = useState({});
  const [moistureWindows, setMoistureWindows] = useState(["24h", "24h"]);
  const [pressureWindow, setPressureWindow] = useState("24h");
  const [tankWindow, setTankWindow] = useState("7d");
  const [batteryVoltageWindow, setBatteryVoltageWindow] = useState("24h");
  const statsByRange = { "1h": stats1h, "24h": statsPayload, "7d": stats7d };
  const stats = statsPayload || stats1h || stats7d || {};
  const loading = loading24h || (!statsPayload && (loading1h || loading7d));
  const error = error24h || error1h || error7d;

  function loadStats() {
    loadStats1h(true);
    loadStats7d(true);
    return loadStats24h();
  }

  function statsForRange(range) {
    if (String(range || "").startsWith("custom:")) return customStats[range] || stats;
    return statsByRange[range] || stats;
  }

  function rangeLabel(range) {
    return String(range || "").startsWith("custom:") ? `${String(range).slice("custom:".length)}h` : range;
  }

  async function applyCustomWindow(key, setValue) {
    const hours = Math.max(1, Math.min(Number.parseInt(customHours[key], 10) || 0, 720));
    if (!hours) return;
    const range = `custom:${hours}`;
    if (!customStats[range]) {
      const payload = await api(`/api/irrigation/statistics?hours=${hours}`);
      setCustomStats((current) => ({ ...current, [range]: payload }));
    }
    setValue(range);
    setCustomHours((current) => ({ ...current, [key]: String(hours) }));
  }

  if (loading && !statsPayload) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading statistics...</span>
      </section>
    );
  }

  const pressureStats = statsForRange(pressureWindow);
  const tankStats = statsForRange(tankWindow);
  const batteryVoltageStats = statsForRange(batteryVoltageWindow);
  const tank24 = tankStats?.tank_24h || [];
  const tankFilteredSpikes = Number(tankStats?.tank_filtered_spikes || 0);
  const batteryVoltageRows = batteryVoltageStats?.battery_voltage_24h || [];
  const batteryVoltageWindowLabel = rangeLabel(batteryVoltageWindow);
  const tankDaily = stats?.tank_daily || [];
  const allSoilMoisture24h = stats?.soil_moisture_24h || [];
  const findMoistureSensor = (sensors, suffix) => sensors.find((sensor) => {
    const text = `${sensor.entity_name || ""} ${sensor.device_name || ""} ${sensor.topic_base || ""}`.toLowerCase();
    return text.includes(`moisture_${suffix}`) || text.includes(`moisture ${suffix}`) || text.includes(`_${suffix}`) || text.endsWith(suffix);
  });
  const soilMoisture24h = [
    findMoistureSensor(allSoilMoisture24h, "02"),
    findMoistureSensor(allSoilMoisture24h, "03"),
  ].filter(Boolean);
  const soilMoistureSensors = soilMoisture24h;
  const pumpDaily = stats?.pump_daily || [];
  const solarDaily = stats?.solar_daily || [];
  const pressureComparison24h = pressureStats?.pressure_comparison_24h || [];
  const sessions = stats?.sessions || [];
  const solarPump = stats?.solar_pump_scheduler || {};
  const solarPumpRuns = solarPump.runs || [];
  const latestTank = [...tank24].reverse().find((row) => metricNumber(row, "level_percent") !== null);
  const latestBatteryVoltage = [...batteryVoltageRows].reverse().find((row) => metricNumber(row, "battery_voltage_v") !== null);
  const todayPump = pumpDaily[0] || {};
  const todaySolar = solarDaily[0] || {};
  const latestSession = sessions[0] || null;
  const latestLocalPressure = [...pressureComparison24h].reverse().find((row) => metricNumber(row, "local_pressure_hpa") !== null);
  const latestOwmPressure = [...pressureComparison24h].reverse().find((row) => metricNumber(row, "openweather_pressure_hpa") !== null);
  const latestComparedPressure = [...pressureComparison24h].reverse().find((row) => metricNumber(row, "pressure_delta_hpa") !== null);
  const latestPressureDelta = metricNumber(latestComparedPressure, "pressure_delta_hpa");
  const latestTankDepth = metricNumber(latestTank, "depth_m");
  const latestTankDepthText = latestTankDepth === null ? "-" : unitValue(latestTankDepth * 100, "cm", 0);
  const batteryVoltageValues = batteryVoltageRows.map((row) => metricNumber(row, "battery_voltage_v")).filter((value) => value !== null);
  const maxBatteryVoltage = batteryVoltageValues.length ? Math.max(...batteryVoltageValues) : null;
  const batteryVoltageTrend = numericTrendSummary(batteryVoltageRows, "battery_voltage_v", { unit: "V", digits: 2, deadband: 0.05 });
  const soilMoistureMeta = (sensor, windowLabel = "24h") => {
    if (!sensor) return "No soil moisture sensor";
    if (!sensor.sample_count) {
      return sensor.latest_ts
        ? `No ${windowLabel} samples | last ${unitValue(sensor.latest_soil_moisture, "%", 0)} at ${timestampLabel(sensor.latest_ts)}`
        : `No ${windowLabel} samples`;
    }
    return `Latest ${unitValue(sensor.latest_soil_moisture, "%", 0)} | min ${unitValue(sensor.min_soil_moisture, "%", 0)} | max ${unitValue(sensor.max_soil_moisture, "%", 0)}`;
  };
  const renderRangeSwitch = (value, setValue, label = "Chart range", key = label) => (
    <SensorRangeSwitch
      value={rangeLabel(value)}
      onChange={setValue}
      label={label}
      customHours={customHours[key] || ""}
      onCustomHoursChange={(nextValue) => setCustomHours((current) => ({ ...current, [key]: nextValue }))}
      onCustomApply={() => applyCustomWindow(key, setValue)}
    />
  );
  const setMoistureWindowAt = (index, value) => {
    setMoistureWindows((current) => current.map((item, itemIndex) => itemIndex === index ? value : item));
  };

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Irrigation Statistics</h2>
          <span>{error || `${tank24.length} tank samples | ${soilMoistureSensors.reduce((sum, sensor) => sum + (sensor.sample_count || 0), 0)} soil samples | ${pumpDaily.length} pump days`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadStats} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles irrigation-stat-tiles">
        <Card title="Tank Now" value={unitValue(latestTank?.level_percent, "%", 0)} meta={latestTank ? `${latestTankDepthText} | ${timestampLabel(latestTank.ts)}` : "No 24h tank sample"} icon={Droplets} />
        <Card title="Pump Today" value={unitValue(todayPump.pump_running_minutes, "min", 0)} meta={`${unitValue(todayPump.watt_hours, "Wh", 1)} | ${unitValue(todayPump.amp_hours, "Ah", 2)}`} icon={Activity} />
        <Card title="Solar Today" value={unitValue(todaySolar.charge_amp_hours, "Ah", 2)} meta={`${unitValue(todaySolar.avg_battery_voltage_v, "V", 2)} avg bat | max ${unitValue(todaySolar.max_charge_current_a, "A", 1)}`} icon={BatteryCharging} />
        <Card title="Pressure Delta" value={unitValue(latestPressureDelta, "hPa", 1)} meta={`local ${unitValue(latestLocalPressure?.local_pressure_hpa, "hPa", 1)} | OWM ${unitValue(latestOwmPressure?.openweather_pressure_hpa, "hPa", 1)}`} icon={Gauge} />
        <Card title="Last Cycle" value={latestSession ? unitValue(latestSession.duration_minutes, "min", 1) : "-"} meta={latestSession ? `${latestSession.started_by || "-"} | ${dateText(latestSession.started_at)}` : "No sessions"} icon={Clock} />
      </section>

      <section className="grid two stats-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Tank Level, {rangeLabel(tankWindow)}</h2>
            <span>{latestTank ? `Latest ${unitValue(latestTank.level_percent, "%", 0)} at ${timestampLabel(latestTank.ts)}${tankFilteredSpikes ? ` | filtered ${tankFilteredSpikes}` : ""}` : "No data"}</span>
            {renderRangeSwitch(tankWindow, setTankWindow, "Tank chart range", "tank")}
          </div>
          <StatLineChart rows={tank24} yKey="level_percent" unit="%" digits={0} color="accent" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Pump Runtime / Day</h2>
            <span>{unitValue(todayPump.amp_hours, "Ah", 2)} today</span>
          </div>
          <StatBarChart rows={pumpDaily} valueKey="pump_running_minutes" unit="min" digits={0} color="accent" />
        </article>
      </section>

      <section className="grid two stats-grid">
        {[0, 1].map((index) => {
          const windowValue = moistureWindows[index] || "24h";
          const windowLabel = rangeLabel(windowValue);
          const sensorsForWindow = statsForRange(windowValue)?.soil_moisture_24h || [];
          const sensor = sensorsForWindow[index];
          const label = sensor?.entity_name || sensor?.device_name || `Soil Moisture ${index + 1}`;
          return (
            <article className="panel chart-panel" key={sensor?.entity_id || `soil-moisture-${index}`}>
              <div className="panel-head">
                <h2>{label}, {windowLabel}</h2>
                <span>{soilMoistureMeta(sensor, windowLabel)}</span>
                {renderRangeSwitch(windowValue, (value) => setMoistureWindowAt(index, value), `${label} chart range`, `soil-${index}`)}
              </div>
              <TimeLineChart rows={sensor?.samples || []} valueKey="soil_moisture" unit="%" digits={0} color={index === 0 ? "green" : "blue"} yMin={0} yMax={100} smooth />
            </article>
          );
        })}
      </section>

      <section className="grid two stats-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Pump Consumption / Day</h2>
            <span>{unitValue(todayPump.amp_hours, "Ah", 2)} today</span>
          </div>
          <StatBarChart rows={pumpDaily} valueKey="amp_hours" unit="Ah" digits={2} color="blue" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Solar Charge / Day</h2>
            <span>{unitValue(todaySolar.charge_amp_hours, "Ah", 2)} today</span>
          </div>
          <StatBarChart rows={solarDaily} valueKey="charge_amp_hours" unit="Ah" digits={2} color="yellow" />
        </article>
      </section>

      <section className="grid two stats-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Battery Voltage, {batteryVoltageWindowLabel}</h2>
            <span>Latest {unitValue(latestBatteryVoltage?.battery_voltage_v, "V", 2)} | max {unitValue(maxBatteryVoltage, "V", 2)} | {batteryVoltageTrend}</span>
            {renderRangeSwitch(batteryVoltageWindow, setBatteryVoltageWindow, "Battery voltage chart range", "battery-voltage")}
          </div>
          <TimeLineChart rows={batteryVoltageRows} valueKey="battery_voltage_v" unit="V" digits={2} color="blue" yMin={0} smooth />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Pressure Sources, {rangeLabel(pressureWindow)}</h2>
            <span>Local {unitValue(latestLocalPressure?.local_pressure_hpa, "hPa", 1)} | OWM {unitValue(latestOwmPressure?.openweather_pressure_hpa, "hPa", 1)} | delta {unitValue(latestPressureDelta, "hPa", 1)}</span>
            {renderRangeSwitch(pressureWindow, setPressureWindow, "Pressure chart range", "pressure")}
          </div>
          <StatNormalizedMultiLineChart
            rows={pressureComparison24h}
            height={230}
            series={[
              { key: "local_pressure_hpa", label: "Local", unit: "hPa", digits: 1, color: "green" },
              { key: "openweather_pressure_hpa", label: "OWM", unit: "hPa", digits: 1, color: "blue" },
            ]}
          />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Daily Pump</h2>
            <span>Runtime and consumption</span>
          </div>
          <Table
            rows={pumpDaily}
            columns={[
              { key: "day", label: "Day", render: (row) => dayLabel(row.day) },
              { key: "pump_running_minutes", label: "Run min" },
              { key: "watt_hours", label: "Wh" },
              { key: "amp_hours", label: "Ah" },
              { key: "max_current_a", label: "Max A" },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Daily Solar</h2>
            <span>Charge current and battery voltage</span>
          </div>
          <Table
            rows={solarDaily}
            columns={[
              { key: "day", label: "Day", render: (row) => dayLabel(row.day) },
              { key: "charge_amp_hours", label: "Solar Ah" },
              { key: "avg_battery_voltage_v", label: "Avg bat V" },
              { key: "min_battery_voltage_v", label: "Min bat V" },
              { key: "max_charge_current_a", label: "Max chg A" },
            ]}
          />
          <div className="table-spacer" />
          <div className="panel-subhead">
            <h3>Daily Tank</h3>
            <span>Ultrasonic level summary</span>
          </div>
          <Table
            rows={tankDaily}
            columns={[
              { key: "day", label: "Day", render: (row) => dayLabel(row.day) },
              { key: "avg_level_percent", label: "Avg %" },
              { key: "min_level_percent", label: "Min %" },
              { key: "max_level_percent", label: "Max %" },
              { key: "avg_depth_m", label: "Avg depth m" },
            ]}
          />
          <div className="table-spacer" />
          <div className="panel-subhead">
            <h3>Solar Pump Runs</h3>
            <span>opportunistic batches</span>
          </div>
          <Table
            rows={solarPumpRuns}
            columns={[
              { key: "started_at", label: "Started", render: (row) => dateText(row.started_at) },
              { key: "duration_minutes", label: "Min" },
              { key: "status", label: "Status" },
              { key: "battery_voltage_v", label: "Bat V", render: (row) => unitValue(row.battery_voltage_v, "V", 2) },
              { key: "charge_current_a", label: "Chg A", render: (row) => unitValue(row.charge_current_a, "A", 2) },
              { key: "pv_voltage_v", label: "PV V", render: (row) => unitValue(row.pv_voltage_v, "V", 1) },
              { key: "tank_full_stop", label: "L/H", render: (row) => `${row.low_signal === true ? "1" : row.low_signal === false ? "0" : "-"} / ${row.high_signal === true ? "1" : row.high_signal === false ? "0" : "-"}` },
              { key: "decision_reason", label: "Reason", render: (row) => shortValue(row.decision_reason, 90) },
            ]}
          />
        </article>
      </section>

      <PilotHistory />
      <IrrigationDiagnostics />
    </>
  );
}
