# VaultLedger documentation

Local-first financial-document Q&A with verified citations and a manifest-backed
evaluation harness.

## Start here

| You are | Read, in this order |
|---|---|
| **Taking ownership of this repo** | [handover.md](handover.md) → [limitations.md](limitations.md) → [architecture.md](architecture.md) |
| **A new engineer on the project** | [getting-started.md](getting-started.md) → [architecture.md](architecture.md) → [evaluation.md](evaluation.md) |
| **Contributing a change** | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) → [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) → [`../SECURITY.md`](../SECURITY.md) |
| **Reviewing the evidence** | [evaluation.md](evaluation.md) → `reports/variant_matrix.md` → `reports/adr_index.md` → `PROGRESS.md` |
| **Just trying to run it** | [getting-started.md](getting-started.md), then `make doctor` |

## The pages

| Page | What it covers |
|---|---|
| [handover.md](handover.md) | Project status, the four conventions that will bite you, and the 14 open debts |
| [getting-started.md](getting-started.md) | Prerequisites, install, the corpus build, every `make` target |
| [architecture.md](architecture.md) | The pipeline end to end, the four retrieval variants, where each model is used, the loop inventory, the guardrail stack |
| [evaluation.md](evaluation.md) | The golden set, every metric with its population and bias direction, run manifests, the regression runner |
| [limitations.md](limitations.md) | What is measured, what is not, and what must never be claimed |
| [briefs/](briefs/) | Archived phase working documents, and a path-reference note |

## The primary record — not superseded by these pages

These four files are the source of truth. The pages above are navigation aids for them.

| File | What it is | Rule |
|---|---|---|
| `SPEC.md` | The original design spec | **Read its ACTIVE DEVIATIONS banner first** — eleven items in the body are superseded by ADRs |
| `PROGRESS.md` | The honest build log, one entry per phase | **Append-only.** No backdating, no compressing |
| `decisions/` | 24 Architecture Decision Records | **Amended, never rewritten** |
| `reports/` | ~200 committed run manifests and generated reports | **Load-bearing** — paths are hard-coded in code and cited in ADRs. Do not reorganise |

## Generated artifacts

Produced by their generators from committed manifests, **never hand-edited** — tests
assert this. Regenerate rather than editing.

| Artifact | Command |
|---|---|
| `reports/model_matrix.md` | `make matrix` |
| `reports/variant_matrix.md` | `make variant-matrix` |
| `reports/failure_pareto.md` | `make failure-pareto` |
| `reports/adr_index.md` | `make adr-index` |
| `reports/guardrail_eval.md` | `make guardrails-eval` |
| `reports/routing_frontier.md` | `make router-eval` |

## The one-sentence version

> Reliable AI systems are not established by one convincing answer. They are established by
> controlled data, traceable transformations, explicit contracts, bounded loops,
> component-level measurement, preregistered decision rules, retained failures, and
> comparable runs — and by writing down, in the same breath as every number, exactly what
> it does not prove.
