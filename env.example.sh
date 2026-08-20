# fsd — the six values you need to run the notebooks. (spec 41 D7)
#
#   cp env.example.sh env.local.sh     # your copy; env.local.sh is gitignored
#   $EDITOR env.local.sh               # fill the six blanks below
#
# THIS file is the committed template and must never hold a real name, id or URL. Your
# filled-in copy is `env.local.sh`, which is gitignored and stays that way. Concrete values
# come from your platform admin — for the `rise` platform they live in AZURE_INFRA_PRIVATE.md
# at the workspace root, never in this repo.
#
# Read by `notebooks/_config.py`, which both notebooks import:
#   notebooks/00_build_images.ipynb   -> AZ_RG, AZ_ML_WORKSPACE
#   notebooks/e2e_austria_aml.ipynb   -> all six
#
# `_config.py` PARSES this file rather than sourcing it — no shell runs — and skips any
# value containing `$`. Every value here must be a literal: if you need the output of an
# `az` command, run it and paste the result.
#
# ─── Why this file is short ──────────────────────────────────────────────────────
# It is what a user copies and fills in, and their entry point is a notebook. A variable
# no notebook reads is a blank you would be asked to fill for no reason, so it is not here.
#
# The run-books under `runbooks/` name many more variables. Those are point-in-time
# documents (spec 41 D3) — never edited after the fact, and progressively stale — so their
# variables are not this template's job. `demos/` names a few of its own. **Every variable
# this project has ever used is documented in `docs/reference/environment.md`**, with what
# it means and a command to verify it; set anything extra ad hoc in the shell if you run an
# old run-book or a demo.
#
# The canonical list of what belongs here is `notebooks/_config.py::NOTEBOOK_VARS`, and
# `tests/test_docs.py` fails if this file and that tuple ever disagree.

# ─── Where the workspace lives ───────────────────────────────────────────────────
export AZ_SUBSCRIPTION_ID=''      # az account show --query id -o tsv
export AZ_RG=''                   # resource group holding the AML workspace
export AZ_ML_WORKSPACE=''         # AML workspace name

# ─── What the jobs run on ────────────────────────────────────────────────────────
export AZ_CLUSTER=''              # the compute cluster the fan-out runs on

# The user-assigned managed identity the NODES authenticate with — NOT your own login.
# Get it with, then paste the result below:
#   az identity show -g "$AZ_RG" -n '<uami-name>' --query clientId -o tsv
export AZ_UAMI_CLIENT_ID=''       # a GUID, as a literal

# ─── Where the runs write ────────────────────────────────────────────────────────
# Full abfss:// URL, literal. Each run creates a timestamped folder underneath it.
#   abfss://<file-system>@<account>.dfs.core.windows.net/<prefix>
export AZ_ROOT=''
