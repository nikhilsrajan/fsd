"""Spec 56 §9 step 5 -- `fsd.aml.ensure_environment`: AC4 (check-then-build), builder
stubbed throughout so no test reaches Azure (AC8)."""

from __future__ import annotations

from fsd.aml import ensure_environment
from fsd.image import ImageDefinition

DEFN = ImageDefinition(
    name="fsd-aml-env", fsd="git+https://github.com/nikhilsrajan/fsd@main",
    extras=("azure", "mpc"),
)


def _fake_git_ref(repo_url, ref):
    return "a" * 40


def _fake_base_digest(base):
    return None  # unresolved base, deterministic and network-free


def _kwargs(**overrides):
    kwargs = dict(
        resolve_base_digest=_fake_base_digest, resolve_git_ref=_fake_git_ref,
        resource_group="rg", workspace="ws",
    )
    kwargs.update(overrides)
    return kwargs


def test_no_registry_entry_builds_and_publishes(tmp_path):
    registry_root = str(tmp_path / "registry")
    calls = {"create": 0}

    def _create(name, context_dir, *, resource_group, workspace):
        calls["create"] += 1
        return "1"

    result = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=_create,
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )

    assert calls["create"] == 1
    assert result.reused is False
    assert result.version == "1"
    assert result.ref == "fsd-aml-env:1"


def test_registry_hit_with_live_asset_builds_nothing(tmp_path):
    registry_root = str(tmp_path / "registry")

    def _create(*a, **k):
        raise AssertionError("should not build: the registry entry's asset is live")

    # first call registers v1
    ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "5",
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )

    result = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=_create,
        _environment_exists=lambda *a, **k: True,
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )

    assert result.reused is True
    assert result.version == "5"
    assert result.ref == "fsd-aml-env:5"


def test_registry_hit_with_deleted_asset_builds(tmp_path):
    registry_root = str(tmp_path / "registry")
    ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "5",
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )

    calls = {"create": 0}

    def _create(name, ctx, **k):
        calls["create"] += 1
        return "6"

    result = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=_create,
        _environment_exists=lambda *a, **k: False,
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )

    assert calls["create"] == 1
    assert result.reused is False
    assert result.version == "6"


def test_force_rebuilds_even_on_a_hit(tmp_path):
    registry_root = str(tmp_path / "registry")
    ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "5",
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )

    calls = {"create": 0}

    def _create(name, ctx, **k):
        calls["create"] += 1
        return "7"

    result = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=_create,
        _environment_exists=lambda *a, **k: True,
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        force=True,
        **_kwargs(),
    )

    assert calls["create"] == 1
    assert result.reused is False
    assert result.version == "7"


# --- Opus review, 2026-08-27: the registry must follow the AML asset ---------------


def _aml_of(registry_root, ref="fsd-aml-env@current"):
    from fsd.image import registry as ireg
    return ireg.resolve(ref, registry_root).aml


def test_rebuilding_a_deleted_asset_repoints_the_registry(tmp_path):
    """`publish` is idempotent by digest, so a rebuild of an UNCHANGED definition allocates no
    new version -- without `_aml.json` the registry keeps naming the asset that was deleted,
    `ensure_environment` finds it missing again, and rebuilds a 10-20 minute image on every
    single call. Regression for exactly that loop."""
    registry_root = str(tmp_path / "registry")
    ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "5",
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )
    assert _aml_of(registry_root)["version"] == "5"

    # v5's asset is gone -> rebuild produces v6, and the registry must now say v6
    ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "6",
        _environment_exists=lambda *a, **k: False,
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )
    assert _aml_of(registry_root)["version"] == "6"

    # and the next call reuses v6 instead of rebuilding a third time
    def _explode(*a, **k):
        raise AssertionError("rebuild loop: the registry still points at the deleted asset")

    third = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=_explode,
        _environment_exists=lambda name, ver, **k: ver != "5",
        _build_link=lambda *a, **k: "https://ml.azure.com/x",
        **_kwargs(),
    )
    assert third.reused is True
    assert third.version == "6"


def test_force_rebuild_also_repoints_the_registry(tmp_path):
    """Same mechanism via the other route into a rebuild-without-a-new-version (D4's `force`)."""
    registry_root = str(tmp_path / "registry")
    ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "5",
        _build_link=lambda *a, **k: "https://ml.azure.com/x", **_kwargs(),
    )
    ensure_environment(
        DEFN, registry=registry_root, force=True,
        _create_environment=lambda name, ctx, **k: "7",
        _environment_exists=lambda *a, **k: True,
        _build_link=lambda *a, **k: "https://ml.azure.com/x", **_kwargs(),
    )
    assert _aml_of(registry_root)["version"] == "7"


def test_the_aml_sidecar_does_not_disturb_the_content_digest(tmp_path):
    """`_aml.json` sits beside `image.json`, never inside it -- so a repoint must leave the
    version resolvable by the same digest it was published under (AC5's immutability)."""
    from fsd.image import registry as ireg

    registry_root = str(tmp_path / "registry")
    first = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "5",
        _build_link=lambda *a, **k: "https://ml.azure.com/x", **_kwargs(),
    )
    ensure_environment(
        DEFN, registry=registry_root, force=True,
        _create_environment=lambda name, ctx, **k: "9",
        _build_link=lambda *a, **k: "https://ml.azure.com/x", **_kwargs(),
    )
    assert ireg.find_by_digest("fsd-aml-env", registry_root, first.digest) == 1
    assert ireg.resolve("fsd-aml-env:1", registry_root).digest == first.digest


def test_the_aml_version_and_the_registry_version_are_reported_separately(tmp_path):
    """AML numbers ASSETS, the registry numbers DEFINITIONS, and they diverge immediately:
    `verify_image(image_ref=..., registry=...)` resolves the registry's number, `environment=`
    wants AML's. Handing over the wrong one fails as a missing `v<N>` directory, so both are
    named fields rather than one ambiguous `version`."""
    from fsd.image import registry as ireg

    registry_root = str(tmp_path / "registry")
    r = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda name, ctx, **k: "5",   # AML says 5; the registry says 1
        _build_link=lambda *a, **k: "https://ml.azure.com/x", **_kwargs(),
    )
    assert (r.version, r.ref) == ("5", "fsd-aml-env:5")
    assert (r.registry_version, r.registry_ref) == (1, "fsd-aml-env:1")
    assert ireg.resolve(r.registry_ref, registry_root).digest == r.digest

    reused = ensure_environment(
        DEFN, registry=registry_root,
        _create_environment=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no build")),
        _environment_exists=lambda *a, **k: True,
        _build_link=lambda *a, **k: "https://ml.azure.com/x", **_kwargs(),
    )
    assert reused.reused is True
    assert (reused.version, reused.registry_version) == ("5", 1)
