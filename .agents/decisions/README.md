# Durable Decisions

Decision records preserve **why** a durable engineering choice exists.

Create one only when the decision is likely to matter to future agents.

## Threshold

Good candidates include:

- architecture boundary;
- public/cross-module contract;
- persistence/schema ownership;
- security/concurrency semantics;
- infrastructure;
- build/deployment strategy;
- long-lived testing strategy;
- a rejected alternative likely to be proposed repeatedly.

Do not create decisions for formatting, ordinary UI adjustments, simple CRUD, small bug fixes, routine refactors, or uncontroversial implementation details.

## Lifecycle

```text
proposed
  ├──→ rejected
  ↓
implemented
  ├──→ superseded
  ↓
archived
```

When core rationale changes, create a new decision that supersedes the old one. Do not rewrite history.

Use `TEMPLATE.md`.
