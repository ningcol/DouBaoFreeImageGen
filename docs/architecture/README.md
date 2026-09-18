# Current Architecture

Architecture documents answer one question:

> If a new agent joined the project today, how is the system structured now?

## Include

- major modules/domains;
- dependency direction;
- data ownership;
- API boundaries;
- state ownership;
- infrastructure boundaries;
- important current invariants.

## Exclude

- long historical narratives;
- rejected alternatives;
- obsolete architecture states.

Those belong in durable decisions.

## Drift policy

Architecture docs may describe current facts that can become stale. Where important constraints are mechanically checkable, prefer converting them into architecture fitness functions/CI gates over relying on prose alone.

Project-owned executable invariants are registered in `.pact/fitness.toml` and run with:

```bash
python scripts/pact/pact.py fitness
```

PACT defines the execution contract, not the architecture style.
