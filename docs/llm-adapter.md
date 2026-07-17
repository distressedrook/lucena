# LLM Adapter — contract (v0, to lock)

> The **generic** LLM layer. The loop depends ONLY on this interface — never on a provider
> SDK. Provider and model are **configuration**, so switching Gemini → OpenRouter → anything is a
> config change, not code. The adapter is **in-process** (a thin HTTP client), never tool-calls, and
> never touches state.

## Interface

OpenAI-chat-shaped (messages in, one completion out) so an OpenRouter adapter is a drop-in.

```python
@dataclass
class Message:      # role: "system" | "user" | "assistant"
    role: str
    content: str

@dataclass
class GenerateOptions:
    model: str | None = None          # provider model id; None → the configured default
    schema: dict | None = None        # JSON Schema → force structured JSON output
    temperature: float = 0.4
    max_tokens: int = 400
    timeout_s: float = 30.0

@dataclass
class Usage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None

@dataclass
class Completion:
    text: str                         # raw text (or the JSON string when schema is set)
    json: dict | None                 # parsed object when schema is set, else None
    model: str                        # the model actually used
    usage: Usage

class LLMAdapter(Protocol):
    async def generate(self, messages: list[Message], opts: GenerateOptions) -> Completion: ...
```

That's the whole surface the loop sees. No tools, no streaming (hot-path generations return
once), no provider types leaking out.

## Providers (config-selected)

- **`GeminiAdapter`** (today) — wraps `google-genai`. Maps `messages` → Gemini contents +
  `system_instruction`; `schema` → `response_mime_type=application/json` (+ response schema); returns
  `usage_metadata`.
- **`OpenRouterAdapter`** (later) — OpenAI-compatible `/chat/completions`: `messages` verbatim,
  `response_format={type: json_schema}` for structured output, `usage` verbatim. Model ids are the
  OpenRouter namespace (`"google/gemini-…"`, `"anthropic/claude-…"`, …).

Selection is config: `{ provider: "gemini"|"openrouter", api_key_env, default_model, per_flow_models? }`.

## Rules

1. **The loop imports the interface, never a provider.** No `google.genai` / `openai` import
   outside the adapter package. Enforced by a lint/grep gate in CI.
2. **Model + params are config**, resolvable per flow (e.g. a cheap model for `coach`, a slightly
   stronger one for `grade`) — but the loop only passes an `opts.model` string it got from
   config; it never hardcodes one.
3. **Retry with backoff on 429/503** lives in the adapter (fail-fast bound so a rate-limited call
   surfaces in seconds, not a multi-minute hang — the lesson from the ADK path). The retry budget is
   **bounded by the caller's deadline** (attempts×backoff must not outlast the turn), and a retried
   call sends the **provider idempotency key** so a lost-response retry doesn't double-charge/generate.
   Deciding to *stop retrying and degrade* (the breaker → truth-without-voice) is the **backend's**
   call, not the adapter's — see `architecture.md` "Failure & degradation".
4. **Structured output is first-class** — `schema` set ⇒ `json` populated (adapter parses + validates;
   returns `json=None` + raw `text` on parse failure so the caller can fall back).
5. **Usage is always returned** for cost accounting.
6. **Never tool-calls, never sets state.** Pure text/JSON generation over what the loop hands
   it.
