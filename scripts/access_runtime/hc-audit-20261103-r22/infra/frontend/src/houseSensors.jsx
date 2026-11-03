import { Table } from "./uiPrimitives";
import { dateText, metricNumber, numberText, unitValue } from "./formatters";

export const HOUSE_STATUS_ROOMS = [
  "Előszoba",
  "Konyha",
  "Nappali",
  "Lenti fürdő",
  "Zsófi szoba",
  "Háló szoba",
  "Zöld szoba",
  "Felső előszoba",
  "Fenti fürdő",
  "Lila szoba",
  "Nyárikonyha",
  "Pince",
  "Garázs",
];

export const SENSOR_SNAPSHOT_ROOMS = [...HOUSE_STATUS_ROOMS, "Udvar"];

export const SENSOR_RANGE_OPTIONS = [
  { value: "1h", label: "1h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
];

const ROOM_NAME_ALIASES = {
  "fehér szoba": "Háló szoba",
  "feher szoba": "Háló szoba",
  "hálószoba": "Háló szoba",
  "haloszoba": "Háló szoba",
  "nyári konyha": "Nyárikonyha",
  "nyari konyha": "Nyárikonyha",
};

export function roomDisplayName(name) {
  const text = String(name || "").trim();
  return ROOM_NAME_ALIASES[text.toLocaleLowerCase("hu-HU")] || text || "-";
}

export function roomKey(name) {
  return roomDisplayName(name)
    .toLocaleLowerCase("hu-HU")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function OpeningSensorIcons({ sensors = [] }) {
  if (!sensors.length) return <span className="home-window-icons empty" aria-label="Nincs ablakérzékelő">-</span>;
  const orderedSensors = sensors.slice().sort((a, b) => {
    const posA = Number.isFinite(Number(a.room_position)) ? Number(a.room_position) : Number.POSITIVE_INFINITY;
    const posB = Number.isFinite(Number(b.room_position)) ? Number(b.room_position) : Number.POSITIVE_INFINITY;
    if (posA !== posB) return posA - posB;
    return String(a.opening_label || a.entity_name || "").localeCompare(String(b.opening_label || b.entity_name || ""), "hu");
  });
  return (
    <span className="home-window-icons" aria-label={`${orderedSensors.length} ablakérzékelő`}>
      {orderedSensors.map((sensor) => {
        const closed = sensor.contact === true;
        const alert = sensor.battery_low === true || sensor.contact == null || sensor.rain_alert_active === true;
        const openingType = sensor.opening_type === "door" ? "door" : "window";
        const label = openingType === "door" ? "Ajtó" : "Ablak";
        const name = sensor.opening_label || sensor.entity_name || label;
        const mosquito = sensor.has_mosquito_net ? " | szúnyogháló" : "";
        const rainAlert = sensor.rain_alert_enabled ? " | eső riasztás előkészítve" : "";
        const alertText = alert ? ` | ${sensor.rain_alert_active ? "eső riasztás" : sensor.battery_low ? "szenzor gond: alacsony elem" : "szenzor gond: nincs kontakt adat"}` : "";
        const position = sensor.room_position == null ? "" : ` | #${sensor.room_position}`;
        const title = `${name}: ${closed ? "csukva" : "nyitva"}${position}${mosquito}${rainAlert}${alertText} | ${sensor.battery == null ? "elem -" : `elem ${numberText(sensor.battery, 0)}%`} | ${dateText(sensor.latest_ts || sensor.contact_ts)}`;
        return (
          <span className={`home-opening-icon ${openingType} ${alert ? "alert" : closed ? "closed" : "open"}`} title={title} key={sensor.entity_id || sensor.entity_name} aria-label={title}>
            <span className="opening-cross" aria-hidden="true" />
            <span className="opening-door-window" aria-hidden="true" />
            <span className="opening-handle" aria-hidden="true" />
          </span>
        );
      })}
    </span>
  );
}

export function sensorsByRoom(sensors = []) {
  return sensors.reduce((acc, sensor) => {
    const key = roomKey(sensor.location || sensor.entity_name || sensor.device_name);
    if (!key || key === "unassigned") return acc;
    const current = acc.get(key);
    if (current && sensorRank(current) >= sensorRank(sensor)) return acc;
    acc.set(key, sensor);
    return acc;
  }, new Map());
}

function sensorRank(sensor) {
  const hasTemperature = metricNumber(sensor, "latest_temperature") !== null;
  const hasHumidity = metricNumber(sensor, "latest_humidity") !== null;
  const latestTs = sensor?.latest_ts ? new Date(sensor.latest_ts).getTime() : 0;
  return (hasTemperature ? 2 : 0) + (hasHumidity ? 2 : 0) + (Number.isFinite(latestTs) ? latestTs / 1e13 : 0);
}

export function openingSensorsByRoom(openingSensors = []) {
  return openingSensors.reduce((acc, sensor) => {
    const key = roomKey(sensor.location);
    if (!key || key === "unassigned") return acc;
    if (!acc.has(key)) acc.set(key, []);
    acc.get(key).push(sensor);
    return acc;
  }, new Map());
}

export function roomStatusRows(sensors = [], openingSensors = [], rooms = HOUSE_STATUS_ROOMS) {
  const sensorByRoom = sensorsByRoom(sensors);
  const openingByRoom = openingSensorsByRoom(openingSensors);
  return rooms.map((room) => {
    const key = roomKey(room);
    return {
      key,
      room,
      sensor: sensorByRoom.get(key) || null,
      openings: openingByRoom.get(key) || [],
    };
  });
}

export function latestRoomStatusTs(sensor, openings = []) {
  const timestamps = [
    sensor?.latest_ts,
    ...openings.map((opening) => opening.latest_ts || opening.contact_ts),
  ]
    .map((value) => (value ? new Date(value).getTime() : NaN))
    .filter(Number.isFinite);
  if (!timestamps.length) return null;
  return new Date(Math.max(...timestamps)).toISOString();
}

export function SensorSnapshotTable({ sensors = [], openingSensors = [] }) {
  const rows = roomStatusRows(sensors, openingSensors, SENSOR_SNAPSHOT_ROOMS);
  return (
    <Table
      className="sensor-snapshot-table"
      rows={rows}
      columns={[
        { key: "room", label: "Sensor", render: (row) => roomDisplayName(row.room) },
        { key: "window", label: "Window", render: (row) => <OpeningSensorIcons sensors={row.openings} /> },
        { key: "latest_temperature", label: "Temp", render: (row) => unitValue(row.sensor?.latest_temperature, "C", 1) },
        { key: "latest_humidity", label: "RH", render: (row) => unitValue(row.sensor?.latest_humidity, "%", 0) },
        { key: "latest_pressure_hpa", label: "hPa", render: (row) => unitValue(row.sensor?.latest_pressure_hpa, "hPa", 1) },
        { key: "latest_absolute_humidity_g_m3", label: "Abs", render: (row) => unitValue(row.sensor?.latest_absolute_humidity_g_m3, "g/m3", 1) },
        { key: "latest_ts", label: "Updated", render: (row) => dateText(latestRoomStatusTs(row.sensor, row.openings)) },
      ]}
    />
  );
}

export function SensorRangeSwitch({ value = "24h", onChange, label = "Chart range", customHours = "", onCustomHoursChange, onCustomApply }) {
  const hasCustomInput = Boolean(onCustomHoursChange || onCustomApply);
  return (
    <div className={`mode-switch sensor-range-switch ${hasCustomInput ? "with-custom" : ""}`} aria-label={label}>
      {SENSOR_RANGE_OPTIONS.map((option) => (
        <button className={value === option.value ? "active" : ""} type="button" onClick={() => onChange?.(option.value)} key={option.value}>
          {option.label}
        </button>
      ))}
      {hasCustomInput && (
        <input
          type="number"
          min="1"
          max="720"
          step="1"
          inputMode="numeric"
          placeholder="h"
          title="Hours back"
          value={customHours}
          onChange={(event) => onCustomHoursChange?.(event.target.value)}
          onBlur={() => onCustomApply?.()}
          onKeyDown={(event) => {
            if (event.key === "Enter") onCustomApply?.();
          }}
        />
      )}
    </div>
  );
}
