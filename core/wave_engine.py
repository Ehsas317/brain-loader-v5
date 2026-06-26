"""
WaveEngine — Brain planning + Trio nursery dispatch.

Manages wave-based execution:
1. Brain analyzes goal and plans tasks
2. Tasks are grouped into parallel waves
3. Each wave runs in a Trio nursery
4. Sequential tasks wait for parallel ones
5. Brain synthesizes all outputs
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import trio

from core.router import UniversalRouter
from core.cost_tracker import CostTracker

# FIX BUG-V5-006: Graceful import for PonytailPlanner with fallback
try:
    from core.ponytail_planner import PonytailPlanner, LadderResult
    PONYTAIL_AVAILABLE = True
except ImportError:
    PONYTAIL_AVAILABLE = False
    # Define minimal stub classes so the rest of the code works
    @dataclass
    class LadderResult:
        rung: int = 0
        skip_dispatch: bool = False
        answer: str = ""
        tokens_saved: int = 0
    
    class PonytailPlanner:
        async def climb_ladder(self, goal: str) -> LadderResult:
            return LadderResult()

logger = logging.getLogger("ladder.wave")


@dataclass
class Task:
    """A single specialist task."""
    id: str
    role: str
    prompt: str
    parallel: bool = True
    depends_on: list[str] = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)


@dataclass
class TaskResult:
    """Structured result from a single task execution."""
    task_id: str = ""
    role: str = ""
    content: str = ""
    provider: str = ""
    model: str = ""
    cost: float = 0.0
    tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.tokens


@dataclass
class WaveResult:
    """Result of executing a wave."""
    tasks: list[Task]
    responses: list[TaskResult] = field(default_factory=list)
    total_cost: float = 0.0
    total_tokens: int = 0
    elapsed_ms: float = 0.0
    yagni_saved: int = 0


class WaveEngine:
    """
    Wave-based task execution engine.
    
    Flow:
        Goal → Brain Plan → Waves → Trio Nursery Dispatch → Synthesis
    """

    def __init__(self, config: dict, cost_tracker: CostTracker) -> None:
        self.config = config
        self.cost_tracker = cost_tracker
        self.router = UniversalRouter(config)
        self.outputs_dir = Path(config.get("outputs", {}).get("directory", "outputs"))
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    async def run_headless(
        self,
        goal: str,
        planner: PonytailPlanner,
        auto_approve: bool = False,
    ) -> str:
        """
        Run brain in headless mode.
        
        Args:
            goal: The user's goal
            planner: Ponytail planner instance
            auto_approve: Skip HITL approval
        
        Returns:
            Final synthesized output
        """
        logger.info("🧠 Processing goal: %s", goal[:80])

        # Step 1: Climb the Ponytail ladder
        ladder_result = await planner.climb_ladder(goal)
        
        if ladder_result.skip_dispatch:
            logger.info("🐴 Ponytail ladder stopped at rung %d — direct answer", ladder_result.rung)
            return self._format_direct_answer(goal, ladder_result)

        # Step 2: Brain plans the wave
        logger.info("🐴 Ponytail ladder climbed to rung %d", ladder_result.rung)
        tasks = await self._plan_wave(goal, ladder_result)
        
        if not tasks:
            return f"# Ladder\n\n**Goal:** {goal}\n\nNo tasks needed — direct answer.\n"

        # Step 3: HITL approval (unless auto_approve)
        if not auto_approve:
            self._show_wave_for_approval(tasks)
            # In headless mode without --yes, we auto-approve
            logger.info("Headless mode: auto-approving wave")

        # Step 4: Dispatch wave
        logger.info("🌊 Dispatching %d task(s) in %s mode...", len(tasks), self.config["mode"])
        wave_result = await self._dispatch_wave(tasks)

        # Step 5: Brain synthesizes
        synthesis = await self._synthesize(goal, wave_result)

        # Step 6: Save output
        output_path = self._save_output(goal, synthesis, wave_result)

        # Summary
        summary = (
            f"\n{'='*60}\n"
            f"  Ladder — Complete\n"
            f"  Goal: {goal[:60]}{'...' if len(goal) > 60 else ''}\n"
            f"  Tasks: {len(tasks)} | Cost: ${wave_result.total_cost:.4f}\n"
            f"  Tokens: {wave_result.total_tokens:,}\n"
            f"  Saved: {output_path}\n"
            f"{'='*60}\n"
        )
        logger.info(summary)
        return synthesis + "\n\n" + summary

    async def _plan_wave(self, goal: str, ladder_result: LadderResult) -> list[Task]:
        """
        Brain plans tasks based on goal and Ponytail ladder result.
        
        Uses the brain role in the router for actual AI-based planning
        when available, with keyword-based fallback for offline operation.
        """
        tasks: list[Task] = []
        mode = self.config.get("ponytail", {}).get("mode", "lite")

        # FIX BUG-V5-004: Try AI-based planning first via the brain role
        try:
            brain_plan = await self.router.route(
                role="brain",
                prompt=self._build_planning_prompt(goal, ladder_result),
                max_tokens=2048,
                temperature=0.7,
            )
            if brain_plan.content and not brain_plan.error:
                parsed_tasks = self._parse_brain_plan(brain_plan.content, goal)
                if parsed_tasks:
                    logger.info("🧠 Brain planned %d tasks via LLM", len(parsed_tasks))
                    return parsed_tasks
        except Exception as e:
            logger.debug("AI planning unavailable, using rule-based fallback: %s", e)

        # Fallback: keyword-based task decomposition
        logger.info("Using rule-based planner (AI planning unavailable)")
        goal_lower = goal.lower()

        # Research tasks
        if any(kw in goal_lower for kw in ["research", "find", "search", "compare", "analyze", "what is", "how to"]):
            tasks.append(Task(
                id="T1",
                role="researcher",
                prompt=f"Research and summarize key findings for: {goal}\n\nFocus on actionable, specific information.",
                parallel=True,
            ))

        # Code tasks
        if any(kw in goal_lower for kw in ["build", "code", "write", "create", "implement", "scraper", "api", "app", "script", "function"]):
            # Merge coder tasks in Full/Ultra mode
            if mode in ("full", "ultra") and len(tasks) > 0:
                tasks.append(Task(
                    id="T2",
                    role="coder",
                    prompt=f"Write minimal, working code for: {goal}\n\nUse stdlib where possible. Mark shortcuts with # ponytail: comments.",
                    parallel=True,
                ))
            else:
                tasks.append(Task(
                    id="T2",
                    role="coder",
                    prompt=f"Write complete, production-ready code for: {goal}\n\nInclude error handling and type hints.",
                    parallel=True,
                ))

        # If no specific task type detected, create a general task
        if not tasks:
            tasks.append(Task(
                id="T1",
                role="default",
                prompt=goal,
                parallel=True,
            ))

        # Critic task (sequential — reviews outputs)
        if len(tasks) > 1:
            tasks.append(Task(
                id=f"T{len(tasks)+1}",
                role="critic",
                prompt=f"Review the outputs for: {goal}\n\nCheck for: bugs, security issues, edge cases, and improvements.",
                parallel=False,
                depends_on=[t.id for t in tasks if t.parallel],
            ))

        return tasks

    def _build_planning_prompt(self, goal: str, ladder_result: LadderResult) -> str:
        """Build a prompt for the brain to plan tasks."""
        return (
            f"You are a task planner. Given the user's goal, break it down into "
            f"specialist tasks that can run in parallel or sequentially.\n\n"
            f"User Goal: {goal}\n\n"
            f"Available roles: researcher, coder, writer, critic\n\n"
            f"Output a JSON list of tasks with id, role, prompt, and parallel (boolean). "
            f"Tasks with parallel=true can run simultaneously. "
            f"The critic role should always be parallel=false and depend on other tasks.\n\n"
            f"Example output format:\n"
            f'[{{"id": "T1", "role": "researcher", "prompt": "Research...", "parallel": true}}, ...]\n'
        )

    def _parse_brain_plan(self, content: str, goal: str) -> list[Task] | None:
        """Parse task list from brain's planning output."""
        try:
            # Try to extract JSON from the response
            json_start = content.find("[")
            json_end = content.rfind("]")
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end + 1])
                tasks = []
                for item in data:
                    tasks.append(Task(
                        id=item.get("id", f"T{len(tasks)+1}"),
                        role=item.get("role", "default"),
                        prompt=item.get("prompt", goal),
                        parallel=item.get("parallel", True),
                        depends_on=item.get("depends_on", []),
                    ))
                return tasks if tasks else None
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("Failed to parse brain plan: %s", e)
        return None

    async def _dispatch_wave(self, tasks: list[Task]) -> WaveResult:
        """
        Dispatch tasks using Trio nursery.
        
        Parallel tasks run together in a nursery.
        Sequential tasks wait for their dependencies.
        """
        result = WaveResult(tasks=tasks)
        start_time = time.perf_counter()
        
        # Split into parallel and sequential
        parallel_tasks = [t for t in tasks if t.parallel]
        sequential_tasks = [t for t in tasks if not t.parallel]

        # Phase 1: Parallel tasks via nursery
        parallel_results: dict[str, TaskResult] = {}

        if parallel_tasks:
            wave_timeout = self.config.get("trio", {}).get("wave_timeout", 300)
            task_timeout = self.config.get("trio", {}).get("task_timeout", 120)

            with trio.move_on_after(wave_timeout):
                async with trio.open_nursery() as nursery:
                    for task in parallel_tasks:
                        nursery.start_soon(
                            self._run_task_with_timeout,
                            task,
                            task_timeout,
                            parallel_results,
                        )

        # Collect parallel results
        for task in parallel_tasks:
            if task.id in parallel_results:
                tr = parallel_results[task.id]
                result.responses.append(tr)
                result.total_cost += tr.cost
                result.total_tokens += tr.tokens

        # Phase 2: Sequential tasks (depend on parallel results)
        context = self._build_context(parallel_results)
        
        for task in sequential_tasks:
            task.kwargs["context"] = context
            tr = await self._run_task(task)
            result.responses.append(tr)
            result.total_cost += tr.cost
            result.total_tokens += tr.tokens

        result.elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # Update cost tracker
        await self.cost_tracker.add_cost(result.total_cost, result.total_tokens)

        return result

    async def _run_task_with_timeout(
        self,
        task: Task,
        timeout: float,
        results: dict[str, TaskResult],
    ) -> None:
        """Run a single task with timeout."""
        try:
            # FIX BUG-V5-003: Use trio.fail_after for hard cancellation
            # instead of move_on_after which allows the task to continue.
            with trio.fail_after(timeout):
                results[task.id] = await self._run_task(task)
        except trio.TooSlowError:
            logger.error("Task %s timed out after %.1fs", task.id, timeout)
            results[task.id] = TaskResult(
                task_id=task.id,
                role=task.role,
                error=f"Timeout after {timeout}s",
            )
        except Exception as e:
            logger.error("Task %s failed: %s", task.id, e)
            results[task.id] = TaskResult(
                task_id=task.id,
                role=task.role,
                error=str(e),
            )

    async def _run_task(self, task: Task) -> TaskResult:
        """Execute a single task through the router."""
        logger.info("  %s %s → dispatching...", task.id, task.role)
        
        response = await self.router.route(
            role=task.role,
            prompt=task.prompt,
            **task.kwargs,
        )

        return TaskResult(
            task_id=task.id,
            role=task.role,
            content=response.content,
            provider=response.provider,
            model=response.model,
            cost=response.cost,
            tokens=response.total_tokens,
            latency_ms=response.latency_ms,
            error=response.error,
        )

    async def _synthesize(self, goal: str, wave_result: WaveResult) -> str:
        """
        Synthesize all task outputs into a final answer.
        
        Uses the brain role for actual LLM synthesis when available,
        with structured concatenation as fallback.
        """
        # FIX BUG-V5-005: Try LLM-based synthesis first
        try:
            context = self._build_synthesis_context(goal, wave_result)
            brain_response = await self.router.route(
                role="brain",
                prompt=context,
                max_tokens=4096,
                temperature=0.7,
            )
            if brain_response.content and not brain_response.error:
                logger.info("🧠 Synthesized via LLM brain")
                return brain_response.content
        except Exception as e:
            logger.debug("LLM synthesis unavailable, using fallback: %s", e)

        # Fallback: structured concatenation
        logger.info("Using structured concatenation (LLM synthesis unavailable)")
        sections = [f"# Ladder — Final Answer\n"]
        sections.append(f"**Goal:** {goal}\n")

        # Group by role
        by_role: dict[str, list[TaskResult]] = {}
        for tr in wave_result.responses:
            by_role.setdefault(tr.role, []).append(tr)

        for role, task_results in by_role.items():
            sections.append(f"\n## {role.title()}\n")
            for tr in task_results:
                if tr.error:
                    sections.append(f"*⚠️ Error: {tr.error}*\n")
                elif tr.content:
                    sections.append(tr.content)
                    sections.append("")

        # Add metadata
        sections.append(f"\n---\n")
        sections.append(f"*Tokens: {wave_result.total_tokens:,} | Cost: ${wave_result.total_cost:.4f} | Time: {wave_result.elapsed_ms/1000:.1f}s*\n")

        return "\n".join(sections)

    def _build_synthesis_context(self, goal: str, wave_result: WaveResult) -> str:
        """Build context for LLM synthesis."""
        parts = [f"Synthesize the following task outputs into a coherent final answer for: {goal}\n"]
        for tr in wave_result.responses:
            parts.append(f"\n### {tr.role.upper()} — {tr.task_id}\n")
            if tr.error:
                parts.append(f"[Error: {tr.error}]\n")
            else:
                parts.append(tr.content[:2000])
        parts.append("\n\nProvide a unified, well-structured final answer.")
        return "\n".join(parts)

    def _build_context(self, results: dict[str, TaskResult]) -> str:
        """Build context string from parallel task outputs for sequential tasks."""
        parts = []
        for task_id, tr in results.items():
            if tr.content:
                parts.append(f"### {tr.role.title()} Output:\n{tr.content[:2000]}")
        return "\n\n".join(parts)

    def _save_output(self, goal: str, synthesis: str, wave_result: WaveResult) -> Path:
        """Save final output to file."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_goal = "".join(c if c.isalnum() else "_" for c in goal[:30])
        filename = f"output_{timestamp}_{safe_goal}.md"
        path = self.outputs_dir / filename
        
        path.write_text(synthesis, encoding="utf-8")
        return path

    def _show_wave_for_approval(self, tasks: list[Task]) -> None:
        """Display planned wave for HITL approval."""
        print("\n╭── Brain's Proposed Wave ──")
        print(f"│ ID  Role        Parallel")
        for t in tasks:
            parallel_icon = "✓ Yes" if t.parallel else "⏳ After"
            preview = t.prompt[:40] + "..." if len(t.prompt) > 40 else t.prompt
            print(f"│ {t.id:<4} {t.role:<11} {parallel_icon}")
            print(f"│     └─ {preview}")
        print("╰───────────────────────────\n")

    def _format_direct_answer(self, goal: str, ladder_result: LadderResult) -> str:
        """Format a direct answer when Ponytail ladder stops early."""
        return (
            f"# Ladder — Direct Answer\n\n"
            f"**Goal:** {goal}\n\n"
            f"{ladder_result.answer or 'No additional processing needed.'}\n\n"
            f"---\n"
            f"*Ponytail ladder stopped at rung {ladder_result.rung}*\n"
            f"*Tokens saved: {ladder_result.tokens_saved}*\n"
        )

    async def close(self) -> None:
        """Cleanup resources."""
        await self.router.close_all()
