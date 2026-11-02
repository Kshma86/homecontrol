import React, { useEffect, useRef, useState } from "react";
import { Activity, BatteryCharging, CalendarDays, Clock, Database, Gauge, Home, Map as MapIcon, Play, RefreshCw, Save, Square } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { dateText, optionLabel, shortValue, textValue, unitValue } from "../../formatters";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { dndMatch, roomCleanPlan, shortPath, timeAfterMinutes, timeText, waitForX10CommandResult } from "./x10Runtime";
import { dayMaskFor, parseSegmentList, weeklyScheduleSignature, x10DayOptions, x10ModeOptions, x10SuctionOptions, x10WaterOptions, x10WeeklyDraftFromState } from "./x10Options";

export default function XiaomiX10({ setToast }) {
  const [busy, setBusy] = useState("");
  const [cleanMode, setCleanMode] = useState("");
  const [suction, setSuction] = useState("");
  const [waterLevel, setWaterLevel] = useState("");
  const [captureLabel, setCaptureLabel] = useState("");
  const [selectedMapId, setSelectedMapId] = useState("");
  const mapSelectRef = useRef(null);
  const lastRobotMapIdRef = useRef("");
  const [weeklySchedules, setWeeklySchedules] = useState(() => x10WeeklyDraftFromState(null));
  const [quickClean, setQuickClean] = useState({
    delay_min: 2,
    map_id: "",
    mode: "2",
    suction: "3",
    water_level: "2",
    segments: [],
    segment_text: "",
  });
  const [scheduleDirty, setScheduleDirty] = useState(false);
  const [scheduleSyncHoldUntil, setScheduleSyncHoldUntil] = useState(0);
  const [pendingScheduleSignature, setPendingScheduleSignature] = useState("");
  const [nowMs, setNowMs] = useState(Date.now());
  const [dndWindows, setDndWindows] = useState(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("x10-dnd-windows") || "[]");
      if (Array.isArray(saved) && saved.length) return saved;
    } catch (err) {
      // Ignore invalid local storage and fall back to one editable window.
    }
    return [{ enabled: false, start: "22:00", end: "07:00" }];
  });
  const { data: state, setData: setState, loading, error, refresh: loadX10 } = usePolledContext("/api/context/robot", { intervalMs: 3000 });

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let stopped = false;

    const connect = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/api/xiaomi-x10/live`);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.type !== "x10_live_map") return;
          setState((current) => current ? { ...current, ...payload } : current);
        } catch {
          // Ignore malformed frames; normal polling remains available.
        }
      };
      socket.onclose = () => {
        if (!stopped) reconnectTimer = window.setTimeout(connect, 2000);
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [setState]);

  useEffect(() => {
    if (!state) return;
    setCleanMode((current) => current || textValue(state.clean_mode));
    setSuction((current) => current || textValue(state.suction));
    setWaterLevel((current) => current || textValue(state.water_level));
    const currentRobotMapId = textValue(state?.map?.current_id);
    if (currentRobotMapId && currentRobotMapId !== lastRobotMapIdRef.current) {
      lastRobotMapIdRef.current = currentRobotMapId;
      setSelectedMapId(currentRobotMapId);
      setQuickClean((current) => ({ ...current, map_id: currentRobotMapId, segments: [], segment_text: "" }));
    }
    if (scheduleDirty) return;
    const serverDraft = x10WeeklyDraftFromState(state);
    const serverSignature = weeklyScheduleSignature(serverDraft);
    if (pendingScheduleSignature && serverSignature === pendingScheduleSignature) {
      setPendingScheduleSignature("");
      setScheduleSyncHoldUntil(0);
      setWeeklySchedules(serverDraft);
      return;
    }
    if (scheduleSyncHoldUntil && Date.now() < scheduleSyncHoldUntil) return;
    setPendingScheduleSignature("");
    setScheduleSyncHoldUntil(0);
    setWeeklySchedules(serverDraft);
  }, [state, scheduleDirty, scheduleSyncHoldUntil, pendingScheduleSignature]);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("x10-dnd-windows", JSON.stringify(dndWindows));
  }, [dndWindows]);

  async function publishX10(command, payload = "1") {
    return api("/api/xiaomi-x10/command", {
      method: "POST",
      body: JSON.stringify({ command, payload }),
    });
  }

  async function sendX10(command, payload = "1", message = "Command sent") {
    setBusy(command);
    try {
      await publishX10(command, payload);
      setToast(message);
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function applyCleaningSettings() {
    setBusy("settings");
    try {
      await publishX10("set_clean_mode", { value: Number(cleanMode || state?.clean_mode || 0) });
      await publishX10("set_suction", { value: Number(suction || state?.suction || 3) });
      await publishX10("set_water_level", { value: Number(waterLevel || state?.water_level || 1) });
      setToast("Cleaning settings sent");
      window.setTimeout(() => loadX10(true), 1200);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function startCapture() {
    setBusy("capture_start");
    try {
      await publishX10("capture_start", {
        label: captureLabel || state?.map?.current_name || "x10_capture",
        map_id: state?.map?.current_id || null,
      });
      setToast("X10 data capture started");
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function stopCapture() {
    setBusy("capture_stop");
    try {
      await publishX10("capture_stop", {});
      setToast("X10 data capture stopped");
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function activateSelectedMap() {
    const mapId = Number(mapSelectRef.current?.value || selectedMapId || state?.map?.current_id);
    if (!mapId) {
      setToast("Select map first");
      return;
    }
    setBusy("select_map");
    try {
      await publishX10("select_map", { map_id: mapId });
      setToast("Map activation sent");
      window.setTimeout(() => loadX10(true), 1500);
      window.setTimeout(() => loadX10(true), 5000);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function selectX10Map(mapId) {
    const nextMapId = textValue(mapId);
    setSelectedMapId(nextMapId);
    setQuickClean((current) => {
      if (textValue(current.map_id) === nextMapId) return current;
      return { ...current, map_id: nextMapId, segments: [], segment_text: "" };
    });
  }

  async function roomClean(room) {
    const activeDnd = dndMatch(dndWindows, new Date(nowMs));
    if (activeDnd) {
      setToast(`DND active: ${activeDnd.start}-${activeDnd.end}`);
      return;
    }
    const mapId = state?.map?.current_id;
    const segmentId = room.segment_id;
    if (!mapId || !segmentId) return;
    setBusy("room_clean");
    try {
      if (cleanMode !== "") {
        await publishX10("set_clean_mode", { value: Number(cleanMode) });
      }
      if (waterLevel !== "") {
        await publishX10("set_water_level", { value: Number(waterLevel) });
      }
      await publishX10("room_clean", {
        map_id: mapId,
        segments: [segmentId],
        delay_min: 2,
        suction: Number(suction || state?.suction || 3),
        clean_param: Number(waterLevel || state?.water_level || 3),
      });
      setToast(`${room.name || segmentId} scheduled`);
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateWeeklySchedule(dayIndex, key, value) {
    setScheduleDirty(true);
    setWeeklySchedules((current) => current.map((item) => (
      item.day_index === dayIndex ? { ...item, [key]: value, ...(key === "map_id" ? { segments: [] } : {}) } : item
    )));
  }

  function toggleWeeklyRoom(dayIndex, segmentId, checked) {
    setScheduleDirty(true);
    setWeeklySchedules((current) => current.map((item) => {
      if (item.day_index !== dayIndex) return item;
      const value = Number(segmentId);
      const next = checked
        ? [...new Set([...item.segments, value])]
        : item.segments.filter((roomId) => Number(roomId) !== value);
      return { ...item, segments: next };
    }));
  }

  function updateQuickClean(key, value) {
    setQuickClean((current) => ({ ...current, [key]: value }));
  }

  function toggleQuickRoom(segmentId, checked) {
    const value = Number(segmentId);
    setQuickClean((current) => {
      const next = checked
        ? [...new Set([...current.segments, value])]
        : current.segments.filter((roomId) => Number(roomId) !== value);
      return { ...current, segments: next };
    });
  }

  async function scheduleQuickCleaning() {
    const activeDnd = dndMatch(dndWindows, new Date(nowMs));
    if (activeDnd) {
      setToast(`DND active: ${activeDnd.start}-${activeDnd.end}`);
      return;
    }
    const mapId = Number(quickClean.map_id || state?.map?.current_id || 3);
    const segments = [...new Set([
      ...parseSegmentList(quickClean.segments),
      ...parseSegmentList(quickClean.segment_text),
    ])];
    if (!segments.length) {
      setToast("Select room or enter segment for quick clean");
      return;
    }
    const delayMin = Math.max(1, Number(quickClean.delay_min) || 2);
    setBusy("quick_clean");
    try {
      const previousResultTs = Number(state?.command_result?.ts || 0);
      await publishX10("schedule_clean", {
        map_id: mapId,
        segments,
        start_time: timeAfterMinutes(delayMin),
        days: "0000000",
        enabled: 1,
        mode: Number(quickClean.mode || state?.clean_mode || 2),
        suction: Number(quickClean.suction || state?.suction || 3),
        clean_param: Number(quickClean.water_level || state?.water_level || 2),
      });
      await waitForX10CommandResult(api, "schedule_clean", previousResultTs);
      setToast(`Quick clean scheduled in ${delayMin} min`);
      window.setTimeout(() => loadX10(true), 900);
      window.setTimeout(() => loadX10(true), 2500);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function saveWeeklyCleaningSchedule() {
    const mapId = state?.map?.current_id;
    const enabledWithoutRooms = weeklySchedules.find((item) => item.enabled && !item.segments.length);
    if (!mapId) return;
    if (enabledWithoutRooms) {
      setToast(`Select room for ${x10DayOptions[enabledWithoutRooms.day_index]?.label || "day"}`);
      return;
    }
    setBusy("schedule_clean");
    const schedulePayload = weeklySchedules
      .map((item) => ({
        day_index: item.day_index,
        task_id: item.task_id,
            enabled: item.enabled && item.segments.length ? 1 : 0,
            start_time: item.start_time || "06:00",
            days: dayMaskFor(item.day_index),
            map_id: Number(item.map_id || mapId),
            mode: Number(item.mode || state?.clean_mode || 0),
        suction: Number(item.suction || state?.suction || 3),
        clean_param: Number(item.water_level || state?.water_level || 3),
        segments: item.segments.map((roomId) => Number(roomId)).filter(Boolean),
      }));
    try {
      await publishX10("schedule_clean_week", {
        map_id: mapId,
        schedules: schedulePayload,
      });
      setPendingScheduleSignature(weeklyScheduleSignature(weeklySchedules));
      setScheduleSyncHoldUntil(Date.now() + 10000);
      setScheduleDirty(false);
      setToast("Weekly cleaning schedule saved");
      window.setTimeout(() => loadX10(true), 2500);
      window.setTimeout(() => loadX10(true), 6500);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function disableWeeklyCleaningSchedule() {
    const mapId = state?.map?.current_id;
    if (!mapId) return;
    const disabledSchedules = weeklySchedules.map((item) => ({ ...item, enabled: false }));
    setWeeklySchedules(disabledSchedules);
    setScheduleDirty(true);
    setBusy("schedule_clean");
    try {
      await publishX10("schedule_clean_week", {
        map_id: mapId,
        schedules: disabledSchedules
          .map((item) => ({
            day_index: item.day_index,
            task_id: item.task_id,
            enabled: 0,
            start_time: item.start_time || "06:00",
            days: dayMaskFor(item.day_index),
            map_id: Number(item.map_id || mapId),
            mode: Number(item.mode || state?.clean_mode || 0),
            suction: Number(item.suction || state?.suction || 3),
            clean_param: Number(item.water_level || state?.water_level || 3),
            segments: item.segments.map((roomId) => Number(roomId)).filter(Boolean),
          })),
      });
      setPendingScheduleSignature(weeklyScheduleSignature(disabledSchedules));
      setScheduleSyncHoldUntil(Date.now() + 10000);
      setScheduleDirty(false);
      setToast("Weekly cleaning schedule disabled");
      window.setTimeout(() => loadX10(true), 2500);
      window.setTimeout(() => loadX10(true), 6500);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateDnd(index, key, value) {
    setDndWindows((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [key]: value } : item
    )));
  }

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading Xiaomi X10...</span>
      </section>
    );
  }

  const rooms = (state?.map?.rooms || []).filter((room) => room.segment_id && room.name && !String(room.name).startsWith("room_"));
  const x10Maps = state?.catalog?.maps?.length ? state.catalog.maps : [{ map_id: state?.map?.current_id || 3, name: state?.map?.current_name || "Current map", has_room_data: true }];
  const roomsByMap = state?.catalog?.rooms_by_map || {};
  const liveMap = state?.robot_live_map;
  const robotStateCode = Number(state?.robot_state ?? state?.state?.state);
  const robotActivelyMapping = [1, 5, 12].includes(robotStateCode);
  // The bridge keeps the last complete live PNG on persistent storage. Keep
  // showing that route after the run ends only while it belongs to the map the
  // robot currently reports. Otherwise a completed run on another floor can
  // outlive a later map switch and must not override the active map.
  const liveMapHasImage = Boolean(state?.robot_live_png_url && liveMap?.header);
  const roomsForMap = (mapId) => (roomsByMap[String(mapId)] || (Number(mapId) === Number(state?.map?.current_id) ? rooms : []))
    .filter((room) => room.segment_id && room.name && !String(room.name).startsWith("room_"));
  const catalogCurrentMap = x10Maps.find((mapItem) => mapItem.is_current);
  const robotMapId = state?.map?.current_id || catalogCurrentMap?.map_id;
  const liveMapMatchesRobotMap = Boolean(
    robotMapId
    && liveMap?.map_id
    && Number(liveMap.map_id) === Number(robotMapId)
  );
  const liveMapFresh = liveMapHasImage && liveMap?.available === true && liveMapMatchesRobotMap;
  const selectedMap = x10Maps.find((mapItem) => Number(mapItem.map_id) === Number(selectedMapId || robotMapId)) || x10Maps[0] || {};
  const selectedMapRooms = roomsForMap(selectedMap.map_id || robotMapId);
  const robotMap = x10Maps.find((mapItem) => Number(mapItem.map_id) === Number(robotMapId)) || catalogCurrentMap || {};
  const robotMapName = robotMap.name || state?.map?.current_name || "unknown";
  const selectedMapName = selectedMap.name || robotMapName;
  const mapSyncPending = Boolean(selectedMap.map_id && robotMapId && Number(selectedMap.map_id) !== Number(robotMapId));
  const mapCardMeta = mapSyncPending
    ? `waiting for robot ${robotMapName}`
    : `${selectedMapRooms.length} room | robot synced`;
  const bridgeOnline = String(state?.bridge_online) === "1" || state?.bridge_online === 1;
  const topics = Object.values(state?.topics || {}).sort((a, b) => String(a.rel_topic).localeCompare(String(b.rel_topic)));
  const cleanPlan = roomCleanPlan(state?.room_clean_status, nowMs);
  const activeDnd = dndMatch(dndWindows, new Date(nowMs));
  const cleanModeLabel = optionLabel(x10ModeOptions, state?.clean_mode);
  const suctionLabel = optionLabel(x10SuctionOptions, state?.suction);
  const waterLabel = optionLabel(x10WaterOptions, state?.water_level);
  const captureStatus = state?.capture_status || {};
  const captureActive = Boolean(captureStatus?.active);
  const robotStateText = textValue(state?.robot_state_text || state?.state?.state_text);
  const telemetryMissing = state?.telemetry_available === false;
  const telemetrySource = textValue(state?.telemetry_source);
  const quickMapId = Number(quickClean.map_id || selectedMapId || state?.map?.current_id || 3);
  const quickRooms = roomsForMap(quickMapId);
  const quickSelectedSegments = [...new Set([
    ...parseSegmentList(quickClean.segments),
    ...parseSegmentList(quickClean.segment_text),
  ])];
  const robotPosition = state?.robot_position;
  const robotPositionPx = Number(state?.robot_position_px?.map_id) === Number(robotMapId)
    ? state.robot_position_px
    : null;
  const dockPositionPx = state?.dock_position_px;
  const mapScale = 4;
  const mapHeader = (liveMapFresh && liveMap?.header) || state?.map?.current?.header || {};
  const mapWidth = Number(mapHeader?.width);
  const mapHeight = Number(mapHeader?.height);
  const mapPositionStyle = (position) => {
    if (!position) return {};
    if (Number.isFinite(mapWidth) && mapWidth > 0 && Number.isFinite(mapHeight) && mapHeight > 0) {
      return { left: `${(Number(position.x) / mapWidth) * 100}%`, top: `${(Number(position.y) / mapHeight) * 100}%` };
    }
    return { left: Number(position.x) * mapScale, top: Number(position.y) * mapScale };
  };
  const useLiveMap = liveMapFresh;
  const displayedRooms = useLiveMap && Array.isArray(liveMap?.rooms) ? liveMap.rooms : rooms;
  const displayedMapUrl = useLiveMap ? state.robot_live_png_url : state?.map?.current_png_url;
  const displayedMapVersion = useLiveMap
    ? (liveMap?.robot_time || liveMap?.ts || 0)
    : (state?.map?.md5 || state?.map?.current?.md5 || 0);

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Xiaomi X10</h2>
          <span>{error || `${state?.base_topic || "homecontrol/xiaomi_x10"} | ${bridgeOnline ? "bridge online" : "bridge offline"} | ${selectedMapName || "map unknown"}`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={() => loadX10()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles x10-tiles">
        <Card title="Robot State" value={robotStateText} meta={telemetryMissing ? "telemetry missing | map data available" : `source=${telemetrySource} | raw=${textValue(state?.robot_state)} | task=${textValue(state?.task_state)}`} icon={Activity} tone={bridgeOnline && !telemetryMissing ? "" : "warn"} />
        <Card title="Battery" value={unitValue(state?.battery, "%", 0)} meta={`source=${telemetrySource} | bridge ${textValue(state?.bridge_status)} | seen ${textValue(state?.bridge_last_seen)}`} icon={BatteryCharging} tone={telemetryMissing ? "warn" : ""} />
        <Card title="Cleaning" value={cleanModeLabel} meta={`vacuum=${suctionLabel} | water=${waterLabel} | mop=${textValue(state?.mop_attached)}`} icon={Gauge} />
        <Card title="Map" value={robotMapName || "-"} meta={mapCardMeta} icon={MapIcon} tone={mapSyncPending ? "warn" : ""} className={`x10-map-card ${mapSyncPending ? "map-sync-pending" : ""}`} />
        <Card title="Room Clean" value={cleanPlan?.label || "-"} meta={cleanPlan?.meta || (activeDnd ? `DND ${activeDnd.start}-${activeDnd.end}` : "no pending schedule")} icon={Clock} tone={activeDnd ? "warn" : ""} />
      </section>

      <section className="x10-map-quick-layout">
        <article className="panel x10-map-panel">
          <div className="panel-head">
            <h2>Robot helyzete</h2>
            <span>{robotPosition ? `x=${robotPosition.x}, y=${robotPosition.y} | ${dateText(robotPosition.ts * 1000)}` : "Nincs élő pozíció"}</span>
          </div>
          {displayedMapUrl ? (
            <div className="x10-map-frame">
              <div className="x10-map-canvas mirrored">
                <img src={`${displayedMapUrl}?v=${displayedMapVersion}`} alt={`${robotMapName} térkép`} />
                {dockPositionPx && Number(dockPositionPx.map_id) === Number(robotMapId) && (
                  <span className="x10-map-marker dock" title="Dokkoló" style={mapPositionStyle(dockPositionPx)}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2 5 14h6l-1 8 9-13h-6V2Z" /></svg>
                  </span>
                )}
                {robotPositionPx && (
                  <span
                    className="x10-map-marker robot"
                    title={`Robot | ${robotPositionPx.angle ?? 0}°`}
                    style={{
                      ...mapPositionStyle(robotPositionPx),
                      "--robot-angle": `${robotPositionPx.angle ?? 0}deg`,
                    }}
                  >
                    <span className="x10-vacuum-glyph">
                      <svg viewBox="0 0 32 32" aria-hidden="true">
                        <circle className="x10-vacuum-shell" cx="16" cy="16" r="14" />
                        <path className="x10-vacuum-bumper" d="M7.5 9.5a11 11 0 0 1 17 0" />
                        <circle className="x10-vacuum-lidar-ring" cx="16" cy="9" r="4" />
                        <circle className="x10-vacuum-lidar-cap" cx="16" cy="9" r="1.7" />
                        <path className="x10-vacuum-panel" d="M9 21.5c4.5 2 9.5 2 14 0" />
                        <path className="x10-vacuum-heading" d="M16 1.5 12.8 6h6.4Z" />
                      </svg>
                    </span>
                  </span>
                )}
                {displayedRooms.filter((room) => room.center_px).map((room) => (
                  <span
                    className="x10-map-room-label"
                    key={`map-label-${room.segment_id}`}
                    style={mapPositionStyle(room.center_px)}
                  >
                    {room.name}
                  </span>
                ))}
              </div>
            </div>
          ) : <span className="muted-text">A térképkép nem érhető el.</span>}
          <div className="x10-map-live-status">
            {liveMapFresh
              ? `${robotActivelyMapping ? "Élő követés aktív" : "Utolsó munka útvonala"} | frame ${liveMap.frame_id} | piros: tiltott, lila: felmosástól tiltott`
              : `Élő követés: ${liveMap?.error || "takarítás közben indul"}`}
          </div>
        </article>

        <article className="panel x10-quick-panel">
          <div className="panel-head">
            <h2>Quick Scheduled Clean</h2>
            <span>{activeDnd ? `DND ${activeDnd.start}-${activeDnd.end}` : `starts ${timeAfterMinutes(quickClean.delay_min)}`}</span>
          </div>
          <div className="x10-quick-grid">
            <label>
              Delay
              <input type="number" min="1" max="15" step="1" value={quickClean.delay_min} onChange={(event) => updateQuickClean("delay_min", event.target.value)} />
            </label>
            <label>
              Map
              <select value={quickMapId} onChange={(event) => setQuickClean((current) => ({ ...current, map_id: Number(event.target.value), segments: [], segment_text: "" }))}>
                {x10Maps.map((mapItem) => <option key={mapItem.map_id} value={mapItem.map_id}>{mapItem.name}</option>)}
              </select>
            </label>
            <label>
              Mode
              <select value={quickClean.mode} onChange={(event) => updateQuickClean("mode", event.target.value)}>
                {x10ModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Vacuum
              <select value={quickClean.suction} onChange={(event) => updateQuickClean("suction", event.target.value)}>
                {x10SuctionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Water
              <select value={quickClean.water_level} onChange={(event) => updateQuickClean("water_level", event.target.value)}>
                {x10WaterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Segments
              <input type="text" value={quickClean.segment_text} placeholder="4,7" onChange={(event) => updateQuickClean("segment_text", event.target.value)} />
            </label>
          </div>
          <div className="x10-weekly-rooms x10-quick-rooms">
            {quickRooms.length ? quickRooms.map((room) => (
              <label className="check" key={`quick-${quickMapId}-${room.segment_id}`}>
                <input type="checkbox" checked={quickClean.segments.map(Number).includes(Number(room.segment_id))} onChange={(event) => toggleQuickRoom(room.segment_id, event.target.checked)} />
                {room.name}
              </label>
            )) : <span className="muted-text">No room data</span>}
          </div>
          <IconButton icon={Clock} disabled={Boolean(busy) || Boolean(activeDnd) || !quickSelectedSegments.length} onClick={scheduleQuickCleaning}>{busy === "quick_clean" ? "Scheduling" : "Schedule"}</IconButton>
        </article>

        <article className="panel x10-active-map-panel">
          <div className="panel-head">
            <h2>Active Map</h2>
            <span>{selectedMapName || "unknown"} | selected ID {selectedMap.map_id || "-"}</span>
          </div>
          <div className="inline-form x10-map-select">
            <label>
              Map
              <select ref={mapSelectRef} value={selectedMapId || robotMapId || ""} onChange={(event) => selectX10Map(event.target.value)}>
                {x10Maps.map((mapItem) => (
                  <option key={mapItem.map_id} value={mapItem.map_id}>
                    {mapItem.name || `Map ${mapItem.map_id}`} #{mapItem.map_id}{mapItem.is_current ? " current" : ""}
                  </option>
                ))}
              </select>
            </label>
            <IconButton icon={MapIcon} disabled={Boolean(busy) || !selectedMapId} onClick={activateSelectedMap}>
              {busy === "select_map" ? "Activating" : "Activate Map"}
            </IconButton>
            <IconButton icon={RefreshCw} className="secondary" disabled={Boolean(busy)} onClick={() => sendX10("refresh_map", "1", "Map list refreshed")}>
              Refresh Map List
            </IconButton>
          </div>
        </article>

        <article className="panel x10-control-panel">
          <div className="panel-head">
            <h2>Control</h2>
            <span>{busy ? `sending ${busy}` : "MQTT command proxy"}</span>
          </div>
          <div className="button-grid">
            <IconButton icon={Play} disabled={Boolean(busy)} onClick={() => sendX10("start")}>Start</IconButton>
            <IconButton icon={Square} disabled={Boolean(busy)} className="secondary" onClick={() => sendX10("stop")}>Stop</IconButton>
            <IconButton icon={Home} disabled={Boolean(busy)} onClick={() => sendX10("home")}>Dock</IconButton>
            <IconButton icon={RefreshCw} disabled={Boolean(busy)} onClick={() => sendX10("status")}>Status</IconButton>
            <IconButton icon={CalendarDays} disabled={Boolean(busy)} onClick={() => sendX10("read_scheduler")}>Scheduler</IconButton>
          </div>
          <div className="x10-capture-box">
            <label>
              Capture Label
              <input
                type="text"
                value={captureLabel}
                placeholder={state?.map?.current_name || "x10_capture"}
                onChange={(event) => setCaptureLabel(event.target.value)}
              />
            </label>
            <div className="x10-capture-status">
              <strong>{captureActive ? "Capture active" : "Capture idle"}</strong>
              <span>{captureActive ? `${captureStatus.sample_count || 0} samples | ${shortPath(captureStatus.file)}` : "saves map/status samples to x10_maps/captures"}</span>
            </div>
            {captureActive ? (
              <IconButton icon={Square} className="secondary" disabled={Boolean(busy)} onClick={stopCapture}>{busy === "capture_stop" ? "Stopping" : "Stop Capture"}</IconButton>
            ) : (
              <IconButton icon={Database} disabled={Boolean(busy)} onClick={startCapture}>{busy === "capture_start" ? "Starting" : "Start Capture"}</IconButton>
            )}
          </div>
        </article>

      </section>

      <section className="grid">

        <article className="panel x10-scheduler-panel">
          <div className="panel-subhead">
            <h3>Weekly Cleaning Schedule</h3>
            <span>{scheduleDirty ? "unsaved changes" : "one task per day"}</span>
          </div>
          <div className="x10-weekly-list">
            {weeklySchedules.map((row) => {
              const day = x10DayOptions[row.day_index];
              return (
                <div className={`x10-weekly-row ${row.enabled ? "active" : ""}`} key={row.task_id}>
                  <label className="check x10-weekly-day">
                    <input
                      type="checkbox"
                      checked={Boolean(row.enabled)}
                      onChange={(event) => updateWeeklySchedule(row.day_index, "enabled", event.target.checked)}
                    />
                    {day?.label || row.day_index}
                  </label>
                  <label>
                    Start
                    <input type="time" value={row.start_time || "06:00"} onChange={(event) => updateWeeklySchedule(row.day_index, "start_time", event.target.value)} />
                  </label>
                  <label>
                    Map
                    <select value={row.map_id || state?.map?.current_id || 3} onChange={(event) => updateWeeklySchedule(row.day_index, "map_id", Number(event.target.value))}>
                      {x10Maps.map((mapItem) => <option key={mapItem.map_id} value={mapItem.map_id}>{mapItem.name}</option>)}
                    </select>
                  </label>
                  <label>
                    Mode
                    <select value={row.mode} onChange={(event) => updateWeeklySchedule(row.day_index, "mode", event.target.value)}>
                      {x10ModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    Vacuum
                    <select value={row.suction} onChange={(event) => updateWeeklySchedule(row.day_index, "suction", event.target.value)}>
                      {x10SuctionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    Water
                    <select value={row.water_level} onChange={(event) => updateWeeklySchedule(row.day_index, "water_level", event.target.value)}>
                      {x10WaterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <div className="x10-weekly-rooms">
                    {roomsForMap(row.map_id || state?.map?.current_id || 3).length ? roomsForMap(row.map_id || state?.map?.current_id || 3).map((room) => (
                      <label className="check" key={`${row.task_id}-${room.segment_id}`}>
                        <input
                          type="checkbox"
                          checked={row.segments.map(Number).includes(Number(room.segment_id))}
                          onChange={(event) => toggleWeeklyRoom(row.day_index, room.segment_id, event.target.checked)}
                        />
                        {room.name}
                      </label>
                    )) : <span className="muted-text">No room data</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="x10-schedule-box">
            <strong>{cleanPlan?.targetMs ? `Scheduled start: ${timeText(cleanPlan.targetMs)}` : "No pending scheduled room clean"}</strong>
            <span>{cleanPlan?.targetMs ? `Countdown ${cleanPlan.label} | ${cleanPlan.status}` : "Room cleaning is started through the vacuum scheduler"}</span>
          </div>
          <div className="button-row compact">
            <IconButton icon={Save} disabled={Boolean(busy)} onClick={saveWeeklyCleaningSchedule}>{busy === "schedule_clean" ? "Saving" : "Save Schedule"}</IconButton>
            <button type="button" className="secondary" disabled={Boolean(busy)} onClick={disableWeeklyCleaningSchedule}>Disable & Save</button>
          </div>

          <div className="panel-subhead">
            <h3>Cleaning Settings</h3>
            <span>{cleanModeLabel} | vacuum={suctionLabel} | water={waterLabel}</span>
          </div>
          <div className="x10-settings-grid">
            <label>
              Mode
              <select value={cleanMode} onChange={(event) => setCleanMode(event.target.value)}>
                <option value="">Current</option>
                {x10ModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Vacuum
              <select value={suction} onChange={(event) => setSuction(event.target.value)}>
                <option value="">Current</option>
                {x10SuctionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Water
              <select value={waterLevel} onChange={(event) => setWaterLevel(event.target.value)}>
                <option value="">Current</option>
                {x10WaterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <IconButton icon={Save} disabled={Boolean(busy)} onClick={applyCleaningSettings}>{busy === "settings" ? "Sending" : "Apply Now"}</IconButton>
          </div>

          <div className="panel-subhead">
            <h3>DND</h3>
            <span>{activeDnd ? `active ${activeDnd.start}-${activeDnd.end}` : "dashboard guard"}</span>
          </div>
          <div className="x10-dnd-list">
            {dndWindows.map((item, index) => (
              <div className="x10-dnd-row" key={index}>
                <label className="check">
                  <input type="checkbox" checked={Boolean(item.enabled)} onChange={(event) => updateDnd(index, "enabled", event.target.checked)} />
                  Enabled
                </label>
                <label>
                  From
                  <input type="time" value={item.start || "22:00"} onChange={(event) => updateDnd(index, "start", event.target.value)} />
                </label>
                <label>
                  To
                  <input type="time" value={item.end || "07:00"} onChange={(event) => updateDnd(index, "end", event.target.value)} />
                </label>
              </div>
            ))}
          </div>
          <div className="button-row compact">
            <button type="button" className="secondary" onClick={() => setDndWindows([...dndWindows, { enabled: true, start: "22:00", end: "07:00" }])}>Add DND</button>
            <button type="button" className="secondary" onClick={() => setDndWindows(dndWindows.length > 1 ? dndWindows.slice(0, -1) : dndWindows)}>Remove Last</button>
          </div>

          <div className="panel-subhead">
            <h3>Last Result</h3>
            <span>{dateText(state?.topics?.command_result?.timestamp ? new Date(state.topics.command_result.timestamp * 1000).toISOString() : null)}</span>
          </div>
          <pre className="json-box">{shortValue(state?.command_result || state?.error || {}, 900)}</pre>
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Live X10 MQTT</h2>
          <span>{topics.length} retained/current topics</span>
        </div>
        <Table
          rows={topics}
          columns={[
            { key: "rel_topic", label: "Topic" },
            { key: "json", label: "Value", render: (row) => shortValue(row.json, 150) },
            { key: "age_sec", label: "Age", render: (row) => `${row.age_sec}s` },
          ]}
        />
      </section>
    </>
  );
}
