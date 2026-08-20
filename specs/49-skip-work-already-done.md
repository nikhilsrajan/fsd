---
status: current
summary: Extend spec 47 Part C's "don't redo what's done" from the download leg to the other two legs of create_training_data — skip the datacube build when every cube is already present, and skip the flatten when its arrays are already derived from exactly those cubes, unless overwrite says otherwise.
---

# Spec 49 — skip the work that is already done: cubes, then flatten

**Status: ✅ SIGNED OFF 2026-08-20 — NOT YET IMPLEMENTED.** **All six §7 questions were signed
off on their proposed defaults** (user, 2026-08-20), and **§8's external cross-validation is
complete**. It confirmed D3's central choice against Bazel's and DVC's own reasoning, and
**strengthened** D3's Azure argument: a blob's `Last-Modified` is not merely unreliable, it is
read-only and cannot be back-dated by any means — so for the blob side, declining timestamps was
never a judgement call. Nothing in `src/` is touched yet. Raised by the user 2026-08-20, immediately
after signing off spec 48 (then `test_adapter`, now `verify_adapter`): *"just like how in create_training_data, downloading was avoided if all
required downloads were already present, creation of datacubes should also be skipped if all
datacubes already present. And if all datacubes were already present and training data numpy
arrays are also present without any discrepancy … then even flattening becomes unnecessary
(unless modeller forces the overwrite) — the only task create_training_data does is to download
the flattened numpy arrays."*

> **The one sentence:** spec 47 Part C taught the **download** leg not to redo finished work; the
> **build** and **flatten** legs never learned, so a re-run that should cost one file transfer
> still costs a cluster fan-out.

---

## 1. The gap

`create_training_data` has three legs. Spec 47 fixed one.

| leg | skips finished work? | what a no-op re-run costs today |
|---|---|---|
| **download** | ✅ spec 47 D8/#64 — driver-side catalog diff, returns without submitting | seconds |
| **build datacubes** | ❌ | a full fan-out: N jobs, N cold starts |
| **flatten** | ❌ | a reduce job over every cube |

The end state the user describes is the honest one: when everything downstream is already there,
**the only thing `create_training_data` should do is fetch the flattened arrays.**

### What each leg already has to work with

- **Build.** `create_datacube.setup` writes `input.csv`, one row per shape, each with an
  `export_folderpath` and a `datacube_filepath`. Spec 46 D1/D2 made that folder name deterministic
  from the *requested* window and `mosaic_days` (`20180401_20180930_m20`), so a re-run with the
  same parameters addresses **exactly the same paths**. Whether each cube exists is therefore a
  question the driver can answer from `input.csv` alone — the same shape as spec 47's catalog diff.
  Note `workflows.task` already skips an existing cube *on the node* (its docstring: "returns
  immediately without rebuilding"), which is precisely the spec 47 #64 situation: the skip is real
  but it happens **after** the cold start it should have avoided.
- **Flatten.** Its inputs are the cubes named in `input.csv`; its outputs are
  `data.npy`/`ids.npy`/`labels.npy`/`metadata.pickle.npy` in `export_folderpath`. Nothing today
  records **which cubes** a given set of arrays was derived from.

---

## 2. Scope

**In:** a driver-side skip for the **build** leg of `create_training_data` (and of
`create_datacube.run_create_datacube`, which is where the fan-out is dispatched); a driver-side
skip for the **flatten** leg; an `overwrite=` control that can force either; and the staleness
record that makes the flatten skip safe.

**Out:** the download leg (done, spec 47 D8); `run_inference`'s per-cell skip (already resumable
via `_existing_outputs`, spec 47 D5 — different mechanism, unchanged); changing artifact formats;
`fs.rm` on blob (#50); the inference fan-out.

---

## 3. Decisions

### D1 — the build leg skips per-cell, and short-circuits when the shortfall is empty

Mirrors spec 47 D8 exactly, one level up:

1. after `setup` has written `input.csv`, read the `datacube_filepath` column;
2. the **shortfall** is the rows whose cube is absent;
3. **shortfall empty** → print `[build] 0 of 900 cubes missing; nothing to build` and return
   **without submitting a single job**;
4. **shortfall partial** → dispatch **only** the missing rows, and say so.

Step 4 matters as much as step 3, and for the same reason spec 47 gave: a run that is 95 % built
must not fan out 100 %. This also converts `workflows.task`'s existing node-side skip from a
cold-start-priced no-op into a driver-side one.

### D2 — presence is `datacube.npy` **and** `metadata.pickle.npy`, both non-empty

A cube is two files (spec: `datacube.npy` + `metadata.pickle.npy`, the pickle kept for the
rasterio transform/CRS). Treating the `.npy` alone as "present" would accept a half-written cube —
the same class of defect as #74, which spec 47 §3a documented for downloads and chose to fix at
source. **This spec must not repeat it**: the presence test names both files, and §7 Q3 asks
whether cube writes are atomic today.

### D3 — the flatten skip keys on **cube identity**, never on modification time

This is the load-bearing decision, and it deliberately declines the mechanism the user proposed.

The user's formulation was *"without any discrepancy in the time of creation (eg. datacubes
creation time being after training data numpy arrays creation)"*. The intent is exactly right — the
arrays must be **derived from the cubes as they are now**. Timestamps are the wrong instrument for
it here, for three concrete reasons:

- **The two sides live on different clocks.** The cubes are on blob (`abfss://`, server-stamped by
  Azure); the flattened arrays land **locally** (`export_folderpath`, stamped by the laptop). A
  comparison between them is a comparison between two unsynchronised clocks. Ordinary skew silently
  produces both false "fresh" and false "stale".
- **On blob, the timestamp structurally cannot mean what the rule needs it to mean.** A blob's
  `Last-Modified` is **read-only**, auto-assigned by Azure on every create or overwrite, and cannot
  be set or back-dated through REST, the SDKs, PowerShell, the CLI or ARM (§8). A cube that is
  transferred, re-uploaded or restored therefore looks new without its content changing, and no
  flag can preserve the original — `--preserve-last-modified-time` does not apply to Blob
  destinations at all. This is not skew; it is the storage layer refusing to carry the fact.
- **fsd already chose identity over time, twice.** Spec 47 D1 refuses a resume on the cached *id
  set*, not on file age. Snakemake's own file-modification-time trigger is explicitly its
  **legacy** mode (spec 47 §8). Introducing an mtime rule now would be the one place in the
  pipeline that regressed to it.

**Instead: a stamp.** When flatten completes it writes `_flatten_stamp.json` beside the arrays,
recording the identity of the inputs it consumed — proposed: the sorted list of
`(id, datacube_filepath)` from `input.csv`, plus the run parameters that shaped the arrays
(`bands`, `mosaic_days`, window, `aggregate`, `feature_sequence` fingerprint), plus a content
digest per cube if §7 Q2 says so. The flatten leg is skippable **iff** a stamp exists and the
identity it records equals the identity of the current cube set. Anything else — a cell added, a
cube rebuilt, a band list changed — is a mismatch, and mismatch means run.

This is strictly stronger than the user's time rule (it catches a cube rebuilt with *identical*
mtime, and a changed `aggregate` that touches no cube at all) and it has no clock in it.

### D4 — `overwrite=` forces a leg, and names which one

One control, three settings, so a modeller can force exactly the leg they mean:

```python
overwrite=False            # default: skip whatever is already done (D1, D3)
overwrite="datacubes"      # rebuild cubes (and therefore re-flatten: the stamp will mismatch)
overwrite="flatten"        # keep cubes, redo the flatten
overwrite=True             # both
```

`overwrite="datacubes"` implying a re-flatten is not a special case — it falls out of D3, because
rebuilt cubes fail the stamp comparison. That is the property that makes the stamp worth having:
the legs cannot disagree about what is stale.

### D5 — the skip is announced, never silent

Every skip prints what it skipped and why, in spec 47 D5's established shape:

```
[download] 0 of 828 assets missing; nothing to download
[build]    0 of 900 cubes missing; nothing to build
[flatten]  arrays match the current 900 cubes (stamp 2026-08-20T…); skipping
[fetch]    export -> ./demo_training_data | 4 files, 18.2 MB
```

A user who cannot tell the difference between "it worked instantly" and "it did nothing" will not
trust the fast path, and will pass `overwrite=True` forever out of superstition — which costs more
than the feature saves. Spec 47's whole thesis applies.

### D6 — when all three legs skip, the verb still returns a real `TrainingData`

The user's framing — *"the only task create_training_data does is to download the flattened numpy
arrays"* — is the acceptance criterion. The fully-skipped path must still land the arrays in
`export_folderpath` and return a `TrainingData` whose `.load()` works, indistinguishable from a
full run's. A skip is an optimisation, never a different return shape.

---

## 4. Acceptance criteria

1. `create_training_data` whose every cube already exists submits **no build job** and prints
   `[build] 0 of N cubes missing`.
2. A partially-built run dispatches **only** the missing cells: 900 shapes, 40 missing → 40 rows in
   the submitted shards.
3. A cube counts as present only when **both** `datacube.npy` and `metadata.pickle.npy` exist and
   are non-empty (D2).
4. Flatten is skipped when `_flatten_stamp.json` records exactly the current cube set and run
   parameters; the arrays are still landed and a working `TrainingData` returned (D6).
5. Flatten is **not** skipped when: a cell is added or removed; a cube is rebuilt; `bands`,
   `mosaic_days`, the window, or `aggregate` changed. Each case is its own test.
6. **No modification time is read anywhere in the skip logic** — asserted by test (D3).
7. `overwrite="datacubes"` rebuilds cubes and re-flattens; `overwrite="flatten"` keeps cubes and
   re-flattens; `overwrite=True` does both; `overwrite=False` is the default (D4).
8. An invalid `overwrite=` value raises, naming the valid ones (spec 47 Part D: caller misuse
   raises).
9. Every skip prints one line naming what was skipped and why (D5).
10. A fully-skipped run and a full run produce `TrainingData` objects whose `.load()` outputs are
    equal (D6).
11. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean; no network in the unit tests.

---

## 5. Risks

- **The stamp goes stale against the archive, not the cubes.** If a granule is re-ingested and cubes
  are *not* rebuilt, the stamp still matches and flatten is still skipped — correctly, since the
  cubes did not change, but the arrays are then derived from imagery the user may think was
  refreshed. Names the same hole as #74. The honest mitigation is D5's printed line, plus
  `overwrite=`.
- **A skip that is wrong is much worse than a rebuild that is wasteful.** Every mismatch case must
  fail *towards* running. AC5 enumerates them, and the default on any doubt (missing stamp,
  unreadable stamp, unrecognised schema) must be to run.
- **`feature_sequence` fingerprinting is the weak link.** It is a list of `(callable, kwargs)`; a
  changed *function body* with the same name will not change any obvious fingerprint. §7 Q4.
- **Interaction with spec 48.** `verify_adapter` also lands artifacts locally and also wants a
  resume-identity check (spec 48 D5). If both invent one, they will differ. §7 Q5 asks whether the
  stamp mechanism should be shared from the start.

---

## 6. Alternatives considered

- **Modification times, as originally proposed.** Rejected — D3: two unsynchronised clocks (blob vs
  laptop), mtime resets on copy, and it is the mode Snakemake itself calls legacy.
- **Content hashes of every cube.** Rejected as the *default*: a 900-cube hash pass over the WAN
  approaches the cost of the rebuild it avoids — the same objection spec 47 D9 raised against
  per-asset stats. Offered as an opt-in in §7 Q2, mirroring D9's opt-in existence pass (#75).
- **Let Snakemake decide.** Tempting, since the local runner already has a DAG with file targets.
  Rejected: the AML runner has no such DAG, and the skip must behave identically under both runners
  or the two paths diverge — the same reason spec 47 put the download diff on the driver.
- **A single `resume=True` flag covering all three legs.** Rejected: it cannot express
  "rebuild cubes but not the download", which is the common case after an archive fix.

---

## 7. Questions at sign-off — ALL RESOLVED (user, 2026-08-20: every default stands)

1. **[SIGNED OFF — default stands]** **Does the build skip belong in `create_training_data`, or in
   `create_datacube.run_create_datacube`?** The latter benefits `run_inference` too, but changes a
   shared path. *Default proposed: `run_create_datacube`, so every caller gets it — matching where
   spec 47 put the download diff.*
2. **[SIGNED OFF — default stands]** **Should cube presence be openable-and-well-formed, or merely non-empty?** A truncated cube
   passes D2 today, exactly as a truncated download passes spec 47 D9. *Default proposed:
   non-empty by default, with an opt-in deeper check — and file the atomic-write issue for cubes as
   the real fix, mirroring #74.*
3. **[SIGNED OFF — default stands]** **Is `overwrite=` the right spelling**, given `run_inference` already has a boolean `overwrite`?
   A string-or-bool union on one verb and a bool on another is a small inconsistency. *Default
   proposed: accept both spellings, document the string form.*
4. **[SIGNED OFF — default stands]** **How is `feature_sequence` fingerprinted?** Qualified function names + kwargs is cheap and
   misses an edited body; source hashing catches it but is brittle across formatting. *Default
   proposed: qualname + kwargs, and say plainly in the docstring that editing a feature function's
   body does not invalidate the stamp.*
5. **[SIGNED OFF — default stands]** **Should the stamp mechanism be shared with spec 48's resume-identity check** (D5 there), rather
   than each spec growing its own? *Default proposed: yes — one helper, since both are answering
   "were these artifacts derived from exactly this request?".*
6. **[SIGNED OFF — default stands]** **Does the same treatment belong on `run_inference`'s build leg?** It has a per-cell output skip
   but pays the same cold start to discover it. *Default proposed: out of scope here, file an
   issue.*

---

## 8. Best-practice alignment / sources

Cross-validation run at sign-off (2026-08-20). It **confirmed D3's central choice** (identity, not
timestamps) against how the two most-cited content-addressed build systems justify the same
decision, **validated the sidecar-stamp shape** against DVC's `dvc.lock`, and **strengthened D3's
Azure argument** from "copying resets mtime" to something considerably harder. Searches run:
Bazel/Nix content addressing vs Make's mtime; DVC `dvc.lock` staleness decisions; Azure Blob
`Last-Modified` semantics on copy.

### External

- **[Bazel — Remote Caching](https://bazel.build/remote/caching)** and
  **[Bazel caching explained: how Bazel works](https://sluongng.hashnode.dev/bazel-caching-explained-pt-1-how-bazel-works)**:
  supplied the **direct confirmation of D3**. The contrast is drawn in exactly the terms this spec
  needed: a system like Make decides "up to date" by **comparing timestamps** of outputs against
  inputs, whereas Bazel tracks staleness by **inspecting the content digests of the inputs**. It also
  supplied the shape of the record — Bazel's action key is *"a hash of everything that defines the
  action: the input files' content digests, the command string, and the environment variables"* —
  which is precisely D3's proposed stamp (the cube set, plus the run parameters that shaped the
  arrays). D3 was written before this search; the search confirms it converged on the standard
  answer rather than inventing one.
- **[DVC — Running Pipelines](https://doc.dvc.org/user-guide/pipelines/running-pipelines)** and
  **[dvc status](https://dvc.org/doc/command-reference/status)**: supplied the validation that a
  **sidecar lock file is the conventional shape**, not an fsd invention. `dvc.lock` pins the hashes
  of every dependency *and output* per stage; `dvc repro` re-hashes dependencies, compares against
  the lock, and skips any stage whose inputs, code or **parameters** are unchanged. `_flatten_stamp.json`
  is the same mechanism with one stage. Two refinements adopted from this source: the stamp should
  record the **outputs** as well as the inputs (so a deleted or truncated array invalidates it), and
  **parameters count as dependencies** — which is what makes a changed `aggregate` invalidate the
  stamp even though no cube moved. Both were already in D3; this confirms they are load-bearing
  rather than optional.
- **[Azure/azure-storage-azcopy #1296](https://github.com/Azure/azure-storage-azcopy/issues/1296)**,
  **[#3194](https://github.com/Azure/azure-storage-azcopy/issues/3194)** and
  **[Microsoft Q&A — preserving Last-Modified when copying blobs](https://learn.microsoft.com/en-us/answers/questions/5808274/preserving-original-last-modified-timestamp-when-c)**:
  **strengthened D3's second bullet beyond what it claimed.** The draft said copying resets mtime.
  The actual position is harder: a blob's `Last-Modified` is **read-only and auto-assigned by Azure
  on every create or overwrite**, and **cannot be set or back-dated** through REST, the .NET/Java/
  Python SDKs, PowerShell, the CLI or ARM. `--preserve-last-modified-time` does not apply to Blob
  destinations at all. So the timestamp on a cube is not merely unreliable — it is **structurally
  incapable** of carrying "when this cube's content was produced" across any transfer. D3's rejection
  of mtime is therefore not a judgement call about skew; for the blob side it is the only option.
  (The documented workaround — stash the original time in custom metadata — is itself a stamp, which
  is what D3 proposes.)
- **[Snakemake — CLI / `--rerun-triggers`](https://snakemake.readthedocs.io/en/stable/executing/cli.html)**
  (already cited by spec 47 §8, re-used here): its default triggers are `code`, `input`, `mtime`,
  `params`, `software-env`, and **`mtime` alone is explicitly the *legacy* mode**. This is the
  precedent D3 leans on for treating a parameter change (`aggregate`, `bands`) as invalidating, not
  just a file change.

### Internal

- `specs/47-driver-side-honesty.md` D8/D9/§3a: the whole template. D1 is D8 one level up; D2 and
  Risk 1 are §3a's truncation hole restated for cubes; D5's printed-line requirement is D9's "the
  cheap key must be named, never invisible".
- `specs/47-driver-side-honesty.md` D1: supplied D3's core argument — fsd already refuses on
  *identity* rather than file age, so an mtime rule here would be the one place in the pipeline that
  regressed.
- `specs/46-run-addressability-and-grid-dedup.md` D1/D2: the deterministic run-folder name is what
  makes a re-run address the same cube paths at all — the precondition for D1.
- `src/fsd/workflows/task.py`: its existing "returns immediately without rebuilding" node-side skip
  is the evidence that the work is *already* known to be redundant, just discovered after the cold
  start — exactly the #64 shape.
- `src/fsd/api.py::create_training_data`: established the three-leg structure and that the flatten
  phase delegates to `flatten_training_data`, so the skip has one place to live.
- `specs/48-verify-adapter.md` D5: the other caller of the shared identity helper (§7 Q5).
- The user's own statement of the requirement (2026-08-20), quoted in the status line — the source
  of D6's acceptance criterion, and of the mtime formulation D3 declines.

**Nothing outstanding.** The one finding that changes the spec is the Azure `Last-Modified` result,
which makes D3's second bullet stronger than drafted; D3's text is updated to match rather than left
understating its own case.

## 9. Implementation note

Per `CLAUDE.md`'s model split, implementation is a **Sonnet session at `/effort medium`** once
signed off. Landing order, smallest and safest first:

0. **`overwrite=` plumbing + validation** (D4) — no behaviour change yet, but it is what every
   later step branches on.
1. **The build skip** (D1/D2) — a direct analogue of spec 47 Part C, against `input.csv` instead of
   the catalog.
2. **The stamp** (D3) — write it on every flatten first, *without* reading it. One release of
   stamps-but-no-skips makes step 3 safe to land.
3. **The flatten skip** (D3/D6) — read the stamp and short-circuit. The riskiest step, and the one
   §7 Q2/Q4 may narrow.
