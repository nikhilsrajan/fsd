---
status: current
summary: A pip-install consumer cannot bootstrap config — `env.example.sh` is not in the wheel and `notebooks/_config.py` crashes at import outside a checkout. Replace both with a user-level `~/.config/fsd/config.toml`, written by a new `fsd init` console script and read by an explicit `fsd.config.load()`. Seven decisions. Overturns spec 41 D7's bootstrap while preserving its actual invariant.
---

# Spec 54 — user-level config and `fsd init`

**Status:** **SIGNED OFF (user, 2026-08-26)** — §7's single question resolved at its recommended
proposal (`[azure]` + lowercase keys). Not implemented. · **Opened:** 2026-08-26
**Closes:** [#78](https://github.com/nikhilsrajan/fsd/issues/78)
**Origin:** the first two hard stops in
[`docs/findings/consumer-repo-friction.md`](../docs/findings/consumer-repo-friction.md), observed
2026-08-26 while standing up `rise/` — a separate repository consuming fsd as an installed
dependency (phase 2).
**Blocks:** the phase-2 consumer notebook. **Related:**
[#80](https://github.com/nikhilsrajan/fsd/issues/80) (dep trim, lands first),
[#82](https://github.com/nikhilsrajan/fsd/issues/82) (the `v0.1.0` tag, lands after the consumer
notebook works).
**Implementation:** Sonnet `/effort medium` against this spec once signed off (CLAUDE.md model
split). §9 is the build order.

---

## 1. The problem

fsd's config bootstrap is reachable only from a git checkout. Both halves fail for a consumer.

**The template is not in the package.** `env.example.sh` lives at the fsd repo root. The wheel's
`RECORD` contains `fsd/**` and `fsd-0.1.0.dist-info/**` and nothing else — `packages.find where =
["src"]` sees to that. The documented bootstrap, `cp env.example.sh env.local.sh`, copies a file
out of a checkout the consumer does not have. Nothing a consumer reads even names the file:
`README.md`'s install section does not mention it; `docs/howto/run-at-scale.md` does, once, in a
prerequisites bullet — a developer document.

**The loader crashes on import.**

```python
# notebooks/_config.py:70 — module scope
REPO = find_repo()
NOTEBOOKS = REPO / "notebooks"
ENV_LOCAL = REPO / "env.local.sh"
```

`find_repo()` walks upward for `pyproject.toml` **and** `src/fsd/`. A consumer repo has neither, so
copying `_config.py` next to the notebook does not rescue it — `from _config import load` raises
`RuntimeError` before any cell body runs.

The failure is circular by construction: `env_local()`'s `FileNotFoundError` says
`cp {REPO}/env.example.sh {path}`, where `REPO` is the thing that could not be found.

**What is *not* the problem.** The six values are **addresses, not secrets** — a subscription id, a
resource group, a workspace, a cluster, a managed-identity client id, a storage root. The actual
credential is `az login` + `DefaultAzureCredential`, and nothing here changes that. This spec moves
addresses; it does not introduce credential storage. (#78, user, 2026-08-21.)

## 2. Scope

**In:**

- A user-level config file, its location rule, and its schema.
- `fsd.config.load()` — the read path, with a documented precedence.
- `fsd init` — fsd's first console script, and the write path.
- Retiring `env.example.sh` and the config half of `notebooks/_config.py`, including the two tests
  that pin them.
- Updating `notebooks/e2e_austria_aml.ipynb` and `notebooks/00_build_images.ipynb` to the new call.

**Out:**

- **Any implicit read by the library.** See D3 — this is the invariant, not an omission.
- Credential storage of any kind. `az login` remains the auth path.
- Multiple named profiles / environments (`az`'s `--profile`, `gcloud`'s configurations). One
  config, one set of values. A second platform is a reason to revisit, not to pre-build.
- Non-Azure config keys. The schema has one section because fsd has one cloud today.
- The consumer repo's own `requirements.txt`, notebook, or how-to — those are the user's, and are
  written after this lands.
- **`rise init`** — a *project*-level scaffold, one layer above `fsd init`: stand up a consumer
  repo (requirements pinning fsd, a starter notebook, the config call already wired). Wanted, and
  explicitly deferred (user, 2026-08-26). It belongs to `rise`, not to fsd, and it should be
  designed against a consumer notebook that already exists rather than ahead of one. `fsd init`
  must not grow scaffolding options in anticipation of it.

## 3. Decisions

### D1 — The config lives at a user-level path, with a dedicated override variable

Resolution order for the config **directory**:

1. `$FSD_CONFIG_DIR`, if set and absolute.
2. `$XDG_CONFIG_HOME/fsd`, if `XDG_CONFIG_HOME` is set and absolute.
3. POSIX: `~/.config/fsd`. Windows: `%APPDATA%\fsd`.

The file is `config.toml` inside it. A relative path in either variable is **ignored, not
resolved** — the XDG spec's own rule ("if an implementation encounters a relative path in any of
these variables it should consider the path invalid and ignore it"), which prevents a stray
`FSD_CONFIG_DIR=.` from silently writing into whatever directory a notebook kernel started in.

*Why user-level at all:* it makes the gitignore problem disappear rather than become fsd's to
manage. `env.local.sh` is gitignored in the fsd checkout; in a consumer repo nobody has written
that rule yet, and the first person to commit their filled-in copy leaks a live storage URL. A path
outside every project tree cannot be committed by accident.

*Why a dedicated `FSD_CONFIG_DIR` rather than XDG alone:* both CLIs fsd sits next to do exactly
this — Azure CLI reads `$AZURE_CONFIG_DIR` (default `$HOME/.azure`), gcloud reads `$CLOUDSDK_CONFIG`
(default `~/.config/gcloud`). A tool-specific override is what makes CI and container images
workable without touching a user-wide variable. Note the two disagree on the default, which is why
XDG is honoured as the *second* step rather than treated as universal.

### D2 — TOML, read with stdlib `tomllib`, written by fsd's own emitter

Schema — one section, six string keys, no nesting beyond it:

```toml
# ~/.config/fsd/config.toml — written by `fsd init`.
# These are addresses, not secrets. Your credential is `az login`.
[azure]
subscription_id = ""
resource_group  = ""
workspace       = ""
cluster         = ""
uami_client_id  = ""
root            = ""
```

Reading is `tomllib.load` — stdlib since 3.11, and fsd already requires `>=3.11`.

**Writing is a ~20-line emitter in `fsd/config.py`, not a new dependency.** `tomllib` "does not
support writing TOML" and the stdlib docs point at `tomli-w`. Taking that dependency to emit six
flat strings would be moving in the wrong direction while [#80](https://github.com/nikhilsrajan/fsd/issues/80)
is removing 53 packages. The emitter writes TOML basic strings and escapes exactly what the TOML
spec requires of them — backslash and double-quote, plus the control characters — which is
tractable precisely because the schema is closed and flat. A round-trip test (`emit` → `tomllib.load`
→ compare) over a table of adversarial values is the guard, and it is cheap.

If the schema ever gains nesting, arrays, or user-supplied keys, this decision is revisited and
`tomli-w` is the answer. Say so in the emitter's docstring.

**Why not simply keep the shell format** (asked at sign-off, 2026-08-26 — recorded because the
next reader will ask it too). The env file was fine while a **human** wrote it and a **shell** read
it. `fsd init` breaks both halves of that:

1. **A shell file cannot be read safely, only parsed.** `_config.env_local` already refuses to
   `source` — sourcing runs arbitrary shell from a file whose purpose is holding
   credential-adjacent values — so it hand-wrote `_EXPORT_RE`. That regex has already carried a
   real defect: it anchored the value to end-of-line, so every line with a trailing comment failed
   to match and a fully filled-in file was reported as empty. Its docstring records this. A format
   that needs a bespoke parser we own and must keep correct loses to one whose parser is in the
   standard library.
2. **Writing shell is much harder than reading it.** Shell quoting has real edge cases — a value
   containing a single quote inside single quotes needs `'\''` — and a mis-quoted shell file is
   *not* a parse error. It is a file that silently means something else, or that executes something
   when sourced. TOML basic-string escaping is a backslash and a double quote. The risk is
   asymmetric and it appears only now, because nothing generated `env.local.sh` before.
3. **The shell affordance is already unused where it matters.** `source env.local.sh` is the
   format's one genuine advantage, and a notebook — the consumer's entry point — sources nothing.
   `_config.py` exists precisely because of that. The file is already being parsed rather than
   executed everywhere it is actually read.
4. **And D4 keeps that affordance anyway.** The bare `AZ_*` names sit *above* the file in
   precedence, so `source env.local.sh` still overrides `config.toml` for anything launched from
   that shell, and every run-book that exports these keeps working. The `source`-ability moves out
   of the file format and into the precedence rule, where it costs nothing.
5. **Cross-platform and room to grow.** `export FOO=bar` means nothing to PowerShell, and a section
   header is free in TOML — in a flat env file the only namespacing is a name prefix, which is why
   everything is called `AZ_*` today.

### D3 — `load()` is explicit; the library still never reads config on its own

```python
import fsd
cfg = fsd.config.load()
fsd.download(..., dst_folderpath=f"{cfg.root}/imagery", ...)
```

`fsd.download`, `fsd.create_training_data` and `fsd.run_inference` gain **no** config awareness.
They keep taking every storage location as an argument, and they keep failing loudly when one is
missing.

This is the part of spec 41 D7 that survives, and it is the important part: *"`src/fsd/` never
reads the environment for a storage location; it takes one as an argument."* What D7 got wrong was
the **bootstrap** — putting the template at a repo root, and the loader in `notebooks/`. The
operator/library line is redrawn one level up: `fsd.config` is an **operator-facing helper that
ships with the library**, and calling it is the operator's explicit act.

A library that resolves its own storage root from ambient state is a library whose behaviour
depends on which machine it runs on. Every fan-out node would inherit whatever the driver's
`$HOME` happened to hold. `load()` at the top of a notebook, passing values down, keeps the seam
where spec 41 wanted it.

### D4 — Precedence: explicit argument, then environment, then file

For each of the six values, `load()` takes the first that is set and non-empty:

1. an explicit keyword to `load()` (`load(root="abfss://…")`) — for tests and scripted overrides;
2. the bare `AZ_*` environment variable — `AZ_SUBSCRIPTION_ID`, `AZ_RG`, `AZ_ML_WORKSPACE`,
   `AZ_CLUSTER`, `AZ_UAMI_CLIENT_ID`, `AZ_ROOT`;
3. the corresponding key in `[azure]`.

This mirrors the Azure CLI's own documented order (command-line parameters → environment variables
→ values in the configuration file), which is the ordering an operator already has in their hands.

**Keeping the bare `AZ_*` names is deliberate**, not inherited by accident. A developer who already
does `source env.local.sh` gets the new `load()` working with zero migration, run-books that
`export AZ_ROOT=…` keep working unchanged, and the AML node path — which sets `AZURE_CLIENT_ID` and
friends in the job environment — is unaffected. The names are already the project's vocabulary,
documented in `docs/reference/environment.md`.

### D5 — `fsd init` is fsd's first console script

```toml
[project.scripts]
fsd = "fsd.cli:main"
```

A `console_scripts` entry point; the installer generates a wrapper that calls `main()` and exits on
its return value, so `main()` returns `int` (`0` = success).

`src/fsd/cli.py`, stdlib `argparse`, two subcommands:

| command | behaviour |
|---|---|
| `fsd init` | interactive prompt for the six values; existing values shown as defaults and kept on empty input; writes `config.toml`; prints the path written |
| `fsd init --from-env-file PATH` | non-interactive: parse an `env.local.sh` and write the six values it yields. The migration path for everyone who already has one |
| `fsd init --set key=value …` | non-interactive: set named keys, leave the rest. For CI and containers |
| `fsd config` | print the resolved value of each key **and where it came from** (`arg` / `env` / `file` / *unset*), plus the config path |

`fsd config` earns its place: with three sources, "why is it using that root?" is otherwise
unanswerable, and a stale `export AZ_ROOT` in a shell profile silently outranking the file is
exactly the bug this design invites. Print provenance, and it is a five-second diagnosis.

`--from-env-file` reuses `_config.py`'s `_EXPORT_RE` verbatim, including its documented handling of
trailing comments and its skipping of values containing `$`. That parser is battle-tested — the
comment case is in its docstring *because* an earlier anchor made every line fail to match — so it
moves into `fsd/config.py` rather than being rewritten.

`fsd init` **never prints a value it did not just receive from the user**, and `fsd config`'s
output is subject to the identifier sweep like any other output. Neither writes to a log.

### D6 — `env.example.sh` and `notebooks/_config.py` are retired, and so are their two tests

- **`env.example.sh` — deleted.** Its job was to be copied and filled in; `fsd init` now does that,
  and a template a consumer cannot reach is worse than no template. `docs/reference/environment.md`
  remains the complete decode ring and is where the six are documented.
- **`notebooks/_config.py` — deleted.** The config half moves to `fsd.config`. Its checkout-path
  helpers (`REPO`, `NOTEBOOKS`) are replaced in the two fsd notebooks by a two-line
  `pathlib` cell: those notebooks are developer artifacts that genuinely do live in the checkout,
  so `Path.cwd()` with an assert is honest where `find_repo()` was over-engineered.
- **`tests/test_docs.py::test_env_example_declares_exactly_the_notebook_vars` — deleted** with the
  file it pins. `test_az_vars_are_documented` stays and is **extended**: every key in
  `fsd.config`'s field list must appear in `docs/reference/environment.md`. The parity contract
  survives; only its left-hand side changes from a shell template to the schema.
- **`tests/test_notebooks.py`** loses its five `_config` tests (they move to `tests/test_config.py`,
  rewritten against the new module) and keeps both leak guards. The guard asserting
  `"_config" in src` becomes an assertion that the notebook calls `fsd.config.load()` — its purpose
  is unchanged: *no notebook may carry a literal identifier*.

`docs/howto/run-at-scale.md` and `docs/howto/build-the-images.md` reference `env.example.sh` and
must be updated in the same commit; both are "dated"-tier documents, so update the prerequisite
lines, do not rewrite the documents.

### D7 — A missing value names every gap at once, and names the fix

```
fsd.config.MissingConfig: cluster, uami_client_id, root — not set.

  Run `fsd init` to fill them in (writes ~/.config/fsd/config.toml),
  or set AZ_CLUSTER, AZ_UAMI_CLIENT_ID, AZ_ROOT in your environment.

  These are addresses, not secrets — your credential is `az login`.
  Concrete values come from your platform admin. See docs/reference/environment.md.
```

Reporting **all** missing names at once is inherited from `_config.load` and kept for its stated
reason: filling one blank, re-running a cell, and being told about the next is a bad loop when each
round trip is a notebook cell. A missing *file* is not a distinct error class — an absent file is
simply six unset values, reported the same way, which removes the `FileNotFoundError` branch
entirely.

`MissingConfig` subclasses `KeyError` so existing `except KeyError` in a notebook still catches it.

## 4. Acceptance criteria

1. **The consumer case works.** In a venv with fsd installed from a git URL and **no fsd checkout
   anywhere on the path**: `fsd init --from-env-file <a temp env file>` writes the file, and
   `python -c "import fsd; print(fsd.config.load().root)"` prints the value. This is the criterion
   #78 exists for; it must be exercised from a directory with no `pyproject.toml` above it.
2. `fsd --help`, `fsd init --help` and `fsd config` all run after a plain `pip install`.
3. `import fsd; fsd.config.load` resolves without a separate `from fsd import config` — `config` is
   imported in `fsd/__init__.py`.
4. **Precedence is tested at each level**: file only; env overriding file; explicit kwarg
   overriding env; and an empty-string value at one level correctly falling through to the next.
5. **Location resolution is tested for all five branches** of D1, including the relative-path
   rejection for both variables.
6. **TOML round-trips**: emit → `tomllib.load` → equal, over a table including a value with `"`, one
   with `\`, one with a `#`, one with a newline, one with non-ASCII, and one empty.
7. `MissingConfig` lists **every** missing key in one message and mentions `fsd init`.
8. **No test requires Azure, a network, or a filesystem outside `tmp_path`.** `FSD_CONFIG_DIR` is
   pointed at `tmp_path` via `monkeypatch`; no test may touch the developer's real `~/.config/fsd`.
   This is spec 37 §7's rule and it is the one most easily broken here.
9. `pytest -q` and `ruff check src/ tests/` clean. `tests/test_notebooks.py`'s leak guards still
   pass against both tracked notebooks, and both notebooks still have no saved outputs.
10. The identifier sweep (`RECIPES.md`) is clean before the branch is pushed — this change touches
    two notebooks and two how-tos.

## 5. Risks

- **A stale `AZ_*` export silently outranks the file.** D4 chose env-over-file to make migration
  free, and the cost is this. Mitigated by `fsd config` printing provenance (D5); accepted because
  the alternative — file-over-env — breaks every run-book that exports these.
- **Hand-rolled TOML emission.** Accepted for a closed, flat, six-string schema, guarded by the
  round-trip test (§4.6), and reversible: swapping in `tomli-w` is a one-function change. The
  docstring must say so, or a later reader will widen the schema without noticing the constraint.
- **`fsd` is a short command name.** It is a plausible collision on a machine with other tooling.
  Acceptable for a repo of this scope; `pip` will report the shadowing.
- **Deleting `env.example.sh` breaks anyone mid-run-book.** The run-books are point-in-time
  documents (spec 41 D3) and are not edited retroactively; `--from-env-file` is the bridge, and it
  should be named in the PROGRESS entry so the user finds it before hunting.
- **Scope creep towards a config framework.** Profiles, non-Azure sections and layered project
  configs are all one small step away. §2 names them out; the spec is the place that holds the line.

## 6. Alternatives considered

- **Ship `env.example.sh` as package data.** Rejected: it makes the wheel carry a non-code asset for
  the sole purpose of being copied back out, and does nothing about `_config.py`'s import-time
  crash. It also contradicts the two-user split recorded in the finding — a consumer install
  carries code and dependencies, and non-code assets stay discoverable in the GitHub repo.
- **Make `find_repo()` return `None` instead of raising.** Rejected: it converts an import-time
  crash into an `AttributeError` several cells later, which is strictly worse, and still leaves the
  consumer with no file to fill in.
- **A project-local `fsd.toml`, discovered by walking upward.** Rejected: it recreates the gitignore
  problem in every consumer repo — the file sits inside a git tree and someone eventually commits a
  live storage URL. Four such leaks have already been caught in this project. It also reintroduces
  upward-walking discovery, the exact mechanism that failed here.
- **`.env` + `python-dotenv`.** Rejected: a dependency, project-local (same leak), and no
  established location for a user-level `.env`.
- **`tomli-w` for writing.** Rejected for now — see D2, with the condition under which it is right.
- **`platformdirs` for the location.** Rejected: a dependency to produce a path that D1 computes in
  ten lines, and its macOS answer (`~/Library/Application Support/fsd`) is *not* what the CLIs fsd
  sits next to actually use — gcloud puts `~/.config/gcloud` on macOS. Matching neighbours beats
  matching a convention here.
- **Keep `_config.py` for the fsd checkout and add `fsd.config` for consumers.** Rejected: two
  loaders with two precedence rules, and the developer path — the one the maintainer runs daily —
  would be the one *not* exercising the consumer code path. One loader, used by everyone.

## 7. Questions at sign-off — RESOLVED (user, 2026-08-26)

**Q1 — schema key names: `[azure]` + lowercase keys, or the `AZ_*` names verbatim?**

This spec assumes the first: `[azure] root = "…"`, read as `cfg.root`, with D4's mapping to the
`AZ_*` environment names.

*For the proposed form:* `AZ_ROOT = "abfss://…"` in a TOML file reads as a shell line that lost its
`export` — the file is the thing a human opens and edits, and it should look like a config file.
Grouping under `[azure]` is also what makes a second section possible later without a rename.
*Against:* `cfg.AZ_ROOT` → `cfg.root` is a rename in both fsd notebooks, and it introduces a
name map that must be kept correct in two directions.

**Recommendation: take the proposed form.** The map is six lines with a test asserting it is a
bijection, and the consumer notebook — the one that matters — is being written fresh against
whatever this spec says.

> **RESOLVED — take the proposed form** (user, 2026-08-26). `[azure]` + lowercase keys, `cfg.root`.
> Everything else in §3 was signed off as written.

## 8. Best-practice alignment / sources

Per-source credit — what each source specifically contributed.

**Python `tomllib` documentation** ([docs.python.org/3/library/tomllib](https://docs.python.org/3/library/tomllib.html),
fetched 2026-08-26). Contributed **the constraint that forces D2's shape**: *"This module does not
support writing TOML."* It is read-only, added in 3.11, and the docs name `Tomli-W` as the writer
*"that can be used in conjunction with this module"* and TOML Kit as the style-preserving option
*"for editing already existing TOML files."* That is what makes writing a dependency decision rather
than a free one — hence D2's emitter, and hence naming `tomli-w` as the documented escape hatch
rather than pretending none exists.

**XDG Base Directory Specification — freedesktop.org**
([specifications.freedesktop.org/basedir](http://specifications.freedesktop.org/basedir/latest/),
fetched 2026-08-26). Contributed **step 2–3 of D1 and its relative-path rule**: *"If
`$XDG_CONFIG_HOME` is either not set or empty, a default equal to `$HOME`/.config should be used"*,
and — quoted directly into D1 — *"All paths set in these environment variables must be absolute. If
an implementation encounters a relative path in any of these variables it should consider the path
invalid and ignore it."* That second sentence is why D1 **ignores** a relative override instead of
resolving it, which is the behaviour that stops a notebook kernel's cwd from becoming the config
home.

**Azure CLI configuration — Microsoft Learn**
([learn.microsoft.com/cli/azure/azure-cli-configuration](https://learn.microsoft.com/en-us/cli/azure/azure-cli-configuration),
fetched 2026-08-26). Contributed **two things**. First, **D4's precedence order**, adopted from its
stated evaluation order — *"1. Command-line parameters 2. Environment variables 3. Values in the
configuration file"* — so fsd's operators meet the ordering they already use. Second, **the
tool-specific override variable in D1**: *"The configuration file itself is located at
`$AZURE_CONFIG_DIR/config`. The default value of `AZURE_CONFIG_DIR` is `$HOME/.azure` on Linux and
macOS."* It also supplies the **precedent for the command shape**: `az init` is an existing
interactive config-writing command, which is what `fsd init` is modelled on. Note this source
**corrects** #78's phrasing: `az` does *not* use `~/.config` — it uses `~/.azure` — so "outside the
project tree" is the shared convention, not XDG specifically. D1 is written to that finer claim.

**gcloud CLI configurations — Google Cloud documentation**
([docs.cloud.google.com/sdk/docs/configurations](https://docs.cloud.google.com/sdk/docs/configurations),
fetched 2026-08-26). Contributed **the second data point behind D1**: configurations are stored in
*"your user config directory (typically `~/.config/gcloud` on MacOS and Linux, or `%APPDATA%\gcloud`
on Windows)"*, overridable via `CLOUDSDK_CONFIG`. Two specifics fall out. It is the source for
**D1's Windows fallback shape**, and — because gcloud uses `~/.config/gcloud` on **macOS**, not
`~/Library/Application Support` — it is the direct evidence in §6 for rejecting `platformdirs`,
whose macOS answer would diverge from both neighbours. Together with the Azure source it
establishes the pattern D1 actually follows: a user-level directory plus a *tool-specific* override
variable, with the vendors disagreeing on the default path.

**Entry points specification — Python Packaging Authority**
([packaging.python.org/specifications/entry-points](https://packaging.python.org/en/latest/specifications/entry-points/),
fetched 2026-08-26). Contributed **D5's mechanism and the `main() -> int` contract**:
*"Distributions can specify `console_scripts` entry points, each referring to a function. When pip
(or another console_scripts aware installer) installs the distribution, it will create a
command-line wrapper for each entry point"*; the generated wrapper is `sys.exit(main())`, and the
function *"may return an integer as an exit code, or None (treated as 0)"*. The `module:function`
object-reference syntax is what fixes the `fsd = "fsd.cli:main"` spelling.

**Not re-derived here:** #78 already records the 2026-08-21 decision and its rationale (addresses
not secrets; user-level config makes the gitignore problem disappear). This section verifies the
claims that decision rested on rather than restating it — and the Azure CLI source above amends one
of them.

## 9. Implementation note — build order for Sonnet

Each step is independently testable; do not start the next until the previous is green.

1. **`src/fsd/config.py`** — append a clearly delimited *user config* section below the existing
   constants (the file's docstring must be amended: it currently claims the module holds only
   decided contracts). Add: the path resolver (D1), `_emit_toml` (D2), `load()` (D3/D4),
   `MissingConfig` (D7), the `AZ_*` ↔ key map (Q1), and the `_EXPORT_RE` parser moved from
   `notebooks/_config.py`. **No CLI yet.**
2. **`tests/test_config.py`** — §4 criteria 3–8. `monkeypatch.setenv("FSD_CONFIG_DIR", str(tmp_path))`
   in a fixture used by every test that touches disk; nothing may reach the real `~/.config/fsd`.
3. **`src/fsd/cli.py` + `[project.scripts]`** — argparse, the four command forms in D5. Reinstall
   the venv (`pip install -e ".[dev]"`) for the entry point to appear. Test `main()` by calling it
   with an argv list, not by shelling out.
4. **`fsd/__init__.py`** — import `config` so `fsd.config.load()` works after a bare `import fsd`.
5. **Retire (D6)** — delete `env.example.sh` and `notebooks/_config.py`; delete
   `test_env_example_declares_exactly_the_notebook_vars`; extend `test_az_vars_are_documented`;
   rewrite `tests/test_notebooks.py`'s `_config` assertions. **Both leak guards stay.**
6. **Notebooks + how-tos** — update the two tracked notebooks' config cells and the prerequisite
   lines in `docs/howto/run-at-scale.md` and `build-the-images.md`. Clear all notebook outputs
   before committing (`tests/test_notebooks.py` enforces this).
7. **Full suite + ruff + identifier sweep**, then hand back to Opus for review.

Do **not** touch `fsd.download` / `create_training_data` / `run_inference` — D3 is the point of the
spec, and a signature change there is out of scope.
