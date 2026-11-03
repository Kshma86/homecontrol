import { useEffect, useState } from "react";
import { Activity, Clock, Cpu, Database, Gauge, HardDrive, Radio, RefreshCw, Server, Thermometer } from "lucide-react";
import { ResourceUsageChart, StatBarChart, TimeLineChart } from "../../chartPrimitives";
import { useContextRefresh } from "../../apiClient";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { boolText, byteText, dateText, metricNumber, numberText, statusTone, unitValue } from "../../formatters";
import { fetchPerformanceContext } from "./performanceApi";
import { appendResourceHistory } from "./performanceState";

function performanceEntityName(name) {
  const labels = {
    "Nyestriasztó": "Marten Deterrent",
  };
  return labels[name] || name;
}

export default function Performance() {
  const [perf, setPerf] = useState(null);
  const [clientResponseMs, setClientResponseMs] = useState(null);
  const [resourceHistory, setResourceHistory] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadPerformance() {
    setLoading(true);
    setError("");
    const started = performance.now();
    try {
      const data = await fetchPerformanceContext();
      setClientResponseMs(performance.now() - started);
      setPerf(data);
      setResourceHistory((current) => appendResourceHistory(current, data));
    } catch (err) {
      setClientResponseMs(performance.now() - started);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPerformance();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") loadPerformance();
    }, 60000);
    return () => window.clearInterval(id);
  }, []);

  useContextRefresh(["/api/context/performance"], (payload) => {
    setPerf(payload);
    setLoading(false);
    setResourceHistory((current) => appendResourceHistory(current, payload));
  });

  if (loading && !perf) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading performance...</span>
      </section>
    );
  }

  const cpu = perf?.cpu || {};
  const memory = perf?.memory || {};
  const postgres = perf?.postgres || {};
  const mqtt = perf?.mqtt || {};
  const apiLog = perf?.api_log || {};
  const slowEndpoints = apiLog.slow_endpoints || [];
  const summary = perf?.summary || {};
  const dockerContainers = perf?.docker?.containers || [];
  const dockerByCpu = dockerContainers
    .slice()
    .sort((a, b) => (metricNumber(b, "cpu_percent") || 0) - (metricNumber(a, "cpu_percent") || 0));
  const topContainer = dockerByCpu[0] || null;
  const heartbeats = perf?.heartbeats || [];
  const workers = perf?.workers || [];
  const staleHeartbeats = heartbeats.filter((item) => item.status !== "online").length;
  const clientMs = clientResponseMs === null ? null : Math.round(clientResponseMs);
  const serverPower = perf?.server_power || {};
  const serverPowerSummary = serverPower.summary || {};
  const serverPowerDevice = serverPower.device || {};
  const serverPowerRows = serverPower.power_24h || [];
  const serverPowerDailyRows = serverPower.daily_30d || [];
  const serverPowerDailyWhRows = serverPowerDailyRows.map((row) => ({ ...row, energy_wh: (metricNumber(row, "energy_kwh") || 0) * 1000 }));
  const serverPowerTitle = serverPowerDevice.display_name || serverPowerDevice.entity_name || "HC szerver";
  const aiServerPower = serverPower.ai_server || {};
  const aiServerPowerSummary = aiServerPower.summary || {};
  const aiServerPowerRows = aiServerPower.power_24h || [];
  const aiServerPowerDailyWhRows = (aiServerPower.daily_30d || []).map((row) => ({ ...row, energy_wh: (metricNumber(row, "energy_kwh") || 0) * 1000 }));
  const aiServerPowerTitle = aiServerPower.device?.display_name || aiServerPower.device?.entity_name || "AI szerver";
  const hardwareSensors = perf?.hardware_sensors || {};
  const hardwareTemperatureHistory = hardwareSensors.history_24h || [];
  const cpuTemperatureValues = hardwareTemperatureHistory.map((row) => metricNumber(row, "cpu_temperature_c")).filter((value) => value !== null);
  const chipsetTemperatureValues = hardwareTemperatureHistory.map((row) => metricNumber(row, "chipset_temperature_c")).filter((value) => value !== null);
  const avgCpuTemperature = cpuTemperatureValues.length ? cpuTemperatureValues.reduce((sum, value) => sum + value, 0) / cpuTemperatureValues.length : null;
  const avgChipsetTemperature = chipsetTemperatureValues.length ? chipsetTemperatureValues.reduce((sum, value) => sum + value, 0) / chipsetTemperatureValues.length : null;

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Performance</h2>
          <span>{error || `Updated ${dateText(perf?.generated_at)} | auto refresh 30s`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadPerformance} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid performance-tiles">
        <Card
          title="CPU"
          value={unitValue(cpu.percent, "%", 1)}
          meta={cpu.ok ? "host/container view" : cpu.error || "unavailable"}
          tone={cpu.ok && cpu.percent >= 85 ? "warn" : ""}
          icon={Cpu}
        />
        <Card
          title="RAM"
          value={unitValue(memory.percent, "%", 1)}
          meta={`${byteText(memory.used_bytes)} / ${byteText(memory.total_bytes)}`}
          tone={memory.ok && memory.percent >= 85 ? "warn" : ""}
          icon={HardDrive}
        />
        <Card
          title="Top Container"
          value={topContainer ? unitValue(topContainer.cpu_percent, "%", 1) : "-"}
          meta={topContainer?.name || "no container stats"}
          tone={topContainer && metricNumber(topContainer, "cpu_percent") >= 80 ? "warn" : ""}
          icon={Server}
        />
        <Card
          title="PostgreSQL"
          value={postgres.ok ? `${postgres.total ?? "-"} conn` : "Offline"}
          meta={postgres.ok ? `${postgres.active ?? 0} active | ${postgres.idle ?? 0} idle | max ${postgres.max ?? "-"}` : postgres.error}
          tone={postgres.ok ? "" : "bad"}
          icon={Database}
        />
        <Card
          title="MQTT"
          value={mqtt.connected ? "Connected" : "Disconnected"}
          meta={mqtt.connected ? `${mqtt.broker?.host || "-"}:${mqtt.broker?.port || "-"}` : mqtt.last_error || "broker unavailable"}
          tone={mqtt.connected ? "" : "bad"}
          icon={Radio}
        />
        <Card
          title="API Response"
          value={clientMs === null ? "-" : `${clientMs} ms`}
          meta={`server ${numberText(perf?.api?.response_ms, 1)} ms | db ${numberText(perf?.api?.db_response_ms, 1)} ms`}
          tone={clientMs !== null && clientMs > 1000 ? "warn" : ""}
          icon={Gauge}
        />
      </section>

      <section className="grid two">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Thermometer size={17} aria-hidden="true" /> CPU Temperature / 24h</h2>
            <span>
              {hardwareSensors.ok === false
                ? "no hardware sensors visible"
                : `${unitValue(hardwareSensors.cpu_temperature_c, "C", 1)} now | avg ${unitValue(avgCpuTemperature, "C", 1)} | ${hardwareSensors.summary?.history_samples || hardwareTemperatureHistory.length} samples`}
            </span>
          </div>
          <TimeLineChart rows={hardwareTemperatureHistory} valueKey="cpu_temperature_c" unit="C" digits={1} color="red" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Thermometer size={17} aria-hidden="true" /> Chipset Temperature / 24h</h2>
            <span>
              {hardwareSensors.ok === false
                ? "no hardware sensors visible"
                : `${unitValue(hardwareSensors.chipset_temperature_c, "C", 1)} now | avg ${unitValue(avgChipsetTemperature, "C", 1)} | ${hardwareSensors.chipset_sensor_name || "chipset"}`}
            </span>
          </div>
          <TimeLineChart rows={hardwareTemperatureHistory} valueKey="chipset_temperature_c" unit="C" digits={1} color="blue" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>{serverPowerTitle} Power / 24h</h2>
            <span>
              {serverPower.ok === false
                ? serverPower.error || "plug unavailable"
                : `${unitValue(serverPowerSummary.current_power_w, "W", 0)} now | avg ${unitValue(serverPowerSummary.avg_power_w_24h, "W", 1)} | max ${unitValue(serverPowerSummary.max_power_w, "W", 0)} | ${serverPowerSummary.power_samples || serverPowerRows.length} samples`}
            </span>
          </div>
          <TimeLineChart rows={serverPowerRows} valueKey="power_w" unit="W" digits={0} color="blue" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Daily {serverPowerTitle} Use</h2>
            <span>
              {serverPower.ok === false
                ? serverPower.error || "plug unavailable"
                : `${unitValue((metricNumber(serverPowerSummary, "today_energy_kwh") || 0) * 1000, "Wh", 0)} today`}
            </span>
          </div>
          <StatBarChart rows={serverPowerDailyWhRows} valueKey="energy_wh" unit="Wh" digits={0} color="green" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>{aiServerPowerTitle} Power / 24h</h2>
            <span>{aiServerPower.ok === false ? aiServerPower.error || "plug unavailable" : `${unitValue(aiServerPowerSummary.current_power_w, "W", 0)} now | avg ${unitValue(aiServerPowerSummary.avg_power_w_24h, "W", 1)} | max ${unitValue(aiServerPowerSummary.max_power_w, "W", 0)}`}</span>
          </div>
          <TimeLineChart rows={aiServerPowerRows} valueKey="power_w" unit="W" digits={0} color="yellow" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Daily {aiServerPowerTitle} Use</h2>
            <span>{aiServerPower.ok === false ? aiServerPower.error || "plug unavailable" : `${unitValue((metricNumber(aiServerPowerSummary, "today_energy_kwh") || 0) * 1000, "Wh", 0)} today`}</span>
          </div>
          <StatBarChart rows={aiServerPowerDailyWhRows} valueKey="energy_wh" unit="Wh" digits={0} color="yellow" />
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> API Request Log</h2>
          <span>
            {apiLog.sample_count || 0} samples | {apiLog.endpoint_count || 0} endpoints | {unitValue((apiLog.window_sec || 0) / 3600, "h", 1)} window
          </span>
        </div>
        <Table
          rows={slowEndpoints}
          columns={[
            {
              key: "route",
              label: "Endpoint",
              render: (row) => (
                <span className="inline-endpoint">
                  <strong>{row.method || "-"}</strong>
                  <code>{row.route || row.path || "-"}</code>
                </span>
              ),
            },
            { key: "count", label: "Count" },
            { key: "avg_ms", label: "Avg", render: (row) => unitValue(row.avg_ms, "ms", 1) },
            { key: "p95_ms", label: "P95", render: (row) => unitValue(row.p95_ms, "ms", 1) },
            { key: "max_ms", label: "Max", render: (row) => unitValue(row.max_ms, "ms", 1) },
            { key: "last_ms", label: "Last", render: (row) => unitValue(row.last_ms, "ms", 1) },
            {
              key: "last_status",
              label: "Status",
              render: (row) => {
                const status = Number(row.last_status);
                return <span className={`status-pill ${statusTone(status > 0 && status < 400, status >= 400 && status < 500)}`}>{row.last_status || "-"}</span>;
              },
            },
            { key: "last_seen", label: "Seen", render: (row) => dateText(row.last_seen) },
          ]}
        />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Clock size={17} aria-hidden="true" /> Device Heartbeats</h2>
            <span>{heartbeats.length} device/entity | {staleHeartbeats} not online</span>
          </div>
          <Table
            rows={heartbeats}
            columns={[
              { key: "entity_name", label: "Entity", render: (row) => performanceEntityName(row.entity_name) },
              { key: "device_name", label: "Device" },
              { key: "platform", label: "Platform" },
              { key: "status", label: "Status", render: (row) => <span className={`status-pill ${statusTone(row.status === "online", row.status !== "offline")}`}>{row.status || "unknown"}</span> },
              { key: "last_seen_ts", label: "Last heartbeat", render: (row) => dateText(row.last_seen_ts) },
              { key: "age_sec", label: "Age", render: (row) => row.age_sec === null || row.age_sec === undefined ? "-" : `${row.age_sec} s` },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Server size={17} aria-hidden="true" /> Docker Containers</h2>
            <span>{perf?.docker?.ok ? `${summary.docker_running || 0}/${summary.docker_total || 0} running` : perf?.docker?.error || "unavailable"}</span>
          </div>
          <Table
            rows={dockerByCpu}
            columns={[
              { key: "name", label: "Name" },
              { key: "cpu_percent", label: "CPU", render: (row) => unitValue(row.cpu_percent, "%", 1) },
              { key: "memory_percent", label: "RAM", render: (row) => row.memory_usage ? row.memory_usage : `${byteText(row.memory_usage_bytes)} | ${unitValue(row.memory_percent, "%", 1)}` },
              { key: "pids", label: "PIDs", render: (row) => row.pids ?? "-" },
              { key: "network_io", label: "Net I/O", render: (row) => row.network_io || `${byteText(row.network_rx_bytes)} / ${byteText(row.network_tx_bytes)}` },
              { key: "block_io", label: "Block I/O", render: (row) => row.block_io || `${byteText(row.block_read_bytes)} / ${byteText(row.block_write_bytes)}` },
              { key: "state", label: "State", render: (row) => <span className={`status-pill ${statusTone(row.state === "running")}`}>{row.state || "-"}</span> },
              { key: "status", label: "Status" },
            ]}
          />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> Background Processes</h2>
            <span>{summary.workers_running || 0}/{summary.workers_total || workers.length} running | {perf?.thread_count || 0} threads</span>
          </div>
          <div className="worker-list">
            {workers.map((worker) => (
              <div className="worker-row" key={worker.key}>
                <div>
                  <strong>{worker.name}</strong>
                  <span>{worker.enabled ? "enabled" : "disabled"}</span>
                </div>
                <span className={`status-pill ${statusTone(worker.running, worker.enabled === false)}`}>{boolText(worker.running)}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> Resource Usage</h2>
            <span>{resourceHistory.length} samples | 30s refresh | 15 min window</span>
          </div>
          <ResourceUsageChart rows={resourceHistory} />
        </article>
      </section>
    </>
  );
}
