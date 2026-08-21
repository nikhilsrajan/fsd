---
status: current
summary: Resolve create_training_data backwards from the artifact the caller asked for — arrays, then cubes, then imagery — so a leg's expensive preflight (above all `setup`, ~96 s and ~1800 blob writes at 900 shapes) never runs to discover it had nothing to do. Completes spec 49's own acceptance sentence, which the forward orchestrator does not currently deliver.
---

# Spec 50 — resolve backwards from the target: the `create_training_data` walk

**Status: 🟡 DRAFT 2026-08-21 — awaiting sign-off.** Raised by the user 2026-08-21 after
observing that a fully-resumed `create_training_data` still paid a full `setup` pass before any
skip could fire. Nothing in `src/` is touched yet.

> **The one sentence:** spec 49 taught each leg to skip finished work, but each leg still runs its
> own preflight *before* its skip can be evaluated — so the cheapest question ("are the arrays
> already here?") is asked last, after the most expensive answer has already been paid for.

---

## 1. The gap

Spec 49 delivered three skips. They are all **forward**: control enters leg 1, leg 1 decides
whether to work, control enters leg 2, and so on.

| leg | decides on | evaluated |
|---|---|---|
| download | discovered assets vs the catalog | spec 47 D8 |
| build | `input.csv`'s cube paths vs what exists | spec 49 D1 |
| flatten | `_flatten_stamp.json` identity equality | spec 49 D3 |

The cost is not the skips. It is **what each leg does before it is allowed to skip.**

`run_create_datacube` defaults to `overwrite_setup_csv=True`, which **deletes `input.csv` and
re-runs `setup` on every call**:

```python
if overwrite_setup_csv and fs.exists(csv_filepath):
    fs.rm(csv_filepath)
if not fs.exists(csv_filepath):
    setup(...)
```

`setup` reads the catalog, filters it per shape, and writes **two files per shape** to
`export_folderpath` — `geometry.geojson` and `catalog.parquet` (`create_datacube.py`). At 900
shapes that is **1800 blob round-trips** before `_build_shortfall` is even called. Measured on the
Austria AML e2e, 2026-08-21: **`[setup] 900/900 shapes | elapsed 96s`**, paid in full on a run
whose every cube already existed. It is the single slowest driver-side phase of a no-op re-run,
and it is pure overhead — see also #54, which named the same write pattern as a cloud cost.

### Why this is a spec 49 defect, not a spec 50 feature

Spec 49's status line quotes the user's own acceptance sentence:

> *"…then even flattening becomes unnecessary (unless modeller forces the overwrite) — **the only
> task create_training_data does is to download the flattened numpy arrays.**"*

D6 restates it as the acceptance criterion. Today that is false: the fully-done path still reads
the catalog, filters 900 shapes and writes 1800 files. Every one of spec 49's 11 acceptance
criteria passes, because they are all written against `input.csv` and `run_create_datacube`
directly — none of them asserts anything about **what ran before the skip**. So this spec
*completes* spec 49 rather than extending it, which is the argument for doing it now rather than
filing it.

### The structural reason

`setup` cannot be skipped **within** the forward shape, because the flatten skip's identity is
computed *from `input.csv`* — and `input.csv` is `setup`'s output. The forward orchestrator has to
run the expensive rule to obtain the information it needs to decide whether to run it. That is the
knot, and no amount of extra caching inside a leg unties it.

---

## 2. Scope

**In:** resolving `create_training_data` backwards from the artifact the caller asked for; making a
target's identity computable **without** running the rule that produces it (D3); scoping `setup` to
the shortfall (D4); recording known-empty cells (D5); a deterministic default run folder, which is
**#83** and is a precondition rather than an option (D6).

**Out:** `run_inference` (its per-cell skip is decided on the node — **#77**, its own spec);
a general DAG engine spanning every verb; **delegating to Snakemake** (D1); content digests of
cubes (spec 49 §7 Q2's default stands — this spec changes control flow, not the staleness
predicate); changing artifact formats; `fsd.download` as a standalone verb (unchanged).

---

## 3. Decisions

### D1 — the walk is fsd's own, on the driver; Snakemake is the *model*, not the mechanism

Spec 49 §6 rejected "let Snakemake decide" because **the AML runner has no DAG**, and a skip that
behaves differently under the two runners is worse than no skip. That constraint is unchanged and
this spec honours it: the walk is plain Python on the driver, above the runner seam, so `local` and
`aml` resolve identically and only *execution* differs.

What is adopted from Snakemake is the **semantics of a rule**, which is what the user asked for
(2026-08-21):

- a rule declares `output` and `input`;
- a requested target is matched to the rule whose `output` it satisfies;
- that rule's `input` files are then **recursively considered as targets themselves** (§8: this is
  Make's own phrasing, and Snakemake's DAG construction);
- a file with **no rule producing it** must already exist, or the walk fails loudly.

The property that matters, and the one fsd lacks today: **a rule's body never runs in order to
decide whether the rule must run.** The decision is made from the target's own presence and
identity. `setup` violates exactly this.

### D2 — the target is the landed arrays; the rules are the three legs

```
target:  export_folderpath/{data,coords,ids,labels,metadata.pickle}.npy   (+ _flatten_stamp.json)
   ^
   | rule FLATTEN   in: the N cubes named by the request   out: the arrays
   ^
   | rule BUILD(id) in: catalog rows ∩ shape(id), in-window   out: run/<window>/<id>/datacube.npy
   ^                                                               + metadata.pickle.npy
   | rule DOWNLOAD  in: provider discovery                    out: catalog.parquet + assets
```

Resolution runs top-down (arrays → cubes → imagery); **execution** then runs bottom-up along the
resolved plan, exactly as Make and Snakemake do. The walk short-circuits at the first satisfied
target: if the arrays are present and their identity matches the request, **nothing below is
evaluated at all** — no catalog read, no `setup`, no listing of 900 cube paths.

### D3 — a target's identity must be computable without running its rule

**This is the load-bearing decision.** Today `_flatten_identity(input_df, ...)` reads `input.csv`,
so the flatten skip is unevaluable until `setup` has produced it. The identity moves to the
**request**:

- the sorted **shape ids** (from `label_polygons`, which the caller already supplied);
- the window (`startdate`/`enddate`), `mosaic_days`, `bands`, `scl_mask_classes`;
- `aggregate` + the feature-transform fingerprint (qualname + kwargs, spec 49 §7 Q4 unchanged).

This is sound because **a cube's path is derivable from `(run_folderpath, window, id)` and nothing
else** — `setup`'s per-shape catalog filtering is what is needed to *build* a cube, never to *name*
one. So the walk can enumerate every expected cube path with zero catalog access, which is what
makes D4 possible.

Note what does **not** change: the comparison is still equality against a recorded identity, still
never a modification time (spec 49 D3), and still without content digests by default.

### D4 — `setup` is scoped to the shortfall

Once the walk knows which cube targets are missing, `setup` runs **only for those shapes**. Three
consequences:

- the no-op case runs `setup` **zero** times (today: 900 shapes, ~96 s, ~1800 blob writes);
- the partial case writes control files for the shortfall only — 40 missing cells cost 80 writes,
  not 1800. This is #54's cost, reduced in proportion to the work actually needed;
- `overwrite_setup_csv`'s delete-then-regenerate default becomes unnecessary for the common path
  and should be revisited (§7 Q3).

### D5 — a cell with no imagery is recorded as known-empty, never rediscovered

`setup` today prints `[setup] skip id=…: no tiles in range/overlap` and omits that shape from
`input.csv`. A walk that enumerates targets from **shape ids** would see those cells as permanently
missing, try to build them on every run, and never converge — the walk would report a non-empty
shortfall forever on a request that is genuinely complete.

So the run folder carries a small manifest recording, per request identity, the ids that resolved
to **no imagery**. The walk then distinguishes:

- *no cube, and no imagery for it* → satisfied (nothing to do, and say so);
- *no cube, imagery available* → a real target to build.

This is new state and it can itself go stale (§5). It is the price of naming targets without
reading the catalog, and it is cheaper than the alternative, which is reading the catalog.

### D6 — the default run folder becomes deterministic (this is #83, and it is a precondition)

`run_folderpath` currently defaults to `{root}/runs/{run_id}` with `run_id` a fresh UTC timestamp
(**#83**), so every target is missing on every call and no walk — backward or forward — can ever be
satisfied. The default must derive from the **request**, not the clock.

The AML `run_id` used for `shards/` and `_status/` stays fresh per submission: it identifies a
*submission*, which is the right thing for it to identify. Only the **artifact** paths become
deterministic. §7 Q1 asks what the derived name should be.

### D7 — the walk announces what it resolved, before it runs anything

Spec 47 D5's rule, applied to the plan rather than to each leg:

```
[plan] target: ./demo_training_data arrays -> STALE (no stamp)
[plan]   flatten: 900 cubes required
[plan]   build:   860 present, 40 missing, 0 known-empty -> will build 40
[plan]   download: catalog satisfies all 40 -> nothing to download
[plan] will run: build(40) -> flatten -> land
```

and, in the satisfied case, the whole run is:

```
[plan] target: ./demo_training_data arrays -> CURRENT (stamp matches this request)
[fetch] export -> ./demo_training_data | 5 files, 18.2 MB
```

A user who cannot see why the fast path was fast will not trust it. This is also the diagnostic
that would have made #83 self-evident in one line instead of two full cluster runs.

### D8 — `overwrite=` becomes force semantics on the graph

`overwrite=` keeps its spec 49 D4 spelling and gains the natural reading, matching Snakemake's
`--forcerun` / `--forceall` split (§8):

- `overwrite="flatten"` → force the flatten target, leave its inputs alone;
- `overwrite="datacubes"` → force the cube targets **and everything downstream** (the flatten
  necessarily re-runs, which is what spec 49 D4 already asserted and now falls directly out of the
  graph rather than being special-cased in `api.py`);
- `overwrite=True` → force the whole plan;
- `overwrite=False` → the walk decides.

---

## 4. Acceptance criteria

1. `create_training_data` whose arrays are present with a matching stamp performs **no catalog
   read, no `setup` call, and no dispatch** — asserted by test (a fake `setup` that raises if
   called).
2. That same call still lands the arrays and returns a `TrainingData` whose `.load()` equals a full
   run's (spec 49 D6/AC10 carried forward, unchanged).
3. A partial run calls `setup` **only for the missing ids**: 900 shapes, 40 missing → `setup`
   receives 40 shapes, and 80 control files are written, not 1800.
4. The flatten identity is computed from the **request** and never reads `input.csv` — asserted by
   test (identity computed with no `input.csv` on disk).
5. Cube paths are enumerated with **no catalog access** — asserted by test.
6. A cell with no in-window imagery is recorded once and reported as known-empty on the next run;
   two consecutive identical runs both report a shortfall of 0 (D5, the non-convergence case).
7. `run_folderpath` defaults to a value derived from the request: two identical calls seconds apart
   address identical cube paths (#83; `tests/test_build_skip.py`'s characterisation test flips from
   asserting a timestamp leaf to asserting equality).
8. `overwrite="datacubes"` forces cubes and flatten; `overwrite="flatten"` forces flatten only;
   `overwrite=True` forces all; an invalid value raises naming the valid ones (spec 49 AC7/AC8
   carried forward).
9. The `[plan]` block prints before any work, names each target's state, and names what will run.
10. No modification time is read anywhere in the walk (spec 49 AC6 carried forward).
11. Behaviour is identical under `runner="local"` and `runner="aml"` — the walk is above the runner
    seam, asserted by test.
12. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean; no network in unit tests.

---

## 5. Risks

- **The walk is only as honest as the identity.** It answers "current with respect to the
  *request*", never "with respect to the *world*". A re-ingested granule leaves every target
  satisfied. Unchanged from spec 49 Risk 1 and #76 — but the backward shape makes it *easier* to
  miss, because in the satisfied case nothing is read at all. D7's `[plan]` line is the mitigation,
  plus `overwrite=`.
- **The known-empty manifest (D5) is new state that can go stale.** A cell that had no imagery in
  April and does after a re-ingest stays known-empty until the manifest is invalidated. It is keyed
  to the request identity, so a changed window or band set clears it — but a changed *archive* under
  an unchanged request does not. This is the same hole as the bullet above, in a new place.
- **A refactor of the verb everything else depends on.** `create_training_data` is the most-used
  entry point and the e2e notebook drives it. Phasing (§9) exists to keep each step revertible.
- **Cheap-check ordering can invert.** The walk assumes the top question is the cheapest. It is
  today (local file reads). If the arrays ever land somewhere remote, the short-circuit becomes a
  WAN round-trip and the ordering should be re-examined.

---

## 6. Alternatives considered

- **A top-level short-circuit only** — ask "are the arrays current?" first, keep the forward
  orchestrator underneath. Genuinely captures most of the value for the common case and was the
  cheaper recommendation. **Not rejected — adopted as §9 phase 1**, so the value lands early and
  phase 2 is optional. The reason to go further is that the short-circuit alone does nothing for the
  *partial* case, which is the one a real re-run actually hits: 40 missing cubes still costs a full
  900-shape `setup`.
- **Delegate to Snakemake** — rejected, D1, on spec 49 §6's grounds: the AML runner has no DAG and
  the two runners must agree. Snakemake stays the *local execution* runner it already is.
- **Content digests per cube** — rejected as default, spec 49 §7 Q2 and §6 unchanged: a 900-cube
  hash pass over the WAN approaches the cost of the rebuild it avoids.
- **Keep forward, make `setup` incremental instead** — i.e. cache `input.csv` and diff it. This is
  the knot in §1: the flatten identity is computed from `input.csv`, so caching it means trusting a
  cached file to decide whether the cached file is trustworthy. D3 unties this properly.

---

## 7. Questions for sign-off

1. **What is the deterministic run-folder name (D6/#83)?** Options: `runs/<window>_<hash of sorted
   shape ids + params>` (fully derived, collision-safe, opaque); or a caller-supplied `run_name=`
   defaulting to something stable like `runs/train` (readable, but two different polygon sets
   collide unless the caller is careful). *Default proposed: derived hash, with the readable prefix
   in front of it (`runs/20180401_20180930_m20_a1b2c3d4`), so it is both diagnosable and safe.*
2. **Where is the known-empty record kept (D5)?** A sibling `_manifest.json` in the run folder, or
   extra rows in `input.csv` flagged empty. *Default proposed: sibling file — `input.csv` is the
   build unit's input contract and should not grow rows that are not work.*
3. **Does `overwrite_setup_csv` survive (D4)?** With `setup` scoped to the shortfall its
   delete-then-regenerate default is close to meaningless. *Default proposed: deprecate it,
   `overwrite=` is the one control.*
4. **Does the download leg join the walk, or keep its own catalog diff?** Its diff already works and
   is cheap (one catalog read). *Default proposed: keep spec 47 D8 as-is, and have the walk simply
   not reach it when the cubes are satisfied — the win is skipping the leg entirely, not
   re-mechanising it.*
5. **Phase 1 only, or both phases (§9)?** Phase 1 is small and reversible; phase 2 is the real
   refactor. *Default proposed: land phase 1, measure a real re-run, then decide phase 2 on
   evidence rather than on this spec's estimate.*
6. **Does `verify_adapter` join the walk?** It has its own cube resume (spec 48 D5) that already
   works. *Default proposed: out of scope, no change.*

---

## 8. Best-practice alignment / sources

Cross-validation run at draft (2026-08-21), under `CLAUDE.md`'s standing permission for spec
searches. It confirmed that D1/D2's resolution order is the standard formulation rather than an fsd
invention, supplied the exact phrasing for "recursively consider each prerequisite as a target",
and supplied D8's force semantics. Searches run: Snakemake rule/wildcard resolution and DAG
construction; Snakemake `--rerun-triggers` and the force flags; GNU Make's goal/prerequisite
recursion.

### External

- **[Snakemake — Rules](https://snakemake.readthedocs.io/en/stable/snakefiles/rules.html)**:
  supplied **D1's rule semantics and D2's resolution order**. It establishes that when *"the rule's
  output matches a requested file, the substrings matched by the wildcards are propagated to the
  input files"*, and that Snakemake then **recurses on that rule's input files to build the DAG
  backwards**, repeating the match-and-propagate at each level. It also supplied the failure mode in
  D1's fourth bullet: an input file with **no rule producing it** is a prerequisite that must
  already exist. This is the precise model the user asked fsd to adopt, and D2's arrays → cubes →
  imagery chain is it with `id` as the wildcard.
- **[Snakemake — CLI / `--rerun-triggers`](https://snakemake.readthedocs.io/en/stable/executing/cli.html)**:
  supplied **D8's force semantics**, which fsd's `overwrite=` had invented independently. `--force`
  is *"force the execution of the selected target … regardless of already created output"* while
  `--forceall` is *"the selected … rule **and all rules it is dependent on**"* — exactly the
  `overwrite="flatten"` vs `overwrite=True` split, which confirms spec 49 D4's spelling maps onto an
  established distinction rather than an ad-hoc one. It also re-confirms (as spec 47 §8 and 49 §8
  both cited) that the default trigger set is `code, input, mtime, params, software-env` and that
  **mtime alone is the legacy mode** — the precedent for D3 continuing to refuse timestamps.
- **[GNU Make — How Make Works](https://www.gnu.org/software/make/manual/html_node/How-Make-Works.html)**:
  supplied **the canonical statement of the backward walk** in §1 and D1. Make starts from a *default
  goal*; *"the other rules are processed because their targets appear as prerequisites of the goal"*,
  each prerequisite being treated as a target itself, recursively. And the execution condition is
  stated as *"the recompilation must be done if the source file … is more recent than the object
  file, **or if the object file does not exist**"* — i.e. missing-output alone forces the rule, which
  is D2's short-circuit read in reverse. Make decides this on timestamps, which is precisely the half
  fsd declines (spec 49 D3); the *topology* is adopted, the *predicate* is not.
- **Bazel action keys and DVC `dvc.lock`** (cited in full in spec 49 §8, re-used here): supplied the
  confirmation that a recorded identity of "everything that defines the work" — inputs, command,
  parameters — is the right staleness predicate to hang off each edge of the graph. D3 is that
  record, moved from `input.csv` to the request so it can be evaluated before the rule runs.

### Internal

- `src/fsd/workflows/create_datacube.py::run_create_datacube` + `setup`: the §1 measurement.
  `overwrite_setup_csv=True` deletes `input.csv` and re-runs `setup`; `setup` writes `geometry.geojson`
  + `catalog.parquet` per shape. This is the evidence for the whole spec.
- `src/fsd/api.py::_flatten_identity`: reads `input_df`, which is `setup`'s output — the knot §1
  describes and D3 unties.
- `specs/49-skip-work-already-done.md` D6 + its status quote: the acceptance sentence this spec
  finishes. Its §6 supplied D1's constraint (the AML runner has no DAG) and its §7 Q2 supplied the
  digest deferral this spec does not reopen.
- `specs/47-driver-side-honesty.md` D5: D7's printed-plan requirement.
- **#83**: D6's precondition. **#54**: the per-shape control-file write cost D4 reduces. **#76**:
  §5's first risk. **#77**: why `run_inference` is out of scope.
- `tests/test_build_skip.py` (2026-08-21): already characterises the timestamped default, so AC7
  has a test to flip rather than one to write.

## 9. Implementation note

Per `CLAUDE.md`'s model split, implementation is a **Sonnet session at `/effort medium`** once
signed off. Phased so each step is independently revertible:

0. **#83 / D6 — the deterministic run folder.** Nothing else works without it, and it is valuable
   alone: it is what makes spec 49's existing skips reachable at all.
1. **D3 — request-derived identity**, written and compared but with the forward orchestrator still
   in place. One release of "the identity is computable early" before anything depends on it being
   computed early. Mirrors spec 49 §9's stamps-before-skips discipline.
2. **Phase 1: the top-level short-circuit** (§6) — target satisfied → land and return. Small, and it
   is where the no-op case's 96 s goes away.
3. **Phase 2: the full walk** — D2/D4/D5/D7, `setup` scoped to the shortfall. This is where the
   *partial* case's cost goes away, and it is the step §7 Q5 may defer.

Steps 0 and 2 carry most of the measurable value; step 3 is what makes the shape principled rather
than special-cased.
