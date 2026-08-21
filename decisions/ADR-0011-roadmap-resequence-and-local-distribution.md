# ADR-0011: Ship the product before judging it; distribute locally without a native shell

2026-08-11 · Status: **accepted** (owner decision)

## Context

Phase 15 closed with the graph pipeline built and measured. SPEC §16 schedules the
comparison report and portfolio artifacts next, with the multi-model bake-off as §17.
The owner has re-prioritised: the working, installable product matters more than the
portfolio write-up, and the internship demo should be produced last.

Two findings from the Phase-15 review shaped this decision.

**Only one model family has ever been evaluated.** Committed receipts contain 32 runs
on `ollama/qwen3:8b` and 5 on `ollama/qwen3:4b`. There are zero Gemma runs. The
two-family, three-size bake-off is not missing from the plan — it *is* SPEC §17 — but
it has never executed, so no evidence currently supports the model choice.

**Decoding parameters were never a decision at all.** `temperature` is hardcoded to
`0.0` as a Python default argument in four call sites and is not a config knob, which
violates this repo's own rule that every knob routes through `config.py`. `top_p` is
never set anywhere; Ollama's default applies silently. No phase's acceptance criteria
contain a decoding sweep. The project cannot currently justify its own decoding settings.

Separately, investigating distribution revealed that the constraint is not the user
interface. Every path that runs the real product requires Ollama plus multi-gigabyte
model weights on the recipient's machine. The intended recipient — the internship
hiring manager — is non-technical.

## Options

**Keep the SPEC order.** Portfolio first, bake-off second, product packaging never
explicitly scheduled. Rejected: it produces a recruiter-facing summary of a system the
recruiter cannot run, and ADR-0003's own reasoning argues against judging models
against a half-built system.

**Re-sequence with a native desktop shell (Tauri/Electron).** Initially chosen, then
reversed. A native shell would require bundling the Python backend and its virtual
environment as a sidecar — the largest technical risk in the roadmap — and would still
leave the Ollama dependency untouched. It buys polish, not access.

**Re-sequence with a browser UI and a one-click launcher.** The existing Streamlit UI
stays; a launcher script starts the backend and opens the browser so the recipient never
uses a terminal. No Python bundling, no Apple Developer account, no notarisation.

## Decision

Re-sequence the remaining phases:

| Phase | Content |
|---|---|
| 16 | Live documents: inbox outside the repo, real-PDF ingest, OCR, folder watcher |
| 17 | Packaging and handoff: demo video, one-click launcher, Ollama first-run flow |
| 18 | Model and decoding bake-off (SPEC §17, extended with a decoding sweep) |
| 19 | Portfolio, demo v2, internship artifacts (SPEC §16) |

This is consistent with **ADR-0003**, which placed the bake-off after the portfolio
phase specifically so "every model is judged against the finished system rather than a
half-built one." Moving the product work ahead of both strengthens that reasoning rather
than contradicting it.

**Distribution is a browser UI plus a one-click local launcher.** The native shell is
**deferred, not cancelled**; reviving it re-opens the code-signing question. An earlier
assumption that unsigned apps are unusable was wrong: macOS permits opening them via
System Settings → Privacy & Security → "Open Anyway". The $99 Apple Developer account
buys frictionless distribution, not possible distribution, and under this decision is not
needed at all.

**The demo pins `qwen3:8b`**, the evaluated primary, not the smaller `qwen3:4b`. The
owner accepts the larger first-run download so that the demo runs the same model the
committed metrics describe. Substituting a smaller model to save download time would
make every quoted figure describe a model other than the one running.

**Phase 18 extends SPEC §17** to promote `temperature` and `top_p` to typed config
first — defaulting to today's effective values so the change is provably
behaviour-neutral — and only then sweep them, with the grid and decision rule
pre-registered before running, per the Phase-15 precedent.

## Consequences

The portfolio artifacts land last, so there is a longer window in which the project has
no recruiter-facing summary. That is accepted deliberately: a runnable product plus an
honest build log is a better artifact than a summary of an unrunnable one.

Model choice remains unjustified by evidence until Phase 18. Until then, no claim may be
made that `qwen3:8b` is the best available local model — only that it is the one the
system was built and measured on.

The recipient must still install Ollama and download model weights. This decision does
not remove that; it removes the pretence that a different UI technology would have.

Phase 19 inherits **ADR-0010's constraint**: none of the portfolio work may upgrade
Phase 15's failed quality gates into successes. The strict 73.3% entity recall, the 13.6%
precision with fabricated account nodes, the underpowered B-vs-C comparison, and the
inconclusive context-budget arm all travel into the portfolio as they are.

Real user documents introduce a data-handling obligation the synthetic corpus never did.
The repository is public, so the document inbox lives outside the working tree and Phase
16 builds a startup check that refuses to run if it does not. OCR handling and its
silent-failure risk are deferred to their own decision record.

## Evidence

- Receipt census across `reports/`: 32 × `qwen3:8b`, 5 × `qwen3:4b`, 0 × Gemma.
- `temperature` hardcoded at four call sites in `generate/`, `evals/judge/`, and
  `graph/ollama_binding.py`; absent from `config.yaml` and `config.py`. `top_p` absent
  from the codebase entirely.
- `cfg.paths.pdfs` with a `*.pdf` glob: ingest is already folder-configurable, so live
  documents are a configuration change rather than a rewrite.
- `ingest/parse.py:48` already carries a `needs_ocr` flag; detection exists, execution
  does not.
- LightRAG full-corpus build measured at 45.8 minutes for 60 documents
  (`reports/phase15_graph_index_2e50d5948f99.json`), so incremental insert is the only
  workable watcher design.
- Public remote `github.com/abhinavgupta0809/vaultledger`, synced at `d01ecb4`.

## Amendment — 2026-08-21: canonical public repository

The evidence line above records the remote used when this ADR was written. After ownership
transfer, the canonical public repository is
`https://github.com/Cent-Capital/VaultLedger`, with project metadata pointing to
`https://cent.capital`. VaultLedger is now distributed under Apache-2.0.

This amendment changes neither the Phase 16 design nor its privacy boundary. Real user
documents and every derived index, graph, projection, and trace remain outside the public
working tree.
