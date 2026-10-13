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

if (typeof module !== "undefined") {
  module.exports = StrataUIState;
  module.exports.RequestTiming = StrataRequestTiming;
}
