# Canvas image upload reuse — V0.11.2

Verified 2026-10-14.

Canvas-scoped image uploads now reuse an existing file when its sanitized name
(or an existing collision suffix) and exact bytes match. The original file is
not rewritten. The browser does not expose a trustworthy original full path;
matching the bytes in the destination directory also covers selecting the file
from that canvas's own images folder.

Different image contents keep the existing non-overwriting suffix behavior.
Other canvases still receive their own copy. Matching is limited to the same
filename collision family in the current destination, not a global asset scan.
The byte comparison reads in chunks, and upload writes are synchronized so
concurrent identical image imports do not create duplicate files. Video,
library and legacy unscoped upload behavior is unchanged.

Validation:

- `python tests/test_canvas_upload_reuse.py -v`: 6/6 passed; includes unchanged
  original timestamp, same-size different contents, suffix reuse, separate
  canvases, long filenames and concurrent upload requests.
- `python tests/verify_canvas_upload_reuse.py`: real app server on a private
  port, private data/assets directories, real browser file input. Uploaded an
  external PNG, then selected the saved PNG from the canvas images directory:
  response URL unchanged, no extra file, original timestamp unchanged, image
  rendered. Same basename with different contents created a separate file.
- Screenshot and results: `_verification/upload-reuse/same-folder-upload.png`
  and `_verification/upload-reuse/results.json`.
- Project self-check passed (syntax, units, frontend wiring). Full legacy E2E
  was skipped in that invocation; the upload runtime check ran separately.
- Main local backend restarted after verifying no queued/running tasks. Health
  returned ok with a new process and software version V0.11.2.

Previously created duplicates are retained. This change prevents new duplicate
copies and does not delete files that may already be referenced by canvas nodes.
