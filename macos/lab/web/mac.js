// Compatibility and accessibility over the pinned API shell; native settings stay with the server.
"use strict";
(() => {
  const input = document.getElementById("input");
  const subtitle = document.getElementById("chat-empty-sub");
  const welcomeText = "Ask a question, work through some code, or give your next idea a place to start.";
  const keepWelcomeCopy = () => { if (subtitle.textContent !== welcomeText) subtitle.textContent = welcomeText; };
  new MutationObserver(keepWelcomeCopy).observe(subtitle, {childList: true, characterData: true, subtree: true});
  keepWelcomeCopy();
  const originalToast = toast;
  toast = (kind, title, text, ms, action) => {
    if (title === "New chat" && action?.label === "Undo") {
      const undo = new StrataChatUndo(messages), restore = action.run;
      action = {...action, run: () => {
        if (!undo.restore(messages, busy, restore)) originalToast("info", "Your new chat is kept", "The earlier chat can no longer replace this conversation.");
      }};
    }
    return originalToast(kind, title, text, ms, action);
  };

  const originalUpdate = updateAssistant;
  updateAssistant = (element, message, streaming) => {
    // The older renderer replaces partial text with an error. Keep both visible.
    originalUpdate(element, message.error && message.text ? {...message, error: ""} : message, streaming);
    const bubble = element.querySelector(".st-bubble");
    if (message.error && message.text) {
      const warning = document.createElement("div");
      warning.className = "msg-error partial-response-error";
      warning.textContent = message.error;
      bubble.appendChild(warning);
    }
    bubble.querySelectorAll("table").forEach((table) => {
      const scroll = document.createElement("div");
      scroll.className = "response-table";
      scroll.tabIndex = 0;
      scroll.setAttribute("role", "region");
      scroll.setAttribute("aria-label", "Response table; scroll to see all columns");
      table.replaceWith(scroll);
      scroll.appendChild(table);
    });
  };

  $("export-btn").onclick = () => {
    if (!messages.length) { toast("info", "Nothing to save yet"); return; }
    const url = URL.createObjectURL(new Blob([strataChatMarkdown(messages, health.model)], {type: "text/markdown"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = `strata-chat-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}.md`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  let attachmentWarningChat = null;
  const originalSend = send;
  send = async () => {
    if (!busy && (input.value.trim() || attachments.length) && strataUnavailableFiles(messages).length && attachmentWarningChat !== messages) {
      toast("warn", "Earlier files need reattaching", "File contents are not kept after a reload. Reattach them if this question depends on them.", 6000);
      attachmentWarningChat = messages;
    }
    return originalSend();
  };
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
    document.querySelectorAll(".st-msg--user").forEach((element) => {
      const message = messages[+element.dataset.i];
      if (!strataUnavailableFiles([message]).length) return;
      const files = element.querySelector(".msg-images");
      [...files.children].forEach((chip, index) => {
        if (message.files[index].text != null) return;
        chip.classList.add("chip--unavailable");
        chip.title = "Contents unavailable after reload. Reattach this file to use it again.";
      });
      const note = document.createElement("div");
      note.className = "attachment-warning";
      const copy = document.createElement("span");
      copy.textContent = "File contents were not saved. Reattach to use them again.";
      const reattach = document.createElement("button");
      reattach.type = "button";
      reattach.className = "st-btn st-btn--secondary";
      reattach.textContent = "Reattach";
      reattach.onclick = () => $("file").click();
      note.append(copy, reattach);
      files.after(note);
    });
    resizeInput();
    if (!messages.length) document.getElementById("chat-scroll").scrollTop = 0;
  };
  // ?q= may already be streaming before this script loads. send() owns that
  // assistant element until completion; rebuilding rows would detach it.
  if (!busy) renderChat();

  // Keep the closed drawer out of keyboard navigation; restore focus when dismissed.
  const drawer = document.getElementById("drawer");
  const sharing = new StrataSharedSettings();
  let sharingKnown = false;
  $("s-share").addEventListener("click", () => sharing.edited());
  loadShared = () => {
    sharingKnown = false;
    $("shared-status").textContent = "Checking settings for other apps…";
    return sharing.load(async () => {
      const response = await fetch("/settings", {headers: headers()});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return !!(await response.json()).shared;
    }, (value, untouched) => {
      sharedOn = value;
      sharingKnown = true;
      if (untouched) $("s-share").setAttribute("aria-checked", String(value));
      $("shared-status").textContent = "";
    }, () => { $("shared-status").textContent = "Could not check other apps. Your choice will be applied when you save."; });
  };

  const thinking = [...$("s-thinking").children];
  const thinkingTabStops = () => thinking.forEach((button) => { button.tabIndex = button.getAttribute("aria-checked") === "true" ? 0 : -1; });
  const originalLoadDrawer = loadDrawer;
  loadDrawer = (...args) => { originalLoadDrawer(...args); thinkingTabStops(); };
  thinking.forEach((button, index) => {
    button.addEventListener("click", thinkingTabStops);
    button.addEventListener("keydown", (event) => {
      let next;
      if (["ArrowRight", "ArrowDown"].includes(event.key)) next = (index + 1) % thinking.length;
      if (["ArrowLeft", "ArrowUp"].includes(event.key)) next = (index + thinking.length - 1) % thinking.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = thinking.length - 1;
      if (next == null) return;
      event.preventDefault();
      thinking[next].click();
      thinking[next].focus();
    });
  });

  // Keep the pinned sampling values; validate before saving. If GET is still
  // pending, explicitly write the chosen sharing state instead of guessing it.
  $("s-apply").onclick = async () => {
    for (const [id, label] of [["s-max", "Max tokens"], ["s-seed", "Seed"]]) {
      const control = $(id);
      control.setCustomValidity(strataIntegerError(control.value, label));
      if (!control.reportValidity()) return;
    }
    const selected = thinking.find((button) => button.getAttribute("aria-checked") === "true");
    settings = {thinking: selected ? selected.dataset.v : "high", temperature: +$("s-temp").value,
      top_p: +$("s-topp").value, top_k: +$("s-topk").value,
      max: $("s-max").value.trim(), seed: $("s-seed").value.trim(),
      show: $("s-show").getAttribute("aria-checked") === "true",
      esp: $("s-esp").getAttribute("aria-checked") === "true"};
    store.set("sampling", settings);
    const share = $("s-share").getAttribute("aria-checked") === "true";
    const saveForApps = share || sharedOn || !sharingKnown;
    openDrawer(false);
    if (saveForApps) {
      try {
        await saveShared(share, settings);
        toast("success", "Sampling saved", share ? "Other apps use these settings from their next request." : "Other apps use their own settings again.");
      } catch (error) { toast("error", "Saved here, but not for other apps", error.message, 6000); }
    } else {
      toast("success", "Sampling saved", settings.temperature === 0 ? "Greedy: the same question gives the same answer." : "");
    }
  };
  for (const id of ["s-max", "s-seed"]) $(id).addEventListener("input", () => $(id).setCustomValidity(""));
  const originalOpenDrawer = openDrawer;
  openDrawer = (open) => {
    sharing.invalidate();
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
    $("connection-settings").hidden = status.label !== "Key needed";
    document.querySelector(".monitor").dataset.stale = String(status.state === "error");
    if (status.state === "error") document.getElementById("monitor-summary").textContent = status.announcement + " · readings are stale";
  };
  $("connection-settings").onclick = () => { showTab("about"); $("api-key").focus(); };

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
