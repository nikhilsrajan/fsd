# General-purpose pipeline images emit raw arrays; the adapter feature transform runs only at model-specific endpoints

**Status:** accepted (spec 39, grilled + agreed 2026-07-24; complements ADR 0018 / ADR 0002)

**Context.** Spec 39 moves `flatten` onto the cluster (a single-node reduce) so the driver stays
control-plane-only (ADR 0004) instead of relaying ~900 cubes over VPN. But the model's feature
transform is part of the `ModelAdapter` (ADR 0018), and the anti-skew invariant (spec 18 F1) requires
the *same* transform at training-data generation and inference. The naive reading — "have the flatten
step emit `features.npy`" — would force the adapter (a model-specific dependency) into the general-
purpose datacube/flatten AML image, which must stay model-agnostic (only the **inference** image is
model-specific — ADR 0002).

**Decision.** **General-purpose pipeline images (download, datacube, flatten) emit only raw artifacts;
they never import an adapter.** The adapter feature transform runs at exactly the two model-specific
endpoints: (1) **on the driver**, after the raw training array lands locally, where
`create_training_data` runs `_apply_training_features` to emit `features.npy` (the driver already has
the adapter installed — it is the operator's machine, not a cluster image); and (2) **in the inference
image**, on inference cubes. F1 is preserved because both endpoints call the *same* adapter — not
because features are materialized on a general-purpose node.

**Considered options.** **Emit `features.npy` from the cluster flatten job** — rejected: bakes a
model-specific dependency into a general-purpose image, breaking the ADR-0002 image boundary and
forcing a per-adapter rebuild of the datacube/flatten image. **Drop the feature transform from fsd
entirely and make the user's training script apply it** — rejected: weakens ADR 0018's anti-skew
invariant from an fsd guarantee to a "the user must call the right helper" convention, for a symmetry-
with-inference that is not required (the driver is not a general-purpose image, so it *can* run the
transform).

**Consequences.** For `runner="aml"`, the training-data path is: build fan-out → flatten reduce (raw)
→ land raw locally → driver applies the adapter → `features.npy`. The flatten reduce reuses the
existing general-purpose fsd Environment (no new image, no adapter). `create_training_data` keeps its
`adapter=`/`feature_sequence=`/`aggregate=` params and its `features.npy` output unchanged — the only
change is *where* the transform runs (always the driver, never a cluster node). Spec 18, the Adapter
glossary, and `examples/eurocrops_rf.py`'s train recipe need no revision.
