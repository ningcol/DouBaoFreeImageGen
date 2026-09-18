# Truth Ownership

PACT avoids a single global "source of truth" ranking. Different questions have different authorities.

| Question | Authority |
| --- | --- |
| What should users/business experience? | Confirmed Product Truth |
| What does the system currently do? | Code + runtime/generated facts |
| What public/API contract is promised? | Contract/schema authority |
| How is the current system structured? | `docs/architecture/` |
| Why was a durable choice made? | `.agents/decisions/` |
| What is this change trying to accomplish? | Active Task Contract / change/spec/plan |
| What must this task demonstrably satisfy? | Task Contract acceptance criteria, bounded by confirmed Product Truth |
| What was actually verified? | Evidence from tests/browser/runtime/CI |
| How should a recurring task be performed today? | Skill/playbook |

## Rules

1. One fact should have one owner.
2. Prefer references over duplicated explanations.
3. Generated facts should be regenerated, not manually synchronized.
4. Product truth must not be inferred from implementation alone.
5. Architecture documents describe current structure; historical rationale belongs in decisions.
6. Tests are evidence, not automatically normative product truth.

## Conflict example

If a confirmed rule says "preserve entered data after province switch" while code and tests clear it:

- this is product drift;
- do not rewrite the product rule to match code;
- if product truth remains authoritative, fix code/tests;
- if product truth itself is ambiguous or obsolete, escalate the product behavior to the owner.
