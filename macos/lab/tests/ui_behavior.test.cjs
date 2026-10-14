const test = require('node:test');
const assert = require('node:assert/strict');
const ui = require('../web/ui-state.js');

const sse = (records) => new Response(records.join(''), {headers: {'Content-Type': 'text/event-stream'}});
const chunk = (value) => `data: ${JSON.stringify(value)}\n\n`;

test('Undo restores an untouched cleared conversation', () => {
  const cleared = [], previous = [{text: 'Earlier chat'}];
  let current = cleared;
  const undo = new ui.ChatUndo(cleared);
  assert.equal(undo.restore(current, false, () => { current = previous; }), true);
  assert.equal(current, previous);
});

test('Undo cannot replace a newer message, another chat, or an active reply', () => {
  for (const [current, busy] of [[[{text: 'New message'}], false], [[], false], [[], true]]) {
    const cleared = [], undo = new ui.ChatUndo(cleared);
    if (busy) current.splice(0);
    let replaced = false;
    assert.equal(undo.restore(current, busy, () => { replaced = true; }), false);
    assert.equal(replaced, false);
  }
  const cleared = [], undo = new ui.ChatUndo(cleared);
  cleared.push({text: 'New message in the same array'});
  assert.equal(undo.restore(cleared, false, () => assert.fail('replaced newer chat')), false);
});

test('a partial chat stream without a terminal record rejects with its text retained', async () => {
  const response = ui.completionResponse(sse([chunk({choices: [{delta: {content: 'Partial answer'}}]})]));
  const reader = response.body.getReader();
  const first = await reader.read();
  assert.match(new TextDecoder().decode(first.value), /Partial answer/);
  await assert.rejects(reader.read(), /before the answer finished/i);
});

test('DONE, finish_reason, and explicit server errors terminate streams', async () => {
  for (const terminal of ['data: [DONE]\n\n', chunk({choices: [{delta: {}, finish_reason: 'length'}]}), chunk({error: {message: 'server error'}})]) {
    const response = ui.completionResponse(sse([chunk({choices: [{delta: {content: 'Answer'}}]}), terminal]));
    assert.match(await response.text(), /Answer/);
  }
});

test('terminal records split across byte chunks are recognized', async () => {
  const bytes = new TextEncoder().encode('data: [DONE]\r\n\r\n');
  let index = 0;
  const original = new Response(new ReadableStream({pull(controller) {
    if (index === bytes.length) controller.close();
    else controller.enqueue(bytes.slice(index, ++index));
  }}), {headers: {'Content-Type': 'text/event-stream'}});
  assert.equal(await ui.completionResponse(original).text(), 'data: [DONE]\r\n\r\n');
});

test('deliberate cancellation remains an AbortError', async () => {
  const abort = new AbortController();
  abort.abort();
  await assert.rejects(ui.completionResponse(sse([]), abort.signal).text(), {name: 'AbortError'});
});

test('failed HTTP responses retain their original error body', async () => {
  const original = new Response('{"error":{"message":"API key needed"}}', {status: 401});
  assert.equal(ui.completionResponse(original), original);
  assert.equal(original.status, 401);
});

test('restored attachments are identified without altering their retention', () => {
  const files = [{name: 'lost.py'}, {name: 'present.py', text: ''}];
  assert.deepEqual(ui.unavailableFiles([{role: 'user', files}]), [{name: 'lost.py'}]);
  assert.deepEqual(files, [{name: 'lost.py'}, {name: 'present.py', text: ''}]);
});

test('Markdown export includes current file text and identifies unavailable files', () => {
  const markdown = ui.chatMarkdown([{role: 'user', text: 'Review this', files: [
    {name: 'code.py', text: 'print(````)'}, {name: 'old.py'},
  ]}, {role: 'assistant', text: 'Reply', reasoning: 'Thoughts'}], 'Local model');
  assert.match(markdown, /File: code\.py\n`````\nprint\(````\)\n`````/);
  assert.match(markdown, /old\.py.*unavailable/i);
  assert.match(markdown, /Thinking/);
  assert.match(markdown, /## Local model/);
});

test('numeric settings accept only empty or positive safe integers', () => {
  for (const value of ['', '1', '1024', '1e3']) assert.equal(ui.integerError(value, 'Max tokens'), '');
  for (const value of ['-1', '0', '1.5', 'NaN', 'Infinity', '9007199254740992']) {
    assert.match(ui.integerError(value, 'Max tokens'), /positive whole number/i);
  }
});

test('late shared settings update the server state without replacing a user edit', async () => {
  const state = new ui.SharedSettings();
  let resolve, control = false, server;
  const pending = state.load(() => new Promise((done) => { resolve = done; }), (value, untouched) => {
    server = value;
    if (untouched) control = value;
  });
  assert.equal(control, false, 'the drawer starts with sharing disabled');
  control = true;
  state.edited();
  resolve(false);
  await pending;
  assert.equal(server, false);
  assert.equal(control, true);
});

test('old shared-setting responses cannot affect a reopened drawer', async () => {
  const state = new ui.SharedSettings();
  let resolve, value;
  const old = state.load(() => new Promise((done) => { resolve = done; }), (next) => { value = next; });
  state.invalidate();
  await state.load(async () => true, (next) => { value = next; });
  resolve(false);
  await old;
  assert.equal(value, true);
});

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const pinned = fs.readFileSync(path.join(__dirname, '../vendor/Strata-macOS/serve/web/app.js'), 'utf8');
const maintained = fs.readFileSync(path.join(__dirname, '../web/mac.js'), 'utf8');
const fragment = (source, start, end) => {
  assert.ok(source.includes(start) && source.includes(end), 'pinned compatibility markers changed');
  return source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
};
const install = (name, next, context, args = '') => vm.runInContext(
  fragment(maintained, `function ${name}(`, `function ${next}(`) + `${name}(${args});`, context);

test('the actual New-chat compatibility hook prevents the reproduced message loss', () => {
  const run = (patched) => {
    const nodes = {}, get = (id) => { nodes[id] ||= {}; return nodes[id]; };
    let action;
    const context = vm.createContext({$: get, messages: [{role: 'user', text: 'Earlier'}], busy: null,
      saveChat() {}, renderChat() {}, toast(kind, title, text, ms, undo) { if (undo) action = undo; },
      StrataChatUndo: ui.ChatUndo});
    vm.runInContext(fragment(pinned, '$("new-btn").onclick', '$("export-btn").onclick'), context);
    if (patched) install('installUndo', 'installAssistantRendering', context);
    get('new-btn').onclick();
    context.messages.push({role: 'user', text: 'Newer'});
    action.run();
    return context.messages[0].text;
  };
  assert.equal(run(false), 'Earlier', 'reproduces the pinned behavior before the fix');
  assert.equal(run(true), 'Newer');
});

test('the actual export hook preserves file content that the pinned export drops', async () => {
  const run = async (patched) => {
    let exported;
    const nodes = {}, get = (id) => { nodes[id] ||= {}; return nodes[id]; };
    const context = vm.createContext({$: get, messages: [{role: 'user', text: 'Review', files: [{name: 'code.py', text: 'file_secret_example'}]}],
      health: {model: 'mock'}, toast() {}, Blob, Date, setTimeout() {},
      document: {createElement: () => ({click() {}})},
      URL: {createObjectURL(blob) { exported = blob; return 'blob:test'; }, revokeObjectURL() {}},
      strataChatMarkdown: ui.chatMarkdown});
    const source = patched ? maintained : pinned;
    vm.runInContext(fragment(source, '$("export-btn").onclick', patched ? 'let attachmentWarningChat' : '// pictures and text files'), context);
    get('export-btn').onclick();
    return exported.text();
  };
  assert.doesNotMatch(await run(false), /file_secret_example/);
  assert.match(await run(true), /file_secret_example/);
});

test('the actual renderer keeps partial answer text beside its error', () => {
  const warnings = [], bubble = {text: '', querySelectorAll: () => [], appendChild(value) { warnings.push(value); }};
  const element = {querySelector: () => bubble};
  const context = vm.createContext({updateAssistant(el, message) { bubble.text = message.error || message.text; },
    document: {createElement: () => ({})}});
  install('installAssistantRendering', 'installChatActions', context);
  context.updateAssistant(element, {text: 'Partial answer', error: 'Connection interrupted'}, false);
  assert.equal(bubble.text, 'Partial answer');
  assert.equal(warnings[0].textContent, 'Connection interrupted');
});

test('the actual Apply hook rejects invalid values and honors sharing before GET completes', async () => {
  const values = {'s-temp': '0.6', 's-topp': '0.95', 's-topk': '20', 's-max': '-1', 's-seed': '1.5'};
  const nodes = Object.fromEntries(Object.entries(values).map(([id, value]) => [id, {value, error: '',
    setCustomValidity(error) { this.error = error; }, reportValidity() { return !this.error; }}]));
  for (const id of ['s-show', 's-esp', 's-share']) nodes[id] = {getAttribute: () => id === 's-share' ? 'false' : 'true'};
  nodes['s-apply'] = {};
  let saved = false, shared;
  const context = vm.createContext({$: (id) => nodes[id], strataIntegerError: ui.integerError,
    thinking: [{dataset: {v: 'high'}, getAttribute: () => 'true'}], settings: {},
    store: {set() { saved = true; }}, isSharingKnown: () => false, sharedOn: false,
    openDrawer() {}, saveShared: async (value) => { shared = value; }, toast() {}});
  vm.runInContext(fragment(maintained, '$("s-apply").onclick = async', 'for (const id of ["s-max", "s-seed"])'), context);
  await nodes['s-apply'].onclick();
  assert.equal(saved, false);
  nodes['s-max'].value = '';
  await nodes['s-apply'].onclick();
  assert.equal(saved, false);
  nodes['s-seed'].value = '';
  await nodes['s-apply'].onclick();
  assert.equal(saved, true);
  assert.equal(shared, false, 'explicitly disables sharing even while GET is pending');
});

const stateSource = fs.readFileSync(path.join(__dirname, '../web/ui-state.js'), 'utf8');

test('the installed fetch guard is restricted to chat completion POST streams', async () => {
  const context = vm.createContext({TextDecoder, DOMException, ReadableStream, Response,
    window: {fetch: async () => sse([chunk({choices: [{delta: {content: 'Partial'}}]})]), AbortController, setTimeout, clearTimeout}});
  vm.runInContext(stateSource, context);
  assert.match(await (await context.window.fetch('/metrics')).text(), /Partial/);
  assert.match(await (await context.window.fetch('/v1/chat/completions', {method: 'GET'})).text(), /Partial/);
  await assert.rejects((await context.window.fetch('/v1/chat/completions', {method: 'POST'})).text(), /before the answer finished/i);
});

test('the metrics deadline returns the shell status, headers and whole body, then clears itself', async () => {
  const timers = [], seen = [];
  const context = vm.createContext({DOMException, Response, window: {AbortController,
    fetch: async (resource, options) => {
      seen.push(options);
      return new Response('{"error":{"message":"API key needed"}}', {status: 401, headers: {'X-Shell': 'pinned'}});
    },
    setTimeout: (callback, ms) => timers.push({callback, ms}),
    clearTimeout: (id) => { timers[id - 1].cleared = true; }}});
  vm.runInContext(stateSource, context);
  const response = await context.window.fetch('/metrics', {headers: {Authorization: 'Bearer synthetic'}});
  assert.equal(response.status, 401);
  assert.equal(response.headers.get('X-Shell'), 'pinned');
  assert.match(await response.text(), /API key needed/);
  assert.deepEqual(seen[0].headers, {Authorization: 'Bearer synthetic'});
  assert.equal(seen[0].signal.aborted, false);
  assert.deepEqual(timers.map(({ms, cleared}) => ({ms, cleared})), [{ms: ui.METRICS_TIMEOUT_MS, cleared: true}]);
});

test('the pinned send path marks a truncated reply failed only after the compatibility fix', async () => {
  const run = async (patched) => {
    const nodes = {input: {value: 'Explain this'}, chat: {lastElementChild: {}}};
    const context = vm.createContext({$: (id) => nodes[id], messages: [], attachments: [], busy: null,
      health: {model: 'mock'}, settings: {thinking: 'none', temperature: 0, max: '', seed: ''},
      renderAttachments() {}, autosize() {}, renderChat() {}, AbortController, performance: {now: () => 100},
      headers: () => ({}), apiMessages: () => [{role: 'user', content: 'Explain this'}], projectionLoaded: () => false,
      setBusy() {}, TextDecoder, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
      updateAssistant() {}, saveChat() {}, scrollDown() {}, fmt: String, toast() {},
      fetch: async () => {
        const response = sse([chunk({choices: [{delta: {content: 'Partial answer'}}]})]);
        return patched ? ui.completionResponse(response) : response;
      }});
    vm.runInContext(fragment(pinned, 'async function send()', '$("composer").onsubmit'), context);
    await context.send();
    return context.messages[1];
  };
  assert.equal((await run(false)).error, undefined);
  const failed = await run(true);
  assert.equal(failed.text, 'Partial answer');
  assert.match(failed.error, /before the answer finished/i);
});

test('the pinned save boundary still stores attachment names without contents', () => {
  let saved;
  const context = vm.createContext({messages: [{role: 'user', text: 'Review', files: [{name: 'code.py', text: 'file contents'}]}],
    store: {set(key, value) { saved = value; }}});
  vm.runInContext(fragment(pinned, 'function saveChat()', 'function timeStr(t)'), context);
  context.saveChat();
  assert.equal(saved[0].files[0].name, 'code.py');
  assert.equal(saved[0].files[0].text, undefined);
});

test('installing the maintained UI during a shortcut request keeps its reply visible', async () => {
  const chat = {children: [], querySelectorAll() { return this.children.slice(); },
    appendChild(element) { this.children.push(element); }, get lastElementChild() { return this.children.at(-1); }};
  const nodes = {input: {value: 'Shortcut question'}, chat, 'chat-empty': {}};
  let completeFetch;
  const context = vm.createContext({$: (id) => nodes[id], messages: [], attachments: [], busy: null,
    health: {model: 'mock'}, settings: {thinking: 'none', temperature: 0, max: '', seed: ''},
    msgEl(message) { return {text: message.text, remove() { chat.children.splice(chat.children.indexOf(this), 1); }}; },
    document: {querySelectorAll: () => []}, strataUnavailableFiles: ui.unavailableFiles,
    renderAttachments() {}, autosize() {}, resizeInput() {}, AbortController, performance: {now: () => 100},
    headers: () => ({}), apiMessages: () => [{role: 'user', content: 'Shortcut question'}], projectionLoaded: () => false,
    setBusy() {}, TextDecoder, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
    updateAssistant(element, message) { element.text = message.text; }, saveChat() {}, scrollDown() {}, fmt: String, toast() {},
    fetch: () => new Promise((resolve) => { completeFetch = resolve; })});
  vm.runInContext(fragment(pinned, 'function renderChat()', 'function nearBottom()'), context);
  vm.runInContext(fragment(pinned, 'async function send()', '$("composer").onsubmit'), context);
  const sending = context.send(), captured = chat.lastElementChild;
  assert.ok(context.busy);
  vm.runInContext(fragment(maintained, 'function decorateUnavailableAttachments(', 'function installSharedSettings(') + 'installChatRestore(resizeInput);', context);
  completeFetch(sse([chunk({choices: [{delta: {content: 'Actual reply'}}]}), 'data: [DONE]\n\n']));
  await sending;
  assert.equal(context.messages[1].text, 'Actual reply');
  assert.equal(chat.lastElementChild, captured, 'the active reply element must stay attached during installation');
  assert.equal(chat.lastElementChild.text, 'Actual reply');
});

test('sharing and Apply retain the pinned global lexical state across classic scripts', async () => {
  const nodes = {'s-share': {checked: 'false', getAttribute() { return this.checked; },
    setAttribute(name, value) { this.checked = value; }}, 'shared-status': {}, 's-apply': {}};
  for (const [id, value] of [['s-temp', '0.4'], ['s-topp', '0.9'], ['s-topk', '12'], ['s-max', '256'], ['s-seed', '42']]) {
    nodes[id] = {value, setCustomValidity() {}, reportValidity: () => true};
  }
  for (const id of ['s-show', 's-esp']) nodes[id] = {getAttribute: () => 'true'};
  let posted;
  const context = vm.createContext({$: (id) => nodes[id], window: {},
    store: {get: (key, fallback) => fallback, set() {}}, headers: () => ({}),
    fetch: async () => ({ok: true, json: async () => ({shared: true})}),
    sharing: new ui.SharedSettings(), sharingKnown: false, isSharingKnown: () => context.sharingKnown,
    thinking: [{dataset: {v: 'low'}, getAttribute: () => 'true'}],
    strataIntegerError: ui.integerError, openDrawer() {}, toast() {},
    saveShared: async (on, settings) => { posted = {on, settings}; }});
  // Use the actual shell declarations: global `let` state is not window state.
  vm.runInContext(fragment(pinned, 'const DEFAULTS =', 'function saveChat()'), context);
  vm.runInContext(fragment(pinned, 'let sharedOn = false;', 'function sharedDefaults(s)'), context);
  vm.runInContext(fragment(maintained, 'loadShared = () =>', 'return {known:'), context);
  await context.loadShared();
  assert.equal(vm.runInContext('sharedOn', context), true);
  assert.equal(context.sharedOn, undefined);
  assert.equal(context.window.sharedOn, undefined);
  vm.runInContext(fragment(maintained, '$("s-apply").onclick = async', 'for (const id of ["s-max", "s-seed"])'), context);
  await nodes['s-apply'].onclick();
  assert.equal(vm.runInContext('settings.thinking', context), 'low');
  assert.equal(vm.runInContext('settings.max', context), '256');
  assert.equal(vm.runInContext('settings.seed', context), '42');
  assert.equal(posted.settings, vm.runInContext('settings', context));
  assert.equal(context.settings, undefined);
  assert.equal(context.window.settings, undefined);
});
