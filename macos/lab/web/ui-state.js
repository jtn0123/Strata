"use strict";

// The pinned Monitor polls /metrics once a second and schedules the next poll
// only after a reply settles. A reply still pending after this is abandoned.
const STRATA_METRICS_TIMEOUT_MS = 5000;
// Older samples are shown as stale. This exceeds one poll wait plus one full
// deadline (6 s), so only a failed or abandoned poll can expire a sample.
const STRATA_TELEMETRY_FRESH_MS = 10000;

// A cached tab render must not make failed telemetry look like a fresh sample.
class StrataUIState {
  constructor() { this.metrics = null; this.problem = ""; this.updatedAt = 0; }
  receive(metrics, now = Date.now()) {
    if (metrics !== this.metrics) {
      this.metrics = metrics;
      this.problem = "";
      this.updatedAt = now;
    }
  }
  // Why the shown readings are not current, or "" while they are. Before the
  // first sample there is nothing to expire.
  staleReason(now = Date.now()) {
    if (this.problem) return this.problem;
    const expired = this.updatedAt > 0 && now - this.updatedAt > STRATA_TELEMETRY_FRESH_MS;
    return expired ? `No new readings for over ${STRATA_TELEMETRY_FRESH_MS / 1000} seconds` : "";
  }
  status(state, text, now = Date.now()) {
    if (state === "error") this.problem = text;
    if (this.problem) {
      return {state: "error", label: /API key/i.test(this.problem) ? "Key needed" : "Offline", announcement: this.problem};
    }
    const stale = this.staleReason(now);
    if (stale) return {state: "stale", label: "Not updating", announcement: stale};
    const announcement = {idle: "Ready", reading: "Reading prompt", generating: "Generating answer", queued: "Requests queued"}[state] || text;
    return {state, label: state === "idle" ? "Ready" : text, announcement};
  }
}

class StrataRequestTiming {
  begin(message, started, kind) { this.message = message; this.started = started; this.kind = kind; }
  record(message, streaming, now) {
    if (message !== this.message || !Number.isFinite(this.started)) return;
    const timing = message.performanceTiming ||= {measurement_kind: this.kind};
    const elapsed = Math.max(0, now - this.started);
    if (timing.first_text_ms == null && (message.text || message.reasoning)) timing.first_text_ms = elapsed;
    if (!streaming) {
      timing.total_ms = elapsed;
      timing.finish = message.error ? "error" : message.stopped ? "stopped" : "completed";
    }
    return timing;
  }
  end() { this.message = null; this.started = null; }
}

class StrataChatUndo {
  constructor(cleared) { this.cleared = cleared; }
  restore(current, busy, restore) {
    if (busy || current !== this.cleared || current.length) return false;
    restore();
    return true;
  }
}

// The pinned chat reader accepts EOF without checking its terminal SSE record.
// Watch only that response; keep the bytes and AbortError behavior unchanged.
class StrataSSECompletion {
  constructor() { this.decoder = new TextDecoder(); this.pending = ""; this.terminal = false; }
  receive(bytes) {
    this.pending += this.decoder.decode(bytes, {stream: true});
    let newline;
    while ((newline = this.pending.indexOf("\n")) >= 0) {
      this.line(this.pending.slice(0, newline));
      this.pending = this.pending.slice(newline + 1);
    }
  }
  line(line) {
    if (!line.trim().startsWith("data:")) return;
    const data = line.trim().slice(5).trim();
    if (data === "[DONE]") { this.terminal = true; return; }
    try {
      const packet = JSON.parse(data);
      if (packet.error || packet.choices?.some((choice) => typeof choice.finish_reason === "string" && choice.finish_reason)) this.terminal = true;
    } catch { /* the original parser owns malformed records */ }
  }
  end() {
    this.pending += this.decoder.decode();
    this.line(this.pending);
    if (!this.terminal) throw new Error("The connection ended before the answer finished. Any partial response is kept; retry when the server is ready.");
  }
}

function strataCompletionResponse(response, signal) {
  if (!response.ok || !response.body || !response.headers.get("Content-Type")?.includes("text/event-stream")) return response;
  const reader = response.body.getReader(), completion = new StrataSSECompletion();
  const stream = new ReadableStream({
    async pull(controller) {
      try {
        const {value, done} = await reader.read();
        if (done) {
          if (signal?.aborted) throw new DOMException("The request was stopped.", "AbortError");
          completion.end();
          controller.close();
          reader.releaseLock();
        } else {
          completion.receive(value);
          controller.enqueue(value);
        }
      } catch (error) {
        controller.error(error);
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
    },
    cancel(reason) { return reader.cancel(reason); },
  });
  return new Response(stream, {status: response.status, statusText: response.statusText, headers: response.headers});
}

function strataUnavailableFiles(messages) {
  return messages.flatMap((message) => (message.files || []).filter((file) => file.text == null));
}

function strataChatMarkdown(messages, model) {
  return messages.map((message) => {
    if (message.role !== "user") {
      const reasoning = message.reasoning ? `<details><summary>Thinking</summary>\n\n${message.reasoning}\n\n</details>\n\n` : "";
      const interruption = message.text && message.error ? `\n\nRequest interrupted: ${message.error}` : "";
      return `## ${model}\n\n${reasoning}${message.text || message.error || ""}${interruption}\n`;
    }
    const files = (message.files || []).map((file) => {
      if (file.text == null) return `Attachment: ${file.name} — contents unavailable after reload; reattach to use them again.`;
      const fence = "`".repeat(Math.max(2, ...(file.text.match(/`+/g) || []).map((part) => part.length)) + 1);
      return `File: ${file.name}\n${fence}\n${file.text}\n${fence}`;
    });
    return `## You\n\n${[message.text, ...files].filter(Boolean).join("\n\n")}\n`;
  }).join("\n");
}

function strataIntegerError(value, label) {
  return value.trim() && (!Number.isSafeInteger(Number(value)) || Number(value) <= 0)
    ? `${label} must be a positive whole number, or leave it empty.` : "";
}

class StrataSharedSettings {
  request = 0;
  revision = 0;
  edited() { this.revision++; }
  invalidate() { this.request++; }
  async load(read, write, fail = () => {}) {
    const request = ++this.request, revision = this.revision;
    try {
      const value = await read();
      if (request === this.request) write(value, revision === this.revision);
    } catch (error) {
      if (request === this.request) fail(error);
    }
  }
}

// Bound one /metrics reply, including its body, so a stalled response cannot stop
// the pinned poll loop. A caller's own signal still cancels it with its reason.
async function strataMetricsResponse(fetcher, resource, options = {}) {
  const deadline = new window.AbortController(), caller = options.signal;
  const stopped = new Promise((resolve, reject) => {
    deadline.signal.addEventListener("abort", () => reject(deadline.signal.reason), {once: true});
  });
  const cancel = () => deadline.abort(caller.reason);
  if (caller?.aborted) cancel(); else caller?.addEventListener("abort", cancel, {once: true});
  const timer = window.setTimeout(() => deadline.abort(new DOMException(
    `Telemetry did not answer within ${STRATA_METRICS_TIMEOUT_MS / 1000} seconds.`, "TimeoutError")), STRATA_METRICS_TIMEOUT_MS);
  try {
    // Racing also settles if a fetch implementation ignores the signal.
    const response = await Promise.race([fetcher(resource, {...options, signal: deadline.signal}), stopped]);
    const body = response.body ? await Promise.race([response.arrayBuffer(), stopped]) : null;
    return new Response(body, {status: response.status, statusText: response.statusText, headers: response.headers});
  } finally {
    window.clearTimeout(timer);
    caller?.removeEventListener("abort", cancel);
  }
}

// Install before app.js so its optional ?q= shortcut is covered too. Only
// /metrics has a deadline: completion streams may wait through long prompt reading.
if (typeof window !== "undefined") {
  const strataFetch = window.fetch.bind(window);
  window.fetch = async (resource, options) => {
    if (resource === "/metrics") return strataMetricsResponse(strataFetch, resource, options);
    const response = await strataFetch(resource, options);
    return resource === "/v1/chat/completions" && options?.method === "POST"
      ? strataCompletionResponse(response, options.signal) : response;
  };
}

if (typeof module !== "undefined") {
  module.exports = StrataUIState;
  module.exports.RequestTiming = StrataRequestTiming;
  module.exports.ChatUndo = StrataChatUndo;
  module.exports.SSECompletion = StrataSSECompletion;
  module.exports.completionResponse = strataCompletionResponse;
  module.exports.unavailableFiles = strataUnavailableFiles;
  module.exports.chatMarkdown = strataChatMarkdown;
  module.exports.integerError = strataIntegerError;
  module.exports.SharedSettings = StrataSharedSettings;
  module.exports.METRICS_TIMEOUT_MS = STRATA_METRICS_TIMEOUT_MS;
  module.exports.TELEMETRY_FRESH_MS = STRATA_TELEMETRY_FRESH_MS;
}
