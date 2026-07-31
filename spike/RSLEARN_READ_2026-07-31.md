---
status: current
summary: Re-read of rslearn v0.1.13 (2026-07-31) against fsd as it exists today -- what the 2026-07-06 comparison got wrong, and what the spike still has to measure.
---

# rslearn re-read — v0.1.13, 2026-07-31

> **Point-in-time.** Read of `rslearn/` at `a5c50c63` (2026-07-28), **v0.1.13** — the previous
> analysis (`../RSLEARN_COMPARISON.md`, 2026-07-06) was written against **v0.1.12** and against
> fsd *before* P1–P4 shipped. Every claim below cites the file and line it came from, so it can
> be re-checked when rslearn moves. **Nothing here was run** — this is a source read (CLAUDE.md
> keeps networked/long work in run-books). What must be *measured* is listed in §6.

## 0. Why re-read at all

Two things changed under the 2026-07-06 analysis:

- **fsd changed.** Its "crown jewel differentiator" — cloud scale-out — is no longer a plan,
  it shipped and was cluster-validated 2026-07-29. §3 of the comparison ("rslearn does not
  solve our scale-out") is still true, but it is now an argument about *finished* work rather
  than future work, which changes what Plan C would cost.
- **The evidence base changed.** `satellite_benchmark/` — the archive the spike charter names
  as its comparison corpus — **was deleted.** The spike needs a new ground truth; §5 proposes one.

## 1. Scale and shape

| | rslearn v0.1.13 | fsd (`main` @ `83485ec`) |
|---|---|---|
| Python LOC | **54,850** | 10,787 `src/` |
| Data sources | **34 modules** in `data_sources/` | 2 (CDSE, MPC) |
| License / backing | Apache-2.0, AllenAI OlmoEarth team | MIT, this project |
| Core paradigm | windows → layers → Lightning DataModule | datacube tensor → flatten → sklearn |

## 2. Q3 (install weight) — **answered statically. It is heavy, and there is no lite path.**

`rslearn/pyproject.toml:11-31` — these are **core** `dependencies`, not extras:

```
torch>=2.7.0 · torchvision>=0.22.0 · torchmetrics[detection]>=1.7 · lightning>=2.5.1.post0
boto3>=1.39 · fiona>=1.10 · flask>=3.0.0 · rasterio>=1.4 · pyproj · shapely · soilgrids · Pillow
```

**`pip install rslearn` installs the entire deep-learning stack**, plus a web framework
(`flask`) and an AWS SDK, whether or not you touch training. There is no `rslearn[core]` or
`[data]` extra that omits torch — the optional groups are `extra`, `dev`, `terratorch`, `docs`
(`pyproject.toml:33-97`), and `extra` only *adds* more (xarray, zarr, transformers, wandb, …).

**This retires the comparison's framing of Q2** ("can we get a datacube out *without dragging in
Lightning*?"). At install time: no, categorically. The question that survives is narrower and is
now a runtime one — see §4.

Consequence for the comparison's §5 "lean footprint" claim: it holds, and it got *stronger*.
fsd's Mode-A promise (`pip install fsd`, numpy/rasterio/fsspec, a laptop, an RF) cannot be met
by anything that installs torch. If Plan C is adopted for acquisition, **the lean-install
property is spent** unless rslearn becomes an optional extra behind fsd's own source seam.

> Still to measure (Q3 is not fully closed): actual venv size on disk, wheel-download bytes,
> cold install wall time. Probe 01.

## 3. Q1 (Azure) — **rslearn has no Azure support at all. This is the real unknown.**

Grep over all 54,850 LOC:

| pattern | hits in `rslearn/**/*.py` |
|---|---|
| `azure` / `adlfs` / `abfs://` / `blob.core` | **0** |
| `gs://` | 13 |
| `s3://` | 11 |

The only `azure` string in the repo is `docs/data_sources/planetary_computer_PlanetaryComputer.md:8`,
describing MPC's *own* hosting ("reads of the underlying COGs on Azure Blob Storage") — i.e.
reading **from** public/signed blobs, not writing **to** ours. `pyproject.toml:43` declares
`fsspec[gcs, s3]` — **no azure backend**.

rslearn is built on `universal_pathlib` (UPath) + fsspec (`utils/fsspec.py`), so `abfss://`
*should* work if `adlfs` is installed, because that is what fsspec is for. But it is
**undeclared, untested and unsupported upstream**, and fsd's own experience is that the hard
part was never fsspec — it was **GDAL/VSI auth under managed identity**, which fsd solved
separately (spec 31, `/vsiadls/` + fresh token). rslearn reads pixels through rasterio too
(`utils/raster_format.py`), so it inherits exactly that problem and has no known solution for it.

**This is the single highest-risk, least-knowable-from-source question in the spike.** It is the
one that genuinely needs the VM.

## 4. Q2 (the datacube + the T contract) — **structurally closer than we thought, but not equivalent**

### 4.1 The comparison doc was wrong on one point, and it matters

`RSLEARN_COMPARISON.md` §2 says fsd's **"identical-calendar-T contract is unique."** It is not.
`QueryConfig.period_duration` (`config/dataset.py:445-457`) does the same *kind* of thing:

> *"If set, split the window's time range into sub-periods of this duration… Each sub-period
> produces a single separate item group, up to `max_matches` total groups/periods."*

So `SpaceMode.MOSAIC` + `period_duration=timedelta(days=mosaic_days)` + `max_matches=T` is the
direct analogue of fsd's calendar mosaic. That correction is the most useful thing in this read:
the two systems are **much closer** on the axis we thought was our moat.

### 4.2 …but the implementation diverges in three independent ways

From `data_sources/utils.py:434-485`, the period loop:

| # | rslearn behavior | source | fsd behavior | consequence |
|---|---|---|---|---|
| 1 | **Empty sub-periods are dropped** — `if period_groups: groups.append(...)` | `utils.py:464` | every window emitted, empty ones nodata-filled | **`T` becomes data-dependent.** Not knowable before querying, and differs between grid cells |
| 2 | Periods walk **backwards from the end** (`period_end = time_range[1]`, then `period_end = period_start`) | `utils.py:446-455` | start-anchored from `startdate` | window **phase differs** when the span isn't an exact multiple |
| 3 | Loop guard `period_end - period_duration >= time_range[0]` ⇒ a trailing partial period is **dropped** | `utils.py:447-448` | `T = ceil(span / mosaic_days)` — partial window **kept** | rslearn gives **floor**, fsd gives **ceil** |

Plus a live deprecation trap: `per_period_mosaic_reverse_time_order` **defaults to `True`**
(`config/dataset.py:466-473`), so groups come back **most-recent-first** and emit a
`FutureWarning`; the default flips to chronological after 2026-04-01.

**Why (1) is the load-bearing one for fsd.** Two fsd properties depend on `T` being a pure
function of `(startdate, enddate, mosaic_days)` — `api.compute_n_timestamps`, `api.py:69-80`:

- **Preflight** (`ROADMAP.md` §2.6/§3.3) asserts `T == adapter.n_timestamps` *before any
  download*. Against rslearn, `T` isn't known until after the query, so the cost guardrail
  that "catches the most common deploy failure" cannot fire early.
- **Cross-cell flatten** requires every cube over the same window to share one `timestamps`
  axis. If cell A has 9 non-empty periods and cell B has 10, they cannot be stacked.

Neither is fatal — a re-alignment shim (map returned groups onto their period index, fill the
gaps) would restore both. But it is **new fsd code that Plan C was supposed to delete**, and it
has to be written before any equivalence comparison is even meaningful.

### 4.3 What rslearn's datacube actually is

`dataset/materialize.py:132-238` — `RasterMaterializer` writes, per window, per layer, **per
item group**, via `window.data.open_layer_writer(...).write_raster(...)`. Compositing happens
per group (`compositing.py`): `FirstValidCompositor`, `MeanCompositor`, `MedianCompositor`,
`SpatialMosaicTemporalStackCompositor`, and temporal reducers (mean/max/min).

`SpatialMosaicTemporalStackCompositor` (`compositing.py:283`) is the closest thing to fsd's
datacube — spatial mosaic then temporal stack — and is the first thing the spike should try.

Readback to numpy exists and is public: `window_data_storage/storage.py:88,110`
(`read_raster` / `read_rasters`), also `per_layer.py:265,287`. So **"numpy time series out" is
mechanically supported** — the obstacle is the T semantics in §4.2, not the array plumbing.

**Torch on the import path:** `utils/array.py` is imported by `materialize.py:13`,
`compositing.py:18` and `config/dataset.py:29` — but its torch import is guarded by
`if TYPE_CHECKING:` (`utils/array.py:10-11`), and no other module outside `models/` or `train/`
imports torch. So the acquisition/materialize path **looks** torch-free at import time. That is a
static reading of 81 torch-importing files; it needs one empirical `sys.modules` check (probe 01).

## 5. Harmonization — fsd's is more robust than rslearn's

The comparison doc credits rslearn with "baseline-04.00 harmonization" as a reason to adopt it.
Re-reading `data_sources/copernicus.py:44-90`, that credit needs qualifying:

- **It is opt-in and defaults to OFF** — `harmonize: bool = False` (`copernicus.py:680`).
- **It hard-asserts the offset is exactly −1000** — `assert offset == -1000`
  (`copernicus.py:73`), with the comment *"For now assert the offset is always -1000."* Any
  other declared `BOA_ADD_OFFSET` **crashes**.
- It reads the value from the product metadata XML tags (`RADIO_ADD_OFFSET` for L1C,
  `BOA_ADD_OFFSET` for L2A) — the right source, same as fsd.

fsd's spec 34 + amendment A2 landed on the opposite posture deliberately: **derive per item,
accept `{0, −1000}`, refuse rather than assume.** That was vindicated on real data — the blob MPC
archive's pre-Collection-1 2018 products correctly declare `0`, and the run-book's original
hardcoded `== -1000` assertion would have failed (PROGRESS, 2026-07-31). **rslearn would
`AssertionError` on exactly that archive.**

Separately, `aws_sentinel2_element84.py:35-36` notes its COGs are "already harmonized, even
though it is not really documented" — an honest comment, and a reminder that harmonization
posture varies per source in rslearn too.

**Verdict on this line item:** rslearn's harmonization is *narrower* and *off by default*. This
is no longer a reason to adopt; if anything it is a small point for fsd. The comparison's §8
follow-up ("verify fsd's CDSE does it too") is closed — issues #10 and #30 are both closed.

## 6. What the spike must still measure (nothing below is knowable from source)

| Q | Question | Needs | Cost |
|---|---|---|---|
| **Q3a** | venv size, download bytes, cold-install wall time | VM, network | one `pip install` |
| **Q2a** | Does importing the materialize path pull `torch` into `sys.modules`? | install only | seconds, offline |
| **Q2b** | Does `period_duration` really drop empty periods / floor the span / end-anchor? | install only | seconds, **offline, synthetic items, zero satellite bytes** |
| **Q1a** | Can a rslearn tile store / UPath write to `abfss://` under managed identity? | VM, blob | small |
| **Q1b** | Does rasterio/GDAL inside rslearn read `abfss://` under MSI, or does it need fsd's `/vsiadls/` translation? | VM, blob | small |
| **Q1c** | Pixel equivalence vs fsd on the same cell/dates/bands | VM, network | one small acquisition |

**Q2a and Q2b are decisive and nearly free** — they need rslearn installed but consume **no
satellite data at all**, and Q2b is the one that determines whether Plan C needs a re-alignment
shim. Do them first; they can veto the expensive half.

## 7. Ground truth for the equivalence test — the tutorial fixture replaces `satellite_benchmark/`

The charter names `satellite_benchmark/` (Ethiopia, 159 GiB). **It no longer exists.** The
replacement is already committed and is better suited:

`tests/data/tutorial/` — 27 MB, 108 COGs, **36 granules × B04/B08/SCL**, grid cell **`4772924`**,
MGRS tile **T33UWP** (single tile — no multi-CRS confound), **2018-04-01 → 2018-09-28**, with
`catalog.parquet`, 43 labelled fields, the cell polygon, and a provenance `README.md`.

Why it is the right corpus: it is **small, committed, offline-reproducible, radiometrically
correct** (declared `offset = 0`, verified — unlike the old Austria e2e archive, which is
un-harmonized and ~1000 DN high), and fsd's own numbers over it are already published and
reviewed (`T = 10` at `mosaic_days=20`, 43 fields → 20/13/10 across three classes). So "does
rslearn reproduce fsd's cube?" has a checked answer to compare against on day one.

It also sharpens Q2b into a concrete prediction worth betting on:

> fsd over this window gives **`T = ceil(181 / 20) = 10`**. rslearn, given
> `period_duration=20d, max_matches=10` over the same range, is predicted by §4.2 to return
> **9 groups** (floor: `181 // 20 = 9` full periods, trailing 1 day dropped) — **fewer still if
> any 20-day period has no scene.** If the probe returns 10, this read is wrong somewhere and
> §4.2 must be re-derived.

## 8. Where this leaves Plan C

Unchanged from the comparison: **scale-out is ours regardless**, and that half is now *built*.
What moved:

- **Against C:** the install-weight cost is worse than assumed (torch is core, no lite path) and
  it directly contradicts fsd's Mode-A promise; harmonization is no longer a reason to adopt;
  the T-contract gap means adoption *adds* fsd code rather than deleting it; there is **zero**
  Azure support in a project whose entire deployment target is Azure.
- **For C:** 34 data sources against fsd's 2 is still an enormous gap, and it is the whole
  content of issues #11/#21/#31/#32/#33/#36; `period_duration` shows the temporal model is
  compatible in *kind*; the readback API is clean; Apache-2.0 and actively maintained.

The honest shape of the decision has narrowed: **not "should fsd be built on rslearn"** — the
Azure gap and the install weight make that expensive — **but "should fsd's `Source` seam gain an
optional rslearn-backed source, for breadth, behind an extra."** That is a much smaller,
cheaper, reversible question, and it is the one the run-book is designed to answer.

---
*Cross-refs: `README.md` (this branch's charter), `../RSLEARN_COMPARISON.md` (the 2026-07-06
analysis this revises), `../specs/44-rslearn-spike.md` (what we will run),
`../runbooks/44-rslearn-spike.md` (how).*
