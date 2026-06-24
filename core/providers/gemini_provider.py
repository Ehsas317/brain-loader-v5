"""Google Gemini provider — via httpx (Trio-native)."""

from __future__ import annotations

import logging

import httpx

from core.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger("brain_loader.providers.gemini")


class GeminiProvider(BaseProvider):
    """Google Gemini API provider."""

    def __init__(self, config: dict) -> None:
        super().__init__("gemini", config)
        self.base_url = config.get(
            "base_url", "https://generativelanguage.googleapis.com/v1beta"
        )

    async def _execute(self, prompt: str, **kwargs) -> ProviderResponse:
        """Send request to Gemini generateContent endpoint."""
        client = await self._get_client()
        api_key = self.api_key
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")

        model = kwargs.get("model", self.model)
        # Strip 'models/' prefix if present
        if model.startswith("models/"):
            model = model.split("/", 1)[1]

        system = kwargs.get("system", "You are a helpful assistant.")
        input_tokens = self._estimate_tokens(prompt)

        response = await client.post(
            f"{self.base_url}/models/{model}:generateContent",
            params={"key": api_key},
            json={
                "systemInstruction": {"role": "user", "parts": [{"text": system}]},
                "contents": [
                    {"role": "user", "parts": [{"text": prompt}]}
                ],
                "generationConfig": {
                    "maxOutputTokens": kwargs.get("max_tokens", 4096),
                    "temperature": kwargs.get("temperature", 0.7),
                },
            },
        )
        response.raise_for_status()
        data = response.json()

        # Extract text from candidates
        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    content += part["text"]

        usage = data.get("usageMetadata", {})
        return ProviderResponse(
            content=content,
            input_tokens=usage.get("promptTokenCount", input_tokens),
            output_tokens=usage.get("candidatesTokenCount", self._estimate_tokens(content)),
            model=model,
            provider=self.name,
        )
