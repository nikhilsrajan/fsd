"""Azure Key Vault secret access (spec 37 D5).

The `rise` compute identity already holds `Key Vault Secrets User` on the project's
Key Vault, so this needs no infra grant -- just a thin read, authenticated by the
same `AZURE_CLIENT_ID` spec 36 D4 sets for blob (`DefaultAzureCredential` selects a
user-assigned identity by that env var for every Azure SDK, Key Vault included --
one identity covers storage and secrets, on the node and the driver alike).

`vault_url` is always a caller-supplied parameter, never hardcoded here -- a concrete
`rise` Key Vault URL is an infra identifier that has no business in this public repo.
"""

from __future__ import annotations


def get_secret(vault_url: str, name: str) -> str:
    """Read one secret's current value from Key Vault.

    Lazy-imports `azure-keyvault-secrets` / `azure-identity` (mirrors
    `workflows.runners._import_aml_command`'s injection pattern) so `import fsd`
    never needs the `[azure]` extra, and tests substitute this function instead of
    requiring the extra ("no test may require Azure", spec 37 §7).
    """
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    return client.get_secret(name).value
