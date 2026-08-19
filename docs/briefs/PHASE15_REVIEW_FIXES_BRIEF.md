# Phase 15 review — required fixes before Phase 16

Opened 2026-08-11 · For Codex · Source: independent review of `23a52e8..dfb483c`

## Standing verdict

The implementation and the metric discipline are sound. Verified independently, not
read from `PROGRESS.md`: 152 tests pass and Ruff is clean; the alias rule commit
`23a52e8` genuinely contains no numbers; the rule is schema-derived, account-scoped,
and digit-anchored; both score columns reproduce exactly (11/15 = 73.3% / 13.6%
strict, 15/15 = 100% / 18.5% alias, 19/81 = 23.5% node-counted); both eval receipts
carry the same `git_sha`, `config_hash`, `golden_set_hash`, seed, and
`guardrails_enabled`; the citation path resolves graph hits back to real Phase-2
`Chunk` objects; and Obsidian's own vault registry confirms the extracted vault was
opened in 1.13.6 at 16:42 EDT, between `8d4cb3b` and `dfb483c`. ADR-0009 is honest
about its post-hoc status.

Four things need fixing. None of them are "the numbers are wrong." All of them are
"the write-up claims more than the evidence carries," which on this repo is the more
expensive kind of error.

---

## Fix 1 (highest priority) — the B-vs-C headline is one signal reported as two

`PROGRESS.md` states C's margin is "−33.4 percentage points on **both** citation hit
and abstention accuracy," which reads as two independent confirmations.

Check every row of both `_answers.json` receipts: `citation_doc_hit` and
`abstention_correct` are **equal on all 11 scored rows in both arms**. They are not
independent evidence. On this population they are the same fact, because a row that
abstains produces no citation and fails both, and every row that answered cited
correctly.

Reproduce before writing anything:

```bash
python - <<'PY'
import json
for name,p in [("B","reports/phase11_ollama_qwen3_8b_b_hybrid_4a099797b084_answers.json"),
               ("C","reports/phase11_ollama_qwen3_8b_c_graph_f3be41d85c23_answers.json")]:
    rows=json.load(open(p))
    pairs=[(r.get("citation_doc_hit"),r.get("abstention_correct")) for r in rows
           if "citation_doc_hit" in r]
    print(name, "rows scored:", len(pairs),
          "| disagreements:", sum(bool(a)!=bool(b) for a,b in pairs))
PY
```

The result underneath is a single sentence: **C abstained on 4 of 6 answerable rows;
B abstained on 1 and lost 1 to a 180-second connection timeout.** That is B 4/6
versus C 2/6 — a two-row difference.

It is also underpowered. Fisher exact, two-tailed, on 4/6 vs 2/6 gives **p = 0.567**.
A single row flipping moves the margin by **16.7 points**.

**Do:**
- Rewrite the margin paragraph so the two metrics are described as collinear on this
  population, not as two results. State the underlying abstention fact plainly.
- Add the power statement: n = 6, two-row difference, Fisher exact p = 0.567, one row
  = 16.7pp. ADR-0005 already set this precedent when it called the over-refusal AC
  underpowered; apply the same standard here.
- Soften the *decision* language only. "C lost the comparison" and "B remains the
  default" currently read as established. Keep B as the default — that is the right
  operational call on the evidence available — but say it is a provisional default on
  an underpowered comparison, not a demonstrated result.

**Do not:**
- Change any measured number, re-run the comparison hoping for a cleaner margin, or
  drop a metric from the table. The metrics are correct; only their description is
  overstated.
- Delete the citation-hit column. Report it and say it is collinear here.

Optionally add a generic sentence to the matrix report generator explaining that
citation hit and abstention accuracy converge structurally whenever abstentions
produce no citations. If added, it must be generically true, not a description of
this run — that file is generated, never hand-edited.

---

## Fix 2 — the experiment varies two things at once

`vaultledger/evals/matrix.py` gives `C_graph` an `answer_top_n` of **12** and
`B_hybrid` **6**. `PROGRESS.md` frames the larger budget as favoring C. That is one
reading. The other is that a longer, noisier context is what *caused* C's four false
abstentions — in which case the comparison is measuring context budget, not graph
retrieval, and "graph retrieval is worse" is not attributable.

The comparison is cheap to disambiguate: C's six rows took roughly two to three
minutes wall.

**Do — and do it in this order:**

1. **Pre-register the interpretation before running.** Write down, in the commit or
   the PROGRESS draft, what each outcome will mean:
   - C at top_n 6 performs like C at 12 → the budget is not the cause; the graph
     retrieval result stands.
   - C at top_n 6 performs closer to B → the original comparison was confounded, and
     the Phase-15 conclusion must be restated as inconclusive between the two causes.
   This is the same discipline that made the alias rule defensible. Do not run first
   and interpret after.
2. Run the third arm at `answer_top_n = 6`, same model, same golden-set hash, same
   guardrails, clean SHA.
3. Report all three arms. Keep the original two rows exactly as committed.

If you decline to run it, that is acceptable — but then state the confound explicitly
as a limitation in `PROGRESS.md` and say the phase cannot separate graph retrieval
from context budget. Silence is the only unacceptable option.

---

## Fix 3 — an unexplained reversal of Phase 14's artifact policy

`dfb483c` commits regenerated `phase7_d0b6b7444eb3`, `phase9_judge_a40a6497095d`, and
`phase13_guardrails_6cf2b1ba4447`, and moves all three `_latest.json` pointers. I
diffed their metrics against the previously committed runs: **identical in every
metric.** Only `run_id`, `timestamp`, `git_sha`, and `config_hash` differ.

Phase 14's own commit message states the opposite policy:

> "Those are discarded: a verification run is not a phase close, and a second manifest
> carrying the same measurement is noise a future reader has to disambiguate."

There is a legitimate reason to keep them this time — `config_hash` changed, because
`config.yaml` gained the `graph:` block, so these runs prove the older gates still
hold under the Phase-15 config. That is real new information and Phase 14's
regenerations did not have it. **The reason is nowhere in the record**, so what a
reader sees is a silent policy flip.

**Do:** add a short paragraph to the Phase-15 close entry naming the three
regenerated artifacts, stating that their metrics are unchanged, and giving the
config-hash rationale for keeping them where Phase 14 discarded its own. Confirm in
that paragraph that each phase's original close artifact remains committed and
untouched.

---

## Fix 4 — closing on a failed gate needs an explicit, recorded waiver

`CLAUDE.md` states: *"Don't start a phase until the prior phase's acceptance criteria
(SPEC §16) pass."* Phase 15's pre-registered entity-recall AC did not pass, and the
close entry ends with "Next: Phase 16."

Closing was very likely the right call — the miss was a naming artifact, the
fabricated-account finding is worth more than the threshold, and the phase reported
the miss instead of redefining it. The problem is that the waiver is currently
implicit, which turns a strong decision into an apparent process violation.

**Do:** record the waiver explicitly, preferably as **ADR-0010**, since this is a
deviation from a stated build rule and the repo uses ADRs for exactly that. It should
state: which AC failed and by how much; why the phase closed anyway; what would have
to be true to revisit it; and that the waiver covers Phase 15 only and does not
license closing future phases on failed gates.

---

## Minor items

- **Variant C is not reproducible from a clean clone.** The matrix runner requires
  `vdb_entities.json`, `vdb_relationships.json`, and `vdb_chunks.json`, which stay
  gitignored; only the GraphML is committed. A reviewer can re-derive the graph
  *score* but must rebuild the index (~45 min) to re-run the C eval. Add one sentence
  saying so. Committing the vector stores is not requested — the trade-off is right,
  it just needs stating.
- **Both vault exports share `exports/obsidian_vault`.** Identity depends on which
  target ran last. The `Source:` line and the `--replace` guard mitigate this
  adequately; no code change requested, one sentence in the README or PROGRESS is
  enough. Note that the review overwrote the ground-truth vault while verifying the
  extracted export; regenerate with `make graph-vault` if the demo projection is
  wanted back.

---

## Acceptance

- [ ] Margin paragraph rewritten: metrics described as collinear, abstention fact
      stated plainly, power reported (n=6, p=0.567, one row = 16.7pp), decision
      language marked provisional.
- [ ] Context-budget confound either resolved by a pre-registered third arm at
      `answer_top_n = 6`, or stated as an explicit unresolved limitation.
- [ ] Regenerated-artifact rationale recorded and reconciled with Phase 14.
- [ ] ADR-0010 records the failed-gate waiver and its scope.
- [ ] Two minor sentences added.
- [ ] `make test` and `make lint` green; no committed metric value altered; the strict
      73.3% record still intact and un-rewritten.

## What must not change

The strict 11/15 = 73.3% result, the committed receipts, ADR-0009's post-hoc framing,
and the fabricated-account findings. Every fix here is about matching claims to
evidence. None of them should improve a single number.
