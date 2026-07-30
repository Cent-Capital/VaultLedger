# Track-A demo v1

Recording target: `vaultledger_track_a_v1.gif`. The artifact is not present
until a real browser walkthrough has been recorded. It is a visual demo, not an
eval artifact; every measured claim shown in it must come from a committed
RunManifest under `reports/`.

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
