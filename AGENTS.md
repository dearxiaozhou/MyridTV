# MyridTV Agent Operating Rules

## Version Rule

1. The canonical MyridTV software version is stored in `VERSION`.
2. The visible dock badge must display `版本：Vx.y.z`.
3. The current software version is `V0.0.39` unless the user explicitly sets another version.
4. For future MyridTV software changes, every agent must advance the version before finishing. Increase the patch number by one while it is below `20`; if the current patch number is `20` or greater, the next version is `Vx.(y+1).0`.
   Examples: `V0.0.19` -> `V0.0.20`, `V0.0.20` -> `V0.1.0`, `V0.0.39` -> `V0.1.0`, and `V0.1.20` -> `V0.2.0`.
5. Keep these values synchronized in the same change:
   - `VERSION`
   - `_internal/static/index.html` dock version badge
   - `installer/desktop/MyridTV.Desktop.csproj`
   - `installer/launcher/MyridTV.Launcher.csproj`
6. If the user explicitly requests a specific version, set that exact version for that turn and apply patch increments only to later software changes.

## Verification Rule

After modifying MyridTV, verify the actual running local application window with a screenshot before reporting completion. Do not rely on static file inspection alone.

## Existing-node Image Generation Rule

Generating again on a node that already contains an image (uploaded or generated)
must keep that node ID, position and connections. Archive the previous image in
the canvas's local history folder and replace the node's images with the latest
generation's results. Do not create a canvas history node or group old and new
versions together. A manual rerun must not trigger MCP auto-grouping of versions.
If disk archival fails, stop before provider submission and keep the current
image. If generation fails without any new output, keep the last available image.
Update other canvas references when a shared old file moves to history. Preserve
explicit batch/loop output creation and existing user groups unless separately
requested; those are not automatic history versions.

## Manual-only Canvas Grouping

Canvas groups must be created by an explicit user Group action. Do not split and
group MCP/Agent multi-image results during render, sync or loading. Multi-file
imports must not create a smart-group, and legacy multi-image nodes must not be
converted to groups on load. Preserve existing saved groups and their contents.

## Packaging Rule

1. Release builds must be produced through `installer/prepare-release.ps1` or `installer/build-installer.ps1`. Do not manually copy the app tree into a release folder.
2. The release package must never include local runtime state or personal data. In particular, do not package `_internal/API/.env`, `_internal/data/app_config.json`, user canvases, conversation history, logs, backups, model preferences, caches, generated outputs, or local machine paths.
3. The staged release must contain only a clean `_internal/API/.env.example`, a clean `_internal/data/app_config.template.json`, and empty runtime directories needed for first launch.
4. `prepare-release.ps1` owns the privacy gate. If its release privacy check fails, stop and fix the package source or exclusion logic before producing an installer.
5. After packaging, verify both behavior and privacy: launch the staged or installed app, confirm `http://127.0.0.1:3107/health` responds, and scan the staged or installed tree for forbidden runtime files and local-path leaks.

## Theme Regression Rule

After changing theme or interaction styling, audit all shared and component-specific hover, selected, expanded, and focus rules. Cover the home page, task console and statistics, main dock, canvas left and bottom tools, node upload and media actions, API image/video and ComfyUI/RunningHub parameter bars, standalone prompt nodes, material/prompt libraries, and recycle bin. Resolve higher-specificity overrides rather than checking only the component in the user's screenshot. Use shared design tokens for neutral interaction colors; preserve selected, destructive, disabled, and primary-action states. Refresh changed stylesheet cache keys. Verify representative interactions in both light and dark themes in the running application, save screenshots, and distinguish source-only checks from runtime checks in the verification record.

## Canvas Interaction Style Rule

1. Keep shared canvas hover, selected, expanded, focus, and native dropdown states in `_internal/static/css/canvas-interaction-style.css`. Load this file after every canvas component stylesheet, including speech and theme overrides.
2. Component styles may set layout and surface treatment, but neutral interaction colors must use the shared `--x-*` tokens. Do not leave older hard-coded hover or selected colors that conflict with the shared layer.
3. Custom dropdown triggers must expose `aria-expanded="false"` initially and update it on every open and close path; the shared expanded state uses that attribute.
4. A semantic exception such as pin/warning, destructive, disabled, running, or primary action must be explicit, token-based, and excluded from the generic selected/hover rules instead of relying on a later high-specificity override.
5. Before adding an interaction rule, check the shared selector and verify the selector matches the control itself. Document any component exception beside its rule, refresh the cache key, and verify both themes in the running app.
6. Keep neutral hover/open and selected states distinct: hover/open uses `--x-hover-bg`, `--x-text`, and `--x-selected-line`; selected uses `--x-selected-fill`, `--x-selected-text`, and `--x-selected-ring`.
7. A borderless neutral control needs a visible inset hover edge. If a neutral control is excluded from the shared hover selector, add a matching explicit rule in the shared stylesheet and verify it in the running UI.
