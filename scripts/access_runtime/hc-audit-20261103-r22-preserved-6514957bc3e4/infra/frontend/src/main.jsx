import React, { lazy, Suspense, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, readJsonResponse, useContextRefresh } from "./apiClient";
import { skinOptions } from "./features/admin/adminOptions";
import {
  RenderErrorBoundary,
  V2AutoPage,
  ensureButtonTooltip,
} from "./uiPrimitives";
import {
  Activity,
  Archive,
  BarChart3,
  Bell,
  Bot,
  BookOpen,
  Bug,
  CalendarDays,
  ClipboardList,
  Cpu,
  Database,
  Droplets,
  Home,
  Info,
  Menu,
  Leaf,
  Map,
  Settings,
  SlidersHorizontal,
  Smartphone,
  Wind,
  Zap,
} from "lucide-react";
import "./styles.css";
import { loadLeaflet } from "./leafletLoader";

function lazyWithBuildRecovery(name, importer) {
  const recoveryKey = `hc-lazy-reload-${name}`;
  return lazy(() => importer()
    .then((module) => {
      window.sessionStorage.removeItem(recoveryKey);
      return module;
    })
    .catch((error) => {
      const message = String(error?.message || error);
      const chunkFailure = /dynamically imported module|failed to fetch|loading chunk|importing a module script/i.test(message);
      if (chunkFailure && window.sessionStorage.getItem(recoveryKey) !== "1") {
        window.sessionStorage.setItem(recoveryKey, "1");
        window.location.reload();
        return new Promise(() => {});
      }
      throw error;
    }));
}

const HcAdmin = lazyWithBuildRecovery("admin", () => import("./features/admin/HcAdmin"));
const Parameters = lazyWithBuildRecovery("parameters", () => import("./features/parameters/Parameters"));
const AiChat = lazyWithBuildRecovery("ai", () => import("./features/ai/AiChat"));
const Notes = lazyWithBuildRecovery("notes", () => import("./features/notes/Notes"));
const DebugLogs = lazyWithBuildRecovery("debug", () => import("./features/debug/DebugLogs"));
const UserDashboard = lazyWithBuildRecovery("home", () => import("./features/home/HomeDashboard").then((module) => ({ default: module.UserDashboard })));
const MobileDashboard = lazyWithBuildRecovery("mobile", () => import("./features/home/HomeDashboard").then((module) => ({ default: module.MobileDashboard })));
const TabletDashboard = lazyWithBuildRecovery("tablet", () => import("./features/home/HomeDashboard").then((module) => ({ default: module.TabletDashboard })));
const NyestriasztoScheduler = lazyWithBuildRecovery("nyest", () => import("./features/home/HomeDashboard").then((module) => ({ default: module.NyestriasztoScheduler })));
const DocumentationPage = lazyWithBuildRecovery("docs", () => import("./features/system/DocumentationPage"));
const AboutHomeControl = lazyWithBuildRecovery("about", () => import("./features/system/AboutHomeControl"));
const Performance = lazyWithBuildRecovery("performance", () => import("./features/performance/Performance"));
const HcStatistics = lazyWithBuildRecovery("hc-stat", () => import("./features/statistics/HcStatistics"));
const PageUsageStatistics = lazyWithBuildRecovery("usage-stat", () => import("./features/statistics/PageUsageStatistics"));
const Backup = lazyWithBuildRecovery("backup", () => import("./features/backup/Backup"));
const SchedulerHub = lazyWithBuildRecovery("scheduler", () => import("./features/scheduler/SchedulerHub"));
const SolarDashboard = lazyWithBuildRecovery("solar", () => import("./features/solar/SolarDashboard"));
const PowerWall = lazyWithBuildRecovery("power-wall", () => import("./features/powerWall/PowerWall"));
const TuyaPlayground = lazyWithBuildRecovery("tuya", () => import("./features/tuya/TuyaPlayground"));
const XiaomiX10 = lazyWithBuildRecovery("x10", () => import("./features/x10/XiaomiX10"));
const ClimateControl = lazyWithBuildRecovery("climate", () => import("./features/climate/ClimateControl"));
const MowerV3 = lazyWithBuildRecovery("mower-v3", () => import("./features/mower/MowerV3"));
const MowerLegacy = lazyWithBuildRecovery("mower-legacy", () => import("./features/mower/MowerLegacy"));
const RtkEditor = lazyWithBuildRecovery("rtk-editor", () => Promise.all([import("./features/mower/RtkEditor"), loadLeaflet()]).then(([module]) => module));
const Irrigation = lazyWithBuildRecovery("irrigation", () => import("./features/irrigation/Irrigation"));
const IrrigationStatistics = lazyWithBuildRecovery("irrigation-stat", () => import("./features/irrigation/IrrigationStatistics"));
const PilotHistory = lazyWithBuildRecovery("pilot-history", () => import("./features/irrigation/PilotDashboard").then((module) => ({ default: module.PilotHistory })));
const SqlLab = lazyWithBuildRecovery("sql-lab", () => import("./features/sqlLab/SqlLab"));

const MOBILE_DASHBOARD_MEDIA = "(max-width: 860px), (orientation: landscape) and (max-height: 560px) and (max-width: 940px)";
const TABLET_DASHBOARD_MEDIA = "(min-width: 861px) and (max-width: 1180px)";
const HOME_DASHBOARD_TABS = new Set(["home", "mobile-dashboard", "tablet-dashboard"]);
const navItems = [
  { id: "home", label: "Home", icon: Home, tone: "var(--tone-blue)", homeViewport: "desktop" },
  { id: "mobile-dashboard", label: "Mobile", icon: Smartphone, tone: "var(--tone-cyan)", homeViewport: "mobile" },
  { id: "tablet-dashboard", label: "Tablet", icon: Smartphone, tone: "var(--tone-sky)", homeViewport: "tablet" },
  { id: "irrigation", label: "Irrigation", icon: Droplets, tone: "var(--tone-green)" },
  { id: "solar", label: "Solar", icon: Zap, tone: "var(--tone-yellow)" },
  { id: "x10", label: "X10 Robot", icon: Home, tone: "var(--tone-orange)" },
  { id: "climate", label: "Climate", icon: Wind, tone: "var(--tone-sky)" },
  { id: "mower", label: "Mower", icon: Leaf, tone: "var(--tone-green)" },
  { id: "mower-legacy", label: "Mower Legacy", icon: Archive, tone: "var(--tone-amber)" },
  { id: "rtk-editor", label: "RTK Editor", icon: Map, tone: "var(--tone-cyan)" },
  { id: "power-wall", label: "Power Wall", icon: Zap, tone: "var(--tone-amber)" },
  { id: "nyest-scheduler", label: "Marten Deterrent", icon: Bell, tone: "var(--tone-red)" },
  { id: "ai", label: "AI", icon: Bot, tone: "var(--tone-teal)" },
  { id: "sql-lab", label: "SQL LAB", icon: Database, tone: "var(--tone-indigo)" },
  { id: "scheduler", label: "Scheduler", icon: CalendarDays, tone: "var(--tone-purple)" },
  { id: "statistics", label: "Irrigation Stats", icon: BarChart3, tone: "var(--tone-green)" },
  { id: "hc-stat", label: "House stats", icon: Activity, tone: "var(--tone-indigo)" },
  { id: "usage-statistics", label: "Usage Stats", icon: BarChart3, tone: "var(--tone-cyan)" },
  { id: "performance", label: "Performance", icon: Cpu, tone: "var(--tone-rose)" },
  { id: "backup", label: "Backup", icon: Archive, tone: "var(--tone-cyan)" },
  { id: "hc-admin", label: "HC Admin", icon: Settings, tone: "var(--tone-violet)" },
  { id: "parameters", label: "Parameters", icon: SlidersHorizontal, tone: "var(--tone-purple)" },
  { id: "notes", label: "Notes", icon: ClipboardList, tone: "var(--tone-lime)" },
  { id: "debug", label: "DEBUG", icon: Bug, tone: "var(--tone-rose)" },
  { id: "documentation", label: "Docs", icon: BookOpen, tone: "var(--tone-teal)" },
  { id: "about", label: "About", icon: Info, tone: "var(--tone-blue)" },
];

function dashboardTabForViewport() {
  if (typeof window === "undefined") return "home";
  if (window.matchMedia?.(MOBILE_DASHBOARD_MEDIA).matches) return "mobile-dashboard";
  if (window.matchMedia?.(TABLET_DASHBOARD_MEDIA).matches) return "tablet-dashboard";
  return "home";
}

function defaultTabForViewport() {
  if (typeof window === "undefined") return "home";
  const hash = window.location.hash.replace("#", "");
  const viewportHomeTab = dashboardTabForViewport();
  if (HOME_DASHBOARD_TABS.has(hash) && hash !== viewportHomeTab) return viewportHomeTab;
  if (hash) return hash;
  return viewportHomeTab;
}

function pageUsageClientId() {
  const storageKey = "hc-usage-client-id";
  let clientId = window.localStorage.getItem(storageKey);
  if (!clientId) {
    clientId = window.crypto?.randomUUID?.() || `hc-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem(storageKey, clientId);
  }
  return clientId;
}

function usageDeviceClass() {
  if (window.matchMedia?.(MOBILE_DASHBOARD_MEDIA).matches) return "mobile";
  if (window.matchMedia?.(TABLET_DASHBOARD_MEDIA).matches) return "tablet";
  return "desktop";
}

function useBootstrap() {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const snapshotRef = useRef(null);
  const bootstrapRetryRef = useRef(null);
  const irrigationRefreshInFlight = useRef(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const nextSnapshot = await api("/api/admin/bootstrap");
      setSnapshot(nextSnapshot);
      if (bootstrapRetryRef.current) {
        window.clearTimeout(bootstrapRetryRef.current);
        bootstrapRetryRef.current = null;
      }
    } catch (err) {
      setError(err.message);
      if (!snapshotRef.current && !bootstrapRetryRef.current) {
        bootstrapRetryRef.current = window.setTimeout(() => {
          bootstrapRetryRef.current = null;
          load();
        }, 2000);
      }
    } finally {
      setLoading(false);
    }
  }

  async function refreshIrrigation() {
    if (!snapshotRef.current || irrigationRefreshInFlight.current) return;
    irrigationRefreshInFlight.current = true;
    try {
      const irrigation = await api("/api/context/irrigation");
      setSnapshot((current) => current ? { ...current, irrigation } : current);
      setError("");
    } catch (err) {
      if (!snapshotRef.current) setError(err.message);
    } finally {
      irrigationRefreshInFlight.current = false;
    }
  }

  useEffect(() => {
    load();
    return () => {
      if (bootstrapRetryRef.current) window.clearTimeout(bootstrapRetryRef.current);
    };
  }, []);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  return { snapshot, error, loading, load, refreshIrrigation, setSnapshot };
}

function App() {
  const [deployment, setDeployment] = useState(null);
  useEffect(() => {
    let active = true;
    api('/api/deployment/status').then((data) => { if (active) setDeployment(data); }).catch(() => {});
    return () => { active = false; };
  }, []);
  const { snapshot, error, loading, load, refreshIrrigation, setSnapshot } = useBootstrap();
  const [activeTab, setActiveTab] = useState(defaultTabForViewport);
  const [viewportHomeTab, setViewportHomeTab] = useState(dashboardTabForViewport);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [aiTopbarStatus, setAiTopbarStatus] = useState({ ok: false, detail: "checking" });
  const [toast, setToast] = useState("");
  const [theme] = useState(() => {
    const saved = window.localStorage.getItem("hc-theme");
    if (saved === "light" || saved === "dark") return saved;
    return "dark";
  });
  const [skin, setSkin] = useState(() => {
    const saved = window.localStorage.getItem("hc-skin");
    return skinOptions.some((option) => option.value === saved) ? saved : "premium";
  });

  useEffect(() => {
    if (!toast) return undefined;
    const id = window.setTimeout(() => setToast(""), 2800);
    return () => window.clearTimeout(id);
  }, [toast]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("hc-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.skin = skin;
    window.localStorage.setItem("hc-skin", skin);
  }, [skin]);

  useEffect(() => {
    const applyTooltips = () => document.querySelectorAll("button").forEach(ensureButtonTooltip);
    const handlePointer = (event) => {
      const button = event.target?.closest?.("button");
      ensureButtonTooltip(button);
    };
    applyTooltips();
    document.addEventListener("mouseover", handlePointer);
    document.addEventListener("focusin", handlePointer);
    const observer = new MutationObserver(applyTooltips);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      document.removeEventListener("mouseover", handlePointer);
      document.removeEventListener("focusin", handlePointer);
      observer.disconnect();
    };
  }, []);

  const navIds = new Set(navItems.map((item) => item.id));
  const visibleNavItems = navItems.filter((item) => !item.homeViewport || item.id === viewportHomeTab);
  const activeUiVersion = "v2-preview";
  const activeNavItem = navItems.find((item) => item.id === activeTab);
  const activeNavLabel = activeNavItem?.label || "HomeControl";
  const activeNavTone = activeNavItem?.tone || "var(--tone-blue)";

  useEffect(() => {
    if (!navIds.has(activeTab)) return;
    const payload = {
      page_id: activeTab,
      client_id: pageUsageClientId(),
      device_class: usageDeviceClass(),
      viewport_width: window.innerWidth,
      viewport_height: window.innerHeight,
      standalone: Boolean(window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone),
      user_agent: window.navigator.userAgent,
    };
    api("/api/page-usage/event", { method: "POST", body: JSON.stringify(payload), skipContextRefresh: true }).catch(() => {});
  }, [activeTab]);

  useEffect(() => {
    const syncHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (!hash || !navIds.has(hash)) return;
      const nextHomeTab = dashboardTabForViewport();
      if (HOME_DASHBOARD_TABS.has(hash) && hash !== nextHomeTab) {
        setActiveTab(nextHomeTab);
        return;
      }
      setActiveTab(hash);
    };
    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    const mobileQuery = window.matchMedia?.(MOBILE_DASHBOARD_MEDIA);
    const tabletQuery = window.matchMedia?.(TABLET_DASHBOARD_MEDIA);
    if (!mobileQuery || !tabletQuery) return undefined;

    const syncDashboardViewport = () => {
      const nextHomeTab = dashboardTabForViewport();
      setViewportHomeTab(nextHomeTab);
      setActiveTab((current) => {
        if (HOME_DASHBOARD_TABS.has(current) && current !== nextHomeTab) {
          window.location.hash = nextHomeTab;
          return nextHomeTab;
        }
        return current;
      });
    };

    syncDashboardViewport();
    mobileQuery.addEventListener("change", syncDashboardViewport);
    tabletQuery.addEventListener("change", syncDashboardViewport);
    return () => {
      mobileQuery.removeEventListener("change", syncDashboardViewport);
      tabletQuery.removeEventListener("change", syncDashboardViewport);
    };
  }, []);

  useEffect(() => {
    if (!["home", "irrigation"].includes(activeTab)) return undefined;
    refreshIrrigation();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refreshIrrigation();
    }, 10000);
    return () => window.clearInterval(id);
  }, [activeTab]);

  useEffect(() => {
    let cancelled = false;
    async function loadAiTopbarStatus() {
      try {
        const response = await fetch("/api/ai/status", { headers: { "Content-Type": "application/json" } });
        const data = await readJsonResponse(response);
        if (!cancelled) {
          const ready = Boolean(data.ready);
          const detail = ready
            ? data.detail || `${data.provider || "AI"} ${data.model || ""}`.trim()
            : data.detail || data.error || "AI server unavailable";
          setAiTopbarStatus({ ok: ready, detail });
        }
      } catch (err) {
        if (!cancelled) setAiTopbarStatus({ ok: false, detail: err.message });
      }
    }
    loadAiTopbarStatus();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") loadAiTopbarStatus();
    }, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const statusItems = [
    ["HC Online", Boolean(snapshot) && !error],
    ["MQTT", Boolean(snapshot?.irrigation?.live)],
    ["PostgreSQL", Boolean(snapshot?.devices)],
    ["AI Server", aiTopbarStatus.ok],
    ["Zigbee", snapshot?.devices?.some((device) => device.platform === "zigbee")],
    ["Tuya", snapshot?.devices?.some((device) => device.platform === "tuya")],
  ];

  if (loading && !snapshot) {
    return (
      <main className="loading">
        <Activity size={22} />
        <span>Loading data...</span>
      </main>
    );
  }

  return (
    <div className="app-shell" data-section={activeTab} data-ui-version={activeUiVersion}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark"><Home size={20} aria-hidden="true" /></div>
          <div>
            <h1>HomeControl</h1>
            <p>Smart home OS</p>
          </div>
          <button
            className="mobile-menu-toggle"
            type="button"
            aria-expanded={mobileMenuOpen}
            aria-controls="primary-nav"
            onClick={() => setMobileMenuOpen((open) => !open)}
          >
            <Menu size={17} aria-hidden="true" />
            <span>Menu</span>
          </button>
        </div>
        <div className="sidebar-health">
          <span>DB online</span>
          <span>{snapshot ? `${snapshot.devices.length} device | ${snapshot.entities.length} entity` : "connecting"}</span>
        </div>
        <nav className={mobileMenuOpen ? "side-nav open" : "side-nav"} id="primary-nav" aria-label="Admin tabs">
          {visibleNavItems.map(({ id, label, icon: Icon, tone }) => (
            <button
              className={activeTab === id ? "side-nav-btn active" : "side-nav-btn"}
              style={{ "--tone": tone }}
              type="button"
              onClick={() => {
                setActiveTab(id);
                window.location.hash = id;
                setMobileMenuOpen(false);
              }}
              key={id}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <div className={`app-content section-${activeTab}`} data-section={activeTab} data-ui-version={activeUiVersion} style={{ "--section-tone": activeNavTone }}>
        <header className="topbar">
          <div>
            <h1>{activeNavLabel}</h1>
            <p>{error || (snapshot ? `${snapshot.devices.length} device | ${snapshot.entities.length} entity` : "Connecting...")}</p>
          </div>
          <div className="top-actions">
            <div className="status-strip" aria-label="System status">
              {statusItems.map(([label, ok]) => (
                <span className={ok ? "online" : "offline"} title={label === "AI Server" ? aiTopbarStatus.detail : ""} key={label}><i />{label}</span>
              ))}
            </div>
          </div>
        </header>

        <main>
        {deployment?.restricted && <section className="panel" role="status"><strong>Korlátozott kiadás</strong><p>{deployment.message}</p></section>}
        <Suspense fallback={<section className="loading"><Activity size={22} /><span>Loading view...</span></section>}>
          {snapshot && activeTab === "home" && (
            <RenderErrorBoundary>
              <UserDashboard snapshot={snapshot} reload={load} setToast={setToast} variant="v2" />
            </RenderErrorBoundary>
          )}
          {snapshot && activeTab === "mobile-dashboard" && (
            <RenderErrorBoundary>
              <MobileDashboard snapshot={snapshot} reload={load} setToast={setToast} />
            </RenderErrorBoundary>
          )}
          {snapshot && activeTab === "tablet-dashboard" && (
            <RenderErrorBoundary>
              <TabletDashboard snapshot={snapshot} reload={load} setToast={setToast} activeTab={activeTab} setActiveTab={setActiveTab} menuItems={visibleNavItems} />
            </RenderErrorBoundary>
          )}
          {snapshot && activeTab === "irrigation" && (
            <V2AutoPage enabled sectionId="irrigation">
              <Irrigation snapshot={snapshot} reload={load} setToast={setToast} />
            </V2AutoPage>
          )}
          {activeTab === "solar" && (
            <V2AutoPage enabled sectionId="solar">
              <SolarDashboard />
            </V2AutoPage>
          )}
          {activeTab === "statistics" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="statistics">
                <IrrigationStatistics />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "power-wall" && (
            <RenderErrorBoundary>
              <PowerWall variant="v2" />
            </RenderErrorBoundary>
          )}
          {activeTab === "nyest-scheduler" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="nyest-scheduler">
                <NyestriasztoScheduler setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "ai" && deployment?.ai_enabled !== false && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="ai">
                <AiChat setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "tuya" && (
            <V2AutoPage enabled sectionId="tuya">
              <TuyaPlayground />
            </V2AutoPage>
          )}
          {activeTab === "sql-lab" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="sql-lab">
                <SqlLab setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "x10" && (
            <V2AutoPage enabled sectionId="x10">
              <XiaomiX10 setToast={setToast} />
            </V2AutoPage>
          )}
          {activeTab === "climate" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="climate">
                <ClimateControl setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "mower" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="mower">
                <MowerV3 />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "mower-legacy" && (
            <RenderErrorBoundary>
              <MowerLegacy />
            </RenderErrorBoundary>
          )}
          {activeTab === "rtk-editor" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="rtk-editor">
                <RtkEditor setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {snapshot && activeTab === "scheduler" && (
            <V2AutoPage enabled sectionId="scheduler">
              <SchedulerHub setToast={setToast} />
            </V2AutoPage>
          )}
          {activeTab === "hc-stat" && (
            <V2AutoPage enabled sectionId="hc-stat">
              <HcStatistics />
            </V2AutoPage>
          )}
          {activeTab === "usage-statistics" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="usage-statistics">
                <PageUsageStatistics />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "performance" && (
            <V2AutoPage enabled sectionId="performance">
              <Performance />
            </V2AutoPage>
          )}
          {activeTab === "backup" && (
            <V2AutoPage enabled sectionId="backup">
              <Backup />
            </V2AutoPage>
          )}
          {snapshot && activeTab === "hc-admin" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="hc-admin">
                <HcAdmin
                  snapshot={snapshot}
                  reload={load}
                  setToast={setToast}
                  setSnapshot={setSnapshot}
                  skin={skin}
                  setSkin={setSkin}
                />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "parameters" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="parameters">
                <Parameters />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "notes" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="notes">
                <Notes setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "debug" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="debug">
                <DebugLogs setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "documentation" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="documentation">
                <DocumentationPage setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
          {activeTab === "about" && (
            <RenderErrorBoundary>
              <V2AutoPage enabled sectionId="about">
                <AboutHomeControl setToast={setToast} />
              </V2AutoPage>
            </RenderErrorBoundary>
          )}
        </Suspense>
        </main>
      </div>

      <div className={`toast ${toast ? "show" : ""}`}>{toast}</div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
