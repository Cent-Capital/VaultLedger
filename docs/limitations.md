# Limitations

What is measured, what is not, and what must never be claimed on this evidence.

This page exists because the project's value is the accuracy of its claims. Overstating one
result costs more than the result was worth.

## Claims that must never be made

| Never say | Say instead | Why |
|---|---|---|
| "The best available local model" | **"Measured against five alternatives across two families and three sizes; none beat it"** | ADR-0016. `p=0.754` on ten discordant rows is absence of evidence, not equivalence. |
| "Variant D beats Variant B" | "Variant D beats Variant B **on `qwen3:8b`**; it regressed on `qwen3:4b`" | The AC was met on one model and failed on the other. The split is the result. |
| "≤5% over-refusal achieved" | **"0 of 6 benign queries were over-refused; not meaningfully tested"** | At n=6, zero failures only bounds the true rate at 39.3%. One failure would be 16.7%. |
| "Phases 0–18 closed" | "Phases 0–16 closed; **Phase 17 closed on a waiver (ADR-0013)**; Phase 18 closed" | ADR-0013 waives a gate that was **never attempted**. |
| "Installs cleanly on a fresh Mac" | "The clean-virtualenv path is verified; **the fresh-account install has not been run**" | The forbidden sentence, named as forbidden in ADR-0013. |
| "$0 cost" / "free" | **"$0.00 — unpriced, not free"** | Phase 18 alone spent 4.8 hours of local inference. |
| "100% injection resistance" | "`injection_pass_rate 1.0` over **11 examples**" | 10 unanswerable rows plus one poisoned document. |
| "Entity recall 100%" | **"11/15 = 73.3% strict, which MISSED the 80% gate."** The 15/15 alias figure is a **post-hoc secondary diagnostic** | ADR-0009 was written after seeing the strict result and says so. |
| "The judge is 100% accurate" | "TPR/TNR 1.00 on 20 clear boundary cases, supporting only an **≥83% accuracy** claim" | A null classifier scores 19/20 on that set. |
| "Routing accuracy 90%+ achieved" | **"Met in form only"** | The labels are the router serialised; the metric cannot fail by construction. |
| "OCR works" | "The OCR **pipeline** works end to end with provenance intact" | One cleanly *rendered* page. No accuracy measurement exists. |
| "The failure Pareto shrinks" | "48 → 48 → 47 on the shipped arm; 49 → 49 → 55 on 4B — **not supported**" | The artifact computes and states this itself. |

## Structural limits of the evidence

**The corpus is 60 synthetic documents.** Every quality number describes that corpus. High
recall@20 is partly a property of retrieving a third of the corpus at once.

**There is exactly one chunk per document** at the configured 600-token budget. So
chunk-level and document-level retrieval are the same thing here, and the system has never
been tested on finding the right *passage* inside a long document. Flagged in Phase 2 with
the remedy (shrink `chunking.max_chars` and re-run); never exercised.

**User documents never enter a metric denominator.** By design (ADR-0011/ADR-0012). Every
committed number describes the synthetic corpus only.

**No hosted or frontier model was ever called.** This project measures **local models only**
and says nothing about how open-weight hosted or frontier models perform on the task.
ADR-0003 records that as a scope boundary that was given up deliberately.

**Single runs, not distributions.** Each bake-off and sweep cell ran exactly once. Row-to-row
spread inside a cell is large (`qwen3:14b`: a 188 s row against a 27 s median).

**The judge shares a model with the product.** The LLM judge is the same local `qwen3:8b`
that generates answers, so judge and system share failure modes, and every paired test
inherits any systematic bias in it.

## Open product defects

**1. Citation verification confirms existence, not support.** `verify_citations` checks a
snippet appears verbatim in a retrieved chunk. It never checks that the snippet *supports*
the claim. Demonstrated concretely: on `gs_005` an answer listed seven merchants, of which
`CVS Pharmacy` appeared in **no** surviving snippet and reached the output behind two
technically valid citations. The judge caught it; the guard stack did not.

This is the **largest known open lever**. Two preregistered attempts were rejected —
ADR-0019 (insufficient paired wins) and ADR-0021 (28 false positives across a 1,040-row
replay). The natural next candidate is a local entailment pass: **stricter, not looser.**

**2. Abstention fires whenever zero citations survive.** Combined with defect 1, the system
can retrieve the right page, fail to establish support, and refuse a question it had already
answered correctly. `FALSE_ABSTAIN` accounted for **five of the ten rows** separating the top
two models in the bake-off.

**3. Variant D answered an unanswerable question.** On `ua_007` it produced *"Priya Raman
uses a checking account with Cascade Credit Union, with account number ****3390."* **Every
guard passed it.** A real safety regression against Variant B's 10/10. Recorded, not fixed.

**4. The agent's `sql` tool fails 39–47% of planner calls.** It is *secure* — subquery,
`UNION`, CTE and `sqlite_master` exfiltration are all blocked by the SQLite authorizer's
default-DENY — but the planner cannot write queries it accepts. `qwen3:4b` issued 135 sql
calls across 26 questions, which is how it burns its step budget.

**5. An empty SQL result is still readable as negative evidence.** Two model-facing wording
contracts were rejected (ADR-0022, ADR-0024) and ADR-0023's stop rule forbids a third. The
fix moves to schema work: an explicit person relationship joining invoices and 1099s.

**6. Variant C's extractor fabricates account identifiers.** The local 8B extractor minted
account entities from a ZIP code (`07302`) and a net-pay amount (`2,525.39`), plus two that
appear nowhere in the corpus. For a privacy-first financial product this is more consequential
than the missed recall gate. **Variant C is not promotable** until a new preregistered
extraction run discharges it.

**7. Typed-relation recall reads 0/15 and is near-uninformative.** Ground truth uses typed
predicates; LightRAG emits keyword bags. Exact triple matching cannot cross the vocabularies.
**Never read this as "no correct relations."**

## Measurement debt

| Debt | Consequence |
|---|---|
| The ~60-case over-refusal probe set does not exist | Over-refusal stays "0 of 6, not meaningfully tested" |
| Latency cannot rank models in this harness | No latency ranking may be stated; the frontier chart is descriptive only |
| `routing_accuracy` is met in form only, **and the category→tier map is contradicted on 44 of 80 rows** | Not reportable as a passing AC. A held-out routing set is owed |
| `golden_hash` covers the whole golden-set file | A metric-irrelevant edit will trip the regression guard again |
| L2 (retrieval widen-retry) has never fired | Zero of 19 abstentions were below `rerank_tau`; the trigger does not occur on this corpus |
| No Langfuse span has reached a Langfuse project | Adapter API usage is verified; delivery is not |

## Handoff debt

1. **Phase 17's machine half has never been run** — no fresh macOS Administrator-account
   install, no `receipts/phase17_machine_half.md`, checklist A5–A7 open.
2. **No independent non-technical reader has done the five-minute README cold read.**
3. **The launcher's python.org branch has never executed** — the "clean" venv used
   Homebrew's Python, while `/usr/bin/python3` on the build machine is below the launcher's
   own ≥3.11 gate.
4. **Gatekeeper risk is unverified.** The expected failure mode is a documented extra step —
   *that expectation is reasoning, not a measurement.*
5. **Demo v2, the internship report, and the blog draft** are not started.

## Unexplained

One `make run` process exited with **signal 11** after the server was already serving. No
Python traceback, no crash report captured, never reproduced. `torchvision` is absent while
`transformers` expects it — an inconsistent dependency state in the same native stack.

**That is an observation, not a diagnosis**, and the build log declines to offer one.

## Why this page exists

Every claim in this repository is tied to a manifest, and every rate is reported with its
denominator. The habit that produces that is simple and worth keeping:

> Report the numerator, the denominator, the population, and the bias direction — and state
> what the number does not prove **in the same breath as the number**.
