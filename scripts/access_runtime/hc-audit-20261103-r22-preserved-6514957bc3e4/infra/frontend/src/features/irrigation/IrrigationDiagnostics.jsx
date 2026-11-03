import { Activity, RefreshCw } from "lucide-react";
import { usePolledContext } from "../../apiClient";
import { ageText, dateText, displayEntityName, shortValue, valueText } from "../../formatters";
import { IconButton, Table } from "../../uiPrimitives";

export default function IrrigationDiagnostics() {
  const { data: state, loading, error, refresh: loadDiagnostics } = usePolledContext("/api/context/irrigation");

  const live = state?.live || {};
  const topicRows = Object.entries(live.topics || {}).map(([name, item]) => ({ name, item }));
  const rawRows = live.raw || [];

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Irrigation Diagnostics</h2>
          <span>{error || `${topicRows.length} live topics | ${rawRows.length} raw messages`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadDiagnostics} disabled={loading}>{loading ? "Refreshing" : "Refresh diagnostics"}</IconButton>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>DB Current State</h2>
          <span>entity_state</span>
        </div>
        <Table
          rows={state?.latest || []}
          columns={[
            { key: "entity_name", label: "Entity", render: (row) => displayEntityName(row.entity_name) },
            { key: "key", label: "Key" },
            { key: "value", label: "Value", render: valueText },
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
          ]}
        />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Live MQTT Topics</h2>
            <span>MQTT snapshot</span>
          </div>
          <Table
            rows={topicRows}
            columns={[
              { key: "name", label: "Name" },
              { key: "age", label: "Age", render: (row) => ageText(row.item) },
              { key: "value", label: "Last value", render: (row) => row.item ? shortValue(row.item.json ?? row.item.payload) : "-" },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Raw MQTT Monitor</h2>
            <span>{rawRows.length} messages</span>
          </div>
          <Table
            rows={rawRows}
            columns={[
              { key: "age", label: "Age", render: (row) => `${row.age_sec} s` },
              { key: "topic", label: "Topic" },
              { key: "payload", label: "Payload", render: (row) => shortValue(row.json ?? row.payload, 180) },
            ]}
          />
        </article>
      </section>
    </>
  );
}
