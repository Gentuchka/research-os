# ADR 004: Configurable models per agent role

## Status

Accepted

## Decision

Each agent role (`worker`, `reviewer`, `thinker`) uses a **configurable model profile** from `configs/models.yaml`.

Default provider profile: **GPT 5.6 Sol** with selectable **reasoning effort** (`medium`, `high`, `max`).

Humans change models by editing config (or future Obsidian frontmatter directive) — no code changes.

## Profiles

See `configs/models.yaml`. Each profile specifies:

- `model` — provider model id
- `reasoning_effort` — `medium` | `high` | `max` (when supported)
- `temperature` — explicit float (no defaults in code paths; config must set it)

## Reviewer split

- **Deterministic checks** (schema, cycles, duplicates, evidence resolution) run without LLM.
- **LLM Reviewer** optional for logical critique; can be disabled by setting `reviewer.llm.enabled: false`.

## Consequences

- Run ledger records `model_profile` + `reasoning_effort` per job for reproducibility.
- Eval harness can pin profiles in test config.
