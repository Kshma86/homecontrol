import React, { useState } from "react";
import { Activity, CloudRain, Droplets, RefreshCw, Save, Settings } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { entitySelectLabel, processBinding } from "../../entityHelpers";
import { dateText, numberText, shortValue, unitValue } from "../../formatters";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { decisionStatusText, pilotFields, pilotTermLabel, pilotTermMeta, ruleText, signedMultiplierText } from "./pilotUtils";

function PilotDecisionFormula({ result = {} }) {
  const base = Number(result.base_duration);
  const final = Number(result.final_duration);
  const terms = Array.isArray(result.multiplier_terms) ? result.multiplier_terms : [];
  const skip = final === 0 && terms.length <= 1;
  const formulaTerms = terms.length
    ? terms.map((term, index) => index === 0 ? numberText(term.multiplier ?? term.delta, 2) : signedMultiplierText(term.delta)).join(" ")
    : numberText(result.applied_multiplier, 2);
  const applied = Number(result.applied_multiplier);

  return (
    <div className="pilot-formula">
      <span>Decision formula</span>
      <strong>
        {Number.isFinite(base)
          ? `${unitValue(base, "min", 0)} x (${formulaTerms || "-"}) = ${unitValue(final, "min", 0)}`
          : "-"}
      </strong>
      {Number.isFinite(applied) && !skip && <em>Applied multiplier: {numberText(applied, 2)}x</em>}
      {skip && <em>Skipped by a hard stop rule.</em>}
      <div className="pilot-formula-terms">
        {terms.map((term, index) => (
          <div key={`${term.rule || "term"}-${index}`}>
            <span>{pilotTermLabel(term)}</span>
            <strong>{index === 0 ? numberText(term.multiplier ?? term.delta, 2) : signedMultiplierText(term.delta)}</strong>
            <small>{pilotTermMeta(term)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PilotSummaryCards({ fallbackMode = "-", fallbackAge = "-", seasonProfile = "-" }) {
  const { data: state, error } = usePolledContext("/api/context/irrigation_pilot");

  const forecastDecision = state?.recommendation || {};
  const inputs = forecastDecision.details?.inputs || {};
  const rules = forecastDecision.triggered_rules || [];
  const mode = state?.config?.mode;
  const pilotModeText = mode === "pilot" ? "Pilot" : mode === "navigator" ? "Navigator" : "Pilot";
  const fallbackText = fallbackMode && fallbackMode !== "-" ? fallbackMode : "Fallback";
  const rainSensorWet = inputs.RainSensorWet === true ? "WET" : inputs.RainSensorWet === false ? "DRY" : "-";
  const rainSensorMeta = inputs.RainSensorLastWet ? `last wet: ${dateText(inputs.RainSensorLastWet)}` : `battery ${unitValue(inputs.RainSensorBattery, "%", 0)} | lqi ${numberText(inputs.RainSensorLinkquality, 0)}`;

  return (
    <>
      <Card title="Mode" value={`${pilotModeText} | ${fallbackText}`} meta={error || `Season ${seasonProfile} | fallback age ${fallbackAge}`} icon={Settings} />
      <Card title="Current forecast" value={unitValue(forecastDecision.final_duration, "min", 0)} meta={error || ruleText(rules)} icon={Droplets} />
      <Card title="Rain sensor" value={rainSensorWet} meta={error || rainSensorMeta} icon={CloudRain} />
    </>
  );
}

export default function PilotDashboard({ setToast }) {
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState("");
  const { data: state, loading, error, refresh: loadPilot } = usePolledContext("/api/context/irrigation_pilot", {
    mapPayload: (payload) => {
      setDraft(payload.config || {});
      return payload;
    },
  });

  function updateDraft(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function saveConfig() {
    setBusy("save");
    try {
      const payload = Object.fromEntries(Object.entries(draft).filter(([key]) => key !== "base_duration_minutes"));
      await api("/api/irrigation/pilot/config", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setToast("Pilot config saved");
      await loadPilot();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function fetchWeather() {
    setBusy("weather");
    try {
      await api("/api/irrigation/weather/fetch", { method: "POST", body: "{}" });
      setToast("Weather refreshed");
      await loadPilot();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function createDecision() {
    setBusy("decision");
    try {
      await api("/api/irrigation/pilot/evaluate", { method: "POST", body: "{}" });
      setToast("Decision logged");
      await loadPilot();
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
        <span>Loading pilot...</span>
      </section>
    );
  }

  const recommendation = state?.recommendation || {};
  const todayDecision = state?.today_decision || null;
  const forecastDecision = recommendation;
  const weather = state?.weather || {};
  const latestWeather = weather.latest || {};
  const forecastDetails = forecastDecision.details || {};
  const inputs = forecastDetails.inputs || {};
  const ruleState = forecastDetails.rules || {};
  const result = forecastDetails.result || {};
  const rules = forecastDecision.triggered_rules || [];
  const baseSchedule = forecastDecision.base_schedule || forecastDetails.result?.base_schedule || null;
  const baseMeta = baseSchedule
    ? `${baseSchedule.label || "Scheduler"} ${baseSchedule.start_time || ""}-${baseSchedule.stop_time || ""}`
    : ["config_fallback", "legacy_config_fallback"].includes(forecastDecision.base_source)
      ? "no active scheduler, config fallback"
      : "scheduler duration";
  const rainSensorWet = inputs.RainSensorWet === true ? "WET" : inputs.RainSensorWet === false ? "DRY" : "-";
  const soilEnabled = draft.soil_moisture_enabled !== false && draft.soil_moisture_enabled !== "false";
  const soilBinding = processBinding(state, "irrigation_soil_moisture");
  const selectedSoilSensor = entitySelectLabel(soilBinding.selected_entity);

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Irrigation Pilot</h2>
          <span>{error || (weather.openweather_configured ? `OpenWeather OK | last ${dateText(latestWeather.ts)}` : "OpenWeather config missing")}</span>
        </div>
        <div className="button-row compact pilot-actions">
          <IconButton icon={CloudRain} title="Fetch and store OpenWeather data now" onClick={fetchWeather} disabled={Boolean(busy)}>{busy === "weather" ? "Refreshing" : "Refresh weather"}</IconButton>
          <IconButton icon={Save} title="Store the current calculation in the decision log without sending a control command" onClick={createDecision} disabled={Boolean(busy)}>{busy === "decision" ? "Logging" : "Test log"}</IconButton>
          <IconButton icon={RefreshCw} title="Reload pilot page data" onClick={loadPilot} disabled={loading}>{loading ? "Refreshing" : "Refresh page"}</IconButton>
        </div>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Status</h2>
            <span>Navigator / Pilot</span>
          </div>
          <div className="mode-toggle">
            <button className={draft.mode !== "pilot" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => updateDraft("mode", "navigator")}>Navigator</button>
            <button className={draft.mode === "pilot" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => updateDraft("mode", "pilot")}>Pilot</button>
          </div>
          <div className="pilot-reason">
            <strong>{forecastDecision.reason || "-"}</strong>
          </div>
          <div className="button-row">
            <IconButton icon={Save} onClick={saveConfig} disabled={Boolean(busy)}>{busy === "save" ? "Saving" : "Save config"}</IconButton>
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Parameters</h2>
            <span>{selectedSoilSensor === "-" ? "rule engine thresholds" : `sensor ${selectedSoilSensor}`}</span>
          </div>
          <div className="pilot-form">
            <label>
              <span>Soil moisture enabled</span>
              <input
                type="checkbox"
                checked={soilEnabled}
                onChange={(event) => updateDraft("soil_moisture_enabled", event.target.checked)}
              />
            </label>
            {pilotFields.map(([key, label, unit, step]) => (
              <label key={key}>
                <span>{label} ({unit})</span>
                <input
                  type="number"
                  step={step}
                  value={draft[key] ?? ""}
                  onChange={(event) => updateDraft(key, event.target.value)}
                />
              </label>
            ))}
          </div>
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Current prediction</h2>
            <span>what would happen if watering started now</span>
          </div>
          <div className="decision-grid">
            <div><span>Scheduler base</span><strong>{unitValue(forecastDecision.base_duration, "min", 0)}</strong></div>
            <div><span>Pilot recommendation</span><strong>{unitValue(forecastDecision.final_duration, "min", 0)}</strong></div>
            <div><span>Executed</span><strong>NO</strong></div>
            <div><span>Active rules</span><strong>{ruleText(rules)}</strong></div>
          </div>
          <PilotDecisionFormula result={result} />
          <div className="pilot-reason muted-block">{forecastDecision.reason || "-"}</div>
          {todayDecision && (
            <div className="pilot-reason muted-block">
              Last final decision: {unitValue(todayDecision.final_duration, "min", 0)} | {decisionStatusText(todayDecision)} | {dateText(todayDecision.timestamp)}
            </div>
          )}
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Detailed decision info</h2>
            <span>inputs and result</span>
          </div>
          <Table
            rows={[
              { key: "Rain24h", value: unitValue(inputs.Rain24h, "mm", 1) },
              { key: "ForecastRain", value: unitValue(inputs.ForecastRain, "mm", 1) },
              { key: "POP", value: unitValue(inputs.POP, "%", 0) },
              { key: "Temperature", value: unitValue(inputs.Temperature, "C", 1) },
              { key: "Humidity", value: unitValue(inputs.Humidity, "%", 0) },
              { key: "Temperature source", value: inputs.TemperatureSource || "-" },
              { key: "Humidity source", value: inputs.HumiditySource || "-" },
              { key: "Forecast temperature", value: unitValue(inputs.ForecastTemperature, "C", 1) },
              { key: "OpenWeather humidity", value: unitValue(inputs.OpenWeatherHumidity, "%", 0) },
              { key: "Wind", value: unitValue(inputs.Wind, "m/s", 1) },
              { key: "Yard temperature", value: unitValue(inputs.LocalTemperature, "C", 1) },
              { key: "Yard humidity", value: unitValue(inputs.LocalHumidity, "%", 0) },
              { key: "Yard absolute humidity", value: unitValue(inputs.LocalAbsoluteHumidity, "g/m3", 1) },
              { key: "Yard sample age", value: unitValue(inputs.LocalSensorAgeHours, "h", 1) },
              { key: "Yard temp usable", value: inputs.LocalTemperatureUsable ? "YES" : "NO" },
              { key: "Yard humidity usable", value: inputs.LocalHumidityUsable ? "YES" : "NO" },
              { key: "Rain sensor wet", value: rainSensorWet },
              { key: "Rain sensor last wet", value: inputs.RainSensorLastWet ? dateText(inputs.RainSensorLastWet) : "-" },
              { key: "Rain sensor battery", value: unitValue(inputs.RainSensorBattery, "%", 0) },
              { key: "Rain sensor linkquality", value: numberText(inputs.RainSensorLinkquality, 0) },
              { key: "Garden soil sensor", value: inputs.SoilSensor || "-" },
              { key: "Garden soil moisture", value: unitValue(inputs.SoilMoisture, "%", 0) },
              { key: "Garden soil sample age", value: unitValue(inputs.SoilMoistureAgeHours, "h", 1) },
              { key: "Garden soil samples 24h", value: numberText(inputs.SoilMoistureSampleCount24h, 0) },
              { key: "Garden soil avg 24h", value: unitValue(inputs.SoilMoistureAvg24h, "%", 0) },
              { key: "Garden soil usable", value: inputs.SoilMoistureUsable ? "YES" : "NO" },
            ]}
            columns={[
              { key: "key", label: "Input" },
              { key: "value", label: "Value" },
            ]}
          />
          <div className="rule-list">
            {["rain_skip", "forecast_skip", "soil_wet_skip", "soil_wet_reduce", "soil_dry_increase", "heat_increase", "cold_decrease", "multiplier_clamped"].map((name) => (
              <span className={ruleState[name] ? "active" : ""} key={name}>{name}</span>
            ))}
          </div>
          <div className="pilot-result">
            <span>Base duration: {unitValue(result.base_duration, "min", 0)} ({baseMeta})</span>
            <span>Multiplier: {result.raw_multiplier == null ? "-" : `${numberText(result.raw_multiplier, 2)}x`} / applied {result.applied_multiplier == null ? "-" : `${numberText(result.applied_multiplier, 2)}x`}</span>
            <span>Corrections: {shortValue(result.corrections || [])}</span>
            <span>Final duration: {unitValue(result.final_duration, "min", 0)}</span>
          </div>
        </article>
      </section>

    </>
  );
}

export function PilotHistory() {
  const { data: state, loading, error, refresh: loadPilot } = usePolledContext("/api/context/irrigation_pilot");

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading pilot history...</span>
      </section>
    );
  }

  const weather = state?.weather || {};
  const latestWeather = weather.latest || {};
  const weatherEndpoint = latestWeather.raw?.endpoint || latestWeather.raw?.payload?.endpoint || latestWeather.raw?.source;
  const uvText = latestWeather.uv_index === null || latestWeather.uv_index === undefined ? "Not available" : numberText(latestWeather.uv_index, 1);
  const uvMeta = weatherEndpoint ? `${uvText} (${weatherEndpoint})` : uvText;

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Pilot History</h2>
          <span>{error || `${state?.decisions?.length || 0} decisions | weather ${latestWeather.ts ? dateText(latestWeather.ts) : "not available"}`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadPilot} disabled={loading}>{loading ? "Refreshing" : "Refresh pilot history"}</IconButton>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Weather snapshot</h2>
          <span>stored OpenWeatherMap data</span>
        </div>
        <Table
          rows={[latestWeather].filter((row) => row && row.id)}
          columns={[
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
            { key: "temperature_c", label: "Temp C" },
            { key: "humidity_percent", label: "RH %" },
            { key: "wind_speed_mps", label: "Wind" },
            { key: "rain_mm", label: "Rain" },
            { key: "forecast_rain_24h_mm", label: "Forecast rain" },
            { key: "forecast_pop_max_percent", label: "POP" },
            { key: "uv_index", label: "UV", render: () => uvMeta },
            { key: "cloudiness_percent", label: "Cloud" },
            { key: "pressure_hpa", label: "Pressure" },
            { key: "sunrise", label: "Sunrise", render: (row) => dateText(row.sunrise) },
            { key: "sunset", label: "Sunset", render: (row) => dateText(row.sunset) },
          ]}
        />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Decision log</h2>
          <span>{state?.decisions?.length || 0} entries</span>
        </div>
        <Table
          rows={state?.decisions || []}
          columns={[
            { key: "timestamp", label: "Time", render: (row) => dateText(row.timestamp) },
            { key: "mode", label: "Mode" },
            { key: "base_duration", label: "Base" },
            { key: "final_duration", label: "Final" },
            { key: "execution_status", label: "Status", render: (row) => decisionStatusText(row) },
            { key: "triggered_rules", label: "Rules", render: (row) => ruleText(row.triggered_rules) },
            { key: "reason", label: "Reason" },
          ]}
        />
      </section>
    </>
  );
}
