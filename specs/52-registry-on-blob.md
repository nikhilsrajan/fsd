# Spec 52 — the registry on blob: `fsd.deploy` publishes to the cloud

**Status:** DRAFT, awaiting sign-off · **Opened:** 2026-08-24 · **Amends:** spec 51 D2, spec 31
**Closes:** [#86](https://github.com/nikhilsrajan/fsd/issues/86),
[#88](https://github.com/nikhilsrajan/fsd/issues/88) · **Completes spec 51 AC12 for `abfss://`;
narrows it for every other URL scheme** (see D5)

---

## 1. The gap

Spec 51 shipped a model registry and `fsd.deploy`. D1 says the registry is "a prefix on the
storage seam", and AC12 says behaviour must be "identical for a local registry path and a URL
registry". Neither is true today. **`REGISTRY` in the e2e notebook is a folder on the user's
laptop, because a blob registry does not work.**

Two independent defects, found on 2026-08-23/24 while writing AC12's test — the one acceptance
criterion nobody had exercised:

**#88 — `registry.publish` never returns against a non-local backend.** Not slow: infinite.
`_write_new_version` stages the version files under `.staging-<uuid>/` and renames that directory
onto `v<N>`. `storage.fs.rename` only has a real atomic move locally (`os.rename`); for anything
else it delegates to the fsspec filesystem's `mv`. `_write_new_version` then treats **every**
`OSError` from that rename as "I lost a race, try `v<N+1>`" — which is sound for `os.rename`,
where that is the only reason it refuses. On a backend with no atomic directory move the failure
is *deterministic*, recurs identically at every version, and the loop increments forever. No
timeout, no error, no output.

**#86 — `deploy` never authenticates.** `fsd.storage.azure.configure_storage` is the one function
that switches adlfs from anonymous to credentialed. Exactly three verbs call it: `download`,
`create_training_data`, `flatten_training_data`. `deploy` — and `run_inference`, `verify_adapter`,
`verify_image` — never do. A blob registry would therefore be read and written **anonymously**.
This is wider than its issue title: today the notebook works only because an earlier verb in the
same kernel set a *process-global* flag as a side effect. A fresh kernel resuming straight to
inference is already unauthenticated.

### The premise spec 51 D2 rested on is false

D2 says publication is "atomic via `storage.fs.rename` from a staging prefix", and
`fs.rename`'s docstring justifies it:

> *"on an HNS Azure account this is one metadata operation"*

**That is not what happens.** Verified 2026-08-24 against the installed `adlfs 2026.8.0`:

```
AzureBlobFileSystem._rename -> absent
AzureBlobFileSystem._mv     -> absent
AzureBlobFileSystem.mv      -> inherited fsspec.spec.AbstractFileSystem.mv
```

and that inherited `mv` is `self.copy(...)` followed by `self.rm(path1, recursive=recursive)`,
with `recursive=False` by default. On a directory the copy does nothing and the `rm` raises. So
`abfss://` fails **exactly** like `memory://` — certainly, not "likely" as #88 speculated.

The statement is nevertheless *half* true, and that half is this spec's opening: **Azure really
does have an atomic directory rename.** ADLS Gen2 with a hierarchical namespace exposes it as
`Path::Create` with an `x-ms-rename-source` header — a single metadata operation, independent of
how many files the directory holds. `adlfs` simply never calls it. `azure-storage-file-datalake`
does, as `DataLakeDirectoryClient.rename_directory`.

**So the fix is not to abandon D2's design. It is to make `fs.rename` do what it already claims.**

This is the second time a claim about `fs.rename` has turned out to be untrue (the first cost
spec 51 D2 a review cycle). See MEMORY `verify-the-primitive-a-spec-cites`.

---

## 2. Scope

**In:** `storage.fs.rename` gains a real atomic directory move for `abfss://`; `_write_new_version`
stops looping forever; `configure_storage` is called by every verb that touches the storage seam;
`deploy` accepts `storage="azure"`; spec 51 AC12 becomes testable and is tested.

**Out:** S3 (no atomic directory move, and no S3 target exists yet — D3 makes it a loud refusal,
not a hang); a lock service (spec 51 §5 stands); changing the registry's on-disk layout (D2);
migrating existing local registries (D6); `run_inference` fetching models from the registry
instead of staging per run (§7 Q3).

---

## 3. Decisions

### D1 — `fs.rename` gets a real atomic directory move for `abfss://` [chosen by user, 2026-08-24]

`storage.fs.rename` resolves in three branches, in this order:

| source + destination | mechanism | atomic? | arbitrates a race? |
|---|---|---|---|
| both local | `os.rename` (today, unchanged) | yes | yes — `EEXIST`/`ENOTEMPTY` |
| both `abfss://`, source is a **directory** | `DataLakeDirectoryClient.rename_directory`, **conditional** | yes | yes — `409 PathAlreadyExists` |
| both `abfss://`, source is a **file** | `DataLakeFileClient.rename_file`, **conditional** | yes | yes — `409 PathAlreadyExists` |
| anything else | **raise**, naming the backend | — | — |

**Both file and directory renames are required, and the file case is the majority.** Three of the
registry's four `fs.rename` calls move a single FILE, not a directory:

| call site | what is renamed | shape |
|---|---|---|
| `set_alias` (`registry.py:199`) | `.staging-<uuid>.json` → `_aliases.json` | **file** |
| `write_deploy_record` (`registry.py:305`) | `.staging-<uuid>.json` → `_deploy.json` | **file** |
| `_write_new_version` (`registry.py:394`) | `.staging-<uuid>/` → `v<N>/` | directory |

A `fs.rename` that only handled directories would publish a version and then fail to write its
alias or its deploy record — i.e. it would break promotion and the bundle↔image binding, which is
most of what makes a registry worth having. `fs.rename` therefore dispatches on the source's
shape. It must decide that **without** a `fs.isdir`-per-rename tax on the local path, which is the
hot one: check the shape only on the `abfss://` branch, where a round-trip is already being paid.

The third branch is the behavioural change that matters most: today it hangs, and after this it
fails in one line saying why. A backend without an atomic directory move cannot host a registry,
and saying so is not a regression — it is the first time that fact is expressed at all.

**The conditional is not optional, and getting it wrong is worse than the bug this spec fixes.**
`Path::Create` **overwrites the destination by default**:

> *"By default, the destination is overwritten and if the destination already exists and has a
> lease the lease is broken. […] To fail if the destination already exists, use a conditional
> request with `If-None-Match: "*"`."*

An unconditional `rename_directory` would therefore let a losing racer **silently destroy the
winner's published version** — silent data loss, strictly worse than #88's hang, and it would
break spec 51 D2's immutability guarantee outright. So the abfss branch MUST pass
`etag="*", match_condition=MatchConditions.IfMissing` (confirmed keywords on
`DataLakeDirectoryClient.rename_directory(new_name, **kwargs)`, `azure.core.MatchConditions`
confirmed to expose `IfMissing`). The resulting `409 PathAlreadyExists` is what `_write_new_version`
reads as "I lost the race" (D3) — the same signal `os.rename`'s `ENOTEMPTY` carries locally.

**Directory renames may need continuation.** The REST contract limits how many paths one
invocation renames and returns `x-ms-continuation` when more remain, to be passed back on a
subsequent call. A bundle is a handful of files, so this will not trigger in practice — but "will
not trigger in practice" is how #88 got shipped. The implementation must either confirm the SDK
loops on continuation internally or loop itself, and a test must assert the behaviour for a
directory large enough to matter. **Until that is confirmed, "atomic" in the table above means
atomic per invocation, not proven atomic for arbitrarily large directories.**

**Why native-rename and not a marker file.** The alternative — write the version's files directly
under `v<N>` and a `_complete` marker last, treating unmarked versions as invisible — was
prototyped and works on `memory://`. It was rejected because it is strictly weaker where it
counts: it gives up race arbitration *everywhere including local*, where `os.rename` provides it
for free today; it changes the on-disk layout, so every existing registry needs re-publishing; and
it buys generality (S3) that no current or planned deployment needs. It stays documented in §6 as
the path to a second cloud, so nothing is discovered twice.

**Where the code lives.** Inside `fsd/storage/`, which is the storage seam's designated home for
backend specifics (`fsd/storage/azure.py` already imports Azure SDKs). No module outside
`fsd.storage` learns that Azure exists. The seam's contract — "Azure Blob / S3 become config, not
code" — is about *callers*, and callers are unaffected: `registry.publish` keeps calling
`fs.rename` and never knows which branch ran.

**`azure-storage-file-datalake` becomes a declared dependency** of the `[azure]` extra. It is
already installed transitively via `adlfs` (12.25.0 confirmed), but depending on it directly means
declaring it.

### D2 — the registry's on-disk layout does not change

`<registry>/<name>/v<N>/` with `bundle.json`, `code/`, artifacts and `_deploy.json`; a sibling
`_aliases.json`; `.staging-*` prefixes invisible to `_list_versions`. No marker file, no new
metadata, no version bump. A registry published before this spec resolves identically after it,
and a local registry copied to blob resolves identically to one published there — which is spec 51
D11's relocatability, now actually exercisable.

### D3 — a backend that cannot publish says so in one line, immediately

`_write_new_version`'s retry loop is bounded and learns to tell a race from a hard failure.

- A `FileExistsError`/`ENOTEMPTY`/`EEXIST` from the rename means **a competitor finished first** —
  today's behaviour: discard the stage, check whether the winner holds our digest (D2 idempotency),
  else `version += 1` and retry.
- **Any other error is not a race.** Discard the stage and re-raise, wrapped with the registry root
  and the backend, so the caller learns that this backend cannot host a registry rather than
  watching a cell spin.
- The loop is additionally bounded at **`_MAX_PUBLISH_ATTEMPTS = 16`** and raises on exhaustion.
  Sixteen genuine lost races in one publish is not a scenario worth serving; an unbounded loop is
  the failure mode this spec exists to remove, and a bound is cheap insurance against a
  *different* deterministic error being misclassified as a race in future.

This decision is independent of D1 and would be worth making even if D1 were rejected.

### D4 — `configure_storage` is called by every verb that touches the seam

`deploy`, `run_inference`, `verify_adapter` and `verify_image` each call
`configure_storage(storage)` at the same point in preflight the other three verbs already do —
before the first storage access, after argument validation.

`configure_storage` sets **process-global** fsspec state (`FSSPEC_ABFSS_ANON=false` plus
`fsspec.config.conf`), so no `storage_options` threading is required and none is added: the
registry functions' existing `storage_options=` parameters stay as they are, unused by these
callers. Making the call explicit at each verb replaces today's accident — where authentication
works only because some *earlier* verb in the same process happened to set the flag.

**`deploy` stops refusing non-local storage.** Today `_check_local_seams(runner, storage,
storage_allowed=False)` rejects `storage="azure"`. That gate was correct when a blob registry could
not work; it is what this spec removes.

### D5 — `registry=` may be a URL, and that is the tested path

Spec 51 AC12 stops being aspirational. `deploy` → `resolve` → `run_inference` is exercised against
a non-local registry root in the test suite, and the AC12 test currently skipped with a pointer to
#88 is unskipped.

**Unit tests use `memory://`, which D1 makes raise, not hang** — so the suite asserts the *refusal*
for a backend with no atomic move, which is the real contract for everything that is not local or
`abfss://`. The `abfss://` path itself cannot be unit-tested offline: it is verified by a
**run-book** the user executes against a real account (§5), because a mocked `rename_directory`
would only prove fsd calls a mock.

### D6 — no migration, because there is nothing to migrate

Registries are days old and the layout is unchanged (D2). The one registry that exists is
`notebooks/demo_registry`, local, and it keeps working. Moving it to blob is a file copy plus
re-pointing `REGISTRY` — spec 51 D11 guarantees every ref still resolves, and `registry.migrate`
already re-digests every version to prove the copy landed intact.

---

## 4. Acceptance criteria

1. `fs.rename` moves a directory atomically between two `abfss://` paths via
   `DataLakeDirectoryClient.rename_directory`, and onto an **existing** destination it raises
   rather than overwriting — asserted by publishing to a destination that already exists and
   checking the prior content is **still there afterwards**, not merely that an error was raised.
   (Azure overwrites by default; this AC is the guard on D1's conditional.)
   - **1b.** A directory rename that exceeds one invocation's path limit still completes — either
     the SDK continues internally (confirm, do not assume) or `fs.rename` follows
     `x-ms-continuation` itself.
2. `fs.rename` between two paths on any other non-local backend raises immediately, naming the
   backend and the reason. **It does not hang** — asserted with a timeout in the test.
3. `registry.publish` against `memory://` raises within seconds instead of looping (the #88
   regression test).
4. `_write_new_version` retries only on a race-shaped error, re-raises everything else, and is
   bounded at 16 attempts.
5. `deploy(..., storage="azure")` is accepted, and `deploy` calls `configure_storage` before its
   first storage access.
6. `run_inference`, `verify_adapter` and `verify_image` each call `configure_storage`, asserted by
   a test that runs the verb in a process where no other verb has run.
7. Spec 51 AC12 holds **for `abfss://`**: `deploy` → `resolve` → `run_inference` behave
   identically for a local registry path and an `abfss://` one. For every other URL scheme the
   criterion is deliberately **narrowed**, not met: those raise (AC2). Say so in spec 51's AC12
   rather than marking it green — "identical for a URL registry" was written before anyone knew
   only one URL scheme could support it.
   - **7b.** `set_alias` and `write_deploy_record` work against an `abfss://` registry — the file
     renames, not just the version publish. A test that only publishes would miss both.
8. `azure-storage-file-datalake` is declared in the `[azure]` extra.
9. A local registry copied to a blob root resolves identically at both (spec 51 D11/AC13b,
   re-asserted here because it is now reachable).
10. `pytest -q` and `ruff check src/ tests/ demos/ examples/` clean; no network in unit tests.

---

## 5. Risks

**The `abfss://` path cannot be proven by this repo's test suite.** Everything offline is either
`memory://` (which D1 makes raise) or a mock (which proves nothing about Azure). The real proof is
a run-book: publish two versions to a blob registry, resolve an alias, run inference off the ref,
and confirm a second publish of identical content is a no-op. **This spec is not "done" on green
tests** — see MEMORY `real-run-beats-review`, where green tests plus two review rounds still missed
what the first real AML run found.

**HNS is assumed.** `rename_directory` is atomic on a hierarchical-namespace account. On a flat
blob account it is not available in the same form. The `rise` storage account is HNS (fsd already
depends on that for `/vsiadls/` reads), but the failure must be a clear error, not a silent
fallback to copy-and-delete. The run-book confirms which kind of account is in play.

**Abandoned staging trees will accumulate on blob.** `_discard` cleans up a failed publish with
`fs.rm(path, recursive=True)`, which is documented as unreliable on `abfss://` (#50). It is
best-effort by design — wrapped in `contextlib.suppress(Exception)` precisely so a cleanup failure
never masks the error that caused it — and a leftover is invisible to `_list_versions` (which
matches `v<N>` only), so this is **not** a correctness problem. It is a tidiness one: a blob
registry will slowly collect `.staging-*` prefixes that nothing removes. Out of scope here; noted
so it is not rediscovered as a bug.

**Credentials at rename time.** `DataLakeDirectoryClient` needs its own credential; it does not
inherit adlfs's. It must resolve `DefaultAzureCredential` the same way `fsd/storage/azure.py`
already does, and honour the same `AZURE_CLIENT_ID` a node is given — otherwise this works on a
laptop and fails on a cluster node, which is the worst place to discover it.

---

## 6. Alternatives considered

**Marker file, no rename anywhere** (prototyped 2026-08-24, works on `memory://`). Write the
version's files under `v<N>`, then `_complete.json` last; `_list_versions` ignores unmarked
versions. Generic across every backend including S3, and it needs no atomic directory move at all —
a single-object PUT is atomic on Azure Blob by documented guarantee. **Rejected for now** because it
gives up race arbitration everywhere, *including local where it currently works*, and changes the
on-disk layout for generality nothing needs yet. Recorded here in full so that adding S3 later is a
decision, not a rediscovery.

**A lock service.** Spec 51 §5 already rejected it and nothing here reopens that. The user's
position (2026-08-24): concurrent publication of the same model does not occur in this team.

**Leaving it local and documenting the limitation.** This was the decision for about an hour on
2026-08-24 before the user reversed it. Recorded because the reasoning still holds for S3: a
registry nobody can reach is not obviously worse than no registry, and the model reaches the
cluster either way via per-run staging.

---

## 7. Questions at sign-off

1. **`_MAX_PUBLISH_ATTEMPTS = 16` — right number?** It only bounds genuine lost races. Proposed
   default stands unless the user prefers a different bound.
2. **Should `fs.rename`'s non-local refusal name the marker-file design as the fix?** The error
   could point at §6 so a future S3 user knows the shape of the answer rather than just that they
   are blocked. Proposed: yes, one sentence.
3. **Should `run_inference` fetch the model from the registry instead of staging it per run?**
   Deliberately **out of scope** here — a blob registry makes it *possible* (the bundle would
   already be on blob, so `_stage_bundle` becomes a blob-to-blob copy that could be skipped), but
   it changes how nodes get models and deserves its own decision. Flagged so the possibility is
   not mistaken for part of this spec.
4. **Does `deploy` need `storage=` at all now, or should it infer from the registry URL's scheme?**
   Proposed: keep the explicit kwarg, matching every other verb; inference would be the "silent
   fallback" pattern spec 51 D4 refused elsewhere.

---

## 8. Best-practice alignment / sources

Cross-validation run at draft (2026-08-24) under `CLAUDE.md`'s standing permission for spec
searches. It **overturned this spec's starting assumption**: the draft opened intending to replace
the rename with a marker file, on the belief that no atomic directory move existed on object
storage. The ADLS Gen2 documentation established that one does, which is what D1 rests on.
Searches run: Azure Blob `Put Blob` atomicity and concurrency semantics; ADLS Gen2 hierarchical
namespace atomic directory rename via `Path::Create` / `x-ms-rename-source`.

### External

- **[Azure Data Lake Storage hierarchical namespace](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-namespace)**:
  supplied **D1's central fact** — a hierarchical namespace "enables atomic directory
  manipulation", processing a directory move "by updating a single entry (the parent directory)"
  rather than touching each blob. This is what makes stage-then-rename salvageable on Azure and is
  the reason D1 chose it over §6's marker file.
- **[Path - Create (ADLS Gen2 REST API)](https://learn.microsoft.com/en-us/rest/api/storageservices/datalakestoragegen2/path/create)**:
  supplied **the mechanism D1 names** — rename is `Path::Create` carrying an `x-ms-rename-source`
  header, i.e. a metadata operation, not a copy — and then **corrected D1's first draft**, which
  had claimed the rename refuses an existing destination. It does not: *"By default, the
  destination is overwritten […] To fail if the destination already exists, use a conditional
  request with `If-None-Match: \"*\"`."* That single sentence is why D1 mandates the conditional;
  without it this spec would have shipped silent data loss in place of a hang. The same page
  supplied the `409 PathAlreadyExists` code D3 keys on, and the `x-ms-continuation` limit D1's
  last paragraph flags.
- **[Azure DataLake client library for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/storage-file-datalake-readme?view=azure-python)**:
  supplied **D1's implementation target** — directory-level `Create`/`Rename`/`Delete` are exposed
  for HNS-enabled accounts, and rename/move are atomic there. Confirms fsd can reach the operation
  from Python without hand-rolling REST, and grounds §5's HNS-only risk.
- **[Put Blob (REST API)](https://learn.microsoft.com/en-us/rest/api/storageservices/put-blob)**:
  supplied **§6's foundation** — "partial updates are not supported with Put Blob", so a
  single-object write is all-or-nothing. This is what would make a `_complete` marker sound, and is
  recorded so the rejected alternative stays credible rather than vague.
- **[Manage concurrency in Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/concurrency-manage)**:
  supplied **§6's and D3's honesty about races** — the default is last-writer-wins, and snapshot
  isolation means readers see a consistent version rather than a partial one. It also names leases
  and optimistic concurrency as the real answers if arbitration is ever needed, which is why §6 can
  say the marker file "gives up race arbitration" without hand-waving about what would restore it.

### Internal — primary evidence, read rather than cited

- **`adlfs 2026.8.0`, inspected directly**: `AzureBlobFileSystem` defines neither `_rename` nor
  `_mv`; `.mv` resolves to `fsspec.spec.AbstractFileSystem.mv`, whose body is `copy()` then
  `rm(path1, recursive=recursive)`. This is the whole of #88 and it disproves `fs.rename`'s
  docstring. Read from the installed package, not from documentation — per MEMORY
  `verify-the-primitive-a-spec-cites`.
- **`fsd/model/registry.py::_write_new_version`**: the `except OSError` → `version += 1` loop, and
  its own docstring conceding "a backend whose `mv` merges a prefix into an existing one leaves both
  writers' files interleaved". D3 acts on that concession.
- **`fsd/storage/azure.py::configure_storage`**: sets process-global fsspec state, which is what
  lets D4 be four one-line calls instead of a `storage_options` refactor.
- **`memory://` marker-file prototype** (2026-08-24): publish-without-rename works and an
  unmarked version is correctly invisible. Evidence for §6 being a real option, not a straw man.
