# A collection string resolves on the driver; the declaration travels as JSON

**Status:** accepted (grilling session, 2026-09-04 — confirmed by the user; spec to follow)

**Context.** Masking is no longer a verb parameter — a `CollectionDeclaration` is the only source of
truth ([ADR 0030](0030-source-and-collection-are-orthogonal-axes.md)). A user who wants different
mask classes therefore registers a **named collection variant** rather than passing a list. That
needs a public registry — and a registry is an in-process dict, which **does not exist inside an AML
job container**. A `collection=` string arriving at a node as a CLI argument would raise `KeyError`
~30 minutes into a dispatch: the same late, remote-only failure shape as #80.

**Decision.** `fsd.collections.register(id, declaration)` is a plain in-process dict — no entry
points, no packaging, no image rebuild. The **driver resolves the string to a
`CollectionDeclaration` before dispatch**, and the **resolved declaration travels as JSON** in a
control file under the run folder, which every shard reads. The variant's *name* travels alongside
it for the path digest and cube metadata. **Nodes never consult a registry.** This is done uniformly,
including for built-in collections that *would* resolve on a node — one code path, rather than two
where only the user-variant path breaks and only remotely.

**Considered options.** **In-process dict consulted node-side** — breaks on AML, and only there.
**A `module:attr` reference resolved node-side** (the `ModelAdapter` pattern) — works, but forces a
user's variant to be a packaged, installed module and an image rebuild, for what is data rather than
code. **Reading it from the catalog stamp** — insufficient by construction: a build *variant* is
deliberately not what the catalog was stamped with.

**Consequences.** A user's collection variant needs **no image rebuild** — strictly better than the
adapter story. The pattern matches [ADR 0021](0021-dispatch-telemetry-is-a-file-not-a-return-value.md)
(driver resolves, a durable file carries, the node reads). **A declaration may not contain
callables** — a custom mosaic function, or the mask `producer` reserved in #98, must stay a
`"module:attr"` string resolved node-side against an installed package, exactly as `ModelAdapter`
does. Written down now so #98 does not discover it later.
