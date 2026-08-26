---
status: current
summary: Two changes to spec 54's schema, in opposite directions. `root` comes OUT -- it names a per-run destination, not a durable address, and pinning it per-user makes a second project awkward (user, 2026-08-26). Two optional registry keys go IN, so a config file decides where the model and image registries live (user, 2026-08-27) while fsd's own code still only takes arguments. Plus `fsd init --blank`. Four decisions.
---

# Spec 55 — `root` leaves the config, the registries enter it

**Status:** **SIGNED OFF (user, 2026-08-27)** — every §7 question resolved; see §7 for what was
dropped at sign-off and why. Not implemented. · **Opened:** 2026-08-26
**Amends:** [spec 54](54-user-level-config.md) (D2's schema, D5's `init` forms, D7's error).
Spec 54 is **not** superseded — its D1 location rule, D3 explicitness and D4 precedence all stand.
**Origin:** the user's notes of 2026-08-26 and 2026-08-27, after spec 54 landed.
**Related:** [#78](https://github.com/nikhilsrajan/fsd/issues/78) (closed, the spec this amends),
[spec 56](56-image-definitions-and-registry.md) (the sibling spec; D2 here is what its registry
argument is fed from).
**Implementation:** Sonnet `/effort medium` against this spec (CLAUDE.md model split). §9 is the
build order.

---

## 1. The problem

Two, from using what spec 54 built, plus one gap it left.

**`root` is per-project; the file is per-user.** The user, 2026-08-26: *"a user might want to work
with multiple projects and to hard-set it early on might make things less user friendly."* The
other five values answer *which platform am I on* — subscription, resource group, workspace,
cluster, managed identity. They change when you change employer, not when you change project.
`root` answers *where does this run's data go*, which changes per project, per experiment, and
sometimes per cell. Writing it once into `~/.config/fsd/config.toml` and reading it back
everywhere makes the common case (one project) two keystrokes shorter and every other case a trip
to a file in a directory the user does not have open.

The same note observed that a user-level file is otherwise *"standard practice"* — it is (spec 54
§8 cites `az` and `gcloud`; dbt says it in its own words, §8 below). This spec does not move the
file. It removes the one key that never belonged in it, and adds two that do.

**Nothing tells fsd where the registries are.** Spec 56 puts image definitions in a registry and
spec 51 already put models in one, and both take the path as an argument — correctly, since fsd is
a general library and the concrete location is one project's business. But the two notebooks fsd
itself ships are **leak-guarded**: `tests/test_notebooks.py` fails the build on six identifier
patterns, so neither may hold a literal `abfss://` URL. Without a config key they have nowhere to
read one from. The user, 2026-08-27: *"fsd is supposed to be a general library — therefore the goal
is to hardset these parameters within the new rise repository. design wise fsd code should allow
config files to decide where the repository lies and use variables."*

**`fsd init` cannot write a file you intend to fill in yourself.** Every form writes values:
interactive prompts, `--set`, `--from-env-file`. There is no *"just create it, I will edit it"* —
which is what `env.example.sh` was for, and the affordance did not survive its retirement. Related,
and found by the spec 54 review: a non-tty `fsd init` (a CI step, a piped shell) dies on a bare
`EOFError` out of `input()`, because prompting is the only default.

## 2. Scope

**In:**

- Removing `root` from the config schema, and everything that follows.
- Adding `model_registry` and `image_registry` as **optional** keys, and the required/optional
  split in `load()` that they force.
- What a notebook does for `root` instead, given that it may not hold a literal storage URL.
- `fsd init --blank`, and making a non-tty `fsd init` say something useful.

**Out:**

- The file's location (spec 54 D1 stands), the precedence rule (D4 stands), the explicitness rule
  (D3 stands — this spec makes it *more* true, not less).
- Named profiles / multiple environments. Still out, and this spec is part of why they are not
  needed: the value that would have driven a profile is now an argument.
- **Any concrete `rise` value.** The registry URLs the user supplied name a real storage account;
  they live in `AZURE_INFRA_PRIVATE.md` and in the `rise` repo. Nothing under `fsd/` — a public MIT
  repo — carries them, in this spec or in any file it produces.
- Adding subset support to `load()` (`load("resource_group", "workspace")`). See §7 Q1: resolved as
  *leave it until it becomes an actual pain*.
- Cleaning `AZ_ROOT` out of the env-file/notebook plumbing that still names it. Deferred to a later
  Opus session — see §7's dropped D5.

## 3. Decisions

### D1 — `root` is removed from the config schema

The required keys become five: `subscription_id`, `resource_group`, `workspace`, `cluster`,
`uami_client_id`. `_KEY_TO_ENV` loses its `root: AZ_ROOT` entry. `load()` no longer returns a
`root` attribute, `fsd init` no longer prompts for one, and `fsd config` no longer prints one.

**The line, so this is not re-litigated as an ad-hoc removal.** What belongs in the config file is a
**durable address** — something stable for this user across runs and, mostly, across projects. What
does not is a **per-run destination**. The five platform coordinates are durable: a platform admin
hands them over, and they change when the tenancy does. The registries (D2) are durable by design —
spec 51's notebook comment already argues it, hanging the model registry off `AZ_ROOT` and not off
the per-run `ROOT` because *"Models outlive the runs that made them."* `root` is the destination
itself, chosen per run by whoever is running it.

Spec 41 D7 and spec 54 D3 both say the library takes storage locations as **arguments** and never
resolves them from ambient state. `root` sitting in a config file was the one place that rule was
bent — not by `src/fsd/`, which still never read it, but by the operator-facing helper feeding it.
This removes the bend.

*The consequence, stated plainly:* every caller now writes its own root. That is the cost, it is
deliberate, and it is one line per notebook.

### D2 — Two optional keys, `model_registry` and `image_registry`

```toml
[azure]
subscription_id = "…"
resource_group  = "…"
workspace       = "…"
cluster         = "…"
uami_client_id  = "…"
model_registry  = ""     # optional — where fsd.model.registry publishes
image_registry  = ""     # optional — where fsd.image.registry publishes (spec 56)
```

With `AZ_MODEL_REGISTRY` / `AZ_IMAGE_REGISTRY` as their bare env names, so spec 54 D4's precedence
(kwarg > env > file) applies to them unchanged and `_KEY_TO_ENV` stays a bijection.

**`load()` gains a required/optional split.** `REQUIRED_KEYS` is the five; `OPTIONAL_KEYS` is these
two; `KEYS` is both, and remains the order things are written and reported in. An unset **required**
key raises `MissingConfig` naming every gap at once, exactly as spec 54 D7 says. An unset
**optional** key is returned as `None` and raises nothing — a user who never touches a registry must
not be blocked by one.

**Where the concrete values live.** In the `rise` repo and in the user's own
`~/.config/fsd/config.toml`, never in fsd. This is the whole point of the key existing: fsd's code
signatures stay `publish(registry=..., ...)` and `ensure_environment(..., registry=...)` — variables
all the way down — while a config file supplies the value for the two notebooks that cannot carry
it. The user, 2026-08-27: *"within the module it should be all variables."*

**Why these two are config and `root` is not**, given they are all `abfss://` strings: a registry is
a durable address that several projects may legitimately share, and it is *named* rather than
*chosen per run*. If that turns out to be false — if a second project wants a second image registry
— the answer is the same as for any other key: pass it explicitly, since it is an argument in every
fsd signature anyway. The config key is a convenience for the common case, not a channel the library
reads.

### D3 — What the notebooks do for `root`

Neither tracked notebook may carry a literal storage URL, so "the caller passes root" cannot mean
"paste your `abfss://` URL into the config cell". They read it from the environment, in a visible
cell, with an error that says what to do:

```python
# Your storage root is per-project, so fsd does not store it (spec 55 D1). Export it before
# starting the kernel, or set it here if this notebook is not one that gets committed.
ROOT = os.environ.get("AZ_ROOT")
assert ROOT, "set AZ_ROOT (export AZ_ROOT=abfss://…) — spec 55 D1: root is not config"
```

**The reason is the leak guard, and only the leak guard.** An earlier draft of this decision also
argued that `AZ_ROOT` should keep working because run-books export it. That argument is withdrawn:
the user, 2026-08-27 — *"we do not care about the runbooks. runbooks are point in time docs ... we
do not prioritise being able to run the runbooks. we do not make decisions so that the runbooks are
still compatible."* Run-book compatibility is not a design input here or anywhere else. `AZ_ROOT`
stays because a public notebook needs a non-literal source for a private string, full stop.

A consumer repo whose notebook is not committed to a public repo can write the URL inline. That is
their call; the guard is fsd's rule about fsd's own files.

### D4 — `fsd init --blank`, and a non-tty that explains itself

```
fsd init --blank      # write config.toml with every key present and empty; prompt for nothing
```

Mutually exclusive with `--set` and `--from-env-file`, as they are with each other. It writes the
commented header `_emit_toml` already produces, **refuses to overwrite a file that already holds a
non-empty value** unless `--force` (a blank init over a filled-in file is destructive, and nothing
else in `fsd init` destroys a value), and prints the path — the only useful thing it can print,
having no values.

This restores `env.example.sh`'s one genuine affordance — *here is the shape, fill it in* — at a
location a consumer can reach, which spec 54 §1 identified as the template's fatal flaw.

Keys are written **present and empty** rather than commented out, so the file parses and `load()`
reports the gaps by name instead of `tomllib` reporting a syntax error.

**And prompting stops being the fallback for a non-tty.** `fsd init` with no arguments and no
terminal currently raises `EOFError` from `input()`. It detects `not sys.stdin.isatty()` and exits
non-zero naming the three non-interactive forms.

## 4. Acceptance criteria

1. `fsd.config.REQUIRED_KEYS` is the five, `OPTIONAL_KEYS` is the two, `KEYS` is both in write
   order; `_KEY_TO_ENV` covers all seven and the bijection test still passes.
2. `load()` returns a namespace with all seven attributes and no `root`. The two optional ones are
   `None` when unset anywhere; **no** `MissingConfig` is raised for them.
3. `MissingConfig` from an empty config names exactly the five required keys and their five `AZ_*`
   names, and still mentions `fsd init`.
4. `load(root="…")` raises `TypeError` — the existing unknown-kwarg guard covers it, and a test
   pins that it does, because passing `root=` is exactly the mistake a spec-54-era caller makes.
5. Precedence holds for an optional key too: `load(image_registry=…)` beats `AZ_IMAGE_REGISTRY`
   beats the file, and an empty string at one level falls through to the next.
6. `fsd init --blank` writes all seven keys empty, prompts for nothing, prints the path, exits 0;
   against a file with a non-empty value it refuses and exits non-zero unless `--force`.
7. `fsd init` with `stdin` not a tty exits non-zero naming `--blank` / `--set` / `--from-env-file`
   and does not raise `EOFError`. Tested by monkeypatching `sys.stdin.isatty`.
8. `fsd config` prints seven rows with provenance; an unset optional key reads as unset rather than
   as a missing requirement.
9. `tests/test_docs.py::test_az_vars_are_documented` passes with all seven, and
   `docs/reference/environment.md` documents `AZ_MODEL_REGISTRY` / `AZ_IMAGE_REGISTRY`, and
   `AZ_ROOT` as an environment variable that **fsd does not read**.
10. `e2e_austria_aml.ipynb` gets D3's `ROOT` cell, both tracked notebooks carry no literal storage
    URL, and `tests/test_notebooks.py`'s guards still pass.
11. `pytest -q` and `ruff check src/ tests/` clean; identifier sweep clean — **including that no
    concrete storage-account name entered any tracked file.**

## 5. Risks

- **A user with one project types a root they used to have stored.** Accepted: one line, and it is
  the line that makes the second project free.
- **`AZ_ROOT` looks like it is still config.** It is still a documented variable and now read by the
  notebook rather than by fsd. Real distinction, invisible at a glance;
  `docs/reference/environment.md` has to say it in words (AC 9).
- **The registry keys reintroduce "a storage location in a config file",** which D1 just removed one
  of. Mitigated by them being optional, by every fsd signature still taking the path, and by D2
  stating the durable-address test that separates them. If that test starts feeling like a
  rationalisation, the honest response is to remove them again, not to add a third category.
- **The notebook `assert` is a worse error than `MissingConfig`** — it names one gap, not all.
  Accepted: it sits in a cell the reader can see and edit, which is the property D3 buys.
- **Churn on a spec that landed a day ago.** Cheap now, expensive once the consumer notebooks are
  written against the old schema — which is exactly why this is specced before phase 2 continues.

## 6. Alternatives considered

- **Project-local `fsd.toml` holding `root`, discovered by walking up.** Offered at the decision
  point and declined by the user in favour of passing it. Would have reintroduced what spec 54 §6
  rejected: a live storage URL inside a git tree — the leak this project has caught four times —
  and made fsd responsible for a `.gitignore` rule.
- **Named profiles (`[project.rise]`, `load(profile=…)`).** Offered and declined. It is the `gcloud
  configurations` shape and it works, but it is a second lookup mechanism to explain, spec 54 §2
  ruled it out, and the second project still starts with an edit to a file in a hidden directory.
- **Keep `root` in the schema but make it optional** (as D2 does for the registries). Rejected: the
  key stays in the file inviting a value, `load()` sometimes returns it, and every caller needs a
  branch for whether it did. The registries differ because a caller who has no registry does not
  want one at all, whereas every run has a root.
- **One `registry_root` key, with `model_registry`/`image_registry` derived by convention.**
  Considered at sign-off. Rejected: it makes fsd own a layout convention, and it forecloses putting
  the image registry somewhere shared while the model registry stays per-project.
- **No config keys at all; `AZ_IMAGE_REGISTRY` / `AZ_MODEL_REGISTRY` env vars only.** Considered at
  sign-off. It keeps D1's line perfectly clean, at the cost of the one file the user actually edits
  not mentioning the registries at all.
- **`fsd init --template` printing TOML to stdout** instead of `--blank` writing a file. Rejected:
  the user then needs to know where to redirect it, which is the knowledge `fsd init` removes.

## 7. Questions at sign-off — ALL RESOLVED (user, 2026-08-26/27)

**Q1 — does `load()` gain subset support?** `00_build_images.ipynb` needs `resource_group` +
`workspace`, and `load()` requires the whole required set, so building an image demands a cluster
and a managed identity you may not have yet.
> **RESOLVED — as proposed: leave it** (user, 2026-08-27): *"leave it till it becomes an actual
> pain."* `load()` keeps requiring all five required keys.

**Q2 — what does `--blank` write?** Keys present and empty, or a commented-out template?
> **RESOLVED — as proposed:** present and empty (D4), so the file parses and `load()` reports gaps
> by name.

**Q3 — where do the registry paths come from?** Added 2026-08-27.
> **RESOLVED — two optional config keys** (user, 2026-08-27), now D2. Concrete values live in the
> `rise` repo and the user's own config file; fsd's signatures stay variables.

**Two decisions were DROPPED at sign-off.** Recorded here because a later reader will otherwise
propose them again:

- **Dropped D4 — "a `root` key already in someone's file is ignored, and `fsd config` says so
  once."** The user, 2026-08-27: *"there is no 'existing config.toml' file ... we have not shipped
  fsd for people to use. i have been the sole user. this feature could be ignored until an actual
  issue pops up."* `_read_file_values` already filters unknown keys, so a stale `root` is ignored
  silently and nothing needs building.
- **Dropped D5 — "`--from-env-file` prints a line when it skips `AZ_ROOT`."** Same reasoning, plus:
  the user assigned the wider job — *"clean up AZ_ROOT for env files and notebooks"* — to a later
  Opus session. Filed as an issue rather than built here.

## 8. Best-practice alignment / sources

Per-source credit — what each source specifically contributed.

**dbt — "Connection profiles" / `profiles.yml`**
([docs.getdbt.com/docs/core/connect-data-platform/connection-profiles](https://docs.getdbt.com/docs/core/connect-data-platform/connection-profiles),
fetched 2026-08-26). Contributed **the confirmation that a user-level file is right, and the
vocabulary for why `root` is different from the rest**. dbt gives three reasons for
`~/.dbt/profiles.yml`: *"Security — Keeps credentials out of project directories and version
control. Reusability — A single file for all dbt projects on the machine. Separation — Connection
details don't travel with project code."* All three describe the keys this spec keeps. The same
source draws the other half of the line: `dbt_project.yml` is the project-specific file and
*"references a profile name defined in profiles.yml"* — the project file holds what varies per
project, the user file holds what does not. fsd takes the stricter form: its per-project value is a
single string, and a function argument is cheaper than a second file.

**Spec 54 §8's sources are not re-derived.** The Azure CLI's precedence order, the XDG relative-path
rule and the `console_scripts` contract are unchanged by this spec; it amends the schema, not the
mechanism.

## 9. Implementation note — build order

1. **`src/fsd/config.py`** — split `KEYS` into `REQUIRED_KEYS` + `OPTIONAL_KEYS`; drop `root`; add
   the two registry keys and their `AZ_*` names. `load()` raises only for missing **required** keys
   and returns `None` for unset optional ones. `_emit_toml` / `write_config` are already driven off
   `KEYS` and need no change beyond the new order.
2. **`tests/test_config.py`** — AC 1–5. The existing six-key fixtures become five required + two
   optional.
3. **`src/fsd/cli.py`** — `--blank` (mutually exclusive; `--force` to overwrite a filled file), the
   non-tty guard, and `fsd config` printing optional keys as optional.
4. **`tests/test_cli.py`** — AC 6, 7, 8.
5. **Notebooks** — `e2e_austria_aml.ipynb` gets D3's `ROOT` cell and reads `cfg.model_registry`;
   `00_build_images.ipynb` is otherwise spec 56's business.
6. **Docs** — `docs/reference/environment.md`: `AZ_ROOT` moves from "one of the six `fsd init`
   writes" to "an environment variable your notebook reads; fsd does not read it", and the two
   registry variables are added to the table. `CHANGES.md` entry amending spec 54's.
7. **Full suite + ruff + identifier sweep.**

Do **not** touch `fsd.download` / `create_training_data` / `run_inference` — they already take every
location as an argument, which is the state this spec restores the config to.
