# ADR 006: Defer formal verification integration

## Status

Accepted

## Decision

No Lean, Isabelle, or other proof assistant integration in P0–P2.

`ResearchObject.formalization` field remains optional string (null by default). Future ADR will add a `FormalVerificationAdapter` behind MCP tools.

## Consequences

- `Proof` acceptance is Reviewer judgment + structured evidence, not machine-checked proof.
- Architecture leaves room for `verify_proof` MCP tool later without changing object types.
