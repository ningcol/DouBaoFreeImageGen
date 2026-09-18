# Skill: Convergence Review

## Purpose

Perform a semantic consistency review after meaningful changes.

This skill reviews; it does not silently redefine product truth.

## Inputs

Use the task/change intent, relevant Product Truth, current architecture, implementation, tests, runtime/browser evidence, and durable decisions needed for the affected scope.

Do not expand to the entire repository unless risk or uncertainty requires it.

## Questions

1. Does observed behavior align with confirmed product truth?
2. Does implementation align with active change intent/spec?
3. Do tests align with the intended product behavior?
4. Does current architecture documentation still match relevant structure?
5. Did the change introduce unrequested behavior?
6. Was a durable engineering decision introduced without a record?
7. Was an existing decision effectively superseded?
8. Is relevant documentation stale?
9. Is there unresolved product ambiguity requiring owner input?

## Classification

- `aligned` — checked and consistent.
- `stale` — technical/current-state documentation needs repair.
- `missing` — required behavior/artifact is absent.
- `partial` — intent is implemented only partly.
- `contradicts` — implementation and authoritative intent conflict.
- `unrequested` — behavior was added without supported intent.
- `owner-decision` — ambiguity is genuinely product/risk-level.

## Output contract

For a durable or machine-consumed review, emit a JSON report conforming to:

`.pact/schema/convergence-report.schema.json`

Every nontrivial finding must state:

- what was observed;
- what was expected;
- which authority establishes the expectation;
- concrete evidence;
- recommended action.

An `owner-decision` finding must additionally include `owner_question` phrased as an observable product/business choice.

Validate the report with:

```bash
python scripts/pact/converge.py <report.json>
```

## Escalation

Technical drift should normally be repaired autonomously.

Only `owner-decision` findings should interrupt the owner.

Do not turn raw implementation alternatives into owner questions. Translate them into user/business consequences.

## Completion interaction

`missing`, `partial`, `contradicts`, and `owner-decision` are blocking by default.

`stale` may remain nonblocking only when risk is acceptable and the drift is explicitly repaired or registered.
