# UI stability baseline

Run from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run_regression.ps1 -Only ui_baseline
```

The runner starts a private port with temporary user data. The browser blocks
external requests and intercepts writes; the fixture never submits generation
or writes to a user's canvas. Use Playwright 1.63.0 with its installed Chromium;
`MYRIDTV_TEST_BROWSER` optionally selects a local executable.

The first baseline covers two video nodes, light/dark themes, 1100/1680 widths,
selection, reference-menu open/close, Escape, outside click, switching nodes,
wheel zoom, option selection and menu viewport bounds. Interactions use browser
pointer/keyboard input. Fixture setup alone uses direct state injection.

Evidence is written to `_verification/ui-baseline` (override with
`MYRIDTV_UI_ARTIFACTS`): results.json, screenshots and Playwright traces.
Screenshots are diagnostic evidence, not a pixel-diff approval baseline.
The existing CI verify job now runs this portable baseline as a required step;
the legacy full local E2E suite remains separate. A baseline failure blocks the
dependent package job, and the evidence is uploaded even on failure.

Extend this baseline with an independently reproducible failure before changing
shared UI behavior. Add image/audio/group fixtures, generation transitions,
host DPI and visual diffs in subsequent stages; they are not covered here.

## V0.11.0 verification (2026-10-13)

- Before viewport correction: the new bounds assertion failed at 1680px in
  both themes (reference popover left=-1.5px); 1100px cases passed.
- After correction: UI baseline 4/4; parameter event regression 5/5;
  interaction combinations 14/14; layout coordinator passed.
- Project verify passed: Python/JS syntax, i18n, dangling names, unit tests,
  frontend wiring. Full browser E2E was skipped in this invocation; the four
  targeted browser suites above were run separately against isolated runtimes.
- Desktop application reloaded and displayed V0.11.0; existing canvas reopened,
  zoom/navigation and reference popover opening observed in the actual window.
- CI configuration has been edited locally; no remote CI run or package build
  is claimed.
