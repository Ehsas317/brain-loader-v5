# Brain Loader v5 — Lazy Conductor

**Multi-backend AI orchestration with Ponytail minimal-code philosophy and Trio structured concurrency.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Trio](https://img.shields.io/badge/concurrency-Trio-green.svg)](https://trio.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **v5 represents the convergence of six architectural visions:** The minimal-code philosophy of Ponytail (53.5k stars), the structured concurrency of Trio (nurseries, cancel scopes, no orphaned tasks), and the best patterns from all four previous Brain Loader versions — v1/v2's core orchestration, v3's local MLX/Ollama hot-swapping, and v4's multi-backend hybrid/API failover chains.

## What is Brain Loader?

Brain Loader is an **AI orchestration framework** that coordinates multiple LLM providers to accomplish complex goals. Think of it as a conductor for AI specialists:

- **Brain** analyzes your goal and plans the work
- **Specialists** (researcher, coder, critic) execute in parallel
- **Auto-failover** ensures tasks complete even if providers go down
- **Ponytail ladder** skips unnecessary work, saving 40-70% of API costs

## Key Features

1. **Ponytail Decision Ladder** — Skip unnecessary work. Direct answers for simple goals. Stdlib hints for common patterns.
2. **Trio Structured Concurrency** — No orphaned tasks. Clean cancellation. Exception groups. Parent-child task trees.
3. **Hybrid Mode** — Keep your local brain (quality planning) but offload execution to cheap APIs (speed).
4. **100% API Mode** — Run anywhere, zero RAM requirements, 10-50x faster.
5. **100% Local Mode** — Zero cost, offline-capable, privacy-preserving (MLX/Ollama).
6. **Auto-Failover** — Never get stuck. Circuit breakers per provider. If one fails, another picks up.
7. **Cost Control** — Track every penny. YAGNI savings tracking. Warn before overspending.
8. **Terminal-Native REPL** — Interactive approval, live status, markdown rendering.
9. **httpx-Native** — All HTTP providers use the same async client. No SDK dependencies.

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Ehsas317/brain-loader-v5.git
cd brain-loader-v5

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate    # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API keys
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
# See config.yaml for all provider options

# 5. Run!
python main.py                              # Interactive REPL
python main.py "Build a FastAPI scraper"    # Headless mode
```

## Configuration

All configuration is in `config.yaml`:

```yaml
mode: hybrid                    # local | api | hybrid

ponytail:
  mode: lite                   # lite | full | ultra
  ladder:
    rung_1_brain_direct: true  # Direct answers for simple Q/A
    rung_2_memory_reuse: true  # Check memory for previous solutions
    rung_3_stdlib_first: false # Prefer built-in solutions

providers:
  deepseek:
    enabled: true
    api_key_env: "DEEPSEEK_API_KEY"
    model: deepseek-chat

  ollama:
    enabled: false             # Set true for local mode
    model: qwen3:32b
```

## The Ponytail Decision Ladder

Before dispatching ANY specialists, v5 climbs the Ponytail ladder:

```
User Goal
    │
    ▼
Rung 1: Simple Q/A? → Direct answer, $0 cost
    │
    ▼
Rung 2: In memory? → Return previous synthesis, $0 cost
    │
    ▼
Rung 3: Native solution? → Return stdlib hint, $0 cost
    │
    ▼
Rung 4: Merge tasks? → Fewer API calls
    │
    ▼
Rung 5: Minimum viable wave → Specialists write minimum code
```

| Mode | Aggressiveness | Typical Savings |
|------|---------------|-----------------|
| **Lite** | Conservative | 10-20% tokens |
| **Full** | Merge tasks, stdlib first | 40-50% tokens |
| **Ultra** | Maximum laziness | 60-70% tokens |

## Architecture

```
Brain Loader v5 — Lazy Conductor
│
├── Brain REPL (Rich TUI)
│   ├── HITL approval
│   ├── Live task table
│   └── /ponytail mode toggle
│
├── Ponytail Ladder (Decision Tree)
│   ├── Rung 1-5 checks
│   ├── Skip unnecessary dispatch
│   └── Merge tasks when possible
│
├── Trio Wave Engine
│   ├── Structured task trees
│   ├── No orphaned API calls
│   └── Clean Ctrl+C cancellation
│
└── Backend Layer
    ├── API: Anthropic, OpenAI, OpenRouter, Groq, Gemini, DeepSeek
    └── Local: MLX (Apple Silicon), Ollama (Any OS)
```

## Provider Chains

Each role has its own failover chain:

| Role | Default Chain |
|------|--------------|
| **Researcher** | OpenRouter → Groq → DeepSeek → Ollama |
| **Coder** | DeepSeek → Groq → OpenAI → OpenRouter → Ollama |
| **Critic** | Anthropic → OpenAI → DeepSeek |
| **Default** | DeepSeek → Groq → OpenAI → OpenRouter |

If a provider fails, the next one picks up instantly. Circuit breakers prevent hammering failing providers.

## Cost Estimation

| Mode | 50-Task Project | Cost | Time |
|------|----------------|------|------|
| v4 Hybrid | 50 tasks | ~$2.20 | ~30 min |
| v5 Lite | 40 tasks | ~$1.80 | ~25 min |
| v5 Full | 25 tasks | ~$1.10 | ~18 min |
| v5 Ultra | 15 tasks | ~$0.60 | ~12 min |

## Why Trio Over asyncio?

| Feature | asyncio (v4) | Trio (v5) |
|---------|-------------|-----------|
| Orphaned tasks | Possible with `create_task` | Impossible — nurseries enforce cleanup |
| Cancellation | Messy `CancelledError` | Clean `CancelScope` |
| Ctrl+C | May leave tasks running | Guaranteed clean shutdown |
| Exception handling | `gather()` swallows errors | Exception groups preserve context |

## Project Structure

```
brain-loader-v5/
├── main.py                    # Entry point (Trio event loop)
├── config.yaml               # All configuration
├── requirements.txt          # Core dependencies
├── requirements_local.txt    # + MLX for Apple Silicon
├── core/
│   ├── router.py             # UniversalRouter with failover chains
│   ├── wave_engine.py        # Brain planning + Trio dispatch
│   ├── cost_tracker.py       # Session cost + YAGNI savings
│   ├── ponytail_planner.py   # Decision ladder engine
│   └── providers/            # All LLM provider implementations
├── tui/
│   └── repl.py               # Interactive terminal REPL
├── utils/
│   ├── telegram_notify.py    # Cost notifications
│   └── state_manager.py      # Crash recovery
├── .github/
│   └── FUNDING.yml           # Sponsor this project
├── docs/
│   └── FUNDING-v4-legacy.yml # v4 funding reference
├── LICENSE                   # MIT License
├── CONTRIBUTING.md           # Contribution guidelines
└── CHANGELOG.md              # Version history
```

## Environment Variables

```bash
# Required for API/Hybrid mode
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GROQ_API_KEY="gsk_..."
export GOOGLE_API_KEY="..."
export OPENROUTER_API_KEY="sk-or-..."

# Optional
export BRAIN_LOADER_MODE="hybrid"    # Override config mode
export TELEGRAM_BOT_TOKEN="..."      # Notifications
export TELEGRAM_CHAT_ID="..."
```

## Troubleshooting

**"All providers in chain failed"**
- Check API keys: `echo $OPENAI_API_KEY`
- Test provider directly with curl
- Check circuit breaker status in logs

**"No local fallback available"**
- Ensure Ollama is running: `ollama serve`
- Check model is pulled: `ollama list`

**High costs**
- Toggle `/ponytail` in REPL to Full/Ultra mode
- Use cheaper providers (DeepSeek, Groq free tier)
- Switch to `mode: "local"` for testing

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- **Ponytail** — The minimal-code philosophy (53.5k stars)
- **Trio** — Structured concurrency done right
- **Contributors**: Qwen (async engine), Manus (enterprise failover), Claude (structured JSON), Kimi (synthesis), and the entire Brain Loader community.

---

**Happy building — lazily.**
