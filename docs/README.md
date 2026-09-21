# BKTSTR documentation

BKTSTR is independent of the Bailey Fund. These documents describe the software,
research contracts, and implementation sequence, not a fund portfolio.

| Document | Purpose |
| --- | --- |
| [Project overview](../README.md) | Purpose, current capabilities, and setup |
| [Agent instructions](../AGENTS.md) | Constraints for future agent work |
| [Research runbook](../AGENT_BACKTEST_RUNBOOK.md) | How to conduct and report an experiment |
| [System design](BKTSTR_SYSTEM_MANUAL.md) | Existing foundation and target architecture |
| [Implementation plan](IMPLEMENTATION_PLAN.md) | Ordered work, interfaces, verification, and acceptance gates |
| [API reference](API_REFERENCE.md) | Implemented HTTP behavior |
| [Strategy configuration](STRATEGY_CONFIGURATION.md) | Local JSON/Python compilation and supported numerical filters |
| [Macro evidence](MACRO_EVIDENCE.md) | Point-in-time selection, replay, and verified BLS adapter coverage |
| [Project status report](PROJECT_STATUS.md) | Standalone usefulness, personal research fit, and remaining structural gaps |
| [Trade idea containers](TRADE_IDEA_CONTAINERS.md) | Adopted event research structure, reusable theses, study variants, and linked policies |
| [Research foundation plan](plans/2026-09-20-trade-idea-research.md) | Planned RF-A through RF-K implementation before Jev Task 3 |
| [Cache architecture](CACHE_ARCHITECTURE.md) | Data reuse and reproducibility boundaries |
| [Cache integration](../integration/INTEGRATION_GUIDE.md) | Existing code integration points |
| [Local credentials](development/local-credentials.md) | Existing Windows key helper |
| [Contributing](../CONTRIBUTING.md) | Development and review |
| [Releases](development/releases.md) | Deployment and release verification |
| [Changelog](../CHANGELOG.md) | Concise compatibility record |

The system design, implementation plan, and linked research foundation plan form
the forward roadmap. The research foundation milestone now precedes Jev Task 3.
Proposed interfaces are labelled as planned; they are not runnable API contracts.
Current source, OpenAPI, and authenticated capabilities define what can run today.

Superseded roadmaps, release snapshots, session workarounds, and implementation
journals have been removed from the active documentation. Git history retains
their historical record. Do not restore them as current instructions.
