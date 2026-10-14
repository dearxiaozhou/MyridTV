# Generation ownership and frame stability — V0.11.4

Fourth-stage increment, 2026-10-14.

## Reproduced failure

In the running application, submit node A, select/edit node B, then resolve A's
provider response. Before this change A completed correctly but selected itself,
rebound the editor, restored A's settings over B's, and lost B's visible draft.
The new regression first failed all four ownership assertions and now passes.

## Ownership rules

- Each single-node run captures its own settings before asynchronous work.
  Legacy synchronous request/meta helpers borrow the shared getter only for
  their synchronous call; it is restored before yielding. Provider dispatch and
  completion never restore an old global settings snapshot.
- `CanvasGenerationLifecycle` owns attempt identity, terminal cleanup and frame
  lock/restore. New attempts invalidate older callbacks. Pending API tasks are
  bound to the attempt that started their polling.
- Comfy cancellation and recovery polling check both attempt/job ownership after
  asynchronous responses, so old cleanup does not clear or interrupt a new job.
- Completion only updates selection for its currently selected node. It does
  not move the editor from B to A or mark B's prompt as A's preserved draft.
- Pending counts represent outstanding task IDs, not the requested output count.
  Completed task IDs are removed after localization commits; concurrent task
  completions cannot restore an older task-list snapshot.
- `cardSize` remains the persisted authoritative frame. A resize made while a
  task runs is retained on success, failure, cancellation and reload. Invalid
  frame metadata falls back to valid explicit dimensions before a default ratio.
- Specification controls do not resize queued/running API/Jimeng/Comfy cards.

Existing provider-specific progress/status fields remain compatibility adapters.
This change does not claim every legacy cascade, speech or remote-provider
state write has been migrated into one universal state machine.

## Verification

- `tests/e2e_canvas_generation_lifecycle.py`: 16 outcome/ownership assertions,
  15 engine/outcome frame cases, and 5 full runner dispatch/completion fixtures.
  Real app/browser runtime; external requests blocked and providers stubbed.
- `tests/test_canvas_generation_lifecycle.py`: stale attempt rejection,
  cancellation invalidation, cleanup flags, frame fallback and UI-state isolation.
- Expanded light/dark UI baseline 4/4 and project self-check passed. Full legacy
  browser suite was skipped in the self-check invocation; targeted runtime
  suites above ran separately.
- Diagnostics: `_verification/generation-lifecycle/results.json` and
  `ownership.png`. The mandatory CI UI step now also runs this lifecycle suite
  and uploads its evidence. Remote CI itself was not run locally.

No paid generation was submitted by these checks. Source/installer version labels
and affected script cache keys are synchronized to V0.11.4.

## Desktop startup verification

The normal local launcher initially failed with WinError 10013: Windows had
reserved TCP ports 3013–3112, including 3107. Its previous connect-only check
could not detect a non-listening excluded port. The launcher now probes actual
exclusive binding before selecting a fallback and writes the selected port to
the existing app config used by both backend and desktop shell.

The occupied/free/released-port regression passed. Normal startup selected
3113; `http://127.0.0.1:3113/health` returned ok and V0.11.4. The actual desktop
window displayed V0.11.4 and loaded the existing canvas/media. No Windows port
reservation, firewall, or security setting was changed. External integrations
that explicitly pin 3107 must use the configured current port.

The bundled stdio MCP client now follows the app's configured backend on each
request, preserving an explicit `MYRIDTV_MCP_BASE` override. Configuration-change
and override tests passed, and real MCP discovery on 3113 returned 27 tools.
