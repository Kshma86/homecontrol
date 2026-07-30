# AI Module Context

## Scope

The AI module proxies chat/config/model operations to a local or remote AI
server and manages an optional remote AI node.

Primary implementation:

- `infra/backend/ai_proxy_service.py`
- `infra/backend/ai_node_service.py`
- `apps/ai-server/ai_server.py`
- `apps/ai-node/`
- `infra/backend/tests/test_ai_proxy_service.py`

## AI Proxy Ownership

- Proxy owner: `AiProxyService`.
- Backend routes: `/api/ai/*`.
- External server: configured AI server URL.
- Context source for chat: `GET /api/context/ai/summary`.

## AI Proxy Endpoints

- `GET /api/ai/status`
- `POST /api/ai/chat`
- `GET /api/ai/config`
- `POST /api/ai/config`
- `GET /api/ai/models`
- `POST /api/ai/models/pull`
- `GET /api/ai/models/pull/status`

Chat rules:

- `message` is required.
- History is capped to the last 20 entries.
- Every chat payload includes AI-ready HomeControl context.
- Every chat payload includes `context.knowledge_docs`, selected from
  `docs/ai` by `AiKnowledgeLoader`.
- Every non-empty chat request is stored in `hc.ai_chat_audit` with question,
  provider/model/status, selected skills, data sources, DB query count, and
  timestamped context/skill timing details.
- AI-request analysis must use `context.ai_chat_audit` as the source of truth.
  The purpose of that analysis is to improve the context layer: identify missing
  context fields, wrong skill routing, slow context sections, expensive DB paths,
  and frequent question patterns that deserve compact first-class AI context.
- If upstream succeeds but returns `ok: false`, backend returns `502`.
- Upstream unavailable errors return structured `ok: false` payloads.

## Knowledge Loader

`AiKnowledgeLoader` lives in `infra/backend/ai_proxy_service.py`.

It is performance-conscious:

- always includes base files: `README.md`, `module-map.md`,
  `homecontrol-agent-guide.md`;
- selects up to four relevant modules from the current message and the last few
  history items;
- includes the selected module `*-domain.md` and `*-scenarios.md` files;
- caps injected documentation by character budget;
- caches file contents briefly and invalidates by file mtime.

The AI server receives this under:

```json
{
  "context": {
    "knowledge_docs": {
      "version": "homecontrol-ai-context.v1",
      "selected_modules": ["irrigation"],
      "files": ["README.md"],
      "content": "..."
    }
  }
}
```

The AI server's `context_system_message()` injects this as system-level module
knowledge before the live JSON context. Domain docs are authoritative for rules;
the live JSON context is authoritative for current state.

## AI Chat Audit Context

`context.ai_chat_audit` is a compact summary over recent `hc.ai_chat_audit`
rows. It includes:

- `sample_size`, `success`, and `latency`;
- `top_skills` and `top_data_sources`;
- `slow_context_sections` and `slow_skills`;
- recent question samples.

When the user asks to analyze AI requests, do not speculate from memory or from
generic LLM behavior. Use the audit summary and frame the answer as context-layer
improvement work: what data is missing, which sources are overused or slow, which
skills route often, and what compact summaries should be added next.

## AI Node Ownership

`AiNodeService` manages a remote AI node:

- health checks for SSH and Ollama;
- Wake-on-LAN;
- optional power plug control through power-wall service;
- SSH commands for Docker Compose stack management;
- delayed power-off thread.

## AI Node Environment

- `AI_NODE_HOST`
- `AI_NODE_NAME`
- `AI_NODE_MAC`
- `AI_NODE_BROADCAST`
- `AI_NODE_SSH_USER`
- `AI_NODE_SSH_PORT`
- `AI_NODE_SSH_KEY`
- `AI_NODE_STACK_DIR`
- `AI_NODE_NET_IFACE`
- `AI_NODE_POWER_ENTITY_ID`
- `AI_NODE_POWER_OFF_DELAY_SEC`
- `AI_NODE_OLLAMA_URL`
- `AI_NODE_OPENWEBUI_URL`
- `AI_NODE_STATUS_TIMEOUT`
- `AI_NODE_SSH_TIMEOUT`

## AI Node Endpoints

- `GET /api/ai/node/status`
- `POST /api/ai/node/wake`
- `POST /api/ai/node/command`

Supported remote commands:

- `start_stack`
- `stop_stack`
- `restart_stack`
- `pull_images`
- `shutdown`

## Safety Rules

- Do not send chat without context summary unless explicitly debugging.
- Do not expose private SSH key values; only expose whether set.
- Validate Wake-on-LAN MAC before sending packets.
- Remote SSH command actions must stay allowlisted.
- Power plug control must go through `PowerWallService`.
- Delayed power-off delay is clamped to `0..86400` seconds.
