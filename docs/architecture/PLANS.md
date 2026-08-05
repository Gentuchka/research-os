PROJECT: Research OS

## Objective

Design and implement a **Research Operating System** for long-term mathematical research.

This is **not** a chatbot.

This is **not** a simple multi-agent system.

This is a persistent research environment where specialized AI agents collaborate over months or years to explore difficult mathematical conjectures.

The system must maximize **verified knowledge accumulation** while minimizing **AI-generated noise (AI slop)**.

The system must be architecture-first.

Do **not** start implementing immediately.

Your first task is to design the architecture and produce technical specifications.

---

# Core Philosophy

The purpose of the system is NOT

> "Solve a conjecture."

The purpose is

> **Maximize the accumulation of verifiable mathematical knowledge.**

Even if the main conjecture is never solved, the system should continuously produce:

- verified lemmas
- counterexamples
- useful constructions
- failed proof attempts
- dead ends
- promising techniques
- intermediate conjectures
- strengthened conjectures
- weakened conjectures
- relationships between mathematical objects

Failure is considered useful if it increases knowledge.

---

# Overall Architecture

The architecture should resemble an operating system rather than a chatbot.

```
Human

↓

Scheduler

↓

Agents

↓

Research MCP Server

↓

Knowledge Graph

↓

Obsidian Vault

↓

Git
```

Agents must never directly modify markdown files.

Everything goes through MCP.

---

# Primary Components

Design specifications for:

- Knowledge Graph
- MCP Server
- Scheduler
- Worker Agent
- Reviewer Agent
- Thinker Agent
- Metrics Engine
- Version Control
- Obsidian Integration
- Human Interface

---

# Research Objects

Everything in the system should be represented as typed research objects.

Possible object types:

```
Main Conjecture

Hypothesis

Lemma

Definition

Technique

Construction

Counterexample

Observation

Proof

Research Question

Experiment

Paper

Report
```

Every object should have a unique ID.

---

# Knowledge Graph

The research database is NOT a tree.

It is a typed directed acyclic graph.

Supported edge types include:

```
strengthens

weakens

generalizes

specializes

depends_on

uses

proved_by

disproved_by

kills

extends

derived_from

motivated_by

equivalent_to

requires
```

Never use generic "related" edges.

---

# Research Invariants

These invariants are mandatory.

Every agent must obey them.

---

## Invariant 1

Knowledge is immutable.

Nothing is edited.

Nothing is overwritten.

Only:

- append
- archive
- supersede
- link

are allowed.

---

## Invariant 2

Every object must have provenance.

Every hypothesis must answer:

Where did this come from?

Possible origins:

- main conjecture
- worker report
- thinker proposal
- literature
- existing hypothesis

---

## Invariant 3

Every new node must increase information.

Nodes that differ only cosmetically must never be created.

---

## Invariant 4

Graph must remain acyclic.

---

## Invariant 5

Facts and opinions are stored separately.

Facts:

- proof exists
- counterexample exists

Opinions:

- importance
- promise
- novelty

must never be mixed.

---

## Invariant 6

Every relation must have a defined type.

---

## Invariant 7

Every research iteration must increase knowledge.

Even unsuccessful proof attempts must produce:

- failed approaches
- useful observations
- discovered lemmas
- possible future work

---

## Invariant 8

Every claim must reference evidence.

No unsupported statements.

---

## Invariant 9

History is permanent.

Research history cannot disappear.

---

# Worker

Purpose:

Solve one research task.

Worker must never:

- redesign graph
- update metrics
- modify statuses
- create markdown
- perform global planning

Worker only investigates one node.

Input:

- hypothesis
- related objects
- previous attempts
- techniques
- definitions
- lemmas

Output:

- proof attempt
- counterexample attempt
- observations
- new lemmas
- suggested ideas
- estimated difficulty
- confidence
- structured report

---

# Reviewer

Reviewer is responsible for research quality.

Responsibilities:

- validate reports
- detect logical issues
- reject low-quality reasoning
- detect duplicates
- merge duplicate hypotheses
- compute metrics
- update graph
- archive obsolete nodes
- detect superseded hypotheses
- update frontier
- create candidate nodes

Reviewer is the only agent allowed to update the knowledge graph.

---

# Thinker

Thinker performs strategic reasoning.

Thinker does not investigate individual hypotheses.

Thinker analyzes the entire graph.

Responsibilities:

- detect global patterns
- discover missing connections
- identify unexplored directions
- suggest new intermediate conjectures
- identify useful techniques
- reorganize research strategy

Thinker should run infrequently.

---

# Scheduler

Scheduler selects the next task.

Workers never choose tasks.

Scheduler selects tasks from the Research Frontier.

---

# Research Frontier

Frontier consists of the most promising active nodes.

Selection should consider:

- importance
- promise
- distance
- expected information gain
- research cost

---

# Metrics

Each node should contain independent metrics.

Examples:

```
importance

difficulty

distance

novelty

promise

information_gain

verification_confidence

branching_factor

research_cost

stability
```

Distance measures proximity to the original conjecture.

These metrics must remain independent.

---

# Superseding

If a stronger counterexample disproves multiple weaker hypotheses,

Reviewer must automatically mark weaker hypotheses as

```
SUPERSEDED
```

instead of keeping multiple active branches.

---

# Research Budget

Every node has limited resources.

Example:

```
attempt_budget

token_budget

time_budget

tool_budget

branch_budget
```

Nodes that consume too much budget become

```
STUCK

or

FROZEN
```

until new information appears.

---

# Provenance Graph

Besides the mathematical graph, maintain a provenance graph.

Example:

```
Worker Report

↓

Observation

↓

Hypothesis

↓

Counterexample

↓

Disproved Hypothesis
```

The system should always explain

why every node exists.

---

# Anti-Slop Policy

The system should aggressively minimize AI-generated noise.

Reviewer should reject:

- duplicated reasoning
- unsupported claims
- repetitive hypotheses
- cosmetic hypothesis variants
- low-information reports
- hallucinated references

---

# MCP Server

Agents never access the filesystem.

Agents interact only through MCP tools.

Possible tools:

```
create_node

archive_node

find_similar

create_link

find_frontier

compute_metrics

nearest_main

graph_statistics

search_by_definition

search_by_lemma

search_counterexamples

search_techniques

history

timeline

find_dead_nodes

find_orphans

find_duplicate

semantic_search
```

---

# Obsidian

Obsidian is the long-term storage layer.

Each research object corresponds to a markdown file.

Vault structure should be designed.

Templates should be generated automatically.

---

# Version Control

Git should track the evolution of the research graph.

Every change should be reproducible.

---

# Deliverables

Do NOT start coding.

First produce:

1. Complete architecture
2. Folder structure
3. Domain model
4. Graph schema
5. MCP API specification
6. Agent specifications
7. Scheduler specification
8. Metrics specification
9. Obsidian schema
10. Anti-slop specification
11. Implementation roadmap

Only after approval should implementation begin.