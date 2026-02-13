"""State management for persisting knowledge and monitoring history"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .config import get_config_dir


class MonitorState(BaseModel):
    """State for a single monitor"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    last_check: datetime | None = None
    last_results: dict[str, Any] = Field(default_factory=dict)
    seen_items: set[str] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_serializer("seen_items")
    def serialize_seen_items(self, value: set[str]) -> list[str]:
        """Serialize set to list for JSON compatibility"""
        return list(value)

    @field_serializer("last_check")
    def serialize_last_check(self, value: datetime | None) -> str | None:
        """Serialize datetime to ISO format string"""
        return value.isoformat() if value else None

    @classmethod
    def from_dict(cls, data: dict) -> "MonitorState":
        """Load from dictionary with type conversion"""
        if "last_check" in data and data["last_check"]:
            data["last_check"] = datetime.fromisoformat(data["last_check"])
        if "seen_items" in data:
            data["seen_items"] = set(data["seen_items"])
        return cls(**data)


class StateManager:
    """Manage persistent state across monitoring runs"""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or get_config_dir() / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.monitors: dict[str, MonitorState] = {}
        self.cache_dir = self.state_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)

    def get_monitor_state(self, monitor_name: str) -> MonitorState:
        """Get state for a specific monitor"""
        if monitor_name not in self.monitors:
            state_file = self.state_dir / f"{monitor_name}.json"
            if state_file.exists():
                with open(state_file) as f:
                    data = json.load(f)
                    self.monitors[monitor_name] = MonitorState.from_dict(data)
            else:
                self.monitors[monitor_name] = MonitorState()

        return self.monitors[monitor_name]

    def save_monitor_state(self, monitor_name: str, state: MonitorState):
        """Save state for a specific monitor"""
        self.monitors[monitor_name] = state
        state_file = self.state_dir / f"{monitor_name}.json"

        with open(state_file, "w") as f:
            json.dump(state.model_dump(), f, indent=2, default=str)

    def update_monitor(self, monitor_name: str, results: dict[str, Any], seen_items: set[str] | None = None):
        """Update monitor state with new results"""
        state = self.get_monitor_state(monitor_name)
        state.last_check = datetime.now()
        state.last_results = results

        if seen_items is not None:
            state.seen_items.update(seen_items)

        self.save_monitor_state(monitor_name, state)

    def get_new_items(self, monitor_name: str, current_items: set[str]) -> set[str]:
        """Get items that haven't been seen before"""
        state = self.get_monitor_state(monitor_name)
        return current_items - state.seen_items

    def cache_query_result(self, query_key: str, result: Any, ttl_seconds: int = 300):
        """Cache a query result with TTL using monotonic time"""
        cache_file = self.cache_dir / f"{self._sanitize_key(query_key)}.json"
        cache_data = {
            "result": result,
            "timestamp": datetime.now().isoformat(),  # For backward compatibility
            "cached_at_mono": time.monotonic(),  # Monotonic time for TTL
            "ttl_seconds": ttl_seconds,
        }

        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2, default=str)

    def get_cached_query(self, query_key: str) -> Any | None:
        """Get cached query result if not expired (using monotonic time)"""
        cache_file = self.cache_dir / f"{self._sanitize_key(query_key)}.json"

        if not cache_file.exists():
            return None

        with open(cache_file) as f:
            cache_data = json.load(f)

        ttl = cache_data.get("ttl_seconds", 300)

        # Use monotonic time if available (new format)
        if "cached_at_mono" in cache_data:
            age = time.monotonic() - cache_data["cached_at_mono"]
        else:
            # Fallback to wall-clock time for old cache entries
            cached_time = datetime.fromisoformat(cache_data["timestamp"])
            age = (datetime.now() - cached_time).total_seconds()

        if age > ttl:
            cache_file.unlink()  # Delete expired cache
            return None

        return cache_data["result"]

    def save_conversation_context(self, context_name: str, context: dict):
        """Save conversation context for later reference"""
        context_file = self.state_dir / "context" / f"{context_name}.json"
        context_file.parent.mkdir(exist_ok=True)

        with open(context_file, "w") as f:
            json.dump({"context": context, "timestamp": datetime.now().isoformat()}, f, indent=2, default=str)

    def load_conversation_context(self, context_name: str) -> dict | None:
        """Load saved conversation context"""
        context_file = self.state_dir / "context" / f"{context_name}.json"

        if not context_file.exists():
            return None

        with open(context_file) as f:
            data = json.load(f)
            return data.get("context")

    def get_history(self, monitor_name: str, limit: int = 10) -> list[dict]:
        """Get historical results for a monitor"""
        history_file = self.state_dir / "history" / f"{monitor_name}.jsonl"

        if not history_file.exists():
            return []

        history = []
        with open(history_file) as f:
            for line in f:
                history.append(json.loads(line))

        return history[-limit:]

    def append_history(self, monitor_name: str, result: dict):
        """Append result to monitor history"""
        history_dir = self.state_dir / "history"
        history_dir.mkdir(exist_ok=True)
        history_file = history_dir / f"{monitor_name}.jsonl"

        with open(history_file, "a") as f:
            json.dump({"timestamp": datetime.now().isoformat(), "result": result}, f, default=str)
            f.write("\n")

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """Sanitize key for use as filename"""
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in key)

    def get_stats(self) -> dict:
        """Get statistics about stored state"""
        monitor_count = len(list(self.state_dir.glob("*.json")))
        cache_count = len(list(self.cache_dir.glob("*.json")))
        history_count = (
            len(list((self.state_dir / "history").glob("*.jsonl"))) if (self.state_dir / "history").exists() else 0
        )

        return {
            "state_dir": str(self.state_dir),
            "monitors": monitor_count,
            "cached_queries": cache_count,
            "history_files": history_count,
        }

    def cleanup_expired_cache(self):
        """Remove all expired cache entries (using monotonic time)"""
        removed = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file) as f:
                    cache_data = json.load(f)

                ttl = cache_data.get("ttl_seconds", 300)

                # Use monotonic time if available (new format)
                if "cached_at_mono" in cache_data:
                    age = time.monotonic() - cache_data["cached_at_mono"]
                else:
                    # Fallback to wall-clock time for old cache entries
                    cached_time = datetime.fromisoformat(cache_data["timestamp"])
                    age = (datetime.now() - cached_time).total_seconds()

                if age > ttl:
                    cache_file.unlink()
                    removed += 1
            except Exception:
                # If we can't read it, delete it
                cache_file.unlink()
                removed += 1

        return removed
