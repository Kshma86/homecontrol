import React, { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Ban, Eye, FileJson, FolderOpen, ListStart, MapPin, Pause, Play, Plus, Route, RotateCcw, Save, Square, Trash2, Upload, X } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { IconButton } from "../../uiPrimitives";

const validPoint = (point) => Number.isFinite(Number(point?.lat)) && Number.isFinite(Number(point?.lon));

function createMissionId() {
  if (typeof window.crypto?.randomUUID === "function") return window.crypto.randomUUID();

  const bytes = new Uint8Array(16);
  if (typeof window.crypto?.getRandomValues === "function") window.crypto.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

class MinHeap {
  constructor() { this.items = []; }
  push(item) {
    this.items.push(item);
    let index = this.items.length - 1;
    while (index > 0) {
      const parent = Math.floor((index - 1) / 2);
      if (this.items[parent].score <= item.score) break;
      this.items[index] = this.items[parent]; index = parent;
    }
    this.items[index] = item;
  }
  pop() {
    if (!this.items.length) return null;
    const first = this.items[0]; const last = this.items.pop();
    if (this.items.length) {
      let index = 0;
      while (true) {
        const left = index * 2 + 1; const right = left + 1;
        if (left >= this.items.length) break;
        const child = right < this.items.length && this.items[right].score < this.items[left].score ? right : left;
        if (this.items[child].score >= last.score) break;
        this.items[index] = this.items[child]; index = child;
      }
      this.items[index] = last;
    }
    return first;
  }
  get length() { return this.items.length; }
}

function geoJsonFor(points, closed, coverage, exclusions) {
  const coordinates = points.map((point) => [Number(point.lon), Number(point.lat)]);
  const geometry = closed && coordinates.length >= 3
    ? { type: "Polygon", coordinates: [[...coordinates, coordinates[0]]] }
    : coordinates.length >= 2 ? { type: "LineString", coordinates } : null;
  return {
    type: "FeatureCollection",
    properties: { name: "HomeControl RTK editor", saved_at: new Date().toISOString(), closed },
    features: [
      ...(geometry ? [{ type: "Feature", properties: { name: closed ? "Mower boundary" : "Mower route", role: closed ? "boundary" : "route" }, geometry }] : []),
      ...exclusions.filter((zone) => zone.points.length >= 3).map((zone, index) => ({ type: "Feature", properties: { name: `Tiltott zóna ${index + 1}`, role: "exclusion", zone_id: zone.id }, geometry: { type: "Polygon", coordinates: [[...zone.points.map((point) => [point.lon, point.lat]), [zone.points[0].lon, zone.points[0].lat]]] } })),
      ...(coverage?.route?.length > 1 ? [{ type: "Feature", properties: { name: "Generated mowing plan", ...coverage.settings }, geometry: { type: "LineString", coordinates: coverage.route.map((point) => [point.lon, point.lat]) } }] : []),
      ...points.map((point, index) => ({ type: "Feature", properties: { ...point.properties, order: index + 1 }, geometry: { type: "Point", coordinates: [point.lon, point.lat] } })),
    ],
  };
}

function generateCoverage(points, exclusions, settings, options = {}) {
  if (points.length < 3) return null;
  const lat0 = points.reduce((sum, point) => sum + point.lat, 0) / points.length;
  const lon0 = points.reduce((sum, point) => sum + point.lon, 0) / points.length;
  const latRad = lat0 * Math.PI / 180;
  const heading = settings.heading * Math.PI / 180;
  const sin = Math.sin(heading);
  const cos = Math.cos(heading);
  const projected = points.map((point) => {
    const east = (point.lon - lon0) * Math.PI / 180 * 6378137 * Math.cos(latRad);
    const north = (point.lat - lat0) * Math.PI / 180 * 6378137;
    return { u: east * sin + north * cos, v: east * cos - north * sin };
  });
  const projectPoint = (point) => {
    const east = (point.lon - lon0) * Math.PI / 180 * 6378137 * Math.cos(latRad);
    const north = (point.lat - lat0) * Math.PI / 180 * 6378137;
    return { u: east * sin + north * cos, v: east * cos - north * sin };
  };
  const toProjected = (point) => {
    const east = (point.lon - lon0) * Math.PI / 180 * 6378137 * Math.cos(latRad);
    const north = (point.lat - lat0) * Math.PI / 180 * 6378137;
    return { u: east * sin + north * cos, v: east * cos - north * sin };
  };
  const polygonContains = (polygon, point) => {
    let result = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const a = polygon[i]; const b = polygon[j];
      if (((a.v > point.v) !== (b.v > point.v)) && point.u < (b.u - a.u) * (point.v - a.v) / (b.v - a.v) + a.u) result = !result;
    }
    return result;
  };
  const toLatLon = ({ u, v }) => {
    const east = u * sin + v * cos;
    const north = u * cos - v * sin;
    return { lat: lat0 + north / 6378137 * 180 / Math.PI, lon: lon0 + east / (6378137 * Math.cos(latRad)) * 180 / Math.PI };
  };
  const spacing = Math.max(0.05, settings.widthM * (1 - settings.overlap / 100));
  const margin = Math.max(0, settings.marginM) + Math.max(0, settings.roverWidthM) / 2;
  const rawProjectedExclusions = exclusions.filter((zone) => zone.points.length >= 3).map((zone) => zone.points.map(projectPoint));
  const projectedExclusions = rawProjectedExclusions.map((raw) => {
    const center = { u: raw.reduce((sum, point) => sum + point.u, 0) / raw.length, v: raw.reduce((sum, point) => sum + point.v, 0) / raw.length };
    return raw.map((point) => {
      const du = point.u - center.u; const dv = point.v - center.v; const length = Math.hypot(du, dv) || 1;
      return { u: point.u + du / length * margin, v: point.v + dv / length * margin };
    });
  });
  const distanceToSegment = (point, a, b) => {
    const du = b.u - a.u; const dv = b.v - a.v; const squared = du * du + dv * dv;
    const ratio = squared ? Math.max(0, Math.min(1, ((point.u - a.u) * du + (point.v - a.v) * dv) / squared)) : 0;
    return Math.hypot(point.u - (a.u + du * ratio), point.v - (a.v + dv * ratio));
  };
  const distanceToEdges = (polygon, point) => polygon.reduce((best, a, index) => Math.min(best, distanceToSegment(point, a, polygon[(index + 1) % polygon.length])), Infinity);
  const inside = (point) => polygonContains(projected, point)
    && distanceToEdges(projected, point) + 1e-5 >= margin
    && !rawProjectedExclusions.some((polygon) => polygonContains(polygon, point) || distanceToEdges(polygon, point) + 1e-5 < margin);
  const intervalsAt = (polygon, v) => {
    const intersections = [];
    polygon.forEach((a, index) => {
      const b = polygon[(index + 1) % polygon.length];
      if ((a.v <= v && b.v > v) || (b.v <= v && a.v > v)) intersections.push(a.u + (v - a.v) * (b.u - a.u) / (b.v - a.v));
    });
    intersections.sort((a, b) => a - b);
    const intervals = [];
    for (let index = 0; index + 1 < intersections.length; index += 2) intervals.push([intersections[index], intersections[index + 1]]);
    return intervals;
  };
  const minV = Math.min(...projected.map((point) => point.v)) + margin;
  const maxV = Math.max(...projected.map((point) => point.v)) - margin;
  const rows = [];
  for (let v = minV; v <= maxV + 1e-6; v += spacing) {
    const sampleStep = Math.min(0.04, spacing / 4);
    const available = intervalsAt(projected, v).flatMap(([start, end]) => {
      const safeRuns = []; let runStart = null; let lastSafe = null;
      const samples = Math.max(1, Math.ceil((end - start) / sampleStep));
      for (let sample = 0; sample <= samples; sample += 1) {
        const u = start + (end - start) * sample / samples;
        if (inside({ u, v })) {
          if (runStart === null) runStart = u;
          lastSafe = u;
        } else if (runStart !== null) {
          if (lastSafe - runStart > 0.1) safeRuns.push([runStart, lastSafe]);
          runStart = null; lastSafe = null;
        }
      }
      if (runStart !== null && lastSafe - runStart > 0.1) safeRuns.push([runStart, lastSafe]);
      return safeRuns;
    });
    if (available.length) rows.push({ v, intervals: available.map(([startU, endU]) => ({ startU, endU, cellId: null })) });
  }
  const cells = [];
  let previousIntervals = [];
  rows.forEach((row) => {
    const previousOverlapCounts = previousIntervals.map((previous) => row.intervals.filter((current) => Math.min(previous.endU, current.endU) - Math.max(previous.startU, current.startU) > 0.02).length);
    row.intervals.forEach((current) => {
      const overlaps = previousIntervals.map((previous, index) => ({ previous, index })).filter(({ previous }) => Math.min(previous.endU, current.endU) - Math.max(previous.startU, current.startU) > 0.02);
      if (overlaps.length === 1 && previousOverlapCounts[overlaps[0].index] === 1) current.cellId = overlaps[0].previous.cellId;
      else { current.cellId = cells.length; cells.push({ id: current.cellId, rows: [], minV: row.v, centerU: 0 }); }
      const cell = cells[current.cellId];
      cell.rows.push({ v: row.v, startU: current.startU, endU: current.endU });
      cell.centerU = cell.rows.reduce((sum, item) => sum + (item.startU + item.endU) / 2, 0) / cell.rows.length;
    });
    previousIntervals = row.intervals;
  });
  const remainingCells = cells.filter((cell) => cell.rows.length);
  remainingCells.forEach((cell) => {
    const baseSegments = cell.rows.map((item, index) => {
      const segment = [toLatLon({ u: item.startU, v: item.v }), toLatLon({ u: item.endU, v: item.v })];
      return index % 2 ? [segment[1], segment[0]] : segment;
    });
    const mirrored = baseSegments.map((segment) => [segment[1], segment[0]]);
    cell.variants = [
      baseSegments,
      mirrored,
      baseSegments.slice().reverse().map((segment) => [segment[1], segment[0]]),
      mirrored.slice().reverse().map((segment) => [segment[1], segment[0]]),
    ];
  });
  const orderedCells = []; const segments = []; let routeCursor = null;
  while (remainingCells.length) {
    let bestCellIndex = 0; let bestVariantIndex = 0; let bestDistance = Infinity;
    remainingCells.forEach((cell, cellIndex) => cell.variants.forEach((variant, variantIndex) => {
      const distance = routeCursor ? distanceMeters(routeCursor, variant[0][0]) : -cell.rows.length;
      if (distance < bestDistance) { bestDistance = distance; bestCellIndex = cellIndex; bestVariantIndex = variantIndex; }
    }));
    const [cell] = remainingCells.splice(bestCellIndex, 1);
    cell.segments = cell.variants[bestVariantIndex]; delete cell.variants;
    orderedCells.push(cell); segments.push(...cell.segments); routeCursor = cell.segments.at(-1)[1];
  }
  const segmentSafe = (a, b) => {
    const length = Math.hypot(b.u - a.u, b.v - a.v);
    const steps = Math.max(2, Math.ceil(length / 0.08));
    for (let step = 0; step <= steps; step += 1) {
      const ratio = step / steps;
      if (!inside({ u: a.u + (b.u - a.u) * ratio, v: a.v + (b.v - a.v) * ratio })) return false;
    }
    return true;
  };
  const shortestSafePath = (from, to) => {
    const start = toProjected(from); const end = toProjected(to);
    if (segmentSafe(start, end)) return [from, to];
    if (options.fast) return null;
    const minU = Math.min(...projected.map((point) => point.u)); const maxU = Math.max(...projected.map((point) => point.u));
    const gridMinV = Math.min(...projected.map((point) => point.v)); const gridMaxV = Math.max(...projected.map((point) => point.v));
    const area = Math.max(1, (maxU - minU) * (gridMaxV - gridMinV));
    const resolution = Math.max(0.1, Math.sqrt(area / 180000));
    const width = Math.ceil((maxU - minU) / resolution) + 1; const height = Math.ceil((gridMaxV - gridMinV) / resolution) + 1;
    const size = width * height;
    const state = new Uint8Array(size); const visited = new Uint8Array(size); const previous = new Int32Array(size); previous.fill(-1);
    const distance = new Float64Array(size); distance.fill(Infinity);
    const pointAt = (index) => ({ u: minU + (index % width) * resolution, v: gridMinV + Math.floor(index / width) * resolution });
    const isFree = (index) => {
      if (!state[index]) state[index] = inside(pointAt(index)) ? 2 : 1;
      return state[index] === 2;
    };
    const heuristic = (point) => Math.hypot(end.u - point.u, end.v - point.v);
    const open = new MinHeap();
    const seedX = Math.round((start.u - minU) / resolution); const seedY = Math.round((start.v - gridMinV) / resolution);
    for (let dy = -3; dy <= 3; dy += 1) for (let dx = -3; dx <= 3; dx += 1) {
      const x = seedX + dx; const y = seedY + dy;
      if (x < 0 || y < 0 || x >= width || y >= height) continue;
      const index = y * width + x; const point = pointAt(index);
      if (!isFree(index) || !segmentSafe(start, point)) continue;
      const cost = Math.hypot(point.u - start.u, point.v - start.v);
      if (cost < distance[index]) { distance[index] = cost; open.push({ index, cost, score: cost + heuristic(point) }); }
    }
    const directions = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]];
    let goalIndex = -1;
    while (open.length) {
      const current = open.pop();
      if (visited[current.index] || current.cost !== distance[current.index]) continue;
      visited[current.index] = 1;
      const currentPoint = pointAt(current.index);
      if (segmentSafe(currentPoint, end)) { goalIndex = current.index; break; }
      const currentX = current.index % width; const currentY = Math.floor(current.index / width);
      directions.forEach(([dx, dy]) => {
        const x = currentX + dx; const y = currentY + dy;
        if (x < 0 || y < 0 || x >= width || y >= height) return;
        const nextIndex = y * width + x;
        if (visited[nextIndex] || !isFree(nextIndex)) return;
        const nextPoint = pointAt(nextIndex);
        if (!segmentSafe(currentPoint, nextPoint)) return;
        const nextCost = current.cost + resolution * (dx && dy ? Math.SQRT2 : 1);
        if (nextCost >= distance[nextIndex]) return;
        distance[nextIndex] = nextCost; previous[nextIndex] = current.index;
        open.push({ index: nextIndex, cost: nextCost, score: nextCost + heuristic(nextPoint) });
      });
    }
    if (goalIndex < 0) return null;
    const rawPath = [end]; let cursor = goalIndex;
    while (cursor >= 0) { rawPath.push(pointAt(cursor)); cursor = previous[cursor]; }
    rawPath.push(start); rawPath.reverse();
    const simplified = [rawPath[0]]; let anchor = 0;
    while (anchor < rawPath.length - 1) {
      let next = rawPath.length - 1;
      while (next > anchor + 1 && !segmentSafe(rawPath[anchor], rawPath[next])) next -= 1;
      simplified.push(rawPath[next]); anchor = next;
    }
    if (simplified.slice(1).some((point, index) => !segmentSafe(simplified[index], point))) return null;
    return simplified.map(toLatLon);
  };
  const connectors = segments.slice(1).map((segment, index) => {
    const from = segments[index][1]; const to = segment[0];
    const path = shortestSafePath(from, to);
    const shownPath = path || [from, to];
    const lengthM = shownPath.slice(1).reduce((sum, point, pathIndex) => sum + distanceMeters(shownPath[pathIndex], point), 0);
    return { from, to, path: shownPath, safe: Boolean(path), lengthM };
  });
  const route = segments.length ? [segments[0][0], segments[0][1]] : [];
  connectors.forEach((connector, index) => {
    route.push(...connector.path.slice(1));
    const segmentEnd = segments[index + 1][1];
    if (route.at(-1).lat !== segmentEnd.lat || route.at(-1).lon !== segmentEnd.lon) route.push(segmentEnd);
  });
  const cuttingM = segments.reduce((sum, segment) => sum + distanceMeters(segment[0], segment[1]), 0);
  const totalM = cuttingM + connectors.reduce((sum, connector) => sum + connector.lengthM, 0);
  const unsafeConnectors = connectors.filter((connector) => !connector.safe).length;
  const detourConnectors = connectors.filter((connector) => connector.safe && connector.path.length > 2).length;
  return { segments, cells: orderedCells, connectors, route, cuttingM, totalM, unsafeConnectors, detourConnectors, turnTight: false, effectiveMarginM: margin, exclusionCount: projectedExclusions.length, executionReady: unsafeConnectors === 0, settings: { ...settings, driveType: "differential_tank", pivotTurn: true, spacingM: spacing } };
}

function distanceMeters(a, b) {
  const lat = ((a.lat + b.lat) / 2) * Math.PI / 180;
  const dx = (b.lon - a.lon) * Math.PI / 180 * 6378137 * Math.cos(lat);
  const dy = (b.lat - a.lat) * Math.PI / 180 * 6378137;
  return Math.hypot(dx, dy);
}

export default function RtkEditor({ setToast = () => {}, planningOnly = false }) {
  const { data: mowerData } = usePolledContext("/api/context/mower", { intervalMs: planningOnly ? 0 : 3000,
    initialData: planningOnly ? {} : null, refreshOnMount: !planningOnly, refreshPaths: planningOnly ? [] : ["/api/context/mower"] });
  const L = window.L;
  const mapElementRef = useRef(null);
  const mapRef = useRef(null);
  const editLayerRef = useRef(null);
  const coverageLayerRef = useRef(null);
  const simulationRef = useRef(null);
  const simulationTimerRef = useRef(null);
  const missionFileInputRef = useRef(null);
  const pointsRef = useRef([]);
  const exclusionsRef = useRef([]);
  const closedRef = useRef(false);
  const historyRef = useRef([]);
  const addModeRef = useRef(false);
  const drawingExclusionRef = useRef(false);
  const [points, setPoints] = useState([]);
  const [selected, setSelected] = useState(null);
  const [rangeMode, setRangeMode] = useState(false);
  const [rangeAnchor, setRangeAnchor] = useState(null);
  const [selectedIndexes, setSelectedIndexes] = useState([]);
  const [closed, setClosed] = useState(false);
  const [addMode, setAddMode] = useState(false);
  const [offsetCm, setOffsetCm] = useState("10");
  const [simulating, setSimulating] = useState(false);
  const [coverage, setCoverage] = useState(null);
  const [cutWidthCm, setCutWidthCm] = useState("42");
  const [overlapPct, setOverlapPct] = useState("15");
  const [marginCm, setMarginCm] = useState("25");
  const [headingDeg, setHeadingDeg] = useState("0");
  const [autoHeading, setAutoHeading] = useState(true);
  const [planning, setPlanning] = useState(false);
  const [speedMps, setSpeedMps] = useState("0.35");
  const [roverWidthCm, setRoverWidthCm] = useState("55");
  const [exclusions, setExclusions] = useState([]);
  const [exclusionDraft, setExclusionDraft] = useState([]);
  const [drawingExclusion, setDrawingExclusion] = useState(false);
  const [selectedExclusion, setSelectedExclusion] = useState(null);
  const [openedFileName, setOpenedFileName] = useState("Nincs fájl betöltve");
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [gotoBusy, setGotoBusy] = useState(false);
  const [missionBusy, setMissionBusy] = useState("");
  const [roverLengthCm, setRoverLengthCm] = useState("70");
  const [antennaForwardCm, setAntennaForwardCm] = useState("0");
  const [antennaLeftCm, setAntennaLeftCm] = useState("0");
  const [missionBladeRpm, setMissionBladeRpm] = useState("6000");
  const [loadedMission, setLoadedMission] = useState(null);
  const [loadedMissionName, setLoadedMissionName] = useState("");
  const positioningSupported = !planningOnly && mowerData?.integration?.capabilities?.includes("positioning.v1") === true;
  const missionUploadSupported = !planningOnly && mowerData?.integration?.mission_upload_enabled === true;
  const missionSupported = !planningOnly && mowerData?.integration?.mission_controls_enabled === true;
  const missionMode = planningOnly ? "planning" : mowerData?.integration?.mission_mode || "unavailable";
  const missionStatus = mowerData?.status?.mission || {};

  pointsRef.current = points;
  exclusionsRef.current = exclusions;
  closedRef.current = closed;
  addModeRef.current = addMode;
  drawingExclusionRef.current = drawingExclusion;

  function commit(next) {
    historyRef.current.push({
      points: pointsRef.current.map((point) => ({ ...point, properties: { ...(point.properties || {}) } })),
      exclusions: exclusionsRef.current.map((zone) => ({ ...zone, points: zone.points.map((point) => ({ ...point })) })),
      closed: closedRef.current,
    });
    if (historyRef.current.length > 100) historyRef.current.shift();
    setPoints(next);
  }

  function clearPointSelection() {
    setSelected(null); setSelectedIndexes([]); setRangeAnchor(null);
  }

  function selectBoundaryPoint(index) {
    if (!rangeMode) { setSelected(index); setSelectedIndexes([]); return; }
    setSelected(null);
    if (rangeAnchor === null) {
      setRangeAnchor(index); setSelectedIndexes([index]);
      setToast(`Kezdőpont: #${index + 1}. Válaszd ki a szakasz végét.`);
      return;
    }
    const start = Math.min(rangeAnchor, index); const end = Math.max(rangeAnchor, index);
    setSelectedIndexes(Array.from({ length: end - start + 1 }, (_, offset) => start + offset));
    setRangeAnchor(null);
    setToast(`${end - start + 1} egymást követő pont kijelölve`);
  }

  function removeSelectedPoints() {
    if (!selectedIndexes.length) return;
    const selectedSet = new Set(selectedIndexes);
    commit(points.filter((_, index) => !selectedSet.has(index)));
    clearPointSelection();
    setClosed((value) => value && points.length - selectedSet.size >= 3);
    setToast(`${selectedSet.size} pont törölve`);
  }

  function convertSelectionToExclusion() {
    if (selectedIndexes.length < 3) return setToast("Tiltott zónához legalább 3 pontot jelölj ki");
    const selectedSet = new Set(selectedIndexes);
    const zonePoints = selectedIndexes.slice().sort((a, b) => a - b).map((index) => ({ lat: points[index].lat, lon: points[index].lon }));
    commit(points.filter((_, index) => !selectedSet.has(index)));
    setExclusions((current) => [...current, { id: `zone-${Date.now()}`, points: zonePoints }]);
    clearPointSelection(); setRangeMode(false);
    setClosed((value) => value && points.length - selectedSet.size >= 3);
    setToast(`${zonePoints.length} pont tiltott zónává alakítva`);
  }

  useEffect(() => {
    if (!L || !mapElementRef.current || mapRef.current) return undefined;
    const map = L.map(mapElementRef.current, { maxZoom: 26, zoomSnap: 0.25, zoomDelta: 0.5 }).setView([47.15, 19.5], 7);
    const street = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxNativeZoom: 19, maxZoom: 22, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' });
    street.addTo(map);
    editLayerRef.current = L.layerGroup().addTo(map);
    coverageLayerRef.current = L.layerGroup().addTo(map);
    map.on("click", (event) => {
      if (drawingExclusionRef.current) {
        setExclusionDraft((current) => [...current, { lat: event.latlng.lat, lon: event.latlng.lng }]);
        return;
      }
      if (!addModeRef.current) return;
      commit([...pointsRef.current, { lat: event.latlng.lat, lon: event.latlng.lng, properties: {} }]);
    });
    mapRef.current = map;
    return () => { window.clearInterval(simulationTimerRef.current); map.remove(); mapRef.current = null; };
  }, [L]);

  useEffect(() => {
    if (!L || !editLayerRef.current) return;
    editLayerRef.current.clearLayers();
    const latLngs = points.map((point) => [point.lat, point.lon]);
    if (closed && points.length >= 3) L.polygon(latLngs, { color: "#40d9ff", weight: 4, fillOpacity: 0.12 }).addTo(editLayerRef.current);
    else if (points.length >= 2) L.polyline(latLngs, { color: "#40d9ff", weight: 5 }).addTo(editLayerRef.current);
    points.forEach((point, index) => {
      const icon = L.divIcon({
        className: `rtk-editor-point ${selected === index ? "selected" : ""} ${selectedIndexes.includes(index) ? "range-selected" : ""}`,
        html: `<span>${index + 1}</span>`,
        iconSize: selected === index ? [28, 28] : [24, 24],
        iconAnchor: selected === index ? [14, 14] : [12, 12],
      });
      const marker = L.marker([point.lat, point.lon], { icon, draggable: true, autoPan: true, keyboard: true });
      marker.addTo(editLayerRef.current).on("click", () => selectBoundaryPoint(index));
      marker.on("dragstart", () => setSelected(index));
      marker.on("dragend", (event) => {
        const position = event.target.getLatLng();
        const next = pointsRef.current.map((item, itemIndex) => itemIndex === index ? { ...item, lat: position.lat, lon: position.lng } : item);
        commit(next);
      });
    });
    exclusions.forEach((zone, zoneIndex) => {
      if (zone.points.length >= 3) L.polygon(zone.points.map((point) => [point.lat, point.lon]), { color: "#ff4d5a", weight: selectedExclusion === zoneIndex ? 5 : 3, fillColor: "#ff3344", fillOpacity: 0.2 }).addTo(editLayerRef.current).on("click", () => setSelectedExclusion(zoneIndex));
      zone.points.forEach((point, pointIndex) => {
        const icon = L.divIcon({ className: `rtk-exclusion-point ${selectedExclusion === zoneIndex ? "selected" : ""}`, html: `<span>${zoneIndex + 1}.${pointIndex + 1}</span>`, iconSize: [27, 27], iconAnchor: [13, 13] });
        const marker = L.marker([point.lat, point.lon], { icon, draggable: true, autoPan: true });
        marker.addTo(editLayerRef.current).on("click", () => setSelectedExclusion(zoneIndex)).on("dragend", (event) => {
          const position = event.target.getLatLng();
          setExclusions((current) => current.map((item, itemZoneIndex) => itemZoneIndex === zoneIndex ? { ...item, points: item.points.map((itemPoint, itemPointIndex) => itemPointIndex === pointIndex ? { lat: position.lat, lon: position.lng } : itemPoint) } : item));
        });
      });
    });
    if (exclusionDraft.length) L.polyline(exclusionDraft.map((point) => [point.lat, point.lon]), { color: "#ff4d5a", weight: 3, dashArray: "6 5" }).addTo(editLayerRef.current);
  }, [L, points, closed, selected, selectedIndexes, rangeMode, rangeAnchor, exclusions, exclusionDraft, selectedExclusion]);

  useEffect(() => { setCoverage(null); setSelectedConnector(null); stopSimulation(); }, [points, closed, exclusions]);

  useEffect(() => {
    if (!L || !coverageLayerRef.current) return;
    coverageLayerRef.current.clearLayers();
    if (!coverage) return;
    const cellColors = ["#b7ff4a", "#40d9ff", "#d38cff", "#ffe45c", "#65f0b1"];
    coverage.cells.forEach((cell, cellIndex) => cell.segments.forEach((segment) => L.polyline(segment.map((point) => [point.lat, point.lon]), { color: cellColors[cellIndex % cellColors.length], weight: 4, opacity: 0.95 }).addTo(coverageLayerRef.current)));
    coverage.connectors.forEach((connector, index) => L.polyline(connector.path.map((point) => [point.lat, point.lon]), { color: connector.safe ? "#ffb020" : "#ff4d5a", weight: selectedConnector === index ? 8 : connector.safe ? 3 : 4, opacity: selectedConnector === index ? 1 : 0.9, dashArray: selectedConnector === index ? undefined : "5 6" }).addTo(coverageLayerRef.current));
  }, [L, coverage, selectedConnector]);

  async function importGeoJson(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      const features = data.type === "FeatureCollection" ? data.features || [] : [data];
      const polygonFeatures = features.filter((feature) => feature?.geometry?.type === "Polygon");
      const polygon = polygonFeatures.find((feature) => feature?.properties?.role !== "exclusion");
      const line = features.find((feature) => feature?.geometry?.type === "LineString");
      let coordinates = polygon?.geometry?.coordinates?.[0] || line?.geometry?.coordinates;
      let isClosed = Boolean(polygon);
      if (polygon && coordinates?.length > 1 && coordinates[0][0] === coordinates.at(-1)[0] && coordinates[0][1] === coordinates.at(-1)[1]) coordinates = coordinates.slice(0, -1);
      if (!coordinates?.length) coordinates = features.filter((feature) => feature?.geometry?.type === "Point").map((feature) => feature.geometry.coordinates);
      const next = (coordinates || []).map(([lon, lat]) => ({ lat: Number(lat), lon: Number(lon), properties: {} })).filter(validPoint);
      if (!next.length) throw new Error("A fájl nem tartalmaz használható pontokat");
      const importedExclusions = polygonFeatures.filter((feature) => feature !== polygon && (feature.properties?.role === "exclusion" || polygonFeatures.indexOf(feature) > 0)).map((feature, index) => {
        let zoneCoordinates = feature.geometry.coordinates?.[0] || [];
        if (zoneCoordinates.length > 1 && zoneCoordinates[0][0] === zoneCoordinates.at(-1)[0] && zoneCoordinates[0][1] === zoneCoordinates.at(-1)[1]) zoneCoordinates = zoneCoordinates.slice(0, -1);
        return { id: feature.properties?.zone_id || `zone-${Date.now()}-${index}`, points: zoneCoordinates.map(([lon, lat]) => ({ lat: Number(lat), lon: Number(lon) })).filter(validPoint) };
      }).filter((zone) => zone.points.length >= 3);
      commit(next); setClosed(isClosed); clearPointSelection(); setRangeMode(false); setExclusions(importedExclusions); setSelectedExclusion(null); setOpenedFileName(file.name);
      mapRef.current?.fitBounds(next.map((point) => [point.lat, point.lon]), { padding: [35, 35], maxZoom: 21 });
      setToast(`${next.length} határpont és ${importedExclusions.length} tiltott zóna betöltve`);
    } catch (error) { setToast(`GeoJSON hiba: ${error.message}`); }
  }

  function offset(north, east) {
    const centimeters = Number(offsetCm);
    if (!Number.isFinite(centimeters) || centimeters <= 0) return setToast("Adj meg pozitív eltolást centiméterben");
    const indexes = selected === null ? points.map((_, index) => index) : [selected];
    const meters = centimeters / 100;
    commit(points.map((point, index) => indexes.includes(index) ? {
      ...point,
      lat: point.lat + north * meters / 6378137 * 180 / Math.PI,
      lon: point.lon + east * meters / (6378137 * Math.cos(point.lat * Math.PI / 180)) * 180 / Math.PI,
    } : point));
  }

  function undo() {
    const previous = historyRef.current.pop();
    if (previous) {
      setPoints(previous.points || previous);
      if (previous.exclusions) setExclusions(previous.exclusions);
      if (typeof previous.closed === "boolean") setClosed(previous.closed);
      clearPointSelection();
    }
  }

  function exclusionAction() {
    if (!drawingExclusion) {
      setAddMode(false); setExclusionDraft([]); setDrawingExclusion(true); setSelectedExclusion(null); return;
    }
    if (exclusionDraft.length < 3) return setToast("A tiltott zónához legalább 3 pont kell");
    setExclusions((current) => [...current, { id: `zone-${Date.now()}`, points: exclusionDraft }]);
    setExclusionDraft([]); setDrawingExclusion(false); setToast("Tiltott zóna lezárva");
  }

  function download() {
    if (!points.length) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(geoJsonFor(points, closed, coverage, exclusions), null, 2)], { type: "application/geo+json" }));
    const link = document.createElement("a"); link.href = url; link.download = `rtk-editor-${new Date().toISOString().replace(/[:.]/g, "-")}.geojson`; link.click(); URL.revokeObjectURL(url);
    setToast(`${points.length} pont elmentve`);
  }

  function stopSimulation() {
    window.clearInterval(simulationTimerRef.current); simulationTimerRef.current = null; simulationRef.current?.remove(); simulationRef.current = null; setSimulating(false);
  }

  function simulate() {
    const sequence = coverage?.route?.length ? coverage.route : closed ? [...points, points[0]] : points;
    if (sequence.length < 2 || !L || !mapRef.current) return;
    stopSimulation(); setSimulating(true); let index = 0;
    simulationRef.current = L.circleMarker([sequence[0].lat, sequence[0].lon], { radius: 9, color: "#fff", fillColor: "#ffb020", fillOpacity: 1, weight: 3 }).addTo(mapRef.current);
    simulationTimerRef.current = window.setInterval(() => { index += 1; if (index >= sequence.length) return stopSimulation(); simulationRef.current?.setLatLng([sequence[index].lat, sequence[index].lon]); }, 700);
  }

  async function buildCoverage() {
    const settings = { widthM: Number(cutWidthCm) / 100, overlap: Number(overlapPct), marginM: Number(marginCm) / 100, roverWidthM: Number(roverWidthCm) / 100, heading: ((Number(headingDeg) % 360) + 360) % 360, speedMps: Number(speedMps) };
    if (!closed || points.length < 3) return setToast("Előbb zárd le a legalább 3 pontos határt");
    if (!(settings.widthM > 0) || settings.overlap < 0 || settings.overlap >= 90 || settings.marginM < 0 || !(settings.roverWidthM > 0) || !(settings.speedMps > 0)) return setToast("Ellenőrizd a tervezési paramétereket");
    setPlanning(true);
    await new Promise((resolve) => window.setTimeout(resolve, 30));
    let next;
    if (autoHeading) {
      const candidates = Array.from({ length: 18 }, (_, index) => index * 10).map((heading) => {
        const plan = generateCoverage(points, exclusions, { ...settings, heading }, { fast: true });
        return { heading, plan, coarseScore: plan ? plan.unsafeConnectors * 100000 + plan.cells.length * 100 + plan.totalM : Infinity };
      }).filter((candidate) => candidate.plan?.segments.length).sort((a, b) => a.coarseScore - b.coarseScore).slice(0, 4);
      const finalists = candidates.map((candidate) => {
        const plan = generateCoverage(points, exclusions, { ...settings, heading: candidate.heading });
        return { plan, score: plan ? plan.unsafeConnectors * 1000000000 + plan.totalM + plan.cells.length * 0.2 : Infinity };
      }).sort((a, b) => a.score - b.score);
      next = finalists[0]?.plan || null;
      if (next) setHeadingDeg(String(next.settings.heading));
    } else next = generateCoverage(points, exclusions, settings);
    setPlanning(false);
    if (!next?.segments.length) return setToast("A beállított határtávolsággal nem fér el nyírási sáv");
    setCoverage(next); setToast(autoHeading ? `Optimális irány: ${next.settings.heading}° · ${next.segments.length} nyírási sáv` : `${next.segments.length} nyírási sáv generálva`);
  }

  function compileMission() {
    if (!coverage?.executionReady || !coverage.segments?.length) throw new Error("Csak hibamentes, megoldott átkötésű tervből készíthető mission");
    const roverWidthMm = Math.round(Number(roverWidthCm) * 10); const roverLengthMm = Math.round(Number(roverLengthCm) * 10);
    const cutWidthMm = Math.round(Number(cutWidthCm) * 10); const clearanceMm = Math.round(Number(marginCm) * 10);
    const antennaForwardMm = Math.round(Number(antennaForwardCm) * 10); const antennaLeftMm = Math.round(Number(antennaLeftCm) * 10);
    const bladeRpm = Math.round(Number(missionBladeRpm)); const driveSpeed = Math.round(Number(speedMps) * 1000);
    if (!(roverWidthMm > 0 && roverLengthMm > 0 && cutWidthMm > 0 && clearanceMm >= 0 && bladeRpm > 0 && driveSpeed > 0)) throw new Error("Ellenőrizd a mission gép- és sebességadatait");
    const origin = points[0]; const latRad = origin.lat * Math.PI / 180;
    const toEnu = (point) => ({
      east_mm: Math.round((point.lon - origin.lon) * Math.PI / 180 * 6378137 * Math.cos(latRad) * 1000),
      north_mm: Math.round((point.lat - origin.lat) * Math.PI / 180 * 6378137 * 1000),
    });
    const segmentMeta = new Map();
    coverage.cells.forEach((cell, cellIndex) => cell.segments.forEach((segment, laneIndex) => segmentMeta.set(segment, { cell: cellIndex + 1, lane: laneIndex + 1 })));
    const operations = []; const first = toEnu(coverage.segments[0][0]);
    operations.push({ type: "PATH_START", ...first, tolerance_mm: 250 }, { type: "BLADE_ON", target_rpm: bladeRpm });
    let current = coverage.segments[0][0];
    const appendDrive = (target, blade, cell = 0, lane = 0) => {
      const fromEnu = toEnu(current); const targetEnu = toEnu(target);
      const east = targetEnu.east_mm - fromEnu.east_mm; const north = targetEnu.north_mm - fromEnu.north_mm;
      if (Math.hypot(east, north) < 10) { current = target; return; }
      const heading = Math.round((((Math.atan2(east, north) * 180 / Math.PI) % 360 + 360) % 360) * 1000);
      operations.push({ type: "TURN_IN_PLACE", heading_mdeg: heading });
      operations.push({ type: "DRIVE_LINE", ...targetEnu, speed_mm_s: blade ? driveSpeed : Math.min(200, driveSpeed), blade: true, cell, lane });
      current = target;
    };
    coverage.segments.forEach((segment, index) => {
      if (index > 0) {
        const connector = coverage.connectors[index - 1];
        if (!connector?.safe) throw new Error(`A(z) #${index} átkötés nincs megoldva`);
        connector.path.slice(1).forEach((point) => appendDrive(point, false));
      }
      const meta = segmentMeta.get(segment) || { cell: 0, lane: 0 };
      appendDrive(segment[1], true, meta.cell, meta.lane);
    });
    operations.push({ type: "BLADE_OFF" }, { type: "STOP" });
    if (operations.length > 4096) throw new Error(`Túl sok mission művelet: ${operations.length}/4096`);
    const missionId = createMissionId();
    return {
      schema: "hc.mower.mission.v1", mission_id: missionId, revision: Math.floor(Date.now() / 1000), created_at: new Date().toISOString(),
      origin: { lat_e7: Math.round(origin.lat * 1e7), lon_e7: Math.round(origin.lon * 1e7) },
      geometry: { drive_type: "differential_tank", pivot_turn: true, rover_width_mm: roverWidthMm, rover_length_mm: roverLengthMm, pivot_safety_radius_mm: Math.ceil(Math.hypot(roverWidthMm, roverLengthMm) / 2 + 25), cut_width_mm: cutWidthMm, antenna_forward_mm: antennaForwardMm, antenna_left_mm: antennaLeftMm, boundary_clearance_mm: clearanceMm },
      limits: { drive_speed_mm_s: driveSpeed, connector_speed_mm_s: Math.min(200, driveSpeed), turn_speed_mdeg_s: 30000, start_tolerance_mm: 250, waypoint_tolerance_mm: 120, max_cross_track_mm: 250, max_heading_error_mdeg: 45000, max_rtk_age_ms: 1500, max_correction_age_ms: 3000 },
      boundary: points.map(toEnu), exclusions: exclusions.map((zone) => zone.points.map(toEnu)), operations,
    };
  }

  function downloadMission() {
    try {
      const mission = compileMission(); const url = URL.createObjectURL(new Blob([JSON.stringify(mission, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = `mower-mission-${mission.mission_id}.json`; link.click(); URL.revokeObjectURL(url);
      setToast(`${mission.operations.length} műveletes mission JSON elmentve`);
    } catch (error) { setToast(`Mission fordítási hiba: ${error.message}`); }
  }

  async function loadMissionFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) return setToast("A mission JSON legfeljebb 5 MiB lehet");
    try {
      const mission = JSON.parse(await file.text());
      if (!mission || mission.schema !== "hc.mower.mission.v1") throw new Error("nem támogatott vagy hiányzó schema");
      if (typeof mission.mission_id !== "string" || !mission.mission_id.trim()) throw new Error("hiányzó mission_id");
      if (!Number.isInteger(mission.revision) || mission.revision < 1) throw new Error("hibás revision");
      if (!mission.origin || !mission.geometry || !mission.limits) throw new Error("hiányzó origin, geometry vagy limits");
      if (!Array.isArray(mission.boundary) || mission.boundary.length < 3) throw new Error("a boundary legalább 3 pontot igényel");
      if (!Array.isArray(mission.operations) || mission.operations.length < 4) throw new Error("hiányzó mission műveletek");
      setLoadedMission(mission);
      setLoadedMissionName(file.name);
      setToast(`Mission betöltve: ${file.name} · ${mission.operations.length} művelet`);
    } catch (error) {
      setLoadedMission(null);
      setLoadedMissionName("");
      setToast(`Mission fájl hiba: ${error.message}`);
    }
  }

  function clearLoadedMission() {
    setLoadedMission(null);
    setLoadedMissionName("");
    setToast("A betöltött mission eltávolítva; ismét az editor terve lesz használva");
  }

  async function deployMission() {
    if (planningOnly) return;
    setMissionBusy("deploy");
    try {
      const mission = loadedMission || compileMission();
      const result = await api("/api/mower/mission/deploy", { method: "POST", body: JSON.stringify(mission) });
      setToast(result.mode === "preview"
        ? `Mission feltöltve és preview-validálva · ${result.operation_count} művelet · aktiválás nélkül`
        : `Mission aktív · ${result.operation_count} művelet · CRC ${result.payload_crc32}`);
    } catch (error) { setToast(`Mission telepítési hiba: ${error.message}`); }
    finally { setMissionBusy(""); }
  }

  async function missionAction(action) {
    if (planningOnly) return;
    if (action === "start" && !window.confirm("A térképes mission elindíthatja a rovert és a kést. A terület biztonságos és felügyelt?")) return;
    setMissionBusy(action);
    try {
      const result = await api(`/api/mower/mission/${action}`, { method: "POST", body: "{}" });
      setToast(result.message || `Mission ${action} parancs elküldve`);
    } catch (error) { setToast(`Mission ${action} hiba: ${error.message}`); }
    finally { setMissionBusy(""); }
  }

  function focusConnector(connector, index) {
    setSelectedConnector(index);
    const connectorPoints = connector.path?.length ? connector.path : [connector.from, connector.to];
    if (connectorPoints.length) mapRef.current?.fitBounds(connectorPoints.map((point) => [point.lat, point.lon]), { padding: [90, 90], maxZoom: 24 });
    setToast(`A(z) #${index + 1} megoldatlan átkötés kiemelve`);
  }

  async function sendRoverToSelectedPoint() {
    if (planningOnly) return;
    if (selected === null || !points[selected]) return;
    const point = points[selected];
    if (!window.confirm(`A rover a(z) #${selected + 1} határponthoz indulhat. A kés kikapcsolva marad. Indítható?`)) return;
    setGotoBusy(true);
    try {
      const result = await api("/api/mower/command", { method: "POST", body: JSON.stringify({ command: "goto_point", value: { lat: point.lat, lon: point.lon, speed_mps: Math.min(0.2, Number(speedMps) || 0.2) } }) });
      setToast(`Pozicionálási parancs elküldve · ${result.request_id}`);
    } catch (error) { setToast(`A rover nem indítható: ${error.message}`); }
    finally { setGotoBusy(false); }
  }

  const length = points.slice(1).reduce((sum, point, index) => sum + distanceMeters(points[index], point), 0) + (closed && points.length > 2 ? distanceMeters(points.at(-1), points[0]) : 0);

  return <div className="rtk-editor-page">
    <div className="page-heading"><div><span className="eyebrow">Mower survey</span><h1>RTK Editor</h1><p>Határvonalak és waypoint útvonalak centiméteres szerkesztése és szimulációja.</p></div></div>
    <article className="panel rtk-editor-toolbar">
      <label className="rtk-editor-file"><FolderOpen size={16} /><span>GeoJSON betöltése</span><input type="file" accept=".geojson,.json,application/geo+json,application/json" onChange={importGeoJson} /></label>
      <div className="rtk-editor-open-file" title={openedFileName}><FileJson size={16} /><span>Megnyitva:</span><strong>{openedFileName}</strong></div>
      <IconButton icon={Plus} className={addMode ? "active" : "secondary"} onClick={() => setAddMode((value) => !value)}>{addMode ? "Pontozás be" : "Pont hozzáadása"}</IconButton>
      <IconButton icon={RotateCcw} className="secondary" disabled={!historyRef.current.length} onClick={undo}>Visszavonás</IconButton>
      <IconButton icon={MapPin} className="secondary" disabled={points.length < 3} onClick={() => setClosed((value) => !value)}>{closed ? "Határ megnyitása" : "Határ zárása"}</IconButton>
      <IconButton icon={rangeMode ? X : ListStart} className={rangeMode ? "active" : "secondary"} disabled={!points.length} onClick={() => { setRangeMode((value) => !value); clearPointSelection(); }}>{rangeMode ? "Szakaszkijelölés vége" : "Szakasz kijelölése"}</IconButton>
      {selectedIndexes.length > 0 && <IconButton icon={Trash2} className="danger" onClick={removeSelectedPoints}>Kijelölt pontok törlése ({selectedIndexes.length})</IconButton>}
      {selectedIndexes.length >= 3 && <IconButton icon={Ban} className="danger" onClick={convertSelectionToExclusion}>Tiltott zónává ({selectedIndexes.length})</IconButton>}
      <IconButton icon={drawingExclusion ? Save : Plus} className={drawingExclusion ? "danger" : "secondary"} onClick={exclusionAction}>{drawingExclusion ? `Tiltott zóna lezárása (${exclusionDraft.length})` : "Tiltott zóna rajzolása"}</IconButton>
      {drawingExclusion && <IconButton icon={Square} className="secondary" onClick={() => { setExclusionDraft([]); setDrawingExclusion(false); }}>Rajzolás megszakítása</IconButton>}
      {!drawingExclusion && selectedExclusion !== null && <IconButton icon={Trash2} className="danger" onClick={() => { setExclusions((current) => current.filter((_, index) => index !== selectedExclusion)); setSelectedExclusion(null); }}>Kijelölt zóna törlése</IconButton>}
      <IconButton icon={Save} disabled={!points.length} onClick={download}>Mentés</IconButton>
      <IconButton icon={Trash2} className="danger" disabled={!points.length} onClick={() => { commit([]); setSelected(null); }}>Törlés</IconButton>
    </article>
    <div className="rtk-editor-layout">
      <article className="panel rtk-editor-map-panel">
        <div ref={mapElementRef} className={`rtk-editor-map ${addMode || drawingExclusion ? "adding" : ""}`} />
        <section className="rtk-editor-guide">
          <div><span className="eyebrow">Gyors segítség</span><h2>A felvett nyomvonal darabolása</h2></div>
          <ol>
            <li>Nyomd meg a <strong>Szakasz kijelölése</strong> gombot.</li>
            <li>Kattints a szakasz első, majd utolsó pontjára.</li>
            <li>A két pont közötti teljes szakasz piros kijelölést kap.</li>
            <li>Válaszd a <strong>Kijelölt pontok törlése</strong> vagy a <strong>Tiltott zónává</strong> műveletet.</li>
          </ol>
          <div className="rtk-editor-guide-notes">
            <p><strong>Egy pont javítása:</strong> kattints a pontra, majd húzd arrébb vagy mozgasd a nyilakkal.</p>
            <p><strong>Nagyobb nagyítás:</strong> nagyíts tovább a térképcsempék határánál; az editor automatikusan a rácsos precíziós háttéren folytatja, akár 26-os zoomig.</p>
            <p><strong>Biztonsági mentés:</strong> nagyobb átalakítás előtt használd a Mentés gombot; az utolsó művelet a Visszavonással is helyreállítható.</p>
          </div>
        </section>
      </article>
      <aside className="panel rtk-editor-side">
        <div className="panel-head"><h2>Finomhangolás</h2><span>{selectedIndexes.length ? `${selectedIndexes.length} pont kijelölve` : selected === null ? "Teljes alakzat" : `#${selected + 1}. pont`}</span></div>
        <label>Eltolás <span>{offsetCm} cm</span><input type="number" min="1" step="1" value={offsetCm} onChange={(event) => setOffsetCm(event.target.value)} /></label>
        <div className="rtk-offset-pad"><button onClick={() => offset(1, 0)} title="Észak"><ArrowUp /></button><button onClick={() => offset(0, -1)} title="Nyugat"><ArrowLeft /></button><button onClick={() => setSelected(null)} title="Kijelölés törlése">Mind</button><button onClick={() => offset(0, 1)} title="Kelet"><ArrowRight /></button><button onClick={() => offset(-1, 0)} title="Dél"><ArrowDown /></button></div>
        <small className="rtk-editor-selection-help">{rangeMode ? (rangeAnchor === null ? "Érintsd meg a szakasz első pontját, majd az utolsót." : `Kezdőpont: #${rangeAnchor + 1}. Most válaszd ki a szakasz végét.`) : selectedIndexes.length ? "A kijelölt pontokat törölheted vagy tiltott zónává alakíthatod a felső eszköztáron." : selected === null ? "Nincs kijelölt pont: a nyilak a teljes alakzatot mozgatják." : `A(z) #${selected + 1} pont aktív: húzd a térképen, vagy mozgasd a nyilakkal.`}</small>
        <div className="rtk-goto-point"><IconButton icon={MapPin} disabled={selected === null || !positioningSupported || gotoBusy} onClick={sendRoverToSelectedPoint}>{gotoBusy ? "Pozicionálási parancs…" : selected === null ? "Jelölj ki egy határpontot" : `Rover küldése a(z) #${selected + 1} ponthoz`}</IconButton>{!positioningSupported && <small>A rover firmware még nem jelzi a positioning.v1 képességet; a gomb az ESP/STM támogatás elkészültekor válik aktívvá.</small>}</div>
        <div className="mower-data-list"><div className="mower-data-row"><span>Pontok</span><strong>{points.length}</strong></div><div className="mower-data-row"><span>Hossz</span><strong>{length.toFixed(2)} m</strong></div><div className="mower-data-row"><span>Alakzat</span><strong>{closed ? "Zárt határ" : "Nyitott útvonal"}</strong></div><div className="mower-data-row"><span>Tiltott zónák</span><strong>{exclusions.length}</strong></div></div>
        <div className="rtk-coverage-config"><h3><Route size={17} /> Bejárási terv</h3><label>Vágásszélesség <span>cm</span><input type="number" min="5" step="1" value={cutWidthCm} onChange={(event) => setCutWidthCm(event.target.value)} /></label><label>Átfedés <span>%</span><input type="number" min="0" max="89" step="1" value={overlapPct} onChange={(event) => setOverlapPct(event.target.value)} /></label><label>Határtávolság <span>cm</span><input type="number" min="0" step="1" value={marginCm} onChange={(event) => setMarginCm(event.target.value)} /></label><label>Gépszélesség <span>cm</span><input type="number" min="10" step="1" value={roverWidthCm} onChange={(event) => setRoverWidthCm(event.target.value)} /></label><div className="rtk-drive-type"><span>Hajtásmód</span><strong>Tankkormányzás · helyben fordul</strong></div><label className="rtk-auto-heading"><span>Menetirány</span><button type="button" className={autoHeading ? "active" : ""} onClick={() => setAutoHeading((value) => !value)}>{autoHeading ? "Automatikus" : "Kézi"}</button></label><label>Menetirány <span>° északtól</span><input type="number" min="0" max="359" step="1" value={headingDeg} disabled={autoHeading} onChange={(event) => setHeadingDeg(event.target.value)} /></label><label>Tervezett sebesség <span>m/s</span><input type="number" min="0.05" step="0.05" value={speedMps} onChange={(event) => setSpeedMps(event.target.value)} /></label><IconButton icon={Route} disabled={!closed || points.length < 3 || planning} onClick={buildCoverage}>{planning ? "Optimális irány keresése…" : "Bejárás generálása"}</IconButton></div>
        {coverage && <><div className={`mower-data-list rtk-coverage-results ${coverage.executionReady ? "ready" : "warning"}`}><div className="mower-data-row"><span>Tervezési állapot</span><strong>{coverage.executionReady ? "ELLENŐRZÉS RENDBEN" : "BEAVATKOZÁS KELL"}</strong></div><div className="mower-data-row"><span>Logikai mezők</span><strong>{coverage.cells.length}</strong></div><div className="mower-data-row"><span>Nyírási sávok</span><strong>{coverage.segments.length}</strong></div><div className="mower-data-row"><span>Kikerült zónák</span><strong>{coverage.exclusionCount}</strong></div><div className="mower-data-row"><span>Generált kerülők</span><strong>{coverage.detourConnectors}</strong></div><div className="mower-data-row"><span>Vágási táv</span><strong>{coverage.cuttingM.toFixed(1)} m</strong></div><div className="mower-data-row"><span>Teljes bejárás</span><strong>{coverage.totalM.toFixed(1)} m</strong></div><div className="mower-data-row"><span>Becsült idő</span><strong>{(coverage.totalM / Number(speedMps) / 60).toFixed(1)} perc</strong></div><div className="mower-data-row"><span>Effektív peremtáv</span><strong>{(coverage.effectiveMarginM * 100).toFixed(0)} cm</strong></div><div className="mower-data-row"><span>Megoldatlan átkötés</span><strong>{coverage.unsafeConnectors}</strong></div><div className="mower-data-row"><span>Fordulóhely</span><strong>{coverage.turnTight ? "SZŰK" : "MEGFELELŐ"}</strong></div></div>
        {coverage.unsafeConnectors > 0 && <div className="rtk-unsafe-connectors"><h3><Eye size={17} /> Megoldatlan átkötések</h3><p>A tervező nem talált biztonságos, határon belüli utat a két nyírási szakasz között.</p>{coverage.connectors.map((connector, index) => !connector.safe && <button key={index} className={selectedConnector === index ? "active" : ""} onClick={() => focusConnector(connector, index)}><span>Átkötés #{index + 1}</span><strong>{connector.lengthM.toFixed(2)} m</strong><Eye size={15} /></button>)}</div>}</>}
        <div className={`rtk-mission-panel ${missionUploadSupported ? "supported" : "disabled"}`}>
          <h3><Upload size={17} /> Térképes mission</h3>
          <div className="rtk-mission-state"><span>Rover támogatás</span><strong>{missionMode === "full" ? "MISSION.V1 · TELJES" : missionMode === "preview" ? "UPLOAD PREVIEW" : "NEM ELÉRHETŐ"}</strong><span>Állapot</span><strong>{missionStatus.state || "-"}</strong><span>Előrehaladás</span><strong>{Number.isFinite(Number(missionStatus.progress_ratio)) ? `${(Number(missionStatus.progress_ratio) * 100).toFixed(1)}%` : "-"}</strong><span>Művelet</span><strong>{missionStatus.operation_type || "-"}</strong></div>
          <input ref={missionFileInputRef} type="file" accept="application/json,.json" hidden onChange={loadMissionFile} />
          <div className="rtk-mission-file"><IconButton icon={FolderOpen} className="secondary" disabled={Boolean(missionBusy)} onClick={() => missionFileInputRef.current?.click()}>Mission JSON betöltése</IconButton>{loadedMission && <div><span title={loadedMissionName}>{loadedMissionName}</span><small>{loadedMission.operations.length} művelet · rev. {loadedMission.revision}</small><button type="button" onClick={clearLoadedMission} aria-label="Betöltött mission eltávolítása"><X size={15} /></button></div>}</div>
          <div className="rtk-mission-geometry"><label>Rover hossza <span>cm</span><input type="number" min="10" step="1" value={roverLengthCm} onChange={(event) => setRoverLengthCm(event.target.value)} /></label><label>Antenna előre <span>cm</span><input type="number" step="1" value={antennaForwardCm} onChange={(event) => setAntennaForwardCm(event.target.value)} /></label><label>Antenna balra <span>cm</span><input type="number" step="1" value={antennaLeftCm} onChange={(event) => setAntennaLeftCm(event.target.value)} /></label><label>Kés célfordulat <span>rpm</span><input type="number" min="1" max="25000" step="100" value={missionBladeRpm} onChange={(event) => setMissionBladeRpm(event.target.value)} /></label></div>
          <div className="rtk-mission-actions"><IconButton icon={Save} disabled={!coverage?.executionReady || Boolean(missionBusy)} onClick={downloadMission}>Mission JSON mentése</IconButton>{!planningOnly && <><IconButton icon={Upload} disabled={(!loadedMission && !coverage?.executionReady) || !missionUploadSupported || Boolean(missionBusy)} onClick={deployMission}>{missionBusy === "deploy" ? "Feltöltés…" : loadedMission ? (missionMode === "preview" ? "Betöltött mission preview feltöltése" : "Betöltött mission feltöltése és aktiválása") : missionMode === "preview" ? "Fordítás és preview feltöltés" : "Fordítás, feltöltés, aktiválás"}</IconButton><IconButton icon={Play} disabled={!missionSupported || missionStatus.state !== "ACTIVE_IDLE" || Boolean(missionBusy)} onClick={() => missionAction("start")}>Mission indítása</IconButton><IconButton icon={Pause} className="secondary" disabled={!missionSupported || missionStatus.state !== "RUNNING" || Boolean(missionBusy)} onClick={() => missionAction("pause")}>Szünet</IconButton><IconButton icon={RotateCcw} className="secondary" disabled={!missionSupported || !["PAUSED", "PAUSED_RESTART"].includes(missionStatus.state) || Boolean(missionBusy)} onClick={() => missionAction("resume")}>Folytatás</IconButton><IconButton icon={Square} className="danger" disabled={!missionSupported || !["RUNNING", "PAUSED", "PAUSED_RESTART"].includes(missionStatus.state) || Boolean(missionBusy)} onClick={() => missionAction("stop")}>Mission stop</IconButton></>}</div>
          {missionMode === "preview" && <small>A rover csak <code>mission.upload_preview.v1</code> képességet hirdet: feltöltés és diagnosztikai validálás engedett, aktiválás és mozgatás nem.</small>}
          {missionMode === "unavailable" && <small>Mission írás csak friss, legalább 2.4.0 szerződés és <code>mission.v1</code> vagy <code>mission.upload_preview.v1</code> capability mellett engedett. A read-only státusz ettől még lekérdezhető.</small>}
        </div>
        <div className="rtk-editor-sim"><IconButton icon={simulating ? Square : Play} disabled={(coverage?.route?.length || points.length) < 2} onClick={simulating ? stopSimulation : simulate}>{simulating ? "Szimuláció leállítása" : coverage ? "Bejárás lejátszása" : "Határ lejátszása"}</IconButton></div>
        <p className="mower-safety-note">A térképi háttér csak tájékozódási alap. A centiméteres határt az RTK méréshez igazítsd.</p>
      </aside>
    </div>
  </div>;
}
