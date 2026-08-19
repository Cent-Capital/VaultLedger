# Phase 10 close-out brief

Starting point: commit `96738d0`, clean tree, 85 passed, ruff clean.
`PROGRESS.md` currently records Phase 10 as `— OPEN`.

The owner records the demo. Codex does everything else below. Do not build
browser-automation or video-capture tooling — an automated capture is a new
dependency and a worse artifact than a human walkthrough.

---

## Owner: record the demo (~10 minutes)

Follow `demo/README.md` exactly; it is already committed and is the script.

1. `make doctor` — confirm 7/7 before recording. Do not record a broken run.
2. `make run`, then screen-record while walking the six steps: Library →
   Ask in Local mode (`What was Marcus Chen's March closing balance?`) →
   the green "Data stayed on your machine" badge, `$4,207.55`, the verified
   citation and trace footer → Evals (retrieval deltas, judge TPR/TNR,
   adversarial pass rate, green regression gate) → end on the Track-A boundary
   with Experiment Lab labelled as Phase 11+ scope.
3. Save as `demo/vaultledger_track_a_v1.gif`. Keep it under ~10 MB; if a full
   walkthrough is larger, trim to the Ask and Evals segments rather than
   committing a heavy binary.

Two things the committed script already says, and that hold on the day:

- The expected answer is a SPEC-by-example fixture, not a claim invented for
  the recording.
- If the model abstains or produces an unverifiable citation, keep it in and
  record it as a real reliability finding. Do not re-roll until it looks good.
  A demo that shows the system refusing to guess is a better artifact for this
  product than one that hides it.

## Codex: close-out tasks

### 1. Flip Phase 10 to closed in `PROGRESS.md`

Only after `demo/vaultledger_track_a_v1.gif` exists in the repo.

- Remove `— **OPEN**` from the Phase 10 heading.
- Change the demo AC from "not met" to met, and state in one line what the
  recording actually shows — including any abstention or citation failure that
  was left in.
- Update the "Honest boundaries" first bullet, which currently says the phase
  is open.
- Leave the other honest boundaries untouched and true: the judge labels are
  calibration labels not yet human-adjudicated, no Langfuse span has reached a
  Langfuse project, hosted cost is estimated with unpriced rates.

### 2. Update the README status

It currently says the phase "remains open until the real browser walkthrough is
recorded." Replace with the closed state and link the demo artifact. Do not
upgrade any of the three constrained claims above while doing it.

### 3. Optional but recommended — close the fresh-machine AC properly

That AC is recorded as *partially* met because no clean-virtualenv transcript is
committed. To close it fully: fresh `git clone` into a temp directory, fresh
venv, follow the README verbatim end to end, and commit the transcript (plus
wall-clock time and any step that needed fixing) as `demo/fresh-checkout.md` or
similar. If any step fails, fix the README and re-run from a clean clone.

If this is skipped, leave the AC recorded as partially met. Do not upgrade the
wording without the transcript.

### 4. Re-verify and record measured numbers

Run `make verify-track-a` and put the *measured* result in the PROGRESS
Verification block — exit code, wall clock, test count, safety counts,
judge TPR/TNR, regression pass. Do not copy the figures already in the entry;
they are from a 2026-07-30 review run and must be re-measured at the closing
commit.

### 5. Commit with a real message body

The two Phase 10 commits (`7689f79`, `91c41b8`) shipped with bare subject lines
and no body, which is why the phase ended up with no written record and needed
`96738d0` to repair it. One commit, subject plus body, in the style of the
Phase 6-9 commits: what changed, what was measured, what remains unclaimed.

## Not in scope for closing the ACs

- The **internship report draft** is Phase 10 scope in SPEC but not an AC, and
  per `CLAUDE.md` it belongs in `~/Desktop/PM-OS`, not this repo. Flag it as
  outstanding rather than writing it here.
- The **judge-label review** (owner) and **Kimi/GLM rates** are deliberately
  deferred to Phase 11. Do not touch `human_labels.yaml` or
  `regression_baseline.json`.

## Definition of done

- [ ] `demo/vaultledger_track_a_v1.gif` committed
- [ ] PROGRESS Phase 10 heading no longer marked OPEN; demo AC recorded as met
- [ ] README status updated; the three constrained claims unchanged
- [ ] `make verify-track-a` re-run and its measured result recorded
- [ ] Fresh-checkout transcript committed, or the AC left recorded as partial
- [ ] One commit, with a body
