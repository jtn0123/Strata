# Bug and polish pass after PR 3

Baseline: merged commit `baf12dd7cccc994eb16492d98cdee33baf80f7a0`. Runtime,
benchmark and UI agents investigated independently, then cross-reviewed each
other's integration boundaries. Findings below have reproductions or direct
runtime evidence; cosmetic preferences and uncertain candidates are separate.

## Confirmed findings

All entries below are corrected in this pass. Impact describes the old behavior;
effort describes the scope of its correction. Tests use synthetic content.

| ID | Problem in ordinary terms | Impact | Effort | Evidence and correction |
| --- | --- | --- | --- | --- |
| B01 | Stop did not recognize the maintained profile launchers. | High | Low | Recorded `runtime_profiles.py` supervisors were rejected. Accept both maintained entry points; preserve PID, creation-time and workspace ownership checks. |
| B02 | Stopping ordinary startup could leave a model or API child running. | High | Medium | Real SIGINT/SIGTERM/SIGHUP at native/API creation failed against the baseline. Defer stops until ownership is assigned, then clean up both children and the guard; restore caller handlers. |
| B03 | Older documented benchmark commands could also orphan their child. | High | Medium | Tiny real children survived cancellation before correction. Both drivers now use the shared cleanup/deferred-publication helpers. |
| B04 | Native failures escaped the supported API error path. | High | Medium | HTTP failure, malformed stream, reset and early EOF now become `EngineDied`, structured API errors and failed history for OpenAI/Anthropic, streaming/nonstreaming. |
| B05 | A failed request could still acquire a plausible speed reading. | Medium | Medium | Transport failures must not receive native or synthesized decode TPS. Coverage includes a detokenization failure outside the native generator, not just errors raised inside it. Partial text remains available. |
| B06 | Two simultaneous model checks could collide on one temporary file. | Medium | Low | The shared `.tmp` publication reproduced `FileNotFoundError`. Unique temporary files and atomic replacement remove that collision. |
| B07 | Preflight missed an already-running parent engine. | High | Low | A native process named `strata` was ignored. Detect both supported engines before starting another; do not signal either process. |
| B08 | A benchmark could pass despite exceeding its swap limit at shutdown. | High | Low | A campaign with live swap zero and final swap 3 GiB passed a 2 GiB budget. The final sample now enforces the same configured threshold. |
| B09 | Invalid native token counts could enter speed comparisons. | High | Low | Negative/mismatched counts were accepted. Validate actual emitted IDs, output cap and prompt-read-plus-cache conservation in the shared reader/editing/cache paths. |
| B10 | A cache result could qualify without a complete answer or cache reuse. | High | Medium | Require a normal EOS, positive timing metrics and a real cache hit for the cache arm. Supply tokenizer-derived stop IDs in both actual engine constructors; an integration regression caught and corrected the first implementation's missing setup. |
| B11 | Cache campaigns could pass with failed monitoring or an unclosed child. | High | Low | Full-caller fixtures previously passed failed guard/monitor/exit receipts. These now fail the campaign. |
| B12 | Preparation failures in documented drivers lost useful receipts or identity checks. | Medium | Medium | Corrupted model/replaced engine fixtures fail before native execution and preserve failed preparation receipts. Both commands verify identities before launch and again afterward. |
| B13 | An old Undo could overwrite a newer conversation. | High | Low | Execute the actual old and maintained toast hooks: restoration requires the original empty chat identity and no active reply. |
| B14 | A dropped chat connection looked like a successful answer. | High | Medium | Execute the pinned send path with a truncated SSE stream: EOF now requires an explicit terminal record. Partial answer and warning remain visible; Stop remains cancellation. |
| B15 | Reloaded file names implied the model still had their contents. | Medium | Low | Reload intentionally saves names only. Mark restored files unavailable, offer Reattach and warn on the first follow-up; do not persist contents. |
| B16 | Chat export omitted attached text. | Medium | Low | Actual old export dropped a synthetic attached file. Export available file text with safe fences and label unavailable restored files. |
| B17 | Invalid numeric settings could be saved. | Medium | Low | Browser checks with max `-1` and seed `1.5` keep the drawer open and saved values unchanged. Accept only empty or positive safe whole numbers. |
| B18 | A delayed settings read could replace the user's sharing choice. | Medium | Medium | Revision/request tracking ignores old drawer responses and preserves edits made during an active GET. |
| B19 | Apply before that read completed could leave sharing enabled unexpectedly. | Medium | Low | Actual Apply hook explicitly writes the selected sharing state when the old server state is unknown. |
| B20 | Dark-mode user messages were difficult to read. | Medium | Low | Actual computed contrast improved from 1.219:1 to 11.410:1 by using the theme's text color. |
| B21 | Wide replies/files pushed Send outside a narrow screen. | Medium | Low | The 320 px fixture produced a 487 px document before correction. Remove the view's intrinsic flex minimum and contain tables locally; final document width is 320 px and Send ends at 289 px. |
| B22 | A quick-link chat could start before the UI layer loaded and leave its answer invisible. | High | Low | Actual pinned `send()` plus maintained initialization reproduced stored text with a detached visible message element. Preserve the active sender's DOM during startup; normal subsequent renders retain the compatibility fixes. |

Keyboard/touch polish also adds one tab stop and Arrow/Home/End selection for
Thinking, 44 px narrow/coarse reply/code-copy/removal/close/radio targets and
60 by 44 px switch hit areas around the existing visible track. The authentication
banner opens About and focuses the API-key field. Zero-request Monitor wording is
clearer. Existing visible labels were already associated with fields; explicit
ARIA names are polish, not a claim that the old controls lacked labels.

## Validation and limits

Local validation passes **281 load-free Python tests, 12 benchmark termination
tests, one launcher termination test containing six signal/stage cases, two
socket/restart tests, five campaign-protocol tests and 27 JavaScript tests**.
JavaScript/launcher syntax checks and `git diff --check` pass. These are 328
test methods/cases across the listed suites; nested signal subcases are not
added again to that total.

The maintained offline inventory includes every new load-free Python test. Real
termination and socket checks run separately; the offline gate still denies real
sockets/native execution. Both JavaScript suites execute in CI, including actual
pinned-before/maintained-after chat hooks. Clean-export/hosted results are recorded
separately in the pull request; local passing tests do not imply hosted success.

The real browser uses a local mock engine and disposable synthetic chats. Layouts
at 320, 390 and 1280 px fit the viewport. At 320 px a wide table scrolls its 414 px
contents inside a 246 px container. Real mock completion, synthetic truncated SSE,
deliberate Stop, numeric validation, Thinking keyboard controls, restored-file
notice, switch alignment, light/dark styling and authentication navigation were
checked. Before/after screenshots and detailed receipts remain local and ignored.

No real model, GPU workload or native build ran for this pass. No new TPS gain is
claimed, and current model bytes/default inference settings are unchanged. Prior
measured performance remains the speed evidence. Desktop viewport resizing does
not establish physical mobile-keyboard behavior or VoiceOver acceptance.

## Deferred findings and revisit conditions

| ID | Evidence | Decision / next requirement |
| --- | --- | --- |
| D01 | A parked Q2 campaign captures initial engine pins but a mocked caller accepted captured runs from different binaries. | Before reusing that campaign, compare each captured run against its initial engine pin. Do not rerun the parked model experiment unchanged. |
| D02 | The tuning helper can accept uniformly omitted declared workload lengths in malformed receipts. | Harden receipt identity before reusing this helper with external/older captures; evidence is malformed-input handling, not a demonstrated gain or a reason to rerun tuning. |

These are preserved separately from the maintained-driver fixes. They do not
qualify as new performance ideas or reopen earlier rejected experiments.

## Sonar follow-up

The initial PR 4 analysis reported 21 open findings: one response-validator
complexity finding, eight exception-assertion findings, six cross-script writable
binding findings, one status-element finding, two nested ternaries, two nested
template literals and one class-field initialization finding. This cleanup
addresses each group directly; analysis exclusions and quality rules are unchanged.

The native schema refactor preserves return identity or exact exception type/message
across 1,944 synthetic combinations. Exception tests prepare arguments/lazy
generators before asserting the actual failing call. The UI declares its legitimate
writable shell bindings without creating shadows or migrating lexical settings to
window properties; an actual pinned-shell regression verifies sharing/Apply.
Semantic output retains polite/atomic announcements and its block layout. Nine
export scenarios and eight actual Monitor mode combinations match the previous
commit exactly; class defaults are preserved.

Local validation now passes 282 offline Python tests and 28 JavaScript tests,
plus the same 12 benchmark-termination, one six-case launcher-termination, two
port and five campaign-protocol tests: 330 total. Cloud closure is verified by
the fresh analysis of the final PR head, rather than inferred from the green gate
or local rule checks. Full-model performance measurements remain unchanged.
