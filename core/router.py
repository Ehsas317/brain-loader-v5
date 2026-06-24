"""
UniversalRouter — Trio-native provider chain routing with auto-failover.

Manages provider chains per role, circuit breakers, and intelligent retries.
All provider calls run through this router for consistent error handling.
"""

from __future__ import annotations

import logging
from typing import Any

import trio

from core.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger("brain_loader.router")


class UniversalRouter:
    """
    Routes requests through provider chains with auto-failover.
    
    Each role (researcher, coder, critic, etc.) has its own chain.
    The router walks the chain until a request succeeds.
    
    Example chain for "coder": [deepseek, groq, openai, openrouter, ollama]
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.chains: dict[str, list[str]] = config.get("chains", {})
        self.providers: dict[str, BaseProvider] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize all configured providers."""
        from core.providers.anthropic_provider import AnthropicProvider
        from core.providers.openai_provider import OpenAIProvider
        from core.providers.gemini_provider import GeminiProvider
        from core.providers.ollama_provider import OllamaProvider
        from core.providers.mlx_provider import MLXProvider

        provider_classes = {
            "anthropic": AnthropicProvider,
            "openai": lambda c: OpenAIProvider("openai", c),
            "openrouter": lambda c: OpenAIProvider("openrouter", c),
            "groq": lambda c: OpenAIProvider("groq", c),
            "deepseek": lambda c: OpenAIProvider("deepseek", c),
            "gemini": GeminiProvider,
            "ollama": OllamaProvider,
            "mlx": MLXProvider,
        }

        for name, prov_config in self.config.get("providers", {}).items():
            if name in provider_classes:
                try:
                    provider = provider_classes[name](prov_config)
                    self.providers[name] = provider
                    status = "✓" if provider.is_available else "✗ (no creds)"
                    logger.info("Provider %s %s", name, status)
                except Exception as e:
                    logger.warning("Failed to init provider %s: %s", name, e)

    def get_chain(self, role: str) -> list[BaseProvider]:
        """Get the provider chain for a role."""
        chain_names = self.chains.get(role, self.chains.get("default", []))
        chain = []
        for name in chain_names:
            if name in self.providers:
                chain.append(self.providers[name])
        return chain

    async def route(
        self,
        role: str,
        prompt: str,
        **kwargs: Any,
    ) -> ProviderResponse:
        """
        Route a prompt through the provider chain.
        
        Walks the chain node by node:
        1. Check circuit breaker
        2. Try request
        3. On failure: classify error, decide retry/skip
        4. On success: track cost, return response
        
        Args:
            role: Specialist role (researcher, coder, critic, etc.)
            prompt: The prompt to send
            **kwargs: Additional parameters (model, temperature, etc.)
        
        Returns:
            ProviderResponse with content or error
        """
        chain = self.get_chain(role)
        
        if not chain:
            logger.error("No providers available for role '%s'", role)
            return ProviderResponse(
                content="",
                error=f"No providers configured for role '{role}'",
                provider="router",
            )

        logger.debug(
            "Routing '%s' through chain: %s",
            role, " → ".join(p.name for p in chain)
        )

        last_error = ""
        for provider in chain:
            if not provider.is_available:
                logger.debug("Provider %s not available, skipping", provider.name)
                continue

            # Check circuit breaker
            if not await provider.circuit.can_execute():
                logger.debug("Circuit OPEN for %s, skipping", provider.name)
                continue

            # Attempt request
            logger.info("Trying %s for '%s'...", provider.name, role)
            response = await provider.execute(prompt, **kwargs)

            if response.error:
                last_error = response.error
                error_type = response.error.split(":")[0] if ":" in response.error else response.error

                # Classify error for retry decisions
                if error_type in ("RATE_LIMIT",):
                    logger.info("Rate limited on %s, trying next...", provider.name)
                    await trio.sleep(2)  # Brief backoff
                    continue
                elif error_type in ("QUOTA_EXCEEDED", "BILLING", "AUTH"):
                    logger.info("Quota/auth issue on %s, skipping...", provider.name)
                    continue  # Don't retry — won't help
                elif error_type in ("TIMEOUT", "NETWORK_ERROR", "SERVER_ERROR"):
                    logger.info("Transient error on %s, trying next...", provider.name)
                    continue
                else:
                    logger.info("Error on %s: %s", provider.name, response.error[:80])
                    continue
            else:
                # Success!
                if response.fallback_used:
                    logger.info(
                        "✓ '%s' completed via fallback %s ($%.4f)",
                        role, provider.name, response.cost
                    )
                else:
                    logger.info(
                        "✓ '%s' completed via %s ($%.4f)",
                        role, provider.name, response.cost
                    )
                return response

        # All providers in chain failed
        logger.error("All providers failed for role '%s'. Last error: %s", role, last_error)
        return ProviderResponse(
            content="",
            error=f"All chain nodes failed. Last: {last_error}",
            provider="router",
            fallback_used=True,
        )

    async def route_parallel(
        self,
        tasks: list[tuple[str, str, dict]],
    ) -> list[ProviderResponse]:
        """
        Route multiple tasks in parallel via Trio nursery.
        
        Args:
            tasks: List of (role, prompt, kwargs) tuples
        
        Returns:
            List of ProviderResponses (same order as tasks)
        """
        results: list[ProviderResponse | None] = [None] * len(tasks)

        async def execute_one(idx: int, role: str, prompt: str, kwargs: dict) -> None:
            results[idx] = await self.route(role, prompt, **kwargs)

        async with trio.open_nursery() as nursery:
            for i, (role, prompt, kwargs) in enumerate(tasks):
                nursery.start_soon(execute_one, i, role, prompt, kwargs)

        return [r for r in results if r is not None]

    async def close_all(self) -> None:
        """Close all provider connections."""
        for provider in self.providers.values():
            await provider.close()

    @property
    def available_providers(self) -> list[str]:
        """List of available provider names."""
        return [name for name, p in self.providers.items() if p.is_available]
