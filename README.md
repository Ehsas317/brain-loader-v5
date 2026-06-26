# Brain Loader v5

**Multi-backend AI orchestration with Ponytail minimal-code philosophy and Trio structured concurrency.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Trio](https://img.shields.io/badge/concurrency-Trio-green.svg)](https://trio.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Ladder represents the convergence of six architectural visions:** The minimal-code philosophy of Ponytail, the structured concurrency of Trio (nurseries, cancel scopes, no orphaned tasks), and the best patterns from all four previous versions — v1/v2's core orchestration, v3's local MLX/Ollama hot-swapping, and v4's multi-backend hybrid/API failover chains.

## What is Ladder?

Ladder is an **AI orchestration framework** that coordinates multiple LLM providers to accomplish complex goals. The Ponytail decision ladder climbs rungs to skip work — saving 40-70% of API costs vs traditional dispatch.

## The Ponytail Decision Ladder

Before dispatching ANY specialists, Ladder climbs the Ponytail ladder:

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

## Quick Start

```bash
# Clone and install
git clone https://github.com/Ehsas317/ladder.git
cd ladder
pip install -r requirements.txt

# Set API keys and run
export DEEPSEEK_API_KEY="sk-..."
python main.py "Build a FastAPI scraper"
```

## Why "Ladder"?

The Ponytail decision ladder is the actual innovation here. It climbs rungs to skip work. We named it after the thing that makes it unique.

## License

MIT
