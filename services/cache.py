from __future__ import annotations

import time
from typing import Any, Optional


class SessionCache:
    """Lightweight TTL cache backed by Streamlit's st.session_state."""

    def __init__(self, session_state: dict) -> None:
        self._state = session_state

    def get(self, key: str) -> Optional[Any]:
        """Return cached value if present and not expired, otherwise None."""
        entry = self._state.get(f"_cache_{key}")
        if entry is None:
            return None
        if time.time() >= entry["expires_at"]:
            self.invalidate(key)
            return None
        return entry["value"]

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Store *value* under *key* with a TTL in seconds (default 300)."""
        self._state[f"_cache_{key}"] = {
            "value": value,
            "expires_at": time.time() + ttl,
        }

    def invalidate(self, key: str) -> None:
        """Remove a single cached entry."""
        self._state.pop(f"_cache_{key}", None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Remove all cached entries whose key starts with *prefix*."""
        full_prefix = f"_cache_{prefix}"
        keys_to_delete = [k for k in list(self._state.keys()) if k.startswith(full_prefix)]
        for k in keys_to_delete:
            del self._state[k]

    def invalidate_all(self) -> None:
        """Remove every entry managed by this cache."""
        keys_to_delete = [k for k in list(self._state.keys()) if k.startswith("_cache_")]
        for k in keys_to_delete:
            del self._state[k]
