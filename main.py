#!/usr/bin/env python3
"""
Brain Loader v5 — Lazy Conductor
Entry point with Trio event loop.

Usage:
    python main.py                          # Interactive REPL
    python main.py "Your goal here"         # Headless mode
    python main.py --config path.yaml "Goal"  # Custom config
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import trio
import yaml

from core.wave_engine import WaveEngine
from core.ponytail_planner import PonytailPlanner
from core.cost_tracker import CostTracker
from tui.repl import BrainREPL
from utils.state_manager import StateManager


def setup_logging(config: dict) -> None:
    """Configure logging with Rich-aware handlers."""
    log_dir = Path(config.get("logging", {}).get("directory", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper(), logging.INFO)

    # File handler for persistent logs
    file_handler = logging.FileHandler(
        log_dir / f"brain_loader_{datetime.now().strftime('%Y%m%d')}.log"
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    # Console handler (Rich REPL will override this)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    logging.basicConfig(level=level, handlers=[file_handler, console_handler])


def load_config(path: str | None = None) -> dict:
    """Load configuration from YAML file."""
    if path and Path(path).exists():
        with open(path) as f:
            return yaml.safe_load(f)
    
    # Default config path
    default = Path("config.yaml")
    if default.exists():
        with open(default) as f:
            return yaml.safe_load(f)
    
    # Fallback: return minimal default config
    return _default_config()


def _default_config() -> dict:
    """Return a sensible default configuration."""
    import os
    return {
        "mode": "hybrid",
        "ponytail": {
            "mode": "lite",
            "ladder": {
                "rung_1_brain_direct": True,
                "rung_2_memory_reuse": True,
                "rung_3_stdlib_first": False,
                "rung_4_merge_tasks": False,
                "rung_5_minimal_output": True,
            },
            "annotations": {"enabled": True, "include_upgrade_path": True},
        },
        "trio": {
            "wave_timeout": 300,
            "task_timeout": 120,
            "brain_timeout": 180,
        },
        "providers": {
            "anthropic": {
                "enabled": True,
                "api_key_env": "ANTHROPIC_API_KEY",
                "model": "claude-sonnet-4-20250514",
                "base_url": "https://api.anthropic.com/v1",
                "timeout": 60,
                "cost_per_1m_input": 3.0,
                "cost_per_1m_output": 15.0,
            },
            "openai": {
                "enabled": True,
                "api_key_env": "OPENAI_API_KEY",
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
                "timeout": 60,
                "cost_per_1m_input": 0.15,
                "cost_per_1m_output": 0.60,
            },
            "openrouter": {
                "enabled": True,
                "api_key_env": "OPENROUTER_API_KEY",
                "model": "openrouter/auto",
                "base_url": "https://openrouter.ai/api/v1",
                "timeout": 60,
                "cost_per_1m_input": 1.0,
                "cost_per_1m_output": 2.0,
            },
            "groq": {
                "enabled": True,
                "api_key_env": "GROQ_API_KEY",
                "model": "llama-3.3-70b-versatile",
                "base_url": "https://api.groq.com/openai/v1",
                "timeout": 30,
                "cost_per_1m_input": 0.0,
                "cost_per_1m_output": 0.0,
                "rpm_limit": 30,
            },
            "gemini": {
                "enabled": True,
                "api_key_env": "GOOGLE_API_KEY",
                "model": "gemini-2.5-flash",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "timeout": 60,
                "cost_per_1m_input": 0.15,
                "cost_per_1m_output": 0.60,
            },
            "deepseek": {
                "enabled": True,
                "api_key_env": "DEEPSEEK_API_KEY",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
                "timeout": 60,
                "cost_per_1m_input": 0.14,
                "cost_per_1m_output": 0.28,
            },
            "ollama": {
                "enabled": False,
                "model": "qwen3:32b",
                "base_url": "http://localhost:11434",
                "timeout": 300,
                "cost_per_1m_input": 0.0,
                "cost_per_1m_output": 0.0,
            },
            "mlx": {
                "enabled": False,
                "model": "mlx-community/Qwen3-32B-4bit",
                "cost_per_1m_input": 0.0,
                "cost_per_1m_output": 0.0,
            },
        },
        "chains": {
            "researcher": ["openrouter", "groq", "deepseek", "ollama"],
            "coder": ["deepseek", "groq", "openai", "openrouter", "ollama"],
            "critic": ["anthropic", "openai", "deepseek"],
            "writer": ["deepseek", "groq", "openai"],
            "default": ["deepseek", "groq", "openai", "openrouter"],
        },
        "circuit_breaker": {
            "failure_threshold": 3,
            "recovery_timeout": 60,
            "half_open_max_calls": 2,
        },
        "cost": {
            "max_cost_per_project": 10.0,
            "warn_threshold": 0.85,
            "track_yagni": True,
        },
        "memory": {
            "max_size_bytes": 3072,
            "file": "memory.md",
        },
        "logging": {"level": "INFO", "directory": "logs"},
        "outputs": {"directory": "outputs"},
    }


async def main() -> None:
    """Main entry point — parse args, load config, start REPL or headless."""
    parser = argparse.ArgumentParser(description="Brain Loader v5 — Lazy Conductor")
    parser.add_argument("goal", nargs="?", help="Goal to process (headless mode)")
    parser.add_argument("--config", "-c", help="Path to config YAML")
    parser.add_argument("--mode", choices=["local", "api", "hybrid"], help="Override execution mode")
    parser.add_argument("--ponytail", choices=["lite", "full", "ultra"], help="Override Ponytail mode")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-approve waves (headless)")
    args = parser.parse_args()

    config = load_config(args.config)

    # CLI overrides
    if args.mode:
        config["mode"] = args.mode
    if args.ponytail:
        config["ponytail"]["mode"] = args.ponytail

    setup_logging(config)
    logger = logging.getLogger("brain_loader")
    logger.info("Brain Loader v5 — Lazy Conductor starting...")
    logger.info("Mode: %s | Ponytail: %s", config["mode"], config["ponytail"]["mode"])

    # Initialize core components
    state_manager = StateManager(config)
    cost_tracker = CostTracker(config)
    planner = PonytailPlanner(config)
    engine = WaveEngine(config, cost_tracker)

    # Restore previous state if exists
    await state_manager.restore()

    if args.goal:
        # Headless mode
        logger.info("Headless mode — goal: %s", args.goal)
        result = await engine.run_headless(args.goal, planner, auto_approve=args.yes)
        print(result)
    else:
        # Interactive REPL
        repl = BrainREPL(config, planner, engine, cost_tracker, state_manager)
        await repl.run()


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        print("\n\nBrain Loader v5 — Clean shutdown via Ctrl+C")
        sys.exit(0)
    except Exception as e:
        logging.getLogger("brain_loader").critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
