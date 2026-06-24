"""
BaseProvider — Trio-native abstract base for all LLM providers.
Includes CircuitBreaker for resilient provider chains.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import trio

logger = logging.getLogger("brain_loader.providers")


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject fast
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for provider resilience.
    
    States:
        CLOSED    → Normal operation, requests pass through
        OPEN      → After threshold failures, reject fast
        HALF_OPEN → After recovery_timeout, allow test calls
    """
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 2

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failures: int = field(default=0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)
    _half_open_calls: int = field(default=0, repr=False)
    _lock: trio.Lock = field(default_factory=trio.Lock, repr=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    async def can_execute(self) -> bool:
        """Check if request can proceed. Must be called under lock."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("CircuitBreaker: OPEN → HALF_OPEN (testing recovery)")
                    return True
                return False
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            
            return True  # Fallback

    async def record_success(self) -> None:
        """Record successful request."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failures = 0
                self._half_open_calls = 0
                logger.info("CircuitBreaker: HALF_OPEN → CLOSED (recovered)")
            else:
                self._failures = max(0, self._failures - 1)

    async def record_failure(self) -> None:
        """Record failed request."""
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.monotonic()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("CircuitBreaker: HALF_OPEN → OPEN (recovery failed)")
            elif self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker: CLOSED → OPEN (%d failures)", self._failures
                )


@dataclass
class ProviderResponse:
    """Structured response from any provider."""
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    cost: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    fallback_used: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class BaseProvider(ABC):
    """
    Trio-native abstract base for all LLM providers.
    
    All HTTP providers use httpx.AsyncClient for async I/O.
    Local providers (MLX) use trio.to_thread.run_sync.
    """

    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", False)
        self.model = config.get("model", "")
        self.cost_input = config.get("cost_per_1m_input", 0.0)
        self.cost_output = config.get("cost_per_1m_output", 0.0)
        self.timeout = config.get("timeout", 60)
        self.circuit = CircuitBreaker(
            failure_threshold=config.get("circuit_breaker", {}).get("failure_threshold", 3),
            recovery_timeout=config.get("circuit_breaker", {}).get("recovery_timeout", 60),
            half_open_max_calls=config.get("circuit_breaker", {}).get("half_open_max_calls", 2),
        )
        self._client: httpx.AsyncClient | None = None
        self._lock = trio.Lock()  # Per-backend lock for VRAM protection

    @property
    def api_key(self) -> str | None:
        """Read API key from environment variable."""
        env_var = self.config.get("api_key_env")
        if env_var:
            return os.environ.get(env_var)
        return None

    @property
    def is_available(self) -> bool:
        """Check if provider is enabled and has credentials."""
        if not self.enabled:
            return False
        if self.config.get("api_key_env") and not self.api_key:
            return False
        return True

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create shared httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def execute(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        """
        Execute prompt with circuit breaker protection.
        
        This is the public entry point. It handles:
        1. Circuit breaker checks
        2. Token counting
        3. Cost calculation
        4. Error classification
        """
        if not await self.circuit.can_execute():
            return ProviderResponse(
                content="",
                error=f"Circuit breaker OPEN for {self.name}",
                provider=self.name,
            )

        start_time = time.perf_counter()
        
        try:
            # Call provider-specific implementation
            response = await self._execute(prompt, **kwargs)
            
            # Calculate cost
            response.provider = self.name
            response.latency_ms = (time.perf_counter() - start_time) * 1000
            response.cost = (
                (response.input_tokens / 1_000_000) * self.cost_input +
                (response.output_tokens / 1_000_000) * self.cost_output
            )
            
            await self.circuit.record_success()
            logger.info(
                "%s: ✓ %d tokens ($%.4f) in %.1fms",
                self.name, response.total_tokens, response.cost, response.latency_ms
            )
            return response
            
        except Exception as e:
            await self.circuit.record_failure()
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = self._classify_error(e)
            logger.warning("%s: ✗ %s (%.1fms)", self.name, error_msg, latency_ms)
            
            return ProviderResponse(
                content="",
                error=error_msg,
                provider=self.name,
                latency_ms=latency_ms,
            )

    @abstractmethod
    async def _execute(self, prompt: str, **kwargs: Any) -> ProviderResponse:
        """Provider-specific implementation. Override in subclasses."""
        ...

    def _classify_error(self, error: Exception) -> str:
        """Classify error for retry/failover decisions."""
        error_str = str(error).lower()
        error_type = type(error).__name__

        if any(code in error_str for code in ["429", "rate limit", "too many requests"]):
            return "RATE_LIMIT"
        if any(code in error_str for code in ["401", "403", "quota", "billing", "insufficient_quota"]):
            return "QUOTA_EXCEEDED"
        if any(code in error_str for code in ["timeout", "timed out", "connecttimeout"]):
            return "TIMEOUT"
        if any(code in error_str for code in ["connection", "dns", "network", "unreachable"]):
            return "NETWORK_ERROR"
        if any(code in error_str for code in ["500", "502", "503", "504", "internal"]):
            return "SERVER_ERROR"
        
        return f"UNKNOWN:{error_type}:{str(error)[:100]}"

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~4 chars per token for English text."""
        return max(1, len(text) // 4)
