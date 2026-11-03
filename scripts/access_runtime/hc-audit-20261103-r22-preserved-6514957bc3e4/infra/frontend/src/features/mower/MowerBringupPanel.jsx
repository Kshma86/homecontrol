import React from "react";
import { Activity, Cpu, Radio, RefreshCw, Shield } from "lucide-react";
import { Card, IconButton } from "../../uiPrimitives";
import { displayBoolean } from "./mowerV3Model.mjs";
import { bringupView } from "./mowerBringupModel.mjs";
import useMowerServiceRead from "./useMowerServiceRead";

function Row({ label, value }) {
  return <div className="mower-data-row"><span>{label}</span><strong>{value ?? "Ismeretlen"}</strong></div>;
}

export function MowerBringupView({ reader }) {
  const { snapshot, receivedAt, now, error, loading, refresh } = reader;
  const view = bringupView(snapshot, receivedAt, now, error);
  const { state, health } = view;
  const identity = snapshot?.identity, update = snapshot?.update;
  return <section className="page-stack mower-page mower-v3-page">
    <div className="page-heading mower-heading"><div><span className="eyebrow">HC_BRINGUP · natív HTTP 3.1.0 · csak olvasás</span>
      <h1>Mower — HC kapcsolat</h1><p>Rover LAN-diagnosztika, valódi ESP/STM-forrásból.</p></div>
      <IconButton icon={RefreshCw} disabled={loading} onClick={refresh}>Frissítés</IconButton></div>
    <div className="mower-v3-stage"><Shield size={20} /><div><strong>Csak olvasó, nem üzembe helyezett</strong>
      <span>ARM / START / STOP / kézi vezérlés / roverre írás / frissítés tiltva. A paramétereditor csak HC-draft.</span></div></div>
    <div className="inline-alert warning" role="status"><Radio size={18} />{view.connection}
      {error || snapshot?.connection?.detail ? ` — ${error || snapshot.connection.detail}` : ""}</div>
    {snapshot?.connection?.status === "UNCONFIGURED" && <p>LAN-cím: {snapshot.configuration?.origin_configured ? "beállítva" : "hiányzik"}.
      Privát API-token: {snapshot.configuration?.token_configured ? "betöltve" : "hiányzik vagy nem olvasható"}. A titok csak a backendben marad.</p>}
    <div className="card-grid mower-v3-overview">
      <Card title="STM állapot" value={state?.state || "ISMERETLEN"} meta="Diagnosztika, nem mozgásengedély" icon={Cpu} />
      <Card title="Adatfrissesség" value={view.fresh ? "FRISS" : "NEM IGAZOLT"} meta={view.effectiveAge === null ? "Forráskor ismeretlen" : `${Math.ceil(view.effectiveAge)} ms · határ 1500 ms`} icon={Activity} />
      <Card title="Fizikai megállás" value="NEM IGAZOLT" meta="stopped=false nem mozgásmérés; nincs VESC-megállási bizonyíték" icon={Shield} />
      <Card title="Wi-Fi" value={displayBoolean(health?.wifi_connected, "KAPCSOLÓDVA", "NINCS KAPCSOLAT")} meta={health?.rssi_dbm == null ? "RSSI ismeretlen" : `${health.rssi_dbm} dBm`} icon={Radio} />
    </div>
    <div className="mower-v3-grid">
      <article className="panel"><div className="panel-head"><h2>Roverazonosság</h2><span>Utolsó megfigyelés</span></div>
        <div className="mower-data-list"><Row label="ESP firmware" value={identity?.esp_fw} /><Row label="STM firmware" value={identity?.stm_fw} />
          <Row label="ESP boot" value={identity?.esp_boot} /><Row label="STM boot" value={identity?.stm_boot} />
          <Row label="Flash-kiosztás" value={identity?.stm_flash_layout} /><Row label="Profil CRC" value={identity?.profile_crc} />
          <Row label="Üzembe helyezve" value={displayBoolean(identity?.commissioned, "Igen", "Nem")} />
          <Row label="Mozgásengedély" value={displayBoolean(identity?.motion_permitted, "Engedélyezett", "Tiltva")} /></div>
        <p>A compatible=true protokollegyezés, nem hardverminősítés. Nincs ellenőrzött működési profil.</p></article>
      <article className="panel"><div className="panel-head"><h2>Natív STM-állapot</h2><span>{view.fresh ? "Friss forrás" : "Ismeretlen / elavult"}</span></div>
        <div className="mower-data-list"><Row label="Állapot" value={state?.state} /><Row label="Élesítve" value={displayBoolean(state?.armed, "Igen", "Nem")} />
          <Row label="source_seq" value={state?.source_seq} /><Row label="state_seq" value={state?.state_seq} /><Row label="Vezérlési epoch" value={state?.control_epoch} />
          <Row label="Küldetéstároló" value={state?.store} /><Row label="Ok" value={state?.reason} /><Row label="Hibamaszk" value={state?.fault_mask} />
          <Row label="Biztonsági bemenetek" value={null} /><Row label="Fizikai megállási igazolás" value={null} /></div>
        {!view.fresh && snapshot?.state && <p>Az utolsó megfigyelés nem igazolja a rover jelenlegi állapotát.</p>}</article>
      <article className="panel"><div className="panel-head"><h2>Hálózat és futásidő</h2><span>Friss health-forrás szükséges</span></div>
        <div className="mower-data-list"><Row label="STM peer él" value={displayBoolean(health?.stm_peer_alive, "Igen", "Nem")} />
          <Row label="Szabad ESP heap (bájt)" value={health?.esp_internal_free_bytes} /><Row label="Legnagyobb belső blokk (bájt)" value={health?.esp_largest_internal_block} />
          <Row label="Deadline misses" value={health?.deadline_misses} /><Row label="UART input errors" value={health?.uart_input_errors} />
          <Row label="UART RX faults" value={health?.uart_rx_faults} /><Row label="UART TX expired" value={health?.uart_tx_expired} />
          <Row label="NTRIP" value={health?.ntrip_state} /><Row label="RTCM age (ms)" value={health?.rtcm_age_ms} /></div>
        <p>Hiányzó GNSS / IMU / VESC-adat ismeretlen, nem nulla és nem egészséges szenzor.</p></article>
      <article className="panel"><div className="panel-head"><h2>Updater — diagnosztika</h2><span>Utolsó megfigyelés, nincs session</span></div>
        <div className="mower-data-list"><Row label="Zárolás" value={displayBoolean(update?.locked, "Zárolva", "Feloldva")} />
          <Row label="Fázis" value={update?.phase} /><Row label="Hiba" value={update?.error} /><Row label="Részlet" value={update?.detail} />
          <Row label="Befejezhető" value={displayBoolean(update?.can_finish, "Igen", "Nem")} /></div>
        <p>A METADATA_ERROR valós, éles loader/session-metaadat nincs provisionálva. A HC nem oldja fel, nem töröl és nem bootstrapel.</p></article>
    </div>
    <details className="panel mower-v3-diagnostics"><summary>Csak olvasó diagnosztika — task / stack / boot / forrás</summary>
      <pre>{JSON.stringify(snapshot ? { connection: snapshot.connection, identity, state: snapshot.state, update,
        health: snapshot.health, freshness: snapshot.freshness, health_freshness: snapshot.health_freshness } : { status: "WAITING" }, null, 2)}</pre>
      <p>Utolsó megfigyelés; elavult adatok nem bizonyítanak aktuális állapotot.</p></details>
  </section>;
}

export default function MowerBringupPanel() {
  return <MowerBringupView reader={useMowerServiceRead({ endpoint: "/api/mower/v3/bringup/snapshot", timeoutMs: 14000 })} />;
}
