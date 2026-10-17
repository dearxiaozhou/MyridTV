# Canvas media re-import — V0.12.10 (2026-10-16)

The previous canvas upload reuse condition only applied to images. Audio, video
and general files always allocated a new name even when importing identical
bytes from their own canvas directory. The common save path now checks all
canvas media types against the same-name collision family, within the target
directory only. Same-name different content remains a separate file; other
canvases still get their own copies. Matching uses chunked byte comparison.
Reused videos bypass transcoding so an existing file is not changed on import.
AAC and M4V extension fallback now agrees with the canvas upload acceptance list.

Before the fix, the added tests failed for audios, videos, files and concurrent
audio uploads. All nine upload tests now pass. The project self-check passed;
the full legacy E2E suite was skipped, with targeted upload runtime verification
run separately.

`python tests/verify_canvas_media_reuse.py` starts a private application instance
with isolated data and assets. It uploads real PNG/WAV/H.264 fixtures, selects
the saved file through the real canvas file input, and verifies stable URL,
directory file count, bytes and modification timestamp. General files use the
real multipart API; different-content collisions and subsequent reuse are also
checked. AAC/M4V are tested with unspecified MIME types through the upload API.
No provider requests or upload mocks are used.

The same regression passed against the user's running backend on port 3113,
after restarting only the idle backend through the development startup script.
The temporary verification canvas and its outputs were purged by exact ID with
a title guard. Actual desktop window screenshot: `desktop.jpg`.

Evidence: `_verification/media-reuse/results.json`, `canvas.png`, `desktop.jpg`.
Existing duplicate user files are not deleted by this change.
