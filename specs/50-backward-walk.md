---
status: current
summary: Resolve create_training_data backwards from the artifact the caller asked for — arrays, then cubes, then imagery — so a leg's expensive preflight (above all `setup`, ~96 s and ~1800 blob writes at 900 shapes) never runs to discover it had nothing to do. Completes spec 49's own acceptance sentence, which the forward orchestrator does not currently deliver.
---

# Spec 50 — resolve backwards from the target: the `create_training_data` walk

**Status: ✅ SIGNED OFF 2026-08-21 — NOT YET IMPLEMENTED.** Raised by the user 2026-08-21 after
observing that a fully-resumed `create_training_data` still paid a full `setup` pass before any
skip could fire. **All six §7 questions answered by the user at sign-off**, two of them against the
draft's proposal: **Q1** rejected a set-hash run folder in favour of per-path addressing (D6
rewritten), and **Q3** recovered the actual historical rationale, which turned out to be a
*designed* capability rather than an accident (D9, new). §8's cross-validation was run at draft and
is complete. Nothing in `src/` is touched yet.

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

**Where that delete came from (traced 2026-08-21, at the user's request):** nowhere in fsd. The
line is inherited verbatim from `fetch_satdata/src/fetch_satdata/workflows/create_datacube.py`,
and spec 08 carried it across under an explicit *"Entry point (preserve signature shape)"*
instruction — it was transcribed, not designed. Spec 08 gives a careful rationale for **`setup`
itself** (pre-slicing the large catalog per shape so parallel build jobs do not contend on one
file) and **none at all** for regenerating its output every call. Two further signs it was never
reasoned about in fsd: the legacy line is `os.remove(csv_filepath)` with no existence check, so it
raised `FileNotFoundError` on any first run — fsd silently fixed that by adding
`and fs.exists(...)` — and **no production caller passes the flag**; the only caller that has ever
set it is one test. See §7 Q3, which this changes.

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

**Out:** **multi-window training data (#84)** — D9 restores the accumulation that makes it
*reachable*, and it is broken at the array layer once it is (duplicate ids, and `median_per_id`
silently medianing two windows of the same field into one sample). Filed rather than fixed here:
it is an array/API design question, not a control-flow one. **The two must land together or in that
order**, since D9 is what exposes it; `run_inference` (its per-cell skip is decided on the node — **#77**, its own spec);
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

### D6 — the run folder is stable and addressing is PER PATH, never per set [Q1: user, 2026-08-21]

`run_folderpath` currently defaults to `{root}/runs/{run_id}` with `run_id` a fresh UTC timestamp
(**#83**), so every target is missing on every call and no walk — backward or forward — can ever be
satisfied. The default must not come from the clock.

**The draft proposed hashing the request (including the sorted shape ids) into the folder name. The
user rejected it, and was right:** a set hash makes the *group* the unit of addressing, so adding a
single polygon — or a single grid cell, for inference — changes the hash and invalidates **all 900**
cubes. The correct granularity is the one the pipeline already has:

> *"look at all the datacube paths individually … so adding a new polygon / grid only triggers
> running of that new polygon / grid instead of the whole group."*

So: **no set hash anywhere.** The run folder is a plain stable name, and the addressing granularity
comes from the path segments `setup` already builds, `run_folderpath/<params>/<id>/`. Adding a
polygon adds one `<id>` leaf and builds exactly one cube; everything else remains present and is
skipped.

**One correction the path needs to make this sound.** Today the middle segment is
`<startdate>_<enddate>_m<mosaic_days>` (spec 46 D1/D2) but the *row* identity is
`_UNIT_IDENTITY_COLS` = `(id, startdate, enddate, bands, mosaic_days, mosaic_scheme,
scl_mask_classes)`. Two requests differing only in `bands` are therefore two distinct rows that
resolve to **the same path** — the second silently overwrites the first, and the build skip reads
the wrong-band cube as "present". So the middle segment is extended so that **path granularity
equals row-identity granularity**: `<startdate>_<enddate>_m<mosaic_days>_<key>`, where `<key>` is a
short digest of `(bands, mosaic_scheme, scl_mask_classes)`.

That is a digest, but it is not the thing Q1 rejected, and the distinction is the whole point: it
digests **parameters every cell in the run shares**, never the *set of cells*. Changing `bands`
moves the whole run folder, which is correct — those are different cubes. Adding a polygon touches
nothing but its own leaf, which is what Q1 asked for. Old cubes stay addressable, so switching a
parameter back reuses them instead of rebuilding.

The AML `run_id` used for `shards/` and `_status/` stays fresh per submission: it identifies a
*submission*, which is the right thing for it to identify. Only **artifact** paths become
deterministic.

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

### D9 — `input.csv` accumulates: append and dedupe, never delete [Q3: user, 2026-08-21]

The draft proposed deleting `overwrite_setup_csv` as a meaningless inherited flag. The user
recovered the actual rationale, and it inverts the finding — **the delete was a workaround for a
missing dedupe, guarding a capability that was deliberately designed:**

> *"when setup was run there were two things that was allowed to happen. if an input.csv didn't
> exist, the file was created. if input.csv existed then new rows were appended. the reason
> appending was helpful was because that allowed for creation of training data with different start
> and end dates … I had not implemented a way to check if the exact entry existed within the
> input csv and skip it — which is the true solution."*

**That true solution already exists in fsd.** `create_datacube._dedupe_on_unit_identity` (spec 38
D13, #53) collapses rows sharing `_UNIT_IDENTITY_COLS`, keeping the newest, and its docstring states
the intent exactly: *"an idempotent re-run of setup (which appends unconditionally) must not grow
input.csv by one duplicate copy of every unit each time. A re-run adding a genuinely new shape (or a
changed window/params for an existing id) still adds a distinct row — this is a dedupe, not a 'one
row per id' collapse."*

So the inherited `overwrite_setup_csv=True` does not merely predate the fix — **it actively defeats
it.** Deleting `input.csv` leaves nothing to append to and nothing to dedupe against, which is why
the accumulate-across-windows capability has been unreachable in fsd since day one, and why nobody
noticed the mechanism that would have supported it was already written.

Therefore: `overwrite_setup_csv` is **removed**, `setup` appends, and `_dedupe_on_unit_identity`
does what it was built to do. Staleness is served by D3's identity, not by demolition.

**Consequence, and why #84 is filed:** this makes multi-window training data *reachable*, and it is
broken one layer up — `ids.npy` carries no window component, so two windows of one field collide,
and `median_per_id` then medians them into a single sample without a word. D9 must not land ahead of
that fix, or the pipeline will start quietly producing wrong training sets in a case it currently
just refuses to produce at all.

### D10 — `verify_adapter` always verifies; only its cube may resume [Q6: user, 2026-08-21]

The draft proposed leaving `verify_adapter` out of scope. The user's answer is sharper and becomes a
decision rather than an omission: *"verify_adapter must run because its purpose is to verify."*

A verb whose entire job is to answer "does this adapter compute the right thing?" must never answer
from cache. The distinction the walk has to respect:

- the **cube** is an *input* — resuming it is legitimate, is what makes the iterate-on-the-adapter
  loop fast, and is already spec 48 D5;
- the **adapter run** is the *work* — it re-runs every time, unconditionally.

This is what `verify_adapter` already does (`run_infer_only(..., overwrite=True)`), so no code
changes. It is recorded here so a later "optimisation" that notices `output.tif` already exists has
a decision to argue with rather than a gap to fill.

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
7. `run_folderpath` carries no clock: two identical calls seconds apart address identical cube
   paths (#83; `tests/test_build_skip.py`'s characterisation test flips from asserting a timestamp
   leaf to asserting equality).
7a. **Adding one polygon rebuilds exactly one cube** (D6/Q1): 900 shapes built, then 901 requested →
   the shortfall is 1 and `setup` receives 1 shape. No set-level hash appears in any path.
7b. Two requests differing only in `bands` resolve to **different** cube paths, and neither is read
   as "present" for the other (D6).
7c. `setup` run twice with **different windows** against the same `run_folderpath` yields
   `input.csv` with both sets of rows and **no duplicates**; run twice with the *same* window it
   yields one set (D9, `_dedupe_on_unit_identity`). `overwrite_setup_csv` no longer exists.
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

  **[Addendum, implementation review 2026-08-21 — not a change of decision.]** The escape hatch for
  that last case is `overwrite="datacubes"`/`True`: it runs the legacy full-`setup` pass, which
  re-derives every shape straight from the catalog, and **clears this window's manifest entry** as
  it does so. That clearing is required rather than incidental — once the manifest is subtracted
  from the request-side identity (which it must be, or a single imagery-less cell makes D2's
  short-circuit unmatchable forever), the manifest becomes load-bearing for identity *equality*, so
  it must never be write-only: an id that regains an `input.csv` row is forgotten, or the two
  identities can never agree again and the short-circuit is dead for that request. The *scoped*
  walk still never rediscovers a known-empty cell — that is this bullet's risk, working as designed.
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

## 7. Questions at sign-off — ALL RESOLVED (user, 2026-08-21)

1. **[RESOLVED — default OVERTURNED]** **What is the deterministic run-folder name (D6/#83)?**
   → **no set hash.** A hash over the shape ids makes the group the unit of addressing, so one new
   polygon invalidates all 900. Address per path instead, letting `<params>/<id>` carry the
   granularity it already carries. The params segment is extended so path granularity matches
   `_UNIT_IDENTITY_COLS`. Folded into **D6**.
2. **[RESOLVED — default stands]** **Where is the known-empty record kept (D5)?** → a sibling
   `_manifest.json` in the run folder. `input.csv` is the build unit's input contract and should not
   grow rows that are not work.
3. **Does `overwrite_setup_csv` survive (D4)?** The history (§1) reframes this from "is the flag
   still useful?" to "was the mechanism ever right?". The flag is not arbitrary — it is a crude
   answer to a **real** question: `input.csv` is derived from the catalog, the shapes, the window
   and the run parameters, so a *cached* one can silently describe a **different request** than the
   one being made. Deleting it unconditionally guarantees that never happens. That is the
   pre-identity answer: always redo, never check.

   fsd has since grown the precise answer to exactly that question, and already applies it on the
   other side of the pipeline. `run_inference` calls `_check_resume_identity` on its cached
   `cells/input.csv`, compares the cell-id set against the freshly tiled grids, and **raises
   `PreflightError` on any drift** rather than regenerating blindly (spec 47 D1, #66). The build
   leg of `create_training_data` never got that upgrade — it still uses the sledgehammer.

   *Default proposed: **replace, do not merely deprecate.** `overwrite_setup_csv` goes away and its
   real concern is served by D3's request-derived identity: a cached `input.csv` whose identity
   matches is reused, one that does not match is refused the way `run_inference` refuses (or
   regenerated, §7 Q3a). This makes the two halves of the pipeline answer the staleness question
   the same way, which spec 47 D1 already established as the house style.*

   **Q3a, following from that: on a mismatch, refuse or regenerate?** `run_inference` refuses
   because rewriting `input.csv` would orphan per-cell outputs already written under the old ids
   (spec 47 D1). The build leg has no such orphaning problem — cubes are addressed by id, and a
   changed request simply needs different cubes. *Default proposed: regenerate for the build leg,
   and say so in the `[plan]` block; the asymmetry with `run_inference` is real and comes from
   there being outputs to orphan there and none here.*
4. **[RESOLVED — default stands]** **Does the download leg join the walk, or keep its own catalog
   diff?** → keep spec 47 D8 as-is; the walk simply does not reach it when the cubes are satisfied.
   The win is skipping the leg entirely, not re-mechanising it.
5. **[RESOLVED — default OVERTURNED]** **Phase 1 only, or both phases (§9)?** → **both.** The
   phasing in §9 stays as the landing order, but phase 2 is committed rather than conditional: the
   partial case is the one a real re-run hits, and it is the one phase 1 does nothing for.
6. **[RESOLVED — sharpened]** **Does `verify_adapter` join the walk?** → **it always verifies.**
   Not "out of scope" but a decision: the cube is an input and may resume; the adapter run is the
   work and never does. Folded into **D10**.

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
- `specs/47-driver-side-honesty.md` D5: D7's printed-plan requirement. Its **D1** +
  `api.py::_check_resume_identity` supplied §7 Q3's reframing: fsd already answers "does this
  cached work list describe THIS request?" precisely, on `run_inference`, by comparing the cached
  id set and refusing on drift. `overwrite_setup_csv` is the same question answered by demolition.
- `fetch_satdata/src/fetch_satdata/workflows/create_datacube.py` (read-only legacy) and
  `specs/08-workflows.md`'s *"preserve signature shape"*: together they establish that
  `overwrite_setup_csv` was **inherited, never designed for fsd** — §1. Spec 08 documents why
  `setup` pre-slices the catalog (parallel build jobs must not contend on one large file) and is
  silent on why its output is thrown away each run.
- `src/fsd/workflows/create_datacube.py::_dedupe_on_unit_identity` + `_UNIT_IDENTITY_COLS`
  (spec 38 D13, #53): supplied **D9**. The append-without-duplicates mechanism the user described as
  the "true solution" was already implemented; `overwrite_setup_csv` is what makes it unreachable.
  Its column tuple is also what D6's path segment is corrected against.
- `src/fsd/model/features.py::median_per_id`: supplied D9's consequence and **#84** — it groups by
  `np.unique(ids)`, so two windows of one field become one medianed sample.
- **#83**: D6's precondition. **#54**: the per-shape control-file write cost D4 reduces. **#76**:
  §5's first risk. **#77**: why `run_inference` is out of scope. **#84**: D9's ordering constraint.
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
3. **D9 — append + dedupe, `overwrite_setup_csv` removed.** Small, but sequence it **with or after
   #84's array-layer fix**: this is the step that makes multi-window reachable, and reachable-and-
   broken is worse than unreachable.
4. **Phase 2: the full walk** — D2/D4/D5/D7, `setup` scoped to the shortfall. Committed at sign-off
   (§7 Q5), and where the *partial* case's cost goes away.

Steps 0 and 2 carry most of the measurable value; step 4 is what makes the shape principled rather
than special-cased. Step 3 is the one with an ordering constraint outside this spec.
