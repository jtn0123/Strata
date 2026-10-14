const test = require("node:test");
const assert = require("node:assert/strict");
const StrataUIState = require("../web/ui-state.js");

test("offline persists when switching tabs over the cached sample", () => {
  const state = new StrataUIState(), sample = {live: {state: "idle"}};
  state.receive(sample, 100);
  state.status("error", "Server not reachable");
  state.receive(sample, 200);
  assert.equal(state.status("idle", "Idle").label, "Offline");
  assert.equal(state.updatedAt, 100);
});

test("a successful new telemetry response recovers connection state", () => {
  const state = new StrataUIState();
  state.receive({}, 100);
  state.status("error", "Server not reachable");
  state.receive({}, 200);
  assert.equal(state.status("idle", "Idle", 300).label, "Ready");
  assert.equal(state.problem, "");
  assert.equal(state.updatedAt, 200);
});

test("a sample older than the freshness window is stale until a new sample arrives", () => {
  const state = new StrataUIState(), sample = {}, fresh = StrataUIState.TELEMETRY_FRESH_MS;
  assert.equal(state.staleReason(10 * fresh), "", "nothing expires before the first sample");
  state.receive(sample, 1000);
  assert.equal(state.status("idle", "Idle", 1000 + fresh).label, "Ready", "the window boundary is still current");
  assert.deepEqual(state.status("generating", "Generating · 12 tok/s", 1001 + fresh),
    {state: "stale", label: "Not updating", announcement: `No new readings for over ${fresh / 1000} seconds`});
  state.receive(sample, 2000 + fresh);
  assert.equal(state.status("idle", "Idle", 2000 + fresh).state, "stale", "a cached render is not a new sample");
  state.receive({}, 2000 + fresh);
  assert.equal(state.status("idle", "Idle", 2000 + fresh).label, "Ready");
  assert.equal(state.staleReason(2000 + fresh), "");
});

test("a reported connection error outranks an expired sample", () => {
  const state = new StrataUIState(), fresh = StrataUIState.TELEMETRY_FRESH_MS;
  state.receive({}, 1000);
  assert.equal(state.status("error", "Server not reachable", 2000 + fresh).label, "Offline");
  assert.equal(state.staleReason(2000 + fresh), "Server not reachable");
});

test("the metrics deadline ends before an on-time slow reply could expire a sample", () => {
  // One pinned poll wait (1 s) plus a full deadline must stay inside the window.
  assert.ok(1000 + StrataUIState.METRICS_TIMEOUT_MS < StrataUIState.TELEMETRY_FRESH_MS);
});

test("API key failures are retained separately from offline errors", () => {
  const state = new StrataUIState(), sample = {};
  state.receive(sample);
  state.status("error", "API key needed");
  state.receive(sample);
  assert.equal(state.status("generating", "Generating · 12 tok/s").label, "Key needed");
});

test("numeric speed updates have a stable announcement", () => {
  const state = new StrataUIState();
  const first = state.status("generating", "Generating · 12 tok/s");
  const next = state.status("generating", "Generating · 17 tok/s");
  assert.notEqual(first.label, next.label);
  assert.equal(first.announcement, next.announcement);
  assert.notEqual(next.announcement, state.status("idle", "Idle").announcement);
});

test("a new request never overwrites an earlier reply's timing", () => {
  const timing = new StrataUIState.RequestTiming();
  const old = {text: "earlier", performanceTiming: {total_ms: 90}};
  const current = {text: "new reply"};
  timing.begin(current, 100, "mock");
  timing.record(old, false, 101);
  assert.equal(old.performanceTiming.total_ms, 90);
  timing.record(current, true, 110);
  timing.record(current, false, 125);
  assert.equal(current.performanceTiming.first_text_ms, 10);
  assert.equal(current.performanceTiming.total_ms, 25);
  assert.equal(current.performanceTiming.finish, "completed");
});

test("initial rendering and post-request rendering cannot invent timings", () => {
  const timing = new StrataUIState.RequestTiming(), message = {text: "saved reply"};
  timing.record(message, false, 10);
  assert.equal(message.performanceTiming, undefined);
  timing.begin(message, 100, "model"); timing.end();
  timing.record(message, false, 200);
  assert.equal(message.performanceTiming, undefined);
});

test("failed requests retain their duration without inventing first text", () => {
  const timing = new StrataUIState.RequestTiming(), message = {error: "request failed"};
  timing.begin(message, 100, "mock");
  timing.record(message, false, 150);
  assert.equal(message.performanceTiming.first_text_ms, undefined);
  assert.equal(message.performanceTiming.total_ms, 50);
  assert.equal(message.performanceTiming.finish, "error");
});
