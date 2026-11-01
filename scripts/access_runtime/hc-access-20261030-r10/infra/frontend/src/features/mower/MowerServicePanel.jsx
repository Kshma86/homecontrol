import React from "react";
import { Activity, Cpu, Radio, RefreshCw, Shield } from "lucide-react";
import { Card, IconButton } from "../../uiPrimitives";
import { displayBoolean } from "./mowerV3Model.mjs";
import { serviceView } from "./mowerServiceModel.mjs";
import useMowerServiceRead from "./useMowerServiceRead";

function Row({ label, value }) {
  return <div className="mower-data-row"><span>{label}</span><strong>{value ?? "Ismeretlen"}</strong></div>;
}

export function MowerServiceView({ reader }) {
  const { snapshot, receivedAt, now, error, loading, refresh } = reader;
  const view = serviceView(snapshot, receivedAt, now, error);
  const observed = snapshot?.service;
  const current = view.current;
  const configuration = snapshot?.configuration;
  return <section className="page-stack mower-page mower-v3-page">
    <div className="page-heading mower-heading">
      <div><span className="eyebrow">FIRST_INSTALL_SERVICE · ABI1 · csak olvasás</span><h1>Mower — szerviz</h1>
        <p>LAN-kapcsolat, STM-diagnosztika és a roverre mentett paraméterek.</p></div>
      <IconButton icon={RefreshCw} disabled={loading} onClick={refresh}>Frissítés</IconButton>
    </div>
    <div className="mower-v3-stage"><Shield size={20} aria-hidden="true" /><div>
      <strong>Szervizmód — hajtás/kés tiltva</strong>
      <span>Csak GET-lekérdezés. Nincs ARM, kézi vezérlés, küldetés, paraméterírás vagy firmware-feltöltés.</span>
    </div></div>
    <div className="inline-alert warning" role="status"><Radio size={18} aria-hidden="true" />
      {view.connection}{error || snapshot?.connection?.detail ? ` — ${error || snapshot.connection.detail}` : ""}
    </div>
    {snapshot?.connection?.status === "UNCONFIGURED" && <p className="mower-safety-note">
      LAN-cím: {configuration?.origin_configured ? "beállítva" : "hiányzik"}. Privát API-token: {configuration?.token_configured ? "betöltve" : "hiányzik vagy nem olvasható"}.
      A token kizárólag a backend helyi konfigurációjába kerülhet, nem ebbe a felületbe.
    </p>}
    <div className="mower-v3-overview">
      <Card title="Kapcsolat" value={view.connection} meta="HTTP · helyi Wi-Fi" icon={Radio} />
      <Card title="STM" value={view.fresh ? "FRISS" : "NEM IGAZOLT"} meta={view.effectiveAge === null ? "Forráskor ismeretlen" : `${Math.ceil(view.effectiveAge)} ms · határ 3000 ms`} icon={Activity} />
      <Card title="Mozgásengedély" value={displayBoolean(current?.motion_permitted, "ENGEDÉLYEZETT", "TILTVA")} meta="Mentett paraméter nem mozgásengedély" icon={Shield} />
      <Card title="Paramétertároló" value={!error ? observed?.storage || "ISMERETLEN" : "ISMERETLEN"} meta="Nem alkalmazott konfiguráció" icon={Cpu} />
    </div>
    <div className="mower-v3-grid">
      <article className="panel"><div className="panel-head"><h2>Rover és hálózat</h2><span>Utolsó sikeres megfigyelés</span></div>
        <div className="mower-data-list">
          <Row label="ESP firmware" value={observed?.esp_firmware} /><Row label="STM firmware" value={observed?.stm_firmware} />
          <Row label="STM UID" value={observed?.stm_uid} /><Row label="LAN IP" value={observed?.ip} />
          <Row label="Hostname" value={observed?.hostname} /><Row label="Wi-Fi kapcsolódva" value={displayBoolean(observed?.wifi_connected, "Igen", "Nem")} />
          <Row label="Wi-Fi beállítva" value={displayBoolean(observed?.wifi_configured, "Igen", "Nem")} />
          <Row label="Beállító AP aktív" value={displayBoolean(observed?.setup_ap_active, "Igen", "Nem")} />
          <Row label="mDNS kész" value={displayBoolean(observed?.mdns_ready, "Igen", "Nem")} />
          <Row label="Szabad heap" value={observed?.free_heap === undefined ? null : `${observed.free_heap} bájt`} />
        </div>
      </article>
      <article className="panel"><div className="panel-head"><h2>Friss STM-visszajelzés</h2><span>{view.fresh ? "Szervizforrás" : "Ismeretlen / elavult"}</span></div>
        <div className="mower-data-list">
          <Row label="STM kapcsolat" value={displayBoolean(current?.stm_connected, "Élő", "Nincs")} />
          <Row label="CAN parkolva" value={displayBoolean(current?.can_parked, "Igen", "Nem")} />
          <Row label="Élesítés kikapcsolva" value={displayBoolean(current?.disarmed, "Igen", "Nem")} />
          <Row label="Kimenetek szoftveresen tiltva" value={displayBoolean(current?.outputs_inhibited, "Igen", "Nem")} />
          <Row label="Paraméterek alkalmazva" value={displayBoolean(current?.applied, "Igen", "Nem")} />
          <Row label="Üzembe helyezve" value={displayBoolean(current?.commissioned, "Igen", "Nem")} />
        </div>
        <p>A CAN-parkolás és a szoftveres tiltás nem bizonyít fizikai tápmegszakítást vagy mechanikai megállást.</p>
      </article>
    </div>
    <article className="panel mower-v3-diagnostics"><div className="panel-head"><h2>Roverre mentett paraméterek — csak olvasás</h2><span>Utolsó sikeres readback</span></div>
      <div className="mower-data-list">
        <Row label="Tárolási revízió" value={observed?.revision} /><Row label="Eredménykód" value={observed?.code} />
        <Row label="Paraméter CRC" value={observed?.parameters_crc} /><Row label="STM paraméter CRC" value={observed?.stm_parameters_crc} />
      </div>
      <p>{snapshot?.parameters ? "Mentett adat, nem ACTIVE/APPLIED. Ez nem a HC draftja, és nem töltjük automatikusan az editorba." : "Nincs visszaolvasott paraméterobjektum. Az EMPTY/revision=0 üres tárolót jelent, nem működő alapbeállítást."}</p>
      {snapshot?.parameters && <pre>{JSON.stringify(snapshot.parameters, null, 2)}</pre>}
      {(error || !view.fresh) && observed && <p>Az utolsó megfigyelés nem igazolja a jelenlegi STM-állapotot.</p>}
    </article>
  </section>;
}

export default function MowerServicePanel() {
  return <MowerServiceView reader={useMowerServiceRead()} />;
}
