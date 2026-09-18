# Skill: Project Explain

## Purpose

Explain an existing project feature, behavior, or historical design to the owner without requiring the owner to remember file names or understand implementation jargon.

## Start

Load the Owner Profile, then build the explanation evidence packet:

```bash
python scripts/pact/pact.py owner --json
python scripts/pact/pact.py explain "<owner query>" --json
```

Use the Explanation Packet as the first evidence set.

## Expand only when needed

If the packet reports gaps or the question requires stronger evidence:

- inspect Product Rule source;
- inspect current architecture;
- inspect relevant implementation and tests;
- inspect runtime/browser behavior;
- inspect Git history for actual historical change;
- inspect durable Decision Records for rationale.

Use sufficient context, not exhaustive context.

## Owner-readable answer

Prefer this semantic order:

### What it is

Explain the business/product concept in established project vocabulary.

### What should happen

Ground this only in artifacts whose status establishes confirmed Product Truth. Candidate rules/concepts are context, not normative truth. If none is found, say so.

### How it works today

Ground this in current implementation/runtime evidence, not Product Truth alone.

### Why it is this way

Use an implemented Decision Record for the current rationale. Proposed/rejected records may explain alternatives, and superseded records may explain history, but they are not evidence for the current design rationale.

If no implemented rationale is preserved, explicitly say that the reason is not currently documented. Never invent a plausible architecture story.

### Where it matters

Describe affected pages, flows, domains, or business capabilities before technical modules.

### What changed

Use Change artifacts and/or Git history. Do not call something recent without dated evidence.

### Drift / uncertainty

Surface conflicts between Product Truth, code, tests, architecture, or old documentation.

## Communication rules

- respond in the configured owner language (or current conversation language when `auto`);
- honor configured `technical_depth` and progressive disclosure;
- use canonical business vocabulary;
- explain consequences before implementation;
- do not dump file lists as the answer;
- distinguish "should" from "currently does";
- distinguish recorded rationale from inference;
- put technical paths/symbols under optional detail.
