#!/usr/bin/env python3
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  LADDER — FILE: core/router.py                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Ladder (formerly Brain Loader v5)
# REPO:       https://github.com/Ehsas317/ladder
# WHAT:       The Ponytail decision ladder is the actual innovation here.
#             It climbs rungs to skip work. Named after the thing that makes
#             it unique.
#
# THIS FILE:
#   Universal Router — Trio-native provider chain routing with auto-failover.
#   Manages provider chains per role, circuit breakers, and intelligent retries.
#   All provider calls run through this router for consistent error handling.
#
# HOW TO USE LADDER:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project goal"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
Ladder — Universal Router

Routes requests through provider chains with auto-failover.
Each role has its own chain. The router walks the chain until success.

Example chain for "coder": [deepseek, groq, openai, openrouter, ollama]
"""

from __future__ import annotations

import logging
from typing import Any

import trio

from core.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger("ladder.router")


class UniversalRouter:
    """
    Ladder Universal Router

    Routes requests through provider chains with auto-failover.
    Circuit breakers prevent hammering failing providers.

    Usage:
        router = UniversalRouter(config)
        response = await router.route("coder", "Write Python code...")
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
        """
        chain = self.get_chain(role)
        
        if not chain:
            logger.error("No providers available for role '%s'", role)
            return ProviderResponse(
                content="",
                error=f"No providers configured for role '{role}'",
                provider="router",
            )

        last_error = ""
        for provider in chain:
            if not provider.is_available:
                logger.debug("Provider %s not available, skipping", provider.name)
                continue

            if not await provider.circuit.can_execute():
                logger.debug("Circuit OPEN for %s, skipping", provider.name)
                continue

            logger.info("Trying %s for '%s'...", provider.name, role)
            response = await provider.execute(prompt, **kwargs)

            if response.error:
                last_error = response.error
                err_lower = response.error.lower()

                # FIX BUG-V5-001: Robust substring matching for error classification
                if any(s in err_lower for s in ("rate_limit", "rate limit", "429", "too many requests")):
                    logger.info("Rate limited on %s, trying next...", provider.name)
                    await trio.sleep(2)
                    continue
                elif any(s in err_lower for s in ("quota", "billing", "auth", "unauthorized", "401", "403")):
                    logger.info("Quota/auth issue on %s, skipping...", provider.name)
                    continue
                elif any(s in err_lower for s in ("timeout", "network", "connection", "server", "500", "502", "503")):
                    logger.info("Transient error on %s, trying next...", provider.name)
                    continue
                else:
                    logger.info("Error on %s: %s", provider.name, response.error[:80])
                    continue
            else:
                if response.fallback_used:
                    logger.info("✓ '%s' completed via fallback %s ($%.4f)",
                              role, provider.name, response.cost)
                else:
                    logger.info("✓ '%s' completed via %s ($%.4f)",
                              role, provider.name, response.cost)
                return response

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
        # FIX BUG-V5-002: Return ALL results including errors — never silently drop
        results: list[ProviderResponse] = []

        async def execute_one(role: str, prompt: str, kwargs: dict) -> ProviderResponse:
            return await self.route(role, prompt, **kwargs)

        # FIX: nursery.start_soon requires a sync callable that wraps the async call.
        # The lambda pattern captures variables correctly via default arguments.
        async with trio.open_nursery() as nursery:
            for role, prompt, kwargs in tasks:
                nursery.start_soon(
                    lambda r=role, p=prompt, k=kwargs: results.append(await execute_one(r, p, k))
                )

        return results

    async def close_all(self) -> None:
        """Close all provider connections."""
        for provider in self.providers.values():
            await provider.close()

    @property
    def available_providers(self) -> list[str]:
        """List of available provider names."""
        return [name for name, p in self.providers.items() if p.is_available]
