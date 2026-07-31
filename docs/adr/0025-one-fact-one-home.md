# One fact, one home — each topic has exactly one owning document; everything else links

**Status:** accepted (spec 41 D9, grilled + agreed 2026-07-29)

**Context.** The classic failure of a documentation refactor is producing a fifth restatement of
something already written four times, each subtly different, none authoritative. fsd was already
there before adding a single file: **the architecture story was spread across four documents** —
`ROADMAP.md` §2.1 (Modes A/B/C) and §2.2 (control plane vs data plane), `AZURE_INFRA.md` §3–4 (the
two compute paths, how the seams land), `CONTEXT.md` (driver / node / dispatcher / shard as
glossary), and `CLAUDE.md` (conventions, the MGRS-tile-vs-grid-cell rule). Writing an
`ARCHITECTURE.md` naively would have made it five versions of Mode B.

The same duplication had already produced a measurable defect elsewhere: **~45 distinct `AZ_*`
environment variables** across the runbooks with no canonical list, including four near-duplicate
spellings of one idea (`AZ_ARCHIVE` / `AZ_ARCHIVE_ROOT` / `AZ_ARCHIVE_PATH` /
`AZ_ARCHIVE_CATALOG`). Every documentation defect that cost a real cluster run in the week before
this decision was of that class.

**Decision.** **Each topic has exactly one owning document. Every other document links to it and
does not restate it.** The ownership table lives in spec 41 D9 and is normative; the entries that
change existing files are: the code map, invariants, modes and driver-vs-node move to a new
**`ARCHITECTURE.md`**, and `ROADMAP.md` §2.1/2.2 **shrink to pointers**; variable names and their
verification commands are owned by **`docs/reference/environment.md` + `env.example.sh`**, and the
demo documents stop restating them; measured findings are owned by **`docs/findings/`**, which
`TODO.md` rows and `E2E_AUSTRIA_AML.md` §6 link to. Terminology stays in `CONTEXT.md` and lasting
decisions stay in `docs/adr/` — both already correct.

`ARCHITECTURE.md` follows matklad's *ARCHITECTURE.md* convention: a coarse **codemap** answering
*"where's the thing that does X?"* — *"a map of a country, not an atlas of maps of its states"* — and
an **invariants** section built on his observation that *"important invariants are expressed as an
absence of something"*. That describes fsd's central rules exactly, and they are invisible in the
code precisely because they are absences: no module opens paths outside `fsd.storage` (except
documented rasterio/GDAL VSI pixel reads), no `boto3`, the unit-of-work never knows about AML, fsd
never trains a model.

**Considered options.** **Let documents overlap and rely on care** — rejected: it is the state that
produced four Mode B descriptions and 45 undocumented variables. **Transclusion / includes** — no
toolchain, and GitHub renders none of it. **Generate the overlapping parts from a single source** —
rejected for prose; kept only where it is cheap (the register indexes are regenerated, the variable
table is test-checked against the code). **Deep-link between documents so restatement is
unnecessary** — partially rejected on matklad's own maintenance argument: name modules and types and
let the reader symbol-search, rather than linking file paths and line numbers that rot.

**Consequences.** The rule is partially enforceable, which is the most that can be said for a prose
convention: `tests/test_docs.py` asserts that every relative link resolves and that the variable
table matches the code, but nothing can assert that a document did not quietly restate a topic it
does not own — that stays a review question. Shrinking `ROADMAP.md` §2.1/2.2 is a real edit to a
document people already read, and readers who knew where Mode B was described will have to follow a
pointer. In exchange, the question *"where is this written down?"* acquires a single answer per
topic, and the scope of a future edit becomes knowable: changing how the driver works touches
`ARCHITECTURE.md`, not four files that each half-describe it.
