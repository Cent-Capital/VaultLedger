# ADR-0003: Model lineup — dropping the paid hosted tiers

2026-08-05 · Status: **accepted**

## Context

SPEC builds the experiment tracks on a three-tier model lineup (Section 7.1,
Section 10):

| Tier | SPEC lineup | Role |
|---|---|---|
| T0 / T1 | `qwen3:4b`, `qwen3:8b` via Ollama | local, free |
| T2 | `kimi-k2.6` (Moonshot), `glm-5.2` (Z.ai / OpenRouter) | open-weight **hosted**, paid |
| T3 | Claude Sonnet-class | frontier closed, paid, opt-in |

That lineup is load-bearing well beyond a config entry. G7 requires the benchmark
to span "≥ 6 models spanning three tiers." G8's cost–quality frontier scatters
quality against **dollars per query**. Phase 11's AC is a `model_matrix.md`
"across ≥ 6 models with cost." Phase 12 scores a router that escalates into
T2/T3. Phase 15 runs entity extraction "once with a T2 model for quality."

The owner has since decided: **no paid LLM APIs, ever.** Kimi is cancelled. That
is a hard constraint, not a preference to be optimised around.

`config.yaml` has not caught up — it still names `moonshot/kimi-k2.6` as T2 and
as `cloud.model`, and `anthropic/claude-sonnet-latest` as T3. Nothing has been
transmitted: `cloud.base_url` is blank, so every Cloud-Boosted request has taken
the pre-egress fallback path since Phase 6. The contradiction is on paper only,
but it sits in the file the whole system reads.

A second decision arrived with the first: the multi-model bake-off should not be
built into Phase 11. The owner wants the gateway built now and the full
comparison run **at the end**, once every variant (B hybrid, C graph, D agentic)
exists, so that all models are compared against a finished system rather than a
half-built one. SPEC currently ends at Phase 16.

## Options

**A. Free-tier hosted access.** Several providers expose free endpoints
(OpenRouter's `:free` variants among them). Preserves a genuinely hosted tier at
zero spend and keeps the router's egress, redaction, timeout, and
degraded-fallback paths exercised against a real remote. But free endpoints are
heavily rate-limited, can be withdrawn without notice, and are often served at
different quantisation than the paid route, so a quality number measured there
does not transfer to the paid model of the same name. Benchmarking against
weights you cannot pin breaks determinism, which is the property the whole
harness rests on.

**B. Local-only lineup; redefine the tiers by capability, not by hosting.** Six
generation models are already installed on the 16 GB dev machine. That satisfies
G7's "≥ 6 models" count today with no new dependency and no spend. What it
cannot satisfy is "spanning three tiers" in SPEC's sense, because every model is
the same tier by hosting. The tier axis has to be redefined as capability/size,
and the open-weight-hosted question SPEC names becomes unanswerable here.

**C. Keep the SPEC lineup; record T2/T3 as unmeasured.** Leaves `config.yaml`
naming Kimi, GLM, and Claude and lets the matrix report those cells as not run.
Does not rewrite the spec and keeps the hosted code path alive for anyone with a
budget later. But it produces a headline artifact — an explicit Phase 11 AC —
that is mostly empty cells, and the cost–quality frontier degenerates to a single
point. A deliverable whose main chart is blank is worse than one that measures a
smaller question well.

**D. Local-only lineup, with the cost axis replaced by a resource axis.** As B,
but confronts the frontier problem directly: with every model free, dollars stop
discriminating and the cost–quality frontier collapses. Substitute a resource
that still varies — median latency per query, or resident model size — and the
chart recovers its shape and its argument. "Quality per second" and "quality per
GB of RAM" are the tradeoffs an on-device product actually faces, and the ones a
privacy-first local-first thesis should be making. The cost is that the chart no
longer answers "is the frontier model worth the money," which was SPEC's framing.

## Decision

**D — local-only lineup with a resource axis replacing the cost axis**, plus a
split of the work across two phases.

**Lineup.** Six models: **two families at three sizes each**, so family and size
vary independently and a difference can be attributed to one or the other. GLM is
dropped — it has no local path (see Rejected below).

**One generation per family.** The sizes must come from a single model generation
within each family. Gemma is installed here across three generations — `gemma`
(9B), `gemma3:4b` (4B), `gemma4:e2b` (5.1B) — and using those as "the Gemma row"
would confound generation with size: a difference could be architecture, training
data, or parameter count, and the design could not separate them. A clean 2×3
requires `gemma3` at three sizes and `qwen3` at three sizes.

**Sizes are recorded as measured, never inferred from the tag.** Every lineup
entry carries the parameter count reported by `ollama show`, not the number in
its name. This is not pedantry: `gemma4:e2b` reports 5.1B despite the "e2b" tag,
and size is an axis on the frontier chart, so a mislabelled row puts a point in
the wrong place. Qwen 3 has no 2B tag in the versions seen, so the originally
requested 2B/4B/8B symmetry is replaced by whatever three real sizes each family
actually ships.

Exact tags are pulled and pinned at **Phase 17 kickoff**, with measured
parameters and resident size committed alongside the manifest — consistent with
SPEC's existing instruction to verify model IDs at build time. Two of the six
(`qwen3:4b`, `qwen3:8b`) are already installed and wired.

**Tiering.** T2 and T3 are **retired** — removed from `config.yaml` and from the
router's allowed-tier sets, so no code path claims a capability the project will
never exercise. T0/T1 keep their meaning.

**Axes.** The cost–quality frontier becomes a **latency–quality frontier**, with
resident model size as a secondary axis. Cost columns stay in the manifest schema
and report `0.0` with the existing "unpriced, not free" wording, so the plumbing
survives if a budget ever appears.

**Phase split.** Phase 11 builds the gateway and the matrix *machinery* against
the two models already wired (`qwen3:4b`, `qwen3:8b`) — enough to prove a
RunManifest per cell and a generated `model_matrix.md`. The full seven-model
sweep moves to a **new Phase 17**, run after Phase 16, once variants B/C/D all
exist so every model is compared against the finished system. Phase 12's router
escalates across local model sizes rather than hosting tiers; its privacy ACs are
unaffected. Phase 15's "T2 model at index time" falls back to the largest local
model that fits, with the quality cost measured rather than assumed away.

**Phase 17 — Multi-model bake-off** (new, appended after Phase 16):
run the full golden set across the final lineup on the finished system; generate
`reports/model_matrix.md` and the latency–quality frontier; surface per-model
judge verdicts *with their `reason` field* so the artifact answers "which model
answered best **and why**," not just which scored highest. **AC:** a RunManifest
per model × variant cell; the matrix and frontier harness-generated, never
hand-edited; a written finding — including a null result if the models cluster.

## Rejected

**Option A (free-tier hosted)** — non-determinism at the endpoint is a worse
failure than a narrower benchmark. Every metric in the harness rests on being
able to re-run and get the same answer.

**Option C (keep the lineup, mark T2/T3 unmeasured)** — an empty headline
artifact fails the AC in substance while appearing to satisfy it in form.

**GLM, in any form.** SPEC's `glm-5.2` is a 744B–1T MoE model: it does not run on
a 16 GB laptop, and hosted access is paid, which the constraint forbids. A free
hosted endpoint would have supplied one row nobody could reproduce, since the
weights behind a `:free` alias cannot be pinned. Six reproducible models across
two families is a better experiment than seven with one unpinnable row. The
consequence is recorded honestly: this project measures **local models only**, and
says nothing about how open-weight hosted or frontier models perform on the task.

## Consequences

**Easier.** Zero spend, no API keys, `$40` budget untouched. The whole matrix is
reproducible by anyone who clones the repo and pulls the same Ollama tags. No
rate limits, no credential handling, no egress review for benchmark runs.
Determinism holds end to end.

**Harder.** The dynamic range narrows — models between ~2 GB and ~7 GB may
cluster, and a matrix where every cell scores similarly is a weaker artifact than
one spanning local to frontier. If they cluster, that null result is reported as
a finding, not hidden. The 16 GB machine caps the top end; `qwen3:30b-a3b` was
already ruled out in Phase 0 for the same reason.

**Deferred, with a cost.** Moving the bake-off to Phase 17 means the model
comparison lands *after* Phase 16 declares the portfolio done. The upside is real
— every model gets judged against the finished system rather than a half-built
one. The risk is equally real: Phase 16's "final Pareto sequence" and DoD go green
without the model matrix in hand, so if Phase 17 never happens, the portfolio
ships without one of its headline artifacts. Accepted deliberately; noted here so
the tradeoff is on the record rather than discovered later.

**Given up explicitly.** SPEC's named question — where open-weight hosted models
land between local and frontier, and whether the gap is worth the cost delta —
cannot be answered by this project. This belongs in the report as a scope
boundary, not omitted.

**Revisit when** a budget appears, a larger-RAM machine appears, or a genuinely
pinnable free endpoint appears. The manifest schema keeps its cost fields for
exactly that reason.

## Amendment — 2026-08-05 (Phase 11 implementation)

**What this ADR originally said:** *"its privacy ACs are unaffected — the
Local/Cloud-Boosted switch and consent flow stay exactly as Phase 6 built them,
with Cloud-Boosted permanently in its pre-egress fallback state."*

**What was actually built:** the switch and consent checkbox were removed from
the app, and the `cloud:` config block and `Cloud` settings class were deleted.

**Amended: the removal stands.** The original clause was wrong. A Local /
Cloud-Boosted toggle with the paid tiers retired is a control that can never do
anything — it advertises a capability the product does not have and cannot
acquire, and a user who selects it learns only that it falls back. Dead UI that
implies a feature is worse product than no UI, and worse *honesty*, which is the
axis this project is optimised on. Keeping a switch purely to satisfy a sentence
in a decision record would be cargo-culting the process.

**What is preserved, deliberately:**

- `vaultledger/route/privacy.py` is untouched. `answer_with_privacy`, the consent
  gate, both degraded-fallback branches, and the conservative
  "data may have left your machine" path all remain, and `tests/test_phase6.py`
  still exercises them. The capability is retired from the product surface, not
  deleted from the codebase.
- **The egress badge must stay derived from `answer.data_left_machine`, never
  hardcoded.** The Phase 11 pass initially replaced the conditional with an
  unconditional success string. That was corrected, and
  `test_privacy_badge_is_derived_from_the_answer_not_asserted` now fails if the
  guard is removed while the badge remains. With one privacy mode the branch is
  currently constant — which is precisely why it needs a test rather than a
  reviewer's memory.

**What this costs, recorded rather than discovered later:**

- **SPEC's Phase 6 AC "badge + `model_used` flip correctly" can no longer be
  demonstrated in the product.** It holds at the unit level — `test_phase6.py`
  calls `answer_with_privacy` directly — but no UI path can show the flip. This
  is a scope reduction, not a passing AC. It must not be reported as
  demonstrated.
- **`demo/vaultledger_track_a_v1.gif` (committed `c376b44`) is now out of date.**
  It shows a Local / Cloud-Boosted radio the app no longer has, and README links
  it as the current demo. Noted in `demo/README.md`; re-record at the next demo
  revision rather than pretending the artifact is current.

## Amendment 2 — 2026-08-05 (the latency axis is not currently measurable)

This ADR replaced the cost axis with **latency**, on the reasoning that with every
model free, dollars stop discriminating while a scarce resource still varies. The
Phase 13 guardrail ablation showed that reasoning is not yet supported by the
measurement it depends on.

Two matrix arms were run over the same 80 rows, guards off and guards on. They
produced **identical answers** — same metrics, same failure sets — yet:

| | off arm | on arm | change |
|---|---:|---:|---|
| `qwen3:4b` p50 | 8579 ms | 3714 ms | **−57%** |
| `qwen3:4b` p95 | 17900 ms | 9592 ms | −46% |
| `qwen3:8b` p50 | 6602 ms | 6908 ms | +5% |

Guards add work; they cannot make a model 57% faster. The off-arm 4B run also
carried a generation timeout that did not recur. Both indicate machine load, not
model behaviour.

**Consequence.** Latency at these magnitudes is environment-dominated. Phase 11
measured ~10% p95 movement and called it noise; this is ~50% p50 movement on
byte-identical outputs. Single-run latency **cannot rank two models 2 GB apart**,
which is precisely what the frontier chart is supposed to do. Two prior
conclusions are therefore withdrawn: Phase 11's "4B is materially faster" and the
Phase 12 entry's correction of it ("8B dominates"). Each rested on one run, and
the runs disagree by more than the effect they claimed to measure.

**Not resolved here.** Fixing it means one of: repeat each cell N times and report
a spread rather than a point; pin machine conditions (no concurrent load, fixed
`keep_alive`, warm model) and record them in the manifest; or replace the x-axis
with something reproducible — resident model size and token counts are both
already captured and are environment-independent. Choosing among these is Phase 17
work and needs measurement, not preference.

**Until then:** the latency–quality frontier must not be presented as a headline
artifact, and no model ranking may be stated on latency grounds. Quality metrics
are unaffected — those reproduced bit-identically across arms and across the
Phase 12 re-run.

## Evidence

- Local models present on the dev machine, measured 2026-08-04/05 via the Ollama
  tags API and `ollama show`: `qwen3:4b` 2.5 GB, `gemma3:4b` 3.3 GB,
  `llama3:latest` 4.7 GB, `gemma:latest` 5.0 GB / **9B params**, `qwen3:8b`
  5.2 GB, `gemma4:e2b` 7.2 GB / **5.1B params**, plus `nomic-embed-text` 0.3 GB.
- Dev machine RAM: 16 GB (`hw.memsize`), consistent with the Phase 0 note that
  ruled out `qwen3:30b-a3b`.
- Measured local throughput (Phase 2, 2026-07-13): `qwen3:8b` 20.4 tok/s,
  `qwen3:4b` 38.5 tok/s.
- No hosted call has ever been made: `cloud.base_url` is blank in `config.yaml`,
  and `vaultledger/route/privacy.py` routes every cloud request to the
  pre-egress fallback when no base URL or key is configured.
- **Not measured:** no quality comparison across local models exists yet. Whether
  they cluster or separate is the open question Phase 17 is responsible for
  answering. Tag availability for the intended sizes is also unverified.
