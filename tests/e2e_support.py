# -*- coding: utf-8 -*-
"""Shared network assertions for isolated canvas browser tests."""
from urllib.parse import urlsplit


_EXPECTED_BACKGROUND_POSTS = {"/api/comfyui/auto-expose-media"}


def record_blocked_write(records, method, url, *, as_url=False):
    """Record a forbidden test write, excluding the known workflow maintenance POST.

    Canvas pages may automatically request workflow-field reconciliation while a
    custom ComfyUI workflow loads. E2E route guards still abort that request, so it
    cannot mutate even the isolated test data; it is not a canvas-state write and
    must not make unrelated canvas interaction tests fail.
    """
    parsed = urlsplit(url)
    if method.upper() == "POST" and parsed.path in _EXPECTED_BACKGROUND_POSTS:
        return
    records.append(url if as_url else {"method": method, "url": url})
