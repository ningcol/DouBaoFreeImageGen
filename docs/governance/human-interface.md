# Human Interface Contract

The owner should be able to control the product without becoming the technical reviewer.

## Owner Profile

Project-specific communication preferences live in `.pact/config.toml`.

Before owner-facing explanations, decisions, or completion reports, use the configured profile:

- `role` — the owner's decision role;
- `language` — preferred communication language/locale (`auto` follows the active conversation);
- `technical_depth` — `product`, `balanced`, or `technical`;
- `communication.prefer` — concepts to prioritize;
- `communication.hide_by_default` — implementation detail kept behind disclosure;
- `progressive_disclosure` and `decision_translation` — interaction policy.

Read the validated profile with:

```bash
python scripts/pact/pact.py owner --json
```

Owner Profile changes communication, not the Agent's internal engineering capability.

## Default owner role

Product/project owner, not code reviewer.

## Owner-facing language

Prefer:

- user behavior;
- business behavior;
- page/flow changes;
- data meaning;
- observable consequences;
- verified scenarios;
- unresolved product risks.

Hide by default:

- class/function implementation details;
- framework internals;
- design-pattern debates;
- low-level state mechanics;
- file lists unless useful.

Technical details remain available through progressive disclosure.

## Decision translation

Bad:

> Should this use soft delete or hard delete?

Good:

> After a user deletes this record, should it be permanently unrecoverable, or should administrators be able to restore it later?

Bad:

> Should selected province live in URL state or global state?

Good:

> After a page refresh, should the user stay on the province they selected, or return to the default province?

## Completion report semantics

A normal owner report should communicate:

- what changed;
- what changed for the user/business;
- what was actually verified;
- coverage of every Task Contract acceptance criterion;
- whether project consistency is healthy;
- whether an owner decision remains.

A completed report must not hide a verified acceptance criterion by omitting its Evidence from the verification section.

## Progressive disclosure

Level 1: business result and verification.

Level 2: concise cause/architecture explanation.

Level 3: technical files, symbols, diffs, implementation details.

## Vocabulary

Use canonical business terminology from `docs/product/glossary/` in owner-facing communication. Do not invent project jargon when an established term exists.
