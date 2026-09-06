"""Adapter registry (brand id -> adapter instance)."""
from __future__ import annotations

from typing import Dict, List, Optional

from app.hub.adapters.base import BrandAdapter


class AdapterRegistry:
    """Holds one adapter instance per brand."""

    def __init__(self) -> None:
        self._adapters: Dict[str, BrandAdapter] = {}

    def register(self, adapter: BrandAdapter) -> BrandAdapter:
        """Register (or replace) an adapter."""
        self._adapters[adapter.brand_id] = adapter
        return adapter

    def get(self, brand_id: str) -> Optional[BrandAdapter]:
        """Adapter for a brand or None."""
        return self._adapters.get(brand_id)

    def all(self) -> List[BrandAdapter]:
        """All adapters, sorted by brand id."""
        return [self._adapters[k] for k in sorted(self._adapters)]

    def ids(self) -> List[str]:
        """Registered brand ids."""
        return sorted(self._adapters)


registry = AdapterRegistry()
