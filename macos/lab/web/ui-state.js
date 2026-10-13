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

if (typeof module !== "undefined") module.exports = StrataUIState;
