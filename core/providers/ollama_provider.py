"""Ollama local provider — via httpx (Trio-native)."""

from __future__ import annotations

import logging

import httpx

from core.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger("brain_loader.providers.ollama")


class OllamaProvider(BaseProvider):
    """
    Ollama local LLM provider.
    
    Runs models locally via Ollama server. Requires:
    - ollama installed: https://ollama.ai
    - ollama serve running
    - Model pulled: ollama pull <model>
    """

    def __init__(self, config: dict) -> None:
        super().__init__("ollama", config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self._local_lock = self._lock  # Per-backend VRAM protection

    @property
    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        if not self.enabled:
            return False
        # We can't do an async check here, so rely on the config
        return True

    async def _execute(self, prompt: str, **kwargs) -> ProviderResponse:
        """Send request to Ollama generate endpoint."""
        async with self._local_lock:  # VRAM protection
            client = await self._get_client()
            model = kwargs.get("model", self.model)
            system = kwargs.get("system", "You are a helpful assistant.")
            input_tokens = self._estimate_tokens(prompt)

            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {
                        "temperature": kwargs.get("temperature", 0.7),
                        "num_predict": kwargs.get("max_tokens", 4096),
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("response", "")
            # Ollama returns prompt_eval_count and eval_count
            return ProviderResponse(
                content=content,
                input_tokens=data.get("prompt_eval_count", input_tokens),
                output_tokens=data.get("eval_count", self._estimate_tokens(content)),
                model=model,
                provider=self.name,
            )
