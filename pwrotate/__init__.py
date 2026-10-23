"""pw-manager-auto-rotate (pwrotate): rotate a secret everywhere it lives, from your Bitwarden or Vaultwarden vault."""
from .engine import Engine, Result
from .manifest import Secret, Place, load
from .vault import Vault, MemoryVault, BitwardenVault

__version__ = "0.2.0"
__all__ = ["Engine", "Result", "Secret", "Place", "load", "Vault", "MemoryVault", "BitwardenVault", "__version__"]
