# Canvas UI component contract — V0.11.1

## Ownership

| Component | Owner | Contract |
| --- | --- | --- |
| Multi-image card | `.multi-image-node` in smart-canvas.css | Thumbnail layout and card surface only; never a group-frame selector |
| Group frame | `.canvas-group-node` in smart-canvas.css | Header, border and member boundary; no media-card surface rules |
| Node stacking | `nodeLayerZ()` | Frame 0, connections 1, ordinary media 2, selected/front media 4; selection cannot raise a frame over its contents |
| Parameter popover | `CanvasParamEvents` | One writer for pinned and aria-expanded; Escape restores trigger focus; resize/wheel re-fit once per animation frame |
| Node editor placement | `positionComposerForNode()` | Clamp screen coordinates before converting to world coordinates; keep the editor clear of the left toolbar, minimap and bottom dock; update on viewport/window changes |
| Custom style/filter libraries | Their existing library controller | Explicit exception: search and custom layout; not managed by the parameter lifecycle marker |
| Hover/selection colors | canvas-interaction-style.css | Shared `--x-*` tokens; component CSS owns geometry and surface, not new neutral interaction colors |

The composer (30) and its local popovers (50) are separate stacking contexts;
these are local canvas values, not global application overlay values. Root
dialogs and other pages keep their existing ordering. Do not compare child
z-index values across stacking contexts.

`data-param-popover` identifies controls with explicit click state. Focusing a
closed managed trigger does not open the menu. Unmanaged controls retain their
existing focus behavior. Outside click closes without stealing focus from the
clicked destination; Escape inside a managed menu closes and restores its
trigger. Style/filter libraries retain their dedicated lifecycle.

## Regression contract

`check_frontend_architecture.py` rejects ambiguous `.group-node` surface rules
and component-level z-index overrides. Descendant port/action layers are allowed.
Its rejection behavior was exercised with temporary negative fixtures (3/3).

`e2e_canvas_ui_baseline.py` runs both themes at 1100 and 1680 widths. In addition
to first-stage coverage it checks keyboard re-opening, restored focus, shrinking
an open menu to 900×720, and frame/connection/multi-image ordering before and
after selection and re-render. Image-center hit testing verifies that media
remains clickable rather than merely checking class names.

Both video reference menus and image specification menus are exercised. Editor
bounds are checked on selection, zoom and window resize; a bottom-left fixture
also verifies minimap clearance. The existing wheel control test now hit-tests
an actual empty canvas point instead of assuming a fixed coordinate stays empty
after editor placement changes.

## Verification scope

- UI baseline 4/4; node layout 9/9; interaction combinations 14/14;
  parameter events 5/5.
- Project self-check passed (syntax, i18n, names, units, frontend wiring).
  Full legacy browser suite was skipped in that invocation; the relevant browser
  suites above ran separately in isolated runtimes without provider generation.
- Both themes have screenshots and traces in `_verification/ui-baseline`.
- Actual desktop runtime displayed V0.11.1 and reopened an existing canvas.
  Media selection, frame/connection ordering, and the corrected editor left
  edge were visually inspected. Menu/resize/focus/minimap assertions ran in the
  isolated browser runtime. Desktop focus was repeatedly interrupted by user
  input and other windows, so full desktop double-theme acceptance is not claimed.
- Source interaction audit covers smart canvas/shared styles/light overrides,
  home/theme, legacy canvas, API, Comfy settings and asset manager styles. Evidence:
  `_verification/ui-baseline/style-scope-audit.json`. This is a selector inventory
  and change-scope check, not a claim that every application screen was retested.
- No root button tokens or semantic destructive/running/disabled colors changed.
  Duplicate overridden multi-image background declarations were consolidated;
  the historical card appearance and component shadow were retained.
- Remote CI and packaging are not executed by this local change.

The third-stage state-write consolidation remains separate from these UI
component boundaries.
