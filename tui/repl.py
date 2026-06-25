#!/usr/bin/env python3
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  LADDER — FILE: tui/repl.py                                             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# PROJECT:    Ladder (formerly Brain Loader v5)
# REPO:       https://github.com/Ehsas317/ladder
# WHAT:       The Ponytail decision ladder is the actual innovation here.
#             It climbs rungs to skip work. Named after the thing that makes
#             it unique.
#
# THIS FILE:
#   Interactive terminal REPL for Ladder. Rich TUI with live status
#   dashboard, HITL approval, and command interface.
#
# HOW TO USE LADDER:
#   1. Install:    pip install -r requirements.txt
#   2. Configure:  Edit config.yaml with your API tokens
#   3. Run:        python main.py "Your project goal"
#
# ═══════════════════════════════════════════════════════════════════════════
#

"""
LadderREPL — Rich terminal REPL with live status dashboard.

Commands:
    /status    — Show provider status and cost
    /memory    — Show/edit memory.md
    /mode      — Toggle execution mode
    /cost      — Show cost breakdown
    /ponytail  — Toggle Ponytail mode
    /save      — Save current session
    /exit      — Quit
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import trio

from core.wave_engine import WaveEngine
from core.ponytail_planner import PonytailPlanner
from core.cost_tracker import CostTracker
from utils.state_manager import StateManager

logger = logging.getLogger("ladder.repl")


class LadderREPL:
    """
    Ladder Interactive Terminal REPL

    Provides an interactive command-line interface to monitor
    and control the Ladder orchestrator.

    Usage:
        repl = LadderREPL(config, planner, engine, cost_tracker, state_manager)
        await repl.run()
    """

    def __init__(
        self,
        config: dict,
        planner: PonytailPlanner,
        engine: WaveEngine,
        cost_tracker: CostTracker,
        state_manager: StateManager,
    ) -> None:
        self.config = config
        self.planner = planner
        self.engine = engine
        self.cost_tracker = cost_tracker
        self.state_manager = state_manager
        self.mode = config["mode"]
        self.ponytail_mode = config.get("ponytail", {}).get("mode", "lite")
        self.running = True

    async def run(self) -> None:
        """Main REPL loop."""
        self._print_banner()
        
        while self.running:
            try:
                user_input = await self._get_input("\nYou > ")
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                else:
                    await self._process_goal(user_input)
                    
            except EOFError:
                print("\nGoodbye!")
                break
            except KeyboardInterrupt:
                print("\nUse /exit to quit.")
            except Exception as e:
                logger.error("REPL error: %s", e)
                print(f"Error: {e}")

    async def _process_goal(self, goal: str) -> None:
        """Process a user goal."""
        print(f"\n🧠 Processing: {goal[:60]}{'...' if len(goal) > 60 else ''}")
        
        if self.cost_tracker.hard_stop_active:
            print("⚠️  Cost limit reached. Use /cost to check.")
            return
        
        result = await self.engine.run_headless(goal, self.planner, auto_approve=False)
        print(result)

    async def _handle_command(self, cmd: str) -> None:
        """Handle REPL commands."""
        parts = cmd.split()
        command = parts[0].lower()
        args = parts[1:]

        match command:
            case "/status":
                self._show_status()
            case "/memory":
                await self._show_memory()
            case "/mode":
                await self._toggle_mode(args)
            case "/cost":
                self._show_cost()
            case "/ponytail":
                await self._toggle_ponytail()
            case "/save":
                await self.state_manager.save()
                print("💾 Session saved.")
            case "/exit" | "/quit":
                print("👋 Goodbye!")
                self.running = False
            case "/help":
                self._print_help()
            case _:
                print(f"Unknown command: {command}. Type /help for available commands.")

    def _print_banner(self) -> None:
        """Print the welcome banner."""
        banner = f"""
╭─────────────────── Ladder ─────────────────────╮
│  Lazy Conductor — Multi-Backend AI Orchestration │
│  Mode: {self.mode.upper():6}  ·  Ponytail: {self.ponytail_mode:5}                      │
│  Providers: {' · '.join(self.engine.router.available_providers):25}  │
│                                                  │
│  Commands: /status  /memory  /mode  /cost        │
│            /ponytail  /save  /help  /exit        │
╰──────────────────────────────────────────────────╯
"""
        print(banner)

    def _print_help(self) -> None:
        """Print help text."""
        help_text = """
Commands:
  /status    — Show provider status (available, circuit state)
  /memory    — Show memory.md contents
  /mode      — Toggle: local → api → hybrid
  /cost      — Show cost breakdown and YAGNI savings
  /ponytail  — Toggle: lite → full → ultra
  /save      — Save session state
  /exit      — Quit Ladder
  /help      — Show this help

Any other input is treated as a goal for the brain to process.
"""
        print(help_text)

    def _show_status(self) -> None:
        """Show provider status table."""
        print("\n╭── Provider Status ──")
        for name, provider in self.engine.router.providers.items():
            available = "✓" if provider.is_available else "✗"
            circuit = provider.circuit.state.value
            model = provider.model[:25] if provider.model else "N/A"
            print(f"│ {available} {name:<12} {circuit:<12} {model}")
        print("╰─────────────────────")

    async def _show_memory(self) -> None:
        """Show memory.md contents."""
        memory_path = Path(self.config.get("memory", {}).get("file", "memory.md"))
        if memory_path.exists():
            content = memory_path.read_text(encoding="utf-8")
            print(f"\n--- {memory_path} ---")
            print(content[:2000])
            if len(content) > 2000:
                print(f"... ({len(content)} chars total)")
        else:
            print(f"No memory file at {memory_path}")
            print("Memory will be created automatically.")

    async def _toggle_mode(self, args: list[str]) -> None:
        """Toggle execution mode."""
        if args:
            new_mode = args[0].lower()
            if new_mode in ("local", "api", "hybrid"):
                self.mode = new_mode
                self.config["mode"] = new_mode
                print(f"Mode set to: {new_mode}")
                return
        
        modes = ["local", "api", "hybrid"]
        current_idx = modes.index(self.mode) if self.mode in modes else 0
        self.mode = modes[(current_idx + 1) % len(modes)]
        self.config["mode"] = self.mode
        print(f"Mode: {self.mode}")

    def _show_cost(self) -> None:
        """Show cost information."""
        print(f"\n╭── Cost Summary ──")
        print(f"│ {self.cost_tracker.format_summary()}")
        yagni = self.cost_tracker.format_yagni()
        if yagni:
            print(f"│ {yagni}")
        print("╰──────────────────")

    async def _toggle_ponytail(self) -> None:
        """Toggle Ponytail mode."""
        modes = ["lite", "full", "ultra"]
        current_idx = modes.index(self.ponytail_mode) if self.ponytail_mode in modes else 0
        self.ponytail_mode = modes[(current_idx + 1) % len(modes)]
        self.config["ponytail"]["mode"] = self.ponytail_mode
        self.planner.mode = self.ponytail_mode
        print(f"Ponytail mode: {self.ponytail_mode}")

    async def _get_input(self, prompt: str) -> str:
        """Get user input (Trio-friendly wrapper)."""
        return await trio.to_thread.run_sync(input, prompt)
