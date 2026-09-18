# Domain Vocabulary

PACT vocabulary is anchored in **Domain artifacts**, not a second manually maintained glossary database.

For each durable business concept, create a Domain page under `docs/product/domains/` and put every machine-searchable name in TOML metadata:

```toml
+++
[pact]
type = "domain"
id = "DOMAIN-BATCH"
status = "confirmed"
owners = ["product"]
aliases = [
  "全国批次",
  "批次",
  "省份批次",
  "examBatch",
  "admissionBatch",
  "currentBatch",
]
+++
```

The page heading is the canonical owner-facing name.

Use the body to explain:

- precise business meaning;
- confusing near-synonyms;
- historical terminology;
- important relationships.

## Rules

- Do not force immediate code-wide renaming during PACT adoption.
- Map aliases first; converge naming over time.
- Canonical terms are preferred in owner-facing communication and Product Truth.
- Distinguish same-name/different-meaning concepts explicitly.
- Do not keep a second alias list that can drift from `pact.aliases`.
