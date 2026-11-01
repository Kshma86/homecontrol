# AI Module Scenarios And Eval Cases

## Empty Chat Message

Given:

- `/api/ai/chat` receives an empty message.

Expected:

- HTTP `400`.
- Error is `message is required`.
- No upstream AI request is sent.

## Chat With History

Given:

- Chat request includes more than 20 history entries.

Expected:

- Upstream receives only the last 20 entries.
- Upstream receives `context` from AI summary.
- Upstream receives `context.knowledge_docs`.

## Knowledge Routing

Given:

- Chat message asks about X10 scheduler and climate.

Expected:

- `knowledge_docs.selected_modules` includes `x10` and `climate`.
- `knowledge_docs.files` includes `x10-domain.md` and `climate-domain.md`.
- Knowledge content includes the global AI context pack instructions.

## AI Server Unavailable

Given:

- Upstream AI server times out or refuses connection.

Expected:

- Response has `ok: false`.
- Status is `502`.
- Payload includes server URL and error.

## Analyze AI Requests

Given:

- User asks to analyze AI requests, AI usage, chat audit, or context-layer needs.

Expected:

- Answer from `context.ai_chat_audit`, not from generic assumptions.
- Mention the audit sample size and recent window.
- Focus findings on context-layer improvements: missing compact fields, wrong
  skill routing, slow context sections, expensive DB paths, and frequent question
  patterns that should become first-class context.
- Use `top_skills`, `top_data_sources`, `slow_context_sections`, `slow_skills`,
  `latency`, and `recent_questions` when present.

## Pull Model Without Name

Given:

- `/api/ai/models/pull` receives no model name.

Expected:

- HTTP `400`.
- Error is `model is required`.

## AI Node Wake Invalid MAC

Given:

- `AI_NODE_MAC` is missing or malformed.

Expected:

- Wake command raises validation error.
- No magic packet is sent.

## Unsupported Remote Command

Given:

- AI node command action is not in the allowlist.

Expected:

- Reject with unsupported command.
- No SSH command is executed.

## Suggested Tests

- Chat injects context summary.
- History truncation to 20 entries.
- Upstream HTTP errors preserve payload.
- AI node public config does not expose secrets.
