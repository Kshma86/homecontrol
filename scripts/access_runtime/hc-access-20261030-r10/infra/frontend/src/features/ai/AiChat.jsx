import { aiPowerStatus } from "./aiPowerState.mjs";
import { validateImageFiles, storedAiMessages } from "./aiImages.mjs";
import { useEffect, useRef, useState } from "react";
import { Bot, Database, ExternalLink, Play, Power, RefreshCw, Save, Server, Settings, Square, Trash2 } from "lucide-react";
import { IconButton } from "../../uiPrimitives";
import {
  AI_CHAT_CONTEXT_WINDOW,
  AI_CHAT_STORAGE_KEY,
  AI_POWER_OFF_DELAY_STORAGE_KEY,
  aiFriendlyError,
  defaultAiMessages,
  loadStoredAiMessages,
} from "./aiChatState";
import {
  fetchAiConfig,
  fetchAiModels,
  fetchAiNodeStatus,
  fetchAiPullStatus,
  fetchAiStatus,
  pullAiModel,
  restartAiGatewayRequest,
  runAiNodeCommandRequest,
  saveAiConfigPayload,
  sendAiChatMessage,
  wakeAiNodeRequest,
} from "./aiApi";

export default function AiChat({ setToast }) {
  const [status, setStatus] = useState({ ok: false, ready: false, provider: "-", model: "-", error: "", detail: "" });
  const [config, setConfig] = useState({
    provider: "ollama",
    model: "qwen3:1.7b",
    ollama_url: "http://ollama:11434",
    openai_base_url: "https://api.openai.com/v1",
    openai_api_key: "",
    openai_api_key_set: false,
    temperature: 0.2,
    num_ctx: 16384,
    num_predict: 1536,
    system_prompt: "",
  });
  const [recommendedModels, setRecommendedModels] = useState([]);
  const [localModels, setLocalModels] = useState([]);
  const [pull, setPull] = useState({ running: false, model: "", status: "idle", completed: 0, total: 0, error: "" });
  const [selectedModel, setSelectedModel] = useState("qwen3:1.7b");
  const [messages, setMessages] = useState(() => loadStoredAiMessages());
  const [attachments, setAttachments] = useState([]);
  const [attachmentError, setAttachmentError] = useState("");
  const [readingImages, setReadingImages] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [configBusy, setConfigBusy] = useState("");
  const [node, setNode] = useState({ configured: false, node: {}, ssh: {}, ollama: { models: [] } });
  const [nodeBusy, setNodeBusy] = useState("");
  const [gatewayBusy, setGatewayBusy] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [powerOffDelayMin, setPowerOffDelayMin] = useState(() => {
    const saved = Number(window.localStorage.getItem(AI_POWER_OFF_DELAY_STORAGE_KEY));
    return Number.isFinite(saved) && saved >= 0 ? saved : 5;
  });
  const [nowMs, setNowMs] = useState(() => Date.now());
  const messageListRef = useRef(null);
  const typingTimersRef = useRef([]);
  const refreshTimersRef = useRef([]);

  useEffect(() => {
    loadAiAdmin();
  }, []);

  useEffect(() => {
    let modelRefreshTick = 0;
    const id = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      loadAiStatus();
      loadAiNode();
      modelRefreshTick += 1;
      if (modelRefreshTick % 4 === 0) loadAiModels();
    }, 30000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(AI_POWER_OFF_DELAY_STORAGE_KEY, String(powerOffDelayMin));
  }, [powerOffDelayMin]);


  useEffect(() => {
    const stored = storedAiMessages(messages, AI_CHAT_CONTEXT_WINDOW);
    window.localStorage.setItem(AI_CHAT_STORAGE_KEY, JSON.stringify(stored));
    messageListRef.current?.scrollTo({ top: messageListRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => {
    typingTimersRef.current.forEach((id) => window.clearInterval(id));
    typingTimersRef.current = [];
    refreshTimersRef.current.forEach((id) => window.clearTimeout(id));
    refreshTimersRef.current = [];
  }, []);

  useEffect(() => {
    if (!pull.running) return undefined;
    const id = window.setInterval(loadPullStatus, 1500);
    return () => window.clearInterval(id);
  }, [pull.running]);

  async function loadAiStatus() {
    try {
      const data = await fetchAiStatus();
      setStatus({
        ok: Boolean(data.gateway_ok || data.ok),
        ready: Boolean(data.ready ?? data.ok),
        provider: data.provider || "-",
        model: data.model || "-",
        error: "",
        detail: data.ready || data.ok ? data.detail || "" : "AI server unavailable",
      });
    } catch {
      setStatus({ ok: false, ready: false, provider: "-", model: "-", error: "", detail: "AI gateway unavailable" });
    }
  }

  async function loadAiAdmin() {
    await Promise.all([loadAiStatus(), loadAiConfig(), loadAiModels(), loadPullStatus(), loadAiNode()]);
  }

  async function loadAiNode() {
    try {
      const data = await fetchAiNodeStatus();
      setNode({ ...data, error: "" });
    } catch {
      setNode((current) => ({ ...current, ok: false, error: "AI node status unavailable" }));
    }
  }

  async function loadAiConfig() {
    try {
      const data = await fetchAiConfig();
      if (data.config) {
        setConfig(data.config);
        setSelectedModel(data.config.model || "qwen3:8b");
      }
      setRecommendedModels(data.recommended_models || []);
    } catch (err) {
      setToast(err.message);
    }
  }

  async function loadAiModels() {
    try {
      const data = await fetchAiModels();
      setLocalModels(data.local_models || []);
      if (data.recommended_models?.length) setRecommendedModels(data.recommended_models);
      if (data.error) setStatus((current) => ({ ...current, detail: current.ready ? current.detail : "AI server unavailable" }));
    } catch {
      setStatus((current) => ({ ...current, detail: current.ready ? current.detail : "AI models unavailable" }));
    }
  }

  async function loadPullStatus() {
    try {
      const data = await fetchAiPullStatus();
      setPull(data.pull || { running: false, status: "idle" });
    } catch {
      // Pull status is best-effort; the main status panel shows connectivity errors.
    }
  }

  function scheduleAiRefresh(delays = [1500, 5000, 12000]) {
    delays.forEach((delay) => {
      const id = window.setTimeout(() => {
        loadAiStatus();
        loadAiNode();
        loadAiModels();
        refreshTimersRef.current = refreshTimersRef.current.filter((item) => item !== id);
      }, delay);
      refreshTimersRef.current.push(id);
    });
  }

  function updateConfig(key, value) {
    setConfig((current) => ({ ...current, [key]: value }));
    if (key === "model") setSelectedModel(value);
  }

  async function saveAiConfig(nextConfig = config) {
    setConfigBusy("save");
    try {
      const data = await saveAiConfigPayload(nextConfig);
      setConfig(data.config || nextConfig);
      setStatus((current) => ({ ...current, provider: data.config?.provider || nextConfig.provider, model: data.config?.model || nextConfig.model, error: "" }));
      setToast("AI config saved");
    } catch (err) {
      setToast(err.message);
    } finally {
      setConfigBusy("");
    }
  }

  async function pullModel() {
    const model = selectedModel.trim();
    if (!model) return;
    setConfigBusy("pull");
    try {
      const data = await pullAiModel(model);
      setPull(data.pull || { running: true, model, status: "queued" });
      setToast(`Model download started: ${model}`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setConfigBusy("");
    }
  }

  async function useModel(model) {
    const nextConfig = { ...config, provider: config.provider === "remote_ollama" ? "remote_ollama" : "ollama", model };
    setConfig(nextConfig);
    setSelectedModel(model);
    await saveAiConfig(nextConfig);
  }

  async function wakeAiNode() {
    setNodeBusy("wake");
    try {
      await wakeAiNodeRequest();
      setToast("Wake packet sent");
      await loadAiNode();
      scheduleAiRefresh([2500, 7000, 15000, 30000]);
    } catch (err) {
      setToast(err.message);
    } finally {
      setNodeBusy("");
    }
  }

  async function runAiNodeCommand(action, message) {
    const delaySec = Math.max(0, Math.min(1440, Number(powerOffDelayMin) || 0)) * 60;
    const backupRunning = Boolean(node.backup_guard?.backup_running);
    const confirmText = backupRunning
      ? `A full AI backup is running. Queue shutdown after the backup finishes, then cut power after ${Math.round(delaySec / 60)} minutes?`
      : `Shut down the remote AI PC and cut its power plug after ${Math.round(delaySec / 60)} minutes?`;
    if (action === "shutdown" && !window.confirm(confirmText)) return;
    setNodeBusy(action);
    try {
      const data = await runAiNodeCommandRequest({ action, schedule_power_off_on_failure: action === "shutdown", power_off_delay_sec: delaySec, defer_if_backup_running: true });
      setToast(data.deferred ? "Shutdown queued after backup" : message);
      await loadAiNode();
      scheduleAiRefresh(action === "shutdown" ? [1500, 5000] : [1500, 5000, 12000]);
    } catch (err) {
      setToast(err.message);
    } finally {
      setNodeBusy("");
    }
  }

  async function restartAiGateway() {
    if (!window.confirm("Restart the HomeControl AI gateway and reload AI knowledge files?")) return;
    setGatewayBusy(true);
    try {
      const data = await restartAiGatewayRequest();
      setToast(data.ready === false ? "AI gateway restart requested" : "AI gateway restarted");
      scheduleAiRefresh([1000, 3000, 7000, 12000]);
    } catch (err) {
      setToast(err.message);
    } finally {
      setGatewayBusy(false);
    }
  }

  async function connectRemoteNode() {
    const ollamaUrl = node?.node?.ollama_url || "";
    if (!ollamaUrl) {
      setToast("Remote Ollama URL is not configured");
      return;
    }
    const model = node?.ollama?.models?.[0]?.name || localModels?.[0]?.name || (config.model === "remote-model-pending" ? "" : config.model) || "qwen3:8b";
    const nextConfig = { ...config, provider: "remote_ollama", ollama_url: ollamaUrl, model };
    setConfig(nextConfig);
    setSelectedModel(model);
    await saveAiConfig(nextConfig);
    scheduleAiRefresh();
  }

  function animateAssistantMessage(content, meta = "", error = false) {
    const fullContent = content || "Nincs válasz.";
    const id = `assistant-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setMessages((current) => [
      ...current,
      {
        id,
        role: "assistant",
        content: "",
        fullContent,
        typing: true,
        ts: new Date().toISOString(),
        meta,
        error,
      },
    ]);
    let index = 0;
    const step = Math.max(1, Math.ceil(fullContent.length / 180));
    const timer = window.setInterval(() => {
      index = Math.min(fullContent.length, index + step);
      setMessages((current) => current.map((message) => (
        message.id === id
          ? { ...message, content: fullContent.slice(0, index), typing: index < fullContent.length }
          : message
      )));
      if (index >= fullContent.length) {
        window.clearInterval(timer);
        typingTimersRef.current = typingTimersRef.current.filter((item) => item !== timer);
      }
    }, 18);
    typingTimersRef.current.push(timer);
  }

  function clearAiContextWindow() {
    typingTimersRef.current.forEach((id) => window.clearInterval(id));
    typingTimersRef.current = [];
    window.localStorage.removeItem(AI_CHAT_STORAGE_KEY);
    setMessages(defaultAiMessages());
    setDraft("");
    setAttachments([]);
    setAttachmentError("");
    setToast("AI context window cleared");
  }

  async function attachImages(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    setReadingImages(true);
    setAttachmentError("");
    try {
      validateImageFiles(files, attachments.length);
      const next = [];
      for (const file of files) {
        const url = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error("A képfájl nem olvasható."));
          reader.readAsDataURL(file);
        });
        next.push({ name: file.name, mime_type: file.type, data: url.split(",")[1], url });
      }
      setAttachments((current) => [...current, ...next]);
    } catch (err) {
      setAttachmentError(err.message);
    } finally {
      setReadingImages(false);
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    const text = draft.trim();
    if ((!text && !attachments.length) || busy || readingImages) return;

    const historyForApi = messages
      .filter((item) => !item.error && ["user", "assistant"].includes(item.role) && item.content)
      .map(({ role, content }) => ({ role, content }))
      .slice(-AI_CHAT_CONTEXT_WINDOW);
    const sentImages = attachments;
    const nextMessages = [...messages, { role: "user", content: text, images: sentImages, ts: new Date().toISOString() }];
    setMessages(nextMessages);
    setDraft("");
    setBusy(true);

    try {
      const data = await sendAiChatMessage(text, historyForApi, sentImages);
      setAttachments([]);
      setAttachmentError("");
      setStatus((current) => ({ ...current, ok: true, ready: true, provider: data.provider || status.provider, model: data.model || status.model, error: "", detail: "" }));
      animateAssistantMessage(data.reply || "Nincs válasz.", `${data.provider || "-"} | ${data.model || "-"} | ${data.elapsed_ms ?? "-"} ms`);
    } catch (err) {
      const message = aiFriendlyError(err.message);
      setStatus((current) => ({ ...current, ok: false, ready: false, error: "", detail: message }));
      animateAssistantMessage(message, "", true);
      setToast(message);
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage(event);
    }
  }

  const machineReachable = Boolean(node.ssh?.ok);
  const ollamaRunning = Boolean(node.ollama?.ok);
  const gatewayConnected = config.provider === "remote_ollama" && config.ollama_url === node.node?.ollama_url;
  const modelReady = Boolean(status.ready);
  const aiNodeUnavailable = node.configured && !machineReachable && !ollamaRunning;
  const aiGatewayUnavailable = !status.ready;
  const installedModelNames = new Set(localModels.map((model) => model.name));
  const pullPercent = pull.total > 0 ? Math.round((Number(pull.completed || 0) / Number(pull.total)) * 100) : null;
  const powerState = aiPowerStatus(node.backup_guard, nowMs);
  const powerOffRemainingSec = powerState.remainingSec;
  const powerOffCountdown = powerOffRemainingSec > 0
    ? `${Math.floor(powerOffRemainingSec / 60)}:${String(powerOffRemainingSec % 60).padStart(2, "0")}`
    : "";
  const backupGuard = node.backup_guard || {};
  const shutdownDeferred = Boolean(backupGuard.deferred_shutdown);
  const backupGuardText = powerState.label;

  return (
    <section className="ai-page">
      <section className="panel ai-infra-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Server size={17} aria-hidden="true" /> AI Infrastructure</h2>
          <div className="ai-infra-badges">
            <span className={machineReachable ? "ai-status online" : "ai-status offline"}>machine</span>
            <span className={ollamaRunning ? "ai-status online" : "ai-status offline"}>ollama</span>
            <span className={gatewayConnected ? "ai-status online" : "ai-status offline"}>gateway</span>
            <span className={modelReady ? "ai-status online" : "ai-status offline"}>model</span>
          </div>
        </div>
        <div className="ai-infra-grid">
          <div>
            <span>Remote PC</span>
            <strong>{node.node?.host || "not configured"}</strong>
            <small>{machineReachable ? "SSH reachable" : aiNodeUnavailable ? "AI server unavailable" : node.ssh?.detail || "-"}</small>
          </div>
          <div>
            <span>Ollama</span>
            <strong>{ollamaRunning ? `${node.ollama.models?.length || 0} model` : "stopped"}</strong>
            <small>{ollamaRunning ? node.node?.ollama_url : aiNodeUnavailable ? "remote service unavailable" : node.ollama?.detail || "-"}</small>
          </div>
          <div>
            <span>Gateway</span>
            <strong>{status.provider}</strong>
            <small>{status.ready ? `${status.model} | ready` : aiGatewayUnavailable ? "AI server unavailable" : status.detail || "not ready"}</small>
          </div>
          <div>
            <span>Power Plug</span>
            <strong>{node.node?.power_entity_id || "not configured"}</strong>
            <small>{powerOffCountdown ? `power off in ${powerOffCountdown}` : `off ${powerOffDelayMin} min after shutdown`}</small>
          </div>
          <div>
            <span>Backup Guard</span>
            <strong>{backupGuardText}</strong>
            <small>{shutdownDeferred ? "shutdown will run after backup" : "AI PC shutdown is deferred during backup"}</small>
          </div>
        </div>
        <div className="ai-power-off-control">
          <label>
            <span>Power-off delay</span>
            <input
              type="number"
              min="0"
              max="1440"
              step="1"
              value={powerOffDelayMin}
              onChange={(event) => setPowerOffDelayMin(Math.max(0, Math.min(1440, Number(event.target.value) || 0)))}
            />
          </label>
          <strong>{powerOffCountdown || "not scheduled"}</strong>
        </div>
        <div className="ai-node-actions">
          <IconButton icon={Power} title="Bekapcsolja a tavoli AI gepet es WOL csomagot kuld." disabled={Boolean(nodeBusy) || !node.node?.mac_set} onClick={wakeAiNode}>{nodeBusy === "wake" ? "Waking" : "Wake PC"}</IconButton>
          <IconButton icon={Play} title="Elinditja a tavoli AI stack szolgaltatasait." disabled={Boolean(nodeBusy) || !machineReachable} onClick={() => runAiNodeCommand("start_stack", "Remote AI stack started")}>Start AI</IconButton>
          <IconButton icon={RefreshCw} title="Ujrainditja a tavoli AI PC stackjet." className="secondary" disabled={Boolean(nodeBusy) || !machineReachable} onClick={() => runAiNodeCommand("restart_stack", "Remote AI stack restarted")}>Restart AI</IconButton>
          <IconButton icon={RefreshCw} title="Ujrainditja a HomeControl AI gatewayt es frissiti a tanitasi cache-t." className="secondary" disabled={gatewayBusy} onClick={restartAiGateway}>{gatewayBusy ? "Restarting Gateway" : "Restart Gateway"}</IconButton>
          <IconButton icon={Square} title="Leallitja a tavoli AI stack szolgaltatasait." className="secondary" disabled={Boolean(nodeBusy) || !machineReachable || !ollamaRunning} onClick={() => runAiNodeCommand("stop_stack", "Remote AI stack stopped")}>Stop AI</IconButton>
          <IconButton icon={Save} title="A gatewayt a tavoli Ollama vegpontra allitja." className="secondary" disabled={Boolean(configBusy) || !ollamaRunning || !node.node?.ollama_url} onClick={connectRemoteNode}>Connect</IconButton>
          <IconButton icon={RefreshCw} title="Frissiti az AI statuszt, modelleket es node adatokat." className="secondary" disabled={Boolean(nodeBusy)} onClick={loadAiAdmin}>Refresh</IconButton>
          <IconButton icon={Power} title="Backup kozben sorba allitja, egyebkent leallitja a tavoli AI PC-t es kesleltetett aramtalanitast ker." className="danger" disabled={Boolean(nodeBusy) || !node.node?.power_entity_id || !powerState.known} onClick={() => runAiNodeCommand("shutdown", "Remote AI PC shutdown requested; delayed power off scheduled")}>{backupGuard.backup_running ? "Shutdown After Backup" : "Shut Down PC"}</IconButton>
        </div>
        {node.error && <div className="ai-error">{node.error}</div>}
        {node.node?.openwebui_url && <a className="ai-node-link" href={node.node.openwebui_url} target="_blank" rel="noreferrer"><ExternalLink size={14} aria-hidden="true" /> Open WebUI</a>}
      </section>

      <section className="ai-chat-shell">
        <section className="panel ai-chat-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Bot size={17} aria-hidden="true" /> Chat</h2>
            <div className="ai-chat-head-actions">
              <span className={status.ready ? "ai-status online" : "ai-status offline"}>{status.ready ? "ready" : "not ready"}</span>
              <IconButton icon={Trash2} className="secondary" type="button" title="Clear local AI chat context" disabled={busy || readingImages} onClick={clearAiContextWindow}>Clear</IconButton>
            </div>
          </div>
          <div className="ai-message-list" aria-live="polite" ref={messageListRef}>
            {messages.map((message, index) => (
              <article className={`ai-message ${message.role} ${message.error ? "error" : ""} ${message.typing ? "typing" : ""}`.trim()} key={message.id || `${message.role}-${index}-${message.ts}`}>
                <div className="ai-message-role">{message.role === "user" ? "You" : "AI"}</div>
                <p>{message.content}{message.typing && <span className="ai-typing-caret" aria-hidden="true" />}</p>
                {message.images?.map((item, i) => <img key={i} src={item.url} alt={item.name} style={{ maxWidth: 160, maxHeight: 120, objectFit: "contain" }} />)}
                {message.meta && <small>{message.meta}</small>}
              </article>
            ))}
            {busy && (
              <article className="ai-message assistant">
                <div className="ai-message-role">AI</div>
                <p><span className="ai-thinking-dot" /> <span className="ai-thinking-dot" /> <span className="ai-thinking-dot" /></p>
              </article>
            )}
          </div>
          <form className="ai-chat-form" onSubmit={sendMessage}>
            <div className="ai-attachments">
              <label>Képek csatolása (JPG, PNG, WebP; max. 4 × 3 MiB)
                <input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={attachImages} disabled={busy || readingImages} />
              </label>
              <small>Képküldéshez Ollama vision modell szükséges. A képeket nem mentjük tartósan.</small>
              {attachments.map((item, index) => <div key={index}>
                <img src={item.url} alt={item.name} style={{ maxWidth: 160, maxHeight: 120, objectFit: "contain" }} />
                <button type="button" disabled={busy || readingImages} aria-label={`${item.name} eltávolítása`} onClick={() => setAttachments((current) => current.filter((_, i) => i !== index))}>Eltávolítás</button>
              </div>)}
              {attachmentError && <div role="alert" className="ai-error">{attachmentError}</div>}
            </div>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message AI..."
              rows="3"
            />
            <IconButton icon={Play} type="submit" disabled={busy || readingImages || (!draft.trim() && !attachments.length) || !status.ready}>{busy ? "Sending" : "Send"}</IconButton>
          </form>
        </section>

        <section className="panel ai-side-panel">
          <div className="ai-model-manager">
            <div className="panel-head">
              <h2>Models</h2>
              <span>{localModels.length} local</span>
            </div>
            <label>
              <span>Download model</span>
              <input value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} placeholder="qwen3:8b" list="ai-model-suggestions" />
              <datalist id="ai-model-suggestions">
                {recommendedModels.map((model) => <option value={model.name} key={model.name}>{model.label}</option>)}
              </datalist>
            </label>
            <IconButton icon={Database} disabled={Boolean(configBusy) || pull.running || !selectedModel.trim()} onClick={pullModel}>
              {pull.running ? "Downloading" : "Download"}
            </IconButton>
            <div className="ai-pull-status">
              <span>{pull.model || "no active download"}</span>
              <strong>{pull.status || "idle"}</strong>
              {pullPercent !== null && <small>{pullPercent}%</small>}
              {pull.error && <small className="bad">{pull.error}</small>}
            </div>
            <div className="ai-model-list">
              {recommendedModels.map((model) => (
                <button className={model.installed || installedModelNames.has(model.name) ? "installed" : ""} type="button" onClick={() => useModel(model.name)} key={model.name}>
                  <span>{model.name}</span>
                  <small>{model.size} | {model.installed || installedModelNames.has(model.name) ? "installed" : model.note}</small>
                </button>
              ))}
              {localModels.filter((model) => !recommendedModels.some((item) => item.name === model.name)).map((model) => (
                <button className="installed" type="button" onClick={() => useModel(model.name)} key={model.name}>
                  <span>{model.name}</span>
                  <small>local model</small>
                </button>
              ))}
            </div>
          </div>

          <div className="ai-advanced">
            <button className="secondary ai-advanced-toggle" type="button" onClick={() => setAdvancedOpen((open) => !open)}>
              <Settings size={16} aria-hidden="true" />
              <span>{advancedOpen ? "Hide Advanced" : "Advanced Config"}</span>
            </button>
            {advancedOpen && (
              <div className="ai-config-form">
                <label>
                  <span>Provider</span>
                  <select value={config.provider} onChange={(event) => updateConfig("provider", event.target.value)}>
                    <option value="fallback">Fallback</option>
                    <option value="ollama">Ollama</option>
                    <option value="local_ollama">Local Ollama</option>
                    <option value="remote_ollama">Remote Ollama</option>
                    <option value="openai_compatible">OpenAI compatible</option>
                  </select>
                </label>
                <label>
                  <span>Model</span>
                  <input value={config.model} onChange={(event) => updateConfig("model", event.target.value)} placeholder="qwen3:8b" />
                </label>
                <label>
                  <span>Ollama URL</span>
                  <input value={config.ollama_url || ""} onChange={(event) => updateConfig("ollama_url", event.target.value)} placeholder="http://192.168.1.2:11434" />
                </label>
                <label>
                  <span>Cloud Base URL</span>
                  <input value={config.openai_base_url || ""} onChange={(event) => updateConfig("openai_base_url", event.target.value)} placeholder="https://api.openai.com/v1" />
                </label>
                <label>
                  <span>Cloud API Key</span>
                  <input type="password" value={config.openai_api_key || ""} onChange={(event) => updateConfig("openai_api_key", event.target.value)} placeholder={config.openai_api_key_set ? "saved" : "not set"} />
                </label>
                <label>
                  <span>Temperature</span>
                  <input type="number" min="0" max="2" step="0.1" value={config.temperature} onChange={(event) => updateConfig("temperature", event.target.value)} />
                </label>
                <label>
                  <span>Context</span>
                  <input type="number" min="512" max="262144" step="512" value={config.num_ctx} onChange={(event) => updateConfig("num_ctx", event.target.value)} />
                </label>
                <label>
                  <span>Max Tokens</span>
                  <input type="number" min="16" max="4096" step="16" value={config.num_predict} onChange={(event) => updateConfig("num_predict", event.target.value)} />
                </label>
                <label className="wide">
                  <span>System Prompt</span>
                  <textarea value={config.system_prompt} onChange={(event) => updateConfig("system_prompt", event.target.value)} rows="4" />
                </label>
                <div className="ai-config-actions wide">
                  <IconButton icon={Save} disabled={Boolean(configBusy)} onClick={() => saveAiConfig()}>{configBusy === "save" ? "Saving" : "Save Config"}</IconButton>
                  <IconButton icon={RefreshCw} className="secondary" disabled={Boolean(configBusy)} onClick={loadAiAdmin}>Refresh Config</IconButton>
                </div>
              </div>
            )}
          </div>
        </section>
      </section>
    </section>
  );
}
