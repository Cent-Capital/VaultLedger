# HANDOFF — driving VaultLedger across multiple agents

You run more than one coding agent (Claude Code, Codex, Gemini). This file makes
any of them safe to hand a bounded chunk of VaultLedger without losing the
honesty and determinism the build depends on.

## The one rule
`SPEC.md` + `PROGRESS.md` are the shared context bus. Any agent that reads them
plus this file can execute a self-contained task. Keep the **coupled critical
path on one primary agent** (Claude Code). Hand the other agents **independent,
self-contained chunks** only. See `track-allocation` (in the PM-OS workspace)
for which work goes where.

## What is safe to hand off
Good chunks (self-contained, small handoff context):
- One module or one test file with clear acceptance criteria.
- A research memo ("how does LightRAG index; what are the tradeoffs vs Graphiti").
- First drafts: an ADR, a golden-set candidate batch, README sections.

Bad chunks (keep these on the primary agent):
- Anything that spans two phases or depends on work in flight.
- Anything that edits shared contracts (`schemas.py`, `config.py`) mid-phase.
- Anything where the eval numbers matter and can't be reproduced by the receiver.

## The template (copy, fill the <blanks>, paste into any agent)

```
You are a build agent on VaultLedger: a privacy-first, local-first
financial-document Q&A app with a rigorous evals harness. This is a solo
portfolio + internship build. The commit history and PROGRESS.md are the
receipt, so honesty and determinism matter more than speed.

BEFORE YOU START, READ:
- SPEC.md — the master spec and source of truth. Relevant sections: <§__>
- PROGRESS.md — the honest build log; the last entry is the current state
- CLAUDE.md — repo conventions and the rules below
- <any other file the task touches>

YOUR TASK (self-contained):
<one crisp task: a single module / test file / doc. Not a coupled multi-phase
thing. Not "finish the phase" unless the phase is genuinely small.>

ACCEPTANCE CRITERIA (from SPEC §16 / §18):
- <AC 1, stated as something testable>
- <AC 2>

RULES (non-negotiable):
- Never fabricate results. If you did not run it, say "I have not tested this."
  Eval numbers come from a real run with a RunManifest, never invented or
  guessed. Label uncertainty where it appears, not in a closing note.
- Determinism: the seed lives in config.yaml. Generated artifacts must
  regenerate identically. Bounded loops only (CI bans `while True`; budgets
  live in config.yaml).
- Match the existing code style and the Section 8 schemas exactly. Every knob
  routes through vaultledger/config.py over config.yaml.
- Stay in scope. Do not refactor unrelated code, do not start the next phase,
  do not touch shared contracts unless the task says so.

WHEN DONE, HAND BACK:
- What changed: files touched and why.
- Test + lint status with the ACTUAL output (`make test`, `make lint`).
- A draft PROGRESS.md entry: Built / Acceptance criteria / Deviations from SPEC
  (and why) / Trickiest piece in plain English.
- A draft commit message (honest; end with the Co-Authored-By line the repo
  uses).
- Anything you were unsure about or left for me to verify. Do not paper over it.
```

## Variants

**Code chunk (Codex / Claude Code):** use the template as-is. Point it at the
one module and its test file.

**Research memo (Gemini):** replace the RULES block with: "Cite sources. Separate
what you verified from what you inferred. Give me a recommendation with the
tradeoff, not a survey. Output a short memo I can drop into decisions/ as an ADR
draft." No repo write access needed; paste the memo back.

**Narrative (PM-OS, not this repo):** internship report, blog, deck. Do these in
the PM-OS workspace with its skills, not here. This repo is for things the
compiler or eval harness reads.

## Merge discipline (the part that bites)
Different models write in different styles. When you fold a handoff back in:
1. Read the diff yourself before committing. You are the verification gate.
2. Re-run `make test` and `make lint` locally. Trust the receiver's claims only
   after your own green run.
3. Rewrite the PROGRESS entry in your own voice so the log stays coherent.
4. One honest commit. If the agent guessed a number, delete it and measure it.

## Current handoff status (2026-07-13)

Phases 0-4 are implemented. Phase 3's permanent dense baseline is
`reports/phase3_b4407e88d3ba.json`; Phase 4's hybrid manifest is
`reports/phase4_de57151e3ae3.json`.

Use these commands before handing work to another agent:
- `make lint`
- `make test`
- `python -m vaultledger.evals validate`
- `python -m vaultledger.evals run --variant B_hybrid` with local Ollama access
  and the cached BGE model if the next agent needs to reproduce Phase 4 metrics.

Measured Phase 3 baseline:
- `retrieval_recall@20`: `0.9586734693877551`
- `retrieval_precision@20`: `0.1007142857142856`
- `retrieval_mrr`: `0.49739239518651296`
- `retrieval_hit_rate`: `0.9857142857142858`
- `retrieval_eval_coverage`: `0.875`

Known caveat: sandboxed shells may not be able to access `localhost:11434`, so
`make eval-smoke` can validate the golden set and then skip the dense mini-run.
The Phase-4 acceptance run requires Ollama with `nomic-embed-text` plus the
`BAAI/bge-reranker-base` model downloaded by sentence-transformers.

Measured Phase 4 hybrid retrieval:
- `retrieval_recall@20`: `0.9785714285714285` (`+0.0198979591836734` vs dense)
- `retrieval_mrr`: `0.7855867346938776` (`+0.2881943395073646` vs dense)
- `retrieval_precision@20`: `0.10428571428571416`
- `retrieval_hit_rate`: `0.9857142857142858`

Recommended next handoff chunk:
Implement Phase 5 only: structured `Answer` generation, the bounded L1 repair
loop (`repair_max`), programmatic citation verification against retrieved chunks,
and a safe abstaining fallback. Prove malformed outputs repair or downgrade
without crashing; do not pull Phase-6 cloud routing into this slice.
