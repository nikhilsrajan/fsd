"""Tests for `fsd.config`'s user-level config loader (spec 54, §4 criteria 3-8).

Every test that touches disk goes through `isolated_config_dir`, which points
`FSD_CONFIG_DIR` at `tmp_path` -- spec 37 §7's rule, generalised: no test may reach the
developer's real `~/.config/fsd`.
"""

from __future__ import annotations

import os

import pytest

import fsd
import fsd.config as config


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FSD_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for env_name in config._KEY_TO_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    return tmp_path


# --- AC 3: fsd.config resolves off a bare `import fsd` ------------------------------


def test_config_reachable_off_bare_import():
    assert fsd.config.load is config.load


# --- AC 4: precedence -----------------------------------------------------------------


def test_precedence_file_only(isolated_config_dir):
    config.write_config({"root": "abfss://file-root", "subscription_id": "s", "resource_group": "r",
                          "workspace": "w", "cluster": "c", "uami_client_id": "u"})
    cfg = config.load()
    assert cfg.root == "abfss://file-root"


def test_precedence_env_overrides_file(isolated_config_dir, monkeypatch):
    config.write_config({"root": "abfss://file-root", "subscription_id": "s", "resource_group": "r",
                          "workspace": "w", "cluster": "c", "uami_client_id": "u"})
    monkeypatch.setenv("AZ_ROOT", "abfss://env-root")
    cfg = config.load()
    assert cfg.root == "abfss://env-root"


def test_precedence_kwarg_overrides_env(isolated_config_dir, monkeypatch):
    config.write_config({"root": "abfss://file-root", "subscription_id": "s", "resource_group": "r",
                          "workspace": "w", "cluster": "c", "uami_client_id": "u"})
    monkeypatch.setenv("AZ_ROOT", "abfss://env-root")
    cfg = config.load(root="abfss://kwarg-root")
    assert cfg.root == "abfss://kwarg-root"


def test_precedence_empty_string_falls_through(isolated_config_dir, monkeypatch):
    config.write_config({"root": "abfss://file-root", "subscription_id": "s", "resource_group": "r",
                          "workspace": "w", "cluster": "c", "uami_client_id": "u"})
    monkeypatch.setenv("AZ_ROOT", "")
    cfg = config.load(root="")
    assert cfg.root == "abfss://file-root"


# --- AC 5: location resolution, all five D1 branches -----------------------------------


def test_config_dir_prefers_fsd_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FSD_CONFIG_DIR", str(tmp_path / "fsd-dir"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config.config_dir() == tmp_path / "fsd-dir"


def test_config_dir_falls_back_to_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("FSD_CONFIG_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config.config_dir() == tmp_path / "xdg" / "fsd"


def test_config_dir_falls_back_to_posix_default(tmp_path, monkeypatch):
    monkeypatch.delenv("FSD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path))
    assert config.config_dir() == tmp_path / ".config" / "fsd"


# D1's fifth branch -- `%APPDATA%\\fsd` when `os.name == "nt"` -- has no test on purpose:
# `pathlib.Path()` consults `os.name` at construction, so forcing it to "nt" on POSIX makes
# every `Path(...)` raise `NotImplementedError: cannot instantiate 'WindowsPath'`, including
# pytest's own. Testing it would mean a Path shim in `config_dir()` that exists only for the
# test. Verified by reading, not by assertion.


def test_config_dir_relative_fsd_config_dir_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("FSD_CONFIG_DIR", "relative/path")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path))
    assert config.config_dir() == tmp_path / ".config" / "fsd"


def test_config_dir_relative_xdg_config_home_is_ignored(tmp_path, monkeypatch):
    monkeypatch.delenv("FSD_CONFIG_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/xdg")
    monkeypatch.setattr(config.Path, "home", classmethod(lambda cls: tmp_path))
    assert config.config_dir() == tmp_path / ".config" / "fsd"


# --- AC 6: TOML round-trips -------------------------------------------------------------


def test_toml_round_trips_adversarial_values(isolated_config_dir):
    import tomllib

    values = {
        "subscription_id": 'has "quotes"',
        "resource_group": "has\\backslash",
        "workspace": "has # a hash",
        "cluster": "has\na newline",
        "uami_client_id": "has non-ascii café",
        "root": "",
    }
    # U+007F is a control character TOML forbids raw in a basic string, and it sits ABOVE the
    # printable range -- an `ord(ch) < 0x20` guard misses it and writes a file tomllib rejects.
    values["workspace"] = "has \x7f a delete"
    text = config._emit_toml(values)
    parsed = tomllib.loads(text)["azure"]
    assert parsed == {k: values[k] for k in config.KEYS}


# --- AC 7: MissingConfig names every missing key and mentions `fsd init` ---------------


def test_missing_config_lists_every_missing_key(isolated_config_dir):
    config.write_config({"root": "abfss://only-this-one"})
    with pytest.raises(config.MissingConfig) as exc:
        config.load()
    msg = str(exc.value)
    for key in ("subscription_id", "resource_group", "workspace", "cluster", "uami_client_id"):
        assert key in msg
    assert "root" not in exc.value.missing
    assert "fsd init" in msg


def test_missing_config_is_a_key_error(isolated_config_dir):
    with pytest.raises(KeyError):
        config.load()


# --- AC 7b: neither load() nor init writes to os.environ --------------------------------


def test_load_does_not_mutate_environ_reading_file(isolated_config_dir):
    config.write_config({"root": "abfss://x", "subscription_id": "s", "resource_group": "r",
                          "workspace": "w", "cluster": "c", "uami_client_id": "u"})
    before = dict(os.environ)
    config.load()
    assert dict(os.environ) == before


def test_load_does_not_mutate_environ_reading_env(isolated_config_dir, monkeypatch):
    for key, env_name in config._KEY_TO_ENV.items():
        monkeypatch.setenv(env_name, f"value-{key}")
    before = dict(os.environ)
    config.load()
    assert dict(os.environ) == before


def test_write_config_does_not_mutate_environ(isolated_config_dir):
    before = dict(os.environ)
    config.write_config({"root": "abfss://x"})
    assert dict(os.environ) == before


# --- AC 8: no test reaches the real ~/.config/fsd ---------------------------------------


def test_isolated_config_dir_is_not_the_real_one(isolated_config_dir):
    assert config.config_dir() != config.Path.home() / ".config" / "fsd"


# --- parse_env_file (moved verbatim from notebooks/_config.py) --------------------------


def test_parse_env_file_reads_quoted_and_bare_forms(tmp_path):
    f = tmp_path / "env.local.sh"
    f.write_text(
        "# a comment line\n"
        "export AZ_RG='my-rg'                 # resource group\n"
        'export AZ_ML_WORKSPACE="my-ws"       # workspace\n'
        "export AZ_CLUSTER=bare-value         # unquoted\n"
        "not an export line\n"
    )
    assert config.parse_env_file(f) == {
        "AZ_RG": "my-rg", "AZ_ML_WORKSPACE": "my-ws", "AZ_CLUSTER": "bare-value",
    }


def test_parse_env_file_skips_empty_and_derived_values(tmp_path):
    f = tmp_path / "env.local.sh"
    f.write_text(
        "export AZ_RG=''\n"
        'export AZ_DERIVED="${AZ_RG}/x"\n'
        'export AZ_FROM_CMD="$(az account show --query id -o tsv)"\n'
        "export AZ_REAL='kept'\n"
    )
    assert config.parse_env_file(f) == {"AZ_REAL": "kept"}


# --- write_config merge behaviour --------------------------------------------------------


def test_write_config_merges_over_existing_values(isolated_config_dir):
    config.write_config({"root": "abfss://first", "cluster": "c1"})
    config.write_config({"cluster": "c2"})
    values = config._read_file_values()
    assert values["root"] == "abfss://first"
    assert values["cluster"] == "c2"


def test_key_to_env_map_is_a_bijection():
    assert len(config._KEY_TO_ENV) == len(config.ENV_TO_KEY) == len(config.KEYS)
    for key, env_name in config._KEY_TO_ENV.items():
        assert config.ENV_TO_KEY[env_name] == key
