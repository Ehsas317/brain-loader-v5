"""Anthropic Claude provider — via httpx (Trio-native)."""

from __future__ import annotations

import logging

import httpx

from core.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger("brain_loader.providers.anthropic")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

    def __init__(self, config: dict) -> None:
        super().__init__("anthropic", config)
        self.base_url = config.get("base_url", "https://api.anthropic.com/v1")
        self.version = config.get("version", "2023-06-01")

    async def _execute(self, prompt: str, **kwargs) -> ProviderResponse:
        """Send request to Anthropic Messages API."""
        client = await self._get_client()
        api_key = self.api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        model = kwargs.get("model", self.model)
        system = kwargs.get("system", "")
        max_tokens = kwargs.get("max_tokens", 4096)

        messages = [{"role": "user", "content": prompt}]
        if system:
            # Anthropic uses a separate system parameter
            pass

        input_tokens = self._estimate_tokens(prompt + system)

        response = await client.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": self.version,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system or "You are a helpful assistant.",
                "messages": messages,
            },
        )
        response.raise_for_status()
        data = response.json()

        content = ""
        if data.get("content"):
            for block in data["content"]:
                if block.get("type") == "text":
                    content += block.get("text", "")

        return ProviderResponse(
            content=content,
            input_tokens=data.get("usage", {}).get("input_tokens", input_tokens),
            output_tokens=data.get("usage", {}).get("output_tokens", 0),
            model=model,
            provider=self.name,
        )
