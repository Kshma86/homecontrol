import { useState } from "react";
import { dateText, dayLabel, metricNumber, timestampLabel, unitValue } from "./formatters";

function svgPointerX(event, fallbackWidth) {
  const svg = event.currentTarget;
  const matrix = svg.getScreenCTM?.();
  if (matrix && svg.createSVGPoint) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(matrix.inverse()).x;
  }
  const rect = svg.getBoundingClientRect();
  return ((event.clientX - rect.left) / Math.max(rect.width, 1)) * fallbackWidth;
}

function clampChartX(value, pad, width) {
  return Math.max(pad.left, Math.min(value, width - pad.right));
}

function smoothLinePath(points) {
  if (points.length < 3) return points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    const previous = points[index - 1];
    const midX = (previous.x + point.x) / 2;
    const midY = (previous.y + point.y) / 2;
    return `${path} Q ${previous.x.toFixed(1)} ${previous.y.toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`;
  }, "") + ` T ${points[points.length - 1].x.toFixed(1)} ${points[points.length - 1].y.toFixed(1)}`;
}

export function StatLineChart({ rows = [], yKey, unit = "", digits = 1, color = "accent", height = 250 }) {
  const [hover, setHover] = useState(null);
  const points = rows
    .map((row, index) => ({ index, ts: row.ts, value: metricNumber(row, yKey) }))
    .filter((point) => point.value !== null);
  const width = 720;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  if (!points.length) return <div className="chart-empty">No data</div>;
  const min = Math.min(...points.map((point) => point.value));
  const max = Math.max(...points.map((point) => point.value));
  const span = Math.max(max - min, 1);
  const xMax = Math.max(rows.length - 1, 1);
  const x = (index) => pad.left + (index / xMax) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((max - value) / span) * (height - pad.top - pad.bottom);
  const path = points.map((point, index) => `${index ? "L" : "M"} ${x(point.index).toFixed(1)} ${y(point.value).toFixed(1)}`).join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  const active = hover || last;

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = points.reduce((best, point) => {
      const distance = Math.abs(x(point.index) - svgX);
      return !best || distance < best.distance ? { ...point, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box">
      <svg className={`line-chart ${color}`} viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{unitValue(max, unit, digits)}</text>
        <text x={8} y={height - pad.bottom}>{unitValue(min, unit, digits)}</text>
        <text x={pad.left} y={height - 10}>{timestampLabel(first.ts)}</text>
        <text x={width - pad.right - 48} y={height - 10}>{timestampLabel(last.ts)}</text>
        <path d={path} />
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active.index)} y1={pad.top} x2={hover?.cursorX ?? x(active.index)} y2={height - pad.bottom} />
            <circle cx={x(active.index)} cy={y(active.value)} r="5" />
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip pinned">
          <strong>{unitValue(active.value, unit, digits)}</strong>
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}

export function StatNormalizedMultiLineChart({ rows = [], series = [], height = 210 }) {
  const [hover, setHover] = useState(null);
  const width = 720;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  const prepared = series.map((item) => {
    const points = rows
      .map((row, index) => ({ index, ts: row.ts || row.day, value: metricNumber(row, item.key) }))
      .filter((point) => point.value !== null);
    const values = points.map((point) => point.value);
    const min = values.length ? Math.min(...values) : 0;
    const max = values.length ? Math.max(...values) : 1;
    const span = Math.max(max - min, 1);
    return { ...item, points, min, max, span };
  });
  const activeSeries = prepared.filter((item) => item.points.length);
  if (!activeSeries.length) return <div className="chart-empty">No data</div>;

  const xMax = Math.max(rows.length - 1, 1);
  const x = (index) => pad.left + (index / xMax) * (width - pad.left - pad.right);
  const y = (item, value) => pad.top + ((item.max - value) / item.span) * (height - pad.top - pad.bottom);
  const pathFor = (item) => item.points.map((point, index) => `${index ? "L" : "M"} ${x(point.index).toFixed(1)} ${y(item, point.value).toFixed(1)}`).join(" ");
  const fallback = activeSeries[0].points[activeSeries[0].points.length - 1];
  const active = hover || fallback;

  function valueAt(item, index) {
    return item.points.find((point) => point.index === index) || null;
  }

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = activeSeries[0].points.reduce((best, point) => {
      const distance = Math.abs(x(point.index) - svgX);
      return !best || distance < best.distance ? { ...point, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box climate-chart-box">
      <div className="chart-legend">
        {activeSeries.map((item) => (
          <span className={`legend-item ${item.color}`} key={item.key}>{item.label}</span>
        ))}
      </div>
      <svg className="line-chart climate" viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>high</text>
        <text x={8} y={height - pad.bottom}>low</text>
        {activeSeries.map((item) => <path className={item.color} d={pathFor(item)} key={item.key} />)}
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active.index)} y1={pad.top} x2={hover?.cursorX ?? x(active.index)} y2={height - pad.bottom} />
            {activeSeries.map((item) => {
              const point = valueAt(item, active.index);
              return point ? <circle className={item.color} cx={x(active.index)} cy={y(item, point.value)} r="4.5" key={item.key} /> : null;
            })}
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip climate-tooltip pinned">
          {activeSeries.map((item) => {
            const point = valueAt(item, active.index);
            return <span className={`tooltip-line ${item.color}`} key={item.key}>{item.label}: {point ? unitValue(point.value, item.unit, item.digits) : "-"}</span>;
          })}
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}

export function StatBarChart({ rows = [], valueKey, unit = "", digits = 1, color = "accent" }) {
  const [hover, setHover] = useState(null);
  const values = rows
    .slice()
    .reverse()
    .map((row) => ({ ...row, value: metricNumber(row, valueKey) }))
    .filter((row) => row.value !== null);
  const width = 720;
  const height = 250;
  const pad = { top: 18, right: 18, bottom: 34, left: 44 };
  if (!values.length) return <div className="chart-empty">No data</div>;
  const max = Math.max(...values.map((row) => row.value), 1);
  const slot = (width - pad.left - pad.right) / values.length;
  const barWidth = Math.max(8, Math.min(34, slot * 0.62));
  const barCenter = (index) => pad.left + index * slot + slot / 2;

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = values.reduce((best, row, index) => {
      const distance = Math.abs(barCenter(index) - svgX);
      return !best || distance < best.distance ? { ...row, index, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box">
      <svg className={`bar-chart ${color}`} viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{unitValue(max, unit, digits)}</text>
        {values.map((row, index) => {
          const barHeight = (row.value / max) * (height - pad.top - pad.bottom);
          const x = pad.left + index * slot + (slot - barWidth) / 2;
          const y = height - pad.bottom - barHeight;
          const isActive = hover?.index === index;
          return (
            <g key={`${row.day || index}-${valueKey}`}>
              <rect className={isActive ? "active" : ""} x={x.toFixed(1)} y={y.toFixed(1)} width={barWidth.toFixed(1)} height={barHeight.toFixed(1)} rx="3" />
              {index % Math.ceil(values.length / 7 || 1) === 0 && <text x={(x - 4).toFixed(1)} y={height - 10}>{dayLabel(row.day)}</text>}
            </g>
          );
        })}
        {hover && <line className="hover-line" x1={hover.cursorX} y1={pad.top} x2={hover.cursorX} y2={height - pad.bottom} />}
        {values.map((row, index) => (
          <rect
            className="bar-hitbox"
            key={`${row.day || index}-${valueKey}-hitbox`}
            x={(pad.left + index * slot).toFixed(1)}
            y={pad.top}
            width={slot.toFixed(1)}
            height={height - pad.top - pad.bottom}
          />
        ))}
      </svg>
      {hover && (
        <div className="chart-tooltip pinned">
          <strong>{unitValue(hover.value, unit, digits)}</strong>
          <span>{dayLabel(hover.day)}</span>
        </div>
      )}
    </div>
  );
}

export function TimeLineChart({ rows = [], valueKey, unit = "", digits = 1, color = "blue", height = 250, yMin = null, yMax = null, smooth = false }) {
  const [hover, setHover] = useState(null);
  const values = rows
    .map((row) => ({ ...row, value: metricNumber(row, valueKey), time: new Date(row.ts).getTime() }))
    .filter((row) => row.value !== null && Number.isFinite(row.time));
  const width = 720;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  if (!values.length) return <div className="chart-empty">No data</div>;

  const minTime = Math.min(...values.map((row) => row.time));
  const maxTime = Math.max(...values.map((row) => row.time));
  const maxValue = yMax === null ? Math.max(...values.map((row) => row.value), 1) : yMax;
  const minValue = yMin === null ? Math.min(...values.map((row) => row.value), 0) : yMin;
  const spanValue = Math.max(maxValue - minValue, 1);
  const spanTime = Math.max(maxTime - minTime, 1);
  const x = (row) => pad.left + ((row.time - minTime) / spanTime) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((maxValue - value) / spanValue) * (height - pad.top - pad.bottom);
  const pathPoints = values.map((row) => ({ x: x(row), y: y(row.value) }));
  const path = smooth ? smoothLinePath(pathPoints) : pathPoints.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const active = hover || values[values.length - 1];

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = values.reduce((best, row) => {
      const distance = Math.abs(x(row) - svgX);
      return !best || distance < best.distance ? { ...row, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box">
      <svg className={`line-chart ${color}`} viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{unitValue(maxValue, unit, digits)}</text>
        <text x={8} y={height - pad.bottom}>{unitValue(minValue, unit, digits)}</text>
        <path d={path} />
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active)} y1={pad.top} x2={hover?.cursorX ?? x(active)} y2={height - pad.bottom} />
            <circle cx={x(active)} cy={y(active.value)} r="4.5" />
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip pinned">
          <strong>{unitValue(active.value, unit, digits)}</strong>
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}

export function ResourceUsageChart({ rows = [] }) {
  const [hover, setHover] = useState(null);
  const values = rows
    .map((row) => ({
      ...row,
      time: new Date(row.ts).getTime(),
      cpu_percent: metricNumber(row, "cpu_percent"),
      memory_percent: metricNumber(row, "memory_percent"),
    }))
    .filter((row) => Number.isFinite(row.time) && (row.cpu_percent !== null || row.memory_percent !== null));
  const width = 720;
  const height = 250;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  if (!values.length) return <div className="chart-empty">No resource history yet</div>;

  const minTime = Math.min(...values.map((row) => row.time));
  const maxTime = Math.max(...values.map((row) => row.time));
  const spanTime = Math.max(maxTime - minTime, 1);
  const x = (row) => pad.left + ((row.time - minTime) / spanTime) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((100 - Math.max(0, Math.min(value, 100))) / 100) * (height - pad.top - pad.bottom);
  const pathFor = (key) => values
    .filter((row) => row[key] !== null)
    .map((row, index) => `${index ? "L" : "M"} ${x(row).toFixed(1)} ${y(row[key]).toFixed(1)}`)
    .join(" ");
  const active = hover || values[values.length - 1];

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = values.reduce((best, row) => {
      const distance = Math.abs(x(row) - svgX);
      return !best || distance < best.distance ? { ...row, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box resource-chart-box">
      <div className="chart-legend">
        <span className="legend-item red">CPU</span>
        <span className="legend-item blue">RAM</span>
      </div>
      <svg className="line-chart resource" viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>100%</text>
        <text x={14} y={height - pad.bottom}>0%</text>
        <text x={pad.left} y={height - 10}>{timestampLabel(values[0].ts)}</text>
        <text x={width - pad.right - 48} y={height - 10}>{timestampLabel(values[values.length - 1].ts)}</text>
        <path className="red" d={pathFor("cpu_percent")} />
        <path className="blue" d={pathFor("memory_percent")} />
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active)} y1={pad.top} x2={hover?.cursorX ?? x(active)} y2={height - pad.bottom} />
            {active.cpu_percent !== null && <circle className="red" cx={x(active)} cy={y(active.cpu_percent)} r="4.5" />}
            {active.memory_percent !== null && <circle className="blue" cx={x(active)} cy={y(active.memory_percent)} r="4.5" />}
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip climate-tooltip pinned">
          <span className="tooltip-line red">CPU: {unitValue(active.cpu_percent, "%", 1)}</span>
          <span className="tooltip-line blue">RAM: {unitValue(active.memory_percent, "%", 1)}</span>
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}
