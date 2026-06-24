"""
CostTracker — Session cost tracking + YAGNI savings.

Tracks every API call, warns before overspending, hard-stops at limit.
YAGNI (You Ain't Gonna Need It) savings come from Ponytail ladder decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import trio

logger = logging.getLogger("brain_loader.cost")


@dataclass
class CostSnapshot:
    """Immutable snapshot of costs at a point in time."""
    total_cost: float = 0.0
    total_tokens: int = 0
    api_calls: int = 0
    yagni_tokens_saved: int = 0
    yagni_tasks_skipped: int = 0
    fallbacks_triggered: int = 0


class CostTracker:
    """
    Tracks costs and enforces budget limits.
    
    Features:
    - Per-session cost accumulation
    - Budget warnings (default 85%)
    - Hard stop at max cost
    - YAGNI savings tracking
    """

    def __init__(self, config: dict) -> None:
        self.config = config.get("cost", {})
        self.max_cost = self.config.get("max_cost_per_project", 10.0)
        self.warn_threshold = self.config.get("warn_threshold", 0.85)
        self.track_yagni = self.config.get("track_yagni", True)
        
        self._total_cost = 0.0
        self._total_tokens = 0
        self._api_calls = 0
        self._yagni_tokens_saved = 0
        self._yagni_tasks_skipped = 0
        self._fallbacks_triggered = 0
        self._warned = False
        self._hard_stop = False
        self._lock = trio.Lock()

    async def add_cost(self, cost: float, tokens: int = 0) -> None:
        """Add a cost entry. Checks budget limits."""
        async with self._lock:
            self._total_cost += cost
            self._total_tokens += tokens
            self._api_calls += 1
            
            # Check warning threshold
            if not self._warned and self._total_cost >= self.max_cost * self.warn_threshold:
                self._warned = True
                logger.warning(
                    "[CostTracker] WARNING: $%.2f / $%.2f limit (%.0f%%)",
                    self._total_cost, self.max_cost, 
                    (self._total_cost / self.max_cost) * 100
                )
            
            # Check hard stop
            if self._total_cost >= self.max_cost:
                self._hard_stop = True
                logger.error(
                    "[CostTracker] HARD STOP: $%.2f / $%.2f limit reached!",
                    self._total_cost, self.max_cost
                )

    async def add_yagni_savings(self, tokens_saved: int, tasks_skipped: int = 0) -> None:
        """Record tokens saved by Ponytail ladder decisions."""
        if not self.track_yagni:
            return
        async with self._lock:
            self._yagni_tokens_saved += tokens_saved
            self._yagni_tasks_skipped += tasks_skipped

    async def record_fallback(self) -> None:
        """Record a provider fallback event."""
        async with self._lock:
            self._fallbacks_triggered += 1

    @property
    async def snapshot(self) -> CostSnapshot:
        """Get current cost snapshot."""
        async with self._lock:
            return CostSnapshot(
                total_cost=self._total_cost,
                total_tokens=self._total_tokens,
                api_calls=self._api_calls,
                yagni_tokens_saved=self._yagni_tokens_saved,
                yagni_tasks_skipped=self._yagni_tasks_skipped,
                fallbacks_triggered=self._fallbacks_triggered,
            )

    @property
    async def can_spend(self) -> bool:
        """Check if there's budget remaining."""
        async with self._lock:
            return not self._hard_stop and self._total_cost < self.max_cost

    @property
    def hard_stop_active(self) -> bool:
        """Check if hard stop is active."""
        return self._hard_stop

    def format_summary(self) -> str:
        """Format a human-readable cost summary."""
        # Note: This is synchronous for REPL display
        # For accurate values, use snapshot in async context
        return (
            f"Cost: ${self._total_cost:.4f} / ${self.max_cost:.2f} "
            f"| Tokens: {self._total_tokens:,} "
            f"| Calls: {self._api_calls}"
        )

    def format_yagni(self) -> str:
        """Format YAGNI savings summary."""
        if not self.track_yagni:
            return ""
        saved_cost = (self._yagni_tokens_saved / 1_000_000) * 0.5  # rough estimate
        return (
            f"YAGNI: {self._yagni_tokens_saved:,} tokens saved "
            f"(~${saved_cost:.2f}) | {self._yagni_tasks_skipped} tasks skipped"
        )
