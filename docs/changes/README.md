# Changes

Change artifacts describe **current change intent**, not durable project truth.

Lifecycle:

```text
active → completed | abandoned
```

Layout:

```text
docs/changes/
├── active/
├── completed/
└── abandoned/
```

Use a change artifact for work large enough that another agent may need to resume or review it.

A change artifact can include:

- goal;
- observable success;
- scope;
- constraints;
- work/progress;
- findings;
- references to durable decisions;
- verification;
- completion criteria.

When work finishes, move the artifact to `completed/` and set `status: completed`.

When work is intentionally stopped without completion, move it to `abandoned/` and set `status: abandoned`.

Do not place durable rationale here when it belongs in a Decision Record.
