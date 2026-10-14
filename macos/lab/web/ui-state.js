"use strict";

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
  status(state, text) {
    if (state === "error") this.problem = text;
    if (this.problem) {
      return {state: "error", label: /API key/i.test(this.problem) ? "Key needed" : "Offline", announcement: this.problem};
    }
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
    } catch (_) { /* the original parser owns malformed records */ }
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
    if (message.role !== "user") return `## ${model}\n\n${message.reasoning ? `<details><summary>Thinking</summary>\n\n${message.reasoning}\n\n</details>\n\n` : ""}${message.text || message.error || ""}${message.text && message.error ? `\n\nRequest interrupted: ${message.error}` : ""}\n`;
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
  constructor() { this.request = 0; this.revision = 0; }
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

// Install before app.js so its optional ?q= shortcut is covered too.
if (typeof window !== "undefined") {
  const strataFetch = window.fetch.bind(window);
  window.fetch = async (resource, options) => {
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
}
