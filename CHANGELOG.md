# Changelog

All notable changes to Brain Loader will be documented in this file.

## [5.0.0] — 2025-01-15

### Added
- **Ponytail Decision Ladder** — Skip unnecessary work. 5-rung decision tree before any API calls.
- **Trio Structured Concurrency** — Replaced asyncio with Trio for no orphaned tasks, clean cancellation, and exception groups.
- **YAGNI Savings Tracking** — Track tokens and money saved by Ponytail ladder decisions.
- **httpx-Native Providers** — All HTTP providers use httpx.AsyncClient. No SDK dependencies.
- **Circuit Breaker Pattern** — Per-provider circuit breakers with CLOSED/OPEN/HALF_OPEN states.
- **Cost Warning System** — Warn at 85% of budget, hard stop at limit.
- **Memory System** — Rolling 3KB context with crash recovery.
- **State Manager** — Persistent session state across restarts.
- **Telegram Notifications** — Cost and savings alerts after each wave.
- **RPM Throttling** — Built-in rate limit handling for Groq free tier.

### Changed
- **Architecture**: From asyncio fire-and-forget to Trio nurseries with guaranteed task cleanup.
- **Provider Chain**: Configurable per-role chains with intelligent failover.
- **Router**: UniversalRouter manages all provider routing and error classification.

### Fixed
- **Orphaned API Calls**: Trio nurseries guarantee no dangling HTTP connections.
- **Ctrl+C Handling**: Clean shutdown with `trio.move_on_after()` cancel scopes.
- **Exception Handling**: Exception groups preserve all failure contexts.

### Migration from v4
See [Migration Guide](docs/migration-v4-to-v5.md) (coming soon).

## [4.0.0] — 2024-08-01

### Added
- Multi-backend hybrid mode (local + API)
- 100% API mode with parallel dispatch
- Per-role provider chains
- Circuit breaker pattern
- Cost tracking per run
- Budget warnings and hard stops
- Terminal-native REPL with Rich
- Human-in-the-loop approval
- Live task status dashboard
- Structured JSON brain output
- Wave-based execution
- Per-backend locks for VRAM protection
- Rolling memory context
- Headless mode

## [3.0.0] — 2024-04-01

### Added
- Local MLX backend (Apple Silicon)
- Local Ollama backend
- Hot-swapping between local models
- Local lock system for VRAM protection

## [2.0.0] — 2024-02-01

### Added
- Async parallel task execution
- Multiple API provider support
- Basic cost tracking

## [1.0.0] — 2024-01-01

### Added
- Initial release
- Single API provider support
- Basic task orchestration
