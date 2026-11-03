import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Compass, Crosshair, ExternalLink, Gauge, MapPin, Navigation,
  Power, Radio, RefreshCw, RotateCcw, Save, Shield, Square, Upload, Wifi, Cpu, Plus, Trash2, Play,
} from "lucide-react";
import { api, readJsonResponse, usePolledContext } from "../../apiClient";
import { Card, IconButton } from "../../uiPrimitives";
import Notes from "../notes/Notes";

const value = (source, keys, fallback = "-") => {
  for (const key of keys) {
    if (source?.[key] !== undefined && source?.[key] !== null) return source[key];
  }
  return fallback;
};

const yesNo = (current) => current === true || current === 1 || current === "1" ? "OK" : "No";
const num = (current, digits = 0) => Number.isFinite(Number(current)) ? Number(current).toFixed(digits) : "-";

const FAULT_NAMES_HU = {
  CAN_TX: "CAN küldési hiba",
  CAN_BUS_OFF: "CAN bus-off",
  MOTOR_TIMEOUT: "Motor visszajelzés időtúllépés",
  ESTOP: "Vészleállító aktív",
  BUMPER: "Ütközésérzékelő aktív",
  LIFT: "Megemelés érzékelve",
  TILT: "Túl nagy dőlés",
  PERIMETER: "Határolóvezeték hiba",
  LINK_TIMEOUT: "Vezérlőkapcsolat időtúllépés",
};

function faultDescription(mask, name) {
  const normalizedName = String(name || "").trim().toUpperCase();
  if (normalizedName) return FAULT_NAMES_HU[normalizedName] || normalizedName.replaceAll("_", " ");
  const numericMask = Number(mask);
  if (!numericMask) return "Nincs aktív hiba";
  const decoded = [];
  if (numericMask & 0x00000001) decoded.push("CAN küldési hiba");
  if (numericMask & 0x00000002) decoded.push("CAN bus-off");
  if (numericMask & 0x00000004) decoded.push("Motor visszajelzés időtúllépés");
  if (numericMask & 0x00000008) decoded.push("Vészleállító aktív");
  if (numericMask & 0x00000010) decoded.push("Ütközésérzékelő aktív");
  if (numericMask & 0x00000020) decoded.push("Megemelés érzékelve");
  if (numericMask & 0x00000040) decoded.push("Túl nagy dőlés");
  if (numericMask & 0x00000080) decoded.push("Határolóvezeték hiba");
  if (numericMask & 0x00000100) decoded.push("Vezérlőkapcsolat időtúllépés");
  const knownMask = 0x000001ff;
  const unknownMask = (numericMask >>> 0) & ~knownMask;
  if (unknownMask) decoded.push(`Ismeretlen bit: 0x${(unknownMask >>> 0).toString(16).padStart(8, "0").toUpperCase()}`);
  return decoded.length ? decoded.join(" · ") : "Ismeretlen vezérlőhiba";
}

function manualClientId() {
  const key = "hc-mower-manual-client-id";
  const existing = window.sessionStorage.getItem(key);
  if (existing) return existing;
  const created = `hc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  window.sessionStorage.setItem(key, created);
  return created;
}

function StatePill({ ok, children, warn = false }) {
  return <span className={`mower-pill ${ok ? "ok" : warn ? "warn" : "off"}`}>{children}</span>;
}

function DataRow({ label, value: current, detail }) {
  return <div className="mower-data-row"><span>{label}</span><strong>{current}</strong>{detail && <small>{detail}</small>}</div>;
}

function ArtificialHorizon({ pitch, roll, alive }) {
  const safePitch = Number.isFinite(Number(pitch)) ? Number(pitch) : 0;
  const safeRoll = Number.isFinite(Number(roll)) ? Number(roll) : 0;
  const shownPitch = Math.max(-45, Math.min(45, safePitch));
  return (
    <div className={`mower-horizon ${alive ? "live" : "offline"}`} aria-label={`Artificial horizon, pitch ${safePitch.toFixed(1)} degrees, roll ${safeRoll.toFixed(1)} degrees`}>
      <div className="mower-horizon-bank-scale"><i className="b60" /><i className="b30" /><i className="b0" /><i className="p30" /><i className="p60" /></div>
      <div className="mower-horizon-world" style={{ "--pitch-offset": `${shownPitch * 2.15}px`, "--roll-angle": `${-safeRoll}deg` }}>
        <div className="mower-horizon-sky" />
        <div className="mower-horizon-ground" />
        <div className="mower-horizon-line" />
        <div className="mower-pitch-ladder">
          {[-30, -20, -10, 10, 20, 30].map((mark) => <span className={mark < 0 ? "up" : "down"} style={{ "--mark": mark }} key={mark}><i />{Math.abs(mark)}</span>)}
        </div>
      </div>
      <div className="mower-horizon-aircraft"><i /><b /><i /></div>
      <div className="mower-horizon-pointer" />
      <div className="mower-horizon-readout"><span>PITCH <b>{safePitch.toFixed(1)}°</b></span><span>ROLL <b>{safeRoll.toFixed(1)}°</b></span></div>
    </div>
  );
}

function RtkLiveMap({ pose }) {
  const L = window.L;
  const mapElementRef = useRef(null);
  const mapRef = useRef(null);
  const roverMarkerRef = useRef(null);
  const trackLayerRef = useRef(null);
  const trackShadowRef = useRef(null);
  const [track, setTrack] = useState([]);

  useEffect(() => {
    if (!L || !mapElementRef.current || mapRef.current) return undefined;
    const map = L.map(mapElementRef.current, { zoomControl: true, maxZoom: 22 }).setView([47.15, 19.5], 7);
    const streetLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxNativeZoom: 19,
      maxZoom: 22,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    });
    const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 22,
      attribution: "Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    });
    streetLayer.addTo(map);
    L.control.layers({ Térkép: streetLayer, Műhold: satelliteLayer }, null, { position: "topright", collapsed: false }).addTo(map);
    trackShadowRef.current = L.polyline([], { color: "#071018", weight: 9, opacity: 0.75, lineCap: "round", lineJoin: "round" }).addTo(map);
    trackLayerRef.current = L.polyline([], { color: "#40d9ff", weight: 5, opacity: 1, lineCap: "round", lineJoin: "round" }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      roverMarkerRef.current = null;
      trackLayerRef.current = null;
      trackShadowRef.current = null;
    };
  }, [L]);

  useEffect(() => {
    const lat = Number(pose?.lat);
    const lon = Number(pose?.lon);
    if (!mapRef.current || !pose?.valid || !Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const latLng = [lat, lon];
    const heading = Number.isFinite(Number(pose?.heading_deg)) ? Number(pose.heading_deg) : 0;
    const markerHtml = `<span class="mower-map-rover-arrow" style="transform:rotate(${heading}deg)"></span>`;
    const icon = L.divIcon({ className: `mower-map-rover ${pose?.rtk_fixed ? "fixed" : ""}`, html: markerHtml, iconSize: [38, 38], iconAnchor: [19, 19] });
    if (!roverMarkerRef.current) {
      roverMarkerRef.current = L.marker(latLng, { icon, zIndexOffset: 1000 }).addTo(mapRef.current);
      mapRef.current.setView(latLng, 21);
    } else {
      roverMarkerRef.current.setLatLng(latLng).setIcon(icon);
    }
    setTrack((current) => {
      const previous = current[current.length - 1];
      if (previous && previous[0] === lat && previous[1] === lon) return current;
      const next = [...current, latLng].slice(-500);
      trackShadowRef.current?.setLatLngs(next);
      trackLayerRef.current?.setLatLngs(next);
      return next;
    });
  }, [pose?.valid, pose?.lat, pose?.lon, pose?.heading_deg, pose?.rtk_fixed]);

  const centerOnMower = () => {
    const lat = Number(pose?.lat);
    const lon = Number(pose?.lon);
    if (mapRef.current && pose?.valid && Number.isFinite(lat) && Number.isFinite(lon)) mapRef.current.setView([lat, lon], Math.max(mapRef.current.getZoom(), 21));
  };

  function saveTrack() {
    if (!track.length) return;
    const savedAt = new Date();
    const geoJson = {
      type: "FeatureCollection",
      properties: {
        name: "HomeControl live RTK mower track",
        saved_at: savedAt.toISOString(),
        point_count: track.length,
        coordinate_system: "WGS84",
      },
      features: [
        ...(track.length > 1 ? [{
          type: "Feature",
          properties: { name: "Live RTK track", role: "track", point_count: track.length },
          geometry: { type: "LineString", coordinates: track.map(([lat, lon]) => [lon, lat]) },
        }] : []),
        ...track.map(([lat, lon], index) => ({
          type: "Feature",
          properties: { order: index + 1, role: "track_point" },
          geometry: { type: "Point", coordinates: [lon, lat] },
        })),
      ],
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(geoJson, null, 2)], { type: "application/geo+json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `mower-live-rtk-track-${savedAt.toISOString().replace(/[:.]/g, "-")}.geojson`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function resetMap() {
    setTrack([]);
    trackShadowRef.current?.setLatLngs([]);
    trackLayerRef.current?.setLatLngs([]);
  }

  return (
    <section className="mower-rtk-map-section" aria-label="Élő RTK pozíció">
      <div className="mower-rtk-map-section-head"><h3><MapPin size={17} /> Élő pozíció és nyomvonal</h3><StatePill ok={pose?.rtk_fixed} warn={pose?.valid}>{pose?.rtk_fixed ? "RTK FIX" : pose?.valid ? pose?.fix_name || "FIX" : "NO FIX"}</StatePill></div>
      <div className="mower-rtk-map-layout">
        <div ref={mapElementRef} className="mower-rtk-map" role="application" aria-label="Interaktív OpenStreetMap az élő mower RTK pozícióval" />
        <div className="mower-rtk-map-data">
          <DataRow label="Orientáció" value={`${num(pose?.heading_deg, 1)}°`} detail={pose?.heading_source || "nincs adat"} />
          <DataRow label="WGS84" value={`${num(pose?.lat, 8)}, ${num(pose?.lon, 8)}`} />
          <DataRow label="Minták" value={track.length} detail="csak ebben a böngésző-munkamenetben" />
          <button type="button" onClick={centerOnMower} disabled={!pose?.valid}><Crosshair size={15} /> Mower középre</button>
          <button type="button" className="secondary" onClick={saveTrack} disabled={!track.length}><Save size={15} /> Nyomvonal mentése</button>
          <button type="button" className="secondary" onClick={resetMap}>Nyomvonal törlése</button>
        </div>
      </div>
      <p className="mower-safety-note"><AlertTriangle size={15} />Ez csak megjelenítés: nem indít mozgást és még nem ment felmérési térképet.</p>
    </section>
  );
}

export default function MowerControl({ setToast }) {
  const { data, loading, error, refresh } = usePolledContext("/api/context/mower", { intervalMs: 2000 });
  const [busy, setBusy] = useState("");
  const [bladeRpm, setBladeRpm] = useState("6000");
  const [heading, setHeading] = useState("0");
  const [firmwareFile, setFirmwareFile] = useState(null);
  const [firmwareBusy, setFirmwareBusy] = useState("");
  const [firmwareStatus, setFirmwareStatus] = useState(null);
  const [routeDetail, setRouteDetail] = useState(null);
  const [routeBusy, setRouteBusy] = useState("");
  const [manualState, setManualState] = useState("disconnected");
  const [manualMessage, setManualMessage] = useState("ESP WebSocket not connected");
  const [manualVector, setManualVector] = useState({ forward: 0, turn: 0 });
  const [lastCommandRequest, setLastCommandRequest] = useState(null);
  const manualSocketRef = useRef(null);
  const manualSeqRef = useRef(0);
  const manualStopSeqRef = useRef(0);
  const manualClientRef = useRef(manualClientId());
  const status = data?.status || {};
  const link = status.link || {};
  const imu = status.imu || {};
  const gnss = status.gnss || {};
  const robot = status.robot || {};
  const safety = status.safety || {};
  const fault = status.fault || {};
  const route = status.route || {};
  const headingState = status.heading || {};
  const motors = data?.motors || {};
  const integration = data?.integration || {};
  const controlsDisabled = integration.controls_enabled !== true;
  const gnssFixValid = data?.rtk_pose?.valid === true;

  const faultValue = value(robot, ["fault_mask"], value(fault, ["mask"], 0));
  const faultActive = Number(faultValue) !== 0 || String(value(robot, ["state"], "")).toUpperCase() === "FAULT";
  const faultText = faultDescription(faultValue, value(fault, ["name", "fault_name"], ""));
  const compass = Number(value(headingState, ["current_deg"], value(imu, ["compass_deg"], 0)));
  const compassStyle = useMemo(() => ({ transform: `rotate(${Number.isFinite(compass) ? compass : 0}deg)` }), [compass]);

  async function loadFirmwareStatus(silent = false) {
    try {
      const response = await fetch("/api/mower/firmware/status", { cache: "no-store" });
      const payload = await readJsonResponse(response);
      setFirmwareStatus(payload);
      if (!response.ok && !silent) setToast(payload.error || "STM updater unavailable");
    } catch (err) {
      setFirmwareStatus({ ok: false, error: err.message });
      if (!silent) setToast(err.message);
    }
  }

  useEffect(() => {
    loadFirmwareStatus(true);
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible" && !firmwareBusy) loadFirmwareStatus(true);
    }, 5000);
    return () => window.clearInterval(id);
  }, [firmwareBusy]);

  async function loadRoute(silent = false) {
    try {
      const response = await fetch("/api/mower/route", { cache: "no-store" });
      const payload = await readJsonResponse(response);
      if (!response.ok || payload.ok === false) throw new Error(payload.error || "RTK route unavailable");
      setRouteDetail(payload);
    } catch (err) {
      if (!silent) setToast(err.message);
    }
  }

  useEffect(() => {
    loadRoute(true);
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible" && !routeBusy) loadRoute(true);
    }, 2000);
    return () => window.clearInterval(id);
  }, [routeBusy]);

  async function command(name, commandValue, successText) {
    if (name !== "stop" && controlsDisabled) {
      setToast(`Vezérlés letiltva: mower contract ${integration.contract_reported || "hiányzik"}, elvárt ${integration.contract_expected || "2.1.0"}`);
      return;
    }
    setBusy(name);
    try {
      const result = await api("/api/mower/command", {
        method: "POST",
        body: JSON.stringify(commandValue === undefined ? { command: name } : { command: name, value: commandValue }),
      });
      setLastCommandRequest({ requestId: result.request_id, command: result.command, sentAt: Date.now() });
      setToast(`${successText || "Mower command sent"} · ACK pending`);
      window.setTimeout(() => refresh(true), 350);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  const commandAckMatches = Boolean(lastCommandRequest?.requestId && status.command?.request_id === lastCommandRequest.requestId);

  async function uploadFirmware() {
    if (!firmwareFile) {
      setToast("Choose an STM .bin file first");
      return;
    }
    if (!firmwareFile.name.toLowerCase().endsWith(".bin") || firmwareFile.size > 2 * 1024 * 1024) {
      setToast("Select a .bin file no larger than 2 MiB");
      return;
    }
    if (!window.confirm(`Stage ${firmwareFile.name} (${firmwareFile.size.toLocaleString()} bytes) on the STM32?`)) return;
    setFirmwareBusy("upload");
    setFirmwareStatus((current) => ({ ...current, active: true, message: "Uploading and verifying firmware…", bytes: 0, expected: firmwareFile.size }));
    try {
      const form = new FormData();
      form.append("firmware", firmwareFile, firmwareFile.name);
      const response = await fetch("/api/mower/firmware/upload", { method: "POST", body: form });
      const payload = await readJsonResponse(response);
      if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.message || "STM upload failed");
      setToast("STM firmware staged and CRC verified");
    } catch (err) {
      setToast(err.message);
    } finally {
      setFirmwareBusy("");
      loadFirmwareStatus(true);
    }
  }

  async function firmwareAction(action) {
    const prompt = action === "activate"
      ? "Activate the staged STM firmware? The mower will stop and the STM32 will reset."
      : "Reset the STM32 now? All motor commands will stop.";
    if (!window.confirm(prompt)) return;
    setFirmwareBusy(action);
    try {
      const response = await fetch(`/api/mower/firmware/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await readJsonResponse(response);
      if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.message || `STM ${action} failed`);
      setToast(payload.message || `STM ${action} accepted`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setFirmwareBusy("");
      window.setTimeout(() => loadFirmwareStatus(true), 1500);
    }
  }

  async function routeAction(action) {
    if (action === "play" && !window.confirm("Start RTK waypoint playback? The mower may begin moving immediately if it is armed.")) return;
    if (action === "clear" && !window.confirm("Delete every recorded RTK waypoint?")) return;
    setRouteBusy(action);
    try {
      const response = await fetch(`/api/mower/route/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await readJsonResponse(response);
      if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.message || `Route ${action} failed`);
      setToast(payload.message || `Route ${action} accepted`);
      await loadRoute(true);
    } catch (err) {
      setToast(err.message);
    } finally {
      setRouteBusy("");
    }
  }

  function saveRoute() {
    const points = (routeDetail?.points || []).filter((point) => Number.isFinite(Number(point.lat)) && Number.isFinite(Number(point.lon)));
    if (!points.length) {
      setToast("Nincs menthető waypoint");
      return;
    }
    const savedAt = new Date();
    const pointFeatures = points.map((point, index) => ({
      type: "Feature",
      properties: {
        order: index + 1,
        fix_name: point.fix_name ?? null,
        fix_quality: point.fix_quality ?? null,
        hdop: Number.isFinite(Number(point.hdop)) ? Number(point.hdop) : null,
      },
      geometry: { type: "Point", coordinates: [Number(point.lon), Number(point.lat)] },
    }));
    const geoJson = {
      type: "FeatureCollection",
      properties: { name: "HomeControl mower route", saved_at: savedAt.toISOString(), point_count: points.length },
      features: [
        ...(points.length > 1 ? [{
          type: "Feature",
          properties: { name: "Mower waypoint route", point_count: points.length },
          geometry: { type: "LineString", coordinates: points.map((point) => [Number(point.lon), Number(point.lat)]) },
        }] : []),
        ...pointFeatures,
      ],
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(geoJson, null, 2)], { type: "application/geo+json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `mower-route-${savedAt.toISOString().replace(/[:.]/g, "-")}.geojson`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setToast(`${points.length} waypoint elmentve`);
  }

  function manualSend(type, extra = {}) {
    const socket = manualSocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return null;
    manualSeqRef.current += 1;
    socket.send(JSON.stringify({ type, seq: manualSeqRef.current, ...extra }));
    return manualSeqRef.current;
  }

  function manualStop() {
    const stopSeq = manualState === "ready" ? manualSend("stop") : null;
    if (stopSeq !== null) {
      manualStopSeqRef.current = stopSeq;
      setManualState("ready");
      setManualMessage("Rover stopped · WebSocket ownership remains active");
    }
    setManualVector({ forward: 0, turn: 0 });
  }

  function disconnectManual() {
    const socket = manualSocketRef.current;
    if (manualState === "ready") manualSend("release");
    manualSocketRef.current = null;
    socket?.close(1000, "HC manual control disabled");
    setManualState("disconnected");
    setManualMessage("Manual control disabled");
  }

  function connectManual() {
    const url = data?.manual_control?.url;
    if (!url || controlsDisabled || manualState === "connecting" || manualState === "ready") return;
    const currentSocket = manualSocketRef.current;
    if (currentSocket?.readyState === WebSocket.OPEN) {
      setManualState("connecting");
      setManualMessage("Requesting manual control claim");
      currentSocket.send(JSON.stringify({ type: "claim", client: manualClientRef.current, protocol: "homecontrol.mower.manual.v1" }));
      return;
    }
    setManualState("connecting");
    setManualMessage(`Connecting to ${url}`);
    let socket;
    try {
      socket = new WebSocket(url, data?.manual_control?.protocol || "homecontrol.mower.manual.v1");
    } catch (err) {
      setManualState("error");
      setManualMessage(err.message);
      return;
    }
    manualSocketRef.current = socket;
    socket.onopen = () => {
      socket.send(JSON.stringify({ type: "claim", client: manualClientRef.current, protocol: "homecontrol.mower.manual.v1" }));
      setManualMessage("Connected; waiting for control claim");
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "claimed") {
          setManualState("ready");
          setManualMessage(`Control active · deadman ${message.deadman_ms || 700} ms`);
        } else if (message.type === "ack") {
          setManualVector({ forward: Number(message.forward || 0), turn: Number(message.turn || 0) });
          if (Number(message.seq) === manualStopSeqRef.current) {
            setManualState("ready");
            setManualMessage("Rover stop acknowledged · ownership remains active");
          }
        } else if (message.type === "error") {
          setManualState("error");
          setManualMessage(message.message || message.code || "ESP rejected manual control");
          setManualVector({ forward: 0, turn: 0 });
        } else if (message.type === "state") {
          setManualMessage(`${message.armed ? "ARMED" : "DISARMED"} · F ${message.forward || 0} · T ${message.turn || 0}`);
        }
      } catch {
        setManualMessage("Invalid WebSocket response from ESP");
      }
    };
    socket.onerror = () => {
      setManualState("error");
      setManualMessage("ESP WebSocket unavailable; firmware support is not installed yet");
    };
    socket.onclose = () => {
      if (manualSocketRef.current === socket) manualSocketRef.current = null;
      setManualVector({ forward: 0, turn: 0 });
      setManualState((current) => current === "error" ? current : "disconnected");
    };
  }

  function setManualDrive(forward, turn) {
    const rawForward = Number(forward);
    const rawTurn = Number(turn);
    if (!Number.isInteger(rawForward) || !Number.isInteger(rawTurn) || Math.abs(rawForward) > 6000 || Math.abs(rawTurn) > 6000) {
      manualStop();
      setManualMessage("Invalid manual value rejected; rover stopped");
      return;
    }
    const next = {
      forward: rawForward,
      turn: rawTurn,
    };
    setManualVector(next);
    if (manualState === "ready") manualSend("drive", next);
  }

  function stopRoverDrive() {
    setManualDrive(0, 0);
    setManualMessage("Rover speed set to zero · WebSocket control remains active");
  }

  useEffect(() => {
    if (manualState !== "ready") return undefined;
    const heartbeat = window.setInterval(() => manualSend("heartbeat"), 250);
    const stopOnHide = () => { if (document.visibilityState !== "visible") manualStop(); };
    document.addEventListener("visibilitychange", stopOnHide);
    return () => {
      window.clearInterval(heartbeat);
      document.removeEventListener("visibilitychange", stopOnHide);
    };
  }, [manualState]);

  useEffect(() => () => {
    const socket = manualSocketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      manualSeqRef.current += 1;
      socket.send(JSON.stringify({ type: "stop", seq: manualSeqRef.current }));
      manualSeqRef.current += 1;
      socket.send(JSON.stringify({ type: "release", seq: manualSeqRef.current }));
      window.setTimeout(() => {
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CLOSING) {
          socket.close(1000, "HC page left");
        }
      }, 80);
    }
  }, []);

  return (
    <section className="page-stack mower-page">
      <div className="page-heading mower-heading">
        <div>
          <span className="eyebrow">STM32H743 · ESP32 remote</span>
          <h1>Robot mower</h1>
          <p>Live telemetry, safety state and low-rate MQTT controls.</p>
        </div>
        <div className="mower-heading-actions">
          <StatePill ok={integration.healthy} warn={data?.online}>{integration.healthy ? "Alrendszer rendben" : data?.online ? "Kapcsolat hiányos" : "Mower offline"}</StatePill>
          <IconButton icon={RefreshCw} disabled={loading} onClick={() => refresh()}>{loading ? "Loading" : "Refresh"}</IconButton>
          <a className="button-link secondary" href={data?.remote_url || "http://mower-remote.local/"} target="_blank" rel="noreferrer"><ExternalLink size={16} />Direct remote</a>
        </div>
      </div>

      {error && <div className="inline-alert error"><AlertTriangle size={17} />{error}</div>}
      {integration.contract_compatible === false && <div className="inline-alert error"><AlertTriangle size={17} />
        Inkompatibilis mower protokoll: {integration.contract_reported || "nincs verzió"}; elvárt {integration.contract_expected || "2.1.0"}. A globális STOP kivételével minden vezérlés le van tiltva.
      </div>}
      {data?.online && integration.healthy === false && <div className="inline-alert warning"><AlertTriangle size={17} />
        Mower integráció nem teljes:
        {integration.missing_topics?.length ? ` hiányzó topicok: ${integration.missing_topics.join(", ")}.` : ""}
        {integration.stale_topics?.length ? ` elavult topicok: ${integration.stale_topics.join(", ")}.` : ""}
        {integration.invalid_topics?.length ? ` hibás v2 payloadok: ${integration.invalid_topics.join(", ")}.` : ""}
        {!integration.stm_alive ? " STM kapcsolat nincs." : ""}
        {!integration.can_alive ? " CAN kapcsolat nincs." : ""}
      </div>}
      <div className="card-grid mower-overview">
        <Card title="Robot" value={value(robot, ["state", "mode"], data?.online ? "ONLINE" : "OFFLINE")} meta={faultActive ? `${faultText} · ${faultValue}` : `armed ${yesNo(value(robot, ["armed"], false))}`} icon={Power} tone={faultActive ? "warn" : ""} />
        <Card title="GNSS" value={value(gnss, ["fix_name"], "NO FIX")} meta={`${value(gnss, ["sats"], 0)} satellites · HDOP ${num(value(gnss, ["hdop"]), 2)}`} icon={MapPin} />
        <Card title="Heading" value={`${num(value(imu, ["compass_deg"]), 1)}°`} meta={`north ${value(imu, ["north_valid"], false) ? "set" : "not set"}`} icon={Compass} />
        <Card title="Route" value={route.playing ? "PLAYING" : "IDLE"} meta={`${value(route, ["index"], 0)} / ${value(route, ["count"], 0)} · ${num(value(route, ["distance_m"]), 1)} m`} icon={Navigation} />
        <Card title="Safety" value={faultActive ? "FAULT" : value(robot, ["state"], "READY")} meta={faultActive ? faultText : "Nincs aktív hiba"} icon={Shield} tone={faultActive ? "warn" : ""} />
        <Card title="Alrendszer" value={integration.healthy ? "HEALTHY" : link.stm_alive ? "DEGRADED" : "STM LOST"} meta={`Wi-Fi ${value(link, ["rssi"], "-")} dBm · CAN ${link.can_alive ? "OK" : "lost"}`} icon={Radio} tone={integration.healthy ? "" : "warn"} />
      </div>

      <div className="mower-main-grid">
        <article className="panel mower-control-panel">
          <div className="panel-head"><h2><Shield size={18} /> Safety & control</h2><span>MQTT commands</span></div>
          <div className="mower-emergency">
            <button type="button" className="mower-stop" disabled={Boolean(busy) || !integration.stop_enabled} onClick={() => command("stop", undefined, "Emergency stop sent")}><Square size={24} fill="currentColor" />STOP</button>
            <div><strong>Immediate motion stop</strong><span>Cancels heading control, blade and drive commands.</span></div>
          </div>
          <div className="mower-button-grid">
            <IconButton icon={Power} disabled={Boolean(busy) || controlsDisabled} onClick={() => command("arm")}>Arm</IconButton>
            <IconButton icon={Power} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("disarm")}>Disarm</IconButton>
            <IconButton icon={RotateCcw} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("clear_estop")}>Clear E-stop</IconButton>
            <IconButton icon={Shield} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("fault_clear")}>Clear fault</IconButton>
            <IconButton icon={RefreshCw} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("safety_reset")}>Safety reset</IconButton>
            <IconButton icon={Radio} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("telemetry")}>Fast telemetry</IconButton>
            <IconButton icon={ExternalLink} className={link.legacy_web_ui ? "" : "secondary"} disabled={Boolean(busy) || controlsDisabled} onClick={() => command("web_ui", !Boolean(link.legacy_web_ui), `ESP Web UI ${link.legacy_web_ui ? "disabled" : "enabled"}`)}>Web UI {link.legacy_web_ui ? "ON" : "OFF"}</IconButton>
          </div>
          <div className="mower-set-control">
            <label>Blade target <span>RPM</span><input type="number" min="0" max="25000" step="100" value={bladeRpm} onChange={(event) => setBladeRpm(event.target.value)} /></label>
            <IconButton icon={Gauge} disabled={Boolean(busy) || controlsDisabled} onClick={() => command("blade_rpm", Number(bladeRpm), "Blade target sent")}>Set blade</IconButton>
            <IconButton icon={Square} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("blade_stop")}>Blade stop</IconButton>
          </div>
          <p className="mower-safety-note"><AlertTriangle size={15} />Commands are never retained. Manual driving remains on the ESP direct remote.</p>
        </article>

        <article className="panel mower-compass-panel">
          <div className="panel-head"><h2><Compass size={18} /> IMU instruments</h2><span>{imu.alive ? "live" : value(headingState, ["mode", "state"], "IMU")}</span></div>
          <div className="mower-instruments">
            <div className="mower-instrument"><strong>Heading</strong><div className="mower-compass"><div className="mower-compass-ring"><span>N</span><i style={compassStyle} /><b>{num(compass, 1)}°</b></div></div></div>
            <div className="mower-instrument"><strong>Attitude</strong><ArtificialHorizon pitch={imu.pitch_deg} roll={imu.roll_deg} alive={imu.alive} /></div>
          </div>
          <div className="mower-set-control compact">
            <label>Target <span>degrees</span><input type="number" min="0" max="359" step="1" value={heading} onChange={(event) => setHeading(event.target.value)} /></label>
            <IconButton icon={Crosshair} disabled={Boolean(busy) || controlsDisabled} onClick={() => command("heading_target", Number(heading))}>Turn to</IconButton>
          </div>
          <div className="mower-button-grid three">
            <IconButton icon={Compass} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("north_set")}>Set North</IconButton>
            <IconButton icon={Crosshair} className={imu.auto_north_active ? "" : "secondary"} disabled={Boolean(busy) || controlsDisabled || !imu.alive} onClick={() => command("auto_north", imu.auto_north_active ? "stop" : "start", "Auto North command sent")}>{imu.auto_north_active ? "Stop Auto North" : "Auto North"}</IconButton>
            <IconButton icon={Navigation} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("heading_assist", true)}>Assist on</IconButton>
            <IconButton icon={Square} className="secondary" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("heading_cancel")}>Cancel</IconButton>
          </div>
          <div className="mower-data-list mower-auto-north-status">
            <DataRow label="Auto North" value={value(imu, ["auto_north_status", "auto_north"], imu.auto_north_active ? "ACTIVE" : "IDLE")} detail={imu.auto_north_active ? "sampling" : "inactive"} />
            <DataRow label="Samples" value={Number(value(imu, ["auto_north_samples"], 0)).toLocaleString()} />
          </div>
          <div className="mower-heading-presets">
            {[0, 90, 180, 270].map((degrees) => <button type="button" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("heading_target", degrees)} key={degrees}>{degrees === 0 ? "N" : degrees === 90 ? "E" : degrees === 180 ? "S" : "W"}<small>{degrees}°</small></button>)}
            <button type="button" disabled={Boolean(busy) || controlsDisabled} onClick={() => command("heading_relative", 180)}>Turn around<small>+180°</small></button>
          </div>
        </article>
      </div>

      <article className="panel mower-safety-panel">
        <div className="panel-head"><h2><Shield size={18} /> Safety & faults</h2><StatePill ok={!faultActive && !Boolean(robot.estop)} warn={faultActive || Boolean(robot.estop)}>{faultActive ? "FAULT" : robot.estop ? "E-STOP" : "CLEAR"}</StatePill></div>
        <div className="mower-safety-grid">
          {[
            ["Robot state", value(robot, ["state"], "-") , !["DISARMED", "ARMED", "RUNNING"].includes(String(robot.state || ""))],
            ["Hiba oka", faultActive ? `${faultText} (${faultValue})` : "Nincs aktív hiba", faultActive],
            ["E-stop", Boolean(robot.estop) ? "LATCHED" : "clear", Boolean(robot.estop)],
            ["Bumper", Boolean(safety.bumper) ? "ACTIVE" : "clear", Boolean(safety.bumper)],
            ["Lift", Boolean(safety.lift) ? "DETECTED" : "clear", Boolean(safety.lift)],
            ["Tilt input", Boolean(safety.tilt) ? "ACTIVE" : "clear", Boolean(safety.tilt)],
            ["IMU tilt", Boolean(safety.imu_tilt) ? "ACTIVE" : "clear", Boolean(safety.imu_tilt)],
            ["Perimeter wire", Boolean(safety.wire_lost) ? "LOST" : "OK", Boolean(safety.wire_lost)],
          ].map(([label, current, bad]) => <div className={bad ? "bad" : "good"} key={label}><span>{label}</span><strong>{current}</strong></div>)}
        </div>
      </article>

      <article className="panel mower-manual-panel">
        <div className="panel-head">
          <h2><Gauge size={18} /> Manual cruise control</h2>
          <StatePill ok={manualState === "ready"} warn={manualState === "connecting"}>{manualState}</StatePill>
        </div>
        <div className="mower-manual-layout">
          <div className={`mower-cruise ${manualState === "ready" ? "enabled" : "locked"}`}>
            <div className="mower-cruise-speed"><span>Target speed</span><strong>{manualVector.forward}</strong><small>RPM</small></div>
            <div className="mower-cruise-buttons">
              <button type="button" disabled={manualState !== "ready"} onClick={() => setManualDrive(manualVector.forward + 500, manualVector.turn)}>+500</button>
              <button type="button" disabled={manualState !== "ready"} onClick={() => setManualDrive(manualVector.forward - 500, manualVector.turn)}>−500</button>
              <button type="button" disabled={manualState !== "ready"} onClick={() => setManualDrive(-1000, manualVector.turn)}>Reverse</button>
              <button type="button" disabled={manualState !== "ready"} onClick={() => setManualDrive(manualVector.forward, 0)}>Straight</button>
              <button type="button" className="mower-cruise-stop" disabled={manualState !== "ready"} onClick={stopRoverDrive}><Square size={15} fill="currentColor" /> STOP</button>
            </div>
            <label>Drive RPM <b>{manualVector.forward}</b><input type="range" min="-6000" max="6000" step="100" disabled={manualState !== "ready"} value={manualVector.forward} onChange={(event) => setManualDrive(event.target.value, manualVector.turn)} /></label>
            <label>Steering correction <b>{manualVector.turn}</b><input
              type="range"
              min="-1500"
              max="1500"
              step="50"
              disabled={manualState !== "ready"}
              value={manualVector.turn}
              onChange={(event) => setManualDrive(manualVector.forward, event.target.value)}
              onPointerUp={() => setManualDrive(manualVector.forward, 0)}
              onPointerCancel={() => setManualDrive(manualVector.forward, 0)}
              onKeyUp={() => setManualDrive(manualVector.forward, 0)}
              onBlur={() => setManualDrive(manualVector.forward, 0)}
            /></label>
            {manualState !== "ready" && <div className="mower-cruise-lock"><Shield size={25} /><strong>Drive locked</strong><span>WebSocket claim required</span></div>}
          </div>
          <div className="mower-manual-side">
            <div className="mower-manual-values"><div><span>Forward</span><strong>{manualVector.forward} RPM</strong></div><div><span>Turn</span><strong>{manualVector.turn} RPM</strong></div></div>
            <p>{manualMessage}</p>
            <code>{data?.manual_control?.url || "Waiting for ESP address"}</code>
            <div className="mower-manual-actions">
              {manualState === "ready" ? <IconButton icon={Shield} className="secondary" onClick={disconnectManual}>Disconnect WebSocket</IconButton> : <IconButton icon={Radio} disabled={controlsDisabled || !data?.manual_control?.url || manualState === "connecting"} onClick={connectManual}>{manualState === "connecting" ? "Connecting…" : manualState === "connected" ? "Claim control" : "Connect WebSocket"}</IconButton>}
            </div>
            <small><AlertTriangle size={14} />Manual drive unlocks only after the ESP accepts the WebSocket control claim.</small>
          </div>
        </div>
      </article>

      <article className="panel mower-route-panel">
        <div className="panel-head">
          <h2><Navigation size={18} /> RTK térkép és waypoint útvonal</h2>
          <StatePill ok={routeDetail?.playing} warn={routeDetail?.transport !== "mqtt"}>{routeDetail?.playing ? `${routeDetail.phase || "drive"} · point ${Number(routeDetail.index || 0) + 1}` : `${routeDetail?.count || 0}${Number.isFinite(Number(routeDetail?.max)) ? `/${routeDetail.max}` : ""} points`} · {routeDetail?.transport === "mqtt" ? "MQTT" : "LEGACY HTTP"}</StatePill>
        </div>
        <div className="mower-route-readiness">
          <div className={gnssFixValid ? "ready" : "blocked"}><MapPin size={16} /><span>GNSS fix</span><strong>{value(gnss, ["fix_name"], "NO FIX")}</strong></div>
          <div className={Number(gnss.fix_quality) === 4 ? "ready" : "blocked"}><Crosshair size={16} /><span>RTK quality</span><strong>{Number(gnss.fix_quality) === 4 ? "FIX" : Number(gnss.fix_quality) === 5 ? "FLOAT" : "NOT FIXED"}</strong></div>
          <div className={imu.north_valid ? "ready" : "blocked"}><Compass size={16} /><span>North reference</span><strong>{imu.north_valid ? "SET" : "REQUIRED"}</strong></div>
          <div className={routeDetail?.stm_auto ? "ready" : "blocked"}><Cpu size={16} /><span>Route controller</span><strong>{routeDetail?.stm_auto ? "STM AUTO" : "ESP FALLBACK"}</strong></div>
        </div>
        <RtkLiveMap pose={data?.rtk_pose} />
        <div className="mower-route-toolbar">
          <IconButton icon={Plus} disabled={controlsDisabled || Boolean(routeBusy) || !gnssFixValid || (Number.isFinite(Number(routeDetail?.max)) && Number(routeDetail?.count || 0) >= Number(routeDetail.max))} onClick={() => routeAction("record")}>{routeBusy === "record" ? "Recording…" : "Record current point"}</IconButton>
          <IconButton icon={Play} disabled={controlsDisabled || Boolean(routeBusy) || !routeDetail?.count || !gnssFixValid || !imu.north_valid || routeDetail?.playing} onClick={() => routeAction("play")}>{routeBusy === "play" ? "Starting…" : "Play route"}</IconButton>
          <IconButton icon={Square} className="danger" disabled={controlsDisabled || Boolean(routeBusy) || !routeDetail?.playing} onClick={() => routeAction("stop")}>{routeBusy === "stop" ? "Stopping…" : "Route stop"}</IconButton>
          <IconButton icon={Radio} className="secondary" disabled={controlsDisabled || Boolean(routeBusy)} onClick={() => routeAction("auto_status")}>AUTO status</IconButton>
          <IconButton icon={Save} className="secondary" disabled={Boolean(routeBusy) || !routeDetail?.count} onClick={saveRoute}>Útvonal mentése</IconButton>
          <IconButton icon={Trash2} className="secondary" disabled={controlsDisabled || Boolean(routeBusy) || !routeDetail?.count || routeDetail?.playing} onClick={() => routeAction("clear")}>Clear points</IconButton>
        </div>
        {routeDetail?.playing && <div className="mower-route-live">
          <div><span>Target</span><strong>#{Number(routeDetail.index || 0) + 1}</strong></div>
          <div><span>Phase</span><strong>{routeDetail.mode || "-"}</strong></div>
          <div><span>Distance</span><strong>{num(routeDetail.distance_m, 2)} m</strong></div>
          <div><span>Bearing</span><strong>{num(routeDetail.bearing_deg, 1)}°</strong></div>
          <div><span>Held heading</span><strong>{num(routeDetail.drive_heading_deg, 1)}°</strong></div>
          <div><span>Heading error</span><strong>{num(routeDetail.error_deg, 1)}°</strong></div>
        </div>}
        <div className="mower-route-table-wrap">
          <table className="mower-route-table">
            <thead><tr><th>#</th><th>Latitude</th><th>Longitude</th><th>Fix</th><th>HDOP</th><th>Status</th></tr></thead>
            <tbody>
              {(routeDetail?.points || []).map((point, index) => <tr className={routeDetail.playing && Number(routeDetail.index) === index ? "active" : ""} key={`${point.lat}-${point.lon}-${index}`}><td>{index + 1}</td><td>{num(point.lat, 8)}</td><td>{num(point.lon, 8)}</td><td>{point.fix_name || point.fix_quality}</td><td>{num(point.hdop, 2)}</td><td>{routeDetail.playing && Number(routeDetail.index) === index ? "TARGET" : index < Number(routeDetail.index || 0) && routeDetail.playing ? "DONE" : "WAITING"}</td></tr>)}
              {!routeDetail?.points?.length && <tr><td colSpan="6" className="empty">No waypoints recorded. Move to a position with GNSS fix and record the first point.</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="mower-safety-note"><AlertTriangle size={15} />Playback requires a North reference and GNSS fix. Arm the mower separately only when the test area is clear.</p>
      </article>

      <article className="panel mower-firmware-panel">
        <div className="panel-head">
          <h2><Cpu size={18} /> STM32 firmware</h2>
          <StatePill ok={firmwareStatus?.ok && !firmwareStatus?.active} warn={firmwareStatus?.active}>
            {firmwareStatus?.active ? "updating" : firmwareStatus?.ok ? "staged" : firmwareStatus?.reachable ? "idle" : "unavailable"}
          </StatePill>
        </div>
        <div className="mower-firmware-versions">
          <div><span>Current ESP firmware</span><strong>{value(status.fw, ["esp"], "unknown")}</strong></div>
          <div><span>Current STM firmware</span><strong>{value(status.fw, ["stm"], "unknown")}</strong></div>
        </div>
        <div className="mower-firmware-layout">
          <div className="mower-firmware-copy">
            <strong>{firmwareStatus?.message || firmwareStatus?.error || "Waiting for ESP updater status"}</strong>
            <span>Upload stages the image in STM flash bank 2 and verifies size and CRC32. Activation is always a separate step.</span>
            <div className="mower-update-progress"><i style={{ width: `${firmwareStatus?.expected ? Math.min(100, (Number(firmwareStatus.bytes || 0) / Number(firmwareStatus.expected)) * 100) : 0}%` }} /></div>
            <small>{Number(firmwareStatus?.bytes || 0).toLocaleString()} / {Number(firmwareStatus?.expected || 0).toLocaleString()} bytes{firmwareStatus?.crc ? ` · CRC32 ${firmwareStatus.crc}` : ""}</small>
          </div>
          <div className="mower-firmware-actions">
            <label className="mower-file-picker">
              <span>STM binary</span>
              <input type="file" accept=".bin,application/octet-stream" disabled={Boolean(firmwareBusy)} onChange={(event) => setFirmwareFile(event.target.files?.[0] || null)} />
              <small>{firmwareFile ? `${firmwareFile.name} · ${firmwareFile.size.toLocaleString()} bytes` : "Maximum 2 MiB"}</small>
            </label>
            <IconButton icon={Upload} disabled={Boolean(firmwareBusy) || !firmwareFile} onClick={uploadFirmware}>{firmwareBusy === "upload" ? "Staging…" : "Upload & verify"}</IconButton>
            <IconButton icon={Power} className="danger" disabled={controlsDisabled || Boolean(firmwareBusy) || !firmwareStatus?.ok} onClick={() => firmwareAction("activate")}>{firmwareBusy === "activate" ? "Activating…" : "Activate staged"}</IconButton>
            <IconButton icon={RotateCcw} className="secondary" disabled={controlsDisabled || Boolean(firmwareBusy)} onClick={() => firmwareAction("reset")}>{firmwareBusy === "reset" ? "Resetting…" : "Reset STM"}</IconButton>
          </div>
        </div>
        <p className="mower-firmware-warning"><AlertTriangle size={16} />Do not power off the mower during staging or activation. Activation swaps the STM dual flash bank.</p>
      </article>

      <div className="mower-detail-grid">
        <article className="panel"><div className="panel-head"><h2><MapPin size={18} /> RTK GNSS</h2><StatePill ok={gnssFixValid} warn={gnss.alive}>{value(gnss, ["fix_name"], "NO DATA")}</StatePill></div><div className="mower-data-list">
          <DataRow label="Position" value={`${num(gnss.lat, 7)}, ${num(gnss.lon, 7)}`} />
          <DataRow label="Satellites" value={value(gnss, ["sats"], "-")} detail={`HDOP ${num(gnss.hdop, 2)}`} />
          <DataRow label="Movement" value={`${num(gnss.speed_kmh, 1)} km/h`} detail={`${num(gnss.course_deg, 1)}°`} />
          <DataRow label="NTRIP" value={value(gnss, ["ntrip_state"], "-")} detail={`RTCM ${value(gnss, ["rtcm_bytes"], 0)} B`} />
          <DataRow label="Correction" value={`${num(gnss.correction_age_s, 1)} s`} detail={`RTCM age ${num(Number(gnss.rtcm_age_ms) / 1000, 1)} s`} />
        </div></article>
        <article className="panel"><div className="panel-head"><h2><Gauge size={18} /> Motors</h2><span>VESC telemetry</span></div><div className="mower-motors">
          {[1, 2, 3].map((id) => { const motor = motors[String(id)] || {}; return <div className="mower-motor" key={id}><span>M{id}</span><strong>{id === 1 ? "Left drive" : id === 2 ? "Right drive" : "Blade"}</strong><b>{motor.seen ? `${num(motor.rpm, 0)} RPM` : "UNKNOWN"}</b><small>{motor.current_a != null ? `${num(motor.current_a, 1)} A` : "current unknown"}{motor.duty_ratio != null ? ` · duty ${num(Number(motor.duty_ratio) * 100, 1)}%` : ""}</small></div>; })}
        </div></article>
        <article className="panel"><div className="panel-head"><h2><Wifi size={18} /> Connectivity</h2><StatePill ok={data?.mqtt_connected}>broker</StatePill></div><div className="mower-data-list">
          <DataRow label="ESP" value={value(status.fw, ["esp"], "-")} />
          <DataRow label="STM" value={value(status.fw, ["stm"], "-")} />
          <DataRow label="ESP address" value={value(link, ["ip"], "-")} detail={`${value(link, ["rssi"], "-")} dBm`} />
          <DataRow label="CAN" value={link.can_alive ? "Online" : "Offline"} detail={`${value(link, ["can_age_ms"], "-")} ms`} />
          <DataRow label="Web UI" value={link.legacy_web_ui ? "ON" : "OFF"} detail={data?.mqtt_connected ? "MQTT online" : "MQTT offline"} />
          <DataRow label="Contract" value={integration.contract_reported || "HIÁNYZIK"} detail={integration.contract_compatible ? "compatible" : `expected ${integration.contract_expected || "2.1.0"}`} />
          <DataRow label="Command ACK" value={status.command?.accepted === true ? "ACCEPTED" : status.command?.accepted === false ? "REJECTED" : "-"} detail={value(status.command, ["message"], "")} />
          <DataRow label="ACK command" value={value(status.command, ["command"], "-")} detail={value(status.command, ["code"], "")} />
          <DataRow label="Request ID" value={value(status.command, ["request_id"], "-")} />
          <DataRow label="HC ACK pairing" value={!lastCommandRequest ? "NO REQUEST" : commandAckMatches ? "MATCHED" : "PENDING / UNKNOWN"} detail={lastCommandRequest?.requestId || ""} />
        </div></article>
        <article className="panel"><div className="panel-head"><h2><Cpu size={18} /> ESP diagnostics</h2><StatePill ok={link.diagnostics === true}>{link.diagnostics === true ? "enabled" : "disabled"}</StatePill></div><div className="mower-button-grid mower-diagnostics-toggle">
          <IconButton icon={Gauge} className={link.diagnostics === true ? "secondary" : ""} disabled={controlsDisabled || Boolean(busy) || !data?.mqtt_connected} onClick={() => command("diagnostics", link.diagnostics !== true, `ESP diagnostics ${link.diagnostics === true ? "disabled" : "enabled"}`)}>{link.diagnostics === true ? "Disable diagnostics" : "Enable diagnostics"}</IconButton>
        </div><div className="mower-data-list">
          {link.diagnostics === true ? <>
            <DataRow label="Free heap" value={`${Number(value(link, ["free_heap"], 0)).toLocaleString()} B`} detail={`minimum ${Number(value(link, ["min_free_heap"], 0)).toLocaleString()} B`} />
            <DataRow label="Max allocation" value={`${Number(value(link, ["max_alloc_heap"], 0)).toLocaleString()} B`} />
            <DataRow label="Loop samples" value={Number(value(link, ["loop_count"], 0)).toLocaleString()} detail={`${num(value(link, ["loop_last_us"]), 0)} µs last`} />
            <DataRow label="Loop time" value={`${num(value(link, ["loop_avg_us"]), 0)} µs avg`} detail={`${num(value(link, ["loop_max_us"]), 0)} µs max`} />
            <DataRow label="Route payload" value={`${Number(value(link, ["mqtt_route_payload_bytes"], 0)).toLocaleString()} B`} />
          </> : <p className="mower-diagnostics-off">Live heap and loop sampling are disabled on the ESP.</p>}
          <DataRow label="MQTT publish" value={Number(value(link, ["mqtt_published"], 0)).toLocaleString()} detail={`${Number(value(link, ["mqtt_failed"], 0)).toLocaleString()} failed`} />
          <DataRow label="MQTT commands" value={Number(value(link, ["mqtt_commands"], 0)).toLocaleString()} detail={`${Number(value(link, ["mqtt_command_failed"], 0)).toLocaleString()} failed`} />
        </div></article>
      </div>

      <Notes setToast={setToast} scope="mower" embedded />

      <button className="mower-mobile-stop" type="button" onClick={() => { manualStop(); command("stop", undefined, "Emergency stop sent"); }}>
        <Square size={18} fill="currentColor" /> EMERGENCY STOP
      </button>
    </section>
  );
}
