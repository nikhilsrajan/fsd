# fsd — every AZ_* variable the run-books use, in one place. (spec 41 D7)
#
#   cp env.example.sh env.local.sh     # env.local.sh is gitignored
#   $EDITOR env.local.sh               # fill the blanks
#   source env.local.sh
#
# A missing value is then ONE VISIBLE BLANK LINE here, instead of an absent export
# five run-books deep. Concrete values for the `rise` platform live in
# AZURE_INFRA_PRIVATE.md at the WORKSPACE ROOT (uncommitted, never pushed) — this
# file is in a public MIT repo and must never carry a real name, id or URL.
#
# What each variable means, where its value comes from, and a command to verify it:
#   docs/reference/environment.md
#
# NOTE none of these are read by `src/fsd/` — every one is operator-facing, consumed
# by the run-book shell, the `az` CLI, or demos/e2e_austria_aml.py. fsd's own library
# code takes storage locations as arguments, never from the environment.

# ─── 1. Subscription & resource group ────────────────────────────────────────────
export AZ_SUBSCRIPTION_ID=''      # az account show --query id -o tsv
export AZ_RG=''                   # resource group holding the AML workspace + storage
export AZ_LOC=''                  # region, e.g. the one the cluster lives in

# ─── 2. Storage: account, filesystem, and the roots derived from them ────────────
export AZ_ACCOUNT=''              # ADLS Gen2 storage account name
export AZ_FS=''                   # filesystem / container inside that account
export AZ_PREFIX=''               # your path prefix inside the container, e.g. a username
export AZ_SCRATCH_PREFIX=''       # scratch prefix, no leading/trailing slash

# Derived — leave these as-is unless a run-book says otherwise.
export AZ_ROOT="abfss://${AZ_FS}@${AZ_ACCOUNT}.dfs.core.windows.net/${AZ_PREFIX:+$AZ_PREFIX/}fsd-p2-build"

# ─── 3. The archive and its catalog ──────────────────────────────────────────────
# ⚠️ FOUR SPELLINGS OF ONE IDEA exist across the run-books, because each was written
# in a different week. They are NOT unified here: run-books are point-in-time
# documents (spec 41 D3) and are never edited after the fact. Set whichever the
# run-book you are running actually names. AZ_ARCHIVE_ROOT is the canonical one.
export AZ_ARCHIVE_ROOT="${AZ_ROOT}"                              # canonical: the archive's root
export AZ_ARCHIVE="${AZ_ARCHIVE_ROOT}/archive"                   # alias: root + /archive
export AZ_ARCHIVE_PATH=''                                        # alias: container-relative path form
export AZ_ARCHIVE_CATALOG="${AZ_ARCHIVE_ROOT}/archive/catalog.parquet"
export AZ_CATALOG="${AZ_ARCHIVE}/catalog.parquet"                # alias of AZ_ARCHIVE_CATALOG
export AZ_CATALOG_URL="${AZ_ARCHIVE_CATALOG}"                    # alias, full abfss:// form

# ─── 4. Azure ML: workspace, cluster, environments ───────────────────────────────
export AZ_ML_WORKSPACE=''         # AML workspace name
export AZ_CLUSTER=''              # the d16 compute cluster name
export AZ_ACR=''                  # container registry backing the environments
export AZ_ENV_NAME='fsd-aml-env'          # general-purpose env (download/build/flatten)
export AZ_INFER_ENV_NAME='fsd-infer-env'  # inference env: fsd + the adapter's DEPS only.
                                  # Since spec 44 it does NOT copy any adapter source —
                                  # bundles carry that. Rebuild only when DEPS change.
# Versions are queried, never guessed — a stale version silently runs old code:
export AZ_ENV_VERSION="$(az ml environment list -n "$AZ_ENV_NAME" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query '[0].version' -o tsv 2>/dev/null)"
export AZ_INFER_ENV_VERSION="$(az ml environment list -n "$AZ_INFER_ENV_NAME" -g "$AZ_RG" -w "$AZ_ML_WORKSPACE" --query '[0].version' -o tsv 2>/dev/null)"
export AZ_ENV_NAME_VERSION="${AZ_ENV_NAME}:${AZ_ENV_VERSION}"    # demos/e2e_austria_aml.py reads this

# ─── 5. Identity & secrets ───────────────────────────────────────────────────────
export AZ_UAMI_NAME=''            # user-assigned managed identity the compute runs as
export AZ_UAMI_CLIENT_ID="$(az identity show -g "$AZ_RG" -n "$AZ_UAMI_NAME" --query clientId -o tsv 2>/dev/null)"
export AZ_VAULT_URL=''            # Key Vault URL, if you have write access
export AZ_CDSE_SECRET_NAME=''     # name of the CDSE credentials secret in that vault
export AZ_CREDS_URL="${AZ_ROOT}/_secrets/cdse_credentials.json"  # blob copy the nodes read
export AZ_LOCAL_CREDS_JSON=''     # path to your LOCAL cdse_credentials.json

# ─── 6. Azure Batch — pre-AML fork, kept for run-book 36's probe ─────────────────
export AZ_BATCH_ACCOUNT=''
export AZ_BATCH_POOL=''

# ─── 7. Run inputs: ROI, window, bands ───────────────────────────────────────────
export AZ_ROI_URL="${AZ_ROOT}/_inputs/s2grid=476da24.geojson"    # single-cell smoke ROI
export AZ_ROI_MULTI_URL="${AZ_ROOT}/_inputs/austria_eurocrops_sampled.geojson"
export AZ_ROI_REAL_URL=''         # the AT_ROI geojson on blob (run-book 37 Phase 3)
export AZ_ROI_REAL_LOCAL=''       # its local twin, e.g. ../shapefiles/<roi>.geojson
export AZ_START=''                # window start, YYYY-MM-DD
export AZ_END=''                  # window end, YYYY-MM-DD
export AZ_START_3B="$AZ_START"    # run-book 36 Phase 3b reuses the same window
export AZ_END_3B="$AZ_END"
export AZ_BANDS='B02,B03,B04,B08,B8A,SCL'
export AZ_MAX_TILES='600'         # cap on MGRS tiles; the Austria archive is 576

# ─── 8. Fan-out & run control ────────────────────────────────────────────────────
export AZ_N_SHARDS='8'            # fan-out width — see docs/findings/workload-regimes.md
export AZ_LOCAL_CORES='4'         # cores for the local comparison leg
export AZ_MERGE_MODE='strict'     # strict | reproject
export AZ_COMPARE_CELLS='3'       # cells sampled for the local-vs-cluster comparison
export AZ_ON_VM=''                # set to any value to force "driver is in Azure"

# ─── 9. Artifacts handed between run-books ───────────────────────────────────────
export AZ_BUNDLE_LOCAL=''         # run-book 40's demo_rf_bundle/ — run-book 38 stages it
export AZ_ADAPTERS_SRC='demos/adapters.py'   # baked into the inference environment
export AZ_PHASE3_INPUT_CSV="${AZ_ROOT}/runs/<phase3-run-id>/input.csv"
export AZ_P3_RUN=''               # run-book 38 Phase 3 run folder
export AZ_P3_OUT=''               # run-book 38 Phase 3 output folder
