# CDSE discovery uses the anonymous STAC API; drop `sentinelhub`, `boto3`, and SAFE listing

**Status:** accepted (`DROPPED.md`; closes BUG-001)

**Context.** The legacy `cdseutils` used the `sentinelhub` SDK (SH OAuth creds + base/token URLs)
for catalog search, then a recursive S3 listing of each `.SAFE` product (`fs.glob` / boto3
`filter(Prefix=)`) to discover per-band file paths. That listing intermittently failed
authentication — the flaky, hard-to-reproduce **BUG-001**.

**Decision.** Query the **anonymous CDSE STAC API** via `pystac-client`. STAC item `assets` expose
the per-band S3 hrefs **directly**, so the recursive `.SAFE` listing is removed entirely. The
`sentinelhub` dependency (and its OAuth creds/URLs) and the direct `boto3` client are dropped;
transfers go through the generic `s3fs` transport (ADR 0003).

**Considered options.** Keep SH OAuth catalog search + SAFE listing. Rejected: an extra dependency
and credential set, and the listing is the source of the intermittent auth failures.

**Consequences.** No Sentinel-Hub credentials are needed; the dependency surface shrinks; the BUG-001
class of failures is eliminated at the root. Reconsider only if STAC stops exposing per-band assets
(fall back to listing) or a specific CDSE service requires SH OAuth. CDSE username/password creds are
also dropped (already unused).
