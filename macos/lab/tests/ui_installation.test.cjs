const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const lab = path.join(__dirname, '..');
const markup = fs.readFileSync(path.join(lab, 'web/index.html'), 'utf8');
const scripts = [...markup.matchAll(/<script src="\/web\/([^"]+)"/g)].map((match) => match[1]);
const source = (name) => fs.readFileSync(path.join(lab, name === 'app.js' ? 'vendor/Strata-macOS/serve/web/app.js' : `web/${name}`), 'utf8');
const decode = (text) => text.replace(/&(amp|lt|gt|quot|#39|ndash);/g, (_, name) => ({amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'", ndash: '–'}[name]));

// A deliberately small DOM double, with real markup and no application stubs.
// Layout, contrast and browser accessibility remain the separate browser gate.
class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null;
    this.attributes = {}; this.dataset = {}; this.style = {}; this.listeners = {};
    this.value = ''; this.text = ''; this.hidden = false; this.scrollHeight = 200; this.clientHeight = 200;
    this.classList = {
      add: (name) => { this.className = [...new Set([...this.className.split(/\s+/), name])].join(' '); },
      remove: (name) => { this.className = this.className.split(/\s+/).filter((item) => item !== name).join(' '); },
      toggle: (name, enabled) => { if (enabled) this.classList.add(name); else this.classList.remove(name); },
    };
  }
  get className() { return this.attributes.class || ''; }
  set className(value) { this.attributes.class = value; }
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) { this.children = []; this.text = String(value); }
  set innerHTML(value) { this.children = []; this.text = ''; parseHTML(String(value), this); }
  get firstChild() { return this.children[0]; }
  get lastElementChild() { return this.children.at(-1); }
  get nextElementSibling() { return this.parentNode?.children[this.parentNode.children.indexOf(this) + 1]; }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
    if (name === 'value') this.value = String(value);
    if (name === 'hidden') this.hidden = true;
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  appendChild(child) { child.remove(); child.parentNode = this; this.children.push(child); return child; }
  append(...children) { for (const child of children) this.appendChild(typeof child === 'string' ? Object.assign(new Element('#text'), {text: child}) : child); }
  remove() { if (this.parentNode) this.parentNode.children.splice(this.parentNode.children.indexOf(this), 1); this.parentNode = null; }
  after(child) { const parent = this.parentNode, index = parent.children.indexOf(this); child.remove(); child.parentNode = parent; parent.children.splice(index + 1, 0, child); }
  replaceWith(child) { const parent = this.parentNode, index = parent.children.indexOf(this); this.remove(); child.parentNode = parent; parent.children.splice(index, 0, child); }
  matches(selector) {
    const parts = selector.trim().split(/\s+/), own = parts.pop();
    const tokens = own.match(/#[\w-]+|\.[\w-]+|\[[^\]]+\]|^[\w-]+/g) || [];
    if (!tokens.every((token) => this.matchesToken(token))) return false;
    return !parts.length || !!this.parentNode?.closest(parts.join(' '));
  }
  matchesToken(token) {
    if (token[0] === '#') return this.attributes.id === token.slice(1);
    if (token[0] === '.') return this.className.split(/\s+/).includes(token.slice(1));
    if (token[0] === '[') return Object.hasOwn(this.attributes, token.slice(1, -1));
    return this.tagName.toLowerCase() === token;
  }
  closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector) || null; }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if (selector.split(',').some((part) => child.matches(part))) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  dispatchEvent(event) {
    event.target ||= this;
    this[`on${event.type}`]?.(event);
    for (const handler of this.listeners[event.type] || []) handler(event);
    return true;
  }
  click() { this.dispatchEvent({type: 'click', target: this}); }
  focus() { this.document.activeElement = this; }
  get document() { return this.parentNode?.document || this.ownerDocument; }
  getClientRects() { return this.hidden ? [] : [{}]; }
  setCustomValidity(error) { this.validationMessage = error; }
  reportValidity() { return !this.validationMessage; }
}

function parseHTML(html, root) {
  const stack = [root], voidTags = new Set(['meta', 'link', 'input', 'img', 'br', 'hr']);
  for (const token of html.match(/<!--[\s\S]*?-->|<[^>]*>|[^<]+/g) || []) {
    if (token.startsWith('<!')) continue;
    if (token.startsWith('</')) { if (stack.length > 1) stack.pop(); continue; }
    if (!token.startsWith('<')) { stack.at(-1).text += decode(token); continue; }
    const tag = token.match(/^<([\w-]+)/)?.[1];
    if (!tag) continue;
    const element = new Element(tag);
    for (const attr of token.slice(tag.length + 1, -1).matchAll(/([\w-]+)(?:="([^"]*)"|='([^']*)')?/g)) {
      element.setAttribute(attr[1], decode(attr[2] ?? attr[3] ?? ''));
    }
    stack.at(-1).appendChild(element);
    if (!voidTags.has(tag) && !token.endsWith('/>')) stack.push(element);
  }
}

const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return {promise, resolve};
};
const until = async (condition) => {
  for (let turn = 0; turn < 100 && !condition(); turn++) await Promise.resolve();
  assert.ok(condition(), 'the queued browser operation settled');
};
const sseResponse = (text, terminal = true) => new Response(`data: ${JSON.stringify({choices: [{delta: {content: text}}]})}\n\n${terminal ? 'data: [DONE]\n\n' : ''}`, {headers: {'Content-Type': 'text/event-stream'}});

function installation({question = '', stored = {}} = {}) {
  const root = new Element('root');
  parseHTML(markup.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, ''), root);
  const document = {
    documentElement: root.querySelector('html'), body: root.querySelector('body'),
    getElementById: (id) => root.querySelector(`#${id}`),
    querySelector: (selector) => root.querySelector(selector), querySelectorAll: (selector) => root.querySelectorAll(selector),
    createElement(tag) { const element = new Element(tag); element.ownerDocument = document; return element; },
    addEventListener() {},
  };
  root.ownerDocument = document;
  const storage = new Map(Object.entries(stored).map(([key, value]) => [`strata.${key}`, JSON.stringify(value)]));
  const requests = [], downloads = [], timers = [];
  const context = vm.createContext({document, Blob, Response, ReadableStream, TextDecoder, TextEncoder, DOMException,
    AbortController, URLSearchParams, queueMicrotask, innerHeight: 640,
    localStorage: {getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value)},
    location: {search: question ? `?q=${encodeURIComponent(question)}` : '', hash: '', pathname: '/', origin: 'http://localhost'},
    history: {replaceState() {}}, performance: {now: () => 100},
    MutationObserver: class { observe() {} }, Event: class { constructor(type) { this.type = type; } },
    matchMedia: () => ({matches: false, addEventListener() {}}), addEventListener() {},
    requestAnimationFrame: () => 1, cancelAnimationFrame() {},
    setTimeout: (callback, ms) => timers.push({callback, ms}), clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].cleared = true; },
    URL: {createObjectURL(blob) { downloads.push(blob); return 'blob:test'; }, revokeObjectURL() {}},
    fetch(resource, options) { const pending = deferred(); requests.push({resource, options, ...pending}); return pending.promise; },
  });
  context.window = context;
  const execute = (name) => vm.runInContext(source(name), context, {filename: name});
  const evaluate = (expression) => vm.runInContext(expression, context);
  const reply = (request, resource, response) => {
    assert.ok(request, `expected ${resource} request`); request.answered = true; request.resolve(response);
    return request;
  };
  const answer = (resource, response) => reply(requests.find((entry) => entry.resource === resource && !entry.answered), resource, response);
  // A poll after an abandoned one answers the newest request, not the stalled one.
  const answerLatest = (resource, response) => reply(requests.findLast((entry) => entry.resource === resource && !entry.answered), resource, response);
  // Run each pending timer that matches, as a browser would once it is due.
  const fire = (match) => {
    const due = timers.filter((timer) => !timer.cleared && !timer.ran && match(timer));
    for (const timer of due) { timer.ran = true; timer.callback(); }
    return due.length;
  };
  return {context, document, execute, evaluate, answer, answerLatest, fire, requests, downloads, storage, timers};
}

test('actual classic-script order covers a shortcut already streaming during installation', async () => {
  assert.deepEqual(scripts, ['ui-state.js', 'app.js', 'mac.js', 'performance.js']);
  const page = installation({question: 'Shortcut question'});
  page.execute(scripts[0]); page.execute(scripts[1]);
  page.answer('/health', Response.json({model: 'mock', images: false}));
  await until(() => page.evaluate('busy'));
  assert.ok(page.evaluate('busy'), 'the actual pinned startup began the shortcut request');
  const assistant = page.document.getElementById('chat').lastElementChild;
  page.execute(scripts[2]); page.execute(scripts[3]);
  page.answer('/v1/chat/completions', sseResponse('Partial shortcut reply', false));
  await until(() => !page.evaluate('busy'));
  const messages = page.evaluate('messages');
  assert.equal(messages[1].text, 'Partial shortcut reply');
  assert.match(messages[1].error, /before the answer finished/);
  assert.ok(page.document.getElementById('chat').lastElementChild === assistant, 'the streaming assistant stays attached');
  assert.match(assistant.querySelector('.st-bubble').textContent, /Partial shortcut reply.*before the answer finished/);
  assert.equal(page.evaluate('busy'), null);
  assert.equal(page.document.getElementById('drawer').inert, true);
});

test('whole installation preserves lexical sampling state and deliberate cancellation', async () => {
  const page = installation();
  scripts.forEach(page.execute);
  page.document.getElementById('sampling-btn').click();
  page.document.getElementById('s-max').value = '-1';
  await page.document.getElementById('s-apply').onclick();
  assert.match(page.document.getElementById('s-max').validationMessage, /positive whole number/);
  assert.equal(page.storage.has('strata.sampling'), false);
  page.document.getElementById('s-max').value = '256';
  page.document.getElementById('s-seed').value = '42';
  const applying = page.document.getElementById('s-apply').onclick();
  page.answer('/settings', Response.json({shared: true}));
  const post = page.requests.find((request) => request.resource === '/settings' && request.options.method === 'POST');
  post.resolve(Response.json({shared: false})); await applying;
  assert.equal(page.evaluate('settings.max'), '256');
  assert.equal(page.evaluate('sharedOn'), false);
  assert.equal(page.context.settings, undefined); assert.equal(page.context.sharedOn, undefined);
  page.document.getElementById('input').value = 'Cancel this';
  const sending = page.evaluate('send()');
  page.document.getElementById('stop-btn').click();
  page.answer('/v1/chat/completions', sseResponse('', false)); await sending;
  assert.equal(page.evaluate('messages[1].stopped'), true);
  assert.equal(page.evaluate('messages[1].error'), undefined);
  assert.equal(page.evaluate('messages[1].performanceTiming.finish'), 'stopped');
  assert.equal(page.document.getElementById('send-btn').disabled, false);
});

for (const [choice, clicks, expectedShare] of [['enabled', 1, true], ['disabled', 2, false], ['untouched', 0, true]]) {
  test(`whole sampling Reset retains ${choice} sharing with a delayed settings read`, async () => {
    const page = installation({stored: {sampling: {thinking: 'low', temperature: 0.4, max: '128', show: false}}});
    scripts.forEach(page.execute);
    page.document.getElementById('sampling-btn').click();
    for (let click = 0; click < clicks; click++) page.document.getElementById('s-share').click();
    page.document.getElementById('s-reset').click();
    page.answer('/settings', Response.json({shared: true}));
    await until(() => page.document.getElementById('shared-status').textContent === '');
    assert.equal(page.evaluate('sharedOn'), true, 'the delayed read records the server state');
    assert.equal(page.document.getElementById('s-share').getAttribute('aria-checked'), String(expectedShare));
    const applying = page.document.getElementById('s-apply').onclick();
    const post = page.requests.find((request) => request.resource === '/settings' && request.options.method === 'POST');
    assert.ok(post, 'Apply writes the intended sharing state');
    assert.deepEqual(JSON.parse(post.options.body), {defaults: expectedShare
      ? {reasoning_effort: 'high', temperature: 0.6, top_p: 0.95, top_k: 20} : null});
    post.resolve(Response.json({shared: expectedShare})); await applying;
    assert.deepEqual(JSON.parse(page.storage.get('strata.sampling')),
      {thinking: 'high', temperature: 0.6, top_p: 0.95, top_k: 20, max: '', seed: '', show: true, esp: true});
  });
}

function metricsSample(rows = [], kind = 'mock') {
  return {live: {state: 'idle'}, hardware: {}, engine: {model: 'mock'}, requests: rows,
    performance: {schema: 1, measurement_kind: kind, settings: {model: 'mock', context: 4096, engine: 'mock'},
      resources: {available_bytes: 1024, total_bytes: 2048, swap_used_bytes: 0, new_swap_bytes: null, model_rss_bytes: null, pressure_level: null},
      scope: 'Synthetic timing scope'}};
}

test('whole metrics installation exports and stores only the numeric/settings contract', async () => {
  const secret = 'synthetic-private-value';
  const row = {time: 100, finish: 'stop', measurement_kind: 'mock', prompt_tokens: 8, output_tokens: 2,
    reused: 0, generation_tps: 20, generation_source: 'native', server_first_token_ms: 25, server_duration_ms: 100,
    prompt: secret, reply: secret, file_path: secret, api_key: secret};
  const page = installation({stored: {apikey: secret, chat: [{role: 'user', text: secret, files: [{name: secret}]}]}});
  scripts.forEach(page.execute);
  const metrics = metricsSample([row]);
  Object.assign(metrics, {prompt: secret, reply: secret});
  Object.assign(metrics.performance.settings, {api_key: secret, model_path: secret});
  page.answer('/metrics', Response.json(metrics)); await until(() => page.storage.has('strata.performance.history'));
  page.evaluate(`messages.push({role:'assistant',text:${JSON.stringify(secret)},reasoning:${JSON.stringify(secret)},performanceTiming:{measurement_kind:'mock',first_text_ms:10,total_ms:50,finish:'completed',prompt:${JSON.stringify(secret)}}})`);
  page.document.getElementById('perf-export').click();
  const exported = JSON.parse(await page.downloads.at(-1).text());
  assert.equal(exported.requests[0].server_first_token_ms, 25);
  assert.deepEqual(exported.performance.settings, {model: 'mock', engine: 'mock', context: 4096});
  assert.equal(exported.performance.resources.swap_used_bytes, 0);
  assert.deepEqual(exported.browser_timings, [{measurement_kind: 'mock', first_text_ms: 10, total_ms: 50, finish: 'completed'}]);
  assert.doesNotMatch(JSON.stringify(exported), new RegExp(secret));
  assert.doesNotMatch(page.storage.get('strata.performance.history'), new RegExp(secret));
  assert.match(page.document.getElementById('perf-mode').textContent, /Mock preview/);
  assert.equal(page.document.getElementById('mv-gpu').closest('.metric-card').hidden, true);
  page.evaluate('render(lastMetrics)');
  assert.equal(JSON.parse(page.storage.get('strata.performance.history')).length, 1, 'cached tab renders do not duplicate history');
});

test('whole chat installation restores unavailable chips and keeps newer chat after stale Undo', async () => {
  const page = installation({stored: {chat: [{role: 'user', text: 'Earlier', files: [{name: 'lost.py'}]}]}});
  scripts.forEach(page.execute);
  const chip = page.document.querySelector('.chip--unavailable');
  assert.match(chip.title, /unavailable after reload/);
  assert.match(page.document.querySelector('.attachment-warning').textContent, /Reattach/);
  let pickerOpened = false;
  page.document.getElementById('file').addEventListener('click', () => { pickerOpened = true; });
  page.document.querySelector('.attachment-warning button').click();
  assert.equal(pickerOpened, true);
  page.document.getElementById('new-btn').click();
  const undo = page.document.getElementById('toasts').querySelector('button');
  page.document.getElementById('input').value = 'Newer question';
  page.evaluate("attachments.push({kind:'file',name:'current.py',text:'synthetic file content'})");
  const sending = page.evaluate('send()');
  page.answer('/v1/chat/completions', sseResponse('Reply')); await sending;
  undo.click();
  assert.equal(page.evaluate('messages[0].text'), 'Newer question');
  const saved = JSON.parse(page.storage.get('strata.chat'));
  assert.deepEqual(saved[0].files, [{name: 'current.py'}]);
  page.document.getElementById('export-btn').click();
  assert.match(await page.downloads.at(-1).text(), /File: current\.py\n```\nsynthetic file content\n```/);
  assert.equal(page.evaluate('messages[1].performanceTiming.measurement_kind'), 'unverified');
  assert.match(page.document.querySelector('.message-performance').textContent, /Unverified/);
});

test('whole metrics installation keeps unmeasured values empty and history bounded', async () => {
  const page = installation();
  scripts.forEach(page.execute);
  page.answer('/metrics', Response.json(metricsSample([], 'model')));
  await until(() => page.document.getElementById('perf-mode').textContent.startsWith('Live model'));
  assert.match(page.document.getElementById('perf-mode').textContent, /waiting for first request/);
  for (const id of ['perf-generation', 'perf-first', 'perf-total', 'perf-prompt', 'perf-draft', 'perf-reuse']) {
    assert.equal(page.document.getElementById(id).textContent, '–');
  }
  assert.match(page.document.getElementById('req-body').textContent, /first completed request/);
  const rows = Array.from({length: 205}, (_, index) => ({time: 205 - index, finish: 'stop', output_tokens: index}));
  page.context.sample = metricsSample(rows);
  page.evaluate('lastMetrics = sample; render(sample)');
  const recorded = JSON.parse(page.storage.get('strata.performance.history'));
  assert.equal(recorded.length, 200);
  assert.equal(recorded[0].time, 6); assert.equal(recorded.at(-1).time, 205);
  assert.equal(page.document.getElementById('req-body').children.length, 30);
  page.document.getElementById('perf-export').click();
  assert.equal(JSON.parse(await page.downloads.at(-1).text()).recorded_requests.length, 200);
});

const isPoll = (timer) => timer.callback.name === 'poll';
const isFreshnessCheck = (timer) => timer.callback.name === 'checkFreshness';
const text = (page, id) => page.document.getElementById(id).textContent;
const metricsRequests = (page) => page.requests.filter((request) => request.resource === '/metrics');

test('whole telemetry installation abandons stalled metrics replies and keeps polling', async () => {
  const page = installation();
  scripts.forEach(page.execute);
  const timeout = page.evaluate('STRATA_METRICS_TIMEOUT_MS');
  const deadlines = () => page.timers.filter((timer) => timer.ms === timeout);
  page.answer('/metrics', Response.json(metricsSample()));
  await until(() => text(page, 'pill-text') === 'Ready');
  assert.ok(deadlines().every((timer) => timer.cleared), 'a completed reply releases its deadline');

  page.fire(isPoll);
  const stalled = metricsRequests(page)[1];
  assert.ok(stalled.options.headers, 'the shell request headers are kept');
  assert.equal(stalled.options.signal.aborted, false);
  assert.equal(page.fire((timer) => timer.ms === timeout), 1, 'only the stalled request has a live deadline');
  assert.equal(stalled.options.signal.reason.name, 'TimeoutError', 'the stalled request itself is cancelled');
  await until(() => page.timers.some((timer) => isPoll(timer) && !timer.ran));

  // Headers arrive, but the body never finishes.
  page.fire(isPoll);
  assert.equal(metricsRequests(page).length, 3, 'polling continues after the abandoned reply');
  page.answerLatest('/metrics', new Response(new ReadableStream({start() {}}), {headers: {'Content-Type': 'application/json'}}));
  await until(() => metricsRequests(page)[2].answered);
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(page.timers.some((timer) => isPoll(timer) && !timer.ran), false, 'a stalled body holds the poll until its deadline');
  assert.equal(page.fire((timer) => timer.ms === timeout), 1);
  await until(() => page.timers.some((timer) => isPoll(timer) && !timer.ran));
  page.fire(isPoll);
  assert.equal(metricsRequests(page).length, 4);
  assert.equal(text(page, 'pill-text'), 'Ready', 'two failures inside the freshness window are not yet reported');
});

test('whole telemetry installation shows an expired sample as stale and recovers on the next sample', async () => {
  const page = installation();
  page.context.clock = 1_000_000;
  page.evaluate('Date.now = () => clock');
  scripts.forEach(page.execute);
  page.evaluate("showTab('monitor')");
  const fresh = page.evaluate('STRATA_TELEMETRY_FRESH_MS');
  const sample = metricsSample();
  sample.hardware = {ram_used: 8 * 2 ** 30, ram_total: 16 * 2 ** 30};
  page.answer('/metrics', Response.json(sample));
  await until(() => text(page, 'pill-text') === 'Ready');
  const pill = page.document.getElementById('pill'), monitor = page.document.querySelector('.monitor');
  assert.match(text(page, 'monitor-summary'), /8\.0 \/ 16 GiB system memory in use/);

  page.context.clock += fresh;
  page.fire(isFreshnessCheck);
  assert.equal(text(page, 'pill-text'), 'Ready', 'a sample exactly at the window is still current');
  page.context.clock += 1;
  page.fire(isFreshnessCheck);
  assert.equal(text(page, 'pill-text'), 'Not updating');
  assert.equal(pill.dataset.state, 'stale');
  assert.equal(monitor.dataset.stale, 'true');
  assert.equal(text(page, 'monitor-summary'), `No new readings for over ${fresh / 1000} seconds · readings are stale`);
  assert.match(text(page, 'workspace-model'), / · last seen$/);
  assert.equal(page.document.getElementById('connection-banner').hidden, true, 'an old sample alone is not reported offline');
  await Promise.resolve();
  assert.equal(text(page, 'pill-live'), `No new readings for over ${fresh / 1000} seconds`);
  page.evaluate("showTab('about'); showTab('monitor')");
  assert.equal(text(page, 'pill-text'), 'Not updating', 'a cached tab render keeps the expired state');

  page.fire(isPoll);
  page.answerLatest('/metrics', Response.json(metricsSample()));
  await until(() => text(page, 'pill-text') === 'Ready');
  assert.equal(pill.dataset.state, 'idle');
  assert.equal(monitor.dataset.stale, 'false');
  assert.doesNotMatch(text(page, 'monitor-summary'), /stale/);
  assert.doesNotMatch(text(page, 'workspace-model'), /last seen/);
});

test('whole telemetry installation keeps caller cancellation for metrics requests', async () => {
  const page = installation();
  scripts.forEach(page.execute);
  const timeout = page.evaluate('STRATA_METRICS_TIMEOUT_MS');
  const caller = new AbortController(), reason = new Error('caller stopped');
  page.context.callerSignal = caller.signal;
  const pending = page.evaluate("fetch('/metrics', {signal: callerSignal})");
  const request = page.requests.at(-1), deadline = page.timers.at(-1);
  assert.equal(deadline.ms, timeout);
  caller.abort(reason);
  await assert.rejects(pending, (error) => error === reason);
  assert.equal(request.options.signal.reason, reason, 'the underlying request is cancelled with the caller reason');
  assert.equal(deadline.cleared, true);

  page.context.abortedSignal = AbortSignal.abort();
  await assert.rejects(page.evaluate("fetch('/metrics', {signal: abortedSignal})"), {name: 'AbortError'});
  assert.equal(page.requests.at(-1).options.signal.aborted, true);
  assert.equal(page.timers.at(-1).cleared, true);
});

test('whole installation gives completion streams no metrics deadline', async () => {
  const page = installation();
  scripts.forEach(page.execute);
  const timeout = page.evaluate('STRATA_METRICS_TIMEOUT_MS');
  const deadlines = () => page.timers.filter((timer) => timer.ms === timeout).length;
  const before = deadlines();
  page.document.getElementById('input').value = 'Read this long prompt';
  const sending = page.evaluate('send()');
  const chat = page.requests.find((request) => request.resource === '/v1/chat/completions');
  assert.equal(chat.options.signal, page.evaluate('busy.controller.signal'), 'only the Stop signal reaches the completion');
  page.context.messagesOptions = {method: 'POST', body: '{}'};
  page.evaluate("fetch('/v1/messages', messagesOptions)");
  assert.equal(page.requests.at(-1).options, page.context.messagesOptions, 'Anthropic messages pass through unchanged');
  assert.equal(deadlines(), before, 'no completion request received a deadline');
  page.fire((timer) => timer.ms === timeout);
  assert.equal(chat.options.signal.aborted, false);
  assert.ok(page.evaluate('busy'), 'the completion keeps waiting after every metrics deadline');
  page.answer('/v1/chat/completions', sseResponse('Long reply'));
  await sending;
  assert.equal(page.evaluate('messages[1].text'), 'Long reply');
  assert.equal(page.evaluate('messages[1].error'), undefined);
});

const perfCards = ['perf-generation', 'perf-first', 'perf-total', 'perf-prompt', 'perf-draft', 'perf-reuse'];
const withoutPerformance = (rows = []) => {
  const sample = metricsSample(rows);
  delete sample.performance;
  return sample;
};
const resourceValues = (page) => page.document.getElementById('perf-resources').querySelectorAll('strong').map((value) => value.textContent);

test('whole metrics installation clears model readings when a sample has no performance block, then restores them', async () => {
  const page = installation();
  scripts.forEach(page.execute);
  const row = {time: 100, finish: 'stop', prompt_tokens: 64, output_tokens: 32, reused: 16, generation_tps: 88,
    generation_source: 'native', prompt_tps: 900, server_first_token_ms: 25, server_duration_ms: 400, draft_acceptance_percent: 70};
  const button = page.document.getElementById('perf-export');
  page.answer('/metrics', Response.json(metricsSample([row], 'model')));
  await until(() => text(page, 'perf-generation') === '88.0 tok/s');
  assert.equal(text(page, 'perf-first'), '25 ms');
  assert.match(text(page, 'perf-settings'), /4K context/);
  assert.match(resourceValues(page)[0], /GiB/);

  page.fire(isPoll);
  page.answerLatest('/metrics', Response.json(withoutPerformance([{...row, time: 101}])));
  await until(() => text(page, 'perf-mode') === 'Performance data unavailable');
  for (const id of perfCards) assert.equal(text(page, id), '–', id);
  assert.equal(text(page, 'perf-generation-detail'), 'Not reported by this backend');
  assert.deepEqual(resourceValues(page), Array(5).fill('Not reported'));
  assert.doesNotMatch(text(page, 'perf-settings'), /4K context|mock/);
  const cells = page.document.getElementById('req-body').querySelectorAll('td').map((cell) => cell.textContent);
  assert.deepEqual(cells.slice(1), ['Done', '64', '32', '–', '–', '–', '16'], 'current rows keep counts but no timings');
  assert.match(text(page, 'perf-history'), /^1 recorded request .*no current snapshot/);
  assert.deepEqual(JSON.parse(page.storage.get('strata.performance.history')).map((saved) => saved.time), [100]);
  assert.equal(button.textContent, 'Export history');
  assert.equal(button.disabled, false);
  button.click();
  const history = JSON.parse(await page.downloads.at(-1).text());
  assert.equal(history.performance, null);
  assert.deepEqual(history.requests, []);
  assert.deepEqual(history.recorded_requests.map((saved) => [saved.time, saved.generation_tps]), [[100, 88]]);

  page.fire(isPoll);
  page.answerLatest('/metrics', Response.json(metricsSample([{...row, time: 102, generation_tps: 90}], 'model')));
  await until(() => text(page, 'perf-generation') === '90.0 tok/s');
  assert.match(text(page, 'perf-mode'), /^Live model/);
  assert.equal(text(page, 'perf-generation-detail'), 'Engine timing · last request');
  assert.match(resourceValues(page)[0], /GiB/);
  assert.match(text(page, 'perf-settings'), /4K context/);
  assert.equal(button.textContent, 'Export metrics');
  button.click();
  const current = JSON.parse(await page.downloads.at(-1).text());
  assert.equal(current.performance.measurement_kind, 'model');
  assert.deepEqual(current.requests.map((saved) => saved.time), [102]);
  assert.deepEqual(current.recorded_requests.map((saved) => saved.time), [100, 102]);
});

test('whole metrics installation disables export when a backend reports neither a snapshot nor history', async () => {
  const page = installation();
  scripts.forEach(page.execute);
  const button = page.document.getElementById('perf-export');
  page.answer('/metrics', Response.json(withoutPerformance()));
  await until(() => text(page, 'perf-mode') === 'Performance data unavailable');
  assert.equal(button.textContent, 'Export history');
  assert.equal(button.disabled, true);
  assert.match(text(page, 'req-body'), /first completed request/);
  assert.equal(page.storage.has('strata.performance.history'), false);

  page.fire(isPoll);
  page.answerLatest('/metrics', Response.json(metricsSample([], 'model')));
  await until(() => text(page, 'perf-mode').startsWith('Live model'));
  assert.equal(button.textContent, 'Export metrics');
  assert.equal(button.disabled, false);
  assert.equal(text(page, 'perf-generation-detail'), 'No generation measurement yet');
  button.click();
  assert.equal(JSON.parse(await page.downloads.at(-1).text()).performance.measurement_kind, 'model');
});
