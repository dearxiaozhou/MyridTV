# Existing-node generation — V0.11.18 (2026-10-15)

Uploaded images and generated images use the same rerun policy: archive prior
images on disk, retain the original node and replace its contents. The workflow
input flag and absence of previous generation metadata no longer exclude an
existing image from replacement. Manual reruns mark output placement as replace,
so an MCP-origin node does not auto-split old/new versions into grouped nodes.

The alternative cascade/Jimeng result-replacement path now awaits disk archival
instead of creating a visual history group. All its internal callers await the
replacement. Identical forwarded media URLs are retained instead of moving a
file that is still the next output. Existing visual groups are not deleted.

Safety: archival failure stops before submission; a failed generation without
new output restores the last available image reference. Shared image and prompt
references are updated to the archived path. Attempt guards protect replacement
across asynchronous archival.

`python tests/verify_canvas_overwrite.py` runs the actual app server and browser
with private user-data and asset folders. A real GUI run-button click uses only
stubbed provider submission/results; no paid generation is submitted. Verified:

- Uploaded MCP-origin image (no generated metadata) is archived physically.
- New image replaces the original node; node IDs/count remain unchanged and no
  history or grouping node is added.
- Other nodes and model input references still resolve the old archived file.
- The alternate replacement path also archives on disk without a new UI node.
- Provider failure keeps the last available image on the original node.
- Archival failure preserves the image and does not invoke the provider.
- Saving/reloading retains only the latest image on the same node IDs.

The CI UI gate now runs this disk-and-browser regression and uploads its evidence.
Remote CI execution is not claimed by this local verification. Project self-check,
generation lifecycle regression and cascade-round scheduler (8/8) passed locally.
An independently opened desktop window displayed V0.11.18.

Evidence: `_verification/overwrite/latest-only.png`, `results.json`, `server.log`.

## V0.12.5 — manual grouping only (2026-10-16)

Removed three implicit group-creation paths: MCP/Agent multi-image materialization
on render/load, legacy imported multi-image migration on load, and force-new
multi-file import grouping. Existing saved groups retain bounds/aspect repair;
manual grouping remains available. Existing groups and images are not deleted.

Extended the private-runtime browser regression to cover all four agent origins,
legacy import titles, repeated rendering, saving/reloading, multi-file import,
and manual group persistence. The new no-auto-group assertion failed before the
change and passed afterwards. Provider responses remain fixtures: this does not
claim a paid generation was run. Evidence: `no-auto-group.png`, `results.json`.

Project self-check passed (syntax, unit tests, wiring, i18n; full legacy E2E skipped).
The actual desktop window was inspected and captured in
`desktop-active-generation.jpg`. It had an active generation, so it was not
refreshed or restarted. Loading the changed scripts in that existing desktop
session has not been verified; a refresh after the active run is required.
