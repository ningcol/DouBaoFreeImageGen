# Skill: Owner Report

## Purpose

Produce the default human-facing result after a PACT-governed task.

The owner is a product/project decision-maker, not the implementation reviewer.

## Required grounding

First load the project-specific Owner Profile:

```bash
python scripts/pact/pact.py owner --json
```

Then produce the completion report using:

- configured owner language and technical depth;
- requested product outcome;
- canonical business vocabulary;
- Evidence Receipt;
- Convergence Report.

For machine-checked reporting, create an Owner Report conforming to:

`.pact/schema/owner-report.schema.json`

and validate/render it with:

```bash
python scripts/pact/report.py owner-report.json \
  --evidence evidence-receipt.json \
  --convergence convergence-report.json
```

## Default content

Explain:

1. what changed;
2. what users/business experience now;
3. what was actually verified;
4. whether project consistency is healthy;
5. whether the owner must decide anything.

## Do not

- dump implementation details first;
- ask the owner to choose ordinary technical mechanisms;
- say "verified" without linked evidence;
- say "completed" when required evidence is incomplete or convergence is blocking;
- translate jargon literally when the real need is to explain consequences.

## Product decision format

State the observable business question.

For each option, describe its user/data/risk consequence.

Technical implementation can remain behind progressive disclosure.

Honor `technical_depth`:

- `product`: product/business consequences first; technical detail only on request or when necessary to understand risk;
- `balanced`: concise architecture context is acceptable after the product explanation;
- `technical`: technical detail may be more visible, but product consequences and evidence still come first.
