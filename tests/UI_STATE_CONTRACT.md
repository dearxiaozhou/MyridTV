# UI state ownership — V0.11.3

Third-stage first increment, 2026-10-14.

## Single owner

`canvas-ui-state.js` owns transient primary/multiple selection, selected media,
editor binding and a bounded diagnostic transition history. Its selection and
editor wrappers are frozen. Callers update them through commands rather than
writing into snapshots. Node content (including saved prompt drafts and run
settings) continues to belong to the canvas data model; an editor binding holds
a reference to that node, not a duplicate of its content.

The main script's five independent selection/editor variables were removed.
Their reads use the owner's snapshots and their writes use its commands. The
existing read-only CanvasStateHub exposes a diagnostic `ui` snapshot with node
IDs, not draft contents. The writable owner and read-only registry are separate.

The selection, clipboard, deletion and undo controllers commit related
selection fields together. Existing single-field adapters used by other modules
also write to this same owner; they do not retain independent state. A temporary
global-property adapter preserves existing developer tools and browser fixtures.
Production main-script code no longer uses those global aliases.

## Editor transitions

Switching editor nodes saves the old node's draft, closes its parameter
popovers, then binds/loads the new node. Closing the editor clears its binding
and parameter overlays together. No selection/editor/diagnostic fields were
added to `buildCanvasStoragePayload` or local canvas drafts. Undo selection
snapshots remain intentional local undo data.

## Checks

- UI-state contract: atomic update, immutable snapshots, isolated diagnostics,
  node reference ownership, and compatibility adapter passed.
- Expanded UI baseline: 4/4 (light/dark, 1100/1680 widths). Real keyboard/pointer
  input edits two different node drafts, switches between them, verifies each
  draft and setting remains on its owner, and checks old menus are dismissed.
  Saved payload keys exclude transient UI state.
- Clipboard 11/11, deletion 13/13, undo 7/7, interaction combinations 14/14,
  three-way synchronization passed in isolated browser runtimes.
- Project syntax, i18n, unit tests, dangling-name and frontend wiring self-check
  passed. Full legacy browser suite was skipped in that invocation; the targeted
  runtime checks above ran separately.
- Same-directory upload reuse was exercised again through real browser file
  input and the isolated backend; no duplicate disk file or rendering regression.
- A fresh actual desktop window displayed V0.11.3 and loaded an existing canvas
  with its media and controls. Detailed draft/menu/selection assertions were run
  in isolated application browser runtimes; full desktop interaction coverage is
  not claimed.
- Architecture gate rejects reintroducing the old top-level state variables
  and direct writes to UI snapshots. New/changed script cache keys and software
  version labels are synchronized.

## Remaining scope

Task runtime transitions and node geometry ownership are not migrated by this
increment. They remain separate from this transient UI owner and need their own
failure/cancel/completion fixtures before migration. No claim of whole-frontend
state unification, remote CI execution or installer packaging is made.
