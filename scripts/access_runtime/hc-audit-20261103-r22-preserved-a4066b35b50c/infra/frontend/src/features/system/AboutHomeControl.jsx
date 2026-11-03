import { useEffect, useState } from "react";
import { Activity, Archive, ClipboardList, Cpu, Database, Gauge, HardDrive, Radio, RefreshCw, Server } from "lucide-react";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { byteText, dateText, numberText, shortValue, unitValue, uptimeText } from "../../formatters";
import { fetchAbout } from "./systemInfoApi";
import { aboutViewModel } from "./documentationState";

export default function AboutHomeControl({ setToast }) {
  const [about, setAbout] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadAbout() {
    setLoading(true);
    try {
      setAbout(await fetchAbout());
    } catch (err) {
      setToast(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAbout();
  }, []);

  if (loading && !about) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading About...</span>
      </section>
    );
  }

  const {
    source,
    totals,
    devices,
    entities,
    docker,
    dockerSummary,
    modules,
    sensorTypes,
    metricTypes,
    containers,
    server,
    cpu,
    memory,
    diskRoot,
    database,
    relationSummary,
    measurement,
    dbConnections,
    topTables,
    metricActivity,
    schemaTables,
  } = aboutViewModel(about);
  const loadAvgText = Array.isArray(cpu.load_avg) && cpu.load_avg.length ? cpu.load_avg.map((value) => numberText(value, 2)).join(" / ") : "-";
  const cpuTypeText = [cpu.vendor, cpu.architecture].filter(Boolean).join(" | ") || "-";

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>HomeControl About</h2>
          <span>{about?.generated_at ? `Generated ${dateText(about.generated_at)} | ${numberText(about?.api?.response_ms, 1)} ms` : "Static inventory"}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadAbout} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles about-tiles">
        <Card title="Source Size" value={byteText(totals.bytes)} meta={`${numberText(totals.files, 0)} files`} icon={Archive} />
        <Card title="Program Lines" value={numberText(totals.lines, 0)} meta="source + config + docs" icon={ClipboardList} />
        <Card title="Modules" value={numberText(source.module_count, 0)} meta={source.root || "-"} icon={Database} />
        <Card title="Containers" value={numberText(dockerSummary.total, 0)} meta={`${numberText(dockerSummary.running, 0)} running`} icon={Server} tone={docker.ok === false ? "warn" : ""} />
        <Card title="Devices" value={numberText(devices.devices_active ?? devices.devices_total, 0)} meta={`${numberText(entities.entities_active ?? entities.entities_total, 0)} entities`} icon={Radio} />
        <Card title="Sensor Types" value={numberText(sensorTypes.length, 0)} meta={`${numberText(metricTypes.length, 0)} metric types`} icon={Gauge} />
        <Card title="CPU" value={unitValue(cpu.percent, "%", 1)} meta={`${cpu.model || "-"} | ${numberText(cpu.cores, 0)} cores`} icon={Cpu} tone={cpu.ok && cpu.percent >= 85 ? "warn" : ""} />
        <Card title="RAM" value={byteText(memory.total_bytes)} meta={`${byteText(memory.available_bytes)} free | ${unitValue(memory.percent, "%", 1)} used`} icon={HardDrive} tone={memory.ok && memory.percent >= 85 ? "warn" : ""} />
        <Card title="SSD Free" value={byteText(diskRoot.free_bytes)} meta={`${byteText(diskRoot.total_bytes)} total | ${unitValue(diskRoot.percent, "%", 1)} used`} icon={HardDrive} tone={diskRoot.ok && diskRoot.percent >= 85 ? "warn" : ""} />
        <Card title="Database" value={byteText(database.size_bytes)} meta={`${numberText(relationSummary.table_count ?? database.table_count, 0)} tables | ${numberText(database.index_count, 0)} indexes`} icon={Database} tone={database.ok === false ? "warn" : ""} />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>HC Server</h2>
            <span>{server.hostname || "-"} | uptime {uptimeText(server.uptime_sec)}</span>
          </div>
          <div className="about-fact-grid">
            <div><span>CPU model</span><strong>{cpu.model || "-"}</strong></div>
            <div><span>CPU type</span><strong>{cpuTypeText}</strong></div>
            <div><span>CPU cores</span><strong>{numberText(cpu.cores, 0)}</strong></div>
            <div><span>CPU MHz</span><strong>{unitValue(cpu.mhz, "MHz", 0)}</strong></div>
            <div><span>CPU cache</span><strong>{cpu.cache || "-"}</strong></div>
            <div><span>CPU family/model</span><strong>{[cpu.family, cpu.model_id, cpu.stepping].filter(Boolean).join(" / ") || "-"}</strong></div>
            <div><span>CPU flags</span><strong>{numberText(cpu.flags_count, 0)}</strong></div>
            <div><span>CPU load</span><strong>{loadAvgText}</strong></div>
            <div><span>CPU now</span><strong>{unitValue(cpu.percent, "%", 1)}</strong></div>
            <div><span>BogoMIPS</span><strong>{numberText(cpu.bogomips, 1)}</strong></div>
            <div><span>RAM total</span><strong>{byteText(memory.total_bytes)}</strong></div>
            <div><span>RAM free</span><strong>{byteText(memory.available_bytes)}</strong></div>
            <div><span>RAM used</span><strong>{byteText(memory.used_bytes)}</strong></div>
            <div><span>RAM usage</span><strong>{unitValue(memory.percent, "%", 1)}</strong></div>
            <div><span>SSD total</span><strong>{byteText(diskRoot.total_bytes)}</strong></div>
            <div><span>SSD free</span><strong>{byteText(diskRoot.free_bytes)}</strong></div>
            <div><span>SSD used</span><strong>{byteText(diskRoot.used_bytes)}</strong></div>
            <div><span>SSD usage</span><strong>{unitValue(diskRoot.percent, "%", 1)}</strong></div>
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Database Snapshot</h2>
            <span>{database.ok === false ? database.error || "unavailable" : `${numberText(database.response_ms, 1)} ms`}</span>
          </div>
          <div className="about-fact-grid">
            <div><span>Database</span><strong>{database.name || "-"}</strong></div>
            <div><span>PostgreSQL</span><strong>{database.server_version || "-"}</strong></div>
            <div><span>Encoding</span><strong>{database.encoding || "-"}</strong></div>
            <div><span>Timezone</span><strong>{database.timezone || "-"}</strong></div>
            <div><span>DB size</span><strong>{byteText(database.size_bytes)}</strong></div>
            <div><span>Schemas</span><strong>{numberText(database.schema_count, 0)}</strong></div>
            <div><span>HC tables</span><strong>{numberText(relationSummary.table_count ?? database.table_count, 0)}</strong></div>
            <div><span>Indexes</span><strong>{numberText(database.index_count, 0)}</strong></div>
            <div><span>Estimated rows</span><strong>{numberText(relationSummary.estimated_rows, 0)}</strong></div>
            <div><span>Measurement rows</span><strong>{numberText(measurement.row_estimate, 0)}</strong></div>
            <div><span>Samples 24h</span><strong>{numberText(measurement.samples_24h, 0)}</strong></div>
            <div><span>Active entities 24h</span><strong>{numberText(measurement.active_entities_24h, 0)}</strong></div>
            <div><span>Connections</span><strong>{database.ok === false ? "-" : `${numberText(dbConnections.total, 0)} / ${numberText(dbConnections.max, 0)}`}</strong></div>
            <div><span>Active / idle</span><strong>{`${numberText(dbConnections.active, 0)} / ${numberText(dbConnections.idle, 0)}`}</strong></div>
            <div><span>First sample</span><strong>{dateText(measurement.first_ts)}</strong></div>
            <div><span>Last sample</span><strong>{dateText(measurement.last_ts)}</strong></div>
          </div>
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Largest DB Tables</h2>
            <span>{byteText(relationSummary.total_bytes)} stored in hc schema</span>
          </div>
          <Table
            rows={topTables}
            columns={[
              { key: "name", label: "Table" },
              { key: "row_estimate", label: "Rows", render: (row) => numberText(row.row_estimate, 0) },
              { key: "total_bytes", label: "Total", render: (row) => byteText(row.total_bytes) },
              { key: "table_bytes", label: "Data", render: (row) => byteText(row.table_bytes) },
              { key: "index_bytes", label: "Index", render: (row) => byteText(row.index_bytes) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Metric Activity 24h</h2>
            <span>{numberText(measurement.metric_keys_24h, 0)} metric keys</span>
          </div>
          <Table
            rows={metricActivity}
            columns={[
              { key: "key", label: "Metric" },
              { key: "samples_24h", label: "Samples", render: (row) => numberText(row.samples_24h, 0) },
              { key: "entities_24h", label: "Entities", render: (row) => numberText(row.entities_24h, 0) },
              { key: "last_ts", label: "Latest", render: (row) => dateText(row.last_ts) },
            ]}
          />
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Database Structure</h2>
          <span>{numberText(schemaTables.length, 0)} hc tables</span>
        </div>
        <Table
          rows={schemaTables}
          columns={[
            { key: "name", label: "Table" },
            { key: "primary_key", label: "PK", render: (row) => row.primary_key || "-" },
            { key: "column_count", label: "Columns", render: (row) => numberText(row.column_count, 0) },
            { key: "foreign_key_count", label: "FKs", render: (row) => numberText(row.foreign_key_count, 0) },
            { key: "columns", label: "Structure", render: (row) => shortValue(row.columns, 260) },
          ]}
        />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Source Modules</h2>
            <span>{numberText(totals.lines, 0)} total lines</span>
          </div>
          <Table
            rows={modules}
            columns={[
              { key: "name", label: "Module" },
              { key: "path", label: "Path" },
              { key: "files", label: "Files", render: (row) => numberText(row.files, 0) },
              { key: "lines", label: "Lines", render: (row) => numberText(row.lines, 0) },
              { key: "bytes", label: "Size", render: (row) => byteText(row.bytes) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Sensor Types</h2>
            <span>{numberText(devices.devices_active, 0)} active devices</span>
          </div>
          <Table
            rows={sensorTypes}
            columns={[
              { key: "type", label: "Type" },
              { key: "capabilities", label: "What it does", render: (row) => (row.capabilities || []).join(", ") || "-" },
              { key: "examples", label: "Examples", render: (row) => row.examples || row.locations || "-" },
              { key: "platform", label: "Platform" },
              { key: "device_count", label: "Devices", render: (row) => numberText(row.device_count, 0) },
              { key: "entity_count", label: "Entities", render: (row) => numberText(row.entity_count, 0) },
              { key: "metrics", label: "Metrics", render: (row) => (row.metrics || []).slice(0, 6).join(", ") || "-" },
            ]}
          />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Metric Types</h2>
            <span>enabled entity metrics</span>
          </div>
          <Table
            rows={metricTypes}
            columns={[
              { key: "metric_key", label: "Metric" },
              { key: "entity_count", label: "Entities", render: (row) => numberText(row.entity_count, 0) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Containers</h2>
            <span>{docker.ok === false ? docker.error || "Docker unavailable" : `${numberText(dockerSummary.running, 0)} running`}</span>
          </div>
          <Table
            rows={containers}
            columns={[
              { key: "name", label: "Name" },
              { key: "image", label: "Image" },
              { key: "state", label: "State" },
              { key: "status", label: "Status" },
            ]}
          />
        </article>
      </section>
    </>
  );
}
