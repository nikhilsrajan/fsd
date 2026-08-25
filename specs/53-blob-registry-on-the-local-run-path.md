---
status: current
summary: A model ref resolved against a blob registry cannot be run locally -- `bundle.load` needs a local directory and `sys.path` cannot hold an `abfss://` entry (#89). `run_inference` stages a non-local resolved bundle to scratch before load (D1), reusing `infer_shard.fetch_bundle_to_scratch`; scratch lives under the run's own output folder (D2). One defect, two decisions.
---

# Spec 53 — a blob registry that works on the local run path

**Status:** **SIGNED OFF (user, 2026-08-25)** — both §7 questions resolved at their proposed
defaults. Ready to implement. · **Opened:** 2026-08-25
**Closes:** [#89](https://github.com/nikhilsrajan/fsd/issues/89)
**Origin:** found by the user running `runbooks/52-registry-on-blob.md` against a **real**
`abfss://` registry on 2026-08-25 — after spec 52 passed 956 unit tests, two Opus review rounds and
a mutation-testing pass. MEMORY `real-run-beats-review`, again.

> **Rescoped 2026-08-25, before sign-off.** The first draft also carried #90 (the seam gate
> conflating `storage=` with `registry=`) as D3/D4. Working through what #90 actually costs showed
> it to be an ergonomics defect with a one-word workaround — drop the kwarg — rather than a
> functional one, so it was removed rather than carried. §6 records that reasoning, and #90 stays
> open as a low-priority cleanup. **This spec is now one defect and two decisions.**

---

## 1. The problem

Spec 52 §1 sells one sentence: *"a run can say `crop-rf@champion` instead of a path."* Against a
blob registry, on a local run, it cannot.

```
[model] crop-rf-t10@champion -> v1        <- resolution works, against live Azure
...
  File "src/fsd/model/bundle.py", line 84, in resolve_ref
    module = importlib.import_module(module_path)
ModuleNotFoundError: No module named 'my_adapter'
```

A bundle carries **Python code** — the adapter class — and using it means importing that code.
`_activate_bundle_code` (`bundle.py:650`) does `sys.path.insert(0, "<bundle>/code")`, and with a
blob-resolved ref that entry is `abfss://.../v1/code`. CPython ships exactly two path hooks,
`zipimporter` and `path_hook_for_FileFinder`, and neither reads a URL, so the entry is **inert** —
not wrong, simply never matched. `bundle.load`'s own docstring already states the precondition
this violates: *"`bundle_path` must be a **local** directory (the node fetches it to scratch
first)."*

**Why it went unnoticed.** `run_inference`'s **AML** path stages the bundle before use
(`runners._stage_bundle` -> `infer_shard.fetch_bundle_to_scratch`) because a fresh node starts
empty — so the cloud path was always correct. The **local** path (`_engine.run_local`, and
`_run_prebuilt_via_runner` when `cores > 1`) hands the resolved path straight to `bundle.load`.
**A blob registry works for AML runs and is broken for local runs.** The defect is pre-existing,
but only *reachable* once spec 52 made a blob registry possible at all, which is why nothing before
now could have caught it.

**Severity: no workaround short of doing the staging by hand.** The run-book carries that manual
workaround today so step 4 is completable; it is three extra lines the caller should never write.

---

## 2. Scope

**In:** `run_inference` stages a non-local resolved bundle to a local scratch directory before it
reaches `bundle.load`.

**Out:** `bundle.load`'s local-only contract (§6 option B — offered, not recommended); the AML path
(already correct); `deploy`/`verify_image`; **#90 and the seam gate** (§6); `run_inference` fetching
models from the registry *instead of* staging per run (spec 52 §7 Q2, still its own decision); a
content-addressed bundle cache with eviction (§7 Q2).

---

## 3. Decisions

### D1 — the local run path stages a non-local bundle to scratch, once

When `_resolve_model_ref` yields a path that is not local, `run_inference` fetches it to a local
scratch directory and passes **that** downstream. The primitive already exists and is exactly
right: `workflows/infer_shard.fetch_bundle_to_scratch(bundle_url, local_dir)` is manifest-driven
(no directory listing — spec 38 D3), copies `bundle.json`, every artifact and every `code/` file
via `fs.get`, and returns a directory ready for `bundle.load`. **This spec wires an existing
primitive; it writes no new transfer code.**

**Placement: in `api.run_inference`, immediately after `_resolve_model_ref`.** That is the single
choke point through which `_model_spec`, `_engine.run_local` and `_run_prebuilt_via_runner` all
receive the model, so one call fixes every local consumer. It is also where the fetch is paid
**once per run** rather than once per cube: `engine._BUNDLE_CACHE` keys on the bundle path, and a
stable local path is what lets that cache work at all.

**`_model_spec` needs no change.** It reads `bundle.json` through `fs.open`, which handles a URL
fine — so a preflight rejection still costs no transfer. **Only `sys.path` cannot take a URL**, so
only `load` needs the local copy. Staging any earlier would make every rejected call pay for a
download it never used.

> **Amendment (raised after sign-off, 2026-08-25; resolved by the user same day).** D1 as first
> written said "when `_resolve_model_ref` yields a path that is not local", with **no runner
> condition** — which contradicted **AC7** ("the AML path is untouched"). With a blob registry and
> `runner="aml"`, that wording adds a blob→local fetch that did not exist before, and the AML path
> then stages that local copy straight back up to blob (`runners._stage_bundle`) — a
> blob→local→blob round trip that is correct but wasteful, and a behavior change to a path this
> spec promised not to touch.
>
> **The gate: stage only when the bundle will be loaded on *this* machine** — i.e. when
> `runner == "local"` — using `fs.is_local(path)` (`storage/fs.py:79`) for the locality test.
> `runner="aml"` never calls `bundle.load` on the driver: it stages to blob and each node fetches
> its own copy (`infer_shard.fetch_bundle_to_scratch`), so it needs nothing from D1. Every local
> execution shape *does* need it — `cores=1` (`_engine.run_local`), the `cores>1` Snakemake
> fan-out, and local ROI mode all end at `bundle.load` in a process on this machine.
>
> **`_VALID_RUNNERS` is `("local", "aml")` today, so this gate is total.** A future runner (Azure
> Batch, per `ROADMAP.md`) must declare which side loads the bundle; the condition to write then is
> "does the driver load it", not a growing list of runner names. Recorded so the next runner does
> not inherit `runner == "local"` as though it were the question.

### D2 — scratch lives under the run's own output folder, and is not a cache

`<output_folderpath>/_model/` — created per run, beside the outputs it produced.

Rationale: it is self-cleaning by the same rules as every other run artifact, it needs no global
cache directory and no eviction policy, and it leaves "which model actually ran" inspectable next
to the run that ran it. The cost is re-fetching per run; a bundle is single-digit MB (spec 47
measured 13 MB over VPN), so this is seconds, and spec 47 D5 already prints the transfer with a
size and a ticker, so it is never silent.

---

## 4. Acceptance criteria

1. `run_inference(model="<name>@<alias>", registry="<non-local>")` on the local runner resolves,
   stages, loads and runs — the exact call that raises `ModuleNotFoundError` today (#89).
2. The bundle is fetched **once per run**, not once per datacube: a 2-cube run performs one fetch.
   Asserted by counting `fetch_bundle_to_scratch` calls, not by timing.
3. A **local** registry path is unchanged — no fetch, no copy, no new directory. The local case
   must not pay for the blob case.
4. `_model_spec` still reads a non-local bundle directly, so a call rejected in preflight performs
   **no** transfer. Asserted by driving a preflight failure and counting fetches (zero).
5. The staged bundle lands at `<output_folderpath>/_model/` and holds exactly the
   manifest-declared files — no directory listing was used to build it.
6. `cores > 1` (the `_run_prebuilt_via_runner` fan-out) uses the same staged local path, not the
   original URL.
7. The AML path is untouched **in both directions** (the D1 amendment): a run with
   `runner="aml"` stages exactly as it does today, and a blob registry with `runner="aml"`
   performs **no** local fetch — asserted by counting `fetch_bundle_to_scratch` calls on the
   driver (zero), not by inspecting timings. Every local runner shape does stage.
8. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean; no network in unit tests — the
   blob path is exercised on `memory://`, with the real-Azure proof left to the run-book, for the
   reason spec 52 §5 established.

---

## 5. Risks

**Staging per run costs a transfer, and the round trip can now go both ways.** With a blob
registry, a local run fetches blob->local, while an AML run already does local->blob. Neither is
new work in kind, but together they make spec 52 §7 Q2 (fetch from the registry instead of staging
per run) more attractive, not less. Out of scope here; noted so it is not rediscovered as a defect.

**`sys.path` mutation remains global and first-wins.** D1 does not change that; it only ensures the
entry is a real directory. `_guard_module_collision` continues to do its job, and a stale
`code/*.py` in a version directory remains importable — see spec 52 §10.2, which is why
`_write_new_version` clears an incomplete target before rewriting it.

**`<output_folderpath>/_model/` is a new name inside a user-facing output folder.** If a caller's
own outputs already use that name, they collide. The leading underscore matches the existing
`_bundle` convention (`_ensure_bundle` writes `<output_folderpath>/_bundle`), so the risk is the
same one that convention already carries.

---

## 6. Alternatives considered

**Option B — make `bundle.load` itself fetch when handed a URL.** One change fixes every caller at
once, including future ones, and is genuinely simpler than threading staging through
`run_inference`. Rejected as the recommendation because it gives `load` network I/O and a
temp-directory lifetime it does not have today, silently: spec 44 D2 made "`load` mutates
`sys.path`" a documented, bounded side effect, and "`load` may also download several MB into a
directory it chose" is a materially larger contract for a function whose whole job is to be
predictable. It also puts the fetch inside `engine._BUNDLE_CACHE`'s miss path, where getting
per-cube re-entry wrong is easy and quiet. **§7 Q1 asks anyway** — the simplicity argument is real.

**Fixing #90 here too — dropped, and this is why.** The first draft carried it as D3/D4. #90 is
the seam gate conflating `storage=` with `registry=`, so `storage="azure"` is refused on
`run_inference`'s pre-built-cubes path and spec 52 D4's `configure_storage` call is unreachable
there. It looked like the other half of the same story. It is not, because **`configure_storage`
does not authenticate** — its entire body sets `FSSPEC_ABFSS_ANON=false` and the matching
`fsspec.config` key, which *forbids the anonymous fallback* rather than supplying a credential.
Credentials come from the `az login` chain either way, which is why run-book steps 1/2/3/5 read and
wrote a real `abfss://` account with no `configure_storage` call anywhere. #90's whole cost today is
a confusing refusal when a caller passes a kwarg they did not need; the workaround is to omit it,
and `export FSSPEC_ABFSS_ANON=false` reproduces the flag by hand if it is ever wanted. It stays
open as a low-priority cleanup, with the severity assessment recorded on the issue.

*One caveat kept deliberately visible:* while that gate stands, **#86 is permanently unprovable** —
the run-book's only verb-level step cannot exercise D4. That is a bookkeeping cost, not a
functional one, and it is the one argument for fixing #90 sooner.

---

## 7. Questions at sign-off — ALL RESOLVED (user, 2026-08-25)

Both questions were signed off **at their proposed default**. Recorded individually so a later
reader sees a decision, not an unread list.

1. **[RESOLVED — default stands] D1 stages in `api.run_inference`, not in `bundle.load`.**
   `load` keeps the narrow, predictable contract spec 44 D2 gave it — it mutates `sys.path` and
   nothing else, and it never performs network I/O or chooses a temp directory. The cost, accepted
   knowingly: a *future* caller that hands `load` a URL will hit #89 again rather than being fixed
   for free. §6 keeps option B intact so that is a decision to revisit, not a rediscovery.
   Folded into **D1**.
2. **[RESOLVED — default stands] Scratch is `<output_folderpath>/_model/`, not a digest-keyed
   cache.** Per-run, self-cleaning by the same rules as every other run artifact, no eviction
   policy to design. The digest is already in `_complete.json` (spec 52 D1), so a
   content-addressed cache stays cheap to add later if the re-fetch per run ever shows up in a
   timing. Folded into **D2**.

---

## 8. Best-practice alignment / sources

### Internal — primary evidence, executed or read rather than cited

- **`sys.path` probe, executed 2026-08-25**: inserting an `abfss://` entry and calling
  `importlib.util.find_spec("my_adapter")` returns `None`; `sys.path_hooks` holds exactly
  `zipimporter` and `path_hook_for_FileFinder`. Supplies **§1's central claim** — the entry is
  inert, never matched, rather than merely mis-resolved. Per MEMORY
  `verify-the-primitive-a-spec-cites`.
- **`fsd/model/bundle.py:667` `load` docstring**: already states "`bundle_path` must be a
  **local** directory (the node fetches it to scratch first)". Supplies **D1's framing**: a
  documented precondition the local run path violates, not an undiscovered constraint.
- **`fsd/model/bundle.py:650` `_activate_bundle_code`**: the `sys.path.insert` #89 turns on —
  supplies the exact failure site.
- **`fsd/workflows/infer_shard.py:49` `fetch_bundle_to_scratch`**: manifest-driven, `fs.get`-based,
  returns a `bundle.load`-ready directory. Supplies **D1's implementation** — the primitive exists,
  so this spec wires rather than writes.
- **`fsd/workflows/runners.py:806` `_stage_bundle`**: the AML path's mirror-image staging, which is
  why that path never hit this. Supplies **§1's "why it went unnoticed"**.
- **`fsd/api.py` `run_inference`**, read directly: `_resolve_model_ref` -> `_model_spec` ->
  `_engine.run_local` / `_run_prebuilt_via_runner`, with `_raise_preflight` after the spec read.
  Supplies **D1's placement** and AC4's "preflight costs no transfer".
- **`fsd/storage/azure.py::configure_storage`**, read directly: sets `FSSPEC_ABFSS_ANON=false` and
  the matching `fsspec.config` key, and supplies no credential. Supplies **§6's argument for
  dropping #90**.
- **`adlfs 2026.8.0`, inspected**: `anon` defaults to `None`, and the anonymous branch is a
  *fallback* reached only when credential discovery fails. Supplies the other half of §6's #90
  argument.
- **`runbooks/52-registry-on-blob.md`, executed by the user against a real `abfss://` account,
  2026-08-25**: steps 1/2/3/5 passed with **no** `configure_storage` call in the process (v1 in
  32.9 s, v2 on changed content, alias repoint, idempotent re-publish writing nothing); step 4
  produced `[model] crop-rf-t10@champion -> v1` and then `ModuleNotFoundError`. This is the
  strongest evidence in the spec — a real run, not a test — and it supplies both §1's traceback and
  §6's empirical claim.

### External

None required. This is an internal API-shape decision, and every load-bearing fact above was
verified by reading or executing this repo's own code and its installed dependencies — which
CLAUDE.md's cross-validation practice prefers to citation where available.

---

## 9. Implementation note

Per CLAUDE.md's model split, implementation is a **Sonnet session at `/effort medium`** against
this spec once signed off, handed back to Opus `/effort high` for review. **One phase** — D1 + D2
are a single change and are not independently useful:

0. **D1 + D2 (#89)** — stage a non-local resolved bundle to `<output_folderpath>/_model/` in
   `run_inference`, before `_model_spec`'s consumers reach it. AC1-AC7. Testable end to end on
   `memory://`.

**Then the part tests cannot do:** re-run `runbooks/52-registry-on-blob.md` step 4 **without** the
manual workaround, against the real `abfss://` registry, and confirm it passes unaided. Claude
never runs it. **This spec is not done on green tests** — the same §5 argument spec 52 made applies
unchanged.
