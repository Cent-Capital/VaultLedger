# Roadmap re-sequence — ship the product, then judge it, then pitch it

Opened 2026-08-11 · Owner decisions · Supersedes the SPEC §16 phase order

## The decisions

1. **Re-sequence.** Build the shippable app first, run the model bake-off against the
   finished system, and produce the internship/portfolio artifacts last.
2. **Distribution: browser UI plus a one-click local launcher, not a native shell.**
   The native Tauri/Electron shell is **deferred**, not cancelled.
3. **OCR: `ocrmypdf` preprocessing with a provenance flag**, so scanned documents work
   but never masquerade as clean text-layer extractions.

Re-ordering SPEC phases requires **ADR-0011** before any code moves. It must record the
new order, that ADR-0003's "judge models against the finished system" reasoning
*supports* this change, the distribution decision below, and what is given up: the
portfolio artifacts land last, so there is a longer window with no recruiter-facing
summary.

## Why the native shell was dropped

The UI technology was never the constraint. **Every path that runs the real product
requires Ollama plus multi-gigabyte model weights on the recipient's machine.** A Tauri
shell does not remove that dependency; it only changes which window the app appears in.
It would have added a Python-sidecar bundle — the largest technical risk in the
roadmap — for polish rather than access.

Correction to an earlier assumption: **unsigned apps are not blocked outright.** macOS
allows opening them via System Settings → Privacy & Security → "Open Anyway". The $99
Apple Developer account buys frictionless distribution, not possible distribution. With
the browser-UI decision, no Apple account is needed at all. If the native shell is ever
revived, the signing question returns with it.

## What is already true and must not be re-litigated

- **The pipeline creates relationships; Obsidian only displays them.** Obsidian has no
  extraction engine — it renders `[[wikilinks]]` VaultLedger already wrote. ADR-0008
  fixed Obsidian as a projection, never the retrieval backend, and that holds.
  Retrieval resolves back to original Phase-2 chunks so the citation verifier keeps
  working; retrieving from the markdown projection would lose page and character
  provenance and break the product's safety claim.
- **Ingest is already folder-configurable.** `cfg.paths.pdfs` plus a `*.pdf` glob.
- **Evals stay on synthetic data.** Real user files have no ground truth and cannot
  join any eval population. Every metric keeps its synthetic denominator.

## Phase 16 — live documents, safely

**The safety requirement comes first and is not negotiable.** The repository is public.
Real financial documents must live **outside the repo** (default `~/VaultLedger/Inbox`),
configured by absolute path. A gitignored subdirectory is not sufficient: one
`git add -f` or one misconfigured tool publishes the owner's bank statements. Same for
any Obsidian vault holding real data.

Build:
- An inbox path in config, defaulting outside the repository, with a **startup check
  that refuses to run if the inbox resolves inside the repo working tree.** Build this
  first, not as later hardening.
- Real-PDF ingest for text-layer PDFs.
- **OCR via `ocrmypdf --skip-text` as a preprocessing step**, gated on the `needs_ocr`
  flag that `ingest/parse.py:48` already sets. This adds an invisible text layer to
  scanned pages only, so the existing pdfplumber path, offsets, chunking, and citations
  work unchanged. Do **not** take SPEC FR1's in-parser `pytesseract` route; it costs
  several days reconstructing word geometry for the same result.
- **A provenance flag on OCR-derived documents**, surfaced in the UI, because of two
  product-specific risks that deserve their own ADR (**ADR-0012**):
  - OCR is weakest on digits. A misread account number or amount produces a
    confidently wrong answer with a *valid* citation — the verifier passes it, because
    the text really does say that. This is a silent-failure mode the current
    architecture cannot catch.
  - Statement parsing uses word geometry; layout A distinguishes debit from credit by
    column position. OCR geometry is approximate, so scanned statements may misclassify.
  - OCR'd pages must never enter an eval population.
- A folder watcher that ingests on drop and updates index and graph incrementally.
  The full LightRAG build took 45 minutes for 60 documents, so incremental insert is
  the only workable path and its per-file cost must be measured.
- A visible boundary in the UI between synthetic corpus and user files.

**AC:** a real document dropped into the inbox is ingested, indexed, answerable with
verbatim citations, and visible in the graph, with no real-data path inside the repo;
a scanned document is OCR'd, flagged, and visibly marked in any answer that cites it.

## Phase 17 — packaging and handoff

The target recipient is **non-technical**. Optimize for what they actually have to do,
not for how the app is built.

Build:
- **A 3-minute demo video.** This is the artifact that will actually be consumed. Build
  it regardless of everything else.
- **A one-click launcher** — a `.command` or small wrapper that starts the backend and
  opens the browser UI, so the recipient never opens a terminal.
- **A first-run flow** that detects Ollama, links to its `.dmg`, and pulls the pinned
  models with visible progress.
- **Pin `qwen3:8b` (5.2 GB) for the demo path** — the evaluated primary. The owner
  accepts the longer first-run download in exchange for the demo running the same model
  the committed metrics describe. Do not substitute `qwen3:4b` to save download time:
  that would make every quoted number describe a different model than the one running.
- A short setup README written for someone who has never used a terminal.

**AC:** a non-technical person, given a link and a README, reaches a working local
install and answers a question over their own document without direct help.

## Phase 18 — the model and decoding bake-off

SPEC's Phase 17, moved after the app, and **extended** to cover the gap found in review.

The gap: `temperature` is hardcoded `0.0` as a Python default in four call sites and is
**not a config knob**, violating the repo's own "every knob routes through `config.py`"
rule. `top_p` is **never set anywhere** — Ollama's default applies silently. No decoding
sweep exists in any phase's acceptance criteria.

Build, in this order:
1. Promote `temperature` and `top_p` to typed config, defaulting to today's effective
   values, so the change is provably behaviour-neutral before anything is swept.
2. The six-model lineup: two families, three sizes, sizes taken from `ollama show`
   parameter counts, never from tags or disk size — ADR-0008 already caught that
   `gemma4:e2b` is 7.2 GB on disk but 5.1B parameters. Qwen currently has only two sizes
   installed; a third must be pulled and may not fit in RAM. Record the shortfall
   honestly if it does not.
3. A decoding sweep over the pinned model, with the grid and decision rule
   **pre-registered before running**, per the Phase-15 precedent.
4. The latency–quality frontier visualization, harness-generated, never hand-edited.

**AC:** a RunManifest per cell; a generated artifact answering which model and which
decoding settings win *and why*; a null result reported honestly if they cluster. A null
on temperature is a good outcome — "measured, no material effect, kept 0.0 for
determinism" is a sentence the project currently cannot say.

## Phase 19 — portfolio, demo, internship artifacts

SPEC's Phase 16, moved last: comparison report, Pareto sequence, ADR set, demo v2, blog
draft, final full regression.

**Constraint carried from ADR-0010:** none of this may upgrade Phase 15's failed quality
gates into successes. The strict 73.3% entity recall, the 13.6% precision with fabricated
account nodes, the underpowered B-vs-C comparison, and the inconclusive context-budget
arm all travel into the portfolio as they are.

## Immediate items, before Phase 16 opens

- [ ] **ADR-0011** — the re-sequence and the distribution decision.
- [x] **Push.** Done: `origin/main` at `d01ecb4`, fully synced.
- [ ] Confirm `ocrmypdf`/Tesseract is acceptable as an added install dependency for the
      one-click launcher, or scope OCR to the owner's machine only for v1.
