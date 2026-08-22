"""The model registry (P6): a name for a bundle, on the storage seam (D1).

    <registry>/
      <name>/
        _aliases.json          {"champion": 3, "current": 4}
        v1/  bundle.json, code/, artifacts...   [+ _deploy.json, step 2]
        v2/  ...

Everything reads and writes through `fsd.storage.fs`, so a local registry and a blob
registry are the same code. Versions are immutable; `_aliases.json` is the only mutable
pointer (D3). `publish` is idempotent by content digest (D2) and atomic via
`storage.fs.rename` from a staging prefix. `migrate` relocates a registry and re-digests
every version, so a ref that resolves against one root resolves identically against a
copy of it (D11).

`resolve`/`publish` are the interface; the storage-seam layout is v1's only backend, but
a second one can be added without either signature changing (D10).

Spec: specs/51-deploy-model-registry.md
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import uuid
from typing import NamedTuple

from fsd.model import bundle as bundle_mod
from fsd.storage import fs

__all__ = [
    "Resolved",
    "content_digest",
    "migrate",
    "parse_ref",
    "publish",
    "resolve",
    "set_alias",
    "version_path",
]

ALIASES_FILE = "_aliases.json"
_STAGING_PREFIX = ".staging-"

_REF_RE = re.compile(r"^(?P<name>[^:@]+)(?P<sep>[:@])(?P<value>.+)$")
_VERSION_ALIAS_RE = re.compile(r"^v(\d+)$")
_VERSION_DIR_RE = re.compile(r"^v(\d+)$")


class Resolved(NamedTuple):
    name: str
    version: int
    path: str


# --- ref parsing (D3) ---------------------------------------------------------


def parse_ref(ref: str) -> tuple[str, str, str]:
    """`'crop-rf:3'` -> `('crop-rf', ':', '3')`; `'crop-rf@champion'` -> `('crop-rf', '@',
    'champion')`. A bare name (no `:` or `@`) raises, naming both forms -- a default that
    silently picked one would be the failure mode aliases exist to make visible (D3)."""
    m = _REF_RE.match(ref)
    if not m:
        raise ValueError(
            f"model ref {ref!r} is ambiguous: use 'name:version' (e.g. 'crop-rf:3') or "
            "'name@alias' (e.g. 'crop-rf@champion')."
        )
    return m.group("name"), m.group("sep"), m.group("value")


def version_path(registry: str, name: str, version: int) -> str:
    return os.path.join(registry, name, f"v{version}")


def _name_root(registry: str, name: str) -> str:
    return os.path.join(registry, name)


def resolve(ref: str, registry: str, *, storage_options: dict | None = None) -> Resolved:
    """Turn a ref into the version it names. Costs one `_aliases.json` read for a named
    alias, and nothing for a version pin (`name:N` or the `name@vN` shorthand) -- pinning
    a version never lists or reads anything (D9), which keeps N nodes each resolving a
    model off the hot path."""
    name, sep, value = parse_ref(ref)
    if sep == ":":
        if not value.isdigit():
            raise ValueError(f"model ref {ref!r}: version must be an integer, got {value!r}")
        version = int(value)
    else:
        m = _VERSION_ALIAS_RE.match(value)
        if m:
            version = int(m.group(1))
        else:
            aliases = _read_aliases(registry, name, storage_options)
            if value not in aliases:
                raise ValueError(
                    f"alias {value!r} not found for {name!r} in {registry!r} "
                    f"(known aliases: {sorted(aliases)})"
                )
            version = aliases[value]
    return Resolved(name, version, version_path(registry, name, version))


def _read_aliases(registry: str, name: str, storage_options: dict | None) -> dict:
    opts = storage_options or {}
    path = os.path.join(_name_root(registry, name), ALIASES_FILE)
    try:
        with fs.open(path, "r", **opts) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def set_alias(
    name: str, alias: str, version: int, registry: str, *, storage_options: dict | None = None,
) -> None:
    """Repoint `alias` at `version` (D3). Never touches a version directory.

    Refuses an alias shaped `v<digits>`: that spelling is reserved for the `name@vN`
    version-pin shorthand (D9), so an alias with that name could never be reached by
    `resolve` -- it would silently pin the literal version number instead.
    """
    if _VERSION_ALIAS_RE.match(alias):
        raise ValueError(
            f"alias {alias!r} is shadowed by the 'name@v<N>' version-pin shorthand and "
            "could never be resolved -- pick a different alias name."
        )
    opts = storage_options or {}
    name_root = _name_root(registry, name)
    target = os.path.join(name_root, f"v{version}")
    if not fs.exists(target, **opts):
        raise ValueError(f"cannot set alias {alias!r} -> v{version}: {target!r} does not exist")

    path = os.path.join(name_root, ALIASES_FILE)
    try:
        with fs.open(path, "r", **opts) as f:
            aliases = json.load(f)
    except FileNotFoundError:
        aliases = {}
    aliases[alias] = version
    fs.write_text(path, json.dumps(aliases, indent=2, sort_keys=True), **opts)


# --- content digest (D2) -------------------------------------------------------


def _bundle_content_rels(manifest: dict) -> list[str]:
    """The file set D2's digest is computed over: the manifest itself, every artifact,
    every embedded code file -- exactly what `bundle.load` needs, nothing a caller added
    beside it."""
    rels = {bundle_mod.BUNDLE_MANIFEST}
    rels.update(manifest.get("artifacts", {}).values())
    rels.update(bundle_mod.manifest_code_files(manifest))
    return sorted(rels)


def _read_bundle_content(base_path: str, storage_options: dict | None) -> list[tuple[str, bytes]]:
    """`(relative path, bytes)` for every manifest-declared file under `base_path` --
    a fresh `bundle.save` output and an already-published version directory have the same
    shape, so this reads either."""
    opts = storage_options or {}
    with fs.open(os.path.join(base_path, bundle_mod.BUNDLE_MANIFEST), "r", **opts) as f:
        manifest = json.load(f)
    rels = _bundle_content_rels(manifest)
    return [
        (rel, _read_bytes(os.path.join(base_path, rel), opts))
        for rel in rels
    ]


def _read_bytes(path: str, storage_options: dict) -> bytes:
    with fs.open(path, "rb", **storage_options) as f:
        return f.read()


def _digest_of(files: list[tuple[str, bytes]]) -> str:
    h = hashlib.sha256()
    for rel, data in sorted(files, key=lambda item: item[0]):
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(data)
    return f"sha256:{h.hexdigest()}"


def content_digest(bundle_path: str, *, storage_options: dict | None = None) -> str:
    """SHA-256 over a bundle's manifest-declared files (sorted relative path + bytes,
    D2). Two bundles with this equal are the same content; used by `publish` for
    idempotency and by `migrate` to prove a copy arrived intact."""
    return _digest_of(_read_bundle_content(bundle_path, storage_options))


# --- publish (D2) ---------------------------------------------------------------


def _list_names(registry: str, storage_options: dict) -> list[str]:
    if not fs.exists(registry, **storage_options):
        return []
    names = []
    for entry in fs.ls(registry, **storage_options):
        leaf = entry.rstrip("/").rsplit("/", 1)[-1]
        if leaf.startswith("."):
            continue
        names.append(leaf)
    return sorted(names)


def _list_versions(name_root: str, storage_options: dict) -> list[int]:
    if not fs.exists(name_root, **storage_options):
        return []
    versions = []
    for entry in fs.ls(name_root, **storage_options):
        leaf = entry.rstrip("/").rsplit("/", 1)[-1]
        m = _VERSION_DIR_RE.match(leaf)
        if m:
            versions.append(int(m.group(1)))
    return sorted(versions)


def _write_new_version(
    name_root: str, files: list[tuple[str, bytes]], storage_options: dict,
) -> int:
    """Stage `files` and rename onto the next free `v<N>` (D2). A losing racer retries at
    `v<N+1>` rather than corrupting the winner's directory -- but note the local backend's
    `mv` is `shutil.move`, which nests the source INSIDE an existing destination directory
    rather than raising, so this only catches a race in the (small) window the `exists`
    pre-check leaves open, not one that lands between the check and the rename. The
    registry has no lock service by design (spec 51 §5); this is the accepted gap."""
    version = max(_list_versions(name_root, storage_options), default=0) + 1
    while True:
        target = os.path.join(name_root, f"v{version}")
        if fs.exists(target, **storage_options):
            version += 1
            continue

        stage = os.path.join(name_root, f"{_STAGING_PREFIX}{uuid.uuid4().hex}")
        try:
            for rel, data in files:
                fs.write_bytes(os.path.join(stage, rel), data, **storage_options)
        except BaseException:
            with contextlib.suppress(Exception):
                fs.rm(stage, recursive=True, **storage_options)
            raise

        try:
            fs.rename(stage, target, **storage_options)
        except OSError:
            with contextlib.suppress(Exception):
                fs.rm(stage, recursive=True, **storage_options)
            version += 1
            continue
        return version


def publish(
    bundle_path: str,
    name: str,
    registry: str,
    *,
    alias: str | None = None,
    storage_options: dict | None = None,
    bundle_storage_options: dict | None = None,
) -> int:
    """Publish the bundle at `bundle_path` to `<registry>/<name>/`. Returns the version
    integer.

    Idempotent by content digest (D2): if a version with identical content already
    exists, it is returned and nothing is written -- `publish` is safe to call again
    from a re-run notebook cell. Otherwise the next integer version is allocated and
    published atomically (`storage.fs.rename` from a staging prefix).

    `storage_options` reaches the registry; `bundle_storage_options` reaches
    `bundle_path` (only needed when the bundle itself is not local).
    """
    files = _read_bundle_content(bundle_path, bundle_storage_options)
    digest = _digest_of(files)

    opts = storage_options or {}
    name_root = _name_root(registry, name)
    for v in _list_versions(name_root, opts):
        if content_digest(version_path(registry, name, v), storage_options=storage_options) == digest:
            if alias:
                set_alias(name, alias, v, registry, storage_options=storage_options)
            return v

    version = _write_new_version(name_root, files, opts)
    if alias:
        set_alias(name, alias, version, registry, storage_options=storage_options)
    return version


# --- migrate (D11) ---------------------------------------------------------------


def migrate(
    src_registry: str,
    dst_registry: str,
    *,
    src_storage_options: dict | None = None,
    dst_storage_options: dict | None = None,
) -> None:
    """Copy a registry tree onto a new root, re-digesting every version (D11).

    Not a schema rewrite: nothing the registry writes names its own location (D11's
    invariant), so a ref that resolved against `src_registry` resolves identically
    against `dst_registry` once callers pass the new `registry=`. A version whose
    recomputed digest disagrees with what was copied is refused, not silently accepted.
    """
    src_opts = src_storage_options or {}
    dst_opts = dst_storage_options or {}
    for name in _list_names(src_registry, src_opts):
        name_src = _name_root(src_registry, name)
        name_dst = _name_root(dst_registry, name)

        aliases_src = os.path.join(name_src, ALIASES_FILE)
        if fs.exists(aliases_src, **src_opts):
            with fs.open(aliases_src, "r", **src_opts) as f:
                raw = f.read()
            fs.write_text(os.path.join(name_dst, ALIASES_FILE), raw, **dst_opts)

        for version in _list_versions(name_src, src_opts):
            _migrate_version(
                os.path.join(name_src, f"v{version}"),
                os.path.join(name_dst, f"v{version}"),
                src_opts, dst_opts,
            )


def _migrate_version(vsrc: str, vdst: str, src_opts: dict, dst_opts: dict) -> None:
    files = _read_bundle_content(vsrc, src_opts)
    before = _digest_of(files)
    for rel, data in files:
        fs.write_bytes(os.path.join(vdst, rel), data, **dst_opts)
    after = content_digest(vdst, storage_options=dst_opts)
    if after != before:
        raise ValueError(
            f"migrate: {vsrc} -> {vdst} digest mismatch after copy (source {before}, "
            f"copied {after}) -- refusing a possibly-corrupted copy."
        )
