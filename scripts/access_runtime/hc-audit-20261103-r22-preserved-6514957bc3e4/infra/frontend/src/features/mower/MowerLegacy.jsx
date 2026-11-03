import React from "react";
import { Archive, Compass, Crosshair, Cpu, ExternalLink, Gauge, MapPin, Navigation, Plus, Power, Radio, RefreshCw, RotateCcw, Save, Shield, Square, Trash2, Upload, Wifi, Play } from "lucide-react";
import { Card, IconButton } from "../../uiPrimitives";
import "./mowerV3.css";

// Presentation only: do not import the old controller, live map or notes widget.
// They start network effects even when their controls are disabled.
function InactiveButton({ icon, children, className = "secondary" }) {
  return <IconButton icon={icon} className={className} type="button" disabled>{children}</IconButton>;
}

function DataRows({ rows }) {
  return <div className="mower-data-list">{rows.map(([label, detail]) =>
    <div className="mower-data-row" key={label}><span>{label}</span><strong>—</strong>{detail && <small>{detail}</small>}</div>
  )}</div>;
}

export default function MowerLegacy() {
  return <section className="page-stack mower-page mower-legacy-preview">
    <div className="page-heading mower-heading"><div>
      <span className="eyebrow">STM32H743 · ESP32 remote · Archivált felület</span>
      <h1>Mower Legacy</h1>
      <p>A korábbi Robot mower felület mezőnézete. Csak megtekintésre, minden művelet letiltva.</p>
    </div><div className="mower-heading-actions">
      <span className="status-pill">LEGACY · INAKTÍV</span>
      <InactiveButton icon={RefreshCw}>Refresh</InactiveButton>
      <InactiveButton icon={ExternalLink}>Direct remote</InactiveButton>
    </div></div>
    <div className="inline-alert warning"><Archive size={18} aria-hidden="true" />
      Statikus mezőnézet, nem korábbi mentett vagy élő roveradat. A „—” nem ismert értéket jelöl.
      Nincs háttérlekérés, térképbetöltés, kapcsolat vagy parancsküldés.
    </div>

    <div className="card-grid mower-overview">
      {[
        ["Robot", "state / mode · armed · fault", Power],
        ["GNSS", "fix_name · satellites · HDOP", MapPin],
        ["Heading", "compass_deg · north_valid", Compass],
        ["Route", "playing · index / count · distance_m", Navigation],
        ["Safety", "Robot state · Hiba oka", Shield],
        ["Alrendszer", "healthy · Wi-Fi RSSI · STM · CAN", Radio],
      ].map(([title, meta, icon]) => <Card key={title} title={title} value="—" meta={meta} icon={icon} />)}
    </div>

    <div className="mower-main-grid">
      <article className="panel mower-control-panel">
        <div className="panel-head"><h2><Shield size={18} /> Safety &amp; control</h2><span>MQTT commands · letiltva</span></div>
        <div className="mower-emergency">
          <button type="button" className="mower-stop" disabled><Square size={24} fill="currentColor" />STOP</button>
          <div><strong>Immediate motion stop</strong><span>Legacy STOP is disabled in this preview.</span></div>
        </div>
        <div className="mower-button-grid">
          {[["Arm", Power], ["Disarm", Power], ["Clear E-stop", RotateCcw], ["Clear fault", Shield], ["Safety reset", RefreshCw], ["Fast telemetry", Radio], ["Web UI ON / OFF", ExternalLink]].map(([label, icon]) => <InactiveButton key={label} icon={icon}>{label}</InactiveButton>)}
        </div>
        <div className="mower-set-control">
          <label>Blade target <span>RPM</span><input type="number" min="0" max="25000" step="100" placeholder="—" disabled /></label>
          <InactiveButton icon={Gauge}>Set blade</InactiveButton><InactiveButton icon={Square}>Blade stop</InactiveButton>
        </div>
      </article>
      <article className="panel mower-compass-panel">
        <div className="panel-head"><h2><Compass size={18} /> IMU instruments</h2><span>Statikus</span></div>
        <div className="mower-instruments">
          <div className="mower-instrument"><strong>Heading</strong><div className="mower-compass"><div className="mower-compass-ring"><span>N</span><b>—°</b></div></div></div>
          <div className="mower-instrument"><strong>Attitude</strong><DataRows rows={[["Pitch", "pitch_deg · °"], ["Roll", "roll_deg · °"], ["IMU", "alive"]]} /></div>
        </div>
        <div className="mower-set-control compact">
          <label>Target <span>degrees</span><input type="number" min="0" max="359" step="1" placeholder="—" disabled /></label>
          <InactiveButton icon={Crosshair}>Turn to</InactiveButton>
        </div>
        <div className="mower-button-grid three">
          {[["Set North", Compass], ["Auto North", Crosshair], ["Stop Auto North", Square], ["Assist on", Navigation], ["Cancel", Square]].map(([label, icon]) => <InactiveButton key={label} icon={icon}>{label}</InactiveButton>)}
        </div>
        <DataRows rows={[["Auto North", "auto_north_status / auto_north · auto_north_active"], ["Samples", "auto_north_samples"]]} />
        <div className="mower-heading-presets">
          {[["N", "0°"], ["E", "90°"], ["S", "180°"], ["W", "270°"], ["Turn around", "+180°"]].map(([label, angle]) => <button key={label} type="button" disabled>{label}<small>{angle}</small></button>)}
        </div>
      </article>
    </div>

    <article className="panel mower-safety-panel">
      <div className="panel-head"><h2><Shield size={18} /> Safety &amp; faults</h2><span>—</span></div>
      <div className="mower-safety-grid">{["Robot state", "Hiba oka", "E-stop", "Bumper", "Lift", "Tilt input", "IMU tilt", "Perimeter wire"].map((label) => <div key={label}><span>{label}</span><strong>—</strong></div>)}</div>
    </article>

    <article className="panel mower-manual-panel">
      <div className="panel-head"><h2><Gauge size={18} /> Manual cruise control</h2><span>INAKTÍV</span></div>
      <div className="mower-manual-layout">
        <div className="mower-cruise locked">
          <div className="mower-cruise-speed"><span>Target speed</span><strong>—</strong><small>RPM</small></div>
          <div className="mower-cruise-buttons">{["+500", "−500", "Reverse", "Straight", "STOP"].map((label) => <button key={label} type="button" disabled>{label}</button>)}</div>
          <label>Drive RPM <b>—</b><input type="range" min="-6000" max="6000" step="100" defaultValue="0" disabled /></label>
          <label>Steering correction <b>—</b><input type="range" min="-1500" max="1500" step="50" defaultValue="0" disabled /></label>
          <div className="mower-cruise-lock"><Shield size={25} /><strong>Drive locked</strong></div>
        </div>
        <div className="mower-manual-side">
          <div className="mower-manual-values"><div><span>Forward</span><strong>— RPM</strong></div><div><span>Turn</span><strong>— RPM</strong></div></div>
          <p>ESP WebSocket kapcsolat letiltva.</p><code>manual_control.url · —</code>
          <div className="mower-manual-actions"><InactiveButton icon={Radio}>Connect WebSocket</InactiveButton><InactiveButton icon={Shield}>Claim control</InactiveButton><InactiveButton icon={Shield}>Disconnect WebSocket</InactiveButton></div>
        </div>
      </div>
    </article>

    <article className="panel mower-route-panel">
      <div className="panel-head"><h2><Navigation size={18} /> RTK térkép és waypoint útvonal</h2><span>count / max · playing · phase · index · transport</span></div>
      <div className="mower-route-readiness">{[["GNSS fix", MapPin], ["RTK quality", Crosshair], ["North reference", Compass], ["Route controller", Cpu]].map(([label, Icon]) => <div key={label}><Icon size={16} /><span>{label}</span><strong>—</strong></div>)}</div>
      <div className="mower-rtk-map-section">
        <div className="mower-rtk-map-section-head"><h3><MapPin size={18} /> Élő pozíció és nyomvonal</h3><span>Letiltva</span></div>
        <div className="mower-rtk-map-layout">
          <div className="mower-rtk-map mower-legacy-map-placeholder">Térkép és nyomvonal helye — nincs térképszolgáltatás betöltve.</div>
          <div className="mower-rtk-map-data">
            <DataRows rows={[["Orientáció", "heading_deg · heading_source · °"], ["WGS84", "lat · lon"], ["Minták", "nyomvonalpontok száma"]]} />
            <InactiveButton icon={Crosshair}>Mower középre</InactiveButton><InactiveButton icon={Save}>Nyomvonal mentése</InactiveButton><InactiveButton icon={Trash2}>Nyomvonal törlése</InactiveButton>
          </div>
        </div>
      </div>
      <div className="mower-route-toolbar">
        {[["Record current point", Plus], ["Play route", Play], ["Route stop", Square], ["AUTO status", Radio], ["Útvonal mentése", Save], ["Clear points", Trash2]].map(([label, icon]) => <InactiveButton key={label} icon={icon}>{label}</InactiveButton>)}
      </div>
      <div className="mower-route-live">{["Target", "Phase", "Distance", "Bearing", "Held heading", "Heading error"].map((label) => <div key={label}><span>{label}</span><strong>—</strong></div>)}</div>
      <div className="mower-route-table-wrap"><table className="mower-route-table">
        <thead><tr>{["#", "Latitude", "Longitude", "Fix", "HDOP", "Status"].map((label) => <th key={label}>{label}</th>)}</tr></thead>
        <tbody><tr><td colSpan="6" className="empty">Statikus mezőnézet — nincs betöltött útvonal.</td></tr></tbody>
      </table></div>
    </article>

    <article className="panel mower-firmware-panel">
      <div className="panel-head"><h2><Cpu size={18} /> STM32 firmware</h2><span>INAKTÍV</span></div>
      <div className="mower-firmware-versions">{["Current ESP firmware", "Current STM firmware"].map((label) => <div key={label}><span>{label}</span><strong>—</strong></div>)}</div>
      <div className="mower-firmware-layout">
        <div className="mower-firmware-copy"><strong>Updater status · message / error · —</strong><span>Staging, méret és CRC32 ellenőrzés, külön aktiválás.</span><div className="mower-update-progress"><i style={{ width: "0%" }} /></div><small>bytes / expected · CRC32 · —</small></div>
        <div className="mower-firmware-actions">
          <label className="mower-file-picker"><span>STM binary</span><input type="file" accept=".bin,application/octet-stream" disabled /><small>Maximum 2 MiB</small></label>
          <InactiveButton icon={Upload}>Upload &amp; verify</InactiveButton><InactiveButton icon={Power}>Activate staged</InactiveButton><InactiveButton icon={RotateCcw}>Reset STM</InactiveButton>
        </div>
      </div>
    </article>

    <div className="mower-detail-grid">
      <article className="panel"><div className="panel-head"><h2><MapPin size={18} /> RTK GNSS</h2><span>fix_name · —</span></div>
        <DataRows rows={[["Position", "lat · lon"], ["Satellites", "sats · HDOP"], ["Movement", "speed_kmh · course_deg"], ["NTRIP", "ntrip_state · rtcm_bytes"], ["Correction", "correction_age_s · rtcm_age_ms"]]} />
      </article>
      <article className="panel"><div className="panel-head"><h2><Gauge size={18} /> Motors</h2><span>VESC telemetry</span></div><div className="mower-motors">
        {["Left drive", "Right drive", "Blade"].map((label, index) => <div className="mower-motor" key={label}><span>M{index + 1}</span><strong>{label}</strong><b>— RPM</b><small>current_a · A · duty_ratio · % · —</small></div>)}
      </div></article>
      <article className="panel"><div className="panel-head"><h2><Wifi size={18} /> Connectivity</h2><span>broker · —</span></div>
        <DataRows rows={[["ESP", "fw.esp"], ["STM", "fw.stm"], ["ESP address", "ip · rssi · dBm"], ["CAN", "can_alive · can_age_ms"], ["Web UI", "legacy_web_ui · mqtt_connected"], ["Contract", "contract_reported · contract_expected · compatible"], ["Command ACK", "accepted · message"], ["ACK command", "command · code"], ["Request ID", "request_id"], ["HC ACK pairing", "MATCHED / PENDING / UNKNOWN"]]} />
      </article>
      <article className="panel"><div className="panel-head"><h2><Cpu size={18} /> ESP diagnostics</h2><span>—</span></div>
        <div className="mower-button-grid mower-diagnostics-toggle"><InactiveButton icon={Gauge}>Enable diagnostics</InactiveButton><InactiveButton icon={Gauge}>Disable diagnostics</InactiveButton></div>
        <DataRows rows={[["Free heap", "free_heap · min_free_heap · B"], ["Max allocation", "max_alloc_heap · B"], ["Loop samples", "loop_count · loop_last_us"], ["Loop time", "loop_avg_us · loop_max_us · µs"], ["Route payload", "mqtt_route_payload_bytes · B"], ["MQTT publish", "mqtt_published · mqtt_failed"], ["MQTT commands", "mqtt_commands · mqtt_command_failed"]]} />
      </article>
    </div>

    <section className="notes-page notes-page-embedded">
      <article className="panel notes-entry-panel">
        <div className="panel-head"><h2>New Mower Note</h2><span>Issues | Requests</span></div>
        <div className="notes-entry-form">
          <div className="mode-toggle notes-type-toggle"><button type="button" className="mode-btn" disabled>Issues</button><button type="button" className="mode-btn" disabled>Requests</button></div>
          <textarea placeholder="New mower issue / request..." disabled /><InactiveButton icon={Plus}>Add</InactiveButton>
        </div>
      </article>
      <article className="panel notes-panel"><div className="panel-head"><h2>Mower Notes</h2><span>Statikus</span></div><div className="table-wrap notes-table-wrap"><table className="notes-table">
        <thead><tr>{["Type", "Status", "Text", "Comment", "Created", "Action"].map((label) => <th key={label}>{label}</th>)}</tr></thead>
        <tbody><tr><td colSpan="6">Nincsenek betöltött jegyzetek.</td></tr></tbody>
      </table></div></article>
    </section>
    <button className="mower-mobile-stop" type="button" disabled><Square size={18} fill="currentColor" /> EMERGENCY STOP · LEGACY INAKTÍV</button>
  </section>;
}
