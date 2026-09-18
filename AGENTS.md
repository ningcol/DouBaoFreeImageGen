# Project Agent Guide

This repository uses PACT (Project AI Control Plane).

## Core rules

1. Preserve confirmed Product Truth.
2. Acquire sufficient context before changing behavior; do not read everything by default.
3. AI owns implementation decisions unless they change product meaning, permissions/policy, irreversible outcomes, material risk, or cost.
4. Distinguish what should be true from what the system currently does.
5. Verify observable outcomes before claiming completion.
6. Reconcile drift by authority; never make Product Truth follow code automatically.
7. Report owner-facing results in product/business language by default.

## Knowledge router

- Governance: `docs/governance/`
- Product Truth and vocabulary: `docs/product/`
- Current architecture: `docs/architecture/`
- Durable engineering rationale: `.agents/decisions/`
- Active/completed change intent: `docs/changes/`
- Drift: `docs/drift/`
- Reusable procedures: `.agents/skills/`
- Adoption readiness: `.pact/baseline.toml`

## Decision boundary

Do not ask the owner to choose ordinary implementation mechanisms.

Escalate only when a decision changes user-observable behavior, business/data meaning, permissions/policy, irreversible outcomes, or material risk/cost.

## Completion boundary

"Done" requires appropriate evidence and convergence, not only code changes or green tests.

## Baseline boundary

`pact init` creates structure; it does not certify project knowledge.

If `pact readiness` reports pending baseline reviews, treat those areas as potentially incomplete rather than inventing missing truth.

## Owner communication

Before owner-facing output, read the validated Owner Profile:

```bash
python scripts/pact/pact.py owner --json
```

Honor its language, technical depth, consequence-first translation, and progressive-disclosure preferences.
