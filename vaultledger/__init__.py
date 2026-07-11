"""VaultLedger: a privacy-first, local-first financial-document Q&A system.

Public surface is intentionally small at Phase 0: the data contracts
(``schemas``) and the typed config loader (``config``). Everything else is
built phase by phase per SPEC.md Section 16.
"""

from vaultledger import config, schemas
from vaultledger.config import Config, load_config

__all__ = ["config", "schemas", "Config", "load_config", "__version__"]

__version__ = "0.0.0"  # bumped as phases land
