"""Tests for `fsd.cli` (spec 54 D5). `main()` is called with an argv list, never shelled
out to -- the `fsd` console script itself is exercised manually (AC 1/2), not here.
"""

from __future__ import annotations

import os

import pytest

import fsd.config as config
from fsd.cli import main


@pytest.fixture
def isolated_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FSD_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for env_name in config._KEY_TO_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    return tmp_path


def test_init_set_writes_named_keys_only(isolated_config_dir, capsys):
    rc = main(["init", "--set", "root=abfss://x", "--set", "cluster=c1"])
    assert rc == 0
    values = config._read_file_values()
    assert values["root"] == "abfss://x"
    assert values["cluster"] == "c1"
    assert values["subscription_id"] == ""
    out = capsys.readouterr().out
    assert str(config.config_path()) in out


def test_init_set_rejects_unknown_key(isolated_config_dir, capsys):
    rc = main(["init", "--set", "not_a_key=x"])
    assert rc != 0
    assert not config.config_path().exists()


def test_init_set_rejects_malformed_pair(isolated_config_dir):
    rc = main(["init", "--set", "no-equals-sign"])
    assert rc != 0


def test_init_from_env_file_maps_az_names_to_keys(isolated_config_dir, tmp_path):
    f = tmp_path / "env.local.sh"
    f.write_text(
        "export AZ_ROOT='abfss://from-file'\n"
        "export AZ_CLUSTER='c-from-file'\n"
    )
    rc = main(["init", "--from-env-file", str(f)])
    assert rc == 0
    values = config._read_file_values()
    assert values["root"] == "abfss://from-file"
    assert values["cluster"] == "c-from-file"


def test_init_merges_over_existing_values(isolated_config_dir):
    main(["init", "--set", "root=abfss://first", "--set", "cluster=c1"])
    main(["init", "--set", "cluster=c2"])
    values = config._read_file_values()
    assert values["root"] == "abfss://first"
    assert values["cluster"] == "c2"


def test_config_reports_provenance(isolated_config_dir, monkeypatch, capsys):
    main(["init", "--set", "root=abfss://from-file"])
    monkeypatch.setenv("AZ_CLUSTER", "c-from-env")
    rc = main(["config"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "root = 'abfss://from-file'  (file)" in out
    assert "cluster = 'c-from-env'  (env)" in out
    assert "subscription_id unset" in out


def test_init_from_env_file_does_not_mutate_environ(isolated_config_dir, tmp_path):
    """AC 7b's third case: the write path leaves the caller's environment alone.

    `--from-env-file` is the one `init` form that reads `AZ_*`-shaped names off disk, so it is
    the one most likely to grow a "helpful" `os.environ` export later (spec 54 D4).
    """
    f = tmp_path / "env.local.sh"
    f.write_text("export AZ_ROOT='abfss://from-file'\nexport AZ_CLUSTER='c-from-file'\n")
    before = dict(os.environ)
    assert main(["init", "--from-env-file", str(f)]) == 0
    assert dict(os.environ) == before


def test_init_interactive_prompts_and_keeps_existing_on_empty_input(
    isolated_config_dir, monkeypatch, capsys
):
    """D5's primary form: prompt per key, existing value shown as the default and kept on Enter."""
    main(["init", "--set", "root=abfss://existing", "--set", "cluster=c-existing"])
    capsys.readouterr()
    prompts, answers = [], {"subscription_id": "s-typed", "workspace": "w-typed"}

    def fake_input(prompt):
        prompts.append(prompt)
        key = prompt.split(" ")[0].rstrip(":")
        return answers.get(key, "")          # Enter on everything else

    monkeypatch.setattr("builtins.input", fake_input)
    assert main(["init"]) == 0
    values = config._read_file_values()
    assert values["subscription_id"] == "s-typed"
    assert values["workspace"] == "w-typed"
    assert values["root"] == "abfss://existing"      # kept on empty input
    assert values["cluster"] == "c-existing"
    assert [p for p in prompts if p.startswith("root")] == ["root [abfss://existing]: "]
    assert len(prompts) == len(config.KEYS)


def test_init_never_prints_a_pre_existing_value(isolated_config_dir, capsys):
    """`fsd init` prints only the path written, never a value -- D5's rule against echoing
    a value it did not just receive from the user."""
    main(["init", "--set", "root=abfss://secret-looking-value"])
    capsys.readouterr()
    main(["init", "--set", "cluster=c2"])
    out = capsys.readouterr().out
    assert "abfss://secret-looking-value" not in out
