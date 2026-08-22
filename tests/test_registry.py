"""Spec 51 §9 step 0 — `fsd.model.registry`: layout, `publish`, `resolve`, `migrate`.

One test group per acceptance criterion in `specs/51-deploy-model-registry.md` §4 that step 0
owns (AC1-5, 11, 13; see `handoff-spec51-step0-registry.md`). Step 0 touches no verb, so these
tests call `registry.publish`/`resolve`/`migrate` directly rather than through `fsd.deploy`
(steps 1-3, not implemented yet).

Bundles are built with `bundle.save(joblib.Parallel, {}, ..., code=False)` — an installed class
needs no adapter module written to disk, so fixtures stay a couple of lines each. `joblib` is
already a dependency (used the same way in `tests/test_bundle_transparency.py`).
"""

from __future__ import annotations

import json
import os

import joblib
import pytest

from fsd.model import bundle, registry
from fsd.storage import fs


def _make_bundle(tmp_path, subdir="src_bundle", requirements=None) -> str:
    return bundle.save(
        joblib.Parallel, {}, str(tmp_path / subdir), code=False,
        requirements=requirements, verbose=False,
    )


def _rewrite_bundle_field(bundle_path: str, **fields) -> None:
    """Mutate bundle.json in place so two fixture bundles differ in content."""
    manifest_path = os.path.join(bundle_path, bundle.BUNDLE_MANIFEST)
    with open(manifest_path) as f:
        manifest = json.load(f)
    manifest.update(fields)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)


# --- AC1: publish + resolve round-trip ------------------------------------------------


def test_publish_creates_v1_and_resolve_finds_it(tmp_path):
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")

    version = registry.publish(src, "crop-rf", registry_root)

    assert version == 1
    v1 = registry.version_path(registry_root, "crop-rf", 1)
    assert fs.exists(os.path.join(v1, bundle.BUNDLE_MANIFEST))

    resolved = registry.resolve("crop-rf:1", registry_root)
    assert resolved == registry.Resolved("crop-rf", 1, v1)


# --- AC2: identical content twice is idempotent -----------------------------------------


def test_publish_identical_content_twice_is_idempotent(tmp_path):
    src = _make_bundle(tmp_path)
    registry_root = str(tmp_path / "registry")

    v1 = registry.publish(src, "crop-rf", registry_root)
    before = fs.ls(os.path.join(registry_root, "crop-rf"))

    v2 = registry.publish(src, "crop-rf", registry_root)
    after = fs.ls(os.path.join(registry_root, "crop-rf"))

    assert v2 == v1
    assert len(after) == len(before)


# --- AC3: changed content creates v2; v1 untouched --------------------------------------


def test_publish_changed_content_creates_v2_and_leaves_v1_untouched(tmp_path):
    registry_root = str(tmp_path / "registry")
    src1 = _make_bundle(tmp_path, "src1")
    v1 = registry.publish(src1, "crop-rf", registry_root)
    assert v1 == 1

    src2 = _make_bundle(tmp_path, "src2")
    _rewrite_bundle_field(src2, feature={"kind": "callable", "steps": ["different"]})
    v2 = registry.publish(src2, "crop-rf", registry_root)
    assert v2 == 2

    v1_path = registry.version_path(registry_root, "crop-rf", 1)
    with fs.open(os.path.join(v1_path, bundle.BUNDLE_MANIFEST), "r") as f:
        v1_manifest = json.load(f)
    with open(os.path.join(src1, bundle.BUNDLE_MANIFEST)) as f:
        src1_manifest = json.load(f)
    assert v1_manifest == src1_manifest


# --- step 2 follow-through: publish's idempotency check reads a stored digest first ----


def test_publish_idempotency_uses_stored_deploy_digest_without_recomputing_content(
    tmp_path, monkeypatch,
):
    """Once a version carries `_deploy.json` (written by `deploy`, spec 51 D7), re-publishing
    identical content must not re-digest that version's bytes -- it reads the small stored
    digest instead (`registry.publish`'s own docstring, "known follow-through" in the step-2
    handoff)."""
    registry_root = str(tmp_path / "registry")
    src = _make_bundle(tmp_path)
    v1 = registry.publish(src, "crop-rf", registry_root)
    v1_path = registry.version_path(registry_root, "crop-rf", v1)
    digest = registry.content_digest(v1_path)
    registry.write_deploy_record(
        "crop-rf", v1, {"name": "crop-rf", "version": v1, "digest": digest}, registry_root,
    )

    def _forbidden(*a, **kw):
        raise AssertionError("content_digest recomputed despite a stored _deploy.json digest")

    monkeypatch.setattr(registry, "content_digest", _forbidden)

    again = registry.publish(src, "crop-rf", registry_root)

    assert again == v1


# --- step 2 follow-through: migrate carries a version's _deploy.json across ------------


def test_migrate_carries_the_deploy_record_across(tmp_path):
    src_root = str(tmp_path / "src_registry")
    dst_root = str(tmp_path / "dst_registry")
    src = _make_bundle(tmp_path)
    v1 = registry.publish(src, "crop-rf", src_root)
    record = {"name": "crop-rf", "version": v1, "digest": "sha256:deadbeef"}
    registry.write_deploy_record("crop-rf", v1, record, src_root)

    registry.migrate(src_root, dst_root)

    dst_version = registry.resolve("crop-rf:1", dst_root).path
    with open(os.path.join(dst_version, registry.DEPLOY_FILE)) as f:
        assert json.load(f) == record


# --- AC4: atomic publish (staging + rename, no partial version) ------------------------


def test_publish_leaves_no_partial_version_if_the_copy_fails_midway(tmp_path, monkeypatch):
    # An artifact is added so the bundle has 2 files (bundle.json + artifact) -- the
    # simulated failure below must land on the SECOND write for this test to mean anything.
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"weights")
    src = bundle.save(
        joblib.Parallel, {"model": str(artifact)}, str(tmp_path / "src_bundle_2files"),
        code=False, verbose=False,
    )
    registry_root = str(tmp_path / "registry")

    real_write_bytes = fs.write_bytes
    calls = {"n": 0}

    def flaky_write_bytes(path, data, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated failure mid-copy")
        return real_write_bytes(path, data, **kw)

    monkeypatch.setattr(registry.fs, "write_bytes", flaky_write_bytes)

    with pytest.raises(OSError):
        registry.publish(src, "crop-rf", registry_root)

    assert not fs.exists(registry.version_path(registry_root, "crop-rf", 1))
    # no leftover staging directory either
    if fs.exists(os.path.join(registry_root, "crop-rf")):
        leftovers = fs.ls(os.path.join(registry_root, "crop-rf"))
        assert not any(".staging-" in entry for entry in leftovers)


# --- AC5: alias set on publish; re-deploy with same alias just repoints ----------------


def test_alias_write_and_repoint_touches_no_version(tmp_path):
    registry_root = str(tmp_path / "registry")
    src1 = _make_bundle(tmp_path, "src1")
    v1 = registry.publish(src1, "crop-rf", registry_root, alias="champion")

    aliases_path = os.path.join(registry_root, "crop-rf", registry.ALIASES_FILE)
    with fs.open(aliases_path, "r") as f:
        assert json.load(f) == {"champion": 1}

    src2 = _make_bundle(tmp_path, "src2")
    _rewrite_bundle_field(src2, feature={"kind": "callable", "steps": ["v2"]})
    v2 = registry.publish(src2, "crop-rf", registry_root, alias="champion")
    assert v2 == v1 + 1

    with fs.open(aliases_path, "r") as f:
        assert json.load(f) == {"champion": 2}

    # both versions are exactly what was published, untouched by the alias write
    for v, src in ((v1, src1), (v2, src2)):
        vpath = registry.version_path(registry_root, "crop-rf", v)
        with fs.open(os.path.join(vpath, bundle.BUNDLE_MANIFEST), "r") as f:
            got = json.load(f)
        with open(os.path.join(src, bundle.BUNDLE_MANIFEST)) as f:
            want = json.load(f)
        assert got == want

    resolved = registry.resolve("crop-rf@champion", registry_root)
    assert resolved.version == 2


def test_set_alias_rejects_a_vN_shaped_name(tmp_path):
    registry_root = str(tmp_path / "registry")
    src = _make_bundle(tmp_path)
    registry.publish(src, "crop-rf", registry_root)

    with pytest.raises(ValueError, match="shadowed"):
        registry.set_alias("crop-rf", "v7", 1, registry_root)


def test_bare_name_ref_is_rejected_naming_both_forms(tmp_path):
    with pytest.raises(ValueError, match="name:version.*name@alias|name@alias.*name:version"):
        registry.resolve("crop-rf", str(tmp_path / "registry"))


# --- AC11: alias resolution costs exactly one read, never lists ------------------------


def test_resolve_alias_costs_exactly_one_read_and_never_lists(tmp_path, monkeypatch):
    registry_root = str(tmp_path / "registry")
    src = _make_bundle(tmp_path)
    registry.publish(src, "crop-rf", registry_root, alias="champion")

    counts = {"open": 0, "ls": 0}
    real_open, real_ls = fs.open, fs.ls

    def counting_open(*a, **kw):
        counts["open"] += 1
        return real_open(*a, **kw)

    def counting_ls(*a, **kw):
        counts["ls"] += 1
        return real_ls(*a, **kw)

    monkeypatch.setattr(registry.fs, "open", counting_open)
    monkeypatch.setattr(registry.fs, "ls", counting_ls)

    resolved = registry.resolve("crop-rf@champion", registry_root)

    assert resolved.version == 1
    assert counts["open"] == 1
    assert counts["ls"] == 0


def test_resolve_version_pin_costs_no_reads_and_never_lists(tmp_path, monkeypatch):
    registry_root = str(tmp_path / "registry")
    src = _make_bundle(tmp_path)
    registry.publish(src, "crop-rf", registry_root)

    counts = {"open": 0, "ls": 0}
    real_open, real_ls = fs.open, fs.ls
    monkeypatch.setattr(registry.fs, "open", lambda *a, **kw: (counts.__setitem__("open", counts["open"] + 1), real_open(*a, **kw))[1])
    monkeypatch.setattr(registry.fs, "ls", lambda *a, **kw: (counts.__setitem__("ls", counts["ls"] + 1), real_ls(*a, **kw))[1])

    for ref in ("crop-rf:1", "crop-rf@v1"):
        resolved = registry.resolve(ref, registry_root)
        assert resolved.version == 1

    assert counts["open"] == 0
    assert counts["ls"] == 0


# --- AC13: relocatable (no self-reference) + migrate ------------------------------------


def test_no_written_file_contains_the_registry_root(tmp_path):
    registry_root = str(tmp_path / "registry")
    src1 = _make_bundle(tmp_path, "src1")
    src2 = _make_bundle(tmp_path, "src2")
    _rewrite_bundle_field(src2, feature={"kind": "callable", "steps": ["v2"]})
    registry.publish(src1, "crop-rf", registry_root, alias="champion")
    registry.publish(src2, "crop-rf", registry_root, alias="champion")

    root_str = str(tmp_path)
    for path, _size in fs.find_sizes(registry_root).items():
        if not (path.endswith(".json") or os.path.basename(path).startswith("_")):
            continue
        with open(path, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
        assert root_str not in text
        assert "://" not in text


def test_migrate_copies_registry_and_refs_resolve_identically(tmp_path):
    src_root = str(tmp_path / "src_registry")
    dst_root = str(tmp_path / "dst_registry")

    b1 = _make_bundle(tmp_path, "b1")
    b2 = _make_bundle(tmp_path, "b2")
    _rewrite_bundle_field(b2, feature={"kind": "callable", "steps": ["v2"]})
    registry.publish(b1, "crop-rf", src_root, alias="champion")
    registry.publish(b2, "crop-rf", src_root, alias="latest")

    registry.migrate(src_root, dst_root)

    for ref in ("crop-rf:1", "crop-rf:2", "crop-rf@champion", "crop-rf@latest"):
        want = registry.resolve(ref, src_root)
        got = registry.resolve(ref, dst_root)
        assert got.version == want.version

        want_digest = registry.content_digest(want.path)
        got_digest = registry.content_digest(got.path)
        assert got_digest == want_digest


def test_migrate_refuses_a_corrupted_copy(tmp_path, monkeypatch):
    src_root = str(tmp_path / "src_registry")
    dst_root = str(tmp_path / "dst_registry")
    src = _make_bundle(tmp_path)
    registry.publish(src, "crop-rf", src_root)

    real_write_bytes = fs.write_bytes

    def corrupting_write_bytes(path, data, **kw):
        if path.endswith(bundle.BUNDLE_MANIFEST) and "dst_registry" in path:
            manifest = json.loads(data.decode("utf-8"))
            manifest["corrupted"] = True
            data = json.dumps(manifest).encode("utf-8")
        return real_write_bytes(path, data, **kw)

    monkeypatch.setattr(registry.fs, "write_bytes", corrupting_write_bytes)

    with pytest.raises(ValueError, match="digest mismatch"):
        registry.migrate(src_root, dst_root)


# --- publish races: a loser must never be handed the winner's version ------------------


def _publish_racing_with(monkeypatch, competitor, mine, registry_root, name="crop-rf"):
    """Run `publish(mine)` while a competitor completes the version `publish` is about to
    claim, in the window the `exists` pre-check leaves open. The competitor publishes ONCE
    (a real one is not an infinite adversary). Returns the reported version."""
    real_rename = fs.rename
    raced = []

    def racy_rename(src, dst, **kw):
        if not raced:
            raced.append(dst)
            for rel, data in registry._read_bundle_content(competitor, None):
                fs.write_bytes(os.path.join(dst, rel), data)
        return real_rename(src, dst, **kw)

    monkeypatch.setattr(registry.fs, "rename", racy_rename)
    return registry.publish(mine, name, registry_root)


def test_publish_losing_a_race_retries_instead_of_returning_the_winners_version(
    tmp_path, monkeypatch,
):
    """The `exists` check is not a lock. If a competitor finishes v1 before our rename,
    `publish` must not report v1 -- v1 holds their bundle, and a caller that then resolved
    `crop-rf:1` would run a model it never published (D2, and §5's "fail rather than
    corrupt")."""
    registry_root = str(tmp_path / "registry")
    theirs = _make_bundle(tmp_path, "theirs")
    mine = _make_bundle(tmp_path, "mine")
    _rewrite_bundle_field(mine, feature={"kind": "callable", "steps": ["mine"]})

    version = _publish_racing_with(monkeypatch, theirs, mine, registry_root)

    assert version == 2
    mine_path = registry.version_path(registry_root, "crop-rf", version)
    assert registry.content_digest(mine_path) == registry.content_digest(mine)

    v1 = registry.version_path(registry_root, "crop-rf", 1)
    assert registry.content_digest(v1) == registry.content_digest(theirs)
    assert not any(registry._STAGING_PREFIX in entry for entry in fs.ls(v1))


def test_publish_losing_a_race_to_identical_content_is_still_idempotent(
    tmp_path, monkeypatch,
):
    """Same race, but the competitor published the same bytes -- that is D2's idempotency
    arriving by another route, so their version is the right answer to return."""
    registry_root = str(tmp_path / "registry")
    src = _make_bundle(tmp_path, "src")

    version = _publish_racing_with(monkeypatch, src, src, registry_root)

    assert version == 1
    assert fs.ls(os.path.join(registry_root, "crop-rf")) == [
        registry.version_path(registry_root, "crop-rf", 1)
    ]


# --- alias writes are never observed half-written --------------------------------------


def test_set_alias_publishes_by_rename_so_a_reader_never_sees_a_partial_file(
    tmp_path, monkeypatch,
):
    """`resolve` reads `_aliases.json` and nothing else (D9), so promoting against a live
    fan-out must leave no window where that read sees a half-written file: the new content
    is staged and renamed onto the name, never written over it in place."""
    registry_root = str(tmp_path / "registry")
    src = _make_bundle(tmp_path)
    registry.publish(src, "crop-rf", registry_root)
    registry.set_alias("crop-rf", "champion", 1, registry_root)

    aliases_path = os.path.join(registry_root, "crop-rf", registry.ALIASES_FILE)
    written = []
    real_write_bytes = fs.write_bytes

    def spy_write_bytes(path, data, **kw):
        written.append(path)
        return real_write_bytes(path, data, **kw)

    monkeypatch.setattr(registry.fs, "write_bytes", spy_write_bytes)
    registry.set_alias("crop-rf", "current", 1, registry_root)
    monkeypatch.undo()

    assert aliases_path not in written
    assert any(registry._STAGING_PREFIX in p for p in written)
    with fs.open(aliases_path, "r") as f:
        assert json.load(f) == {"champion": 1, "current": 1}
    assert not any(
        registry._STAGING_PREFIX in entry
        for entry in fs.ls(os.path.join(registry_root, "crop-rf"))
    )
