"""fsd's console script (spec 54 D5).

`fsd init` writes `~/.config/fsd/config.toml` (or wherever `fsd.config.config_dir()`
resolves to); `fsd config` shows the resolved values and where each came from. Both are
operator-facing tools that ship with the library -- `src/fsd/` itself never calls this
module or reads the file it writes (spec 54 D3).
"""

from __future__ import annotations

import argparse
import os
import sys

from fsd import config as fsd_config


def _cmd_init(args: argparse.Namespace) -> int:
    if args.from_env_file:
        env_values = fsd_config.parse_env_file(args.from_env_file)
        updates = {
            fsd_config.ENV_TO_KEY[env_name]: value
            for env_name, value in env_values.items()
            if env_name in fsd_config.ENV_TO_KEY
        }
    elif args.set:
        updates = {}
        for item in args.set:
            key, sep, value = item.partition("=")
            if not sep:
                print(f"fsd init --set: {item!r} is not key=value", file=sys.stderr)
                return 2
            if key not in fsd_config.KEYS:
                print(
                    f"fsd init --set: unknown key {key!r} "
                    f"(expected one of {', '.join(fsd_config.KEYS)})",
                    file=sys.stderr,
                )
                return 2
            updates[key] = value
    else:
        existing = fsd_config._read_file_values()
        updates = {}
        for key in fsd_config.KEYS:
            default = existing.get(key, "")
            prompt = f"{key} [{default}]: " if default else f"{key}: "
            entered = input(prompt).strip()
            updates[key] = entered or default

    path = fsd_config.write_config(updates)
    print(f"Wrote {path}")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    file_values = fsd_config._read_file_values()
    print(f"config file: {fsd_config.config_path()}")
    for key in fsd_config.KEYS:
        env_value = os.environ.get(fsd_config._KEY_TO_ENV[key])
        file_value = file_values.get(key)
        if env_value:
            source, value = "env", env_value
        elif file_value:
            source, value = "file", file_value
        else:
            source, value = None, None
        if source:
            print(f"  {key} = {value!r}  ({source})")
        else:
            print(f"  {key} unset")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fsd")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="write the user-level config file")
    group = init_parser.add_mutually_exclusive_group()
    group.add_argument(
        "--from-env-file", metavar="PATH",
        help="parse an env.local.sh-shaped file and write the AZ_* values it yields",
    )
    group.add_argument(
        "--set", metavar="KEY=VALUE", action="append",
        help="set one config key (repeatable); other keys are left as they are",
    )
    init_parser.set_defaults(func=_cmd_init)

    config_parser = sub.add_parser(
        "config", help="print the resolved config and where each value came from"
    )
    config_parser.set_defaults(func=_cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
