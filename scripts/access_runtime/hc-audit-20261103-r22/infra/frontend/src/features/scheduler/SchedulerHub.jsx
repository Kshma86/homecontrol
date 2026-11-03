import React, { useState } from "react";
import { Activity, CalendarDays, Clock, Database, Gauge, Map as MapIcon, Play, Radio, Settings } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { dateText, jsonText, shortValue } from "../../formatters";
import { climateFanOptions, climateModeOptions } from "../climate/climateOptions";
import { dayLabels } from "./schedulerOptions";

export default function SchedulerHub({ setToast }) {
  const [busy, setBusy] = useState("");
  const { data: state, setData: setState, loading } = usePolledContext("/api/context/scheduler", {
    intervalMs: 5000,
    onError: (err) => setToast(err.message),
  });
  const [simulationDraft, setSimulationDraft] = useState({
    domain: "irrigation",
    action: "water_start",
    schedule_id: "simulation",
    label: "Simulation",
    start_time: "17:00",
    stop_time: "18:30",
    duration_minutes: 90,
    map_id: 3,
    segments: "1",
    suction: 3,
    water_level: 2,
    power: "on",
    climate_mode: "heat",
    target_temperature: 23,
    fan_speed: "auto",
  });
  const [simulationResult, setSimulationResult] = useState(null);

  async function setMode(mode) {
    setBusy(mode);
    try {
      const data = await api("/api/scheduler/config", {
        method: "PUT",
        body: JSON.stringify({ mode, updated_by: "react-admin" }),
      });
      setState(data.state);
      setToast(`${mode.replaceAll("_", " ")} saved; command publishing remains guarded by feature flags`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateSimulationDraft(key, value) {
    setSimulationDraft((current) => {
      const next = { ...current, [key]: value };
      if (key === "domain") {
        if (value === "irrigation") {
          next.action = "water_start";
          next.start_time = next.start_time || "17:00";
          next.stop_time = next.stop_time || "18:30";
          next.duration_minutes = next.duration_minutes || 90;
        } else if (value === "xiaomi_x10") {
          next.action = "clean_start";
          next.start_time = next.start_time || "14:00";
          next.segments = next.segments || "1";
          next.map_id = next.map_id || 3;
        } else {
          next.action = "climate_set";
          next.start_time = next.start_time || "06:30";
          next.power = next.power || "on";
          next.climate_mode = next.climate_mode || "heat";
          next.target_temperature = next.target_temperature || 23;
          next.fan_speed = next.fan_speed || "auto";
        }
      }
      return next;
    });
  }

  async function runSimulation(event) {
    event.preventDefault();
    setBusy("simulate");
    try {
      const payload = {
        ...simulationDraft,
        duration_minutes: Number(simulationDraft.duration_minutes || 0) || undefined,
        map_id: Number(simulationDraft.map_id || 0) || undefined,
        suction: Number(simulationDraft.suction || 0) || undefined,
        water_level: Number(simulationDraft.water_level || 0) || undefined,
        target_temperature: Number(simulationDraft.target_temperature || 0) || undefined,
        segments: String(simulationDraft.segments || "").split(",").map((item) => Number(item.trim())).filter(Boolean),
      };
      const data = await api("/api/v2/simulate/scheduler", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setSimulationResult(data);
      setToast("V2 simulation complete; no rows written and no command published");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading scheduler...</span>
      </section>
    );
  }

  const config = state?.config || {};
  const summary = state?.summary || {};
  const v2 = state?.v2 || {};
  const v2Counts = v2.counts || {};
  const v2Activity = v2.activity || [];
  const v2Chains = v2.chains || [];
  const irrigationPreflight = v2.preflight?.irrigation || {};
  const x10Preflight = v2.preflight?.xiaomi_x10 || {};
  const climatePreflight = v2.preflight?.climate || {};
  const mode = config.mode || "v2_execute_all";
  const v2Modes = v2.modes || [
    { value: "v2_execute_irrigation", label: "V2 execute irrigation", command_owner: "v2" },
    { value: "v2_execute_x10", label: "V2 execute X10", command_owner: "v2" },
    { value: "v2_execute_climate", label: "V2 execute Climate", command_owner: "v2" },
    { value: "v2_execute_x10_climate", label: "V2 execute X10 + Climate", command_owner: "v2" },
    { value: "v2_execute_all", label: "V2 execute all", command_owner: "v2" },
  ];
  const executionEngine = v2.execution_engine || {};
  const modeLabel = v2Modes.find((item) => item.value === mode)?.label || mode.replaceAll("_", " ");
  const jobs = state?.jobs || [];
  const runs = state?.history || state?.runs || [];

  return (
    <>
      <section className="tile-grid scheduler-tiles">
        <Card title="V2 Scheduler" value={modeLabel} meta={executionEngine.publish_enabled ? "V2 owns scheduled publishing" : "V2 publish guarded"} icon={CalendarDays} tone={executionEngine.publish_enabled ? "" : "warn"} />
        <Card title="Known Jobs" value={String(summary.job_count || 0)} meta={`${summary.enabled_count || 0} enabled | ${(summary.domains || []).join(", ") || "-"}`} icon={Clock} />
        <Card title="V2 Events" value={String(v2Counts.events || 0)} meta={v2.available ? "EventStore ready" : "EventStore missing"} icon={Radio} />
        <Card title="V2 Plans" value={String(v2Counts.plans || 0)} meta="PlanStore audit records" icon={MapIcon} />
        <Card title="V2 Executions" value={String(v2Counts.executions || 0)} meta={executionEngine.publish_enabled ? "publish enabled" : "publish disabled"} icon={Activity} />
      </section>

      <section className="scheduler-top-layout">
        <div className="scheduler-compact-stack">
          <article className="panel">
            <div className="panel-head">
              <h2 className="panel-title"><Settings size={17} aria-hidden="true" /> V2 Runtime Switch</h2>
              <span>Publishing is blocked unless execution feature flags are enabled</span>
            </div>
            <div className="mode-switch">
              {v2Modes.map((item) => {
                const Icon = item.value.startsWith("v2_execute") ? Play : Radio;
                return (
                  <button
                    className={mode === item.value ? "active" : "secondary"}
                    type="button"
                    disabled={Boolean(busy)}
                    onClick={() => setMode(item.value)}
                    key={item.value}
                  >
                    <Icon size={16} aria-hidden="true" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
            <div className="scheduler-note">
              <strong>{executionEngine.publish_enabled ? "V2 publishing is enabled for the selected domain." : "V2 publishing is disabled by feature flags."}</strong>
              <span>{`Current command owner: ${executionEngine.command_owner || "blocked"} | reason: ${executionEngine.reason || "-"}`}</span>
            </div>
          </article>

          <article className="panel scheduler-v2-panel">
            <div className="panel-head">
              <h2 className="panel-title"><Database size={17} aria-hidden="true" /> V2 Core Stores</h2>
              <span>Event-State-Rule-Plan-Execution foundation, read-only here</span>
            </div>
            <div className="v2-store-grid">
              <div><span>EventStore</span><strong>{v2.available ? "ready" : "missing"}</strong></div>
              <div><span>StateStore</span><strong>entity_state</strong></div>
              <div><span>PlanStore</span><strong>{v2.available ? "ready" : "missing"}</strong></div>
              <div><span>ExecutionStore</span><strong>{v2.available ? "ready" : "missing"}</strong></div>
            </div>
            <div className="scheduler-note">
              <strong>Scheduler tab is the V2 scheduler workspace.</strong>
              <span>Execution engine enabled={String(Boolean(executionEngine.enabled))}; publish enabled={String(Boolean(executionEngine.publish_enabled))}; owner={executionEngine.command_owner || "blocked"}.</span>
            </div>
          </article>
        </div>
      </section>

      <section className="scheduler-preflight-grid">
        <article className="panel scheduler-v2-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> V2 Irrigation Preflight</h2>
            <span>Readiness before any future V2 publish is allowed</span>
          </div>
          <div className={`preflight-status ${String(irrigationPreflight.overall || "BLOCKED").toLowerCase()}`}>
            <strong>{irrigationPreflight.overall || "BLOCKED"}</strong>
            <span>{irrigationPreflight.block_count || 0} blocked | {irrigationPreflight.warn_count || 0} warning</span>
          </div>
          <div className="preflight-list">
            {(irrigationPreflight.checks || []).map((check) => (
              <div className={`preflight-check ${check.status}`} key={check.key}>
                <strong>{check.key.replaceAll("_", " ")}</strong>
                <span>{check.message}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="panel scheduler-v2-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> V2 X10 Preflight</h2>
            <span>Readiness before V2 owns the robot weekly schedule</span>
          </div>
          <div className={`preflight-status ${String(x10Preflight.overall || "BLOCKED").toLowerCase()}`}>
            <strong>{x10Preflight.overall || "BLOCKED"}</strong>
            <span>{x10Preflight.block_count || 0} blocked | {x10Preflight.warn_count || 0} warning</span>
          </div>
          <div className="preflight-list">
            {(x10Preflight.checks || []).map((check) => (
              <div className={`preflight-check ${check.status}`} key={check.key}>
                <strong>{check.key.replaceAll("_", " ")}</strong>
                <span>{check.message}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="panel scheduler-v2-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> V2 Climate Preflight</h2>
            <span>Readiness before V2 owns the climate schedule</span>
          </div>
          <div className={`preflight-status ${String(climatePreflight.overall || "BLOCKED").toLowerCase()}`}>
            <strong>{climatePreflight.overall || "BLOCKED"}</strong>
            <span>{climatePreflight.block_count || 0} blocked | {climatePreflight.warn_count || 0} warning</span>
          </div>
          <div className="preflight-list">
            {(climatePreflight.checks || []).map((check) => (
              <div className={`preflight-check ${check.status}`} key={check.key}>
                <strong>{check.key.replaceAll("_", " ")}</strong>
                <span>{check.message}</span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="scheduler-layout">
        <article className="panel scheduler-jobs-panel">
          <div className="panel-head">
            <h2 className="panel-title"><CalendarDays size={17} aria-hidden="true" /> V2 Job View</h2>
            <span>Read-through view over scheduler sources; execution history tracks V2 audit and publish decisions</span>
          </div>
          <Table
            rows={jobs.map((job, index) => ({ ...job, id: `${job.domain}-${job.source_ref}-${job.day_of_week ?? index}` }))}
            columns={[
              { key: "domain", label: "Domain", render: (row) => row.domain === "xiaomi_x10" ? "X10" : row.domain === "climate" ? "Climate" : "Irrigation" },
              { key: "label", label: "Job" },
              { key: "day_of_week", label: "Day", render: (row) => row.days_label || (row.day_of_week === null || row.day_of_week === undefined ? "-" : dayLabels[row.day_of_week]) },
              { key: "start_time", label: "Start" },
              { key: "stop_time", label: "Stop", render: (row) => row.stop_time || "-" },
              { key: "is_enabled", label: "Enabled", render: (row) => row.is_enabled ? "Yes" : "No" },
              { key: "status", label: "Status", render: (row) => String(row.status || "-").replaceAll("_", " ") },
            ]}
          />
        </article>
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Play size={17} aria-hidden="true" /> V2 Scheduler Simulation</h2>
          <span>Dry-run only: no database writes and no MQTT publish</span>
        </div>
        <form className="v2-sim-form" onSubmit={runSimulation}>
          <label>
            Domain
            <select value={simulationDraft.domain} onChange={(event) => updateSimulationDraft("domain", event.target.value)}>
              <option value="irrigation">Irrigation</option>
              <option value="xiaomi_x10">X10</option>
              <option value="climate">Climate</option>
            </select>
          </label>
          <label>
            Action
            <select value={simulationDraft.action} onChange={(event) => updateSimulationDraft("action", event.target.value)}>
              {simulationDraft.domain === "irrigation" ? (
                <>
                  <option value="water_start">Water start</option>
                  <option value="water_stop">Water stop</option>
                </>
              ) : simulationDraft.domain === "xiaomi_x10" ? (
                <option value="clean_start">Clean start</option>
              ) : (
                <option value="climate_set">Climate set</option>
              )}
            </select>
          </label>
          <label>
            Ref
            <input type="text" value={simulationDraft.schedule_id} onChange={(event) => updateSimulationDraft("schedule_id", event.target.value)} />
          </label>
          <label>
            Label
            <input type="text" value={simulationDraft.label} onChange={(event) => updateSimulationDraft("label", event.target.value)} />
          </label>
          <label>
            Start
            <input type="time" value={simulationDraft.start_time} onChange={(event) => updateSimulationDraft("start_time", event.target.value)} />
          </label>
          {simulationDraft.domain === "irrigation" ? (
            <>
              <label>
                Stop
                <input type="time" value={simulationDraft.stop_time} onChange={(event) => updateSimulationDraft("stop_time", event.target.value)} />
              </label>
              <label>
                Duration
                <input type="number" min="1" max="720" value={simulationDraft.duration_minutes} onChange={(event) => updateSimulationDraft("duration_minutes", event.target.value)} />
              </label>
            </>
          ) : simulationDraft.domain === "xiaomi_x10" ? (
            <>
              <label>
                Map
                <input type="number" min="1" value={simulationDraft.map_id} onChange={(event) => updateSimulationDraft("map_id", event.target.value)} />
              </label>
              <label>
                Segments
                <input type="text" value={simulationDraft.segments} onChange={(event) => updateSimulationDraft("segments", event.target.value)} />
              </label>
              <label>
                Suction
                <input type="number" min="0" max="3" value={simulationDraft.suction} onChange={(event) => updateSimulationDraft("suction", event.target.value)} />
              </label>
              <label>
                Water
                <input type="number" min="1" max="3" value={simulationDraft.water_level} onChange={(event) => updateSimulationDraft("water_level", event.target.value)} />
              </label>
            </>
          ) : (
            <>
              <label>
                Power
                <select value={simulationDraft.power} onChange={(event) => updateSimulationDraft("power", event.target.value)}>
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
              <label>
                Mode
                <select value={simulationDraft.climate_mode} onChange={(event) => updateSimulationDraft("climate_mode", event.target.value)}>
                  {climateModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                Target
                <input type="number" min="8" max="30" value={simulationDraft.target_temperature} onChange={(event) => updateSimulationDraft("target_temperature", event.target.value)} />
              </label>
              <label>
                Fan
                <select value={simulationDraft.fan_speed} onChange={(event) => updateSimulationDraft("fan_speed", event.target.value)}>
                  {climateFanOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </>
          )}
          <IconButton icon={Play} disabled={busy === "simulate"}>{busy === "simulate" ? "Simulating" : "Dry Run"}</IconButton>
        </form>
        {simulationResult?.chain && (
          <div className="v2-sim-result">
            <div className="v2-chain-grid">
              <div><span>Event</span><strong>{simulationResult.chain.event_type}</strong><small>{simulationResult.chain.event_status}</small></div>
              <div><span>Plan</span><strong>{simulationResult.chain.plan_type}</strong><small>{simulationResult.chain.plan_status}</small></div>
              <div><span>Execution</span><strong>{simulationResult.chain.executor}</strong><small>{simulationResult.chain.execution_status}</small></div>
              <div><span>Publish</span><strong>{String(Boolean(simulationResult.chain.execution_engine?.can_publish))}</strong><small>{simulationResult.chain.execution_engine?.reason || "-"}</small></div>
              <div><span>Confirm</span><strong>{simulationResult.chain.confirmation_diagnostics?.status || "-"}</strong><small>{simulationResult.chain.confirmation_diagnostics?.strategy || "-"}</small></div>
              <div><span>Observed</span><strong>{simulationResult.chain.legacy_comparison?.status || "-"}</strong><small>{simulationResult.chain.legacy_comparison?.summary || "-"}</small></div>
              <div><span>Writes</span><strong>{String(Boolean(simulationResult.writes))}</strong><small>publishes={String(Boolean(simulationResult.publishes))}</small></div>
            </div>
            <div className="v2-json-grid">
              <div>
                <h3>Simulated Event</h3>
                <pre className="json-box">{jsonText(simulationResult.chain.event_payload)}</pre>
              </div>
              <div>
                <h3>Simulated Plan</h3>
                <pre className="json-box">{jsonText({ inputs: simulationResult.chain.plan_inputs, actions: simulationResult.chain.plan_actions })}</pre>
              </div>
              <div>
                <h3>Simulated Execution</h3>
                <pre className="json-box">{jsonText({ topic: simulationResult.chain.command_topic, payload: simulationResult.chain.command_payload, result: simulationResult.chain.execution_result })}</pre>
              </div>
              <div>
                <h3>Diagnostics</h3>
                <pre className="json-box">{jsonText({ engine: simulationResult.engine, confirmation: simulationResult.chain.confirmation_diagnostics, comparison: simulationResult.chain.legacy_comparison })}</pre>
              </div>
            </div>
          </div>
        )}
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Database size={17} aria-hidden="true" /> V2 Core Activity</h2>
          <span>Latest EventStore, PlanStore and ExecutionStore records</span>
        </div>
        <Table
          rows={v2Activity}
          columns={[
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
            { key: "kind", label: "Store", render: (row) => String(row.kind || "-").toUpperCase() },
            { key: "domain", label: "Domain" },
            { key: "label", label: "Type" },
            { key: "status", label: "Status" },
            { key: "detail", label: "Detail" },
            { key: "correlation_id", label: "Correlation", render: (row) => row.correlation_id ? row.correlation_id.slice(0, 8) : "-" },
          ]}
        />
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> V2 Diagnostics</h2>
          <span>Read-only comparison between V2 intent and observed scheduler evidence</span>
        </div>
        <Table
          rows={v2Chains.map((chain, index) => ({ ...chain, id: chain.event_id || index }))}
          columns={[
              { key: "domain", label: "Domain", render: (row) => row.domain === "xiaomi_x10" ? "X10" : row.domain === "climate" ? "Climate" : "Irrigation" },
            { key: "event_type", label: "V2 Event" },
            { key: "v2_wanted", label: "V2 Wanted", render: (row) => shortValue(row.legacy_comparison?.v2_wanted || row.command_payload, 120) },
            { key: "legacy_observed", label: "Observed", render: (row) => shortValue(row.legacy_comparison?.legacy_observed, 120) },
            { key: "compare", label: "Compare", render: (row) => row.legacy_comparison?.status || "-" },
            { key: "summary", label: "Summary", render: (row) => row.legacy_comparison?.summary || "-" },
          ]}
        />
      </section>

      <section className="panel scheduler-explain-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> V2 Chain Explain</h2>
          <span>Event, plan and execution detail for each observed scheduler intent</span>
        </div>
        {v2Chains.length ? (
          <div className="v2-chain-list">
            {v2Chains.map((chain, index) => {
              const action = Array.isArray(chain.plan_actions) ? chain.plan_actions[0] : null;
              const published = chain.execution_result?.published;
              const engineDecision = chain.execution_engine || {};
              const confirmation = chain.confirmation_diagnostics || {};
              const comparison = chain.legacy_comparison || {};
              return (
                <details className="v2-chain" key={chain.event_id || index} open={index === 0}>
                  <summary>
                    <span>{chain.domain === "xiaomi_x10" ? "X10" : chain.domain === "climate" ? "Climate" : chain.domain}</span>
                    <strong>{chain.event_type || "-"}</strong>
                    <em>{chain.execution_status || chain.plan_status || chain.event_status || "-"}</em>
                  </summary>
                  <div className="v2-chain-grid">
                    <div>
                      <span>Event</span>
                      <strong>{chain.event_status || "-"}</strong>
                      <small>{dateText(chain.event_ts)} | {chain.event_source || "-"}</small>
                    </div>
                    <div>
                      <span>Plan</span>
                      <strong>{chain.plan_type || "missing"}</strong>
                      <small>{chain.target_type && chain.target_ref ? `${chain.target_type}:${chain.target_ref}` : "-"}</small>
                    </div>
                    <div>
                      <span>Action</span>
                      <strong>{action?.capability || "-"}</strong>
                      <small>{shortValue(action?.command || action, 90)}</small>
                    </div>
                    <div>
                      <span>Execution</span>
                      <strong>{chain.executor || "missing"}</strong>
                      <small>{chain.command_topic || "-"} | published={published === undefined ? "-" : String(published)}</small>
                    </div>
                    <div>
                      <span>Engine</span>
                      <strong>{engineDecision.can_publish ? "can publish" : "blocked"}</strong>
                      <small>{engineDecision.reason || "-"}</small>
                    </div>
                    <div>
                      <span>Confirm</span>
                      <strong>{confirmation.status || "-"}</strong>
                      <small>{confirmation.strategy || "-"}</small>
                    </div>
                    <div>
                      <span>Compare</span>
                      <strong>{comparison.status || "-"}</strong>
                      <small>{comparison.summary || "-"}</small>
                    </div>
                  </div>
                  <div className="v2-json-grid">
                    <div>
                      <h3>Event Payload</h3>
                      <pre className="json-box">{jsonText(chain.event_payload)}</pre>
                    </div>
                    <div>
                      <h3>Plan Inputs</h3>
                      <pre className="json-box">{jsonText(chain.plan_inputs)}</pre>
                    </div>
                    <div>
                      <h3>Plan Actions</h3>
                      <pre className="json-box">{jsonText(chain.plan_actions)}</pre>
                    </div>
                    <div>
                      <h3>Execution Command</h3>
                      <pre className="json-box">{jsonText({ topic: chain.command_topic, payload: chain.command_payload, result: chain.execution_result })}</pre>
                    </div>
                    <div>
                      <h3>Confirmation Diagnostics</h3>
                      <pre className="json-box">{jsonText(confirmation)}</pre>
                    </div>
                    <div>
                      <h3>Execution Engine</h3>
                      <pre className="json-box">{jsonText({ decision: engineDecision, engine: executionEngine })}</pre>
                    </div>
                    <div>
                      <h3>Observed Evidence</h3>
                      <pre className="json-box">{jsonText(comparison)}</pre>
                    </div>
                  </div>
                  <div className="scheduler-note">
                    <strong>{chain.reasoning || "V2 audit chain is read-only."}</strong>
                    <span>Publishing follows the current V2 engine decision for the domain.</span>
                  </div>
                </details>
              );
            })}
          </div>
        ) : (
          <div className="chart-empty">No V2 chains yet</div>
        )}
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> V2 Scheduler History</h2>
          <span>What the V2 scheduler observed or wanted to do</span>
        </div>
        <Table
          rows={runs}
          columns={[
            { key: "requested_at", label: "Seen", render: (row) => dateText(row.requested_at) },
            { key: "domain_label", label: "Domain" },
            { key: "job_label", label: "Job" },
            { key: "action_label", label: "Wanted Action" },
            { key: "status_label", label: "Status" },
            { key: "event_time", label: "Planned Time", render: (row) => row.observed_date && row.event_time ? `${row.observed_date} ${row.event_time}` : row.event_time || "-" },
            { key: "mode", label: "Mode", render: (row) => row.mode || "-" },
            { key: "shadow_only", label: "Command", render: (row) => row.shadow_only ? "No command" : "Command path" },
            { key: "source", label: "Source", render: (row) => row.source_ref ? `${row.source}:${row.source_ref}` : row.source || "-" },
            { key: "legacy_status", label: "Source Status", render: (row) => String(row.legacy_status || "-").replaceAll("_", " ") },
            { key: "error", label: "Error", render: (row) => row.error || "-" },
          ]}
        />
      </section>
    </>
  );
}
