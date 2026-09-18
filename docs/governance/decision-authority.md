# Decision Authority

PACT minimizes unnecessary owner approvals while preserving owner control over product meaning.

## 1. Autonomous technical decision

The agent decides without owner approval:

- internal class/function/module structure;
- implementation patterns;
- local state mechanics;
- query/cache strategy;
- ordinary refactors;
- test implementation;
- internal naming that does not redefine business terminology.

## 2. Autonomous durable engineering decision

The agent may decide, but should record durable rationale when the choice affects:

- architecture boundaries;
- cross-module/public contracts;
- persistence/schema ownership;
- security/concurrency semantics;
- infrastructure;
- build/deployment strategy;
- long-lived test strategy;
- a recurring decision future agents are likely to challenge again.

Use `.agents/decisions/TEMPLATE.md`.

## 3. Owner decision

Escalate when the choice changes:

- user-observable behavior;
- business rules or data meaning;
- permissions/policy;
- irreversible data outcomes;
- meaningful commercial/operational cost;
- accepted security/reliability risk;
- two technically valid options with different product consequences.

## Escalation gate

Before asking the owner, ask:

1. Does this change what a user can observe?
2. Does it change business meaning?
3. Is it irreversible?
4. Does it change permission/policy?
5. Does it require material risk/cost acceptance?
6. Do valid alternatives represent different product behavior?

If all are No, decide autonomously.

## Translation requirement

Never escalate "REST vs events", "soft delete vs hard delete", or "URL state vs store" as raw technical options.

Translate them into the user/business consequences the owner can meaningfully decide.

## Task Contract escalation rule

A Task Contract may expose unresolved product questions during preparation, but implementation must not turn engineering uncertainty into owner work.

- engineering ambiguity is resolved autonomously by the Agent;
- missing project facts are investigated through PACT/project history;
- only product/risk/cost ambiguity passes the escalation gate above;
- an unresolved owner-level question blocks a completed Owner Report.

The owner should receive a consequence-level question, never a request to choose an internal implementation mechanism.
