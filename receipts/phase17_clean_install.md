# Phase 17 clean-install and launcher receipt

- Date: 2026-08-11 (America/New_York)
- Source revision at start of verification: `5709b480abd0`
- Host: macOS 26.6 (`25G72`), Apple silicon (`arm64`)

This receipt separates evidence that was actually collected from the remaining
handoff gates. It does not claim a fresh macOS user, a clean physical Mac, or an
independent human usability pass.

## Clean Python environment — passed

A new virtual environment was created outside the repository at
`/private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv`. The exact project install
was performed from the repository root:

```console
$ python3 -m venv /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv
$ /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv/bin/python -m pip install -e '.[rerank,gateway,graph]'
$ /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv/bin/python -m spacy download en_core_web_sm
```

Post-install transcript:

```console
$ /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv/bin/python --version
Python 3.14.6

$ /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv/bin/python -c '<import and version probe>'
vaultledger=0.1.0
streamlit=1.61.1
pyarrow=24.0.0
spacy_model=3.8.0
imports=PASS

$ /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv/bin/python -m pip check
No broken requirements found.

$ du -sh /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv
1.9G    /private/tmp/vaultledger-phase17-clean-venv.ur8qFj/venv
```

The import probe covered VaultLedger, ChromaDB, LightRAG, LiteLLM, NetworkX,
PyArrow, sentence-transformers, spaCy, and Streamlit. LiteLLM could not refresh its
optional remote price map in the restricted verification shell and explicitly fell
back to its bundled map; imports still completed. No API key was used.

Streamlit's app harness then executed two consecutive renders from this environment:

```console
first_run_exceptions=0
second_run_exceptions=0
```

The second render matters: during Phase 17 verification, the previously resolved
Streamlit 1.59.1 / PyArrow 25 combination segfaulted while serializing a dataframe on
rerun. Runtime constraints now require `streamlit>=1.61,<2` and `pyarrow>=7,<25`, and
the launcher invalidates environments that do not satisfy that pair.

## Finder launcher and live browser — passed on the development account

- Double-clicked `Launch VaultLedger.command` in Finder; it repaired the existing
  environment, launched Streamlit on `127.0.0.1:8501`, and opened Chrome.
- Double-clicked the launcher again; the existing PID and port were reused, with one
  listener on port 8501 rather than a duplicate server.
- Asked `What was Marcus Chen's March closing balance?` with `B_hybrid` and the
  local `qwen3:8b` model. The live answer was `$4,207.55` with verified citation
  `stmt_marcus_checking_2025-03`, page 1, and snippet `Closing balance: $4,207.55`.
- Asked the measured credit-score question. The live result was `I couldn't find
  that in your documents.`, with no citation and confidence `0.00`.
- Opened the user library and confirmed its external inbox and explicit separation
  from the synthetic evaluation population.

The recruiter walkthrough is `demo/vaultledger_phase17_demo.mp4`: H.264, 1512×982,
30 fps, 112.5 seconds, 2,366,758 bytes. SHA-256:
`f54d4139c682392b34fe021bce0d1270b3bcc54c9758e3bad6d457545ac9a8e4`.

## Readiness and determinism — passed on the development account

`make doctor` was allowed to contact the local Ollama loopback service and reported:

```console
7/7 required checks passed; 1/1 optional capabilities ready.
```

Required local models were present as `nomic-embed-text:latest` (274 MB) and
`qwen3:8b` (5.2 GB). Optional scan support was present as OCRmyPDF 17.10.0 and
Tesseract 5.5.3.

The synthetic chunk corpus stayed byte-identical:

```console
$ shasum -a 256 data/index/chunks.jsonl
ba7148a112191bc81be89636ddbc9ececd90a8a525447814666ee355ae257405  data/index/chunks.jsonl
```

## Gates still open

- **Separate standard macOS user / recipient-half test:** not run. This Mac had no
  spare standard account, and creating one requires operator approval plus macOS
  administrator authentication. The development account test is not substituted for
  that evidence.
- **Independent five-minute cold read:** no human reader was recruited during this
  pass. No usability claim is made from agent review.
- **Homebrew boundary:** OCRmyPDF and Tesseract were already installed system-wide
  on this Mac. A future fresh-user run must not mistake that for proof that the README
  teaches installation of optional OCR tooling from a machine without Homebrew.
