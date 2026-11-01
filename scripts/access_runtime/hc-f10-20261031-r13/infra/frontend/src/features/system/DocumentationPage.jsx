import { useEffect, useState } from "react";
import { Activity, BookOpen, RefreshCw } from "lucide-react";
import { IconButton, Table } from "../../uiPrimitives";
import { byteText, dateText, numberText, shortValue } from "../../formatters";
import { fetchDocumentation } from "./systemInfoApi";
import { selectedDocumentationModule } from "./documentationState";

export default function DocumentationPage({ setToast }) {
  const [docs, setDocs] = useState(null);
  const [selectedKey, setSelectedKey] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadDocs() {
    setLoading(true);
    try {
      const data = await fetchDocumentation();
      setDocs(data);
      setSelectedKey((current) => current || data.modules?.[0]?.key || "");
    } catch (err) {
      setToast(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDocs();
  }, []);

  if (loading && !docs) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading documentation...</span>
      </section>
    );
  }

  const { modules, selected, source, bindings, devices, buttons, deepDive } = selectedDocumentationModule(docs, selectedKey);

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>HomeControl Documentation</h2>
          <span>{docs?.generated_at ? `${numberText(docs?.summary?.module_count, 0)} modules | ${numberText(docs?.summary?.binding_count, 0)} bindings | generated ${dateText(docs.generated_at)}` : "Module handbook"}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadDocs} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="documentation-layout">
        <aside className="panel documentation-nav">
          <div className="panel-head">
            <h2>Modules</h2>
            <span>{numberText(modules.length, 0)} entries</span>
          </div>
          <div className="documentation-module-list">
            {modules.map((module) => (
              <button
                type="button"
                key={module.key}
                className={module.key === selected.key ? "active" : ""}
                onClick={() => setSelectedKey(module.key)}
              >
                <BookOpen size={16} aria-hidden="true" />
                <span>{module.label}</span>
                <small>{module.domain}</small>
              </button>
            ))}
          </div>
        </aside>

        <article className="panel documentation-detail">
          <div className="panel-head">
            <h2>{selected.label || "Module"}</h2>
            <span>{selected.domain || "-"} | {source.path || "runtime"}</span>
          </div>

          <section className="documentation-section">
            <h3>Mit csinal?</h3>
            <p>{selected.summary || "-"}</p>
          </section>

          <section className="documentation-section">
            <h3>Hogyan mukodik, lepesrol lepesre?</h3>
            <ol>
              {(selected.responsibilities || []).map((item) => <li key={item}>{item}</li>)}
            </ol>
          </section>

          <section className="documentation-section">
            <h3>Gombok es muveletek</h3>
            <Table
              rows={buttons}
              columns={[
                { key: "name", label: "Button" },
                { key: "does", label: "What it does" },
                { key: "guard", label: "Guard / condition" },
              ]}
            />
          </section>

          {deepDive.length > 0 && (
            <section className="documentation-section documentation-deep-dive">
              <h3>Reszletes folyamatleiras</h3>
              <div className="documentation-deep-list">
                {deepDive.map((section) => (
                  <article className="documentation-deep-card" key={section.title}>
                    <h4>{section.title}</h4>
                    {section.body && <p>{section.body}</p>}
                    <ul>
                      {(section.items || []).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className="documentation-grid">
            <section className="documentation-section">
              <h3>Elofeltetelek</h3>
              <ul>{(selected.prerequisites || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
            <section className="documentation-section">
              <h3>Kimenetek</h3>
              <ul>{(selected.outputs || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          </section>

          <section className="documentation-section">
            <h3>Forraskod es meret</h3>
            <div className="about-fact-grid documentation-facts">
              <div><span>Path</span><strong>{source.path || (selected.files || []).join(", ") || "-"}</strong></div>
              <div><span>Files</span><strong>{numberText(source.files, 0)}</strong></div>
              <div><span>Lines</span><strong>{numberText(source.lines, 0)}</strong></div>
              <div><span>Size</span><strong>{byteText(source.bytes)}</strong></div>
            </div>
            <ul className="documentation-file-list">
              {(selected.files || []).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>

          <section className="documentation-section">
            <h3>Csatolt funkciok</h3>
            <Table
              rows={bindings}
              columns={[
                { key: "label", label: "Function" },
                { key: "device_name", label: "Device", render: (row) => row.device_name || row.entity_name || "-" },
                { key: "location", label: "Location" },
                { key: "device_type", label: "Type" },
                { key: "topic_base", label: "Topic", render: (row) => shortValue(row.topic_base, 80) },
              ]}
            />
          </section>

          <section className="documentation-section">
            <h3>Dinamikusan talalt eszkozok</h3>
            <Table
              rows={devices}
              columns={[
                { key: "name", label: "Device" },
                { key: "location", label: "Location" },
                { key: "platform", label: "Platform" },
                { key: "device_type", label: "Type" },
                { key: "metrics", label: "Metrics", render: (row) => (row.metrics || []).slice(0, 8).join(", ") || "-" },
              ]}
            />
            <p className="documentation-note">
              {selected.device_count > devices.length
                ? `${numberText(selected.device_count, 0)} matching devices found; showing the first ${numberText(devices.length, 0)}.`
                : `${numberText(devices.length, 0)} matching devices shown.`}
            </p>
          </section>
        </article>
      </section>
    </>
  );
}
