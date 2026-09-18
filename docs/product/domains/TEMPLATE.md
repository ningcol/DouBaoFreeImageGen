+++
[pact]
type = "domain"
id = "DOMAIN-EXAMPLE"
status = "confirmed"
owners = ["product"]
aliases = ["Example Name", "legacyExample"]
paths = []
+++

# <Canonical Domain Name>

## Meaning

What does this concept mean in the business/product world?

## Aliases

Keep **all machine-searchable aliases** in `pact.aliases` above, including:

- owner/UI terms;
- code/data aliases;
- historical names.

Use this section only to explain confusing aliases or distinctions; do not maintain a second alias list here.

## Not the same as

- ...

## Path scope

Optionally add a **small number of durable path globs** to `pact.paths` when they help Impact Analysis map implementation changes back to this Domain.

Do not try to map every file.

## Durable rules

- `RULE-...`

## Relevant architecture

- ...

## Durable decisions

- `DEC-...`

## Verification entry points

- ...

> This page is a router. Do not duplicate the full rule text or decision rationale here.
