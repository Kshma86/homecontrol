import React from "react";
import { Activity } from "lucide-react";

export function Card({ title, value, meta, tone = "", icon: Icon = Activity, className = "" }) {
  const displayValue = value === 0 ? "0" : value || "-";
  return (
    <article className={`card ${tone} ${className}`.trim()}>
      <div className="card-title">
        <Icon size={16} aria-hidden="true" />
        <h2>{title}</h2>
      </div>
      <strong>{displayValue}</strong>
      <span>{meta || "-"}</span>
    </article>
  );
}

function tooltipTextFromChildren(children) {
  if (typeof children === "string" || typeof children === "number") return String(children).trim();
  if (Array.isArray(children)) return children.map(tooltipTextFromChildren).filter(Boolean).join(" ").trim();
  if (children && typeof children === "object" && "props" in children) return tooltipTextFromChildren(children.props.children);
  return "";
}

export function IconButton({ children, icon: Icon = Activity, title, "aria-label": ariaLabel, ...props }) {
  const tooltip = title || ariaLabel || tooltipTextFromChildren(children);
  return (
    <button {...props} title={tooltip || undefined} aria-label={ariaLabel || tooltip || undefined}>
      <Icon size={16} aria-hidden="true" />
      <span>{children}</span>
    </button>
  );
}

export function V2Page({ children, className = "" }) {
  return <section className={`v2-page ${className}`.trim()}>{children}</section>;
}

export function V2AutoPage({ enabled, sectionId, children }) {
  if (!enabled) return children;
  return <V2Page className={`v2-auto v2-auto-${sectionId}`}>{children}</V2Page>;
}

export function ensureButtonTooltip(button) {
  if (!button || button.title) return;
  const label = button.getAttribute("aria-label") || button.textContent || "";
  const tooltip = label.replace(/\s+/g, " ").trim();
  if (tooltip) button.title = tooltip;
}

export function V2Toolbar({ children, className = "" }) {
  return <section className={`stats-head v2-toolbar ${className}`.trim()}>{children}</section>;
}

export function V2KpiRow({ children, className = "" }) {
  return <section className={`v2-kpi-row ${className}`.trim()}>{children}</section>;
}

export function V2SectionGrid({ children, className = "" }) {
  return <section className={`v2-section-grid ${className}`.trim()}>{children}</section>;
}

export function Table({ rows = [], columns, className = "" }) {
  return (
    <div className={`table-wrap ${className}`.trim()}>
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column.key}>{column.label || column.key}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, index) => (
              <tr key={row.id ?? row.key ?? row.name ?? index}>
                {columns.map((column) => (
                  <td key={column.key}>{column.render ? column.render(row) : row[column.key] ?? "-"}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length}>No data</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export class RenderErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    console.error("HomeControl render error", error);
  }

  render() {
    if (this.state.error) {
      return (
        <section className="panel">
          <div className="panel-head">
            <h2>Render Error</h2>
            <span>Refresh or report this message</span>
          </div>
          <pre className="error-box">{this.state.error.message || String(this.state.error)}</pre>
        </section>
      );
    }
    return this.props.children;
  }
}
