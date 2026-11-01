import { useEffect, useMemo, useState } from "react";
import { Bot, CheckCircle2, Code2, Database, Play, RefreshCw, Search } from "lucide-react";
import { api } from "../../apiClient";
import { IconButton } from "../../uiPrimitives";

const STARTER_SQL = `select *
from hc.irrigation_schedule
order by day_of_week, start_time
limit 50`;

function valueText(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function schemaKey(row) {
  return `${row.schema_name}.${row.table_name}`;
}

function extractSqlSnippet(text) {
  const value = String(text || "");
  const fenced = value.match(/```(?:sql|postgresql)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]?.trim()) return fenced[1].trim();
  const lines = value.split("\n");
  const startIndex = lines.findIndex((line) => /^\s*(select|with|explain)\b/i.test(line));
  if (startIndex === -1) return "";
  const snippet = [];
  for (const line of lines.slice(startIndex)) {
    if (!line.trim() && snippet.length) break;
    snippet.push(line);
    if (line.trim().endsWith(";")) break;
  }
  return snippet.join("\n").trim();
}

function relevantSchemaHint(text, tables, columnsByTable, selected, selectedColumns) {
  const haystack = String(text || "").toLowerCase();
  const matches = (tables || [])
    .filter((table) => {
      const shortName = String(table.table_name || "").toLowerCase();
      const fullName = schemaKey(table).toLowerCase();
      return haystack.includes(shortName) || haystack.includes(fullName);
    })
    .slice(0, 6);
  const rows = matches.length ? matches : selected ? [selected] : [];
  if (!rows.length) return "No table selected";
  return rows.map((table) => {
    const cols = schemaKey(table) === (selected ? schemaKey(selected) : "")
      ? selectedColumns
      : columnsByTable.get(schemaKey(table)) || [];
    return `${schemaKey(table)} columns: ${cols.map((column) => `${column.column_name} ${column.data_type}`).join(", ")}`;
  }).join("\n");
}

export default function SqlLab({ setToast }) {
  const [schema, setSchema] = useState({ tables: [], columns: [], indexes: [], constraints: [], limits: {} });
  const [schemaError, setSchemaError] = useState("");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [sql, setSql] = useState(STARTER_SQL);
  const [limit, setLimit] = useState(500);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [question, setQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiStatus, setAiStatus] = useState("idle");
  const aiSql = useMemo(() => extractSqlSnippet(aiAnswer), [aiAnswer]);

  async function loadSchema() {
    setBusy("schema");
    try {
      const data = await api("/api/sql-lab/schema", { skipContextRefresh: true });
      setSchema(data);
      setSchemaError("");
      if (!selected && data.tables?.length) setSelected(data.tables[0]);
    } catch (err) {
      setSchemaError(err.message);
      setToast?.(err.message);
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    loadSchema();
  }, []);

  const columnsByTable = useMemo(() => {
    const grouped = new Map();
    for (const column of schema.columns || []) {
      const key = schemaKey(column);
      grouped.set(key, [...(grouped.get(key) || []), column]);
    }
    return grouped;
  }, [schema.columns]);

  const indexesByTable = useMemo(() => {
    const grouped = new Map();
    for (const index of schema.indexes || []) {
      const key = schemaKey(index);
      grouped.set(key, [...(grouped.get(key) || []), index]);
    }
    return grouped;
  }, [schema.indexes]);

  const constraintsByTable = useMemo(() => {
    const grouped = new Map();
    for (const constraint of schema.constraints || []) {
      const key = schemaKey(constraint);
      grouped.set(key, [...(grouped.get(key) || []), constraint]);
    }
    return grouped;
  }, [schema.constraints]);

  const filteredTables = useMemo(() => {
    const term = filter.trim().toLowerCase();
    if (!term) return schema.tables || [];
    return (schema.tables || []).filter((table) => schemaKey(table).toLowerCase().includes(term));
  }, [schema.tables, filter]);

  const selectedColumns = selected ? columnsByTable.get(schemaKey(selected)) || [] : [];
  const selectedIndexes = selected ? indexesByTable.get(schemaKey(selected)) || [] : [];
  const selectedConstraints = selected ? constraintsByTable.get(schemaKey(selected)) || [] : [];

  async function runSql(event, overrideSql) {
    event?.preventDefault();
    const querySql = overrideSql || sql;
    setBusy("query");
    try {
      const data = await api("/api/sql-lab/query", {
        method: "POST",
        skipContextRefresh: true,
        body: JSON.stringify({ sql: querySql, limit }),
      });
      setResult(data);
      setToast?.(`${data.row_count || 0} rows | ${data.elapsed_ms} ms`);
    } catch (err) {
      setResult({ ok: false, error: err.message });
      setToast?.(err.message);
    } finally {
      setBusy("");
    }
  }

  async function previewTable(table) {
    setSelected(table);
    const nextSql = `select *
from ${table.schema_name}.${table.table_name}
limit 50`;
    setSql(nextSql);
    setBusy(`preview-${schemaKey(table)}`);
    try {
      const data = await api(`/api/sql-lab/preview?schema=${encodeURIComponent(table.schema_name)}&table=${encodeURIComponent(table.table_name)}&limit=50`, {
        skipContextRefresh: true,
      });
      setResult(data);
    } catch (err) {
      setResult({ ok: false, error: err.message });
      setToast?.(err.message);
    } finally {
      setBusy("");
    }
  }

  async function askAi() {
    const text = question.trim();
    if (!text) return;
    const schemaHint = relevantSchemaHint(`${text}\n${sql}`, schema.tables, columnsByTable, selected, selectedColumns);
    const prompt = [
      "SQL LAB help request. Please answer as a SQL tutor for the HomeControl PostgreSQL database.",
      "Only suggest read-only SELECT/WITH/EXPLAIN queries. If you provide a query, put the best runnable query in one fenced sql code block.",
      `User question: ${text}`,
      `Current SQL:\n${sql}`,
      `Selected schema:\n${schemaHint}`,
      result?.error ? `Last SQL error:\n${result.error}` : "",
    ].filter(Boolean).join("\n\n");
    setBusy("ai");
    setAiStatus("thinking");
    setAiAnswer("Thinking...");
    try {
      const data = await api("/api/ai/chat", {
        method: "POST",
        skipContextRefresh: true,
        body: JSON.stringify({ message: prompt, history: [] }),
      });
      setAiAnswer(data.reply || data.answer || data.message || "Nincs válasz.");
      setAiStatus("ready");
    } catch (err) {
      setAiAnswer(err.message);
      setAiStatus("error");
      setToast?.(err.message);
    } finally {
      setBusy("");
    }
  }

  function handleAiKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      askAi();
    }
  }

  function useAiSql() {
    if (!aiSql) {
      setToast?.("No SQL snippet detected in AI answer");
      return;
    }
    setSql(aiSql);
    setToast?.("AI SQL copied to editor");
  }

  async function runAiSql() {
    if (!aiSql) {
      setToast?.("No SQL snippet detected in AI answer");
      return;
    }
    setSql(aiSql);
    await runSql(null, aiSql);
  }

  return (
    <section className="sql-lab">
      <aside className="panel sql-schema-panel">
        <div className="panel-head">
          <div>
            <h2><Database size={17} aria-hidden="true" /> Database</h2>
            <span>{schemaError || `${schema.tables?.length || 0} objects`}</span>
          </div>
          <IconButton icon={RefreshCw} onClick={loadSchema} disabled={busy === "schema"}>{busy === "schema" ? "Loading" : "Refresh"}</IconButton>
        </div>
        <label className="sql-search">
          <Search size={15} aria-hidden="true" />
          <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter tables" />
        </label>
        <div className="sql-table-list">
          {filteredTables.map((table) => (
            <button
              className={selected && schemaKey(selected) === schemaKey(table) ? "active" : ""}
              type="button"
              onClick={() => setSelected(table)}
              onDoubleClick={() => previewTable(table)}
              key={schemaKey(table)}
            >
              <strong>{table.table_name}</strong>
              <span>{table.schema_name} | {table.object_type}</span>
            </button>
          ))}
        </div>
      </aside>

      <main className="sql-main">
        <article className="panel sql-editor-panel">
          <div className="panel-head">
            <div>
              <h2>SQL Editor</h2>
              <span>Read-only SELECT / WITH / EXPLAIN</span>
            </div>
            <div className="sql-editor-actions">
              <label>
                Limit
                <input type="number" min="1" max={schema.limits?.max_rows || 500} value={limit} onChange={(event) => setLimit(event.target.value)} />
              </label>
              <IconButton type="button" icon={Play} onClick={runSql} disabled={busy === "query"}>{busy === "query" ? "Running" : "Run"}</IconButton>
            </div>
          </div>
          <form onSubmit={runSql}>
            <textarea className="sql-editor" value={sql} onChange={(event) => setSql(event.target.value)} spellCheck="false" />
          </form>
        </article>

        <article className="panel sql-result-panel">
          <div className="panel-head">
            <div>
              <h2>Result</h2>
              <span>{result?.ok ? `${result.row_count} rows | ${result.elapsed_ms} ms` : result?.error || "No query yet"}</span>
            </div>
          </div>
          {result?.ok ? (
            <div className="table-wrap sql-result-table">
              <table>
                <thead>
                  <tr>{(result.columns || []).map((column) => <th key={column}>{column}</th>)}</tr>
                </thead>
                <tbody>
                  {(result.rows || []).map((row, index) => (
                    <tr key={index}>
                      {(result.columns || []).map((column) => <td key={column}>{valueText(row[column])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <pre className={result?.error ? "error-box" : "json-box"}>{result?.error || "Run a read-only query to see results."}</pre>
          )}
        </article>
      </main>

      <aside className="panel sql-detail-panel">
        <div className="panel-head">
          <div>
            <h2>Structure</h2>
            <span>{selected ? schemaKey(selected) : "Select a table"}</span>
          </div>
          {selected && <IconButton type="button" icon={Play} onClick={() => previewTable(selected)} disabled={busy === `preview-${schemaKey(selected)}`}>Preview</IconButton>}
        </div>
        {selected ? (
          <>
            <div className="sql-column-list">
              {selectedColumns.map((column) => (
                <div key={column.column_name}>
                  <strong>{column.column_name}</strong>
                  <span>{column.data_type}{column.is_nullable === "NO" ? " | not null" : ""}</span>
                </div>
              ))}
            </div>
            <div className="sql-meta-list">
              {selectedConstraints.map((constraint) => <span key={constraint.constraint_name}>{constraint.constraint_type}: {constraint.constraint_name}</span>)}
              {selectedIndexes.map((index) => <span key={index.indexname}>{index.indexname}</span>)}
            </div>
          </>
        ) : (
          <pre className="json-box">Select a table to inspect columns, indexes and constraints.</pre>
        )}

        <div className="sql-ai-box">
          <div className="panel-head">
            <div>
              <h2><Bot size={17} aria-hidden="true" /> AI Helper</h2>
              <span className={`sql-ai-status ${aiStatus}`}>{aiStatus === "thinking" ? "Thinking..." : aiStatus === "ready" ? "Answer ready" : aiStatus === "error" ? "AI error" : "SQL tutor with current query context"}</span>
            </div>
          </div>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={handleAiKeyDown} placeholder="Pl. hogyan joinoljam az entity és state táblákat?" />
          <div className="sql-ai-actions">
            <IconButton type="button" icon={Bot} onClick={askAi} disabled={busy === "ai" || !question.trim()}>{busy === "ai" ? "Thinking" : "Ask AI"}</IconButton>
            <IconButton type="button" icon={Code2} className="secondary" onClick={useAiSql} disabled={busy === "ai"}>Use SQL</IconButton>
            <IconButton type="button" icon={Play} className="secondary" onClick={runAiSql} disabled={busy === "ai" || busy === "query"}>Run SQL</IconButton>
          </div>
          {aiSql && (
            <div className="sql-ai-detected">
              <CheckCircle2 size={15} aria-hidden="true" />
              <span>SQL snippet detected</span>
            </div>
          )}
          {aiStatus === "ready" && !aiSql && <div className="sql-ai-missing">No SQL snippet detected</div>}
          {aiAnswer && <pre className="sql-ai-answer">{aiAnswer}</pre>}
        </div>
      </aside>
    </section>
  );
}
