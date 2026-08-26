---
status: current
summary: `root` is the one value in spec 54's schema that names a DESTINATION rather than the platform, and pinning it in a user-level file makes a second project awkward (user, 2026-08-26). Remove it from the schema entirely -- the caller passes every storage location, which is spec 41 D7's invariant applied to the last value that escaped it. Plus `fsd init --blank` for a file you fill in by hand. Five decisions.
---

# Spec 55 — `root` leaves the config; `fsd init --blank`

**Status:** DRAFT — awaiting sign-off. · **Opened:** 2026-08-26
**Amends:** [spec 54](54-user-level-config.md) (D2's schema, D5's `init` forms, D7's error).
Spec 54 is **not** superseded — its D1 location rule, D3 explicitness and D4 precedence all stand.
**Origin:** two notes from the user, 2026-08-26, after spec 54 landed. **Related:**
[#78](https://github.com/nikhilsrajan/fsd/issues/78) (closed, the spec this amends),
[spec 56](56-image-definitions-and-registry.md) (the sibling note, and the first consumer of the
rule that a registry path is *passed*, never read from config).

---

## 1. The problem

Two, from using what spec 54 built.

**`root` is per-project; the file is per-user.** The user, 2026-08-26: *"a user might want to work
with multiple projects and to hard-set it early on might make things less user friendly."* The
other five values answer *which platform am I on* — subscription, resource group, workspace,
cluster, managed identity. They change when you change employer, not when you change project.
`root` answers *where does this run's data go*, which changes per project, per experiment, and
sometimes per cell. Writing it once into `~/.config/fsd/config.toml` and reading it back
everywhere makes the common case (one project) two keystrokes shorter and the second case
(any other project) a trip to a file in a directory the user does not have open.

The same note observed that a user-level file is otherwise *"standard practice"* — it is (spec 54
§8 cites `az`, `gcloud`, and dbt says the same thing in its own words, §8 below). This spec does
not move the file. It removes the one key that never belonged in it.

**`fsd init` cannot write a file you intend to fill in yourself.** Every form writes values:
interactive prompts for six, `--set` takes them on the command line, `--from-env-file` reads them
from a file you already have. There is no *"just create it, I will edit it"* — which is what
`env.example.sh` was for, and the affordance did not survive its retirement. Related, and
visible in the spec 54 review: a non-tty `fsd init` (a CI step, a piped shell) dies on a bare
`EOFError` traceback out of `input()`, because prompting is the only default.

## 2. Scope

**In:**

- Removing `root` from the config schema, and everything that follows: `KEYS`, the `AZ_*` map,
  `MissingConfig`, `fsd config`, the two tracked notebooks, `docs/reference/environment.md`.
- What a notebook does instead, given that `tests/test_notebooks.py` forbids it to hold a literal
  storage URL.
- `fsd init --blank`, and making a non-tty `fsd init` say something useful.
- A migration note for a `config.toml` that already has `root` in it.

**Out:**

- The file's location (spec 54 D1 stands), the precedence rule (D4 stands), the explicitness rule
  (D3 stands — this spec makes it *more* true, not less).
- Named profiles / multiple environments. Still out, and this spec is the reason they are not
  needed: the value that would have driven a profile is now an argument.
- Any change to how `AZ_ROOT` works **as an environment variable** in a shell or a run-book. It
  keeps working exactly as it does; it simply stops being part of fsd's config schema.
- Adding subset support to `load()` (`load("resource_group", "workspace")`). Raised by the spec 54
  review because `00_build_images.ipynb` needs two of the six. With `root` gone the remaining five
  are all *platform* coordinates that any AML call needs together, so the case for a subset
  weakens rather than strengthens. Left unbuilt; see §7 Q1.

## 3. Decisions

### D1 — `root` is removed from the config schema

`KEYS` becomes five: `subscription_id`, `resource_group`, `workspace`, `cluster`,
`uami_client_id`. `_KEY_TO_ENV` loses its `root: AZ_ROOT` entry. `load()` returns a namespace with
five attributes and raises `MissingConfig` naming whichever of the five are unset. `fsd init`
prompts for five. `fsd config` prints five.

**The principled line, so this is not re-litigated as an ad-hoc removal.** The five that remain
are *addresses of the platform*: they identify an Azure tenancy and the compute inside it, they are
handed to you by a platform admin, and every fsd call that touches AML needs all of them.  `root`
is a *destination for data*, chosen by whoever is running the job, different per run. Spec 41 D7
and spec 54 D3 both say the library takes storage locations as **arguments** and never resolves
them from ambient state; `root` sitting in a config file was the one place that rule was bent —
not by `src/fsd/`, which still never read it, but by the operator-facing helper that fed it. This
removes the bend.

*The consequence, stated plainly:* every caller now writes its own root. That is the cost, it is
deliberate, and it is one line per notebook.

### D2 — What the notebooks do instead

Neither tracked notebook may carry a literal storage URL — `tests/test_notebooks.py` fails the
build on six identifier patterns, and that guard is the reason those notebooks can be public at
all. So "the caller passes root" cannot mean "paste your `abfss://` URL into the config cell".

The fsd-tracked notebooks read it from the environment, with an error that says what to do:

```python
# Your storage root is per-project, so fsd does not store it (spec 55 D1). Export it, or
# set it here if this notebook is not the one that is committed.
ROOT = os.environ.get("AZ_ROOT")
assert ROOT, "set AZ_ROOT (export AZ_ROOT=abfss://…) — spec 55 D1: root is not config"
```

`AZ_ROOT` stays a documented environment variable in `docs/reference/environment.md` — it is
what every existing run-book already exports, and D4's precedence made it work before this spec.
The difference is only that **fsd does not read it**: the notebook does, explicitly, in a cell the
reader can see. A consumer repo whose notebook is *not* committed to a public repo can of course
write the URL inline; that is their call, and the leak guard is fsd's rule about fsd's own files.

### D3 — `fsd init --blank`

```
fsd init --blank      # write config.toml with every key present and empty; prompt for nothing
```

Mutually exclusive with `--set` and `--from-env-file`, like they are with each other. It writes
the same commented header `_emit_toml` already produces, refuses to overwrite a file that already
has a non-empty value unless `--force` is given (a blank init over a filled-in file is
destructive, and nothing else in `fsd init` destroys a value), and prints the path — which is the
only useful thing it can print, since it has no values.

This restores `env.example.sh`'s one genuine affordance — *here is the shape, fill it in* — at the
location a consumer can actually reach, which is what spec 54 §1 said the template failed to do.

**And prompting stops being the fallback for a non-tty.** `fsd init` with no arguments and no
terminal currently raises `EOFError` from `input()`. It should detect `not sys.stdin.isatty()` and
exit non-zero with the three non-interactive forms named (`--blank`, `--set`, `--from-env-file`).

### D4 — A `root` key already in someone's file is ignored, and said so once

`_read_file_values` already filters to known keys, so an existing `config.toml` written by spec
54's `fsd init` keeps loading — `root` is simply not returned. Silence here is the wrong
behaviour: the value is sitting in the file, visibly, and the user will reasonably expect it to be
used.

`fsd config` prints one line when the file holds keys the schema no longer has:

```
config file: /Users/…/.config/fsd/config.toml
  …
  note: 'root' in this file is ignored — root is passed per call since spec 55, not configured.
```

Not a warning on `load()`. `load()` is called at the top of every notebook cell run and a
per-import nag is noise; `fsd config` is the command whose entire job is explaining where values
come from.

### D5 — `--from-env-file` keeps parsing `AZ_ROOT`, and drops it with a line of output

The migration path (spec 54 D5) reads an `env.local.sh` that certainly contains `export AZ_ROOT=`.
`parse_env_file` returns every `AZ_*` it finds; `_cmd_init` maps only what is in `ENV_TO_KEY`, so
`AZ_ROOT` is already dropped. Make it say so — `skipped AZ_ROOT (not a config key since spec 55)`
— rather than silently discarding the one value the user is most likely to be looking for
afterwards.

## 4. Acceptance criteria

1. `fsd.config.KEYS` is the five; `load()` returns a namespace with exactly those attributes and
   no `root`.
2. `MissingConfig` raised from an empty config names five keys and five `AZ_*` names, and still
   mentions `fsd init`.
3. `load(root="…")` raises `TypeError` — the existing unknown-kwarg guard covers it, and a test
   pins that it does, because passing `root=` is exactly the mistake a spec-54-era caller makes.
4. A `config.toml` containing a `root` key loads without error and `load()` ignores it;
   `fsd config` prints the D4 note naming the ignored key.
5. `fsd init --blank` writes all five keys empty, prompts for nothing, prints the path, and exits
   0; run against a file with a non-empty value it refuses and exits non-zero unless `--force`.
6. `fsd init` with `stdin` not a tty exits non-zero naming `--blank` / `--set` / `--from-env-file`,
   and does not raise `EOFError`. Tested by monkeypatching `sys.stdin.isatty`.
7. `fsd init --from-env-file` on a file containing `AZ_ROOT` writes the other keys, prints the
   skip line, and does not write `root`.
8. `tests/test_docs.py::test_az_vars_are_documented` passes with the five, and
   `docs/reference/environment.md` still documents `AZ_ROOT` (as an environment variable that fsd
   does not read).
9. Both tracked notebooks call `fsd.config.load()`, get `ROOT` from `os.environ`, carry no literal
   storage URL, and `tests/test_notebooks.py`'s guards still pass.
10. `pytest -q` and `ruff check src/ tests/` clean; identifier sweep clean.

## 5. Risks

- **A user with one project is now slightly worse off** — they type a root they used to have
  stored. Accepted: it is one line, and it is the line that makes the second project free.
- **`AZ_ROOT` looks like it is still config.** It is still a documented variable, still exported by
  every run-book, and now read by the notebook rather than by fsd. The distinction is real but
  invisible at a glance, which is why D4 and D5 both spend output on saying it.
- **The notebook assert is a worse error than `MissingConfig`.** `MissingConfig` names every gap at
  once and says how to fix it; a bare `assert ROOT` names one. Accepted for now — it is in a cell
  the reader can see and edit, which is the property D2 is buying.
- **Churn on a spec that landed hours ago.** Spec 54's schema is one commit old and this changes
  it. Cheap now, expensive after the consumer notebooks are written against six keys — which is
  precisely why this is being specced before phase 2 continues rather than after.

## 6. Alternatives considered

- **Project-local `fsd.toml` holding `root`, discovered by walking up.** Offered at the decision
  point and declined by the user in favour of passing it. Would have reintroduced exactly what
  spec 54 §6 rejected: a live storage URL inside a git tree, which is the leak this project has
  caught four times, and it would have made fsd responsible for managing a `.gitignore` rule.
- **Named profiles (`[project.rise]`, `load(profile=…)`).** Offered and declined. It is the
  `gcloud configurations` shape and it works, but it is a second lookup mechanism to explain,
  spec 54 §2 ruled it out, and it stores per-project data — meaning the second project still
  starts with an edit to a file in a hidden directory.
- **Keep `root` in the schema but make it optional.** Rejected as the worst of both: the key stays
  in the file inviting a value, `load()` sometimes returns it, and every caller needs a branch for
  whether it did.
- **A `fsd init --template` printing TOML to stdout instead of `--blank` writing a file.** Rejected:
  the user then has to know where to redirect it, which is the knowledge `fsd init` exists to
  remove. `--blank` writes it at the resolved path and prints where.

## 7. Questions at sign-off

**Q1 — does `load()` gain subset support?** Raised by the spec 54 review: `00_build_images.ipynb`
needs `resource_group` + `workspace`, and `load()` requires the whole schema, so building an image
demands a cluster and a managed identity you may not have yet. With `root` gone the schema is five
platform coordinates, and any AML *job* needs all five — but an image build genuinely needs two.

*Proposal:* `load()` keeps requiring all five, and this is revisited only if a real caller is
blocked. The five are handed over together by a platform admin; a user who has two of them and not
the other three is mid-setup, and `MissingConfig` naming the rest is arguably the right thing to
show them. *Against:* it makes `00_build_images` unusable until every value is filled, which is a
real consumer's first fsd command.

**Q2 — does `--blank` write the five keys, or a fully commented template?** Proposal: keys present
and empty (`root = ""`-style, minus root), because the file must parse and `load()` must report
the gaps rather than `tomllib` reporting a syntax error. A commented-out template reads better and
loads as an empty file. Proposal: keys present and empty, with the existing two header comments.

## 8. Best-practice alignment / sources

Per-source credit — what each source specifically contributed.

**dbt — "Connection profiles" / `profiles.yml`**
([docs.getdbt.com/docs/core/connect-data-platform/connection-profiles](https://docs.getdbt.com/docs/core/connect-data-platform/connection-profiles),
fetched 2026-08-26). Contributed **the confirmation that keeping the file user-level is right, and
the vocabulary for why `root` is different**. dbt gives three reasons for `~/.dbt/profiles.yml`:
*"Security — Keeps credentials out of project directories and version control. Reusability — A
single file for all dbt projects on the machine. Separation — Connection details don't travel with
project code."* All three describe the five values this spec keeps. The same source draws the other
half of the line: `dbt_project.yml` is the project-specific file and *"references a profile name
defined in profiles.yml"* — the project file holds what varies per project, and the user file holds
what does not. fsd takes the stricter form of the same split, because its per-project value is a
single string and a function argument is cheaper than a second file.

**Spec 54 §8's own sources are not re-derived here.** The Azure CLI's precedence order, the XDG
relative-path rule and the `console_scripts` contract are unchanged by this spec; it amends the
schema, not the mechanism.

## 9. Implementation note — build order

1. **`src/fsd/config.py`** — drop `root` from `KEYS` and `_KEY_TO_ENV`. Nothing else in the module
   changes shape: `load`, `MissingConfig`, `_emit_toml` and `write_config` are all driven off
   `KEYS`.
2. **`tests/test_config.py`** — the six-key fixtures become five; add AC 3 (`load(root=…)` raises
   `TypeError`) and AC 4 (a file with `root` loads and ignores it).
3. **`src/fsd/cli.py`** — `--blank` (mutually exclusive, `--force` to overwrite a filled file), the
   non-tty guard, the D4 note in `fsd config`, the D5 skip line in `--from-env-file`.
4. **`tests/test_cli.py`** — AC 5, 6, 7.
5. **Notebooks** — `e2e_austria_aml.ipynb` gets D2's `ROOT` cell (it is the only one that uses
   root); `00_build_images.ipynb` needs no change beyond what spec 56 does to it.
6. **Docs** — `docs/reference/environment.md`: `AZ_ROOT` moves from "one of the six `fsd init`
   writes" to "an environment variable your run-book exports and your notebook reads; fsd does not
   read it". `CHANGES.md` entry amending spec 54's.
7. **Full suite + ruff + identifier sweep.**

Do **not** touch `fsd.download` / `create_training_data` / `run_inference` — they already take
every location as an argument, which is the state this spec restores the config to.
