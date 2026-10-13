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
  assert.equal(state.status("idle", "Idle").label, "Ready");
  assert.equal(state.problem, "");
  assert.equal(state.updatedAt, 200);
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
