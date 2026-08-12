# Phase 17 close checklist

Opened 2026-08-12 · Phase 17 is **open**, not closed · Companion to
`PHASE17_REVIEW_FIXES_BRIEF.md`

Phase 17 has two unmet acceptance criteria from its own kickoff brief. One of them —
the machine half — is the criterion the phase exists to satisfy, and its brief says
plainly: *"This half must pass."*

> **Machine half proven:** the install completed from a fresh macOS user account,
> with the transcript committed and the Homebrew gap noted.

`receipts/phase17_clean_install.md` is honest that this was not done. It is a new
virtualenv on the build machine under the same user. That is a real and useful
receipt; it is not the machine half.

**The close condition is one afternoon of work, not a waiver.** Phase 15 closed on
ADR-0010 because a *measured* result missed a threshold — the number existed and was
reported. Waiving a gate that was never attempted, when attempting it costs a spare
user account and 45 minutes, is a materially weaker thing to have in this build log.

---

## Part A — code that must land first (Codex)

Sequencing matters. Land A1 and A2 before the run, or the run burns 45 minutes
rediscovering two things already known. A3 and A4 are near-certain to be hit during
the run; fixing them first means one run instead of two.

### A1. Document the Gatekeeper first-launch step — **blocks the run**

`README.md:30-34` tells the recipient to download GitHub's **Download ZIP**, unpack,
and double-click `Launch VaultLedger.command`. A browser-downloaded ZIP carries
`com.apple.quarantine` and extracted files inherit it. Double-clicking an unsigned,
un-notarised `.command` from a quarantined archive does not run it — Finder shows
*"cannot be opened because it is from an unidentified developer."*

The executable bit is fine (`git ls-files -s` shows mode `100755`, and `git archive`
preserves it). Quarantine is the blocker.

Add the first-launch step to the README quickstart: **right-click the file → Open →
Open** in the confirmation dialog. Mention that this is needed once, and why (the app
is not code-signed; ADR-0011 decided against an Apple Developer account). Add the
same note to the launcher's troubleshooting section.

**Status of this finding: Likely, not Verified.** It was reasoned from macOS
behaviour; nobody has downloaded the ZIP and tried. Part B step 4 settles it.

### A2. Fix the first screen a fresh install shows — **blocks the run**

`data/synthetic_pdfs/` and `data/index/` are gitignored (`git ls-files
data/synthetic_pdfs | wc -l` → 1, just `.gitkeep`). The launcher never runs `make
data` / `make ingest` — there is no ingest call anywhere in
`scripts/launch_vaultledger.py`.

The app's default tab is `📚 Library / Ingest` with source `Synthetic evaluation
corpus`, so after a 15–45 minute wait the first thing a ZIP-install user sees is
(`app/streamlit_app.py:153-159`):

> "No synthetic corpus yet. Run `make data && make ingest`, then `make doctor`, or
> click Rebuild after the PDFs exist."

…under a README headline reading **"Start here on a Mac — no Terminal commands."**
Clicking "Rebuild synthetic indexes" raises `FileNotFoundError("no PDFs found in … —
run \`make data\` first")`, caught cleanly at `streamlit_app.py:150` so there is no
traceback, but it repeats the same terminal instruction.

Pick one:

- **Preferred:** have the launcher build the corpus when `data/index/records.db` is
  absent, with visible progress. CI now proves this works without a model runtime —
  `python -m vaultledger.synth && python -m vaultledger.ingest --no-embed` — so the
  launcher can do the same before starting Streamlit, then let the vector index build
  on first use.
- **Cheaper:** default the Library tab to **User documents** on a fresh install, and
  reword the empty state so it names no `make` target.

The user-documents path in README step 5 does work without the corpus, so the demo is
survivable either way — but the copy and the first screen currently contradict each
other, and this is the screen the phase is judged on.

### A3. `Ctrl-C` during setup prints a raw traceback

`scripts/launch_vaultledger.py:467-472`:

```python
except (LauncherError, OSError, subprocess.CalledProcessError, urllib.error.URLError) as exc:
```

`KeyboardInterrupt` derives from `BaseException`, not `Exception`, and is not in that
tuple. `launch()`'s `except Exception` at :439 also misses it, so the Streamlit child
is not terminated on that path either. The README tells the user to sit through a
5.2 GB download in a Terminal window; Ctrl-C is the single most likely impatient-user
action.

Add `except KeyboardInterrupt` → print *"Setup cancelled. Nothing was changed."* and
return 130. Add `ValueError` to the tuple as well: `ollama_model_names()` at :226 is
called outside any `try`, so a truncated `/api/tags` body raises
`json.JSONDecodeError` straight through `main()`.

### A4. Ollama detection gates on the CLI symlink, not the running service

`scripts/launch_vaultledger.py:200-206` runs `shutil.which("ollama")` *before* the
HTTP probe at :209. The macOS `.dmg` installs `Ollama.app`; the
`/usr/local/bin/ollama` symlink is a separate admin-authenticated prompt on first
open. A user who installed the app, has it running and serving on
`127.0.0.1:11434` with both models pulled, but declined the CLI prompt, is told
*"Ollama is not installed"* and sent back to the download page.

Probe the loopback endpoint first; fall back to the `which`/download flow only when it
is unreachable. Check `/Applications/Ollama.app` before declaring "not installed."

### A5–A7 — after the run, not before

- **A5.** Stale-lock race at `:349` raises an unguarded `FileExistsError`, shown to
  the user as `[Errno 17] File exists: /var/folders/…`. Wrap in
  `try/except FileExistsError: return False`.
- **A6.** `find_available_port` (`:276-295`) never sets `SO_REUSEADDR`, so quitting and
  immediately relaunching spuriously reports 8501 busy and opens 8502. Set the
  sockopt; treat the port as advisory and retry once on a Streamlit bind failure.
- **A7.** `explain_ocr` grammar when both tools are missing: *"…because ocrmypdf,
  tesseract **is** missing."* (`:257-262`)

---

## Part B — the machine-half run (Abhinav; nobody else can do this)

Budget **45–60 minutes**, most of it download. Do this on the same Mac.

### B0. When to run this — split it in two

There is a real argument for deferring the full run to just before handoff:
**Phase 18 can invalidate it.** The launcher pulls `qwen3:8b` and the README quotes
its 5.2 GB download. If the bake-off changes the pinned model, the download size, the
wait, the first-run flow and the demo all change — and the machine-half receipt would
have to be regenerated anyway. Run it twice, or run it once at the end.

But one part of it cannot wait, because it can invalidate a **decision** rather than a
receipt:

> **Does double-clicking a downloaded `.command` work at all for a non-technical user?**

If Gatekeeper makes that unworkable, ADR-0011's entire distribution decision — browser
UI plus one-click launcher, native shell deferred, no Apple Developer account — comes
back open. The deferred alternative costs $99 and a notarisation workflow. Discovering
that the week of handoff, with no schedule slack, is the bad outcome. Discovering it
now costs ten minutes.

**So split it:**

- **Now (~10 min): the smoke test.** Part B1, then B3 steps 1–5 only. Create the
  account, download the ZIP, double-click, record exactly what happens, and continue
  only far enough to confirm the launcher starts doing something visible. **Abort
  before the model download.** You are answering one question: does the documented
  entry point work, and if not, what does the user see. This does not need A2, A3 or
  A4 landed — only A1, and arguably not even that, since finding out whether
  Gatekeeper blocks it is the point.
- **Before handoff (~45–60 min): the full run.** All of Part B, after Phase 18 has
  settled the model pin, with A1–A4 landed. This is what produces
  `receipts/phase17_machine_half.md`.

**Be honest about what that means for the phase.** Closing 17 on the smoke test alone
is a **waiver** — the stated criterion is a completed install, not a successful
double-click. If you take that route, write it as a waiver in `PROGRESS.md` with the
full run named and scheduled, the way ADR-0010 handled Phase 15. What you must not do
is close 17 quietly and let "machine half" read as met. The one thing this phase exists
to eliminate is an untested install claim.

### B1. Create the test account

System Settings → Users & Groups → Add User.

Make it an **Administrator**, not Standard. The recipient is a hiring manager on their
own Mac, who is an admin there; a Standard account tests something stricter than
reality and would fail on the Ollama CLI prompt for a reason the real recipient will
never hit. **Record that the Standard-user path is therefore untested.**

Name it something obvious like `vltest` so the transcript's paths are self-evidently
not yours.

### B2. Know what this does and does not prove — before you start

**Tests for real:** no virtualenv, no repo, no model cache (`~/.ollama` is per-user, so
weights genuinely re-download), no PATH additions, no Streamlit config, and Gatekeeper
quarantine on a genuinely downloaded ZIP.

**Cannot test, because it is system-wide:** a missing Homebrew (`/opt/homebrew`), a
missing `Ollama.app` (`/Applications`). Record both as gaps rather than papering over
them — the kickoff brief asks for exactly this.

**One prediction worth watching.** Homebrew adds `/opt/homebrew/bin` to PATH via the
*user's own* `~/.zprofile`, which a brand-new account does not have. A `.command` file
opens in Terminal as a login shell, so the launcher's `python3.14 … python3` probe will
likely see only `/usr/bin/python3` — which is **3.9.6** on this machine, below the
launcher's own ≥3.11 gate. If so, the run will exercise the **python.org download
branch, which has never been executed**. That is the single most valuable thing this
run can surface. Record precisely what happens, either way.

This also means the receipt's existing Homebrew note is narrower than the real gap:
the current transcript's "clean" venv was built from Homebrew's Python
(`pyvenv.cfg` → `/opt/homebrew/opt/python@3.14/bin`), so the interpreter, not just
`ocrmypdf`/Tesseract, came from Homebrew.

### B3. Run it exactly as the README tells a stranger to

Do **not** shortcut any step because you know a faster one. The point is to execute
the documented path.

1. Log in as the test user.
2. Open Safari → the GitHub repo → **Code → Download ZIP**. (`main` is pushed, so the
   ZIP now contains the launcher — it did not before 2026-08-12.)
3. Double-click the ZIP once to unpack.
4. Open `vaultledger-main` and **double-click `Launch VaultLedger.command`.**
   **Record what happens here verbatim.** This is the A1 test. If Gatekeeper blocks
   it, note the exact dialog text, then use right-click → Open and continue.
5. Follow whatever the launcher says. Do not fix anything from another Terminal. If
   it tells you to install Python or Ollama, do that as instructed and re-launch.
6. Time the wait from launcher start to the browser opening. Note whether progress
   stayed visible or looked like a hang.
7. When the app opens, note **the first screen you see** — this is the A2 test.
8. Ask one question over the synthetic corpus. Confirm you get an answer with a
   citation.
9. Copy a PDF into `~/VaultLedger/Inbox`, scan it in Library / Ingest, ask a question
   over it in Ask. This is the criterion's real target: *answers a question over their
   own document*.
10. Quit. Double-click the launcher a second time — confirm it reopens rather than
    starting a second copy.

### B4. Capture as you go

Keep a scratch file open. For each step: what you did, what appeared, how long it
took. Copy Terminal output verbatim rather than summarising — the transcript's value
is that it is not a summary. Screenshot anything that looks wrong.

---

## Part C — what to record, in both outcomes

Write `receipts/phase17_machine_half.md` alongside the existing receipt. Do not edit
the existing one; it is accurate about what it did.

**If it succeeds**, the receipt states: the macOS version and build, that the account
was a freshly created Administrator on the same physical Mac, wall-clock time to first
answer, the download sizes actually observed, whether Gatekeeper intervened and what
resolved it, which Python the launcher found and from where, that Homebrew and
`Ollama.app` were pre-existing and system-wide, and that the Standard-user path is
untested.

The sentence the kickoff brief explicitly forbids is *"installs cleanly on a fresh
Mac."* The sentence it explicitly endorses is closer to: *"the launcher was run from a
freshly created macOS user account with no virtualenv, repo, model cache, or shell
configuration, and reached a working install; Homebrew and Ollama.app were already
present system-wide and are not covered by this evidence."*

**If it fails**, the failure is the finding. Record where it stopped, what the user saw,
and what you had to do to get past it — then fix that and run again. Do not run it
repeatedly and record only the successful pass. A first-attempt failure that got fixed
is *better* evidence than a clean run, because it names a real defect the build machine
could never surface.

**Either way**, the human half stays as it is. `README.md:60-62` currently says no
independent non-technical reader has done the five-minute cold read. That remains true
and correctly stated — you are not an independent reader of your own instructions. If
you can get any non-technical person to spend five minutes answering only *"what would
you do first, and where would you stop?"*, record it. If not, leave the existing
sentence exactly as written.

---

## Part D — close criteria

Phase 17 closes when all of these hold:

- [ ] A1 and A2 landed; A3 and A4 landed.
- [ ] The machine-half run was performed from a freshly created macOS user account.
- [ ] `receipts/phase17_machine_half.md` committed, with the Homebrew and
      `Ollama.app` gaps and the untested Standard-user path stated explicitly.
- [ ] Any defect the run surfaced is either fixed or recorded as a known limitation
      with a named owner phase.
- [ ] Brief items 2, 3 and 4 landed (stale claims, context budget, `verify-track-a`).
- [ ] `make test` and `make lint` green; **CI green**; corpus hash still
      `ba7148a112191bc8…`.
- [ ] A `PROGRESS.md` entry that distinguishes the two halves and does not describe
      the machine half as more than it is.
- [ ] `CLAUDE.md`'s Status section updated — it still says "Phases 0–16 are closed"
      and is silent on 17.

**Then** open Phase 18. ADR-0011 put the product ahead of the bake-off deliberately;
the bake-off is not waiting on anything.
