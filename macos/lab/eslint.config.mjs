import js from "@eslint/js";
import globals from "globals";

const readonly = (names) => Object.fromEntries(names.map((name) => [name, "readonly"]));
const writable = (names) => Object.fromEntries(names.map((name) => [name, "writable"]));

// Include the browser names these scripts use, rather than accepting every
// environment name. Verify the standard names against the pinned globals data.
const browserGlobals = Object.fromEntries([
  "Blob", "DOMException", "Event", "MutationObserver", "ReadableStream", "Response",
  "TextDecoder", "URL", "document", "fetch", "location", "matchMedia", "performance",
  "queueMicrotask", "setTimeout", "window",
].map((name) => {
  if (!Object.hasOwn(globals.browser, name)) throw new Error(`Unknown browser global: ${name}`);
  return [name, "readonly"];
}));

const correctnessRules = {
  ...js.configs.recommended.rules,
  "no-undef": ["error", {typeof: true}],
  "eqeqeq": ["error", "always", {null: "ignore"}],
  "no-eval": "error",
  "no-implied-eval": "error",
  "no-new-func": "error",
  "no-return-assign": "error",
  "no-sequences": "error",
  "no-shadow-restricted-names": "error",
  "no-throw-literal": "error",
  "no-unmodified-loop-condition": "error",
  "prefer-const": "error",
  "no-unused-expressions": "error",
  "no-promise-executor-return": "error",
  "no-shadow": ["error", {builtinGlobals: true}],
};

export default [
  {
    files: ["web/mac.js", "web/ui-state.js", "web/performance.js"],
    languageOptions: {ecmaVersion: 2024, sourceType: "script", globals: browserGlobals},
    linterOptions: {reportUnusedDisableDirectives: "error"},
    rules: {
      ...correctnessRules,
      "complexity": ["error", 15],
    },
  },
  {
    files: ["tests/*.test.cjs"],
    languageOptions: {ecmaVersion: 2024, sourceType: "commonjs", globals: globals.node},
    linterOptions: {reportUnusedDisableDirectives: "error"},
    rules: correctnessRules,
  },
  {
    files: ["web/mac.js"],
    // mac.js already declares its writable shell hooks with a global contract
    // that Sonar also reads. Repeating those names here creates redeclarations.
    languageOptions: {
      globals: {
        ...readonly([
          "$", "attachments", "autosize", "busy", "gb", "health", "headers",
          "lastMetrics", "messages", "METRICS", "saveShared", "store", "StrataChatUndo",
          "StrataSharedSettings", "StrataUIState", "strataChatMarkdown", "strataIntegerError",
          "strataUnavailableFiles",
        ]),
      },
    },
  },
  {
    files: ["web/ui-state.js"],
    // The helpers are classic browser globals and expose CommonJS exports only
    // for load-free Node tests. Declaring module does not create it in browsers.
    languageOptions: {globals: {module: "readonly"}},
  },
  {
    files: ["web/performance.js"],
    languageOptions: {
      globals: {
        ...readonly([
          "$", "attachments", "busy", "ctxfmt", "esc", "fmt", "gb", "kfmt", "lastMetrics",
          "messages", "store", "toast", "StrataRequestTiming",
        ]),
        ...writable(["send", "updateAssistant", "render"]),
      },
    },
  },
];
