---
status: current
summary: run_inference's post-run window is ~2 sequential blob round-trips per output cell plus one small write per Item — 777 s of a 300-cell run, scaling with cell count rather than work. Re-use the footprints the driver already holds (D2), thread the remaining COG opens with a per-thread GDAL env (D3), thread the Item writes (D4), stop GDAL probing for sidecars (D5), and print the segment timings so the next run measures itself (D1). Advances #61.
---

# Spec 57 — the collect + STAC window, and the round-trips in it

**Status:** **SIGNED OFF (user, 2026-08-27)** — all three §7 questions resolved as proposed.
Not implemented. · **Opened:** 2026-08-27
**Advances:** [#61](https://github.com/nikhilsrajan/fsd/issues/61) (closes fixes (b) and (c);
fix (d), node-side Item emission, stays open).
**Origin:** the user, 2026-08-27, watching a real AML run: *"i want to understand what is taking
so long in `_finalize_outputs`. there was a long gap between [collect] and [merge]. is creating a
stac catalog taking a long time? if yes, is there a way to speed it up?"*
**Related:** [spec 47](47-driver-side-honesty.md) D5 (`_existing_outputs`, #61 fix (a), landed),
[spec 28](28-stac-output-geometry-fix.md) (the footprint contract this narrows),
[#77](https://github.com/nikhilsrajan/fsd/issues/77) (the *other* half of the same complaint —
dispatching work already done; deliberately not this spec).

---

## 1. The problem

`_finalize_outputs` (`api.py:1330`) is two steps, and both scale with the **number of output
cells** rather than with the amount of work. Measured on a 300-cell run
(#61, run-book 41 Step 3, read from the blobs' own `last_modified` — a direct measurement, not a
residual):

| segment | wall | per unit |
|---|---|---|
| collect (`cog_outputs_to_items`, reads only, zero writes) | **616 s** | 2.05 s/cell |
| STAC writes (300 Items + collection + catalog) | **161 s** | 0.53 s/item |
| merge | 193 s | — |

The gap the user watched is the first two: **777 s**, on a run whose actual inference was skipped.

**Where the 616 s goes.** For every output cell, `cog_outputs_to_items` (`catalog/stac.py:260`)
does two *sequential* remote reads:

1. `rio_open(fp)` — a GDAL/VSI open of the output COG, purely to read `crs.to_epsg()`,
   `height`/`width` and `transform` for `proj:*`.
2. `_read_footprint_geometry(geom_path)` — a `fs.open` of that cell's `geometry.geojson`, spec
   28's true-footprint contract.

At ~1 s each over VPN, 300 cells × 2 ≈ 600 s. #61's fix (a) already removed a third round-trip
(300 `fs.exists` → one `fs.glob`, spec 47 D5).

**Why this is worth a spec rather than a patch.** The obvious fix — thread the loop — is
*wrong as #61 currently states it* (§8), and one of the two round-trips should not exist at all.

## 2. Scope

**In:** the driver-side post-run window of `run_inference` — `cog_outputs_to_items`,
`write_stac_catalog`, and the GDAL env every remote raster open uses.

**Out:**

- **Node-side Item emission** (#61 fix (d)): have each node write its own Items so the driver only
  concatenates, making collect scale with `n_shards` instead of `n_cells`. Strictly better and
  strictly bigger — it changes the node contract. Named, not done.
- **Dispatching work already done** (#77). The same run felt slow for two independent reasons;
  this spec is only the second one.
- **Running the driver in Azure.** #61 notes it is ~50× lower per-round-trip latency for the same
  code. That is a deployment change; D2–D5 help the laptop case too, and are additive to it.
- **`merge`.** Its 193 s is 300 COG *pixel* reads — real work, not overhead. D5 incidentally helps
  it; nothing else here touches it.

## 3. Decisions

### D1 — The window measures itself

Today the only evidence of where the time goes is a gap between two prints, and the numbers in §1
came from reading blob `last_modified` after the fact (run-book 41). `_finalize_outputs` prints
one line per segment with elapsed seconds and a per-unit rate, through the existing
`fsd.progress` ticker:

```
[collect] 299/299 outputs described | 2.05 s/output | elapsed 613s
[stac]    301/301 objects written   | 0.53 s/object | elapsed 159s
[merge]   299/299 inputs reprojected …
```

**This lands first, before any optimisation** — otherwise "it feels faster" is the only available
verdict, and #61's own history shows how easily the wrong component gets blamed (its original
suspect was a 627 s bundle upload that direct measurement showed to be 13 s).

### D2 — The ROI path stops re-reading footprints it wrote

`geometry.geojson` per cell is `srow["geometry"].buffer(0)` — written by
`create_datacube.setup` (`workflows/create_datacube.py:188`) straight out of the
`shapes_gdf` it was handed, which for ROI mode **is the `grids.geojson` the driver itself wrote
minutes earlier** (`api.py:1800`) and still holds in memory as `grids`. The driver is paying a
sequential blob read per cell to fetch back geometry it authored.

So `cog_outputs_to_items`'s `geometries` mapping accepts, as a value, **either** a path (today's
behaviour, read through the seam) **or** an already-loaded geometry, used as-is. `_run_inference_roi`
passes the latter, keyed by cell id.

*This tightens spec 28's contract rather than loosening it.* Today the path form carries a
cross-check — `geometry.geojson`'s `properties.id` must equal the item id derived from the output
path, else raise. In the in-memory form that check becomes **structural**: the driver looks the
footprint up *by* the item id, so a mismatch cannot be constructed. The raise stays for the path
form, which still has two independent sources to disagree.

**Only ROI mode gets this.** `cog_outputs_to_items_from_manifest`, a bare list of COGs, and the
pre-built-cube modes have no `grids` — the path form is their only source and is unchanged.

### D3 — Thread the remaining COG opens, one GDAL env **per worker thread**

The `rio_open` per output stays (nothing else knows the written COG's CRS/shape/transform until
#61 fix (d) lands), but it is I/O-bound and independent per cell, so it threads.

**The trap, and why #61's stated fix is wrong.** #61 says *"do it under a single
`raster.rio_env`, since GDAL's env stack is thread-local"*. Thread-local means the **opposite** of
what that sentence concludes: rasterio 1.4.4 stores the active env in `local = ThreadEnv()`
(`rasterio/env.py:56`), and `defenv`/`hasenv`/`getenv` all key off `local._env`. An `Env` entered
on the driver thread therefore **does not exist** in a worker thread. Verified directly
(2026-08-27):

```
main thread  : hasenv = True  | token visible = True
worker thread: hasenv = False | token visible = False
```

Since `rio_env` is what carries `AZURE_STORAGE_ACCESS_TOKEN` and `AZURE_STORAGE_ACCOUNT`
(`raster/__init__.py:50`), a single driver-thread env would leave every worker opening a remote
COG **with no credential** — a 401, or worse an anonymous read. So **each worker enters its own
`rio_env([fp])`**. `storage_token()` is called per env, which its own docstring already establishes
is cheap: *"`get_token` caches and auto-refreshes internally — re-fetching per open beats a
hand-rolled expiry margin."*

`rio_open`'s existing "⚠️ one dataset at a time" warning is about the **LIFO** env stack within one
thread; one open per thread, scoped by `with`, does not touch that.

### D4 — Thread the STAC Item writes

`write_stac_catalog` ends in `catalog.save(catalog_type=SELF_CONTAINED, stac_io=_StorageStacIO())`,
which walks the tree and writes each Item as its own small blob, sequentially: 301 objects,
0.53 s each. The objects are independent, so they thread the same way D3's reads do — no GDAL env
involved, just `fs.write_text`.

The catalog **layout** does not change: one Item per object stays, because that is what makes the
catalog readable by anything that speaks static STAC. Writing one fat object instead would be
faster and would stop being a STAC catalog.

### D5 — Stop GDAL probing for sidecars on every remote open

Every VSI open of a COG currently costs more than one HTTP request, because GDAL lists the
containing directory looking for sidecars (`.aux.xml`, `.ovr`, `.msk`). Two config options in the
env `rio_env`/`rio_open` already build:

- `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` — *"only the target file is visible; side-car/auxiliary
  files aren't loaded"* (GDAL docs, §8).
- `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif` — *"can speed up dramatically open experience"* (ibid).

**Named risk:** `EMPTY_DIR` means a sidecar that *does* exist stops being read. fsd writes plain
COGs with statistics inline and no `.aux.xml`, so nothing in-repo depends on one — but this
applies to **every** remote raster open (download, datacube, merge), not just the collect path,
which is why it is its own decision and its own line in §5.

## 4. Acceptance criteria

1. **The numbers are printed, not inferred.** A run prints `[collect]`, `[stac]` and `[merge]`
   segment lines with elapsed and per-unit rate. AC met by a unit test on the ticker output, not
   by a cloud run.
2. **ROI mode reads zero `geometry.geojson` objects.** A test asserts the seam is not asked for a
   footprint path when the driver supplies geometries in memory, and that the resulting Items are
   **byte-identical** to the ones the path form produces for the same inputs.
3. **The path form is untouched.** Every existing `cog_outputs_to_items` /
   `cog_outputs_to_items_from_manifest` test passes unmodified, including the id-disagreement raise
   and the missing-entry raise.
4. **Each worker has its own GDAL env.** A test proves a worker thread entering `rio_env` sees the
   token, and that the driver thread's env is not relied on — the regression guard for §8's finding.
5. **Threading is bounded and deterministic in output.** Item order in the catalog does not depend
   on completion order; a failure in one worker surfaces as that failure, not as a truncated
   catalog.
6. **No test requires a network.** Everything runs against `tmp_path` / `memory://`.
7. `pytest -q` and `ruff check src/ tests/` clean.

## 5. Risks

- **`EMPTY_DIR` silently disables a sidecar someone later adds** (D5). It is a global-ish change
  wearing a local-looking diff. Mitigation: it is set only in the *remote* branch of
  `rio_env`/`rio_open`, and named in `CHANGES.md`.
- **Threads over VPN can be worse than sequential** if the link is the bottleneck rather than the
  latency. Latency is the bottleneck here (2 s/cell for a header read is round-trip, not
  bandwidth), so this should hold — but D1 exists precisely so the claim is checked rather than
  assumed.
- **A partially-written catalog** is a new failure shape if a write worker raises mid-flight.
  Today's sequential save has the same property; threading widens the window.
- **Chasing the wrong third.** Even fully fixed, the run still pays #77's dispatch cost and AML's
  ~201 s queue-and-allocate. This spec removes ~700 s of a ~2000 s wall; it is not the last word.

## 6. Alternatives considered

- **Run STAC and merge concurrently** (the user's suggestion, 2026-08-27). Independent in output,
  and rejected: both are bottlenecked on the same link, so the ceiling is `max(stac, merge)`
  instead of `stac+merge` — 777 → 616 s, versus D2–D5's ~777 → <100 s — and it buys nothing on the
  common `merge=False` run while adding a half-written catalog beside a failed merge as a new
  failure mode. Worth revisiting only if D2–D5 land and it is *still* slow.
- **One fat catalog object instead of 301** — see D4. Faster, and no longer a STAC catalog.
- **Node-side Item emission** (#61 (d)) — the actually-right long-term answer; out of scope (§2).
- **Cache the COG metadata in `input.csv` at write time** so the driver reads nothing. Better than
  D3 and a superset of it, but it changes what the node writes, i.e. it *is* #61 (d) wearing a
  smaller hat. Deferred with it.

## 7. Questions at sign-off — ALL RESOLVED AS PROPOSED (user, 2026-08-27)

**Q1 — how many threads?** A fixed default (proposal: **16**, tuned for latency-bound round-trips,
not core count) or derived from `cores`? `cores` means something else here (it is the node's
inference parallelism), so overloading it would be misleading.
> **RESOLVED — a module constant, `_COLLECT_THREADS = 16`, with a comment saying it is tuned for
> round-trip latency and not for core count.** No argument on any public signature until a real run
> asks for one: an unused knob is a knob that gets set wrong. D1's segment line is what a future
> retune reads, so the constant is safe to change on evidence.

**Q2 — does D5 belong in this spec?** It touches every remote raster open in fsd, not just the
collect path.
> **RESOLVED — keep it here.** Two lines, and the collect path is the only place its effect is
> currently measurable. It carries its **own `CHANGES.md` entry and its own test**, so a later
> bisect finds it without reading this spec, and §5's sidecar risk is stated where the behaviour
> changes (`rio_env`/`rio_open`) rather than only here.

**Q3 — one `geometries` parameter taking two shapes, or a second parameter?** D2 as written
overloads the values (path *or* geometry).
> **RESOLVED — overload the values of the single `geometries` parameter.** The contract is one
> thing — *every output has a footprint* — and a second parameter would let a caller pass both and
> force an invented precedence rule. The docstring must state both accepted value shapes and which
> one keeps the `properties.id` cross-check (the path form; the in-memory form is checked
> structurally, D2).

## 8. Best-practice alignment / sources

**rasterio 1.4.4 source, as installed** (`rasterio/env.py`, read 2026-08-27) — the primary source,
and it **corrects the fix guidance in #61**. `local = ThreadEnv()` at `env.py:56`, with `defenv`,
`hasenv` and `getenv` all reading `local._env`, is what makes a `rasterio.Env` per-thread. #61
inferred from "the env stack is thread-local" that the fix was *one* env around a threaded loop;
the same fact means each worker needs its own. Confirmed by direct execution (D3), not by reading
alone — the docstring-is-not-evidence rule from [[verify-the-primitive-a-spec-cites]].

**rasterio concurrency documentation**
([rasterio.readthedocs.io/en/stable/topics/concurrency.html](https://rasterio.readthedocs.io/en/stable/topics/concurrency.html),
fetched 2026-08-27) — contributed the reason threading is the right tool at all: *"the global
interpreter lock (GIL) is released when calling GDAL's `GDALRasterIO()` function"*, so threads
genuinely overlap. Notably it does **not** document Env-vs-thread behaviour, which is why D3 rests
on the source read above rather than on this page.

**GDAL configuration options**
([gdal.org/en/stable/user/configoptions.html](https://gdal.org/en/stable/user/configoptions.html),
fetched 2026-08-27) — contributed D5's two options and their exact semantics:
`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` (*"only the target file is visible; side-car/auxiliary
files aren't loaded"*) and `CPL_VSIL_CURL_ALLOWED_EXTENSIONS` (*"can speed up dramatically open
experience, in case the server cannot return a file list"*). The `EMPTY_DIR` value — as opposed to
`TRUE` — is what makes the risk in §5 precise rather than vague.

**fsd's own measurement, #61 + run-book 41 Step 3** (2026-07-28) — contributed every number in §1.
It is cited as a source rather than as background because the segment split (616 / 161 / 193) is
what makes D2–D4 *ordered*: without it, D4's 161 s looks as big as D2's 300 s.

## 9. Implementation note — build order

0. **D1 first.** Segment timings, and a run to capture the before. Nothing else is verifiable
   without it.
1. **D2** — the free half. No threads, no new failure mode, ~300 s.
2. **D5** — two lines in `rio_env`/`rio_open`, measurable immediately against D1's numbers.
3. **D3** — threaded COG opens, per-worker env. The AC4 test lands with it, not after.
4. **D4** — threaded Item writes.
5. Full suite + ruff, `CHANGES.md`, then **a real run** to compare against step 0's numbers —
   MEMORY [[real-run-beats-review]]: this spec is a performance claim, and a performance claim
   that has not been measured on the cluster is a hypothesis.
