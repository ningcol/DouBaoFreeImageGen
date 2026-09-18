# PACT Pilot Scorecard

PACT should be evaluated by whether it improves real project work, not by how many rules or commands it contains.

This scorecard is intentionally small and task-oriented.

## What we want to learn

The pilot should answer five practical questions.

### 1. Does PACT reduce the owner's technical-management burden?

Record:

- product decisions actually requiring the owner;
- technical implementation questions escalated to the owner;
- clarification rounds required before the owner understood the question/result.

A healthy direction is:

- product decisions remain visible;
- technical escalations trend toward zero;
- owner clarification rounds decrease.

### 2. Does PACT improve completion integrity?

Record:

- unsupported "done" claims blocked by Evidence/Report validation;
- missing verification discovered before completion;
- Convergence findings that prevented a false completion claim.

The goal is not to maximize findings.

The goal is to catch meaningful mistakes before the owner relies on a false completion claim.

### 3. Can PACT recover project memory?

When the owner asks a question such as:

> Why does this feature work this way?

record whether Project Explain:

- resolved the question from durable evidence;
- partially resolved it;
- failed because rationale/context was missing.

A failed explanation can still be useful if PACT clearly identifies the missing Decision/Product Truth instead of inventing an answer.

### 4. Does Context Resolution stay focused?

Record:

- number of knowledge artifacts;
- number of code candidates when code-aware context is used;
- known unknowns;
- whether context overload was observed.

Do not optimize for the smallest number blindly.

The target is **sufficient, high-value context** with low irrelevant load.

### 5. What does PACT cost?

Optionally record approximate PACT-specific overhead minutes.

This includes time spent on PACT-specific baseline/context/evidence/convergence work beyond ordinary implementation.

Do not fake precision if the number is unavailable.

## Machine-observed task data

PACT can derive facts it already owns without asking the pilot operator to copy them into a scorecard:

```bash
python scripts/pact/pact.py eval --task <TASK-ID> --json
```

The observation is built from the prepared Task Contract, Context envelope, `pact run` receipts, completion attempts, Evidence, Convergence, and Owner Report when present.

Machine-observed dimensions include:

- acceptance criteria and owner-visible Evidence coverage;
- Context knowledge/code artifact counts and known unknowns;
- verification run count/pass/fail/workspace-change counts;
- completion attempts and failed attempts;
- stale-workspace, stale-Task-Contract, acceptance-gap, and CI-requirement blocks;
- Evidence claim states;
- Convergence finding/owner-decision counts.

PACT deliberately leaves human-only dimensions in `human_required` instead of fabricating zeros:

- product decisions actually made by the owner;
- technical escalations to the owner;
- clarification rounds;
- owner comprehension;
- subjective Context overload;
- PACT-specific overhead time.

The machine observation complements the pilot evaluation record; it does not replace owner-observed data.

## Historical retrieval replay

Use `docs/evaluation/brownfield-benchmark.md` for the repeatable historical Context-retrieval benchmark. It compares pre-change Context with source files changed by later real commits and separately measures direct retrieval vs a curated post-hoc expanded-query diagnostic. The latter is not an unbiased Agent-performance metric.

This benchmark measures retrieval only. It is not a substitute for the owner-interaction dimensions above.

## Baseline comparison

Records support:

`mode: baseline`

and:

`mode: pact`

When practical, use comparable task types/risk levels.

This is not a controlled scientific experiment by default. Treat small samples as directional evidence.

## No single PACT score

PACT deliberately does not collapse these dimensions into a single 0–100 score.

A single score would hide important trade-offs:

- fewer owner interruptions but much higher process cost;
- better evidence but severe context overload;
- fast implementation but unreliable Project Explain.

Review the dimensions separately.

## Record format

Use:

`.pact/schema/pilot-evaluation.schema.json`

Example:

`.pact/examples/pilot-evaluation.example.json`

Validate or summarize records with:

```bash
python scripts/pact/pact.py eval record.json

python scripts/pact/pact.py eval \
  baseline-1.json baseline-2.json \
  pact-1.json pact-2.json \
  --summary
```

## Pilot success criteria

Do not decide these thresholds before seeing real tasks.

After the first real pilot set, use observed data to decide whether PACT should:

- keep a mechanism;
- simplify it;
- make it optional;
- remove it.

The evaluation system exists to make PACT easier to delete or simplify when evidence says a mechanism is not paying for itself.
