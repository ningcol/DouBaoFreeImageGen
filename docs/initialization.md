# PACT Initialization for Existing Projects

PACT adoption is a baseline exercise, not a template-copy operation.

## Goal

Create a trustworthy starting point from which future agents can work without reconstructing the entire project history.

## Phase 0 — Reviewable adoption point

Use a clean commit/branch/worktree so PACT adoption is independently reviewable.

## Phase 1 — Repository discovery

Observe:

- repository/module layout;
- runtime entry points;
- routes;
- schemas/contracts;
- tests;
- CI/build;
- existing docs;
- relevant Git history.

Output is **observed fact**, not automatically product truth.

## Phase 2 — Vocabulary baseline

Extract core business concepts and aliases across owner language, UI, code, database, and historical docs.

Mark candidate terminology as observed until confirmed.

## Phase 3 — Product truth baseline

Capture only durable, high-value rules that are:

- cross-module or long-lived;
- easy for agents to misunderstand;
- expensive to violate;
- supported by an authoritative product source or owner confirmation.

Do not derive normative rules from code alone.

## Phase 4 — Architecture baseline

Document how the project is structured **now**.

Do not reconstruct every historical architecture state.

## Phase 5 — Durable decision baseline

Backfill only decisions still important to future work: auth boundaries, data ownership, API layering, state ownership, deployment model, etc.

## Phase 6 — Truth ownership matrix

Declare which artifact answers which category of question.

## Phase 7 — Owner profile

Configure default owner-facing vocabulary and how technical consequences should be translated.

## Phase 8 — Verification baseline

Record the verification capabilities that actually exist today: builds, tests, browser/E2E, visual checks, schema checks, CI.

Do not pretend missing verification exists.

## Phase 9 — Known drift register

Record known inconsistencies that will not be repaired immediately.

This prevents future agents from repeatedly rediscovering or silently "fixing" accepted debt.

## Phase 10 — Baseline review and readiness

`pact init` creates structure. It does **not** certify project knowledge.

Initialization creates `.pact/baseline.toml` with review areas initially marked `pending`:

- vocabulary;
- Product Truth;
- architecture;
- truth ownership;
- Owner Profile;
- verification reality;
- Known Drift review.

After each area has actually been inspected, mark it `reviewed` or explicitly `not_applicable`.

Check state with:

```bash
python scripts/pact/pact.py readiness
```

Stages:

```text
scaffolded
→ foundation-valid
→ baseline-in-progress
→ pact-ready
```

Only `pact-ready` means the project has an explicitly reviewed starting baseline.

For projects that want this as a gate:

```bash
python scripts/pact/pact.py readiness --require-ready
```

## Optional continuous CI

PACT can create a separate GitHub Actions workflow without modifying existing workflows:

```bash
python scripts/pact/pact.py init \
  --target ../existing-project \
  --apply \
  --github-actions
```

The workflow validates the PACT foundation/checks/readiness inventory only. Project-owned build, tests, E2E, and visual verification remain project-specific.

## Migration policy

Use **forward-only governance**. Improve historical coverage when work touches an area; do not block adoption on documenting the entire past.
