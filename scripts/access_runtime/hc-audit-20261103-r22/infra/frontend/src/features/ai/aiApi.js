import { imagePayload } from "./aiImages.mjs";
import { api } from "../../apiClient";

export const fetchAiStatus = () => api("/api/ai/status", { allowOkFalse: true });
export const fetchAiNodeStatus = () => api("/api/ai/node/status", { allowOkFalse: true });
export const fetchAiConfig = () => api("/api/ai/config");
export const fetchAiModels = () => api("/api/ai/models", { allowOkFalse: true });
export const fetchAiPullStatus = () => api("/api/ai/models/pull/status");

export function saveAiConfigPayload(config) {
  return api("/api/ai/config", {
    method: "POST",
    body: JSON.stringify({ config }),
  });
}

export function pullAiModel(model) {
  return api("/api/ai/models/pull", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

export function wakeAiNodeRequest() {
  return api("/api/ai/node/wake", { method: "POST", body: "{}" });
}

export function runAiNodeCommandRequest(payload) {
  return api("/api/ai/node/command", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function restartAiGatewayRequest() {
  return api("/api/ai/restart", { method: "POST", body: "{}" });
}

export function sendAiChatMessage(message, history, images = []) {
  return api("/api/ai/chat", {
    method: "POST",
    body: JSON.stringify({ message, history, ...(images.length ? { images: imagePayload(images) } : {}) }),
  });
}
