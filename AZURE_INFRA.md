# AZURE_INFRA — the `rise` deployment target for fsd scale-up

> **What this is.** A standing reference (not a spec) capturing how the RAAPID Azure
> infrastructure — repo `raapid-infra/`, built by a colleague in Terraform — is set up,
> and specifically what the **`rise`** project gives us to run `fsd` at scale on **Azure
> Batch**. Read this before/while writing the Azure Batch spec (the future spec 10).
> **`raapid-infra/` is READ-ONLY for us** (a hard constraint, same status as
> `fetch_satdata/` / `rsutils/` / `cdseutils/`) — at least for now. We read it to
> understand what `rise` provisions and we *consume* those resources; we never edit it. Any
> infra change (max_nodes, max_tasks_per_node, warm-cache image, adding `vms`, etc.) is a
> `main/terraform.tfvars` edit + gated `deploy.sh` run by a **platform admin** (a colleague;
> possibly the user later). We only *propose* infra changes. When we start specing, this is
> the file to re-read for the ground truth about names, identities, network, and gotchas.
>
> Source of truth in `raapid-infra/`: `main/terraform.tfvars` (the `rise` entry),
> `modules/project-capabilities/azure-batch/`, `modules/project-core/`,
> `docs/high-level-architecture.md`, `docs/common-ops.md`, `docs/user-guide.md`.

---

## 1. The big picture (how RAAPID/Azure is organized)

RAAPID is a shared Azure platform managed as **Terraform IaC** (`azurerm ~> 4.17`) in
`raapid-infra/`. One Azure subscription, one shared VNet (`<vnet-cidr>`), many
**projects**. Projects are *pure data*: each is an entry in the `projects` map in
`main/terraform.tfvars`. Adding capabilities to a project = editing that map + a gated
`terraform apply` (`main/deploy.sh`) run by a **platform admin**. We (fsd) are consumers,
not admins — we don't run Terraform; we ask for config changes and then use the resources.

Each project gets, from the **`project-core`** module (always):
- a **resource group**, a **storage account** (ADLS Gen2), a **Key Vault**, a **budget**,
  a **user-assigned managed identity** ("compute identity"), and dedicated **subnets** in
  the shared VNet, all network-isolated by an NSG.

Then **opt-in capabilities** (per project's `capabilities` list) layer on top:
`aml`, `azure-batch`, `container-apps`, `postgresql`, `functions`, `blob-storage`, `vms`.
An **ACR** (container registry) is auto-added whenever a project has `aml`,
`container-apps`, or `azure-batch`.

**Naming convention:** `{resource-type}-{project}-{env}-{location}`; storage/registry/batch
names strip hyphens and truncate. `rise` has no `legacy_name_suffix`, so there's no `-prod`
env infix in its names.

---

## 2. The `rise` project — exactly what we get

From `main/terraform.tfvars` (the `rise` block):

```hcl
"rise" = {
  subnet_index = 7
  budget_amount = <redacted>                 # USD/month, with alert emails
  team_group_object_id         = "REDACTED-..."
  project_lead_group_object_id = "REDACTED-..."
  capabilities = ["aml", "azure-batch"]
  capability_config = {
    aml = {
      max_compute_nodes = 2
      compute_vm_size   = "Standard_E64ds_v4"  # 64 vCPU, memory-optimized
    }
    azure-batch = {
      pool_id       = "<proj>-pool"
      vm_size       = "Standard_D64ds_v6"       # 64 vCPU, general-purpose, local NVMe temp disk
      node_priority = "dedicated"               # on-demand (not evictable spot)
      max_nodes     = 2                          # capped by compute-subnet IP budget at plan time
    }
  }
  allowed_datasets = []                          # NO access to shared Planet/Maxar datasets
}
```

### 2.1 Resources this provisions (with their real names)

`location = <loc>`, no env suffix → names are:

| Kind | Name | Notes |
|---|---|---|
| Resource group | `rg<proj>` | `prevent_destroy` + delete-lock |
| **Project storage** | `st<proj>` | **ADLS Gen2** (HNS on), LRS, `data` container, firewalled |
| Key Vault | `kv<proj>` | RBAC-auth, purge-protected — **where fsd secrets go** |
| **Compute identity (UAMI)** | `id<proj>-compute` | the identity everything runs as |
| Compute subnet | `snet<proj>-compute` | `/24` in the shared VNet, service endpoints |
| NSG | `nsg<proj>` | deny-by-default inbound; Batch/AML mgmt ports open |
| ACR (auto) | `acr<proj>` | container registry for task images |
| **Batch account** | `ba<proj>` | BatchService mode, auto-storage = project storage |
| **Batch pool** | `<proj>-pool` | D64ds_v6, dedicated, autoscale 0→2, container-enabled |
| AML workspace | `mlw<proj>` | + workspace storage `stmlw<proj>` |
| AML compute cluster | `cluster-<proj>` | E64ds_v4, autoscale 0→2 |

### 2.2 The compute identity is the linchpin

`id<proj>-compute` (a **user-assigned managed identity**) is pre-granted, by
`project-core` + the capability modules:
- **Storage Blob Data Contributor** on `st<proj>` (read/write all project blobs)
- **Key Vault Secrets User** on `kv<proj>` (read secrets)
- **AcrPull + AcrPush** on `acr<proj>` (pull/push container images)
- **Contributor** on the Batch account `ba<proj>` (submit jobs/tasks via MSI)

The Batch **account** and every **pool node** run *as* this identity. So code on a node
that uses `DefaultAzureCredential()` (Azure SDK / `azure-identity`) automatically gets a
token for blob, Key Vault, and Batch **with no secrets baked into the image**. This is the
crux of the whole auth story.

### 2.3 Network & security posture (matters for fsd I/O)

- Project storage & Key Vault are **deny-by-default firewalled**: reachable only from the
  VPN IP ranges *and* the project's own subnets (via VNet **service endpoints**). Pool
  nodes live in `snet<proj>-compute`, so they're allowed. A laptop must be on
  the **VPN + `az login`** to touch storage directly.
- **Account keys are DISABLED** on project storage (`shared_access_key_enabled = false`).
  → **No connection strings / account keys exist.** All access is **Entra ID (MSI / user
  token) or user-delegation SAS.** This directly shapes how the fsspec storage seam must
  authenticate (see §4.1).
- Outbound: nodes can reach the Internet (`AllowInternetOutbound`) — so **CDSE downloads
  work** from a pool node — and Azure services.
- NSG opens Batch node-management ports (`29876-29877`, `BatchNodeManagement` service tag)
  and AML (`44224`).

---

## 3. Where fsd fits: the two compute paths

`rise` has **both** `aml` and `azure-batch`. For fsd's **download → datacube** fan-out,
**Azure Batch is the intended target** (the CLAUDE.md "runner seam over a CLI unit-of-work;
an Azure Batch runner dispatches the same task later"). AML is more for training/notebooks
(out of fsd core scope) but is available as a driver host.

**Azure Batch mental model** (maps 1:1 onto fsd's existing design):
- A **pool** = a set of identical VM nodes (`<proj>-pool`, D64ds_v6) that **autoscales 0→N**
  on pending-task pressure and **back to 0 when idle** (so idle cost ≈ 0).
- A **job** = a collection of **tasks**; each **task** = one command line run on a node
  (in our case, inside a container).
- A **driver** submits the job + tasks to the Batch account (via MSI), then Batch schedules
  tasks onto nodes as they scale up.

This is exactly the fsd **runner seam**: today the "build one datacube" unit-of-work is a
CLI (`fsd.workflows.task`) dispatched locally by **Snakemake**; on Azure the **same CLI**
becomes a **Batch task**, and a Batch runner replaces Snakemake as the dispatcher. Snakemake
= the *local* runner; Azure Batch = the *scale* runner. The unit-of-work doesn't change.

```
                 fsd today (local)                    fsd on rise (Azure Batch)
  unit of work   fsd.workflows.task CLI               SAME CLI, inside a container
  dispatcher     Snakemake (local cores)              Azure Batch job/tasks → <proj>-pool
  parallelism    N processes on 1 machine             N tasks across autoscaled nodes
  file I/O       fsspec → local disk                  fsspec → adlfs (st<proj>)
  secrets        secrets/ dir                          Key Vault kv<proj> (via MSI)
```

---

## 4. How fsd's seams land on `rise`

### 4.1 Storage seam (`fsd.storage`, fsspec) → ADLS Gen2 via MSI

- Project storage `st<proj>` is **ADLS Gen2**. fsspec talks to it through
  **`adlfs`** (`AzureBlobFileSystem` / `abfs[s]://`). URIs look like
  `abfss://data@st<proj>.dfs.core.windows.net/<path>` (container `data`).
- **Auth = `DefaultAzureCredential`**, *not* account keys (keys are disabled). On a pool
  node this resolves to the compute identity's MSI automatically; on a laptop it's `az
  login` + VPN. This is a config change to `fsd.storage`, **not** new code paths — exactly
  the "storage becomes config, not code" goal. We'll need to confirm `adlfs` +
  `DefaultAzureCredential` works with our `storage.transfer` / `size` / `load_npy` calls.
- The **generic S3 transport** in fsd (CDSE download via `s3fs`, any `endpoint_url`) is
  untouched — CDSE stays S3; only the *destination* of a tile download becomes an `abfss://`
  URL. `storage.transfer(cdse_s3_url, abfss_dst)` is the one-line tile copy.

**Open item:** fsd's documented raster-read exception uses **rasterio/GDAL VSI**, not
fsspec. On Azure that means GDAL `/vsiadls/` (or `/vsiaz/`) + env-based credentials, which
is a *separate* auth path from adlfs. We must make GDAL read blobs under MSI too (likely
`AZURE_STORAGE_ACCESS_TOKEN` / `AZURE_NO_SIGN_REQUEST` config, or user-delegation SAS). This
is a real design point for the spec.

### 4.2 Runner seam → Azure Batch runner

- Add an **Azure Batch runner** alongside the Snakemake runner in `fsd.workflows`. It
  builds the same `input.csv` of units, then for each unit creates a Batch **task** whose
  command line is the `fsd.workflows.task` CLI (same args we pass today).
- Submission uses the **`azure-batch` SDK** authenticated via `DefaultAzureCredential`
  against `https://ba<proj>.<region>.batch.azure.com` (the account URL is a TF
  output). The compute identity has Contributor on the account.
- Tasks are **containerized** (the pool is `DockerCompatible`): each task runs our fsd
  image pulled from `acr<proj>`.

### 4.3 Container image → ACR

- Build an fsd Docker image (the fsd package + its deps + GDAL/rasterio) and **push to
  `acr<proj>`** (compute identity has AcrPush; a human/CI does the push).
- The pool pulls it via the compute identity (AcrPull). Optionally list it in the pool's
  `container_image_names` for a **warm cache** on scale-up (avoids first-task pull latency)
  — that's a tfvars change on the pool.

### 4.4 Secrets → Key Vault

- CDSE S3 credentials (today in `secrets/`) move to **`kv<proj>`**; fsd reads
  them at runtime via MSI (`azure-keyvault-secrets` + `DefaultAzureCredential`). No secrets
  in the image or in blob.

---

## 5. End-to-end: fsd on `rise` (the target flow)

```
  [driver]  (laptop on VPN, or AML compute, or a small VM)
     |  1. reads geometries + builds the unit list (input.csv) — as today
     |  2. az/MSI: submit Batch job to ba<proj>, one task per unit
     v
  [Batch pool <proj>-pool]  autoscales 0 -> up to 2 x D64ds_v6, pulls fsd image from acr<proj>
     |  each task = `python -m fsd.workflows.task ...` in the fsd container, running as id-rise-compute
     |    - reads CDSE creds from kv<proj> (MSI)
     |    - downloads S2 tiles from CDSE S3 -> writes to abfss://data@st<proj>... (fsspec/adlfs)
     |    - builds datacube (rasterio reads blobs via GDAL VSI), writes datacube.npy + metadata to blob
     v
  [outputs]  in st<proj>; flatten runs as another job/step; pool scales back to 0 (≈ $0 idle)
```

---

## 6. Gotchas & constraints (things that will bite us)

1. **Batch quota starts tiny (~6 dedicated vCPUs).** A fresh Batch account can't even run
   one 64-vCPU node. Before any real run we must file a **per-Batch-account quota increase**
   in the Portal for the D-family in <loc> (need ≥128 vCPU for 2×D64). Quota is
   per-account — it does not carry over from other projects. (`common-ops.md` §quota.)
2. **`max_nodes = 2` today** — deliberately small, and validated at plan time against the
   compute subnet's IP budget. Scaling out = raise `max_nodes` in tfvars (needs subnet IP
   headroom **and** quota). A platform-admin `terraform apply`, not something we do.
3. **`max_tasks_per_node = 1` (module default).** A D64 node has 64 vCPUs; one
   fine-grained per-field task would waste 63 of them. We must either **raise
   max_tasks_per_node** (pack many tasks per node) or make each **task internally parallel**
   (one task builds many cubes across the node's cores, reusing our Snakemake-in-container
   or a process pool). **This is the key task-granularity design decision** (see §7).
4. **Keys disabled / MSI-only auth.** No account-key fallback anywhere — both adlfs *and*
   GDAL VSI must authenticate via Entra ID. Test both read paths early.
5. **Firewalled storage.** From a laptop you need VPN + `az login`; pool nodes are fine
   (they're in the subnet). Don't assume public blob access.
6. **D64ds_v6 has a local NVMe temp disk** (the `d`/`ds`). fsd's build is **I/O-bound**
   (load_images ≈73% of CPU); staging COG reads/writes on the node's local SSD (Batch task
   working dir) rather than round-tripping blob for scratch is likely a big lever.
7. **COG-on-download is local-dst only in fsd v1** (TODO #15: remote-dst COG =
   stage→convert→upload). Azure wants remote-dst; this parked TODO becomes in-scope for the
   Batch spec.
8. **No shared-dataset access** (`allowed_datasets = []`). rise brings its own S2 archive
   into `st<proj>`; we don't read the platform's Planet/Maxar containers.
9. **We don't run Terraform.** Any infra change (max_nodes, max_tasks_per_node, warm-cache
   image, adding `vms` for a driver) is a tfvars edit + gated `deploy.sh` by a platform
   admin. We propose; they apply.

---

## 7. Open design questions for the Batch spec (to work through with examples)

These are the decisions the future spec 10 must settle. Flagged here so we don't lose them:

1. **Task granularity / node packing.** One Batch task per datacube (simple, but
   `max_tasks_per_node` must go up to ~64 to fill a D64), *or* one task per node that fans
   out internally across the 64 cores (reuse Snakemake/process-pool inside the container)?
   Trade-off: scheduler overhead & retry granularity vs. node utilization. **Leaning:**
   coarse tasks that each saturate a node, given the build is I/O-bound and per-cube tasks
   are short.
2. **Where does the driver run?** Laptop-on-VPN (simplest to start), an AML compute job, or
   a small always-/on-demand VM (would need adding `vms` to rise)? The `common-ops` Batch
   example pairs `vms` + `azure-batch` for exactly this.
3. **GDAL/VSI auth under MSI** for the raster-read exception — `/vsiadls/` config, token
   env vars, or hand rasterio a user-delegation SAS URL? Needs a spike.
4. **Input/output data layout in blob** — container/paths for the S2 archive, catalogs,
   datacubes, flattened arrays; how the catalog (GeoParquet) is shared to tasks.
5. **Container image** — base (GDAL/rasterio wheels vs. system GDAL), size, build/push CI,
   warm-cache via `container_image_names`.
6. **Runner abstraction in `fsd.workflows`** — the seam so `--runner=snakemake|batch`
   selects dispatcher without touching the task CLI.
7. **Idempotency / resume at scale** — today `done.txt` sentinels + skip-if-exists; how that
   behaves with Batch task retries and blob eventual consistency.
8. **Cost/observability** — budget alerts already exist ($10k/mo); do we want per-run
   timing/telemetry (the spec-11 `timings.json` seam) written to blob?

## 8. Things to confirm (not yet verified)

- Exact Batch **account URL** output name and the <loc> Batch endpoint host.
- Whether `adlfs` + `DefaultAzureCredential` covers all `fsd.storage` operations we use
  (`transfer`, `size`, `load_npy`, atomic `.part`+rename — rename semantics on ADLS Gen2).
- Current **quota** actually granted on `ba<proj>` (needs `az batch account show`).
- Whether the pool image (`microsoft-dsvm/ubuntu-hpc/2204`) + Docker is enough, or we need a
  custom node image.

---

*Maintenance: update this when the `rise` tfvars change, when we confirm any "to confirm"
item, or when a design question is resolved (then fold it into the spec).*
