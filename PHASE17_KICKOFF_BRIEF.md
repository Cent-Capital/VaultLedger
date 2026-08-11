# Phase 17 kickoff — packaging and handoff

Opened 2026-08-11 · Implements ADR-0011 · For Codex

## Entry state (verified, not assumed)

Phases 0–16 closed, tree clean at `c8609a3`, pushed. `make test` 167 passed,
`make lint` clean, `make doctor` 7/7. Phase 16 closed by running its gate, not by
waiver — do not open Phase 17 by weakening that.

## The goal, stated as the person you are building for

The recipient is **the internship hiring manager: non-technical, busy, on their own
Mac.** Optimise for what *they* have to do, not for how the app is built.

**Acceptance is behavioural:** a non-technical person, given a link and a README,
reaches a working local install and answers a question over their own document
without asking for help.

**That criterion splits in two, and only one half is testable here.** The owner has
no willing test subject, so do not treat the whole thing as a blocker and do not
claim it was met.

- **Machine half — required, and fully testable alone.** Prove a machine that is not
  the build machine reaches a working install. A **fresh macOS user account** is the
  route: no venv, no repo, no model cache, no PATH additions, no Streamlit config.
  It does not catch a missing Homebrew, which is system-wide at `/opt/homebrew` —
  record that gap rather than papering over it. This half must pass.
- **Human half — required to be *attempted*, not to succeed.** The cheap proxy is a
  cold read: give the README to any non-technical reader and ask only "what would
  you do first, and where would you stop?" No install, five minutes. If even that is
  unavailable, `PROGRESS.md` says plainly that no independent reader has seen the
  instructions. The first real non-technical user will be the hiring manager at
  handoff — which is exactly why the machine half must be airtight.

Never write "installs cleanly on a fresh Mac" unless a fresh environment actually
ran it. "The launcher works on the development machine and on a clean user account;
no independent person has attempted the install" is true, useful, and the standard
this repo holds everywhere else.

## Scope decisions already made — do not re-litigate

- **Browser UI plus a one-click launcher.** The native Tauri/Electron shell is
  deferred (ADR-0011). The UI was never the constraint; Ollama plus multi-gigabyte
  weights is, and a native shell removes none of it.
- **No Apple Developer account, no notarisation.** Not needed under this decision.
- **Demo pins `qwen3:8b`**, the evaluated primary. Do not substitute `qwen3:4b` to
  save download time: every committed metric describes 8b, and a demo running a
  different model than the numbers describe is the kind of quiet mismatch this repo
  exists to avoid. The owner has explicitly accepted the longer first-run download.

## Work packages

### 1. The demo video

Build it first and treat it as a deliverable, not a byproduct. A busy non-technical
person will watch three minutes and may never install anything, so this is the
artifact most likely to be consumed. It must show the citation trail and at least
one abstention — the product's honesty is the story, not its answer count.

### 2. One-click launcher

A `.command` or equivalent wrapper that starts the backend and opens the browser UI.
The recipient must never type a terminal command. Handle the case where it is
double-clicked twice, and where port 8501 is already in use.

### 3. First-run flow

Detect Ollama; if absent, link the `.dmg` and stop with a readable message rather
than a traceback. Pull `qwen3:8b` and `nomic-embed-text` with **visible progress** —
a silent ten-minute wait reads as a hang. Detect `ocrmypdf`/Tesseract and degrade
explicitly: scanned PDFs must fail with a clear message, never a silent empty
document (ADR-0012).

### 4. Two audit items folded in from the pre-Phase-17 review

- **Commit a clean-virtualenv install transcript.** PROGRESS has flagged its absence
  for several phases: "evidence that a clean virtualenv install succeeds from
  scratch; nobody has committed that transcript." Phase 17 is exactly where that
  stops being acceptable, because "a stranger can install this" *is* the phase's
  acceptance criterion. Run it from a genuinely clean checkout and venv and commit
  the receipt.
- **Extend `make doctor` to check the OCR toolchain.** It is already the "can this
  machine run it" gate at 7/7 and currently says nothing about `ocrmypdf` or
  Tesseract. A non-technical recipient needs one command that tells them plainly
  what is missing and what that costs them.

### 5. Setup README for a non-technical reader

Written for someone who has never opened a terminal. State the download size and the
expected wait up front — an unexplained ten-minute pause is the most likely point of
abandonment. Say plainly which documents work (text-layer PDFs always; scans only
with the OCR tools installed) and that answers from scans carry a visible warning.

## Boundaries that must hold

- **No live/user path may resolve inside the repository.** The startup check exists;
  do not add a packaging path that bypasses it.
- **Evals stay synthetic.** `assert_evaluation_corpus` must keep refusing user and
  OCR-derived chunks. Packaging must not introduce a path that indexes user
  documents into `data/index`.
- **The synthetic corpus hash must stay `ba7148a112191bc8…`.** Chunk writers use
  `model_dump_json(exclude_defaults=True)` for exactly this reason; if a packaging
  change moves that hash, every committed receipt silently loses its link.
- **No accuracy claims for OCR.** The scan arm proved the pipeline carries
  provenance, on one cleanly rendered page. It is not an accuracy measurement.

## Acceptance

- [ ] Demo video exists and shows citations plus an abstention.
- [ ] Launcher starts the app with no terminal use; double-click and busy-port cases
      handled.
- [ ] First-run flow detects Ollama and the OCR tools, shows pull progress, and fails
      readably rather than with a traceback.
- [ ] `make doctor` reports OCR toolchain status.
- [ ] A clean-virtualenv install transcript is committed.
- [ ] README is readable by a non-technical person and states download size and wait.
- [ ] `make test` and `make lint` green; synthetic corpus hash unchanged.
- [ ] **Machine half proven:** the install completed from a fresh macOS user account,
      with the transcript committed and the Homebrew gap noted.
- [ ] **Human half attempted and reported truthfully:** either a cold-read finding
      from a non-technical reader, or an explicit statement that none was available.
- [ ] An honest `PROGRESS.md` entry that distinguishes the two halves. An untested
      install claim is the exact thing this phase is supposed to eliminate.

## Not in scope

Native shell, code signing, hosted demo, and any change to Phase 15's recorded
results or Phase 18's bake-off.
