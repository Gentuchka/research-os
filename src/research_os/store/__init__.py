"""Store package."""

from research_os.store.connection import connect
from research_os.store.repository import Repository

__all__ = ["Repository", "connect"]
