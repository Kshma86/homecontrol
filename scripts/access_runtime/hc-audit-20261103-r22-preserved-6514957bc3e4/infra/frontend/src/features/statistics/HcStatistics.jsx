import { useState } from "react";
import { Activity, Clock, Droplets, Gauge, RefreshCw } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { StatNormalizedMultiLineChart } from "../../chartPrimitives";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { dateText, displayEntityName, metricNumber, timestampLabel, unitValue } from "../../formatters";
import { SensorRangeSwitch, SensorSnapshotTable, roomDisplayName } from "../../houseSensors";

function openingStateText(contact) {
  if (contact === true) return "Closed";
  if (contact === false) return "Open";
  return "-";
}

function openingTypeText(type) {
  return type === "door" ? "Door" : "Window";
}

export default function HcStatistics() {
  const [chartRanges, setChartRanges] = useState({});
  const [customHours, setCustomHours] = useState({});
  const [customStats, setCustomStats] = useState({});
  const [openingFilters, setOpeningFilters] = useState({ room: "", opening: "", type: "", state: "" });
  const statsPath1h = "/api/homecontrol/statistics?range=1h";
  const statsPath24h = "/api/homecontrol/statistics?range=24h";
  const statsPath7d = "/api/homecontrol/statistics?range=7d";
  const { data: stats1h, loading: loading1h, error: error1h, refresh: loadStats1h } = usePolledContext(statsPath1h, {
    refreshPaths: [statsPath1h],
  });
  const { data: stats24h, loading: loading24h, error: error24h, refresh: loadStats24h } = usePolledContext(statsPath24h, {
    refreshPaths: [statsPath24h],
  });
  const { data: stats7d, loading: loading7d, error: error7d, refresh: loadStats7d } = usePolledContext(statsPath7d, {
    refreshPaths: [statsPath7d],
  });
  const statsByRange = { "1h": stats1h, "24h": stats24h, "7d": stats7d };
  const stats = stats24h || stats1h || stats7d || {};
  const loading = loading24h || (!stats24h && (loading1h || loading7d));
  const error = error24h || error1h || error7d;
  const openingHistoryRange = stats?.range || "24h";

  function loadStats() {
    loadStats1h(true);
    loadStats7d(true);
    return loadStats24h();
  }

  function setSensorRange(entityId, value) {
    setChartRanges((current) => ({ ...current, [entityId]: value }));
  }

  function sensorForRange(sensor, range) {
    if (String(range || "").startsWith("custom:")) {
      const customSensor = customStats[range]?.temp_humidity_sensors?.find((item) => item.entity_id === sensor.entity_id);
      return customSensor || sensor;
    }
    const rangeSensors = statsByRange[range]?.temp_humidity_sensors || [];
    return rangeSensors.find((item) => item.entity_id === sensor.entity_id) || sensor;
  }

  async function applyCustomHours(entityId) {
    const hours = Math.max(1, Math.min(Number.parseInt(customHours[entityId], 10) || 0, 720));
    if (!hours) return;
    const range = `custom:${hours}`;
    if (!customStats[range]) {
      const payload = await api(`/api/homecontrol/statistics?hours=${hours}`);
      setCustomStats((current) => ({ ...current, [range]: payload }));
    }
    setSensorRange(entityId, range);
    setCustomHours((current) => ({ ...current, [entityId]: String(hours) }));
  }

  if (loading && !stats) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading HC statistics...</span>
      </section>
    );
  }

  const sensors = stats?.temp_humidity_sensors || [];
  const openingSensors = stats?.opening_sensors || [];
  const openingEvents = stats?.opening_events || [];
  const openingFilterOptions = {
    rooms: [...new Set(openingEvents.map((row) => roomDisplayName(row.location)).filter(Boolean))].sort((a, b) => a.localeCompare(b, "hu")),
    openings: [...new Set(openingEvents.map((row) => row.opening_label || displayEntityName(row.entity_name)).filter(Boolean))].sort((a, b) => a.localeCompare(b, "hu")),
  };
  const filteredOpeningEvents = openingEvents.filter((row) => {
    const room = roomDisplayName(row.location);
    const opening = row.opening_label || displayEntityName(row.entity_name);
    return (!openingFilters.room || room === openingFilters.room)
      && (!openingFilters.opening || opening === openingFilters.opening)
      && (!openingFilters.type || openingTypeText(row.opening_type) === openingFilters.type)
      && (!openingFilters.state || openingStateText(row.contact) === openingFilters.state);
  });
  const openingFilterActive = Object.values(openingFilters).some(Boolean);
  const indoorSensors = sensors.filter((sensor) => !sensor.is_outdoor);
  const tempValues = indoorSensors.map((sensor) => metricNumber(sensor, "latest_temperature")).filter((value) => value !== null);
  const humidityValues = indoorSensors.map((sensor) => metricNumber(sensor, "latest_humidity")).filter((value) => value !== null);
  const avgTemp = tempValues.length ? tempValues.reduce((sum, value) => sum + value, 0) / tempValues.length : null;
  const avgHumidity = humidityValues.length ? humidityValues.reduce((sum, value) => sum + value, 0) / humidityValues.length : null;

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>HomeControl Statistics</h2>
          <span>{error || `${sensors.length} temp/humidity sensors | per-chart ranges`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadStats} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles">
        <Card title="Sensors" value={sensors.length} meta="temperature / humidity" icon={Activity} />
        <Card title="Indoor Avg Temp" value={unitValue(avgTemp, "C", 1)} meta={`${indoorSensors.length} indoor sensors`} icon={Gauge} />
        <Card title="Indoor Avg Humidity" value={unitValue(avgHumidity, "%", 0)} meta={`${indoorSensors.length} indoor sensors`} icon={Droplets} />
        <Card title="Last Update" value={sensors[0] ? timestampLabel(sensors.reduce((latest, sensor) => new Date(sensor.latest_ts) > new Date(latest.latest_ts) ? sensor : latest, sensors[0]).latest_ts) : "-"} meta="newest sample" icon={Clock} />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Sensor Snapshot</h2>
          <span>Latest temperature, relative humidity, pressure and absolute humidity</span>
        </div>
        <SensorSnapshotTable sensors={sensors} openingSensors={openingSensors} />
      </section>

      <section className="sensor-grid">
        {sensors.map((sensor) => {
          const range = chartRanges[sensor.entity_id] || "24h";
          const chartSensor = sensorForRange(sensor, range);
          const rangeLabel = range.startsWith("custom:") ? `${range.slice("custom:".length)}h` : range;
          return (
            <article className="panel sensor-panel" key={sensor.entity_id}>
              <div className="panel-head">
                <div>
                  <h2>{displayEntityName(sensor.entity_name)}</h2>
                  <span>{unitValue(sensor.latest_temperature, "C", 1)} | {unitValue(sensor.latest_humidity, "%", 0)} | {unitValue(sensor.latest_pressure_hpa, "hPa", 1)} | {unitValue(sensor.latest_absolute_humidity_g_m3, "g/m3", 1)} | {timestampLabel(sensor.latest_ts)}</span>
                </div>
                <SensorRangeSwitch
                  value={rangeLabel}
                  onChange={(value) => setSensorRange(sensor.entity_id, value)}
                  label={`${sensor.entity_name} chart range`}
                  customHours={customHours[sensor.entity_id] || ""}
                  onCustomHoursChange={(value) => setCustomHours((current) => ({ ...current, [sensor.entity_id]: value }))}
                  onCustomApply={() => applyCustomHours(sensor.entity_id)}
                />
              </div>
              <div className="mini-chart-title">Climate Trend</div>
              <StatNormalizedMultiLineChart
                rows={chartSensor.samples}
                height={190}
                series={[
                  { key: "temperature", label: "Temp", unit: "C", digits: 1, color: "red" },
                  { key: "humidity", label: "RH", unit: "%", digits: 0, color: "blue" },
                  { key: "pressure_hpa", label: "hPa", unit: "hPa", digits: 1, color: "yellow" },
                  { key: "absolute_humidity_g_m3", label: "Abs", unit: "g/m3", digits: 1, color: "green" },
                ]}
              />
            </article>
          );
        })}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Opening History</h2>
          <span>{filteredOpeningEvents.length} / {openingEvents.length} events | {openingHistoryRange}</span>
        </div>
        <div className="opening-history-filters">
          <label>
            Room
            <select value={openingFilters.room} onChange={(event) => setOpeningFilters((current) => ({ ...current, room: event.target.value }))}>
              <option value="">All rooms</option>
              {openingFilterOptions.rooms.map((room) => <option value={room} key={room}>{room}</option>)}
            </select>
          </label>
          <label>
            Opening
            <select value={openingFilters.opening} onChange={(event) => setOpeningFilters((current) => ({ ...current, opening: event.target.value }))}>
              <option value="">All openings</option>
              {openingFilterOptions.openings.map((opening) => <option value={opening} key={opening}>{opening}</option>)}
            </select>
          </label>
          <label>
            Type
            <select value={openingFilters.type} onChange={(event) => setOpeningFilters((current) => ({ ...current, type: event.target.value }))}>
              <option value="">All types</option>
              <option value="Window">Window</option>
              <option value="Door">Door</option>
            </select>
          </label>
          <label>
            State
            <select value={openingFilters.state} onChange={(event) => setOpeningFilters((current) => ({ ...current, state: event.target.value }))}>
              <option value="">All states</option>
              <option value="Open">Open</option>
              <option value="Closed">Closed</option>
            </select>
          </label>
          <button type="button" className="secondary" disabled={!openingFilterActive} onClick={() => setOpeningFilters({ room: "", opening: "", type: "", state: "" })}>Clear filters</button>
        </div>
        <Table
          rows={filteredOpeningEvents}
          columns={[
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
            { key: "location", label: "Room", render: (row) => roomDisplayName(row.location) },
            { key: "opening", label: "Opening", render: (row) => row.opening_label || displayEntityName(row.entity_name) },
            { key: "opening_type", label: "Type", render: (row) => openingTypeText(row.opening_type) },
            { key: "contact", label: "State", render: (row) => openingStateText(row.contact) },
          ]}
        />
      </section>
    </>
  );
}
