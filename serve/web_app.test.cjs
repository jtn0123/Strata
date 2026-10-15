// serve/web_app.test.cjs - the web app's escaping and Markdown, run as the page runs them: model text becomes HTML
// here (bubble.innerHTML), so nothing it says may come out as a tag, an attribute or a link of its own.
// node --test serve/*.test.cjs.  The functions are cut out of app.js by their markers, as the lab's tests do
// (macos/lab/tests/ui_behavior.test.cjs), so the page needs no change to be tested.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'web/app.js'), 'utf8');
const fragment = (start, end) => {
  const from = source.indexOf(start), to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `app.js markers changed: ${start} ... ${end}`);
  return source.slice(from, to);
};
const context = vm.createContext({});
vm.runInContext(fragment('const SPRITE = ', 'const fmt = '), context);
vm.runInContext(fragment('function inline(', '// ------------------------------------------------------------------ Chat'), context);
const {esc, markdown} = vm.runInContext('({esc, markdown})', context);

// What the renderer may write, and nothing else: its own tags and attributes, links only to http(s).
const TAGS = new Set(['p', 'br', 'strong', 'em', 'a', 'code', 'pre', 'div', 'span', 'button', 'svg', 'use', 'h3',
  'h4', 'hr', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'ul', 'ol', 'li']);
const ATTRS = new Set(['class', 'href', 'target', 'rel', 'aria-hidden', 'aria-label', 'data-code-copy']);
function assertSafe(html, input) {
  for (const [, name, attrs] of html.matchAll(/<\/?([^\s>/]+)([^>]*)>/g)) {
    assert.ok(TAGS.has(name), `<${name}> from ${JSON.stringify(input)}: ${html}`);
    const rest = attrs.replace(/\s([a-z-]+)(?:="([^"<>]*)")?/g, (all, attr, value) => {
      assert.ok(ATTRS.has(attr), `${attr}= from ${JSON.stringify(input)}: ${html}`);
      if (attr === 'href') assert.match(value, name === 'use' ? /^web\/sprite\.svg#i-[a-z-]+$/   // its own icons
                                          : /^https?:\/\/[^\s"'<>]+$/, `href from ${JSON.stringify(input)}`);
      return '';
    });
    assert.ok(/^\s*\/?$/.test(rest), `stray markup ${JSON.stringify(rest)} from ${JSON.stringify(input)}: ${html}`);
  }
  assert.ok(!/<(?![a-z/])/.test(html), `a bare < from ${JSON.stringify(input)}: ${html}`);
}

const HOSTILE = [
  '<script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '**<img src=x onerror=alert(1)>**',
  '*<svg onload=alert(1)>*',
  '`<b>` and `</code><script>x</script>`',
  '[click](javascript:alert(1))',
  '[click](data:text/html,<script>alert(1)</script>)',
  '[a" onclick="alert(1)](https://example.com)',
  '[x](https://example.com/"onmouseover="alert(1))',
  "[x](https://example.com/'><script>alert(1)</script>)",
  '<a href="javascript:alert(1)">x</a>',
  '# <iframe src=x>',
  '> <style>*{display:none}</style>',
  '- <object data=x>\n- two',
  '| <i>a</i> | b |\n|---|---|\n| <script>c</script> | d |',
  '```<img src=x onerror=alert(1)>\n<script>alert(1)</script>\n```',
  '```html\n</code></pre><script>alert(1)</script>\n```',
  '```\nnot closed <script>',
  '&lt;script&gt; &amp; &#60;b&#62;',
  '\u00000\u0000<script>',
];

test('esc turns every character HTML gives meaning to into an entity', () => {
  assert.equal(esc(`<a href="x" title='y'>&</a>`), '&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;');
  assert.equal(esc(5), '5');
});

test('no hostile text becomes a tag, an attribute or a non-http link', () => {
  for (const input of HOSTILE) {
    const html = markdown(input);
    assertSafe(html, input);
    assert.doesNotMatch(html, /<(script|img|iframe|style|object)/i, input);     // as text they are fine
  }
});

test('the model text is shown as written', () => {
  assert.equal(markdown('<script>alert(1)</script>'), '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>');
  assert.equal(markdown('Tom & Jerry'), '<p>Tom &amp; Jerry</p>');
  // entities are text too: the reader sees "&lt;", not "<"
  assert.equal(markdown('&lt;b&gt;'), '<p>&amp;lt;b&amp;gt;</p>');
  assert.equal(markdown('**<b>bold</b>**'), '<p><strong>&lt;b&gt;bold&lt;/b&gt;</strong></p>');
  assert.equal(markdown('`<b>`'), '<p><code class="inline">&lt;b&gt;</code></p>');
});

test('links: http(s) only, quotes kept inside the attribute', () => {
  assert.equal(markdown('[docs](https://example.com/a?b=1&c=2)'),
    '<p><a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">docs</a></p>');
  assert.equal(markdown('[x](javascript:alert(1))'), '<p>[x](javascript:alert(1))</p>');
  assert.match(markdown('[x](https://example.com/"onmouseover="alert(1))'),
    /href="https:\/\/example\.com\/&quot;onmouseover=&quot;alert\(1"/);
});

test('code blocks: escaped, labelled, and closed only by a fence on its own line', () => {
  const html = markdown('```html\n<p class="x">a</p>\n```');
  assert.match(html, /<span>html<\/span>/);
  assert.match(html, /<pre><code>&lt;p class=&quot;x&quot;&gt;a&lt;\/p&gt;<\/code><\/pre>/);
  // a fence inside a line, or indented with text after it, is part of the code
  const inner = markdown('```md\nUse ``` to fence.\n  ```not the end\n```\nafter');
  assert.match(inner, /<code>Use ``` to fence\.\n {2}```not the end<\/code>/);
  assert.match(inner, /<p>after<\/p>$/);
  // still streaming: no closing fence yet, the rest is code
  assert.match(markdown('Here:\n```py\nprint("<hi>")'), /<code>print\(&quot;&lt;hi&gt;&quot;\)<\/code><\/pre><\/div>$/);
  // the language label is the model's text as well
  assert.match(markdown('```<img src=x>\ncode\n```'), /<span>&lt;img src=x&gt;<\/span>/);
});

test('Markdown structure still renders', () => {
  assert.equal(markdown('# Title\n\nSome *em* and **strong**.'),
    '<h3>Title</h3><p>Some <em>em</em> and <strong>strong</strong>.</p>');
  assert.equal(markdown('- a\n- b\n\n1. c'), '<ul><li>a</li><li>b</li></ul><ol><li>c</li></ol>');
  assert.equal(markdown('| a | b |\n|---|---|\n| 1 | 2 |'),
    '<table><thead><tr><th>a</th><th>b</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>');
  assert.equal(markdown('> quoted\n\n---'), '<blockquote>quoted</blockquote><hr>');
});

test('the tabs are one Tab stop; the arrow keys, Home and End move between them', () => {
  let focused = null;
  const buttons = ['chat', 'monitor', 'about'].map((name) => ({dataset: {tab: name}, attrs: {}, tabIndex: 0,
    setAttribute(k, v) { this.attrs[k] = v; }, focus() { focused = this; }}));
  const nodes = {};
  const page = vm.createContext({document: {querySelectorAll: () => buttons}, $: (id) => (nodes[id] ||= {focus() {}}),
    location: {hash: '', pathname: '/'}, history: {replaceState() {}}, window: {addEventListener() {}},
    loadMcp() {}, loadConfig() {}, render() {}, lastMetrics: null});
  vm.runInContext(fragment('let tab = "chat";', '// ------------------------------------------------------------------ server access'), page);
  const press = (i, key) => { let prevented = false; buttons[i].onkeydown({key, preventDefault() { prevented = true; }}); return prevented; };
  const state = () => buttons.map((b) => `${b.attrs['aria-selected']}/${b.tabIndex}`).join(' ');
  page.showTab('chat');
  assert.equal(state(), 'true/0 false/-1 false/-1');
  for (const [from, key, to] of [[0, 'ArrowRight', 1], [1, 'ArrowRight', 2], [2, 'ArrowRight', 0], [0, 'ArrowLeft', 2],
                                 [2, 'Home', 0], [0, 'End', 2], [2, 'ArrowLeft', 1]]) {
    assert.equal(press(from, key), true, key);
    assert.equal(focused, buttons[to], `${key} from ${from}`);
    assert.equal(state(), buttons.map((b, i) => (i === to ? 'true/0' : 'false/-1')).join(' '));
    assert.equal(nodes[`view-${buttons[to].dataset.tab}`].hidden, false);
  }
  focused = null;
  assert.equal(press(1, 'a'), false);                                         // other keys are the browser's
  assert.equal(focused, null);
});

test('a finished answer is announced once, outside the views (a hidden tab is not read)', () => {
  const said = {textContent: 'earlier'}, timers = [];
  const page = vm.createContext({$: () => said, setTimeout: (f) => timers.push(f)});
  vm.runInContext(fragment('function announce(', 'function renderChat('), page);
  page.announce('Answer: hello');
  assert.equal(said.textContent, '');                                          // emptied: the same words are heard again
  timers.forEach((f) => f());
  assert.equal(said.textContent, 'Answer: hello');
  const html = fs.readFileSync(path.join(__dirname, 'web/index.html'), 'utf8');
  const region = html.match(/<div class="sr-only" id="chat-said"([^>]*)>/);
  assert.ok(region && /aria-live="polite"/.test(region[1]), 'the live region');
  assert.ok(html.indexOf('id="chat-said"') > html.indexOf('</main>'), 'outside the views');
  assert.doesNotMatch(html.match(/<div class="chat" id="chat"[^>]*>/)[0], /aria-live|role="log"/);   // rebuilt as it streams
});
