// A small UI layer over the pinned API shell. No generation parameters or requests are changed.
"use strict";
(() => {
  const input = document.getElementById("input");
  const subtitle = document.getElementById("chat-empty-sub");
  const welcomeText = "Ask a question, work through some code, or give your next idea a place to start.";
  const keepWelcomeCopy = () => { if (subtitle.textContent !== welcomeText) subtitle.textContent = welcomeText; };
  new MutationObserver(keepWelcomeCopy).observe(subtitle, {childList: true, characterData: true, subtree: true});
  keepWelcomeCopy();
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      if (busy) return;
      if (input.value.trim()) {
        toast("info", "Your draft is still here", "Clear the message first to use a starter.");
        input.focus();
        return;
      }
      input.value = button.dataset.prompt;
      input.dispatchEvent(new Event("input", {bubbles: true}));
      input.focus();
    });
  });
  const compact = matchMedia("(max-width: 700px)");
  const resizeInput = () => { input.rows = compact.matches || messages.length ? 1 : 2; autosize(); };
  compact.addEventListener("change", resizeInput);
  resizeInput();

  // Upstream 6a7c6f82: do not magnify tiny disk noise into full-height spikes.
  const originalSpark = spark;
  spark = (id, values, max) => originalSpark(id, values, Math.max(max || 0, 1));

  const tabs = [...document.querySelectorAll(".st-tab")];
  const originalShowTab = showTab;
  showTab = (name) => {
    originalShowTab(name);
    tabs.forEach((button) => { button.tabIndex = button.getAttribute("aria-selected") === "true" ? 0 : -1; });
  };
  tabs.forEach((button, index) => {
    button.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next == null) return;
      event.preventDefault();
      showTab(tabs[next].dataset.tab);
      tabs[next].focus();
    });
  });
  showTab(location.hash.slice(1));

  // On a small screen the welcome content scrolls; an empty chat starts at its top.
  const originalRenderChat = renderChat;
  renderChat = () => {
    originalRenderChat();
    resizeInput();
    if (!messages.length) document.getElementById("chat-scroll").scrollTop = 0;
  };
  if (!messages.length) document.getElementById("chat-scroll").scrollTop = 0;

  // Keep the closed drawer out of keyboard navigation; restore focus when dismissed.
  const drawer = document.getElementById("drawer");
  const originalOpenDrawer = openDrawer;
  openDrawer = (open) => {
    originalOpenDrawer(open);
    drawer.inert = !open;
    document.getElementById("sampling-btn").setAttribute("aria-expanded", String(open));
    (open ? document.getElementById("drawer-close") : document.getElementById("sampling-btn")).focus();
  };
  drawer.inert = drawer.dataset.open !== "true";
  drawer.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const controls = [...drawer.querySelectorAll("button, input")].filter((el) =>
      !el.disabled && !el.closest("[hidden]") && el.getClientRects().length);
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  const originalSetPill = setPill;
  const connection = new StrataUIState();
  let announced = "", pendingAnnouncement = "", announcementQueued = false;
  setPill = (state, text) => {
    const status = connection.status(state, text);
    originalSetPill(status.state, status.label);
    const pill = document.getElementById("pill");
    pill.dataset.state = status.state;
    pill.title = status.announcement;
    pill.setAttribute("aria-label", status.announcement);
    pendingAnnouncement = status.announcement;
    if (!announcementQueued) {
      announcementQueued = true;
      queueMicrotask(() => {
        announcementQueued = false;
        if (announced !== pendingAnnouncement) {
          document.getElementById("pill-live").textContent = pendingAnnouncement;
          announced = pendingAnnouncement;
        }
      });
    }
    document.getElementById("connection-banner").hidden = status.state !== "error";
    document.getElementById("connection-message").textContent = status.label === "Key needed"
      ? "Add your API key in About → Settings to connect."
      : "Can’t reach the local server. Reconnecting… Monitor shows the last readings.";
    document.querySelector(".monitor").dataset.stale = String(status.state === "error");
    if (status.state === "error") document.getElementById("monitor-summary").textContent = status.announcement + " · readings are stale";
  };

  const originalRender = render;
  render = (metrics) => {
    connection.receive(metrics);
    originalRender(metrics);
    const hw = metrics.hardware || {}, engine = metrics.engine || {};
    const model = engine.model || health.model || "Local model";
    document.getElementById("workspace-model").textContent = model + (connection.problem ? " · last seen" : "");
    const summary = document.getElementById("monitor-summary");
    summary.textContent = connection.problem ? connection.problem + " · readings are stale" : hw.ram_total && hw.ram_used != null
      ? `${gb(hw.ram_used)} / ${gb(hw.ram_total, 0)} GiB system memory in use`
      : "System memory is not reported by this backend";
    const unavailable = [];
    for (const key of ["gpu", "vram", "temp", "power", "pcie"]) {
      const metric = METRICS.find((item) => item.key === key);
      const missing = hw[metric.series] == null;
      document.getElementById(`mv-${key}`).closest(".metric-card").hidden = missing;
      if (missing) unavailable.push(metric.label);
    }
    document.getElementById("telemetry-note").textContent = unavailable.length
      ? `${unavailable.join(", ")} ${unavailable.length === 1 ? "is" : "are"} not reported by this backend. Missing readings are hidden, not treated as zero.`
      : "Hardware readings come from the server. Disk activity includes other work on this Mac.";
    document.getElementById("gpu-fact-note").hidden = !!(metrics.hardware_static || {}).gpu_name;
    const unmeasuredSpeed = document.getElementById("mv-speed").textContent.trim() === "–";
    document.getElementById("sp-speed").style.visibility = unmeasuredSpeed ? "hidden" : "visible";
    if (unmeasuredSpeed) document.getElementById("ms-speed").textContent = "Not measured yet";
    if (hw.ram_total) document.getElementById("ram-text").textContent = `${gb(hw.ram_used)} / ${gb(hw.ram_total, 0)} GiB`;
    // These CUDA labels do not describe a backend that supplies no such counters.
    for (const [id, available] of [["slots-text", !!engine.expert_slots], ["temp-text", hw.gpu_temp != null]]) {
      const row = document.getElementById(id).closest(".bar-row");
      row.hidden = !available;
      row.nextElementSibling.hidden = !available;
    }
    if (!(metrics.hardware_static || {}).gpu_name) {
      const labels = [...document.querySelectorAll("#facts-hw dt")];
      const gpu = labels.find((el) => el.textContent === "GPU");
      if (gpu) gpu.nextElementSibling.textContent = "Not reported by this backend";
      const ram = labels.find((el) => el.textContent === "RAM");
      if (ram && hw.ram_total) ram.nextElementSibling.textContent = `${gb(hw.ram_total, 0)} GiB`;
    }
  };
  if (lastMetrics) render(lastMetrics);
})();
