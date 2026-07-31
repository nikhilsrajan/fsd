# AML user-assigned identity is selected via `AZURE_CLIENT_ID` set by the runner, with no fsd code change

**Status:** accepted (spec 36, D4)

**Context.** `fsd/storage/azure.py::_get_credential()` constructs a bare `DefaultAzureCredential()`,
which is correct on a laptop (`az login`) and on a host with a *system-assigned* identity. The `rise`
AML cluster has **only a user-assigned identity and no system-assigned one**, and a user-assigned
identity **must be selected by client ID** — IMDS will not guess. A probe confirmed this fails as a
**silent runtime auth error** on the node (`ManagedIdentityCredential: Expecting value…`), not
something predictable from the code — every blob read on the cluster would have failed.

**Decision.** The **runner sets `AZURE_CLIENT_ID`** (= the node's `DEFAULT_IDENTITY_CLIENT_ID`) in the
job environment. Verified against `azure-identity` 1.25.3: `DefaultAzureCredential.__init__` already
honours `AZURE_CLIENT_ID`, so the entire fix is **one environment variable in the job spec — no `fsd`
code changes**. This keeps AML-specific knowledge inside the dispatcher (ADR 0004 seam boundary).

**Considered options.** **Hard-code `ManagedIdentityCredential` on the node** — rejected: forks the
auth path and breaks running the same image locally. **Teach `fsd` to read
`DEFAULT_IDENTITY_CLIENT_ID`** — rejected: that variable name is AML-specific, violating the seam
boundary. **Put the client ID in `fsd` config** — rejected: it is a concrete `rise` identifier and
`fsd` is a public MIT repo.

**Consequences.** Local behaviour is untouched (the variable is unset on a laptop; the kwarg resolves
to `None`). The concrete `rise` client ID never enters the public repo. A regression test asserts the
credential honours the env var. Revisit only if a researcher must run fsd on AML *without* our runner
(a three-line change — YAGNI now).
