# PACT Runtime

PACT core requires Python 3.11+ and uses only the standard library. No runtime pip dependencies are required.

The stable v1 entry point is:

```bash
python scripts/pact/pact.py <command> [args...]
```

## Recommended agent surface

```text
status             project foundation/readiness/health summary
inspect            combined explanation + code evidence packet
task prepare       Task Contract + risk-adaptive context preparation
task finish        acceptance-aware completion-bundle gate
task status        one-task state
```

The commands below remain stable advanced primitives.

## Available primitives

```text
init       safely scaffold PACT into an existing repository
upgrade    safely update unchanged framework-managed PACT files
version    show source/installed PACT runtime versions
check      deterministic artifact checks
schema-lint validate that schemas use only runtime-supported keywords
workflow-lint require immutable external GitHub Action pins
doctor     deterministic PACT foundation health
readiness  explicit brownfield baseline readiness
audit      deterministic repository health inventory
owner      validate and expose project Owner Profile
risk       show core low/medium/high rigor policy
fitness    run project-owned executable architecture invariants
map        rebuild disposable project map
code-map   rebuild disposable local code relationship map
discover   deterministic project discovery
explain    build an explanation evidence packet for an owner query
context    build candidate Task Context Envelope
impact     map changed files to deterministic/candidate project impacts
converge   validate/summarize semantic Convergence Report
evidence   validate completion Evidence Receipt
report     validate and render evidence-backed Owner Report
eval       validate/summarize pilot records or derive machine task observations
```

Examples:

```bash
python3 pact.py status
python3 pact.py inspect "batch state"

python3 pact.py task prepare "fix province switch" \
  --success "Displayed data follows the selected province" \
  --risk medium

python3 pact.py task status <TASK-ID>
python3 pact.py task finish <TASK-ID>

# Advanced primitives:

python scripts/pact/pact.py init --target ../existing-project
python scripts/pact/pact.py init --target ../existing-project --apply
python scripts/pact/pact.py init --target ../existing-project --apply --github-actions

python scripts/pact/pact.py version --target ../existing-project
python scripts/pact/pact.py upgrade --target ../existing-project
python scripts/pact/pact.py upgrade --target ../existing-project --apply

python scripts/pact/pact.py doctor
python scripts/pact/pact.py readiness
python scripts/pact/pact.py audit --json
python scripts/pact/pact.py owner --json
python scripts/pact/pact.py risk high --json
python scripts/pact/pact.py fitness

python scripts/pact/pact.py discover "batch state"
python scripts/pact/pact.py discover "BatchService" --code

python scripts/pact/pact.py code-map
python scripts/pact/pact.py impact --files src/example.ts --code --json

python scripts/pact/pact.py explain "why does the workspace follow the current batch?" --json

python scripts/pact/pact.py context "fix province switch" \
  --success "Displayed data follows the selected province" \
  --risk medium

python scripts/pact/pact.py context "upgrade runtime" \
  --success "Upgrade behavior remains safe" \
  --risk medium \
  --code

python scripts/pact/pact.py impact --base main --json

python scripts/pact/pact.py eval .pact/examples/pilot-evaluation.example.json
```

## Architecture fitness

`.pact/fitness.toml` is project-owned.

PACT only standardizes how executable invariants are registered and reported; it does not prescribe architecture patterns.

`severity: error` failures block. `severity: warn` failures are reported without blocking.

## Code-aware discovery

Code relationships are generated and disposable.

`discover --code` searches code paths/symbols/import text and adds one-hop import neighbors.

`impact` and `context` follow the core risk profile by default:
- low: no code expansion unless explicitly requested;
- medium/high: code-aware expansion enabled unless explicitly disabled.

Generated relationships carry confidence:
- `direct`: direct lexical code match;
- `relative-resolved`: relative JS/TS/Vue path resolved to a repository file;
- `ast-resolved`: Python relative import resolved from AST/package position;
- `heuristic`: repository-local Python absolute-import match whose runtime import resolution may differ.

Behavioral impact remains a candidate requiring review.

Project/Code maps use source fingerprints. A cached map is reused only while its source set is fresh; otherwise it is refreshed automatically.

On Git repositories, file enumeration uses Git's tracked/visible-untracked view and respects `.gitignore` before parsing. When only part of the source set changed, per-file parse caches reuse unchanged Markdown/symbol/import results and only reparse changed/new files.

Unsupported project-specific aliases or framework magic remain unresolved rather than guessed.

## Discovery vs Explain vs Context

- `discover`: locate relevant project artifacts.
- `explain`: organize those artifacts into Product Truth / Architecture / Decision / Change / Drift evidence for an explanation.
- `context`: build a task-oriented candidate context envelope for implementation work; `--code` adds generated code candidates when useful.

`explain` prepares evidence. An Agent still performs the semantic, owner-readable explanation and must inspect code/runtime/Git when the evidence packet says that is necessary.

## Safe upgrades

`init --apply` records `.pact/install.json` with file ownership and SHA256 provenance.

For normal users, the repository-root `bootstrap.py` can fetch a pinned PACT ref and invoke init/upgrade without cloning PACT first.

- framework-managed files are auto-updatable only when unchanged since install;
- project seed files are never overwritten;
- any true framework conflict blocks the entire automatic apply;
- replacement files are staged before mutation;
- existing targets and install manifest are backed up;
- apply/validation failure rolls back replaced files and manifest;
- obsolete framework files are reported but never auto-deleted.

Run upgrade from the newer PACT source checkout:

```bash
python scripts/pact/pact.py upgrade --target ../existing-project
python scripts/pact/pact.py upgrade --target ../existing-project --apply
```

See `docs/design/distribution-upgrades.md`.

## Doctor vs Readiness

- `doctor` answers whether PACT infrastructure/configuration is valid.
- `readiness` answers whether the existing project's baseline was explicitly reviewed.

A freshly scaffolded project should normally be `foundation-valid`, not `pact-ready`.

Use `readiness --require-ready` only when the project has chosen readiness as a gate.

## Pilot evaluation

PACT evaluation is optional and task-based. It tracks dimensions such as owner technical escalations, clarification rounds, false-done prevention, Project Explain recovery, context overload, and optional process overhead.

PACT intentionally does not compute a single 0–100 score.

See `docs/evaluation/pilot-scorecard.md`.

## Safety boundary

`init` is dry-run by default and never overwrites existing files. An existing `AGENTS.md` is preserved; PACT creates merge guidance instead.

The runtime is deliberately hybrid:

- deterministic tooling validates facts it can reliably establish;
- semantic AI review handles meaning, impact, and sufficiency;
- the CLI never promotes heuristic guesses into authority.

Semantic uncertainty should remain a warning, Context unknown, candidate impact, Explanation gap, or Convergence finding.

## Task Contract / acceptance coverage

High-level task preparation persists `.pact/tasks/<TASK-ID>/contract.json`.

- `--success` creates `AC-1`;
- repeatable `--accept` adds `AC-2`, `AC-3`, ...;
- repeatable `--constraint` adds acceptance-bound criteria with `kind=constraint`;
- Evidence claims bind to acceptance criteria through optional `criteria: ["AC-1"]`;
- prepared tasks expose `contract_sha256`; Evidence for a Task Contract records it as `task_contract_sha256`;
- `task finish` automatically supplies the contract to the completion gate.

When a Task Contract is supplied, completion requires every acceptance criterion to have passing Evidence and requires that passing Evidence to be surfaced in Owner Report verification.


## Machine-observed task evaluation

After a task has been prepared, PACT can derive the task facts it already owns:

```bash
python scripts/pact/pact.py eval --task <TASK-ID> --json
```

The output includes acceptance coverage, Context artifact counts, run outcomes, completion-attempt blockers, Evidence state, and Convergence counts.

Human interaction fields are intentionally listed in `human_required` rather than guessed.
