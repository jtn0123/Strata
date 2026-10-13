"use strict";
(() => {
  const valid = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
  const duration = (ms) => !valid(ms) ? "–" : ms > 0 && ms < 1 ? "<1 ms" : ms < 1000 ? `${fmt(ms)} ms` : `${fmt(ms / 1000, 2)} s`;
  const rate = (value) => valid(value) && value > 0 ? `${fmt(value, 1)} tok/s` : "–";
  const requestKeys = ["time", "finish", "measurement_kind", "prompt_tokens", "output_tokens", "reused", "generation_tps", "generation_source", "prompt_tps", "server_first_token_ms", "server_duration_ms", "draft_acceptance_percent"];
  const settingKeys = ["model", "engine", "context", "cache_type", "spec", "draft", "draft_model", "lookup_profile", "tensor_api", "m5_tuning", "batch", "ubatch", "draft_threads", "draft_placement", "draft_p_min"];
  const onlySettings = (value = {}) => Object.fromEntries(settingKeys.filter((key) => key in value).map((key) => [key, value[key]]));
  const saved = store.get("performance.history", []);
  let recorded = Array.isArray(saved) ? saved.filter((row) => row && typeof row === "object" && valid(row.time)).slice(-200) : [];
  const onlyRequest = (row) => Object.fromEntries(requestKeys.filter((key) => key in row).map((key) => [key, row[key]]));
  let latest = null;
  const requestTiming = new StrataRequestTiming();
  const originalSend = send;
  send = async () => {
    if (busy || (!$("input").value.trim() && !attachments.length)) return originalSend();
    const started = performance.now();
    const pending = originalSend();
    requestTiming.begin(busy?.msg, started, latest?.measurement_kind || "unverified");
    try { return await pending; } finally { requestTiming.end(); }
  };
  const originalUpdate = updateAssistant;
  updateAssistant = (element, message, streaming) => {
    originalUpdate(element, message, streaming);
    requestTiming.record(message, streaming, performance.now());
    const timing = message.performanceTiming;
    let badge = element.querySelector(".message-performance");
    if (timing && valid(timing.total_ms)) {
      if (!badge) { badge = document.createElement("div"); badge.className = "message-performance"; element.appendChild(badge); }
      badge.textContent = `${timing.measurement_kind === "model" ? "" : timing.measurement_kind === "mock" ? "Mock · " : "Unverified · "}First text ${duration(timing.first_text_ms)} · browser total ${duration(timing.total_ms)}`;
      badge.title = "Browser-observed text (including thinking) and full request time. Includes frontend work, transport and queuing; different from engine timings.";
    }
  };

  const originalRender = render;
  render = (metrics) => {
    originalRender(metrics);
    latest = metrics.performance || null;
    if (!latest) { $("perf-mode").textContent = "Performance data unavailable"; return; }
    $("perf-mode").textContent = latest.measurement_kind === "mock" ? "Mock preview · test data" : latest.measurement_kind === "model" ? "Live model · recent request" : "Unverified backend";
    const rows = metrics.requests || [], last = rows[0], memory = latest.resources || {}, settings = latest.settings || {};
    let changed = false;
    for (const row of [...rows].reverse()) {
      if (!valid(row.time)) continue;
      const model = metrics.engine?.model || "unknown";
      if (recorded.some((old) => old.time === row.time && old.model === model)) continue;
      recorded.push({...onlyRequest(row), model, settings: onlySettings(settings)});
      changed = true;
    }
    if (changed) { recorded = recorded.slice(-200); store.set("performance.history", recorded); }
    $("perf-history").textContent = `${recorded.length} recorded ${recorded.length === 1 ? "request" : "requests"} in this browser (up to 200). Export includes numeric timing/settings history; resources are the current snapshot.`;
    $("perf-generation").textContent = rate(last?.generation_tps);
    $("perf-generation-detail").textContent = last?.generation_source === "native" ? "Engine timing · last request" : last?.generation_source === "server-derived" ? "Server-derived rate · last request" : "No generation measurement yet";
    $("perf-first").textContent = duration(last?.server_first_token_ms);
    $("perf-total").textContent = duration(last?.server_duration_ms);
    $("perf-prompt").textContent = rate(last?.prompt_tps);
    $("perf-draft").textContent = valid(last?.draft_acceptance_percent) ? `${fmt(last.draft_acceptance_percent, 1)}%` : "–";
    $("perf-reuse").textContent = valid(last?.reused) && last?.prompt_tokens > 0 ? `${fmt(100 * last.reused / last.prompt_tokens)}%` : "–";
    const pressure = {1: "Normal", 2: "Warning", 4: "Critical"}[memory.pressure_level] || "Not reported";
    const bits = [
      ["Available RAM", valid(memory.available_bytes) ? `${gb(memory.available_bytes)} GiB` : "–"],
      ["Model RSS", valid(memory.model_rss_bytes) ? `${gb(memory.model_rss_bytes)} GiB` : "Not reported"],
      ["System swap", valid(memory.swap_used_bytes) ? `${gb(memory.swap_used_bytes, 2)} GiB` : "–"],
      ["New swap this run", valid(memory.new_swap_bytes) ? `${gb(memory.new_swap_bytes, 2)} GiB` : "Not reported"],
      ["Memory pressure", pressure],
    ];
    $("perf-resources").innerHTML = bits.map(([label, value]) => `<span>${esc(label)} <strong>${esc(value)}</strong></span>`).join("");
    const chunks = valid(settings.batch) && valid(settings.ubatch) ? `prompt chunks ${settings.ubatch} / batch ${settings.batch}` : null;
    const identity = [metrics.engine?.model, settings.engine, settings.context && `${ctxfmt(settings.context)} context`, settings.cache_type, settings.spec, settings.draft != null && `draft ${settings.draft}`, settings.lookup_profile && `lookup ${settings.lookup_profile}`, chunks].filter(Boolean).join(" · ");
    $("perf-settings").textContent = `${identity}. Server timing excludes queue/transport. Browser timing appears under your reply. Compare matched workloads and settings; recent chat measurements vary. Disk readings cover the whole Mac.`;
    const head = $("req-body").closest("table").querySelector("thead");
    head.innerHTML = "<tr><th>Time</th><th>Status</th><th class='num'>Input</th><th class='num'>Output</th><th class='num'>First token</th><th class='num'>Generation</th><th class='num'>Total</th><th class='num'>Reused</th></tr>";
    $("req-body").innerHTML = rows.length ? rows.slice(0, 30).map((row) => `<tr><td>${esc(new Date(row.time * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"}))}</td><td>${esc({stop: "Done", length: "Token limit", cancel: "Stopped", disconnect: "Disconnected", error: "Error"}[row.finish] || row.finish || "–")}</td><td class="num">${kfmt(row.prompt_tokens)}</td><td class="num">${kfmt(row.output_tokens)}</td><td class="num">${duration(row.server_first_token_ms)}</td><td class="num">${rate(row.generation_tps)}</td><td class="num">${duration(row.server_duration_ms)}</td><td class="num">${kfmt(row.reused)}</td></tr>`).join("") : '<tr><td colspan="8" class="muted">Your first completed request will appear here.</td></tr>';
  };
  $("perf-export").onclick = () => {
    if (!lastMetrics?.performance) { toast("info", "No metrics yet"); return; }
    const exported = {schema: 1, exported_at: new Date().toISOString(), performance: {schema:1, measurement_kind:lastMetrics.performance.measurement_kind, settings:onlySettings(lastMetrics.performance.settings), resources:lastMetrics.performance.resources, scope:lastMetrics.performance.scope},
      requests: (lastMetrics.requests || []).map(onlyRequest),
      recorded_requests: recorded.map((row) => ({...onlyRequest(row), model: row.model, settings: onlySettings(row.settings)})),
      browser_timings: messages.filter((message) => message.performanceTiming).map((message) => Object.fromEntries(["measurement_kind", "first_text_ms", "total_ms", "finish"].filter((key) => key in message.performanceTiming).map((key) => [key, message.performanceTiming[key]])))};
    const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2)], {type: "application/json"}));
    const link = document.createElement("a"); link.href = url; link.download = `strata-metrics-${Date.now()}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  if (lastMetrics) render(lastMetrics);
})();
