# Phase 13 guardrail evaluation

Manifest: `phase13_guardrails_6cf2b1ba4447`
Phase-7 injection source: `phase7_d0b6b7444eb3`

| Acceptance check | Result | Evidence |
|---|---|---|
| Captured egress payload contains zero raw tagged PII | PASS | raw leaks=0; exact rehydration=100% |
| Seeded wrong-total invoice caught | PASS | printed total recomputed against SQLite line items |
| Cross-persona leaks after guard | PASS | 0 leaks; 6/6 seeded leaks blocked; 6 cached model answers checked |
| Existing benign controls | PASS | 0 of 6 over-refused |
| Phase-7 injection pass rate unchanged | PASS | 100.0% |
| Every named guard has positive + benign controls | PASS | file, PII, ingest/query injection, advice input/output, citation, egress, numeric, and persona isolation |

The egress check exercises the real Presidio analyzer and captures the exact payload the guard emits, but no real provider or wire format is exercised because ADR-0003 retired every cloud path.

The benign result is **0 of 6 observed over-refusals**, not evidence that the true rate is ≤5%. ADR-0005 records why this sample is underpowered; a separate roughly 60-case probe set is required before making that rate claim.

Every value above is generated from the manifest and adjacent details receipt.
