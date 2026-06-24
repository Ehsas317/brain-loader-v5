"""
OpenAI-compatible provider — handles OpenAI, OpenRouter, Groq, and DeepSeek.
All share the same /chat/completions API shape.
"""

from __future__ import annotations

import logging
import time

import httpx
import trio

from core.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger("brain_loader.providers.openai")


class OpenAIProvider(BaseProvider):
    """
    OpenAI-compatible API provider.
    
    Works with:
    - OpenAI (gpt-4o, gpt-4o-mini)
    - OpenRouter (200+ models)
    - Groq (fast, free tier)
    - DeepSeek (cheap, good quality)
    """

    def __init__(self, name: str, config: dict) -> None:
        # name can be "openai", "openrouter", "groq", "deepseek"
        super().__init__(name, config)
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.rpm_limit = config.get("rpm_limit", 0)  # 0 = no limit
        self._request_times: list[float] = []  # For RPM tracking

    async def _execute(self, prompt: str, **kwargs) -> ProviderResponse:
        """Send request to /chat/completions endpoint."""
        # RPM throttle for Groq
        if self.rpm_limit > 0:
            await self._enforce_rpm()

        client = await self._get_client()
        api_key = self.api_key
        if not api_key:
            raise ValueError(f"{self.config.get('api_key_env', 'API_KEY')} not set")

        model = kwargs.get("model", self.model)
        system = kwargs.get("system", "You are a helpful assistant.")
        max_tokens = kwargs.get("max_tokens", 4096)
        temperature = kwargs.get("temperature", 0.7)

        input_tokens = self._estimate_tokens(prompt)

        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
        # OpenRouter needs extra headers
        if self.name == "openrouter":
            headers["http-referer"] = kwargs.get("site_url", "https://github.com/brain-loader-v5")
            headers["x-title"] = kwargs.get("site_name", "Brain Loader v5")

        response = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        response.raise_for_status()
        data = response.json()

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")

        # Track for RPM
        if self.rpm_limit > 0:
            self._request_times.append(time.monotonic())

        usage = data.get("usage", {})
        return ProviderResponse(
            content=content,
            input_tokens=usage.get("prompt_tokens", input_tokens),
            output_tokens=usage.get("completion_tokens", self._estimate_tokens(content)),
            model=data.get("model", model),
            provider=self.name,
        )

    async def _enforce_rpm(self) -> None:
        """Enforce requests-per-minute limit (Groq free tier = ~30)."""
        now = time.monotonic()
        window_start = now - 60
        
        # Remove requests outside the 60s window
        self._request_times = [t for t in self._request_times if t > window_start]
        
        if len(self._request_times) >= self.rpm_limit:
            # Wait until oldest request falls out of window
            wait_time = self._request_times[0] + 60 - now + 0.1
            if wait_time > 0:
                logger.debug("RPM limit reached, waiting %.1fs", wait_time)
                await trio.sleep(wait_time)
