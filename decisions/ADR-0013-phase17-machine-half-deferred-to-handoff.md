# ADR-0013: Close Phase 17 on a waiver; run the machine half immediately before handoff

2026-08-12 · Status: **accepted** (owner decision)

## Context

Phase 17's kickoff brief made the machine half a hard gate:

> **Machine half — required, and fully testable alone.** Prove a machine that is not
> the build machine reaches a working install. A **fresh macOS user account** is the
> route. This half must pass.

It has not been performed. `receipts/phase17_clean_install.md` is a new virtualenv on
the build machine under the same user, and says so plainly. The code half is complete
and verified: launcher acceptance repairs (Gatekeeper instructions, first-run corpus
bootstrap, cancellation handling, service-first Ollama detection), the four stale
reader-facing claims corrected at their generators, the context-budget defect fixed
with a regression test, and `make verify-track-a` green at `b69499a` after a first run
that failed and was retained.

Two further findings sharpen what the run would test. A second account on this Mac
still shares `/opt/homebrew` and `/Applications/Ollama.app`, so neither is covered.
But a brand-new account has no `~/.zprofile` Homebrew PATH entry, so the launcher's
interpreter probe will likely see only `/usr/bin/python3` — 3.9.6 here, below its own
≥3.11 gate — and exercise the python.org branch, which has never run.

A review recommended splitting the run: a ten-minute Gatekeeper smoke test now,
because an unsigned `.command` that Finder refuses would reopen ADR-0011's
distribution decision rather than merely invalidate a receipt; and the full run before
handoff, because Phase 18 may move the pinned model and with it the download size, the
wait, and the first-run flow.

## Options

**Run the full machine half now.** Meets the gate as written. Rejected by the owner:
Phase 18 may change the pinned model, which would invalidate the receipt and force a
second run, and the owner's priority is a finished product before any validation pass.

**Run the ten-minute smoke test now, defer the rest.** The review's recommendation.
Rejected by the owner on the same grounds — the validation pass happens once, at the
end, as a single block of work.

**Defer the whole machine half to immediately before handoff.** Chosen.

## Decision

**Phase 17 closes on a waiver.** Its machine half is deferred in full — including the
Gatekeeper smoke test — to a single validation pass performed immediately before the
product is shown to its intended recipient.

This follows **ADR-0010**'s precedent for Phase 15, with one difference that must not
be blurred. ADR-0010 waived a gate that was *measured and missed*: entity recall was
73.3% against an 80% threshold, and the number exists. **This ADR waives a gate that
has not been attempted.** That is the weaker of the two, and every document touching it
must say so in those terms.

**No document may describe the machine half as met, partially met, or approximated.**
The clean-virtualenv receipt is not relabelled. `README.md:56-62`, which already
separates what was verified from what was not, stands as written. The forbidden
sentence from the kickoff brief — *"installs cleanly on a fresh Mac"* — remains
forbidden.

**The deferred work is fixed, not open-ended.** `PHASE17_CLOSE_CHECKLIST.md` Parts B
and C define it, and checklist items A5–A7 (stale-lock `FileExistsError`,
`SO_REUSEADDR` plus one bind retry, `explain_ocr` grammar) travel with it, since they
are launcher defects a fresh-account run is likely to surface.

## Consequences

**The distribution decision carries unverified risk until the end.** If Gatekeeper
blocks the documented ZIP → double-click path for a non-technical user, ADR-0011's
browser-UI-plus-launcher decision reopens at the worst moment, and its deferred
alternative — a native shell, code signing, a $99 Apple Developer account and
notarisation — has no schedule left. The owner accepts this. The mitigation is that
`README.md:33` and the launcher troubleshooting already document the right-click →
Open path, so the failure mode is a documented extra step rather than an unexplained
dead end.

**The bake-off may change what gets validated.** If Phase 18 moves the pinned model
away from `qwen3:8b`, the launcher's pull list, the README's stated download size, and
the demo all change before the machine half runs. That is the point of deferring, and
it means the validation pass must come *after* the pin is final.

**Phase 17 is recorded as closed-on-waiver, not closed.** Any status line that says
"Phases 0–17 closed" without naming this waiver is inaccurate. `CLAUDE.md`'s status
section and the `PROGRESS.md` entry must both carry it.

**The human half is unaffected and remains unproven.** No independent non-technical
reader has performed the five-minute cold read. That stays explicitly stated wherever
it appears, and neither the owner nor any agent substitutes for it.

## Evidence

- `receipts/phase17_clean_install.md:7-9, 99-101` — the existing receipt's own scope
  disclaimer; it does not claim a fresh macOS user.
- `PHASE17_KICKOFF_BRIEF.md:24-39, 119-124` — the machine-half criterion and the
  forbidden sentence.
- `PHASE17_CLOSE_CHECKLIST.md` Parts B, C, D — the deferred work, in full.
- `pyvenv.cfg` of the clean-install venv reads `home = /opt/homebrew/opt/python@3.14/bin`;
  `/usr/bin/python3 --version` on this machine is 3.9.6, below the launcher's ≥3.11 gate.
- `PROGRESS.md` Phase 17 continuation entry — code half complete, `make verify-track-a`
  exit 0 in 150.0s at `b69499a`, corpus hash `ba7148a1…5405` checked at four points.
- ADR-0010 — the waiver precedent, and the distinction this ADR draws against it.
