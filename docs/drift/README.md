# Drift

PACT stores each durable drift item as one machine-readable artifact.

Lifecycle:

```text
known → resolved | accepted
```

Layout:

```text
docs/drift/
├── known/
├── resolved/
├── accepted/
└── TEMPLATE.md
```

## Why one file per drift

A single shared register becomes hard to reference, validate, move through lifecycle, and merge across worktrees.

One artifact per drift gives:

- stable ID;
- explicit status;
- independent lifecycle;
- Project Discovery visibility;
- Audit inventory;
- less merge conflict pressure.

## Policy

Known drift records a real unresolved inconsistency.

It is not permission to silently redefine Product Truth or leave high-risk ambiguity unresolved.

When resolved or explicitly accepted, move the artifact to the matching lifecycle directory and update its status.
