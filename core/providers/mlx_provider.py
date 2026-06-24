"""
MLX local provider — Apple Silicon only.
Uses trio.to_thread.run_sync to offload blocking MLX calls.
"""

from __future__ import annotations

import logging
import os
import warnings

import trio

from core.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger("brain_loader.providers.mlx")

# MLX is optional — only available on Apple Silicon
MLX_AVAILABLE = False
try:
    import mlx.core as mx
    from mlx_lm import load, generate

    MLX_AVAILABLE = True
    logger.info("MLX loaded — Apple Silicon detected")
except ImportError:
    logger.debug("MLX not available — install with: pip install mlx mlx-lm")


class MLXProvider(BaseProvider):
    """
    Apple MLX local inference provider.
    
    Uses trio.to_thread.run_sync because MLX is synchronous.
    Only available on Apple Silicon (M1/M2/M3/M4).
    
    First call loads the model into VRAM. Subsequent calls reuse it.
    """

    def __init__(self, config: dict) -> None:
        super().__init__("mlx", config)
        self.model_path = config.get("model", "mlx-community/Qwen3-32B-4bit")
        self._model = None
        self._tokenizer = None
        self._local_lock = self._lock  # Per-backend VRAM protection

    @property
    def is_available(self) -> bool:
        """Check if MLX can run on this machine."""
        if not self.enabled:
            return False
        if not MLX_AVAILABLE:
            return False
        # Check Apple Silicon
        if os.uname().machine not in ("arm64", "aarch64"):
            logger.debug("MLX requires Apple Silicon (arm64)")
            return False
        return True

    async def _execute(self, prompt: str, **kwargs) -> ProviderResponse:
        """Run MLX inference in a thread pool."""
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not installed. Run: pip install mlx mlx-lm")

        async with self._local_lock:  # VRAM protection
            return await trio.to_thread.run_sync(
                self._sync_generate, prompt, kwargs
            )

    def _sync_generate(self, prompt: str, kwargs: dict) -> ProviderResponse:
        """Synchronous MLX generation (runs in thread)."""
        import time as time_mod
        
        start = time_mod.perf_counter()
        
        # Lazy load model
        if self._model is None:
            logger.info("MLX: Loading model %s...", self.model_path)
            self._model, self._tokenizer = load(self.model_path)
            logger.info("MLX: Model loaded")

        system = kwargs.get("system", "You are a helpful assistant.")
        full_prompt = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

        max_tokens = kwargs.get("max_tokens", 4096)
        temperature = kwargs.get("temperature", 0.7)

        input_tokens = len(self._tokenizer.encode(full_prompt))

        response = generate(
            self._model,
            self._tokenizer,
            prompt=full_prompt,
            max_tokens=max_tokens,
            temp=temperature,
            verbose=False,
        )

        output_tokens = len(self._tokenizer.encode(response))
        latency_ms = (time_mod.perf_counter() - start) * 1000

        return ProviderResponse(
            content=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model_path,
            provider=self.name,
            latency_ms=latency_ms,
        )
