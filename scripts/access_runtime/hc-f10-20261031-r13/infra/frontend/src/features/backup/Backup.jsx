import { aiPowerStatus } from "../ai/aiPowerState.mjs";
import { backupProgress } from "./backupJobState.mjs";
import React, { useEffect, useRef, useState } from "react";
import { Activity, Archive, ChevronLeft, ChevronRight, Clock, Database, ExternalLink, GitBranch, HardDrive, Power, RefreshCw, Save, Settings } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { byteText, dateText } from "../../formatters";
import { diffGroupsFromIndexes, isVisibleDiff, nextDiffIndex } from "./backupDiffUtils";

export default function Backup() {
  const [contents, setContents] = useState(null);
  const [selectedBackup, setSelectedBackup] = useState("");
  const [selectedPaths, setSelectedPaths] = useState([]);
  const [restoreRecovery, setRestoreRecovery] = useState(null);
  const [restoreMode, setRestoreMode] = useState("staging");
  const [confirmText, setConfirmText] = useState("");
  const [compare, setCompare] = useState(null);
  const [comparePath, setComparePath] = useState("");
  const [activeDiffIndex, setActiveDiffIndex] = useState(null);
  const [toast, setLocalToast] = useState("");
  const [busy, setBusy] = useState("");
  const [backupRequest, setBackupRequest] = useState(null);
  const [giteaMessage, setGiteaMessage] = useState("Manual HomeControl configuration snapshot");
  const [giteaRestoreRef, setGiteaRestoreRef] = useState("main");
  const [giteaResult, setGiteaResult] = useState(null);
  const diffGridRef = useRef(null);
  const { data: state, setData: setState, loading, refresh: loadBackup } = usePolledContext("/api/context/backup", {
    intervalMs: 5000,
    onError: (err) => setLocalToast(err.message),
    mapPayload: (payload) => {
      if (payload.restore_recoveries?.length) setRestoreRecovery(payload.restore_recoveries[0]);
      if (!selectedBackup && payload.backups?.length) setSelectedBackup(payload.backups[0].name);
      return payload;
    },
  });

  async function loadContents(name = selectedBackup) {
    if (!name) return;
    setBusy("contents");
    try {
      const data = await api(`/api/backup/${encodeURIComponent(name)}/contents`);
      setContents(data);
      const restoreDefaults = new Set(["apps", "infra", "zigbee2mqtt/data", "homeassistant", "scripts"]);
      setSelectedPaths(data.components?.map((item) => item.name).filter((name) => restoreDefaults.has(name)) || []);
      setCompare(null);
      setComparePath("");
      setActiveDiffIndex(null);
      setLocalToast("");
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    if (selectedBackup) loadContents(selectedBackup);
  }, [selectedBackup]);

  useEffect(() => {
    if (!backupRequest?.pending) return;
    const progress = backupProgress(backupRequest, state?.activity?.jobs);
    if (progress.archive) setSelectedBackup(progress.archive);
    if (!progress.pending) setLocalToast(progress.message);
    if (progress.message !== backupRequest.message || progress.pending !== backupRequest.pending) {
      setBackupRequest((current) => ({ ...current, ...progress }));
    }
  }, [state, backupRequest]);

  async function saveSettings(event) {
    event.preventDefault();
    setBusy("settings");
    try {
      const data = await api("/api/backup/settings", {
        method: "PUT",
        body: JSON.stringify(state.settings),
      });
      setState((current) => ({ ...current, settings: data.settings, timer: data.timer, plan: data.plan || current?.plan }));
      setLocalToast(data.timer?.systemctl_ok ? "Backup settings and timer saved" : "Settings saved; systemd reload may be needed on host");
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function createBackup() {
    setBusy("create");
    try {
      const data = await api("/api/backup/create", { method: "POST", body: JSON.stringify({}) });
      setState((current) => ({ ...current, backups: data.backups }));
      setBackupRequest({ run_id: data.run_id, kind: "local", pending: true, requestedAt: Date.now(), message: data.message });
      setLocalToast(data.message || "Local backup queued");
      loadBackup();
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function runFullAiBackup() {
    setBusy("full-ai");
    setBackupRequest({ message: "Teljes AI mentés indításának kérése…", pending: true, kind: "weekly", requestedAt: Date.now() });
    try {
      const data = await api("/api/backup/full-ai", { method: "POST", body: JSON.stringify({}) });
      setLocalToast(data.message || "Full AI backup requested");
      setBackupRequest((current) => ({ ...current, run_id: data.run_id, message: data.message || "Full AI backup queued" }));
      loadBackup();
    } catch (err) {
      setLocalToast(err.message);
      setBackupRequest({ message: `Nem sikerült kérni a mentést: ${err.message}`, pending: false });
    } finally {
      setBusy("");
    }
  }

  async function runGiteaAction(action) {
    const body = action === "commit"
      ? { message: giteaMessage }
      : action === "restore"
        ? { ref: giteaRestoreRef }
        : {};
    if (action === "restore" && !window.confirm(`Restore Gitea ref "${giteaRestoreRef || "main"}" to staging? This will not overwrite live files.`)) return;
    setBusy(`gitea-${action}`);
    try {
      const data = await api(`/api/backup/gitea/${action}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setGiteaResult(data);
      if (data.run_id) setBackupRequest({ run_id: data.run_id, kind: "git", pending: true, requestedAt: Date.now(), message: data.message });
      setLocalToast(data.message || `Gitea ${action} finished`);
      loadBackup();
    } catch (err) {
      setGiteaResult({ ok: false, error: err.message });
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function restoreSelected() {
    setBusy("restore");
    try {
      const result = await api("/api/backup/restore", {
        method: "POST",
        body: JSON.stringify({
          backup: selectedBackup,
          paths: selectedPaths,
          mode: restoreMode,
          confirm: confirmText,
        }),
      });
      setLocalToast(`Restored ${result.restored.length} file(s) to ${result.target}`);
      setConfirmText("");
      setRestoreRecovery(null);
    } catch (err) {
      setRestoreRecovery(err.payload?.recovery_required ? err.payload : null);
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function rollbackRestore() {
    if (!restoreRecovery || confirmText !== "ROLLBACK") return;
    setBusy("restore");
    try {
      await api("/api/backup/restore/recover", { method: "POST", body: JSON.stringify({ run_id: restoreRecovery.run_id, confirm: confirmText }) });
      setRestoreRecovery(null);
      setConfirmText("");
      setLocalToast("Restore changes rolled back");
    } catch (err) { setLocalToast(err.message); }
    finally { setBusy(""); }
  }

  async function compareFile(path) {
    if (!selectedBackup || !path) return;
    setBusy("compare");
    setComparePath(path);
    try {
      const data = await api(`/api/backup/${encodeURIComponent(selectedBackup)}/compare?path=${encodeURIComponent(path)}`);
      setCompare(data);
      const firstDiff = data.rows?.findIndex((row) => isVisibleDiff(row)) ?? -1;
      setActiveDiffIndex(firstDiff >= 0 ? firstDiff : null);
      const visibleDiffs = data.rows?.filter((row) => isVisibleDiff(row)).length || 0;
      setLocalToast(data.same || visibleDiffs === 0 ? "Current and backup file are identical" : `${visibleDiffs} visible diff row(s)`);
    } catch (err) {
      setCompare(null);
      setActiveDiffIndex(null);
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateSetting(key, value) {
    setState((current) => ({
      ...current,
      settings: (() => {
        const next = { ...(current?.settings || {}), [key]: value };
        if (["ai_backup_host", "ai_backup_user", "ai_backup_mount"].includes(key)) {
          const user = next.ai_backup_user || "a";
          const host = next.ai_backup_host || "192.168.1.2";
          const mount = next.ai_backup_mount || "/mnt/hc-backup";
          next.restic_repository = `sftp:${user}@${host}:${mount}/restic/homecontrol`;
        }
        return next;
      })(),
    }));
  }

  function togglePath(path, checked) {
    setSelectedPaths((current) => checked ? [...new Set([...current, path])] : current.filter((item) => item !== path));
  }

  function jumpDiff(direction) {
    const nextIndex = nextDiffIndex(diffGroups, activeDiffIndex, direction);
    if (nextIndex !== null) setActiveDiffIndex(nextIndex);
  }

  useEffect(() => {
    if (activeDiffIndex === null || !diffGridRef.current) return;
    const target = diffGridRef.current.querySelector(`[data-diff-index="${activeDiffIndex}"]`);
    if (target) {
      diffGridRef.current.scrollTo({
        top: Math.max(0, target.offsetTop - 44),
        behavior: "smooth",
      });
    }
  }, [activeDiffIndex]);

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading backups...</span>
      </section>
    );
  }

  const backups = state?.backups || [];
  const settings = state?.settings || {};
  const restricted = state?.deployment?.restricted === true;
  const effectiveSettings = state?.effective_settings || settings;
  const timer = state?.timer || settings.timer_source || {};
  const plan = state?.plan || {};
  const activity = state?.activity || {};
  const aiShutdownGuard = state?.ai_shutdown_guard || {};
  const aiBackupRunning = Boolean(aiShutdownGuard.backup_running);
  const aiShutdownDeferred = Boolean(aiShutdownGuard.deferred_shutdown);
  const aiPower = aiPowerStatus(aiShutdownGuard);
  const backupStateDetail = aiShutdownGuard.state?.detail || (aiBackupRunning ? "full AI backup lock is active" : "");
  const runnerRunning = activity.runner_lock === true;
  const activeBackupUi = runnerRunning || aiBackupRunning || backupRequest?.pending || ["create", "full-ai", "gitea-commit", "gitea-status", "gitea-restore"].includes(busy);
  const activeBackupTitle = runnerRunning || aiBackupRunning
    ? "Backup Running"
    : busy === "create"
      ? "Requesting Local Backup"
      : busy === "full-ai" || backupRequest?.pending
        ? "Backup Queued"
        : busy?.startsWith("gitea-")
          ? "Gitea Operation Running"
          : "Backup Activity";
  const activeBackupMeta = runnerRunning || aiBackupRunning
    ? activity.run?.mode === "weekly" ? backupStateDetail : "Backup in progress; see target results below"
    : busy === "create"
      ? "submitting the backup request"
      : busy === "full-ai" || backupRequest?.pending
        ? "waiting for the backup to start"
        : busy === "gitea-commit"
          ? "snapshot commit and push in progress"
          : busy === "gitea-status"
            ? "checking current snapshot against Gitea"
            : busy === "gitea-restore"
              ? "cloning selected ref to staging"
              : "";
  const latest = backups[0];
  const settingChecks = [
    ["include_postgres", "PostgreSQL dump"],
    ["include_apps", "Apps"],
    ["include_infra", "Infra config"],
    ["include_zigbee2mqtt", "Zigbee2MQTT data"],
    ["include_homeassistant", "Home Assistant"],
    ["include_scripts", "Scripts"],
    ["include_docker_meta", "Docker meta"],
  ];
  const resticChecks = [
    ["include_docker_volumes", "Docker volumes"],
    ["include_media", "Media files"],
    ["include_gitea", "Local Gitea data"],
  ];
  const comparableFiles = (contents?.files || []).filter((item) => item.type === "file" && item.size_bytes <= 300000);
  const diffIndexes = compare?.rows?.map((row, index) => isVisibleDiff(row) ? index : null).filter((index) => index !== null) || [];
  const diffGroups = diffGroupsFromIndexes(diffIndexes);
  const activeDiffGroup = activeDiffIndex === null ? null : diffGroups.find((group) => activeDiffIndex >= group.start && activeDiffIndex <= group.end);
  const activeDiffPosition = activeDiffGroup ? diffGroups.indexOf(activeDiffGroup) : -1;
  const resticRetention = plan.restic?.retention || {};

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Backup</h2>
          <span>{toast || `${backups.length} archive | root ${state?.backup_root || "-"}`}</span>
        </div>
        <div className="button-row compact">
          <IconButton icon={RefreshCw} onClick={loadBackup} disabled={loading}>Refresh</IconButton>
          <IconButton icon={Archive} onClick={createBackup} disabled={busy === "create" || backupRequest?.pending}>{busy === "create" ? "Creating" : "Create Backup"}</IconButton>
          <IconButton icon={HardDrive} onClick={runFullAiBackup} disabled={restricted || busy === "full-ai" || backupRequest?.pending || aiBackupRunning}>{busy === "full-ai" || (backupRequest?.pending && backupRequest.kind === "weekly") ? "Requesting" : aiBackupRunning ? "Full Backup Running" : "Run Full AI Backup"}</IconButton>
        </div>
      </section>

      {backupRequest && (
        <section className="panel backup-activity" aria-live="polite">
          <div className="panel-head"><h2>Teljes AI mentés állapota</h2></div>
          <p>{backupRequest.message}</p>
          <p>{aiBackupRunning ? "A mentés fut." : aiShutdownGuard.state?.state === "failed" ? "A legutóbbi mentés hibával leállt." : aiShutdownGuard.state?.state === "idle" ? "A legutóbbi mentés sikeresen befejeződött." : "Várakozás az állapotra."} {dateText(aiShutdownGuard.state?.updated_at)}</p>
          <p>{backupStateDetail}</p>
        </section>
      )}

      {restricted && <section className="panel" role="status"><p>{state.deployment.message}</p><p>A távoli mentési beállítások megmaradnak, de ebben a kiadásban nem lépnek életbe.</p></section>}

      {activeBackupUi && (
        <section className="backup-running-banner" aria-live="polite">
          <div className="backup-running-pulse" aria-hidden="true" />
          <div>
            <strong>{activeBackupTitle}</strong>
            <span>{activeBackupMeta}</span>
          </div>
          <div className="backup-running-steps">
            <span>Gitea</span>
            <span>GitHub</span>
            <span>Restic</span>
            <span>AI HDD</span>
          </div>
        </section>
      )}

      <section className="tile-grid stats-tiles">
        <Card title="Latest Backup" value={latest ? dateText(latest.timestamp) : "-"} meta={latest ? latest.name : "no archive"} icon={Archive} />
        <Card title="Backup Size" value={latest ? byteText(latest.size_bytes) : "-"} meta="latest archive" icon={HardDrive} />
        <Card title="Schedule" value={settings.schedule_enabled ? (timer.schedule_time || settings.schedule_time || "-") : "Disabled"} meta={timer.source_enabled ? "systemd timer source enabled" : "systemd timer source disabled"} tone={settings.schedule_enabled && !timer.source_enabled ? "warn" : ""} icon={Clock} />
        <Card title="Timer State" value={timer.active || (timer.systemctl_ok ? "Unknown" : "Host helper")} meta={timer.systemctl_ok ? `next ${timer.next_elapse || "-"}` : "source changes are applied by systemd path helper"} tone={timer.systemctl_ok ? "" : "warn"} icon={Settings} />
        <Card title="Restic Retention" value={`${resticRetention.daily || "-"}d / ${resticRetention.weekly || "-"}w / ${resticRetention.monthly || "-"}m`} meta={plan.restic?.repository || settings.restic_repository || "AI HDD repo"} icon={Database} />
        <Card title="Restore Mode" value={restoreMode === "staging" ? "Staging" : "In-place"} meta={restoreMode === "staging" ? state?.staging_root : "requires RESTORE"} tone={restoreMode === "in_place" ? "warn" : ""} icon={RefreshCw} />
        <Card title="AI Shutdown Guard" value={aiPower.label} meta={!aiPower.known ? "guard unavailable; shutdown blocked" : aiShutdownDeferred ? "AI PC will shut down after backup" : "shutdown is protected during backup"} tone={aiPower.warn ? "warn" : ""} icon={Power} />
      </section>

      <section className="backup-plan-grid">
        <article className="panel backup-plan-card">
          <div className="plan-card-head">
            <GitBranch size={18} />
            <div>
              <h2>Gitea / Git</h2>
              <span>{effectiveSettings.git_enabled ? "version tracking enabled" : "version tracking disabled"}</span>
            </div>
          </div>
          <div className="plan-meta">
            <span>{settings.gitea_url || "-"}</span>
            <strong>{settings.git_repository || "-"}{settings.git_offsite_enabled ? ` | offsite ${settings.git_offsite_branch || "main"}` : ""}</strong>
          </div>
          <div className="pill-list">
            {(plan.git?.paths || settings.git_paths || []).map((path) => <span key={path}>{path}</span>)}
          </div>
        </article>

        <article className="panel backup-plan-card">
          <div className="plan-card-head">
            <Database size={18} />
            <div>
              <h2>Restic / AI HDD</h2>
              <span>{effectiveSettings.restic_enabled ? "snapshot backup enabled" : "snapshot backup disabled"}</span>
            </div>
          </div>
          <div className="plan-meta">
            <span>{settings.ai_backup_user || "-"}@{settings.ai_backup_host || "-"}:{settings.ai_backup_mount || "-"}</span>
            <strong>daily best-effort, weekly required | keep {settings.restic_keep_daily || "-"}d/{settings.restic_keep_weekly || "-"}w/{settings.restic_keep_monthly || "-"}m</strong>
          </div>
          <div className="pill-list">
            {(plan.restic?.covers || []).map((item) => <span key={item}>{item}</span>)}
          </div>
        </article>

        <article className="panel backup-plan-card">
          <div className="plan-card-head">
            <Archive size={18} />
            <div>
              <h2>HC Archive</h2>
              <span>manual and scheduled tar.gz fallback</span>
            </div>
          </div>
          <div className="plan-meta">
            <span>{state?.backup_root || "-"}</span>
            <strong>{settings.retention_days || "-"} day local retention</strong>
          </div>
          <div className="pill-list">
            {(plan.local_archive?.covers || []).map((item) => <span key={item}>{item}</span>)}
          </div>
        </article>
      </section>

      <section className="panel backup-activity">
        <div className="panel-head">
          <h2>Backup Activity</h2>
          <span>{activity.log_file || "backup.log"}</span>
        </div>
        <div className="backup-check-grid">
          <div className="status-chip">
            <span>Archive</span>
            <strong>{activity.latest_backup || "no completed archive yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Restic</span>
            <strong>{activity.latest_restic_backup || "no restic snapshot yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Restic check</span>
            <strong>{activity.latest_restic_check || "no repository check yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Gitea</span>
            <strong>{activity.latest_gitea_sync || "no config sync yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Gitea dump</span>
            <strong>{activity.latest_gitea_dump || "no Gitea dump yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Offsite Git</span>
            <strong>{activity.targets?.git_offsite?.last_success || "no confirmed offsite push yet"}</strong>
          </div>
          <div className={`status-chip ${activity.latest_error ? "warn" : ""}`}>
            <span>Last error</span>
            <strong>{activity.latest_error || "none in recent log"}</strong>
          </div>
        </div>
        <div className="backup-check-grid">
          {Object.entries(activity.targets || {}).map(([name, target]) => (
            <div key={name} className={`status-chip ${target.last_attempt?.state === "failed" ? "warn" : ""}`}>
              <span>{name.replaceAll("_", " ")}</span>
              <strong>{target.last_attempt?.state || "unknown"}</strong>
              <small>Last success: {target.last_success ? dateText(target.last_success) : "none"}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="panel backup-activity">
        <div className="panel-head">
          <h2>Gitea Control</h2>
          <span>{settings.gitea_url || "Gitea web"} | {settings.git_repository || "repository"}</span>
        </div>
        <div className="backup-check-grid">
          <div className="status-chip">
            <span>Repository</span>
            <strong>{settings.git_repository || "-"}</strong>
          </div>
          <div className="status-chip">
            <span>Remote</span>
            <strong>git@{settings.ai_backup_host || "192.168.1.2"}:2222</strong>
          </div>
          <div className="status-chip">
            <span>Last sync</span>
            <strong>{activity.latest_gitea_sync || "no config sync yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Web UI</span>
            <strong>{settings.gitea_url || "-"}</strong>
          </div>
          <div className={`status-chip ${settings.git_offsite_enabled ? "" : "warn"}`}>
            <span>Offsite Git</span>
            <strong>{settings.git_offsite_enabled ? (settings.git_offsite_remote || "enabled, no remote") : "disabled"}</strong>
          </div>
        </div>
        <div className="form-grid backup-settings-grid">
          <label className="wide">Commit message
            <input value={giteaMessage} onChange={(event) => setGiteaMessage(event.target.value)} />
          </label>
          <label>Restore ref
            <input value={giteaRestoreRef} onChange={(event) => setGiteaRestoreRef(event.target.value)} />
          </label>
          <div className="wide actions">
            <IconButton icon={RefreshCw} type="button" className="secondary" disabled={restricted || busy === "gitea-status"} onClick={() => runGiteaAction("status")}>{busy === "gitea-status" ? "Checking" : "Status / Diff"}</IconButton>
            <IconButton icon={GitBranch} type="button" disabled={restricted || busy === "gitea-commit"} onClick={() => runGiteaAction("commit")}>{busy === "gitea-commit" ? "Pushing" : "Commit & Push"}</IconButton>
            <IconButton icon={RefreshCw} type="button" className="secondary" disabled={restricted || busy === "gitea-restore"} onClick={() => runGiteaAction("restore")}>{busy === "gitea-restore" ? "Restoring" : "Restore to Staging"}</IconButton>
            {!restricted && settings.gitea_url && <a className="ai-node-link" href={`${settings.gitea_url}/${settings.git_repository || ""}`} target="_blank" rel="noreferrer"><ExternalLink size={14} aria-hidden="true" /> Open Gitea</a>}
          </div>
        </div>
        {giteaResult && (
          <pre className="json-box">{[giteaResult.message || giteaResult.error || "", giteaResult.stdout, giteaResult.stderr].filter(Boolean).join("\n\n")}</pre>
        )}
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Backup Archives</h2>
            <span>Select and inspect an archive</span>
          </div>
          <div className="backup-picker">
            <label>Archive
              <select value={selectedBackup} onChange={(event) => setSelectedBackup(event.target.value)}>
                {backups.map((backup) => <option value={backup.name} key={backup.name}>{backup.name}{backup.completed ? "" : " (legacy, unverified)"}</option>)}
              </select>
            </label>
            <IconButton icon={Archive} onClick={() => loadContents()} disabled={!selectedBackup || busy === "contents"}>{busy === "contents" ? "Opening" : "Open"}</IconButton>
          </div>
          <Table
            rows={backups}
            columns={[
              { key: "name", label: "Archive" },
              { key: "verification", label: "Verification" },
              { key: "size_bytes", label: "Size", render: (row) => byteText(row.size_bytes) },
              { key: "timestamp", label: "Created", render: (row) => dateText(row.timestamp) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Backup Settings</h2>
            <span>Git tracks config, restic protects full system state</span>
          </div>
          <form onSubmit={saveSettings}>
            <h3>Local archive</h3>
            <div className="backup-check-grid">
              {settingChecks.map(([key, label]) => (
                <label className="check" key={key}>
                  <input type="checkbox" checked={Boolean(settings[key])} onChange={(event) => updateSetting(key, event.target.checked)} />
                  {label}
                </label>
              ))}
            </div>
            <div className="form-grid backup-settings-grid">
              <label>Retention days
                <input type="number" min="1" max="365" value={settings.retention_days || 14} onChange={(event) => updateSetting("retention_days", Number(event.target.value))} />
              </label>
              <label>Schedule time
                <input type="time" value={settings.schedule_time || "02:15"} onChange={(event) => updateSetting("schedule_time", event.target.value)} />
              </label>
              <label className="check wide">
                <input type="checkbox" checked={Boolean(settings.schedule_enabled)} onChange={(event) => updateSetting("schedule_enabled", event.target.checked)} />
                Schedule enabled
              </label>
            </div>
            <h3>Gitea / Git</h3>
            <fieldset disabled={restricted} style={{ border: 0, padding: 0, minWidth: 0 }}>
            <div className="form-grid backup-settings-grid">
              <label className="check wide">
                <input type="checkbox" checked={Boolean(settings.git_enabled)} onChange={(event) => updateSetting("git_enabled", event.target.checked)} />
                Git version tracking enabled
              </label>
              <label>Gitea URL
                <input value={settings.gitea_url || ""} onChange={(event) => updateSetting("gitea_url", event.target.value)} />
              </label>
              <label>Repository
                <input value={settings.git_repository || ""} onChange={(event) => updateSetting("git_repository", event.target.value)} />
              </label>
              <label className="check wide">
                <input type="checkbox" checked={Boolean(settings.git_offsite_enabled)} onChange={(event) => updateSetting("git_offsite_enabled", event.target.checked)} />
                Offsite Git mirror enabled
              </label>
              <label className="wide">Offsite remote
                <input placeholder="https://github.com/user/homecontrol.git" value={settings.git_offsite_remote || ""} onChange={(event) => updateSetting("git_offsite_remote", event.target.value)} />
              </label>
              <label>Offsite branch
                <input value={settings.git_offsite_branch || "main"} onChange={(event) => updateSetting("git_offsite_branch", event.target.value)} />
              </label>
              <label className="wide">Offsite token file
                <input value={settings.git_offsite_token_file || ""} onChange={(event) => updateSetting("git_offsite_token_file", event.target.value)} />
              </label>
              <label className="wide">Offsite SSH key
                <input value={settings.git_offsite_ssh_key || ""} onChange={(event) => updateSetting("git_offsite_ssh_key", event.target.value)} />
              </label>
            </div>
            <h3>AI backup HDD</h3>
            <div className="form-grid backup-settings-grid">
              <label>Host
                <input value={settings.ai_backup_host || ""} onChange={(event) => updateSetting("ai_backup_host", event.target.value)} />
              </label>
              <label>User
                <input value={settings.ai_backup_user || ""} onChange={(event) => updateSetting("ai_backup_user", event.target.value)} />
              </label>
              <label className="wide">Mount path
                <input value={settings.ai_backup_mount || ""} onChange={(event) => updateSetting("ai_backup_mount", event.target.value)} />
              </label>
              <label className="wide">SSH key
                <input value={settings.ai_backup_ssh_key || ""} onChange={(event) => updateSetting("ai_backup_ssh_key", event.target.value)} />
              </label>
            </div>
            <h3>Restic / AI HDD</h3>
            <div className="backup-check-grid">
              <label className="check">
                <input type="checkbox" checked={Boolean(settings.restic_enabled)} onChange={(event) => updateSetting("restic_enabled", event.target.checked)} />
                Restic enabled
              </label>
              <label className="check">
                <input type="checkbox" checked={Boolean(settings.ai_weekly_backup_enabled)} onChange={(event) => updateSetting("ai_weekly_backup_enabled", event.target.checked)} />
                Weekly AI backup
              </label>
              {resticChecks.map(([key, label]) => (
                <label className="check" key={key}>
                  <input type="checkbox" checked={Boolean(settings[key])} onChange={(event) => updateSetting(key, event.target.checked)} />
                  {label}
                </label>
              ))}
            </div>
            <div className="form-grid backup-settings-grid">
              <label className="wide">Restic repository
                <input value={settings.restic_repository || ""} onChange={(event) => updateSetting("restic_repository", event.target.value)} />
              </label>
              <label className="wide">Password file
                <input value={settings.restic_password_file || ""} onChange={(event) => updateSetting("restic_password_file", event.target.value)} />
              </label>
              <label>Keep daily
                <input type="number" min="1" max="365" value={settings.restic_keep_daily || 14} onChange={(event) => updateSetting("restic_keep_daily", Number(event.target.value))} />
              </label>
              <label>Keep weekly
                <input type="number" min="1" max="365" value={settings.restic_keep_weekly || 8} onChange={(event) => updateSetting("restic_keep_weekly", Number(event.target.value))} />
              </label>
              <label>Keep monthly
                <input type="number" min="1" max="365" value={settings.restic_keep_monthly || 6} onChange={(event) => updateSetting("restic_keep_monthly", Number(event.target.value))} />
              </label>
              <label>Weekly schedule
                <input value={settings.ai_weekly_backup_schedule || "Sun 03:30"} onChange={(event) => updateSetting("ai_weekly_backup_schedule", event.target.value)} />
              </label>
              <label className="check">
                <input type="checkbox" checked={Boolean(settings.ai_weekly_shutdown_after)} onChange={(event) => updateSetting("ai_weekly_shutdown_after", event.target.checked)} />
                Shutdown if backup woke AI
              </label>
            </div>
            </fieldset>
            <div className="wide actions"><IconButton icon={Save} type="submit" disabled={busy === "settings"}>{busy === "settings" ? "Saving" : "Save Settings"}</IconButton></div>
          </form>
          <div className="timer-source">
            <strong>Systemd source</strong>
            <span>{timer.timer_file || "-"}</span>
            <span>{timer.on_calendar ? `OnCalendar=${timer.on_calendar}` : "OnCalendar is disabled"}</span>
            <span>Helper: homecontrol-backup-apply.path watches this file on the host</span>
          </div>
        </article>
      </section>

      <details className="backup-advanced">
        <summary>
          <span>Restore and file compare</span>
          <b>{selectedBackup || "no archive selected"}</b>
        </summary>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Archive Contents</h2>
            <span>{contents?.components?.length || 0} component | {selectedBackup || "-"}</span>
          </div>
          <div className="restore-components">
            {(contents?.components || []).map((component) => (
              <label className="restore-component" key={component.name}>
                <input type="checkbox" checked={selectedPaths.includes(component.name)} onChange={(event) => togglePath(component.name, event.target.checked)} />
                <span>{component.name}</span>
                <b>{byteText(component.size_bytes)}</b>
              </label>
            ))}
          </div>
          <div className="table-spacer" />
          <Table
            rows={contents?.files || []}
            columns={[
              { key: "path", label: "Path" },
              { key: "type", label: "Type" },
              { key: "size_bytes", label: "Size", render: (row) => row.type === "dir" ? "-" : byteText(row.size_bytes) },
              {
                key: "compare",
                label: "Compare",
                render: (row) => row.type === "file" && row.size_bytes <= 300000 ? (
                  <button className="mini-action" type="button" onClick={() => compareFile(row.path)} disabled={busy === "compare"}>
                    Compare
                  </button>
                ) : "-",
              },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Restore</h2>
            <span>{selectedPaths.length} selected component/path</span>
          </div>
          <div className="restore-box">
            <label>Mode
              <select value={restoreMode} onChange={(event) => setRestoreMode(event.target.value)}>
                <option value="staging">staging preview</option>
                <option value="in_place" disabled={restricted}>restore in-place</option>
              </select>
            </label>
            {(restoreMode === "in_place" || restoreRecovery) && (
              <label>Confirmation
                <input value={confirmText} onChange={(event) => setConfirmText(event.target.value)} placeholder="RESTORE" />
              </label>
            )}
            <div className={restoreMode === "in_place" ? "restore-warning active" : "restore-warning"}>
              {restoreMode === "in_place"
                ? "In-place restore overwrites matching files in the live HomeControl folders. PostgreSQL dumps are not restored in-place in this version."
                : `Staging restore extracts selected files under ${state?.staging_root || "-"}.`}
            </div>
            {restoreRecovery && <div role="alert">
              Partial restore: {restoreRecovery.restored.length} applied, {restoreRecovery.remaining.length} remaining.
              Recovery ID: {restoreRecovery.run_id}. Enter ROLLBACK above to restore the saved preimages.
              <button onClick={rollbackRestore} disabled={restricted || busy === "restore" || confirmText !== "ROLLBACK"}>Roll back restore</button>
            </div>}
            {restricted && <p>Ebben a kiadásban csak staging visszaállítás használható; az éles fájlok visszaírása le van tiltva.</p>}
            <IconButton icon={RefreshCw} onClick={restoreSelected} disabled={(restricted && restoreMode !== "staging") || !selectedBackup || !selectedPaths.length || busy === "restore"}>
              {busy === "restore" ? "Restoring" : "Restore Selected"}
            </IconButton>
          </div>
        </article>
      </section>

      <section className="panel diff-panel">
        <div className="panel-head">
          <h2>File Compare</h2>
          <span>{compare ? `${compare.path} | ${diffGroups.length} diff block(s)` : "Select a file from Archive Contents"}</span>
        </div>
        <div className="backup-picker">
          <label>File
            <select value={comparePath} onChange={(event) => setComparePath(event.target.value)}>
              <option value="">Select file</option>
              {comparableFiles.map((item) => <option value={item.path} key={item.path}>{item.path}</option>)}
            </select>
          </label>
          <IconButton icon={Activity} onClick={() => compareFile(comparePath)} disabled={!comparePath || busy === "compare"}>
            {busy === "compare" ? "Comparing" : "Compare"}
          </IconButton>
        </div>
        {compare ? (
          <>
            <div className="diff-meta">
              <span>Current: {compare.current_exists ? `${compare.current_path} | ${byteText(compare.current_size_bytes)}` : "missing"}</span>
              <span>Backup: {byteText(compare.backup_size_bytes)}</span>
              <span>{diffGroups.length ? `${activeDiffPosition + 1}/${diffGroups.length} diff block` : "no differences"}</span>
              {compare.truncated && <span>Diff display truncated</span>}
              <div className="diff-nav">
                <IconButton icon={ChevronLeft} onClick={() => jumpDiff(-1)} disabled={!diffGroups.length}>Prev</IconButton>
                <IconButton icon={ChevronRight} onClick={() => jumpDiff(1)} disabled={!diffGroups.length}>Next</IconButton>
              </div>
            </div>
            <div className="diff-grid" ref={diffGridRef}>
              <div className="diff-head">Current</div>
              <div className="diff-head">Backup</div>
              {compare.rows.map((row, index) => (
                <React.Fragment key={`${row.current_line || "x"}-${row.backup_line || "x"}-${index}`}>
                  <pre data-diff-index={index} className={`diff-cell left ${row.type} ${activeDiffGroup && index >= activeDiffGroup.start && index <= activeDiffGroup.end ? "active-diff" : ""}`}><span>{row.current_line || ""}</span>{row.current || " "}</pre>
                  <pre className={`diff-cell right ${row.type} ${activeDiffGroup && index >= activeDiffGroup.start && index <= activeDiffGroup.end ? "active-diff" : ""}`}><span>{row.backup_line || ""}</span>{row.backup || " "}</pre>
                </React.Fragment>
              ))}
            </div>
          </>
        ) : (
          <div className="chart-empty diff-empty">No file selected</div>
        )}
      </section>
      </details>
    </>
  );
}
