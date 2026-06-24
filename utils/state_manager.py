"""
StateManager — Crash recovery and session persistence.

Saves and restores:
- Cost tracking state
- Memory contents
- Provider circuit breaker states
- User preferences (mode, ponytail mode)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import trio

logger = logging.getLogger("brain_loader.state")


class StateManager:
    """
    Manages persistent state for crash recovery.
    
    State is saved as JSON to state.json after each wave.
    On startup, previous state is restored if available.
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.state_file = Path("state.json")
        self._lock = trio.Lock()

    async def save(self, extra_state: dict | None = None) -> None:
        """Save current state to disk."""
        async with self._lock:
            state = {
                "version": "5.0.0",
                "mode": self.config.get("mode", "hybrid"),
                "ponytail_mode": self.config.get("ponytail", {}).get("mode", "lite"),
            }
            if extra_state:
                state.update(extra_state)
            
            try:
                self.state_file.write_text(
                    json.dumps(state, indent=2, default=str),
                    encoding="utf-8",
                )
                logger.debug("State saved to %s", self.state_file)
            except Exception as e:
                logger.error("Failed to save state: %s", e)

    async def restore(self) -> dict:
        """Restore state from disk."""
        async with self._lock:
            if not self.state_file.exists():
                return {}
            
            try:
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
                logger.info("State restored from %s", self.state_file)
                
                # Restore preferences
                if "mode" in state:
                    self.config["mode"] = state["mode"]
                if "ponytail_mode" in state:
                    self.config.setdefault("ponytail", {})["mode"] = state["ponytail_mode"]
                
                return state
            except Exception as e:
                logger.error("Failed to restore state: %s", e)
                return {}
