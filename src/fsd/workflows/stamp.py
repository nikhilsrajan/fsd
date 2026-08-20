"""Shared identity-stamp helper: "were these artifacts derived from exactly this request?"

Spec 49 §7 Q5 (signed off): spec 48 D5's resume-identity check for a landed cube and spec 49
D3's flatten-skip stamp are the SAME question asked about two different artifacts, so they
share ONE mechanism rather than each growing its own. A stamp is a small JSON sidecar recording
the caller-visible identity of the request that produced an artifact -- never a modification
time (spec 49 D3: two unsynchronised clocks, and a blob's `Last-Modified` cannot carry "when
this content was produced" across a copy at all). Mirrors the shape of DVC's `dvc.lock` / Bazel's
action key: a record of what defined the work, compared by equality, never by age.

Fails towards running: a missing, unreadable, or malformed stamp is treated as "no match" (never
raises) -- the caller then does the work rather than trusting a stamp it cannot make sense of.
"""

from __future__ import annotations

import datetime
import json

from fsd.storage import fs

__all__ = ["compute_callable_fingerprint", "matches_stamp", "read_stamp", "write_stamp"]

_WRITTEN_AT_KEY = "_written_at"


def compute_callable_fingerprint(fn) -> str:
    """`module.qualname` of a callable -- the cheap fingerprint spec 49 §7 Q4 settled on
    (qualname + kwargs, not a source hash). Editing a feature function's BODY with the same
    name does not change this fingerprint; the docstring of any caller relying on this must
    say so plainly."""
    return f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', repr(fn))}"


def write_stamp(path: str, identity: dict) -> None:
    """Write `identity` (a JSON-serializable dict) to `path`, plus a human-readable
    `_written_at` timestamp (display only -- never read back for comparison, D3: no clock)."""
    payload = dict(identity)
    payload[_WRITTEN_AT_KEY] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fs.write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str))


def read_stamp(path: str) -> dict | None:
    """The stamp at `path`, or `None` if it is absent, unreadable, or not a JSON object --
    every one of those is "no information", never an error (fail towards running)."""
    if not fs.exists(path):
        return None
    try:
        with fs.open(path, "r") as f:
            stamp = json.load(f)
    except Exception:  # noqa: BLE001 - a corrupt/foreign stamp is "no match", not a crash
        return None
    return stamp if isinstance(stamp, dict) else None


def matches_stamp(path: str, identity: dict) -> bool:
    """Does the stamp at `path` record exactly `identity`? `False` on any absent/unreadable/
    mismatched stamp -- the caller's cue to (re)do the work rather than trust it."""
    stamp = read_stamp(path)
    if stamp is None:
        return False
    stamp = {k: v for k, v in stamp.items() if k != _WRITTEN_AT_KEY}
    return stamp == identity
