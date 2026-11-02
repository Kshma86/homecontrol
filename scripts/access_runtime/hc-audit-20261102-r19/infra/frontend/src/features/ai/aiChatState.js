export const AI_CHAT_STORAGE_KEY = "hc-ai-chat-session-v1";
export const AI_CHAT_CONTEXT_WINDOW = 20;
export const AI_POWER_OFF_DELAY_STORAGE_KEY = "hc-ai-power-off-delay-min";
export const AI_POWER_OFF_UNTIL_STORAGE_KEY = "hc-ai-power-off-until";

export const defaultAiMessages = () => [
  {
    role: "assistant",
    content: "Szia! Az AI szerver első alapverziója vagyok. Most még nincs HomeControl hatásköröm, csak beszélgetünk.",
    ts: new Date().toISOString(),
  },
];

export function loadStoredAiMessages() {
  try {
    const rows = JSON.parse(window.localStorage.getItem(AI_CHAT_STORAGE_KEY) || "[]");
    if (Array.isArray(rows) && rows.length) return rows.filter((item) => item?.role && item?.content).slice(-AI_CHAT_CONTEXT_WINDOW);
  } catch {
    // Ignore invalid stored chat state and start clean.
  }
  return defaultAiMessages();
}

export function aiFriendlyError(message) {
  const text = String(message || "");
  if (/ollama unavailable|no route to host|connection refused|timed out|ai provider error|urlopen/i.test(text)) {
    return "AI server unavailable";
  }
  return text || "AI server unavailable";
}
