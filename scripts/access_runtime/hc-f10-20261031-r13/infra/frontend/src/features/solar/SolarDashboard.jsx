import React from "react";
import { Activity, Archive, BatteryCharging, CalendarDays, RefreshCw, Zap } from "lucide-react";
import { usePolledContext } from "../../apiClient";
import { StatBarChart, TimeLineChart } from "../../chartPrimitives";
import { dateText } from "../../formatters";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { solarMetricLabels, solarMetricText, solarStateValue } from "./solarMetrics";

export default function SolarDashboard() {
  const { data: state, loading, error, refresh: loadSolar } = usePolledContext("/api/context/solar", { intervalMs: 30000 });

  const values = state?.state || {};
  const summary = state?.summary || {};
  const entity = state?.entity || {};
  const stateRows = state?.state_rows || [];
  const measurementRows = state?.recent_measurements || [];
  const chartRows = state?.charts || {};
  const loadPower24h = chartRows.load_power_24h || [];
  const productionDaily30d = chartRows.production_daily_30d || [];
  const updatedAt = summary.updated_at || entity.last_seen_ts || entity.presence_updated_at;
  const inverterOutput = solarStateValue(values, "output_power_w");
  const plantOutput = solarStateValue(values, "plant_output_power_w");
  const todayEnergy = solarStateValue(values, "plant_energy_today_kwh") ?? solarStateValue(values, "energy_today_kwh");
  const lifetimeEnergy = solarStateValue(values, "plant_lifetime_energy_kwh") ?? solarStateValue(values, "lifetime_energy_kwh");
  const monthProduction = summary.production_month_kwh ?? null;
  const status = summary.status || entity.status || "unknown";
  const flowRows = [
    ["PV1", "input_1_wattage_w", "input_1_voltage_v", "input_1_current_a"],
    ["PV2", "input_2_wattage_w", "input_2_voltage_v", "input_2_current_a"],
    ["Grid", "export_power_w", "import_power_w", "ac_frequency_hz"],
    ["Load", "local_load_power_w", "load_consumption_today_kwh", "lifetime_load_consumption_kwh"],
  ].map(([name, a, b, c]) => ({
    name,
    a_key: a,
    a: solarMetricText(solarStateValue(values, a), a),
    b_key: b,
    b: solarMetricText(solarStateValue(values, b), b),
    c_key: c,
    c: solarMetricText(solarStateValue(values, c), c),
  }));

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading solar...</span>
      </section>
    );
  }

  return (
    <>
      <section className="stats-head solar-head">
        <div>
          <h2>{entity.entity_name || "Growatt Solar"}</h2>
          <span>{error || `${entity.topic_base || "homecontrol/tele/growatt/cloud"} | ${status} | updated ${dateText(updatedAt)}`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={() => loadSolar()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles solar-summary">
        <Card title="Inverter Output" value={solarMetricText(inverterOutput, "output_power_w")} meta={`plant ${solarMetricText(plantOutput, "plant_output_power_w")}`} icon={Zap} tone={Number(inverterOutput || 0) > 0 ? "" : "warn"} />
        <Card title="Today" value={solarMetricText(todayEnergy, "plant_energy_today_kwh")} meta={`inverter ${solarMetricText(solarStateValue(values, "energy_today_kwh"), "energy_today_kwh")}`} icon={BatteryCharging} />
        <Card title="This Month" value={solarMetricText(monthProduction, "energy_today_kwh")} meta={`${summary.production_month_days || 0} days`} icon={CalendarDays} />
        <Card title="Lifetime" value={solarMetricText(lifetimeEnergy, "plant_lifetime_energy_kwh")} meta={solarMetricText(solarStateValue(values, "lifetime_solar_energy_kwh"), "lifetime_solar_energy_kwh")} icon={Archive} />
      </section>

      <section className="grid two solar-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Consumption 24h</h2>
            <span>{loadPower24h.reduce((sum, row) => sum + Number(row.sample_count || 0), 0)} samples | hourly average</span>
          </div>
          <TimeLineChart rows={loadPower24h} valueKey="avg_load_power_w" unit="W" digits={0} color="blue" />
        </article>
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Daily Production</h2>
            <span>{productionDaily30d.length} days | monthly view</span>
          </div>
          <StatBarChart rows={productionDaily30d} valueKey="production_kwh" unit="kWh" digits={1} color="yellow" />
        </article>
      </section>

      <section className="grid solar-grid">
        <article className="panel">
          <div className="panel-head">
            <h2>Solar Flow</h2>
            <span>{summary.state_count || stateRows.length} current metrics</span>
          </div>
          <Table
            rows={flowRows}
            columns={[
              { key: "name", label: "Area" },
              { key: "a", label: "Primary" },
              { key: "b", label: "Secondary" },
              { key: "c", label: "Tertiary" },
            ]}
          />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Current Solar State</h2>
            <span>{stateRows.length} rows</span>
          </div>
          <Table
            rows={stateRows.map((row, index) => ({ ...row, id: `${row.key}-${index}` }))}
            columns={[
              { key: "key", label: "Metric", render: (row) => solarMetricLabels[row.key]?.[0] || row.key },
              { key: "value", label: "Value", render: (row) => solarMetricText(row.v_num ?? row.v_text ?? row.v_json, row.key) },
              { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Recent Measurements</h2>
            <span>{summary.measurement_count_24h || 0} samples in 24h</span>
          </div>
          <Table
            rows={measurementRows.map((row, index) => ({ ...row, id: `${row.key}-${index}` }))}
            columns={[
              { key: "key", label: "Metric", render: (row) => solarMetricLabels[row.key]?.[0] || row.key },
              { key: "sample_count", label: "Samples" },
              { key: "avg_num", label: "Avg", render: (row) => solarMetricText(row.avg_num, row.key) },
              { key: "max_num", label: "Max", render: (row) => solarMetricText(row.max_num, row.key) },
              { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
            ]}
          />
        </article>
      </section>
    </>
  );
}
