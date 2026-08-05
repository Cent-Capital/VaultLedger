# Track-A demo v1

`vaultledger_track_a_v1.gif` was recorded from a live browser walkthrough and
committed in `c376b44`. It is a visual demo, not an eval artifact; every measured
claim shown in it comes from a committed RunManifest under `reports/`. About two
seconds of the credit-score query's roughly nine-second spinner are shown at 4x
speed; the rest is continuous real time and the on-screen trace latency is
unaltered.

> **Out of date as of 2026-08-05 (ADR-0003 amendment).** The recording shows a
> Local / Cloud-Boosted privacy radio. Phase 11 retired the paid tiers and
> removed that control, so the app no longer matches this GIF. The answer,
> citation, abstention, and eval content it shows are all still accurate.
> Re-record at the next demo revision — do not describe the artifact as current
> until then.

## Re-recording script

1. Run `make doctor`, then `make run`.
2. Open the Library tab. Show 60 parsed documents, zero failures, local Chroma
   and BM25 indexes, and the synthetic-data notice.
3. Open Ask in Local mode. Ask:
   `What was Marcus Chen's March closing balance?`
4. Show the green "Data stayed on your machine" badge, `$4,207.55`, the verified
   March-statement citation, and the local trace footer.
5. Open Evals. Show the measured dense-to-hybrid recall/MRR deltas, validated
   judge TPR/TNR, adversarial pass rate, and green regression gate.
6. End on the Track-A boundary: Experiment Lab is clearly labeled as the
   post-internship expansion beginning in Phase 11.

The expected answer is an existing SPEC-by-example fixture, not a live-demo
claim invented for the recording. If the live model abstains or produces an
unverifiable citation, keep that outcome visible and re-run only after recording
the failure as a real reliability finding.
