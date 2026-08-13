# Phase 18 review — fix brief

Opened 2026-08-13 · For Codex · Reviews `234416d..8534069` (ten commits, unpushed)

Scope: seven items. Every one was **reproduced in the review session** on this machine,
and the command that reproduced it is given so you can confirm the failure before you
change anything and confirm the fix after. Items 1–2 are code defects. Items 3–5 are
claim and preregistration corrections that must land **before the first sweep cell
runs**, because after that they cannot be fixed without breaking preregistration.
Items 6–7 are smaller.

Do not widen this brief. The known-open items listed in `PHASE18_KICKOFF_BRIEF.md`
(citation verification, empty-population guardrail passes, agent time budget,
`routing_accuracy` tautology, judge validation power) remain real and remain owed to
their own pass.

**Entry state, measured this session at `8534069`:** `make test` **192 passed** ·
`make lint` clean · `shasum -a 256 data/index/chunks.jsonl` =
`ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405`, unchanged · tree
clean apart from the untracked `Untitled` · `main` is **ahead of `origin/main` by 10
and has not been pushed, so no CI run exists for any Phase 18 commit**.

The PROGRESS entry's "191 passed, 1 environment-dependent skip" reconciles with the 192
here: the single skip is `tests/test_phase2.py:273`, which skips when Ollama is
unavailable and ran in this session. No discrepancy.

**What this review does not dispute.** The infrastructure is sound and the PROGRESS
entry is honest — it states plainly that the experiment has not run and claims no
winner. Verified good, and worth keeping: metric denominators use all 80 examples so
errored rows count against a model (`_cell_metrics`); judge coverage fails loud;
checkpoints are keyed on population, decoding profile and guard arm; the
product/matrix payload-parity test asserts full request equality
(`tests/test_phase11.py`, `assert sent[0][1] == sent[1][1]`), which backs ADR-0015's
claim; `seed` genuinely reaches the generator, meeting that acceptance item; and all
six pinned tags are installed at `Q4_K_M` with parameter labels matching PROGRESS
exactly.

---

## 1. `LightRAGRetriever.from_config` raises `TypeError` — Variant C is broken

**Reproduce:**

```
.venv/bin/python -c "
import vaultledger.generate
from vaultledger.config import load_config
from vaultledger.retrieve.graph import LightRAGRetriever
LightRAGRetriever.from_config(load_config())
"
```

```
TypeError: LightRAGRetriever.__init__() got an unexpected keyword argument 'max_tokens'
```

`vaultledger/retrieve/graph.py:123-124` passes `max_tokens=` and `timeout_seconds=` to a
constructor that declares neither. `__init__` (line 65) gained only `temperature`,
`top_p`, `seed` and `num_ctx`.

This fires on two live paths:

- `app/streamlit_app.py:340` — the Ask tab whenever graph retrieval is selected. This is
  a user-facing crash in the shipped app.
- `vaultledger/evals/matrix.py:263` — `matrix --variants C_graph`.

Phase 18's own bake-off escapes it only because `config.yaml` pins
`matrix.variants: ["B_hybrid"]`. That is luck, not protection.

The suite does not catch it because `tests/test_phase15.py:203,237` constructs
`LightRAGRetriever(...)` directly and never exercises `from_config`. **No test covers
`from_config` on any retriever.**

**Fix — two halves; the second is easy to miss.** Add `max_tokens: int | None = None`
and `timeout_seconds: int = 300` to `__init__`, store them, and then actually forward
them in `_query_data_async` (line ~150), which currently builds `LocalOllamaBinding`
with only `temperature`/`top_p`/`seed`/`num_ctx`. `LocalOllamaBinding` already accepts
both, so without the second half LightRAG queries keep running at the 300-second
binding default while `config.yaml` declares 600.

**Verify:** the reproduce command above must construct without raising, and add a test
that calls `LightRAGRetriever.from_config(load_config())` so this class of defect
cannot ship again.

---

## 2. Phase 18 introduced a circular import

**Reproduce:**

```
.venv/bin/python -c "import vaultledger.retrieve"
```

```
File ".../vaultledger/generate/reliable.py", line 51, in <module>
    from vaultledger.retrieve import Retriever, assemble_context
ImportError: cannot import name 'Retriever' from partially initialized module
'vaultledger.retrieve' (most likely due to a circular import)
```

**Confirm it is new** — the same command in a worktree at `234416d` succeeds:

```
git worktree add /tmp/pre18 234416d
cd /tmp/pre18 && "$OLDPWD/.venv/bin/python" -c "import sys; sys.path.insert(0,'.'); import vaultledger.retrieve; print('PRE-18 OK')"
```

```
PRE-18 OK
```

`vaultledger/graph/ollama_binding.py:18` added `from vaultledger.generate.ollama import
ollama_chat_payload`. That closes the loop `retrieve → graph.ollama_binding → generate
(package __init__) → agentic → reliable → retrieve`, because importing
`vaultledger.generate.ollama` executes `vaultledger/generate/__init__.py`, which pulls
in the whole generation stack.

It is currently masked, not harmless. Both entry points import `generate` before
`retrieve` — `matrix.py:22` before `matrix.py:27`, `streamlit_app.py:305` before
`:309` — purely because isort orders `generate` ahead of `retrieve` alphabetically. Any
new script, test, or module that reaches `vaultledger.retrieve` first fails at import.

**Fix (preferred):** move `ollama_chat_payload` into a leaf module that pulls in no
package `__init__` — it is a pure payload builder with no dependencies beyond
`ollama_model_name`. Failing that, import it lazily inside `_chat_payload`.

**Verify:** add a regression test that shells out to a fresh interpreter, so it is
immune to test-file import order:

```python
subprocess.run([sys.executable, "-c", "import vaultledger.retrieve"], check=True)
```

---

## 3. The decoding-promotion receipt cannot fail — restate what it proves

`receipts/phase18_decoding_defaults.json` reports `byte_identical: true`, and ADR-0014
and the PROGRESS entry both lean on it as the proof the promotion was behaviour-neutral.
The finding is not that the receipt is wrong. It is that **the probe has no
discriminating power**, so it is not evidence for the claim it is carrying.

**Reproduce** — the receipt's exact prompt and schema, at wildly different decoding
settings:

```
.venv/bin/python -c "
import requests, hashlib
PROMPT=('Return a JSON object whose only key is \`phase\` and whose value is the string \`eighteen\`. Return no other text.')
SCHEMA={'type':'object','properties':{'phase':{'type':'string','const':'eighteen'}},'required':['phase'],'additionalProperties':False}
def go(**o):
    r=requests.post('http://localhost:11434/api/generate', json={'model':'qwen3:8b','prompt':PROMPT,'stream':False,'think':False,'format':SCHEMA,'options':o}, timeout=300)
    r.raise_for_status(); return r.json()['response']
for n,o in (('temp0.0',{'temperature':0.0}),('temp1.5/p0.1',{'temperature':1.5,'top_p':0.1,'seed':7}),('temp2.0/p0.05',{'temperature':2.0,'top_p':0.05,'seed':999})):
    x=go(**o); print(n, hashlib.sha256(x.encode()).hexdigest()[:16], repr(x))
"
```

```
temp0.0        b226be22d7d5d5c6  '{"phase": "eighteen"}'
temp1.5/p0.1   b226be22d7d5d5c6  '{"phase": "eighteen"}'
temp2.0/p0.05  b226be22d7d5d5c6  '{"phase": "eighteen"}'
```

All identical, and `b226be22d7d5d5c6…` is the hash already committed in the receipt — so
the receipt reproduces exactly, and would have reproduced under any decoding settings at
all. Two independent reasons: temperature 0 is greedy, and a `const` schema admits one
string.

**The script's real safeguard is sound and should be promoted to the headline.**
`scripts/phase18_decoding_proof.py:74-78` reads the model's own parameters from
`/api/show` and raises if the typed config disagrees. That check is genuine — confirmed
independently this session that `qwen3:8b` reports `top_p 0.95`. *That* is the evidence
for the value, not the byte-identity.

**Fix — wording, not code.** In ADR-0014 and the PROGRESS entry, replace the
byte-identity framing with the accurate one:

> The product decodes greedily at `temperature=0.0`, so promoting `top_p` to explicit
> config cannot change behaviour, and the receipt confirms it. The value `0.95` is
> justified separately, by cross-checking the installed model's own `/api/show`
> parameters — which the proof script enforces on every run.

Optionally add a second probe with an unconstrained prompt at `temperature=0.7` and two
different `top_p` values, to demonstrate the knob is wired to something. Keep it as a
separate receipt; do not overwrite the existing one.

---

## 4. Two of six preregistered grid cells are degenerate — amend ADR-0014 before running

**Reproduce:**

```
.venv/bin/python -c "
import requests, hashlib
P='List three colours and a one-sentence reason for each.'
def run(**opts):
    o={'temperature':0.0,'num_ctx':8192,'seed':42}; o.update(opts)
    r=requests.post('http://localhost:11434/api/chat', json={'model':'qwen3:8b','messages':[{'role':'user','content':P}],'stream':False,'think':False,'options':o}, timeout=600)
    r.raise_for_status(); return r.json()['message']['content']
for p in (0.95, 0.50, 1.0):
    print(p, hashlib.sha256(run(top_p=p).encode()).hexdigest()[:16])
"
```

```
0.95 f3fd08aba7f615b0
0.5  f3fd08aba7f615b0
1.0  f3fd08aba7f615b0
```

`top_p` is inert at temperature 0. The preregistered grid is
`{0.0, 0.3, 0.7} × {1.0, 0.9}`, so cells `(0.0, 1.0)` and `(0.0, 0.9)` are the same
computation as each other **and** as the `(0.0, 0.95)` baseline that ADR-0014 declines
to rerun. Three of the seven "unique decoding profiles" are one profile.

Cost: roughly 160 model calls (2 cells × 80 rows × candidate + judge) that cannot
produce new information, and two cells that can never satisfy the decision rule.

**Fix — choose one, and land it before the first sweep cell runs.**

- **Relabel.** Keep both cells and declare them in ADR-0014 as a determinism control:
  they must score *identically* to the baseline, and any divergence is evidence of
  nondeterminism in the harness (retrieval order, model reload), not of a decoding
  effect. This is the cheaper option and it converts waste into a real check.
- **Replace.** Drop them and spend the budget where the knob is live — e.g. add
  `top_p 0.8` at temperatures 0.3 and 0.7.

Either way this is an amendment to a preregistration, so it must be committed with its
reasoning **before** any cell runs, exactly as the Phase-15 precedent requires. Recording
it afterwards would be indistinguishable from fitting the design to the results.

---

## 5. `top_k` is uncontrolled and absent from `DecodingProfile`

**Reproduce:**

```
for m in qwen3:8b gemma3:12b; do echo -n "$m "; curl -s http://localhost:11434/api/show -d "{\"model\":\"$m\"}" | grep -o 'top_k *[0-9]*' | head -1; done
```

```
qwen3:8b top_k 20
gemma3:12b top_k 64
```

`grep -rn "top_k" vaultledger/ config.yaml` returns only LightRAG's unrelated retrieval
`top_k` — the sampling parameter is never set, so each family runs on its own Modelfile
default.

Severity is narrow but real:

- **The six-model matrix is unaffected.** Every cell runs at temperature 0, where greedy
  decoding ignores `top_k` entirely. The family difference is not a confound there.
- **The sweep cells at temperature 0.3 and 0.7 are affected.** `top_k=20` is silently
  active and is not recorded in `DecodingProfile`, so a manifest advertised as
  self-describing omits a live decoding parameter.

**Fix:** add `top_k` to `Generation` config and to `DecodingProfile`, send it explicitly
in `ollama_chat_payload`, and record it. Pin it as a fixed control in ADR-0014 rather
than sweeping it. If you would rather not change the payload before the run, the minimum
acceptable alternative is to record the observed per-model `top_k` in the manifest and
name it in ADR-0014 as an uncontrolled setting.

---

## 6. Latency medians have survivorship bias

`_cell_metrics` computes `median_wall_latency_ms`, `p95_wall_latency_ms` and the gateway
equivalents over `completed = [row for row in rows if not row.get("error")]`. Rows that
raised — including 600-second timeouts, which is precisely how `qwen3:14b` failed in the
mechanics smoke — are excluded from the latency distribution while still counting against
the model's quality denominator.

A model that times out on its slowest rows therefore appears **faster** than one that
completes them. `write_latency_quality_frontier` plots exactly this quantity on the x
axis.

The existing SVG caveat — "Descriptive only — not a latency ranking" — covers Phase 13's
run-to-run variance, which is a different failure mode and does not warn a reader about
this one.

**Fix:** surface `generation_eval_coverage` (already computed) next to each frontier
point or in its label, and extend the embedded caveat to say latency is measured over
completed rows only. A point at 100% coverage and a point at 60% coverage are not
comparable on that axis and the artifact should say so.

---

## 7. Smaller items

**7a. Brittle pixel assertions.** `tests/test_phase18.py:207-208` asserts
`width="1180" height="720"` and `<rect x="70" y="630" width="1040" height="65"`. These
pin layout constants rather than the property they stand in for — that labels and axes do
not collide. Any cosmetic change breaks them; a real collision that keeps those constants
passes them. Prefer asserting structural facts (one labelled point per manifest, all
labels within the viewBox).

**7b. Record the LightRAG context change in PROGRESS.** ADR-0015 moves LightRAG from
`num_ctx=32768` to the common `8192`. No boundary is violated — Phase 15's recorded
results are untouched, as ADR-0010/ADR-0011 require. But Phase 15's Variant C numbers now
describe a system the code no longer implements, and LightRAG global-mode assembles its
own context, so a 4× smaller window can truncate silently with no test noticing. One
sentence in the PROGRESS entry naming this is enough.

**7c. Empty commit bodies.** All ten Phase 18 commits have subject lines only. The
reasoning is captured in ADR-0014, ADR-0015 and PROGRESS, so nothing is lost, but the
repo's stated discipline is honest commit messages and the earlier phases carry bodies.

---

## Order of work

1. Items **1** and **2** — code defects, independent of the experiment. Land and push.
2. Items **3**, **4** and **5** — claim and preregistration corrections. These must be
   committed **before the first sweep cell runs**.
3. Item **6** — before any frontier is published as a canonical artifact.
4. Item **7** — any time.
5. Then push and **check CI with `gh run list`, do not infer it**. No Phase 18 commit has
   been through CI yet.

**Verify after:** `make test` (expect 192 plus any tests you add), `make lint`,
`make verify-track-a`, corpus hash still `ba7148a1…`, and `gh run list` green.
