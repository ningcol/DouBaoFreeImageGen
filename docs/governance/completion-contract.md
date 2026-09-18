# Completion Contract

PACT treats "done" as an evidence-backed claim.

## Task Contract

A prepared task has a machine-readable Task Contract containing:

- the task intent;
- observable acceptance criteria with stable `AC-*` IDs;
- explicit constraints that must remain true.

Evidence claims may bind to one or more acceptance IDs. Prepared Task Contracts are fingerprinted, and completion requires Evidence to carry the SHA256 of the exact contract it verified. When a Task Contract is present, completion fails if the contract changed after verification, if any acceptance criterion lacks passing Evidence, or if that Evidence is not represented in the Owner Report.

Task Contract intent is task-scoped authority. It does not silently override confirmed durable Product Truth; conflicts require reconciliation or an owner-level product decision.

## Default definition

A task is complete when, to a degree appropriate for its risk:

1. implementation is complete;
2. observable behavior is verified;
3. relevant project truth has converged;
4. no blocking ambiguity remains;
5. required evidence exists.

## Risk-adaptive rigor

### Low risk

Examples: text, spacing, obvious local bug.

Expected: targeted inspection and verification.

### Medium risk

Examples: normal feature, cross-component state, ordinary API behavior.

Expected: affected feature context, relevant tests, observable verification, targeted convergence.

### High risk

Examples: permissions, migration, schema, public contract, security, payments, cross-domain rules.

Expected: deeper context, durable decisions where applicable, stronger verification, convergence, and durable evidence when justified.

## Invalid completion claims

Do not report:

- "verified" when no verification was run;
- "no impact" without checking affected behavior;
- "safe" based only on code inspection;
- "tests pass" when tests were not executed;
- "matches product requirements" when product truth was never located.

When something could not be verified, say so explicitly.
